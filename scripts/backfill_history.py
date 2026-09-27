"""
Script à lancer ponctuellement (workflow_dispatch) pour reconstruire l'historique
(Brent, Henry Hub, Spot électricité France) sur les 60 derniers jours :
- Brent et Henry Hub : EIA (valeurs journalières officielles, quelques jours de retard)
- Spot France : Energy-Charts (Fraunhofer ISE, données SMARD, CC BY 4.0), moyenne
  journalière des prix day-ahead. L'API RTE ne renvoie que le jour en cours.

Les valeurs officielles écrasent celles déjà présentes : c'est ce qui corrige les
anciens jours où le cron rangeait un prix à la date du run au lieu de la date du prix.
Si une source ne répond pas, ses valeurs existantes ne sont pas touchées.
"""
import json
import os
import datetime
import requests

from fetch_market_data import EIA_API_KEY, PARIS, SOURCE_FIELDS, fetch_eia_series

HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "market_history.json")
HISTORY_MAX_DAYS = 60
SPOT_SOURCE = "Energy-Charts / SMARD"


def fetch_spot_history():
    """{date: moyenne des prix day-ahead du jour} pour la zone France, sur 60 jours."""
    today = datetime.datetime.now(PARIS).date()
    start = today - datetime.timedelta(days=HISTORY_MAX_DAYS)
    r = requests.get(
        "https://api.energy-charts.info/price",
        params={"bzn": "FR", "start": start.isoformat(), "end": today.isoformat()},
        timeout=60,
    )
    r.raise_for_status()
    payload = r.json()

    by_day = {}
    for ts, price in zip(payload.get("unix_seconds") or [], payload.get("price") or []):
        if price is None:
            continue
        day = datetime.datetime.fromtimestamp(ts, PARIS).date().isoformat()
        by_day.setdefault(day, []).append(float(price))

    if not by_day:
        return {}
    # On écarte les journées incomplètes (ex. le jour en cours si pas encore publié)
    full = max(len(p) for p in by_day.values())
    return {
        day: round(sum(p) / len(p), 2)
        for day, p in by_day.items()
        if len(p) >= 0.9 * full and day <= today.isoformat()
    }


def safe_fetch(label, fn, *args):
    print(f"Récupération {label}...")
    try:
        result = fn(*args)
    except Exception as e:
        print(f"  Erreur : {e}")
        return {}
    if result:
        print(f"  {len(result)} jours trouvés ({min(result)} -> {max(result)}).")
    else:
        print("  aucun jour trouvé.")
    return result


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
        if first <= d <= last or (d > last and not entry.get(source_key)):
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

    if EIA_API_KEY:
        brent = safe_fetch("Brent (EIA)", fetch_eia_series, "RBRTE", 90)
        henry = safe_fetch("Henry Hub (EIA)", fetch_eia_series, "RNGWHHD", 90)
    else:
        print("EIA_API_KEY manquant, Brent et Henry Hub non rattrapés.")
        brent = henry = {}
    spot = safe_fetch("spot électricité France (Energy-Charts)", fetch_spot_history)

    n_brent = apply_official(history, "brent_usd", brent, "EIA")
    n_henry = apply_official(history, "henry_hub_usd_mmbtu", henry, "EIA")
    n_spot = apply_official(history, "spot_eur_mwh", spot, SPOT_SOURCE)

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
