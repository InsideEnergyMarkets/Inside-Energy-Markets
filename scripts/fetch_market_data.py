"""
Récupère les données marché et les écrit dans _data/market.json :
- Brent : contrat à terme ICE du premier mois (OilPriceAPI -> secret OILPRICEAPI_KEY)
- Henry Hub : contrat à terme NYMEX du premier mois (OilPriceAPI)
  (en cas d'échec on garde la dernière valeur : on ne mélange jamais contrat à terme et spot EIA)
- Gaz France (PEG, zone TRF) : prix moyen journalier publié par NaTran (ex-GRTgaz) sur sa plateforme
  de transparence Smart (export CSV, sans clé)
- Mix électrique France en temps réel (RTE eco2mix API v2, aucune clé requise)
- Prix spot électricité France day-ahead, moyenne journalière des prix horaires
  (RTE Wholesale Market v3, OAuth2 -> secret RTE_BASE64_KEY)
- Trafic maritime par détroit stratégique (IMF PortWatch, AIS, aucune clé requise),
  avec historique 90 jours dans _data/chokepoints_history.json
- Brent sur 12 mois (EIA) pour le graphique Ormuz / Brent : _data/brent_year.json
- Exportations mensuelles de GNL des États-Unis (EIA) : _data/lng_exports.json
- Prix mondiaux du gaz par mois (FMI via la FRED) : Europe, Asie, États-Unis : _data/gas_world.json
- Stocks de gaz en Europe et en France (GIE AGSI+ -> secret GIE_API_KEY) : _data/gas_storage.json
- Prix day-ahead de l'électricité, France et pays voisins, aujourd'hui et demain
- WTI (OilPriceAPI, repli EIA) et Brent / WTI sur 12 mois (EIA) : _data/oil_year.json
- Prix des carburants à la pompe en France, moyenne nationale (flux officiel DGCCRF,
  data.economie.gouv.fr, Licence Ouverte, sans clé) : _data/fuel.json
- Stocks commerciaux de brut aux États-Unis, hebdomadaires (EIA) : _data/us_crude_stocks.json
- Offre et demande mondiales de pétrole, historique et prévisions (EIA, Short-Term Energy
  Outlook) : _data/oil_balance.json
  (ENTSO-E Transparency Platform -> secret ENTSOE_API_KEY) : _data/day_ahead.json

Garde aussi un historique (_data/market_history.json, 60 derniers jours) et calcule
un résumé hebdomadaire (_data/weekly_summary.json). Chaque prix de l'historique est
rangé à la date du prix lui-même (pas à la date du run) et porte sa source.

En cas d'échec sur une source, on garde l'ancienne valeur (le site ne casse jamais).
"""
import csv
import datetime
import io
import json
import os
import sys
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
ENTSOE_API_KEY = os.environ.get("ENTSOE_API_KEY", "")


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
        if series_code in ("RBRTE", "RWTC")
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


def fetch_brent_oilpriceapi(code="BRENT_CRUDE_USD"):
    """Brent (ou WTI avec code="WTI_USD") via OilPriceAPI, mis à jour toutes les 5 minutes (plan gratuit)."""
    if not OILPRICEAPI_KEY:
        return None
    url = f"https://api.oilpriceapi.com/v1/prices/latest?by_code={code}"
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
    """Brent ICE premier mois. En cas d'échec, dernière valeur connue (jamais le spot EIA : autre produit)."""
    try:
        result = fetch_brent_oilpriceapi()
        if result:
            return result
    except Exception as e:
        print(f"Erreur Brent (OilPriceAPI), on garde l'ancienne valeur: {e}")
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
    """Henry Hub NYMEX premier mois. En cas d'échec, dernière valeur connue (jamais le spot EIA)."""
    try:
        result = fetch_henry_hub_oilpriceapi()
        if result:
            return result
    except Exception as e:
        print(f"Erreur Henry Hub (OilPriceAPI), on garde l'ancienne valeur: {e}")
    return existing.get("henry_hub")


PEG_URL = "https://smart.natrangroupe.com/api/v1/fr/prix_bourse/export/ZONE.csv"


