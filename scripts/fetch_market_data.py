"""
Récupère les données marché et les écrit dans _data/market.json :
- Brent (OilPriceAPI -> secret OILPRICEAPI_KEY, repli sur EIA -> secret EIA_API_KEY)
- Henry Hub, gaz naturel US (OilPriceAPI, repli sur EIA)
- Mix électrique France en temps réel (RTE eco2mix API v2, aucune clé requise)
- Prix spot électricité France day-ahead, moyenne journalière des prix horaires
  (RTE Wholesale Market v3, OAuth2 -> secret RTE_BASE64_KEY)
- Trafic maritime par détroit stratégique (IMF PortWatch, AIS, aucune clé requise),
  avec historique 90 jours dans _data/chokepoints_history.json
- Brent sur 12 mois (EIA) pour le graphique Ormuz / Brent : _data/brent_year.json
- Exportations mensuelles de GNL des États-Unis (EIA) : _data/lng_exports.json
- Prix mondiaux du gaz par mois (FMI via la FRED) : Europe, Asie, États-Unis : _data/gas_world.json
- Stocks de gaz en Europe et en France (GIE AGSI+ -> secret GIE_API_KEY) : _data/gas_storage.json

Garde aussi un historique (_data/market_history.json, 60 derniers jours) et calcule
un résumé hebdomadaire (_data/weekly_summary.json). Chaque prix de l'historique est
rangé à la date du prix lui-même (pas à la date du run) et porte sa source.

En cas d'échec sur une source, on garde l'ancienne valeur (le site ne casse jamais).
"""
import json
import os
import sys
import datetime
from zoneinfo import ZoneInfo

import requests

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "market.json")
HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "market_history.json")
WEEKLY_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "weekly_summary.json")
HISTORY_MAX_DAYS = 60
PARIS = ZoneInfo("Europe/Paris")

EIA_API_KEY = os.environ.get("EIA_API_KEY", "")
RTE_BASE64_KEY = os.environ.get("RTE_BASE64_KEY", "")
GIE_API_KEY = os.environ.get("GIE_API_KEY", "")
OILPRICEAPI_KEY = os.environ.get("OILPRICEAPI_KEY", "")


def load_existing():
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
DAYS_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def last_trading_day(date_str):
    """Samedi ou dimanche -> vendredi précédent (bourses fermées le week-end)."""
    d = datetime.date.fromisoformat(date_str[:10])
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)
    return d


def label_quote(entry):
    """Date de cotation + libellé affiché sur les cartes Brent / Henry Hub.

    Le week-end, OilPriceAPI renvoie la clôture du vendredi datée du jour de la
    collecte : on la rattache au vendredi et on l'écrit clairement.
    """
    if not entry or not entry.get("date"):
        return entry
    trading = last_trading_day(entry["date"])
    entry["date"] = trading.isoformat()
    today = datetime.datetime.now(PARIS).date()
    day = f"{JOURS[trading.weekday()]} {trading:%d/%m}"
    day_en = f"{DAYS_EN[trading.weekday()]} {trading:%d/%m}"
    if trading >= today:
        entry["date_label"] = f"Cours du {day}"
        entry["date_label_en"] = f"Price on {day_en}"
    elif trading == last_trading_day(today.isoformat()):
        entry["date_label"] = f"Clôture du {day} (bourse fermée le week-end)"
        entry["date_label_en"] = f"Close on {day_en} (market closed at weekends)"
    else:
        # En semaine, un prix qui n'est pas du jour : source en retard ou en panne
        entry["date_label"] = f"Dernier cours connu : {day}"
        entry["date_label_en"] = f"Last known price: {day_en}"
    return entry


def oilpriceapi_date(row):
    # as_of = heure de la cotation sur le marché (ex. clôture du vendredi),
    # created_at = heure à laquelle OilPriceAPI l'a collectée
    return row.get("as_of") or row.get("created_at") or row.get("timestamp")


