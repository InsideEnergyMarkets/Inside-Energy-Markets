"""
Test de couverture AISStream.io (AIS temps réel, gratuit) sur les trois détroits.

Écoute le flux pendant AIS_DURATION secondes (600 par défaut) et compte, par zone,
les navires distincts (MMSI) et les tankers (types AIS 80 à 89). Sert à décider si
la couverture est suffisante avant d'intégrer un indicateur « en direct » au site.
Rien n'est écrit dans le repo : le résultat est affiché dans le journal du workflow.

Clé : secret GitHub AISSTREAM_API_KEY (jamais affichée).
"""
import asyncio
import json
import os
import sys
import time

import websockets

API_KEY = os.environ.get("AISSTREAM_API_KEY", "")
DURATION = int(os.environ.get("AIS_DURATION", "600"))

# Zones [[lat_min, lon_min], [lat_max, lon_max]] autour de chaque détroit
ZONES = {
    "Ormuz": [[25.5, 55.5], [27.2, 57.5]],
    "Bab-el-Mandeb": [[12.2, 42.8], [13.3, 43.8]],
    "Malacca": [[1.0, 100.5], [3.5, 104.2]],
}


def zone_of(lat, lon):
    for name, ((lat1, lon1), (lat2, lon2)) in ZONES.items():
        if lat1 <= lat <= lat2 and lon1 <= lon <= lon2:
            return name
    return None


async def listen():
    stats = {name: {"messages": 0, "mmsi": set(), "first": None, "last": None} for name in ZONES}
    ship_type = {}
    subscription = {
        "APIKey": API_KEY,
        "BoundingBoxes": list(ZONES.values()),
        "FilterMessageTypes": ["PositionReport", "StandardClassBPositionReport", "ShipStaticData"],
    }
    deadline = time.monotonic() + DURATION
    async with websockets.connect("wss://stream.aisstream.io/v0/stream", max_size=2**22) as ws:
        await ws.send(json.dumps(subscription))
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(1, deadline - time.monotonic()))
            except asyncio.TimeoutError:
                break
            msg = json.loads(raw)
            if "error" in msg:
                raise RuntimeError(f"AISStream a refusé l'abonnement : {msg['error']}")
            meta = msg.get("MetaData") or {}
            mmsi = meta.get("MMSI")
            if msg.get("MessageType") == "ShipStaticData":
                t = (msg.get("Message") or {}).get("ShipStaticData", {}).get("Type")
                if mmsi and t is not None:
                    ship_type[mmsi] = t
            lat, lon = meta.get("latitude"), meta.get("longitude")
            if mmsi is None or lat is None or lon is None:
                continue
            name = zone_of(lat, lon)
            if not name:
                continue
            s = stats[name]
            s["messages"] += 1
            s["mmsi"].add(mmsi)
            ts = meta.get("time_utc")
            s["first"] = s["first"] or ts
            s["last"] = ts
    return stats, ship_type


def main():
    if not API_KEY:
        print("AISSTREAM_API_KEY manquant : ajoute le secret GitHub avant de lancer le test.")
        return 1
    print(f"Écoute AISStream pendant {DURATION} s sur : {', '.join(ZONES)}")
    stats, ship_type = asyncio.run(listen())
    print()
    for name, s in stats.items():
        ships = s["mmsi"]
        typed = [m for m in ships if m in ship_type]
        tankers = [m for m in typed if 80 <= ship_type[m] <= 89]
        print(f"{name:14} {len(ships):4} navires distincts, {s['messages']:5} positions, "
              f"type connu pour {len(typed)}, dont {len(tankers)} tankers")
        if s["first"]:
            print(f"{'':14} premier message {s['first']}, dernier {s['last']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
