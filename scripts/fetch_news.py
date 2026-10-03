"""
Actualités et incidents maritimes, lancé toutes les 2 h par .github/workflows/update-news.yml.

- _data/news.json : derniers titres liés à l'énergie et aux détroits, repris des flux RSS
  publics de 5 médias (Al Jazeera, France 24, Le Monde, EIA, BBC) (titre, lien, média, date). Les flux RSS sont faits pour être repris ;
  on n'affiche que le titre et le lien vers l'article.
- _data/podcast.json : lien audio, durée et date de chaque épisode (flux RSS du podcast),
  pour le lecteur intégré au site.
- _data/incidents.json : incidents signalés au UKMTO (centre maritime de la Royal Navy),
  via le flux qui alimente la carte de www.ukmto.org. Contenu publié sous Open Government
  Licence v3.0 (www.ukmto.org/terms-and-conditions, points 20 et 22). On garde 12 mois.

En cas d'échec d'une source, on garde les données précédentes (le site ne casse jamais).
"""
import collections
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
HEADERS = {"User-Agent": "InsideEnergyMarkets/1.0 (+https://insideenergymarkets.com/)"}

# Sources : (adresse du flux, langue des titres, filtre). Les flux spécialisés dans l'énergie
# sont repris tels quels (filtre False) ; les flux généralistes passent par un filtre sur le titre.
# La version anglaise du site ne montre que les titres en anglais.
FEEDS = {
    # Spécialisés énergie (les rubriques énergie du Guardian mélangent d'autres sujets : filtrées)
    "Le Monde Énergies": ("https://www.lemonde.fr/energies/rss_full.xml", "fr", False),
    "Connaissance des Énergies": ("https://www.connaissancedesenergies.org/rss.xml", "fr", False),
    "EIA": ("https://www.eia.gov/rss/todayinenergy.xml", "en", False),
    "European Commission": ("https://energy.ec.europa.eu/node/2/rss_en", "en", False),
    "The Guardian": ("https://www.theguardian.com/environment/energy/rss", "en", True),
    "The Guardian Oil": ("https://www.theguardian.com/business/oil/rss", "en", True),
    # Généralistes : seulement les titres liés à l'énergie
    "BBC": ("https://feeds.bbci.co.uk/news/business/rss.xml", "en", True),
    "BBC Middle East": ("https://feeds.bbci.co.uk/news/world/middle_east/rss.xml", "en", True),
    "Al Jazeera": ("https://www.aljazeera.com/xml/rss/all.xml", "en", True),
    "France 24": ("https://www.france24.com/fr/moyen-orient/rss", "fr", True),
    "Le Monde": ("https://www.lemonde.fr/international/rss_full.xml", "fr", True),
    "Le Monde Économie": ("https://www.lemonde.fr/economie/rss_full.xml", "fr", True),
    "France 24 Éco": ("https://www.france24.com/fr/eco-tech/rss", "fr", True),
}
# Nom affiché quand une même rédaction a plusieurs flux
SOURCE_NAME = {"The Guardian Oil": "The Guardian", "BBC Middle East": "BBC", "Le Monde Énergies": "Le Monde",
               "Le Monde Économie": "Le Monde", "France 24 Éco": "France 24"}
NEWS_PER_LANG = 14
NEWS_PER_SOURCE = 3
NEWS_MAX_AGE_DAYS = 5

# Filtre des flux généralistes, sur le titre seul (la description fait remonter trop d'articles
# hors sujet). « Iran » seul est trop large : on l'exige avec un terme énergie ou maritime.
TOPIC = re.compile(r"hormuz|ormuz|red sea|mer rouge|bab.el.mandeb|tanker|pétrolier|brent|wti|lng|gnl"
                   r"|opec|opep|oil|crude|brut|pétrol|gas|gaz|electricit|électricit"
                   r"|power price|nuclear|nucléaire|energy|énergie|énergétique|carburant|diesel|gazole|fuel"
                   r"|renewable|renouvelable|wind farm|éolien|solar|solaire|refiner|raffin", re.I)
IRAN = re.compile(r"iran", re.I)
ENERGY = re.compile(r"oil|pétrol|tanker|ship|navire|strait|détroit|gas|gaz|export|sanction|crude|énergie|energy", re.I)

UKMTO_URL = "https://sccd.royalnavy.mod.uk/api/ukmto/all"
INCIDENTS_KEEP_DAYS = 365

# Flux RSS public du podcast (trouvé via l'API iTunes lookup, id 6807057201)
PODCAST_RSS = "https://anchor.fm/s/10edf0868/podcast/rss"
PODCAST_PATH = os.path.join(DATA_DIR, "podcast.json")
ITUNES = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}


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
    if IRAN.search(title) and not ENERGY.search(title):
        return False
    return bool(TOPIC.search(title))


def fetch_feed(source, url, lang, filtered):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    items = []
    for it in ET.fromstring(r.content).findall(".//item"):
        title = " ".join((it.findtext("title") or "").split())
        link = (it.findtext("link") or "").strip()
        if not title or not link.startswith("http") or (filtered and not is_relevant(title)):
            continue
        try:
            when = parsedate_to_datetime(it.findtext("pubDate")).astimezone(datetime.timezone.utc)
        except Exception:
            continue
        items.append({"title": title, "url": link, "source": SOURCE_NAME.get(source, source), "lang": lang,
                      "date": when.isoformat(timespec="seconds")})
    return items