def fetch_peg(existing, days=70):
    """Gaz France (PEG, zone TRF) : prix moyen journalier publié par NaTran (moyenne pondérée de tous
    les produits échangés sur EEX pour la journée gazière). Renvoie (entrée market.json, {date: prix})."""
    today = datetime.datetime.now(PARIS).date()
    start = today - datetime.timedelta(days=days)
    try:
        r = requests.get(PEG_URL, params={"startDate": start.isoformat(), "endDate": today.isoformat()},
                         headers={"User-Agent": "InsideEnergyMarkets/1.0 (+https://insideenergymarkets.com)"}, timeout=30)
        r.raise_for_status()
        daily = {}
        for row in csv.reader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"):
            if len(row) < 3 or not row[0][:2].isdigit():
                continue
            try:
                day = datetime.datetime.strptime(row[0].strip(), "%d/%m/%Y").date()
                daily[day.isoformat()] = round(float(row[2].strip().replace(",", ".")), 2)
            except ValueError:
                continue
        if not daily:
            raise ValueError("aucune ligne de prix dans l'export")
        last = max(daily)
        d = datetime.date.fromisoformat(last)
        entry = {
            "price_eur_mwh": daily[last], "date": last, "unit": "EUR/MWh", "source": "NaTran",
            "date_label": f"Moyenne du {JOURS[d.weekday()]} {d:%d/%m}",
            "date_label_en": f"Average on {DAYS_EN[d.weekday()]} {d:%d/%m}",
        }
        return entry, daily
    except Exception as e:
        print(f"Erreur PEG (NaTran), on garde l'ancienne valeur: {e}")
        return existing.get("peg"), {}


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
    """Retourne 'fluide' (>= 80 %), 'partiel' (40-79 %), 'ferme' (15-39 %) ou 'arret' (< 15 %)
    selon le ratio trafic actuel / moyenne normale."""
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
    elif ratio >= 0.15:
        return "ferme"
    else:
        return "arret"


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


# ===== Prix day-ahead de l'électricité (ENTSO-E Transparency Platform) =====
# Résultat de l'enchère journalière européenne (publiée vers 13 h pour le lendemain), au pas
# de 15 minutes. France : moyenne de la journée, pointe (8 h-20 h, jours ouvrés), prix heure
# par heure, heures les moins et les plus chères. Pays voisins : moyenne de la journée.
# On garde les 7 derniers jours ; en cas d'erreur, le fichier existant reste en place.
DAY_AHEAD_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "day_ahead.json")
ENTSOE_URL = "https://web-api.tp.entsoe.eu/api"
ENTSOE_ZONES = {
    "FR": "10YFR-RTE------C",
    "DE": "10Y1001A1001A82H",   # Allemagne-Luxembourg
    "BE": "10YBE----------2",
    "NL": "10YNL----------L",
    "ES": "10YES-REE------0",
    "IT": "10Y1001A1001A73I",   # Italie Nord
    "CH": "10YCH-SWISSGRIDZ",
}
DAY_AHEAD_KEEP_DAYS = 7


