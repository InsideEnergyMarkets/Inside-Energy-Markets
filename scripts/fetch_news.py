"""
Actualités et incidents maritimes, lancé toutes les 2 h par .github/workflows/update-news.yml.

- _data/news.json : derniers titres liés à l'énergie et aux détroits, repris des flux RSS
  publics de 5 médias (Al Jazeera, France 24, Le Monde, EIA, BBC) (titre, lien, média, date). Les flux RSS sont faits pour être repris ;
  on n'affiche que le titre et le lien vers l'article.
- _data/incidents.json : incidents signalés au UKMTO (centre maritime de la Royal Navy),
  via le flux qui alimente la carte de www.ukmto.org. Contenu publié sous Open Government
  Licence v3.0 (www.ukmto.org/terms-and-conditions, points 20 et 22). On garde 12 mois.

En cas d'échec d'une source, on garde les données précédentes (le site ne casse jamais).
"""
import datetime
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "_data")
NEWS_PATH = os.path.join(DATA_DIR, "news.json")
INCIDENTS_PATH = os.path.join(DATA_DIR, "incidents.json")
HEADERS = {"User-Agent": "InsideEnergyMarkets/1.0 (+https://insideenergymarkets.github.io/Inside-Energy-Markets/)"}

FEEDS = {
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "France 24": "https://www.france24.com/fr/moyen-orient/rss",
    "Le Monde": "https://www.lemonde.fr/international/rss_full.xml",
    "EIA": "https://www.eia.gov/rss/todayinenergy.xml",
    "BBC": "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
}
NEWS_MAX = 20
NEWS_MAX_AGE_DAYS = 3

# Filtre sur le titre seul (la description fait remonter trop d'articles hors sujet).
# « Iran » seul est trop large : on l'exige avec un terme énergie ou maritime.
TOPIC = re.compile(r"hormuz|ormuz|red sea|mer rouge|houthi|bab.el.mandeb|tanker|pétrolier|\bbrent\b|\blng\b|\bgnl\b"
                   r"|\bopec\b|\bopep\b|oil price|prix du pétrole|\bcrude\b|\bbrut\b", re.I)
IRAN = re.compile(r"\biran", re.I)
ENERGY = re.compile(r"\boil\b|pétrol|tanker|\bship|navire|strait|détroit|\bgas\b|\bgaz\b|export|sanction|crude|énergie|energy", re.I)

UKMTO_URL = "https://sccd.royalnavy.mod.uk/api/ukmto/all"
INCIDENTS_KEEP_DAYS = 365


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


# ===== Actualités =====

def is_relevant(title):
    return bool(TOPIC.search(title) or (IRAN.search(title) and ENERGY.search(title)))