def fetch_eia_series(series_code, length):
    """{date: valeur} des `length` derniers jours publiés par l'EIA pour une série."""
    url = (
        "https://api.eia.gov/v2/petroleum/pri/spt/data/"
        if series_code == "RBRTE"
        else "https://api.eia.gov/v2/natural-gas/pri/fut/data/"
    )
    url += (
        f"?api_key={EIA_API_KEY}&frequency=daily&data[0]=value"
        f"&facets[series][]={series_code}&sort[0][column]=period&sort[0][direction]=desc&length={length}"
    )
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    rows = r.json()["response"]["data"]
    return {row["period"]: round(float(row["value"]), 2) for row in rows}


def fetch_brent_oilpriceapi():
    """Brent via OilPriceAPI, mis à jour toutes les 5 minutes (plan gratuit)."""
    if not OILPRICEAPI_KEY:
        return None
    url = "https://api.oilpriceapi.com/v1/prices/latest?by_code=BRENT_CRUDE_USD"
    r = requests.get(url, headers={"Authorization": f"Token {OILPRICEAPI_KEY}"}, timeout=15)
    r.raise_for_status()
    payload = r.json()
    row = payload.get("data") or payload
    price = row.get("price")
    if price is None:
        raise ValueError(f"champ prix introuvable, réponse reçue: {payload}")
    timestamp = oilpriceapi_date(row)
    return {
        "price_usd": round(float(price), 2),
        "date": (timestamp or "")[:10],
        "unit": "USD/baril",
        "source": "OilPriceAPI",
    }


def fetch_brent(existing):
    try:
        result = fetch_brent_oilpriceapi()
        if result:
            return result
    except Exception as e:
        print(f"Erreur Brent (OilPriceAPI), repli sur EIA: {e}")

    if not EIA_API_KEY:
        print("EIA_API_KEY manquant, on garde l'ancienne valeur Brent.")
        return existing.get("brent")
    try:
        url = (
            "https://api.eia.gov/v2/petroleum/pri/spt/data/"
            f"?api_key={EIA_API_KEY}&frequency=daily&data[0]=value"
            "&facets[series][]=RBRTE&sort[0][column]=period&sort[0][direction]=desc&length=1"
        )
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        row = r.json()["response"]["data"][0]
        return {
            "price_usd": round(float(row["value"]), 2),
            "date": row["period"],
            "unit": "USD/baril",
            "source": "EIA",
        }
    except Exception as e:
        print(f"Erreur Brent (EIA): {e}")
        return existing.get("brent")


def fetch_henry_hub_oilpriceapi():
    """Henry Hub via OilPriceAPI, mis à jour toutes les 5 minutes."""
    if not OILPRICEAPI_KEY:
        return None
    url = "https://api.oilpriceapi.com/v1/prices/latest?by_code=NATURAL_GAS_USD"
    r = requests.get(url, headers={"Authorization": f"Token {OILPRICEAPI_KEY}"}, timeout=15)
    r.raise_for_status()
    payload = r.json()
    row = payload.get("data") or payload
    price = row.get("price")
    if price is None:
        raise ValueError(f"champ prix introuvable, réponse reçue: {payload}")
    timestamp = oilpriceapi_date(row)
    return {
        "price_usd_mmbtu": round(float(price), 2),
        "date": (timestamp or "")[:10],
        "unit": "USD/MMBtu",
        "source": "OilPriceAPI",
    }


def fetch_henry_hub(existing):
    try:
        result = fetch_henry_hub_oilpriceapi()
        if result:
            return result
    except Exception as e:
        print(f"Erreur Henry Hub (OilPriceAPI), repli sur EIA: {e}")

    if not EIA_API_KEY:
        print("EIA_API_KEY manquant, on garde l'ancienne valeur Henry Hub.")
        return existing.get("henry_hub")
    try:
        url = (
            "https://api.eia.gov/v2/natural-gas/pri/fut/data/"
            f"?api_key={EIA_API_KEY}&frequency=daily&data[0]=value"
            "&facets[series][]=RNGWHHD&sort[0][column]=period&sort[0][direction]=desc&length=1"
        )
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        row = r.json()["response"]["data"][0]
        return {
            "price_usd_mmbtu": round(float(row["value"]), 2),
            "date": row["period"],
            "unit": "USD/MMBtu",
            "source": "EIA",
        }
    except Exception as e:
        print(f"Erreur Henry Hub (EIA): {e}")
        return existing.get("henry_hub")


