"""
Récupère les données marché et les écrit dans _data/market.json :
- Brent (OilPriceAPI -> secret OILPRICEAPI_KEY, repli sur EIA -> secret EIA_API_KEY)
- Henry Hub, gaz naturel US (OilPriceAPI, repli sur EIA)
- Mix électrique France en temps réel (RTE eco2mix API v2, aucune clé requise)
- Prix spot électricité France day-ahead, moyenne journalière des prix horaires
  (RTE Wholesale Market v3, OAuth2 -> secret RTE_BASE64_KEY)
- Trafic maritime par détroit stratégique (IMF PortWatch, AIS, aucune clé requise)

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
OILPRICEAPI_KEY = os.environ.get("OILPRICEAPI_KEY", "")


def load_existing():
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]


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
    collected = datetime.date.fromisoformat(entry["date"][:10])
    trading = last_trading_day(entry["date"])
    entry["date"] = trading.isoformat()
    day = f"{JOURS[trading.weekday()]} {trading:%d/%m}"
    entry["date_label"] = (
        f"Clôture du {day} (bourse fermée le week-end)" if trading != collected
        else f"Cours du {day}"
    )
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

        shares = {k: round(v / total * 100, 1) for k, v in sources.items()}
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


def fetch_chokepoint_baseline(name_fragment):
    """Référence annuelle de trafic pour un détroit (IMF PortWatch) — convertie en moyenne journalière."""
    url = (
        "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
        "PortWatch_chokepoints_database/FeatureServer/0/query"
        f"?where=UPPER(portname)%20LIKE%20UPPER('%25{name_fragment}%25')"
        "&outFields=portname,vessel_count_tanker,vessel_count_total"
        "&resultRecordCount=1&f=json"
    )
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    payload = r.json()
    features = payload.get("features") or []
    if not features:
        raise ValueError(f"aucune référence pour {name_fragment}")
    attrs = features[0]["attributes"]

    tanker_annual = attrs.get("vessel_count_tanker")
    total_annual = attrs.get("vessel_count_total")

    return {
        "tanker_avg": round(float(tanker_annual) / 365, 1) if tanker_annual else None,
        "total_avg": round(float(total_annual) / 365, 1) if total_annual else None,
    }


def classify_traffic_status(current, baseline):
    """Retourne 'fluide', 'partiel' ou 'ferme' selon le ratio trafic actuel / moyenne normale."""
    try:
        current = float(current)
        baseline = float(baseline)
    except (TypeError, ValueError):
        return None
    if not current or not baseline or baseline <= 0:
        return None
    ratio = current / baseline
    if ratio >= 0.8:
        return "fluide"
    elif ratio >= 0.4:
        return "partiel"
    else:
        return "ferme"


def fetch_chokepoint_traffic(existing):
    """Trafic maritime (nb de tankers/jour) par détroit, via IMF PortWatch (AIS, gratuit, sans clé).
    On moyenne les 5 derniers jours disponibles pour lisser les anomalies ponctuelles
    (couverture satellite incomplète un jour donné, mise à jour par lots, etc.)."""
    existing_traffic = existing.get("chokepoints", {}) or {}
    result = {}

    for key, name_fragment in CHOKEPOINTS.items():
        try:
            url = (
                "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
                "Daily_Chokepoints_Data/FeatureServer/0/query"
                f"?where=UPPER(portname)%20LIKE%20UPPER('%25{name_fragment}%25')"
                "&outFields=date,portname,n_tanker,n_total"
                "&orderByFields=date%20DESC"
                "&resultRecordCount=5&f=json"
            )
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            payload = r.json()
            features = payload.get("features") or []
            if not features:
                raise ValueError(f"aucun enregistrement pour {name_fragment} (clés reçues: {list(payload.keys())})")

            rows = []
            for feat in features:
                a = feat["attributes"]
                date_ms = a.get("date")
                date_str = None
                if date_ms:
                    try:
                        date_str = datetime.datetime.utcfromtimestamp(float(date_ms) / 1000).strftime("%Y-%m-%d")
                    except (TypeError, ValueError):
                        date_str = str(date_ms)
                rows.append({
                    "date": date_str,
                    "n_tanker": a.get("n_tanker"),
                    "n_total": a.get("n_total"),
                })

            tanker_vals = [r["n_tanker"] for r in rows if r["n_tanker"] is not None]
            total_vals = [r["n_total"] for r in rows if r["n_total"] is not None]

            n_tanker_avg = round(sum(tanker_vals) / len(tanker_vals), 1) if tanker_vals else None
            n_total_avg = round(sum(total_vals) / len(total_vals), 1) if total_vals else None
            latest_date = rows[0]["date"] if rows else None
            oldest_date = rows[-1]["date"] if rows else None

            # PortWatch publie une fois par semaine avec ~1 semaine de retard :
            # on garde l'âge de la donnée pour l'afficher (sinon on croit à une panne)
            age_days = None
            if latest_date:
                try:
                    age_days = (datetime.date.today() - datetime.date.fromisoformat(latest_date[:10])).days
                except ValueError:
                    pass

            entry = {
                "portname": features[0]["attributes"].get("portname"),
                "date": latest_date,
                "age_days": age_days,
                "period_start": oldest_date,
                "n_tanker": n_tanker_avg,
                "n_total": n_total_avg,
                "days_averaged": len(rows),
            }

            try:
                baseline = fetch_chokepoint_baseline(name_fragment)
                entry["tanker_avg"] = baseline.get("tanker_avg")
                entry["total_avg"] = baseline.get("total_avg")
                entry["status"] = classify_traffic_status(n_total_avg, baseline.get("total_avg"))
            except Exception as e2:
                print(f"Erreur référence {key}: {e2}")
                prev = existing_traffic.get(key) or {}
                entry["tanker_avg"] = prev.get("tanker_avg")
                entry["total_avg"] = prev.get("total_avg")
                entry["status"] = prev.get("status")

            result[key] = entry
        except Exception as e:
            print(f"Erreur trafic {key}: {e}")
            result[key] = existing_traffic.get(key)

    return result


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

    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    history = load_history()
    history = append_to_history(history, data, spot_daily)

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