def fetch_entsoe_day_ahead(eic, start_utc, end_utc):
    """Prix day-ahead d'une zone : {datetime UTC du quart d'heure: prix en €/MWh}.
    Les séries horaires sont ramenées au quart d'heure ; les points absents (compression
    de courbe A03) reprennent le prix du point précédent."""
    import xml.etree.ElementTree as ET
    r = requests.get(ENTSOE_URL, params={
        "securityToken": ENTSOE_API_KEY, "documentType": "A44",
        "in_Domain": eic, "out_Domain": eic, "contract_MarketAgreement.type": "A01",
        "periodStart": start_utc.strftime("%Y%m%d%H%M"), "periodEnd": end_utc.strftime("%Y%m%d%H%M"),
    }, timeout=60)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    for el in root.iter():
        el.tag = el.tag.split("}", 1)[-1]
    quarters = {}
    for period in root.iter("Period"):
        start = datetime.datetime.strptime(period.find("timeInterval/start").text, "%Y-%m-%dT%H:%MZ")
        end = datetime.datetime.strptime(period.find("timeInterval/end").text, "%Y-%m-%dT%H:%MZ")
        step = {"PT15M": 15, "PT30M": 30, "PT60M": 60}.get(period.find("resolution").text)
        if not step:
            continue
        points = {int(pt.find("position").text): float(pt.find("price.amount").text) for pt in period.iter("Point")}
        n = int((end - start).total_seconds() // 60 // step)
        price = None
        for pos in range(1, n + 1):
            price = points.get(pos, price)
            if price is None:
                continue
            t0 = start + datetime.timedelta(minutes=(pos - 1) * step)
            for k in range(step // 15):
                quarters[t0 + datetime.timedelta(minutes=15 * k)] = price
    return quarters


def day_ahead_by_paris_day(quarters):
    """Regroupe les quarts d'heure par jour de Paris : {date: [(heure locale, prix), ...]}."""
    days = {}
    for t, price in sorted(quarters.items()):
        local = t.replace(tzinfo=datetime.timezone.utc).astimezone(PARIS)
        days.setdefault(local.date().isoformat(), []).append((local, price))
    return days


def summarize_day_ahead(rows):
    """Statistiques d'une journée (liste de (heure locale, prix) au quart d'heure)."""
    hours = {}
    for local, price in rows:
        hours.setdefault(local.strftime("%H"), []).append(price)
    hourly = [[h, round(sum(v) / len(v), 2)] for h, v in sorted(hours.items())]
    values = [p for _, p in rows]
    peak = [p for local, p in rows if 8 <= local.hour < 20] if rows[0][0].weekday() < 5 else []
    low = min(hourly, key=lambda x: x[1])
    high = max(hourly, key=lambda x: x[1])
    return {
        "avg": round(sum(values) / len(values), 2),
        "peak": round(sum(peak) / len(peak), 2) if peak else None,
        "min": {"hour": low[0], "value": low[1]},
        "max": {"hour": high[0], "value": high[1]},
        "negative_hours": sum(1 for _, v in hourly if v < 0),
        "hourly": hourly,
    }


def update_day_ahead():
    if not ENTSOE_API_KEY:
        print("ENTSOE_API_KEY manquant, prix day-ahead non mis à jour.")
        return
    existing = load_json(DAY_AHEAD_PATH, {})
    today = datetime.datetime.now(PARIS).date()
    start = datetime.datetime.combine(today - datetime.timedelta(days=1), datetime.time(), PARIS)
    end = datetime.datetime.combine(today + datetime.timedelta(days=2), datetime.time(), PARIS)
    start_utc = start.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    end_utc = end.astimezone(datetime.timezone.utc).replace(tzinfo=None)

    fr = dict(existing.get("fr", {}))
    neighbors = {k: dict(v) for k, v in existing.get("neighbors", {}).items()}
    for code, eic in ENTSOE_ZONES.items():
        try:
            days = day_ahead_by_paris_day(fetch_entsoe_day_ahead(eic, start_utc, end_utc))
        except Exception as e:
            print(f"Erreur day-ahead ENTSO-E ({code}): {e}")
            continue
        for date, rows in days.items():
            if len(rows) < 92:   # journée incomplète (bord de la fenêtre demandée)
                continue
            if code == "FR":
                fr[date] = summarize_day_ahead(rows)
            else:
                neighbors.setdefault(code, {})[date] = round(sum(p for _, p in rows) / len(rows), 2)

    if not fr:
        print("Day-ahead : aucune donnée France, on garde le fichier existant.")
        return
    keep = sorted(fr)[-DAY_AHEAD_KEEP_DAYS:]
    fr = {d: fr[d] for d in keep}
    for i, d in enumerate(keep[1:], start=1):
        prev = fr[keep[i - 1]]["avg"]
        fr[d]["change_pct"] = round((fr[d]["avg"] - prev) / abs(prev) * 100, 1) if prev else None
        fr[d]["prev_value"] = prev
        fr[d]["prev_date"] = keep[i - 1]
    neighbors = {k: {d: v[d] for d in sorted(v) if d in fr} for k, v in neighbors.items()}
    out = {
        "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "source": "ENTSO-E",
        "latest": keep[-1],
        "fr": fr,
        "neighbors": neighbors,
    }
    with open(DAY_AHEAD_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("Day-ahead :", ", ".join(f"{d} {fr[d]['avg']} €/MWh" for d in keep[-2:]))


# ===== Pétrole : WTI, Brent / WTI sur 12 mois, stocks américains, prix à la pompe =====
OIL_YEAR_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "oil_year.json")
US_STOCKS_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "us_crude_stocks.json")
FUEL_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "fuel.json")
FUEL_URL = ("https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/"
            "prix-des-carburants-en-france-flux-instantane-v2/records")