def fetch_mix_france(existing):
    try:
        url = (
            "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
            "eco2mix-national-tr/records"
            "?order_by=date_heure%20desc&limit=1&where=nucleaire%20is%20not%20null"
        )
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        payload = r.json()
        results = payload.get("results") or payload.get("records") or []
        if not results:
            raise ValueError("aucun enregistrement retourné par l'API v2")

        raw = results[0]
        if "record" in raw and isinstance(raw["record"], dict):
            rec = raw["record"].get("fields", raw["record"])
        elif "fields" in raw and isinstance(raw["fields"], dict):
            rec = raw["fields"]
        else:
            rec = raw

        sources = {
            "nucleaire": rec.get("nucleaire"),
            "eolien": rec.get("eolien"),
            "solaire": rec.get("solaire"),
            "hydraulique": rec.get("hydraulique"),
            "gaz": rec.get("gaz"),
            "thermique": rec.get("thermique"),
            "bioenergies": rec.get("bioenergies"),
        }
        sources = {k: v for k, v in sources.items() if v is not None and v > 0}
        total = sum(sources.values())
        if total <= 0:
            raise ValueError(f"total de production nul, clés reçues: {list(rec.keys())[:15]}")

        # Du plus gros au plus petit contributeur, pour l'affichage
        shares = {k: round(v / total * 100, 1) for k, v in sorted(sources.items(), key=lambda kv: -kv[1])}
        top = sorted(shares.items(), key=lambda kv: kv[1], reverse=True)

        co2 = rec.get("taux_co2")

        return {
            "date_heure": rec.get("date_heure"),
            "shares": shares,
            "top_source": top[0][0],
            "top_share": top[0][1],
            "co2_intensity": round(co2, 0) if co2 is not None else None,
        }
    except Exception as e:
        print(f"Erreur mix RTE: {e}")
        return existing.get("mix_france")


