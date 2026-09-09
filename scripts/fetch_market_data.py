"""
Récupère 3 données marché et les écrit dans _data/market.json :
- Brent (EIA, clé API gratuite requise -> secret EIA_API_KEY)
- Mix électrique France en temps réel (RTE eco2mix, aucune clé requise)
- Prix spot électricité France day-ahead (RTE Wholesale Market, OAuth2 -> secrets RTE_CLIENT_ID / RTE_CLIENT_SECRET)

En cas d'échec sur une source, on garde l'ancienne valeur (le site ne casse jamais).
"""
import json
import os
import sys
import datetime

import requests

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "market.json")

EIA_API_KEY = os.environ.get("EIA_API_KEY", "")
RTE_CLIENT_ID = os.environ.get("RTE_CLIENT_ID", "")
RTE_CLIENT_SECRET = os.environ.get("RTE_CLIENT_SECRET", "")


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


def get_rte_token():
    """OAuth2 client_credentials — standard RTE, valable ~2h."""
    import base64

    creds = f"{RTE_CLIENT_ID}:{RTE_CLIENT_SECRET}".encode("utf-8")
    b64_creds = base64.b64encode(creds).decode("utf-8")
    r = requests.post(
        "https://digital.iservices.rte-france.com/token/oauth/",
        headers={"Authorization": f"Basic {b64_creds}"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def fetch_spot_price_france(existing):
    if not RTE_CLIENT_ID or not RTE_CLIENT_SECRET:
        print("RTE_CLIENT_ID/RTE_CLIENT_SECRET manquants, on garde l'ancienne valeur spot.")
        return existing.get("spot_price_france")
    try:
        token = get_rte_token()
        now = datetime.datetime.utcnow()
        start = (now - datetime.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        end = now.strftime("%Y-%m-%dT%H:%M:%S+00:00")

        url = "https://digital.iservices.rte-france.com/open_api/wholesale_market/v2/france_power_exchanges"
        r = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params={"start_date": start, "end_date": end},  # requests encode proprement le "+" de l'heure UTC
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
            # pas de détail fin dispo, on retombe sur le prix moyen (base_load) de la période
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