def fetch_feed(source, url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    items = []
    for it in ET.fromstring(r.content).findall(".//item"):
        title = " ".join((it.findtext("title") or "").split())
        link = (it.findtext("link") or "").strip()
        if not title or not link.startswith("http") or not is_relevant(title):
            continue
        try:
            when = parsedate_to_datetime(it.findtext("pubDate")).astimezone(datetime.timezone.utc)
        except Exception:
            continue
        items.append({"title": title, "url": link, "source": source, "date": when.isoformat(timespec="seconds")})
    return items


def update_news():
    items, failures = [], []
    for source, url in FEEDS.items():
        try:
            items.extend(fetch_feed(source, url))
        except Exception as e:
            failures.append(source)
            print(f"Erreur flux {source}: {e}")
    if not items:
        print("Aucun titre récupéré, on garde les actualités précédentes.")
        return

    cutoff = (now_utc() - datetime.timedelta(days=NEWS_MAX_AGE_DAYS)).isoformat()
    seen, news = set(), []
    for item in sorted(items, key=lambda n: n["date"], reverse=True):
        key = re.sub(r"\W+", "", item["title"].lower())[:80]
        if key in seen or item["date"] < cutoff:
            continue
        seen.add(key)
        news.append(item)
    write_json(NEWS_PATH, {"updated_at": now_utc().isoformat(timespec="seconds"), "items": news[:NEWS_MAX]})
    print(f"Actualités : {len(news[:NEWS_MAX])} titres ({len(FEEDS) - len(failures)}/{len(FEEDS)} flux OK)")


# ===== Incidents UKMTO =====

def summarize(details):
    """Phrase d'ouverture de l'alerte UKMTO (lieu, fait), sans l'en-tête technique."""
    text = " ".join((details or "").split())
    m = re.search(r"(UKMTO has received[^.]*\.(?:[^.]*\.)?)", text)
    summary = m.group(1) if m else text
    return summary if len(summary) <= 300 else summary[:300].rsplit(" ", 1)[0] + "…"


PLACES_FR = {
    "strait of hormuz": "Détroit d'Ormuz", "gulf of oman": "Golfe d'Oman", "persian gulf": "Golfe Persique",
    "arabian gulf": "Golfe Persique", "gulf of aden": "Golfe d'Aden", "southern red sea": "Sud de la mer Rouge",
    "northern red sea": "Nord de la mer Rouge", "red sea": "Mer Rouge", "bab el mandeb": "Bab-el-Mandeb",
    "arabian sea": "Mer d'Arabie", "indian ocean basin": "Océan Indien", "ukmto vra": "Océan Indien",
    "somali basin": "Bassin somalien", "southern arabian gulf": "Sud du golfe Persique",
    "northern arabian gulf": "Nord du golfe Persique",
}
VESSELS_FR = {
    "tanker": "Tanker", "cargo": "Cargo", "bulk carrier": "Vraquier", "container": "Porte-conteneurs",
    "container ship": "Porte-conteneurs", "general cargo": "Cargo", "fishing": "Pêche", "dhow": "Boutre",
    "other": "", "merchant": "Navire marchand", "lpg tanker": "Méthanier GPL", "lng tanker": "Méthanier",
}


def translate(value, table):
    return table.get(value.lower(), value) if value else value


def clean(value):
    value = (value or "").strip()
    # Valeurs utilisées par l'UKMTO quand l'information n'est pas connue
    return "" if value.upper() in ("..", ".", "-", "NO", "N/A", "NA", "UNKNOWN", "TBC") else value


def update_incidents():
    try:
        r = requests.get(UKMTO_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        raw = r.json()
    except Exception as e:
        print(f"Erreur UKMTO: {e} (on garde les incidents précédents)")
        return

    stored = {i["id"]: i for i in load_json(INCIDENTS_PATH, {}).get("items", [])}
    for x in raw:
        if x.get("locationLatitude") is None or x.get("locationLongitude") is None:
            continue
        date = x.get("utcDateOfIncident") or x.get("utcDateCreated")
        entry = {
            "id": f"{x.get('incidentIssuer', 'UKMTO')}-{date[:4]}-{x.get('incidentNumber')}",
            "number": x.get("incidentNumber"),
            "date": date,
            "type": x.get("incidentTypeName"),
            "lat": round(float(x["locationLatitude"]), 4),
            "lon": round(float(x["locationLongitude"]), 4),
            "place": translate(clean(x.get("place")), PLACES_FR),
            "vessel_type": translate(clean(x.get("vesselType")), VESSELS_FR),
            "vessel_name": clean(x.get("vesselName")),
            "summary": summarize(x.get("otherDetails")),
        }
        stored[entry["id"]] = entry

    cutoff = (now_utc() - datetime.timedelta(days=INCIDENTS_KEEP_DAYS)).isoformat()
    items = sorted((i for i in stored.values() if i["date"] >= cutoff), key=lambda i: i["date"], reverse=True)
    since = (now_utc() - datetime.timedelta(days=30)).isoformat()
    recent = [i for i in items if i["date"] >= since]
    stats = {"total_30d": len(recent), "attacks_30d": sum(1 for i in recent if i["type"] == "Attack")}
    write_json(INCIDENTS_PATH, {"updated_at": now_utc().isoformat(timespec="seconds"), "stats": stats, "items": items})
    print(f"Incidents UKMTO : {len(raw)} dans le flux, {len(items)} conservés")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    update_news()
    update_incidents()
    return 0


if __name__ == "__main__":
    sys.exit(main())