def get_rte_token():
    r = requests.post(
        "https://digital.iservices.rte-france.com/token/oauth/",
        headers={"Authorization": f"Basic {RTE_BASE64_KEY}"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def fetch_power_exchanges(token, start, end):
    """Prix day-ahead France entre deux datetimes (avec fuseau), tels que renvoyés par RTE."""
    url = "https://digital.iservices.rte-france.com/open_api/wholesale_market/v3/france_power_exchanges"
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        params={
            "start_date": start.isoformat(timespec="seconds"),
            "end_date": end.isoformat(timespec="seconds"),
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("france_power_exchanges") or []


def _spot_value(v):
    # Test explicite sur None : un prix à 0 ou négatif est un vrai prix
    for key in ("price", "value", "spot_price"):
        if v.get(key) is not None:
            return float(v[key])
    return None


def _paris_day(timestamp):
    """Date (heure de Paris) d'un horodatage RTE, quel que soit son fuseau."""
    if not timestamp:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(PARIS)
        return dt.date().isoformat()
    except ValueError:
        return timestamp[:10]


def daily_spot_averages(periods):
    """{date: moyenne des prix horaires du jour}, en ne gardant que les journées complètes."""
    by_day, base_load = {}, {}
    for period in periods:
        values = period.get("values") or []
        for v in values:
            day = _paris_day(v.get("start_date"))
            price = _spot_value(v)
            if day and price is not None:
                by_day.setdefault(day, []).append(price)
        if not values and period.get("base_load") is not None:
            day = _paris_day(period.get("start_date"))
            if day:
                base_load[day] = round(float(period["base_load"]), 2)

    result = dict(base_load)
    if by_day:
        # Une journée complète a au moins 24 prix (23 ou 25 aux changements d'heure,
        # 96 en pas de 15 min) : on écarte les journées tronquées
        full = max(24, max(len(p) for p in by_day.values()))
        for day, p in by_day.items():
            if len(p) >= 0.9 * full:
                result[day] = round(sum(p) / len(p), 2)
    return result


def fetch_spot_price_france(existing):
    if not RTE_BASE64_KEY:
        print("RTE_BASE64_KEY manquant, on garde l'ancienne valeur spot.")
        return existing.get("spot_price_france")
    try:
        token = get_rte_token()
        now = datetime.datetime.now(PARIS).replace(microsecond=0)
        midnight = now.replace(hour=0, minute=0, second=0)
        start = midnight - datetime.timedelta(days=3)
        try:
            # Les prix du jour sont publiés la veille : on demande jusqu'à minuit ce soir
            periods = fetch_power_exchanges(token, start, midnight + datetime.timedelta(days=1))
        except requests.HTTPError:
            periods = fetch_power_exchanges(token, start, now)

        today = midnight.date().isoformat()
        daily = {d: p for d, p in daily_spot_averages(periods).items() if d <= today}
        if not daily:
            raise ValueError(f"aucune journée complète retournée ({len(periods)} périodes)")

        last_day = max(daily)
        d = datetime.date.fromisoformat(last_day)
        return {
            "price_eur_mwh": daily[last_day],
            "date": last_day,
            "date_label": f"Moyenne du {JOURS[d.weekday()]} {d:%d/%m}",
            "date_label_en": f"Average for {DAYS_EN[d.weekday()]} {d:%d/%m}",
            "unit": "EUR/MWh, moyenne journalière",
            "source": "RTE",
            "daily": daily,
        }
    except Exception as e:
        print(f"Erreur RTE spot: {e}")
        return existing.get("spot_price_france")


CHOKEPOINTS = {
    "hormuz": "Hormuz",
    "bab_el_mandeb": "Bab",
    "malacca": "Malacca",
}

PORTWATCH_DAILY_URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
    "Daily_Chokepoints_Data/FeatureServer/0/query"
)
CHOKEPOINTS_HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "chokepoints_history.json")
BRENT_YEAR_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "brent_year.json")
LNG_EXPORTS_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "lng_exports.json")
GAS_WORLD_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "gas_world.json")
# Séries FRED (FMI, moyennes mensuelles en $/MMBtu)
GAS_WORLD_SERIES = {"europe": "PNGASEUUSDM", "asie": "PNGASJPUSDM", "usa": "PNGASUSUSDM"}
GAS_WORLD_MONTHS = 120
GAS_STORAGE_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "gas_storage.json")
TRAFFIC_FIELDS = ("n_tanker", "n_total", "capacity_tanker")
CHOKEPOINT_HISTORY_DAYS = 90

# « Normale » = moyenne journalière de janvier à octobre 2023 : avant les attaques en
# mer Rouge (nov. 2023) et avant la fermeture d'Ormuz. La base annuelle de PortWatch
# était déjà tirée vers le bas par ces crises (Bab-el-Mandeb surtout).
REFERENCE_START, REFERENCE_END = "2023-01-01", "2023-10-31"
REFERENCE_LABEL = "janv.-oct. 2023"


def _portwatch_date(value):
    if isinstance(value, (int, float)):
        return datetime.datetime.utcfromtimestamp(value / 1000).strftime("%Y-%m-%d")
    return str(value)[:10]


def portwatch_daily(name_fragment, count, extra_where=""):
    """Passages quotidiens d'un détroit (IMF PortWatch), du plus ancien au plus récent."""
    r = requests.get(PORTWATCH_DAILY_URL, params={
        "where": f"UPPER(portname) LIKE UPPER('%{name_fragment}%'){extra_where}",
        "outFields": "date,portname," + ",".join(TRAFFIC_FIELDS),
        "orderByFields": "date DESC",
        "resultRecordCount": count,
        "f": "json",
    }, timeout=30)
    r.raise_for_status()
    features = r.json().get("features") or []
    if not features:
        raise ValueError(f"aucun enregistrement PortWatch pour {name_fragment}")
    rows = [{"date": _portwatch_date(f["attributes"]["date"]),
             **{k: f["attributes"].get(k) for k in TRAFFIC_FIELDS}} for f in features]
    return sorted(rows, key=lambda row: row["date"]), features[0]["attributes"].get("portname")