FUEL_KEEP_DAYS = 120
OIL_BALANCE_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "oil_balance.json")


def update_oil_balance():
    """Production (PAPR_WORLD) et consommation (PATC_WORLD) mondiales de pétrole et autres liquides,
    en millions de barils par jour, 24 mois d'historique et les prévisions de l'EIA (Short-Term
    Energy Outlook, publié chaque mois). À partir du mois en cours, les valeurs sont des prévisions."""
    if not EIA_API_KEY:
        return
    today = datetime.datetime.now(PARIS).date()
    start = f"{today.year - 2}-{today.month:02d}"
    url = ("https://api.eia.gov/v2/steo/data/"
           f"?api_key={EIA_API_KEY}&frequency=monthly&data[0]=value"
           "&facets[seriesId][]=PAPR_WORLD&facets[seriesId][]=PATC_WORLD"
           f"&start={start}&sort[0][column]=period&sort[0][direction]=asc&length=200")
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()["response"]["data"]
    except Exception as e:
        print(f"Erreur offre et demande mondiales (EIA STEO): {e}")
        return
    months = {}
    for row in data:
        key = "prod" if row["seriesId"] == "PAPR_WORLD" else "cons"
        months.setdefault(row["period"], {})[key] = round(float(row["value"]), 2)
    rows = [{"m": m, "prod": v["prod"], "cons": v["cons"]} for m, v in sorted(months.items()) if "prod" in v and "cons" in v]
    if not rows:
        print("Offre et demande mondiales : réponse vide, on garde le fichier existant.")
        return
    this_month = f"{today.year}-{today.month:02d}"
    current = next((r for r in rows if r["m"] == this_month), rows[-1])
    out = {"forecast_from": this_month, "current": current, "rows": rows}
    with open(OIL_BALANCE_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Offre et demande mondiales : {len(rows)} mois, {current['m']} production {current['prod']} / consommation {current['cons']}")


def fetch_wti(existing):
    """WTI : OilPriceAPI (même source que le Brent, pour un écart cohérent), repli sur l'EIA."""
    try:
        wti = fetch_brent_oilpriceapi("WTI_USD")
        if wti:
            return label_quote(wti)
    except Exception as e:
        print(f"Erreur WTI (OilPriceAPI): {e}")
    if EIA_API_KEY:
        try:
            series = fetch_eia_series("RWTC", 5)
            d = max(series)
            return label_quote({"price_usd": series[d], "date": d, "unit": "USD/baril", "source": "EIA"})
        except Exception as e:
            print(f"Erreur WTI (EIA): {e}")
    return existing.get("wti")


def update_oil_year():
    """Brent et WTI sur 12 mois (EIA, prix spot quotidiens) pour la fenêtre Brent / WTI."""
    if not EIA_API_KEY:
        return
    try:
        brent = fetch_eia_series("RBRTE", 400)
        wti = fetch_eia_series("RWTC", 400)
    except Exception as e:
        print(f"Erreur Brent / WTI 12 mois (EIA): {e}")
        return
    since = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()
    rows = [{"date": d, "brent": brent[d], "wti": wti[d]} for d in sorted(brent) if d in wti and d >= since]
    if rows:
        with open(OIL_YEAR_PATH, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))


