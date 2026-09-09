"""
Récupère 3 données marché et les écrit dans _data/market.json :
- Brent (EIA, clé API gratuite requise -> secret EIA_API_KEY)
- Mix électrique France en temps réel (RTE eco2mix, aucune clé requise)
- Prix spot électricité France day-ahead (ENTSO-E, clé API gratuite requise -> secret ENTSOE_API_KEY)

En cas d'échec sur une source, on garde l'ancienne valeur (le site ne casse jamais).
"""
import json
import os
import sys
import datetime
import xml.etree.ElementTree as ET

import requests

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "market.json")

EIA_API_KEY = os.environ.get("EIA_API_KEY", "")
ENTSOE_API_KEY = os.environ.get("ENTSOE_API_KEY", "")


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
            "https://odre.opendatasoft.com/api/records/1.0/search/"
            "?dataset=eco2mix-national-tr&rows=1&sort=-date_heure"
        )
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        rec = r.json()["records"][0]["fields"]

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
            raise ValueError("total de production nul")

        shares = {k: round(v / total * 100, 1) for k, v in sources.items()}
        top = sorted(shares.items(), key=lambda kv: kv[1], reverse=True)

        return {
            "date_heure": rec.get("date_heure"),
            "shares": shares,
            "top_source": top[0][0],
            "top_share": top[0][1],
        }
    except Exception as e:
        print(f"Erreur mix RTE: {e}")
        return existing.get("mix_france")


def fetch_spot_price_france(existing):
    if not ENTSOE_API_KEY:
        print("ENTSOE_API_KEY manquant, on garde l'ancienne valeur spot.")
        return existing.get("spot_price_france")
    try:
        now = datetime.datetime.utcnow()
        start = (now - datetime.timedelta(days=1)).strftime("%Y%m%d0000")
        end = now.strftime("%Y%m%d0000")
        url = (
            "https://web-api.tp.entsoe.eu/api"
            f"?securityToken={ENTSOE_API_KEY}&documentType=A44"
            "&in_Domain=10YFR-RTE------C&out_Domain=10YFR-RTE------C"
            f"&periodStart={start}&periodEnd={end}"
        )
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        ns = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"}
        root = ET.fromstring(r.content)
        points = root.findall(".//ns:Point", ns)
        if not points:
            raise ValueError("aucun point de prix retourné")
        last_point = points[-1]
        price = last_point.find("ns:price.amount", ns).text
        return {
            "price_eur_mwh": round(float(price), 2),
            "date": now.strftime("%Y-%m-%d"),
        }
    except Exception as e:
        print(f"Erreur ENTSO-E spot: {e}")
        return existing.get("spot_price_france")


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

    print("Écrit dans", DATA_PATH)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