def _mean(rows, field):
    values = [row[field] for row in rows if row.get(field) is not None]
    return sum(values) / len(values) if values else None


def fetch_chokepoint_reference(name_fragment):
    rows, _ = portwatch_daily(
        name_fragment, 400,
        f" AND date >= DATE '{REFERENCE_START}' AND date <= DATE '{REFERENCE_END}'")
    return {
        "ref_tanker": round(_mean(rows, "n_tanker"), 1),
        "ref_total": round(_mean(rows, "n_total"), 1),
        "ref_capacity_tanker_mt": round(_mean(rows, "capacity_tanker") / 1e6, 2),
        "ref_period": REFERENCE_LABEL,
    }


def classify_traffic_status(current, baseline):
    """Retourne 'fluide', 'partiel' ou 'ferme' selon le ratio trafic actuel / moyenne normale."""
    try:
        current = float(current)
        baseline = float(baseline)
    except (TypeError, ValueError):
        return None
    if baseline <= 0:
        return None
    ratio = current / baseline
    if ratio >= 0.8:
        return "fluide"
    elif ratio >= 0.4:
        return "partiel"
    else:
        return "ferme"


def _pct(value, ref):
    return round(value / ref * 100) if value is not None and ref else None


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def fetch_chokepoint_traffic(existing):
    """Trafic par détroit via IMF PortWatch (AIS satellite, gratuit, sans clé).

    Valeurs du jour = moyenne des 5 derniers jours publiés (lisse les anomalies de
    couverture). Renvoie aussi l'historique sur 90 jours (et 12 mois pour Ormuz),
    écrit à part dans _data/chokepoints_history.json pour les graphiques.
    """
    existing_traffic = existing.get("chokepoints", {}) or {}
    history = load_json(CHOKEPOINTS_HISTORY_PATH, {})
    result = {}

    for key, name_fragment in CHOKEPOINTS.items():
        try:
            rows, portname = portwatch_daily(name_fragment, CHOKEPOINT_HISTORY_DAYS)
            last5 = rows[-5:]
            latest_date = rows[-1]["date"]
            n_tanker, n_total = _mean(last5, "n_tanker"), _mean(last5, "n_total")
            capacity = _mean(last5, "capacity_tanker")

            # La normale ne change pas : on ne la redemande que si elle manque
            prev = existing_traffic.get(key) or {}
            if prev.get("ref_period") == REFERENCE_LABEL and prev.get("ref_total"):
                ref = {k: prev[k] for k in ("ref_tanker", "ref_total", "ref_capacity_tanker_mt", "ref_period")}
            else:
                ref = fetch_chokepoint_reference(name_fragment)

            capacity_mt = round(capacity / 1e6, 2) if capacity is not None else None
            result[key] = {
                "portname": portname,
                "date": latest_date,
                "age_days": (datetime.date.today() - datetime.date.fromisoformat(latest_date)).days,
                "period_start": last5[0]["date"],
                "days_averaged": len(last5),
                "n_tanker": round(n_tanker, 1) if n_tanker is not None else None,
                "n_total": round(n_total, 1) if n_total is not None else None,
                "capacity_tanker_mt": capacity_mt,
                **ref,
                "pct_tanker": _pct(n_tanker, ref["ref_tanker"]),
                "pct_total": _pct(n_total, ref["ref_total"]),
                "pct_capacity": _pct(capacity_mt, ref["ref_capacity_tanker_mt"]),
                "status": classify_traffic_status(n_total, ref["ref_total"]),
            }
            history[key] = rows
            if key == "hormuz":
                history["hormuz_year"], _ = portwatch_daily(name_fragment, 366)
        except Exception as e:
            print(f"Erreur trafic {key}: {e}")
            result[key] = existing_traffic.get(key)

    os.makedirs(os.path.dirname(CHOKEPOINTS_HISTORY_PATH), exist_ok=True)
    with open(CHOKEPOINTS_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, separators=(",", ":"))
    return result