def update_us_crude_stocks():
    """Stocks commerciaux de brut aux États-Unis, hors réserve stratégique (EIA, série WCESTUS1,
    publiée le mercredi), en millions de barils, sur 60 semaines."""
    if not EIA_API_KEY:
        return
    url = ("https://api.eia.gov/v2/petroleum/stoc/wstk/data/"
           f"?api_key={EIA_API_KEY}&frequency=weekly&data[0]=value&facets[series][]=WCESTUS1"
           "&sort[0][column]=period&sort[0][direction]=desc&length=60")
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        rows = r.json()["response"]["data"]
    except Exception as e:
        print(f"Erreur stocks de brut US (EIA): {e}")
        return
    out = [{"date": row["period"], "mb": round(float(row["value"]) / 1000, 1)} for row in sorted(rows, key=lambda x: x["period"])]
    if out:
        with open(US_STOCKS_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, separators=(",", ":"))


def fetch_fuel_average(field, since):
    """Prix moyen d'un carburant en France (€/L) sur les stations qui l'ont mis à jour depuis `since`."""
    r = requests.get(FUEL_URL, params={
        "select": f"avg({field}_prix) as prix, count({field}_prix) as n",
        "where": f"{field}_maj >= date'{since}' and {field}_prix > 0",
    }, timeout=60)
    r.raise_for_status()
    row = r.json()["results"][0]
    return (round(float(row["prix"]), 3) if row.get("prix") else None), row.get("n") or 0


def update_fuel_prices():
    """Moyenne nationale du gazole et du SP95-E10 (flux instantané officiel de la DGCCRF).
    On ne garde que les prix mis à jour dans les 7 derniers jours, et un historique quotidien
    de 120 jours. En cas d'erreur, le fichier existant reste en place."""
    existing = load_json(FUEL_PATH, {})
    today = datetime.datetime.now(PARIS).date()
    since = (today - datetime.timedelta(days=7)).isoformat()
    try:
        gazole, n_gazole = fetch_fuel_average("gazole", since)
        e10, n_e10 = fetch_fuel_average("e10", since)
    except Exception as e:
        print(f"Erreur prix des carburants (DGCCRF): {e}")
        return
    if not gazole or not e10:
        print("Prix des carburants : réponse vide, on garde le fichier existant.")
        return
    history = existing.get("history", {})
    history[today.isoformat()] = {"gazole": gazole, "e10": e10}
    keep = sorted(history)[-FUEL_KEEP_DAYS:]
    history = {d: history[d] for d in keep}
    ref_day = (today - datetime.timedelta(days=7)).isoformat()
    older = [d for d in keep if d <= ref_day]
    change = {}
    if older:
        ref = history[older[-1]]
        change = {"since": older[-1],
                  "gazole_cts": round((gazole - ref["gazole"]) * 100, 1),
                  "e10_cts": round((e10 - ref["e10"]) * 100, 1)}
    out = {"date": today.isoformat(), "gazole": gazole, "e10": e10,
           "stations": max(n_gazole, n_e10), "change_7d": change, "history": history}
    with open(FUEL_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Carburants : gazole {gazole} €/L, SP95-E10 {e10} €/L ({out['stations']} stations)")


# ===== Conversion des prix du gaz en €/MWh (unité européenne) =====
# Les sources américaines (OilPriceAPI, EIA, FMI) donnent des $/MMBtu. On garde ces valeurs
# et on ajoute l'équivalent en €/MWh, avec le taux de référence de la BCE du jour
# (ou du mois pour les moyennes mensuelles). 1 MMBtu = 0,29307107 MWh.
FX_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "fx.json")
MWH_PER_MMBTU = 0.29307107
FX = {"daily": {}, "monthly": {}}


def fetch_ecb_usd(freq, start):
    """Taux de référence BCE : dollars pour 1 euro, {période: taux}. freq 'D' (jour) ou 'M' (mois)."""
    r = requests.get(f"https://data-api.ecb.europa.eu/service/data/EXR/{freq}.USD.EUR.SP00.A",
                     params={"startPeriod": start, "format": "csvdata"}, timeout=30)
    r.raise_for_status()
    rows = csv.DictReader(io.StringIO(r.text))
    return {row["TIME_PERIOD"]: round(float(row["OBS_VALUE"]), 4) for row in rows if row.get("OBS_VALUE")}


