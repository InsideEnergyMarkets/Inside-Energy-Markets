"""
Script à lancer UNE SEULE FOIS pour remplir rétroactivement l'historique
(Brent, Henry Hub, Spot électricité France) sur les 60 derniers jours,
à partir des vraies données historiques de l'EIA et de RTE.
"""
import json
import os
import datetime
import requests

EIA_API_KEY = os.environ.get("EIA_API_KEY", "")
RTE_BASE64_KEY = os.environ.get("RTE_BASE64_KEY", "")
HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "market_history.json")
HISTORY_MAX_DAYS = 60


def fetch_eia_history(series_code):
    """Retourne un dict {date: valeur} pour une série EIA donnée, sur ~90 jours."""
    url = (
        "https://api.eia.gov/v2/petroleum/pri/spt/data/"
        if series_code == "RBRTE"
        else "https://api.eia.gov/v2/natural-gas/pri/fut/data/"
    )
    url += (
        f"?api_key={EIA_API_KEY}&frequency=daily&data[0]=value"
        f"&facets[series][]={series_code}&sort[0][column]=period&sort[0][direction]=desc&length=90"
    )
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    rows = r.json()["response"]["data"]
    return {row["period"]: round(float(row["value"]), 2) for row in rows}


def get_rte_token():
    r = requests.post(
        "https://digital.iservices.rte-france.com/token/oauth/",
        headers={"Authorization": f"Basic {RTE_BASE64_KEY}"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def fetch_rte_spot_history():
    """Retourne un dict {date: prix} pour le spot électricité France, sur 60 jours."""
    if not RTE_BASE64_KEY:
        print("RTE_BASE64_KEY manquant, spot électricité non rattrapé.")
        return {}
    token = get_rte_token()
    now = datetime.datetime.utcnow()
    start = (now - datetime.timedelta(days=HISTORY_MAX_DAYS)).strftime("%Y-%m-%dT00:00:00+00:00")
    end = now.strftime("%Y-%m-%dT00:00:00+00:00")

    url = "https://digital.iservices.rte-france.com/open_api/wholesale_market/v3/france_power_exchanges"
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        params={"start_date": start, "end_date": end},
        timeout=30,
    )
    r.raise_for_status()
    periods = r.json().get("france_power_exchanges") or []

    result = {}
    for period in periods:
        values = period.get("values") or []
        for v in values:
            date_label = (v.get("start_date") or "")[:10]
            price = v.get("price") or v.get("value") or v.get("spot_price")
            if date_label and price is not None:
                result[date_label] = round(float(price), 2)  # garde la dernière valeur du jour
        if not values:
            date_label = (period.get("start_date") or "")[:10]
            price = period.get("base_load")
            if date_label and price is not None:
                result[date_label] = round(float(price), 2)
    return result


def main():
    with open(HISTORY_PATH, "r", encoding="utf-8") as f:
        history = json.load(f)

    existing_dates = {h["date"]: h for h in history}

    print("Récupération historique Brent (EIA)...")
    brent_hist = fetch_eia_history("RBRTE") if EIA_API_KEY else {}
    print(f"  {len(brent_hist)} jours trouvés.")

    print("Récupération historique Henry Hub (EIA)...")
    henry_hist = fetch_eia_history("RNGWHHD") if EIA_API_KEY else {}
    print(f"  {len(henry_hist)} jours trouvés.")

    print("Récupération historique spot électricité France (RTE)...")
    try:
        spot_hist = fetch_rte_spot_history()
    except Exception as e:
        print(f"Erreur spot RTE: {e}")
        spot_hist = {}
    print(f"  {len(spot_hist)} jours trouvés.")

    all_dates = set(brent_hist) | set(henry_hist) | set(spot_hist) | set(existing_dates)
    cutoff = (datetime.date.today() - datetime.timedelta(days=HISTORY_MAX_DAYS)).isoformat()
    all_dates = {d for d in all_dates if d >= cutoff}

    filled_brent = filled_henry = filled_spot = 0

    for date in all_dates:
        entry = existing_dates.get(date, {"date": date})

        if not entry.get("brent_usd") and date in brent_hist:
            entry["brent_usd"] = brent_hist[date]
            filled_brent += 1

        if not entry.get("henry_hub_usd_mmbtu") and date in henry_hist:
            entry["henry_hub_usd_mmbtu"] = henry_hist[date]
            filled_henry += 1

        if not entry.get("spot_eur_mwh") and date in spot_hist:
            entry["spot_eur_mwh"] = spot_hist[date]
            filled_spot += 1

        existing_dates[date] = entry

    new_history = sorted(existing_dates.values(), key=lambda h: h["date"])
    new_history = new_history[-HISTORY_MAX_DAYS:]

    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(new_history, f, ensure_ascii=False, indent=2)

    print(f"\nRempli : {filled_brent} jours Brent, {filled_henry} jours Henry Hub, {filled_spot} jours Spot FR.")
    print(f"Historique total : {len(new_history)} jours.")


if __name__ == "__main__":
    main()