def update_brent_year():
    """Brent sur 12 mois (EIA, clôtures quotidiennes) pour le graphique Ormuz / Brent."""
    if not EIA_API_KEY:
        print("EIA_API_KEY manquant, Brent 12 mois non mis à jour.")
        return
    try:
        series = fetch_eia_series("RBRTE", 400)
    except Exception as e:
        print(f"Erreur Brent 12 mois (EIA): {e}")
        return
    rows = [{"date": d, "v": v} for d, v in sorted(series.items())]
    with open(BRENT_YEAR_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))


def update_lng_exports():
    """Exportations mensuelles de GNL des États-Unis sur 25 mois (EIA, série N9133US2),
    converties de millions de pieds cubes par mois en milliards de pieds cubes par jour."""
    if not EIA_API_KEY:
        print("EIA_API_KEY manquant, exportations de GNL non mises à jour.")
        return
    try:
        r = requests.get(
            "https://api.eia.gov/v2/natural-gas/move/expc/data/"
            f"?api_key={EIA_API_KEY}&frequency=monthly&data[0]=value&facets[series][]=N9133US2"
            "&sort[0][column]=period&sort[0][direction]=desc&length=25",
            timeout=20,
        )
        r.raise_for_status()
        rows = r.json()["response"]["data"]
    except Exception as e:
        print(f"Erreur exportations de GNL (EIA): {e}")
        return
    out = []
    for row in sorted(rows, key=lambda x: x["period"]):
        if row.get("value") in (None, ""):
            continue
        year, month = map(int, row["period"].split("-"))
        nxt = datetime.date(year + month // 12, month % 12 + 1, 1)
        days = (nxt - datetime.date(year, month, 1)).days
        out.append({"month": row["period"], "bcfd": round(float(row["value"]) / days / 1000, 2)})
    if out:
        with open(LNG_EXPORTS_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, separators=(",", ":"))


def fetch_fred_monthly(series_id, months):
    """Série mensuelle de la FRED (fichier CSV officiel), {mois 'AAAA-MM': valeur}."""
    r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}", timeout=30)
    r.raise_for_status()
    out = {}
    for line in r.text.strip().splitlines()[1:]:
        day, _, value = line.partition(",")
        if value and value != ".":
            out[day[:7]] = round(float(value), 2)
    return dict(sorted(out.items())[-months:])