def update_fx():
    """Met à jour _data/fx.json (400 jours de taux quotidiens, taux mensuels depuis 11 ans).
    En cas d'échec, on garde les taux déjà connus."""
    global FX
    FX = load_json(FX_PATH, {"daily": {}, "monthly": {}})
    today = datetime.date.today()
    try:
        daily = fetch_ecb_usd("D", (today - datetime.timedelta(days=400)).isoformat())
        monthly = fetch_ecb_usd("M", f"{today.year - 11}-01")
    except Exception as e:
        print(f"Erreur taux de change BCE: {e} (on garde les taux connus)")
        return
    if daily and monthly:
        last = max(daily)
        FX = {"latest": {"date": last, "usd_per_eur": daily[last]}, "daily": daily, "monthly": monthly}
        with open(FX_PATH, "w", encoding="utf-8") as f:
            json.dump(FX, f, ensure_ascii=False, separators=(",", ":"))


def usd_per_eur_on(date):
    """Taux BCE du jour, ou du dernier jour ouvré précédent (la BCE ne publie pas le week-end)."""
    daily = FX.get("daily") or {}
    known = [d for d in daily if d <= date[:10]]
    if known:
        return daily[max(known)]
    return daily[min(daily)] if daily else None


def mmbtu_usd_to_mwh_eur(value, usd_per_eur):
    if value is None or not usd_per_eur:
        return None
    return round(value / usd_per_eur / MWH_PER_MMBTU, 2)


def add_henry_hub_eur(entry):
    """Ajoute price_eur_mwh (et le taux utilisé) à l'entrée Henry Hub de market.json."""
    if not entry or entry.get("price_usd_mmbtu") is None or not entry.get("date"):
        return entry
    rate = usd_per_eur_on(entry["date"])
    eur = mmbtu_usd_to_mwh_eur(entry["price_usd_mmbtu"], rate)
    if eur is not None:
        entry["price_eur_mwh"] = eur
        entry["usd_per_eur"] = rate
    return entry


def enrich_gas_world():
    """Ajoute à chaque moyenne mensuelle de _data/gas_world.json sa valeur en €/MWh (champ e),
    avec le taux moyen du mois de la BCE."""
    data = load_json(GAS_WORLD_PATH, None)
    monthly = FX.get("monthly") or {}
    if not data or not monthly:
        return
    for points in data.values():
        for p in points:
            rate = monthly.get(p["month"]) or monthly.get(max((m for m in monthly if m <= p["month"]), default=""))
            e = mmbtu_usd_to_mwh_eur(p.get("v"), rate)
            if e is not None:
                p["e"] = e
    with open(GAS_WORLD_PATH, "w", encoding="utf-8") as f:
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
    "peg_eur_mwh": "peg_source",
}
BACKFILL_STATE = os.path.join(os.path.dirname(__file__), "..", "_data", "oilprice_backfill.json")


def backfill_futures(history):
    """Jours de cotation manquants des 30 derniers jours (Brent, Henry Hub) : moyennes journalières
    OilPriceAPI (une seule requête pour les deux séries), au plus une fois par jour. Même produit que le
    cours du jour (contrats à terme du premier mois) ; ne remplace jamais une valeur."""
    if not OILPRICEAPI_KEY:
        return
    today = datetime.date.today()
    state = load_json(BACKFILL_STATE, {})
    if state.get("last") == today.isoformat():
        return
    since = (today - datetime.timedelta(days=30)).isoformat()
    have = {h["date"] for h in history if h.get("brent_usd") is not None and h["date"] >= since}
    weekdays = [(today - datetime.timedelta(days=k)).isoformat() for k in range(1, 31)
                if (today - datetime.timedelta(days=k)).weekday() < 5]
    if sum(1 for d in weekdays if d not in have) <= 2:  # jours fériés de bourse : pas de requête
        return
    codes = {"BRENT_CRUDE_USD": "brent_usd", "NATURAL_GAS_USD": "henry_hub_usd_mmbtu"}
    try:
        r = requests.get("https://api.oilpriceapi.com/v1/prices/past_month",
                         params={"by_code": ",".join(codes), "interval": "daily", "per_page": 500},
                         headers={"Authorization": f"Token {OILPRICEAPI_KEY}"}, timeout=30)
        r.raise_for_status()
        rows = (r.json().get("data") or {}).get("prices", [])
        added = 0
        for row in rows:
            field, day = codes.get(row.get("code")), (oilpriceapi_date(row) or "")[:10]
            if not field or not day or is_weekend(day) or row.get("price") is None:
                continue
            entry = next((h for h in history if h.get("date") == day), {})
            if entry.get(field) is None:
                set_history_value(history, day, field, round(float(row["price"]), 2), "OilPriceAPI")
                added += 1
        print(f"Rattrapage OilPriceAPI : {added} valeurs ajoutées")
    except Exception as e:
        print(f"Erreur rattrapage OilPriceAPI: {e}")
    with open(BACKFILL_STATE, "w", encoding="utf-8") as fh:
        json.dump({"last": today.isoformat()}, fh)


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


