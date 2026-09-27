"""
Script à lancer ponctuellement (workflow_dispatch) pour reconstruire l'historique
(Brent, Henry Hub, Spot électricité France) sur les 60 derniers jours, à partir
des vraies données journalières de l'EIA et de RTE.

Les valeurs officielles écrasent celles déjà présentes : c'est ce qui corrige les
anciens jours où le cron rangeait un prix à la date du run au lieu de la date du prix.
Si une source ne répond pas, ses valeurs existantes ne sont pas touchées.
"""
import json
import os
import datetime
import requests

from fetch_market_data import (
    PARIS,
    SOURCE_FIELDS,
    daily_spot_averages,
    fetch_power_exchanges,
    get_rte_token,
)

EIA_API_KEY = os.environ.get("EIA_API_KEY", "")
RTE_BASE64_KEY = os.environ.get("RTE_BASE64_KEY", "")
HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "market_history.json")
HISTORY_MAX_DAYS = 60
RTE_CHUNK_DAYS = 7


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


def fetch_rte_spot_history():
    """Retourne un dict {date: moyenne journalière} pour le spot France, sur 60 jours."""
    if not RTE_BASE64_KEY:
        print("RTE_BASE64_KEY manquant, spot électricité non rattrapé.")
        return {}
    token = get_rte_token()
    now = datetime.datetime.now(PARIS).replace(microsecond=0)
    midnight = now.replace(hour=0, minute=0, second=0)
    start = midnight - datetime.timedelta(days=HISTORY_MAX_DAYS)

    # Requêtes par tranches de 7 jours alignées sur minuit, pour ne pas dépasser
    # la plage maximale acceptée par l'API et ne pas couper de journée
    result = {}
    while start < now:
        end = min(start + datetime.timedelta(days=RTE_CHUNK_DAYS), now)
        result.update(daily_spot_averages(fetch_power_exchanges(token, start, end)))
        start = end
    today = midnight.date().isoformat()
    return {d: p for d, p in result.items() if d <= today}


def apply_official(history, field, official, source):
    """Écrase `field` avec les valeurs officielles sur la plage qu'elles couvrent.

    Sur cette plage, un jour absent de la source (week-end, jour férié) est vidé :
    l'ancienne valeur y était une valeur répétée. Après la plage (retard de
    publication de l'EIA), on ne garde que les valeurs déjà marquées d'une source.
    """
    if not official:
        return 0
    first, last = min(official), max(official)
    source_key = SOURCE_FIELDS[field]
    for entry in history.values():
        d = entry["date"]
        if first <= d <= last or not entry.get(source_key):
            entry.pop(field, None)
            entry.pop(source_key, None)
    for d, value in official.items():
        entry = history.setdefault(d, {"date": d})
        entry[field] = value
        entry[source_key] = source
    return len(official)


def main():
    with open(HISTORY_PATH, "r", encoding="utf-8") as f:
        history = {h["date"]: h for h in json.load(f)}

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

    n_brent = apply_official(history, "brent_usd", brent_hist, "EIA")
    n_henry = apply_official(history, "henry_hub_usd_mmbtu", henry_hist, "EIA")
    n_spot = apply_official(history, "spot_eur_mwh", spot_hist, "RTE")

    cutoff = (datetime.date.today() - datetime.timedelta(days=HISTORY_MAX_DAYS)).isoformat()
    new_history = sorted(
        (h for h in history.values() if h["date"] >= cutoff and len(h) > 1),
        key=lambda h: h["date"],
    )

    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(new_history, f, ensure_ascii=False, indent=2)

    print(f"\nÉcrit : {n_brent} jours Brent, {n_henry} jours Henry Hub, {n_spot} jours Spot FR.")
    print(f"Historique total : {len(new_history)} jours.")


if __name__ == "__main__":
    main()