def update_gas_world():
    """Prix mondiaux du gaz, moyennes mensuelles du FMI (Primary Commodity Prices) via la FRED :
    Europe (TTF), Asie (GNL livré au Japon), États-Unis (Henry Hub), en $/MMBtu, sur 10 ans.
    En cas d'erreur, on garde le fichier existant."""
    try:
        data = {key: [{"month": m, "v": v} for m, v in fetch_fred_monthly(sid, GAS_WORLD_MONTHS).items()]
                for key, sid in GAS_WORLD_SERIES.items()}
    except Exception as e:
        print(f"Erreur prix mondiaux du gaz (FRED): {e}")
        return
    with open(GAS_WORLD_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def fetch_agsi(params, start, end):
    """Remplissage des stockages de gaz (GIE AGSI+), [{date, full (%), twh}] du plus ancien au plus récent."""
    rows, page = [], 1
    while True:
        r = requests.get("https://agsi.gie.eu/api", headers={"x-key": GIE_API_KEY}, timeout=30,
                         params=dict(params, **{"from": start, "to": end, "size": 300, "page": page}))
        r.raise_for_status()
        payload = r.json()
        rows += payload.get("data", [])
        if page >= int(payload.get("last_page") or 1):
            break
        page += 1
    out = {}
    for row in rows:
        try:
            out[row["gasDayStart"]] = {"date": row["gasDayStart"], "full": round(float(row["full"]), 2),
                                       "twh": round(float(row["gasInStorage"]), 1)}
        except (KeyError, TypeError, ValueError):
            continue
    return [out[d] for d in sorted(out)]


def update_gas_storage():
    """Stocks de gaz de l'UE et de la France, du 1er janvier de l'an dernier à aujourd'hui
    (pour comparer à l'an dernier à la même date). En cas d'erreur, on garde le fichier existant."""
    if not GIE_API_KEY:
        print("GIE_API_KEY manquant, stocks de gaz non mis à jour.")
        return
    today = datetime.date.today()
    start = datetime.date(today.year - 1, 1, 1).isoformat()
    try:
        data = {
            "eu": fetch_agsi({"type": "eu"}, start, today.isoformat()),
            "fr": fetch_agsi({"country": "FR"}, start, today.isoformat()),
        }
    except Exception as e:
        print(f"Erreur stocks de gaz (GIE AGSI+): {e}")
        return
    if not data["eu"]:
        print("Stocks de gaz : réponse vide, on garde le fichier existant.")
        return
    with open(GAS_STORAGE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def load_history():
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


SOURCE_FIELDS = {
    "brent_usd": "brent_source",
    "henry_hub_usd_mmbtu": "henry_hub_source",
    "spot_eur_mwh": "spot_source",
}


def history_entry(history, date):
    entry = next((h for h in history if h.get("date") == date), None)
    if entry is None:
        entry = {"date": date}
        history.append(entry)
    return entry


def set_history_value(history, date, field, value, source):
    """Écrit une valeur à la date du prix (pas à la date du run), avec sa source."""
    if not date or value is None:
        return
    entry = history_entry(history, date)
    entry[field] = value
    entry[SOURCE_FIELDS[field]] = source


def is_weekend(date_str):
    return datetime.date.fromisoformat(date_str[:10]).weekday() >= 5


def append_to_history(history, data, spot_daily):
    today = datetime.date.today().isoformat()

    # Brent et Henry Hub ne cotent pas le week-end : une valeur datée samedi ou
    # dimanche n'est que la clôture du vendredi répétée
    brent = data.get("brent") or {}
    if brent.get("date") and not is_weekend(brent["date"]):
        set_history_value(history, brent["date"], "brent_usd",
                          brent.get("price_usd"), brent.get("source", "EIA"))

    henry = data.get("henry_hub") or {}
    if henry.get("date") and not is_weekend(henry["date"]):
        set_history_value(history, henry["date"], "henry_hub_usd_mmbtu",
                          henry.get("price_usd_mmbtu"), henry.get("source", "EIA"))

    # Jours de cotation encore vides (run manqué, panne OilPriceAPI) : comblés avec
    # l'EIA, qui publie avec quelques jours de retard. Ne remplace jamais une valeur.
    if EIA_API_KEY:
        for series, field in (("RBRTE", "brent_usd"), ("RNGWHHD", "henry_hub_usd_mmbtu")):
            try:
                for day, value in fetch_eia_series(series, 15).items():
                    entry = next((h for h in history if h.get("date") == day), {})
                    if entry.get(field) is None:
                        set_history_value(history, day, field, value, "EIA")
            except Exception as e:
                print(f"Erreur complément EIA {series}: {e}")

    # Spot : moyenne journalière de chaque journée complète renvoyée par RTE
    for day, price in spot_daily.items():
        set_history_value(history, day, "spot_eur_mwh", price, "RTE")

    # Mix : instantané temps réel, rangé à la date du run
    shares = (data.get("mix_france") or {}).get("shares")
    if shares:
        history_entry(history, today)["mix_shares"] = shares

    cutoff = (datetime.date.today() - datetime.timedelta(days=HISTORY_MAX_DAYS)).isoformat()
    history = sorted((h for h in history if h["date"] >= cutoff), key=lambda h: h["date"])

    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    return history


def compute_weekly_summary(history):
    cutoff = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    week = [h for h in history if h["date"] >= cutoff]

    summary = {
        "period_start": week[0]["date"] if week else None,
        "period_end": week[-1]["date"] if week else None,
        "brent": None,
        "spot_price": None,
        "mix": None,
    }

    brent_points = [h["brent_usd"] for h in week if h.get("brent_usd") is not None]
    if len(brent_points) >= 2:
        first, last = brent_points[0], brent_points[-1]
        change_pct = round((last - first) / first * 100, 1) if first else None
        summary["brent"] = {
            "start_usd": first,
            "end_usd": last,
            "change_pct": change_pct,
        }

    spot_points = [h["spot_eur_mwh"] for h in week if h.get("spot_eur_mwh") is not None]
    if spot_points:
        summary["spot_price"] = {
            "avg_eur_mwh": round(sum(spot_points) / len(spot_points), 2),
            "min_eur_mwh": round(min(spot_points), 2),
            "max_eur_mwh": round(max(spot_points), 2),
            "days_count": len(spot_points),
        }

    nuclear_vals, renewable_vals = [], []
    for h in week:
        shares = h.get("mix_shares") or {}
        if not shares:
            continue
        nuclear_vals.append(shares.get("nucleaire", 0))
        renewable_vals.append(
            shares.get("eolien", 0)
            + shares.get("solaire", 0)
            + shares.get("hydraulique", 0)
            + shares.get("bioenergies", 0)
        )
    if nuclear_vals:
        summary["mix"] = {
            "nuclear_avg_share": round(sum(nuclear_vals) / len(nuclear_vals), 1),
            "renewables_avg_share": round(sum(renewable_vals) / len(renewable_vals), 1),
            "days_count": len(nuclear_vals),
        }

    return summary


# Champ du prix dans market.json -> champ correspondant dans l'historique
CHANGE_FIELDS = {
    "spot_price_france": ("price_eur_mwh", "spot_eur_mwh"),
    "brent": ("price_usd", "brent_usd"),
    "henry_hub": ("price_usd_mmbtu", "henry_hub_usd_mmbtu"),
}


def add_changes(data, history):
    """Variation de chaque prix par rapport au cours précédent connu (flèche sur le site)."""
    for key, (field, hist_field) in CHANGE_FIELDS.items():
        entry = data.get(key)
        if not entry or entry.get(field) is None or not entry.get("date"):
            continue
        previous = [h for h in history if h.get(hist_field) is not None and h["date"] < entry["date"][:10]]
        if not previous or not previous[-1][hist_field]:
            continue
        prev = previous[-1]
        entry["prev_value"] = prev[hist_field]
        entry["prev_date"] = prev["date"]
        entry["change_pct"] = round((entry[field] - prev[hist_field]) / prev[hist_field] * 100, 1)


def main():
    existing = load_existing()

    spot = fetch_spot_price_france(existing)
    spot_daily = spot.pop("daily", {}) if spot else {}

    data = {
        "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "brent": label_quote(fetch_brent(existing)),
        "henry_hub": label_quote(fetch_henry_hub(existing)),
        "mix_france": fetch_mix_france(existing),
        "spot_price_france": spot,
        "chokepoints": fetch_chokepoint_traffic(existing),
    }
    update_brent_year()
    update_lng_exports()
    update_gas_world()
    update_gas_storage()

    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    history = load_history()
    history = append_to_history(history, data, spot_daily)

    add_changes(data, history)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    weekly = compute_weekly_summary(history)
    os.makedirs(os.path.dirname(WEEKLY_PATH), exist_ok=True)
    with open(WEEKLY_PATH, "w", encoding="utf-8") as f:
        json.dump(weekly, f, ensure_ascii=False, indent=2)

    print("Écrit dans", DATA_PATH)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print("Historique:", len(history), "jours —", HISTORY_PATH)
    print("Résumé hebdo:", WEEKLY_PATH)
    print(json.dumps(weekly, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