def append_to_history(history, data, spot_daily, peg_daily=None):
    today = datetime.date.today().isoformat()

    # Brent et Henry Hub : uniquement les contrats à terme (OilPriceAPI). Les anciennes valeurs spot
    # de l'EIA sont retirées de ces séries (autre produit : le mélange faussait courbes et variations).
    for h in history:
        for field, src, extra in (("brent_usd", "brent_source", None),
                                  ("henry_hub_usd_mmbtu", "henry_hub_source", "henry_hub_eur_mwh")):
            if h.get(src) == "EIA":
                h.pop(field, None); h.pop(src, None)
                if extra:
                    h.pop(extra, None)

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

    backfill_futures(history)

    # Gaz France (PEG) : chaque journée gazière publiée par NaTran (valeurs définitives, on les réécrit)
    for day, price in (peg_daily or {}).items():
        set_history_value(history, day, "peg_eur_mwh", price, "NaTran")

    # Spot : moyenne journalière de chaque journée complète renvoyée par RTE
    for day, price in spot_daily.items():
        set_history_value(history, day, "spot_eur_mwh", price, "RTE")

    # Mix : instantané temps réel, rangé à la date du run
    shares = (data.get("mix_france") or {}).get("shares")
    if shares:
        history_entry(history, today)["mix_shares"] = shares

    cutoff = (datetime.date.today() - datetime.timedelta(days=HISTORY_MAX_DAYS)).isoformat()
    history = sorted((h for h in history if h["date"] >= cutoff), key=lambda h: h["date"])

    # Henry Hub en €/MWh pour chaque jour, au taux BCE de ce jour-là
    for h in history:
        eur = mmbtu_usd_to_mwh_eur(h.get("henry_hub_usd_mmbtu"), usd_per_eur_on(h["date"]))
        if eur is not None:
            h["henry_hub_eur_mwh"] = eur
        # Un jour sans aucune valeur (ex. ancien spot EIA retiré) ne sert plus à rien
    history = [h for h in history if len(h) > 1]

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
    "henry_hub": ("price_eur_mwh", "henry_hub_eur_mwh"),
    "peg": ("price_eur_mwh", "peg_eur_mwh"),
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

    update_fx()
    spot = fetch_spot_price_france(existing)
    spot_daily = spot.pop("daily", {}) if spot else {}
    peg, peg_daily = fetch_peg(existing)

    data = {
        "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "brent": label_quote(fetch_brent(existing)),
        "wti": fetch_wti(existing),
        "henry_hub": add_henry_hub_eur(label_quote(fetch_henry_hub(existing))),
        "peg": peg,
        "mix_france": fetch_mix_france(existing),
        "spot_price_france": spot,
        "chokepoints": fetch_chokepoint_traffic(existing),
    }
    update_brent_year()
    update_lng_exports()
    update_gas_world()
    enrich_gas_world()
    update_gas_storage()
    update_day_ahead()
    update_oil_year()
    update_us_crude_stocks()
    update_fuel_prices()
    update_oil_balance()

    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    history = load_history()
    history = append_to_history(history, data, spot_daily, peg_daily)

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
