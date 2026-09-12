"""
Récupère 3 données marché et les écrit dans _data/market.json :
- Brent (EIA, clé API gratuite requise -> secret EIA_API_KEY)
- Mix électrique France en temps réel (RTE eco2mix, API v2, aucune clé requise)
- Prix spot électricité France day-ahead (RTE Wholesale Market v3, OAuth2 -> secret RTE_BASE64_KEY)

Garde aussi un historique (_data/market_history.json, 60 derniers jours) et calcule
un résumé hebdomadaire (_data/weekly_summary.json) : variation Brent 7j, moyenne
prix spot 7j, part moyenne nucléaire/renouvelables 7j.

En cas d'échec sur une source, on garde l'ancienne valeur (le site ne casse jamais).
"""
import json
import os
import sys
import datetime

import requests

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "market.json")
HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "market_history.json")
WEEKLY_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "weekly_summary.json")
HISTORY_MAX_DAYS = 60

EIA_API_KEY = os.environ.get("EIA_API_KEY", "")
RTE_BASE64_KEY = os.environ.get("RTE_BASE64_KEY", "")  # Client ID + Secret déjà encodés en base64, fournis par RTE


def load_existing():
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def fetch_brent(existing):
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
        }
    except Exception as e:
        print(f"Erreur Brent: {e}")
        return existing.get("brent")


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
        # La structure exacte varie selon les versions de l'API ODRE :
        # parfois les champs sont à la racine, parfois sous "fields",
        # parfois sous "record" -> "fields". On gère les 3 cas.
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
    """OAuth2 client_credentials — RTE fournit directement la clé base64 (Client ID:Secret encodés)."""
    r = requests.post(
        "https://digital.iservices.rte-france.com/token/oauth/",
        headers={"Authorization": f"Basic {RTE_BASE64_KEY}"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def fetch_spot_price_france(existing):
    if not RTE_BASE64_KEY:
        print("RTE_BASE64_KEY manquant, on garde l'ancienne valeur spot.")
        return existing.get("spot_price_france")
    try:
        token = get_rte_token()
        now = datetime.datetime.utcnow()
        start = (now - datetime.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        end = now.strftime("%Y-%m-%dT%H:%M:%S+00:00")

        url = "https://digital.iservices.rte-france.com/open_api/wholesale_market/v3/france_power_exchanges"
        r = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params={"start_date": start, "end_date": end},
            timeout=20,
        )
        r.raise_for_status()
        payload = r.json()

        periods = payload.get("france_power_exchanges") or []
        if not periods:
            raise ValueError("aucune période retournée")

        last_period = periods[-1]
        values = last_period.get("values") or []

        if values:
            last_value = values[-1]
            price = (
                last_value.get("price")
                or last_value.get("value")
                or last_value.get("spot_price")
            )
            date_label = last_value.get("start_date") or last_period.get("start_date")
        else:
            price = last_period.get("base_load")
            date_label = last_period.get("start_date")

        if price is None:
            raise ValueError(f"champ prix introuvable dans la réponse: {last_period}")

        return {
            "price_eur_mwh": round(float(price), 2),
            "date": (date_label or now.strftime("%Y-%m-%d"))[:10],
        }
    except Exception as e:
        print(f"Erreur RTE spot: {e}")
        return existing.get("spot_price_france")


def load_history():
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def append_to_history(history, data):
    """Ajoute (ou met à jour) l'entrée du jour, garde HISTORY_MAX_DAYS jours max."""
    today = datetime.date.today().isoformat()

    snapshot = {
        "date": today,
        "brent_usd": (data.get("brent") or {}).get("price_usd"),
        "spot_eur_mwh": (data.get("spot_price_france") or {}).get("price_eur_mwh"),
        "mix_shares": (data.get("mix_france") or {}).get("shares"),
    }

    history = [h for h in history if h.get("date") != today]
    history.append(snapshot)
    history.sort(key=lambda h: h["date"])
    history = history[-HISTORY_MAX_DAYS:]

    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    return history


def compute_weekly_summary(history):
    """Calcule variation Brent 7j, moyenne prix spot 7j, part moyenne nucléaire/renouvelables 7j."""
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

    data = {
        "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "brent": fetch_brent(existing),
        "mix_france": fetch_mix_france(existing),
        "spot_price_france": fetch_spot_price_france(existing),
    }

    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    history = load_history()
    history = append_to_history(history, data)

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