def update_news():
    items, failures = [], []
    for source, (url, lang, filtered) in FEEDS.items():
        try:
            items.extend(fetch_feed(source, url, lang, filtered))
        except Exception as e:
            failures.append(source)
            print(f"Erreur flux {source}: {e}")
    if not items:
        print("Aucun titre récupéré, on garde les actualités précédentes.")
        return

    # Les plus récents d'abord, sans doublon, au plus NEWS_PER_SOURCE par média et
    # NEWS_PER_LANG par langue (pour que les versions française et anglaise soient fournies)
    cutoff = (now_utc() - datetime.timedelta(days=NEWS_MAX_AGE_DAYS)).isoformat()
    seen, per_source, per_lang, news = set(), {}, {}, []
    for item in sorted(items, key=lambda n: n["date"], reverse=True):
        key = re.sub(r"\W+", "", item["title"].lower())[:80]
        src, lang = item["source"], item["lang"]
        if key in seen or item["date"] < cutoff or per_source.get(src, 0) >= NEWS_PER_SOURCE                 or per_lang.get(lang, 0) >= NEWS_PER_LANG:
            continue
        seen.add(key)
        per_source[src] = per_source.get(src, 0) + 1
        per_lang[lang] = per_lang.get(lang, 0) + 1
        news.append(item)
    write_json(NEWS_PATH, {"updated_at": now_utc().isoformat(timespec="seconds"), "items": news})
    print(f"Actualités : {len(news)} titres {per_lang} ({len(FEEDS) - len(failures)}/{len(FEEDS)} flux OK)")


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


def place_en(value):
    """Nom anglais d'une zone, harmonisé comme la version française (UKMTO VRA = océan Indien)."""
    if not value:
        return value
    if value.lower() in ("ukmto vra", "indian ocean basin"):
        return "Indian Ocean"
    if value.lower() == "arabian gulf":
        return "Persian Gulf"
    return value.title().replace(" Of ", " of ").replace("Bab El Mandeb", "Bab el-Mandeb")


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
            "place_en": place_en(clean(x.get("place"))),
            "vessel_type": translate(clean(x.get("vesselType")), VESSELS_FR),
            "vessel_type_en": "" if clean(x.get("vesselType")).lower() == "other" else clean(x.get("vesselType")).title(),
            "vessel_name": clean(x.get("vesselName")),
            "summary": summarize(x.get("otherDetails")),
        }
        stored[entry["id"]] = entry

    cutoff = (now_utc() - datetime.timedelta(days=INCIDENTS_KEEP_DAYS)).isoformat()
    items = sorted((i for i in stored.values() if i["date"] >= cutoff), key=lambda i: i["date"], reverse=True)
    since = (now_utc() - datetime.timedelta(days=30)).isoformat()
    recent = [i for i in items if i["date"] >= since]
    places = collections.Counter(i["place"] for i in recent if i["place"])
    # Ancien stockage sans nom anglais : on le recalcule à partir du nom d'origine si besoin
    names_en = {i["place"]: i.get("place_en") or i["place"] for i in recent if i["place"]}
    stats = {
        "total_30d": len(recent),
        "attacks_30d": sum(1 for i in recent if i["type"] == "Attack"),
        "top_places": [{"place": p, "place_en": names_en[p], "n": n} for p, n in places.most_common(3)],
    }
    write_json(INCIDENTS_PATH, {"updated_at": now_utc().isoformat(timespec="seconds"), "stats": stats, "items": items})
    print(f"Incidents UKMTO : {len(raw)} dans le flux, {len(items)} conservés")


# ===== Podcast : fichiers audio pour le lecteur du site =====

def parse_duration(value):
    """« 00:03:27 », « 03:27 » ou « 207 » -> secondes."""
    seconds = 0
    for part in (value or "").strip().split(":"):
        if not part.strip().isdigit():
            return None
        seconds = seconds * 60 + int(part)
    return seconds or None


def update_podcast():
    """Lien audio, durée et date de chaque épisode, repris du flux RSS public du podcast
    (Spotify for Creators). Le lien passe par Spotify for Creators, donc les écoutes sur le
    site comptent dans ses statistiques. En cas d'échec, on garde le fichier précédent."""
    try:
        r = requests.get(PODCAST_RSS, headers=HEADERS, timeout=30)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"Erreur flux du podcast: {e}")
        return
    episodes = {}
    for it in root.iter("item"):
        number = (it.findtext("itunes:episode", namespaces=ITUNES) or "").strip()
        enclosure = it.find("enclosure")
        if not number.isdigit() or enclosure is None or not enclosure.get("url"):
            continue
        try:
            date = parsedate_to_datetime(it.findtext("pubDate")).date().isoformat()
        except Exception:
            date = None
        episodes[str(int(number))] = {
            "audio": enclosure.get("url"),
            "duration": parse_duration(it.findtext("itunes:duration", namespaces=ITUNES)),
            "date": date,
        }
    if not episodes:
        print("Flux du podcast vide, on garde le fichier précédent.")
        return
    write_json(PODCAST_PATH, {"updated_at": now_utc().isoformat(timespec="seconds"), "episodes": episodes})
    print(f"Podcast : {len(episodes)} épisodes dans le flux")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    update_news()
    update_incidents()
    update_podcast()
    return 0


if __name__ == "__main__":
    sys.exit(main())
