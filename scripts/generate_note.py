"""
Note de marché hebdomadaire, générée chaque lundi par .github/workflows/weekly-note.yml.

Calcule les chiffres de la semaine écoulée (lundi au dimanche) à partir des données du site
(_data/*.json) et écrit deux fichiers dans la collection _notes (français et anglais), plus un
texte prêt à coller pour LinkedIn dans _linkedin/ (hors site). Les phrases sont construites à
partir des chiffres (pas d'IA) : chaque valeur vient d'une source citée sur la page.

Format inspiré des notes de marché du secteur : titre qui résume la semaine, contexte, rubriques
à puces avec les fourchettes de la semaine, un graphique par rubrique et une lecture clé.

Usage : python scripts/generate_note.py [--week 2026-W40] [--force]
Par défaut, la dernière semaine complète. --force réécrit une note existante (sinon on la garde,
pour ne pas écraser un « mot de Tom » ajouté à la main).
"""
import argparse
import datetime
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(ROOT, "_data")
NOTES_DIR = os.path.join(ROOT, "_notes")
LINKEDIN_DIR = os.path.join(ROOT, "_linkedin")

DAYS = {"fr": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
        "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]}
MONTHS = {"fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
                 "octobre", "novembre", "décembre"],
          "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September",
                 "October", "November", "December"]}
RENEWABLES = ("eolien", "solaire", "hydraulique", "bioenergies")


def load(name, default=None):
    try:
        with open(os.path.join(DATA, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def num(value, lang, digits=2):
    s = f"{value:,.{digits}f}"
    return s.replace(",", " ").replace(".", ",") if lang == "fr" else s


def pct(value, lang, digits=1):
    sign = "+" if value > 0 else ("−" if value < 0 else "")
    return f"{sign}{num(abs(value), lang, digits)}" + (" %" if lang == "fr" else "%")


def day_label(date, lang):
    d = datetime.date.fromisoformat(date)
    if lang == "fr":
        return f"{DAYS['fr'][d.weekday()]} {d.day}" + ("er" if d.day == 1 else "")
    return f"{DAYS['en'][d.weekday()]} {d.day}"


def date_long(d, lang):
    if lang == "fr":
        return f"{d.day}{'er' if d.day == 1 else ''} {MONTHS['fr'][d.month - 1]} {d.year}"
    return f"{d.day} {MONTHS['en'][d.month - 1]} {d.year}"


def signed(value, lang, digits=1):
    """Nombre signé avec un vrai signe moins (comme pct, sans le %)."""
    return ("+" if value > 0 else ("−" if value < 0 else "")) + num(abs(value), lang, digits)


def where_fr(place):
    """« dans le détroit d'Ormuz », « dans le golfe d'Aden », « en mer Rouge », « dans l'océan Indien »."""
    low = place[0].lower() + place[1:]
    if place.startswith("Mer"):
        return "en " + low
    if place.startswith("Océan"):
        return "dans l'" + low
    if place.startswith(("Détroit", "Golfe", "Bassin", "Nord", "Sud")):
        return "dans le " + low
    return "dans la zone " + place


def direction(change):
    return "up" if change > 0 else ("down" if change < 0 else "flat")


def series(history, field):
    return [(h["date"], h[field]) for h in history if h.get(field) is not None]


def weekly_move(points, start, end):
    """Variation sur la semaine : dernier cours de la semaine face au dernier cours avant le lundi."""
    before = [v for d, v in points if d < start]
    inside = [(d, v) for d, v in points if start <= d <= end]
    if not inside:
        return None
    ref = before[-1] if before else inside[0][1]
    last_d, last = inside[-1]
    hi = max(inside, key=lambda p: p[1])
    lo = min(inside, key=lambda p: p[1])
    return {"last": last, "last_date": last_d, "ref": ref, "change": (last - ref) / ref * 100 if ref else 0,
            "high": hi, "low": lo}


def compute(week_start):
    start, end = week_start.isoformat(), (week_start + datetime.timedelta(days=6)).isoformat()
    prev_start = (week_start - datetime.timedelta(days=7)).isoformat()
    hist = load("market_history.json", [])
    market = load("market.json", {})
    s = {"start": start, "end": end}

    spot = [(d, v) for d, v in series(hist, "spot_eur_mwh") if start <= d <= end]
    spot_prev = [v for d, v in series(hist, "spot_eur_mwh") if prev_start <= d < start]
    if spot:
        avg = sum(v for _, v in spot) / len(spot)
        s["spot"] = {"avg": avg, "high": max(spot, key=lambda p: p[1]), "low": min(spot, key=lambda p: p[1]),
                     "prev_avg": sum(spot_prev) / len(spot_prev) if spot_prev else None,
                     "negative_days": sum(1 for _, v in spot if v < 0)}

    mixes = [h["mix_shares"] for h in hist if h.get("mix_shares") and start <= h["date"] <= end]
    if mixes:
        s["mix"] = {"nuclear": sum(m.get("nucleaire", 0) for m in mixes) / len(mixes),
                    "renewables": sum(sum(m.get(k, 0) for k in RENEWABLES) for m in mixes) / len(mixes),
                    "gas": sum(m.get("gaz", 0) for m in mixes) / len(mixes)}

    s["brent"] = weekly_move(series(hist, "brent_usd"), start, end)
    s["hh"] = weekly_move(series(hist, "henry_hub_eur_mwh"), start, end)

    brent, wti = market.get("brent") or {}, market.get("wti") or {}
    if brent.get("price_usd") and wti.get("price_usd") and start <= (wti.get("date") or "") <= end:
        s["spread"] = brent["price_usd"] - wti["price_usd"]

    storage = load("gas_storage.json", {})
    for zone in ("eu", "fr"):
        pts = [p for p in storage.get(zone, []) if p["date"] <= end]
        if pts:
            last = pts[-1]
            d = datetime.date.fromisoformat(last["date"])
            week_ago = next((p for p in reversed(pts) if p["date"] <= (d - datetime.timedelta(days=7)).isoformat()), None)
            ly_date = d.replace(year=d.year - 1).isoformat()
            last_year = next((p for p in storage.get(zone, []) if p["date"] == ly_date), None)
            s["storage_" + zone] = {"full": last["full"], "date": last["date"],
                                    "week": last["full"] - week_ago["full"] if week_ago else None,
                                    "ly": last["full"] - last_year["full"] if last_year else None}

    fuel = (load("fuel.json", {}) or {}).get("history", {})
    days = sorted(d for d in fuel if d <= end)
    in_week = [d for d in days if d >= start]
    if in_week:
        first = [d for d in days if d < start]
        ref = first[-1] if first else in_week[0]
        s["fuel"] = {k: {"last": fuel[in_week[-1]][k], "change": fuel[in_week[-1]][k] - fuel[ref][k]}
                     for k in ("gazole", "e10") if fuel[in_week[-1]].get(k) and fuel[ref].get(k)}

    stocks = [p for p in (load("us_crude_stocks.json", []) or []) if p["date"] <= end]
    if len(stocks) >= 2 and stocks[-1]["date"] >= prev_start:
        s["us_stocks"] = {"mb": stocks[-1]["mb"], "change": stocks[-1]["mb"] - stocks[-2]["mb"], "date": stocks[-1]["date"]}

    cps = market.get("chokepoints") or {}
    s["straits"] = {k: {"pct": (cps.get(k) or {}).get("pct_total"), "status": (cps.get(k) or {}).get("status"),
                        "date": (cps.get(k) or {}).get("date")} for k in ("hormuz", "bab_el_mandeb", "malacca")}

    inc = [i for i in (load("incidents.json", {}) or {}).get("items", []) if start <= i["date"][:10] <= end]
    places = {}
    for i in inc:
        places[i.get("place")] = places.get(i.get("place"), 0) + 1
    top = max(places.items(), key=lambda kv: kv[1]) if places else None
    top_en = next((i.get("place_en") for i in inc if top and i.get("place") == top[0]), None)
    s["incidents"] = {"total": len(inc), "attacks": sum(1 for i in inc if i.get("type") == "Attack"),
                      "top": top, "top_en": top_en}

    news = (load("news.json", {}) or {}).get("items", [])
    s["news"] = [n for n in news if start <= n["date"][:10] <= end]
    return s


STATUS = {"fr": {"fluide": "fluide", "partiel": "partiellement perturbé", "ferme": "fortement perturbé",
                 "arret": "quasi à l'arrêt"},
          "en": {"fluide": "flowing normally", "partiel": "partly disrupted", "ferme": "heavily disrupted",
                 "arret": "almost at a standstill"}}
SOAR_FR = "s'envole"
COLORS = {"power": "#00817d", "gas": "#e8b33a", "oil": "#e8703a", "sea": "#2f6f8f", "ref": "#94a3b8"}


def short_day(date, lang):
    d = datetime.date.fromisoformat(date)
    return (DAYS[lang][d.weekday()][:3] + (". " if lang == "fr" else " ") + str(d.day)).capitalize()


def ddmm(date):
    d = datetime.date.fromisoformat(date[:10])
    return f"{d.day:02d}/{d.month:02d}"


def chart_series(week_start):
    """Données des petits graphiques de la note (une série par rubrique)."""
    start, end = week_start.isoformat(), (week_start + datetime.timedelta(days=6)).isoformat()
    hist = load("market_history.json", [])
    c = {}
    c["power"] = [(d, v) for d, v in series(hist, "spot_eur_mwh") if start <= d <= end]
    since30 = (week_start - datetime.timedelta(days=23)).isoformat()
    c["oil"] = [(d, v) for d, v in series(hist, "brent_usd") if since30 <= d <= end]
    storage = load("gas_storage.json", {}) or {}
    eu = [p for p in storage.get("eu", []) if p["date"] <= end]
    by_date = {p["date"]: p["full"] for p in storage.get("eu", [])}
    since = (week_start - datetime.timedelta(days=84)).isoformat()
    pts = [p for p in eu if p["date"] >= since][::7] + ([eu[-1]] if eu else [])
    seen, gas = set(), []
    for p in pts:
        if p["date"] in seen:
            continue
        seen.add(p["date"])
        d = datetime.date.fromisoformat(p["date"])
        gas.append((p["date"], p["full"], by_date.get(d.replace(year=d.year - 1).isoformat())))
    c["gas"] = gas
    rows = (load("chokepoints_history.json", {}) or {}).get("hormuz", [])
    vals = [r for r in rows if r.get("n_tanker") is not None and r["date"] <= end]
    ma = []
    for i, r in enumerate(vals):
        win = [x["n_tanker"] for x in vals[max(0, i - 6):i + 1]]
        ma.append((r["date"], round(sum(win) / len(win), 1)))
    c["sea"] = ma[-60:]
    c["sea_ref"] = ((load("market.json", {}) or {}).get("chokepoints", {}).get("hormuz") or {}).get("ref_tanker")
    return c


def make_chart(kind, c, s, lang):
    fr = lang == "fr"
    if kind == "power" and c["power"]:
        ref = s["spot"]["prev_avg"]
        return {"type": "bar", "unit": "€/MWh", "labels": [short_day(d, lang) for d, _ in c["power"]],
                "series": [{"name": "Spot moyen du jour" if fr else "Daily average spot", "color": COLORS["power"],
                            "data": [round(v, 2) for _, v in c["power"]]}],
                "ref": round(ref, 2) if ref else None,
                "ref_label": "Moyenne de la semaine précédente" if fr else "Previous week's average"}
    if kind == "gas" and c["gas"]:
        y = c["gas"][-1][0][:4]
        return {"type": "line", "unit": "%", "labels": [ddmm(d) for d, _, _ in c["gas"]],
                "series": [{"name": f"UE {y}" if fr else f"EU {y}", "color": COLORS["gas"], "data": [v for _, v, _ in c["gas"]]},
                           {"name": f"UE {int(y) - 1}" if fr else f"EU {int(y) - 1}", "color": COLORS["ref"], "dashed": True,
                            "data": [ly for _, _, ly in c["gas"]]}]}
    if kind == "oil" and c["oil"]:
        return {"type": "line", "unit": "$/b", "labels": [ddmm(d) for d, _ in c["oil"]],
                "series": [{"name": "Brent", "color": COLORS["oil"], "data": [v for _, v in c["oil"]]}]}
    if kind == "sea" and c["sea"]:
        return {"type": "line", "unit": "tankers/j" if fr else "tankers/d", "labels": [ddmm(d) for d, _ in c["sea"]],
                "series": [{"name": "Tankers par jour à Ormuz (moyenne 7 j)" if fr else "Tankers a day through Hormuz (7-day avg)",
                            "color": COLORS["sea"], "data": [v for _, v in c["sea"]]}],
                "ref": c["sea_ref"], "ref_label": "Normale (janv.-oct. 2023)" if fr else "Normal (Jan-Oct 2023)"}
    return None


def build(s, c, lang):
    """Contenu de la note dans une langue : titre, intro, contexte, tuiles, rubriques à puces, lecture clé."""
    fr = lang == "fr"
    tiles, sections, movers = [], [], []

    sp = s.get("spot")
    if sp:
        chg = (sp["avg"] - sp["prev_avg"]) / sp["prev_avg"] * 100 if sp["prev_avg"] else None
        tiles.append({"label": "Électricité, spot moyen" if fr else "Power, average spot", "value": num(sp["avg"], lang),
                      "unit": " €/MWh", "change": pct(chg, lang) if chg is not None else None,
                      "dir": direction(chg) if chg is not None else "flat"})
        if chg is not None:
            movers.append(("l'électricité", "power prices", "Électricité" if fr else "Power", chg))
        b = []
        if fr:
            b.append(f"Spot France : entre {num(sp['low'][1], lang)} et {num(sp['high'][1], lang)} €/MWh selon les jours, "
                     f"{num(sp['avg'], lang)} €/MWh en moyenne" + (f" ({pct(chg, lang)} sur une semaine)." if chg is not None else "."))
            b.append(f"Journée la plus chère : {day_label(sp['high'][0], lang)} ; la moins chère : {day_label(sp['low'][0], lang)}.")
            if sp["negative_days"]:
                b.append(f"Prix moyen négatif {sp['negative_days']} jour(s) dans la semaine.")
        else:
            b.append(f"French spot: between €{num(sp['low'][1], lang)} and €{num(sp['high'][1], lang)}/MWh depending on the day, "
                     f"€{num(sp['avg'], lang)}/MWh on average" + (f" ({pct(chg, lang)} week on week)." if chg is not None else "."))
            b.append(f"Most expensive day: {day_label(sp['high'][0], lang)}; cheapest: {day_label(sp['low'][0], lang)}.")
            if sp["negative_days"]:
                b.append(f"Negative daily average on {sp['negative_days']} day(s).")
        m = s.get("mix")
        if m:
            b.append(f"Production : nucléaire {num(m['nuclear'], lang, 0)} %, renouvelables {num(m['renewables'], lang, 0)} %, gaz {num(m['gas'], lang, 0)} %." if fr else
                     f"Generation: nuclear {num(m['nuclear'], lang, 0)}%, renewables {num(m['renewables'], lang, 0)}%, gas {num(m['gas'], lang, 0)}%.")
        sections.append({"key": "power", "title": "Électricité" if fr else "Electricity", "icon": "fa-bolt", "emoji": "⚡",
                         "bullets": b, "chart": make_chart("power", c, s, lang), "source": "RTE, Energy-Charts / SMARD"})

    b = []
    hh = s.get("hh")
    if hh:
        tiles.append({"label": "Henry Hub", "value": num(hh["last"], lang), "unit": " €/MWh",
                      "change": pct(hh["change"], lang), "dir": direction(hh["change"])})
        movers.append(("le gaz américain", "US gas", "Henry Hub", hh["change"]))
        b.append(f"Henry Hub (États-Unis) : entre {num(hh['low'][1], lang)} et {num(hh['high'][1], lang)} €/MWh, "
                 f"{num(hh['last'], lang)} €/MWh en fin de semaine ({pct(hh['change'], lang)})." if fr else
                 f"Henry Hub (US): between €{num(hh['low'][1], lang)} and €{num(hh['high'][1], lang)}/MWh, "
                 f"€{num(hh['last'], lang)}/MWh at the end of the week ({pct(hh['change'], lang)}).")
    eu, frs = s.get("storage_eu"), s.get("storage_fr")
    if eu:
        tiles.append({"label": "Stocks de gaz UE" if fr else "EU gas storage", "value": num(eu["full"], lang, 1), "unit": " %",
                      "change": f"{signed(eu['week'], lang)} pt" if eu["week"] is not None else None,
                      "dir": direction(eu["week"]) if eu["week"] is not None else "flat"})
        b.append((f"Stocks européens : {num(eu['full'], lang, 1)} % de remplissage" + (f" ({signed(eu['week'], lang)} point en une semaine)." if eu["week"] is not None else ".")) if fr else
                 (f"European storage: {num(eu['full'], lang, 1)}% full" + (f" ({signed(eu['week'], lang)} pt in a week)." if eu["week"] is not None else ".")))
        if eu["ly"] is not None:
            b.append(f"Par rapport à l'an dernier : {num(abs(eu['ly']), lang, 1)} points {'au-dessus' if eu['ly'] > 0 else 'en dessous'} à la même date." if fr else
                     f"Against last year: {num(abs(eu['ly']), lang, 1)} pts {'above' if eu['ly'] > 0 else 'below'} on the same date.")
        if frs:
            b.append(f"France : {num(frs['full'], lang, 1)} % de remplissage." if fr else f"France: {num(frs['full'], lang, 1)}% full.")
    if b:
        sections.append({"key": "gas", "title": "Gaz" if fr else "Gas", "icon": "fa-fire-flame-simple", "emoji": "🔥",
                         "bullets": b, "chart": make_chart("gas", c, s, lang),
                         "source": "OilPriceAPI, EIA, GIE AGSI+" + (", taux BCE" if fr else ", ECB rates")})

    b = []
    br = s.get("brent")
    if br:
        tiles.append({"label": "Brent", "value": num(br["last"], lang), "unit": " $/baril" if fr else " $/bbl",
                      "change": pct(br["change"], lang), "dir": direction(br["change"])})
        movers.append(("le Brent", "Brent", "Brent", br["change"]))
        b.append(f"Brent : entre {num(br['low'][1], lang)} et {num(br['high'][1], lang)} $ le baril, "
                 f"{num(br['last'], lang)} $ en fin de semaine ({pct(br['change'], lang)})." if fr else
                 f"Brent: between ${num(br['low'][1], lang)} and ${num(br['high'][1], lang)} a barrel, "
                 f"${num(br['last'], lang)} at the end of the week ({pct(br['change'], lang)}).")
    if "spread" in s:
        b.append(f"Écart Brent-WTI : {num(s['spread'], lang)} $ par baril." if fr else f"Brent-WTI spread: ${num(s['spread'], lang)} a barrel.")
    us = s.get("us_stocks")
    if us:
        b.append(f"Stocks de brut américains : {signed(us['change'], lang)} million{'s' if abs(us['change']) >= 2 else ''} de barils, à {num(us['mb'], lang, 1)} millions." if fr else
                 f"US crude inventories: {signed(us['change'], lang)} million barrels, to {num(us['mb'], lang, 1)} million.")
    fu = s.get("fuel")
    if fu and "gazole" in fu:
        g = fu["gazole"]
        cents = g["change"] * 100
        b.append((f"À la pompe : gazole {num(g['last'], lang, 3)} €/L ({signed(cents, lang)} centime{'s' if abs(cents) >= 2 else ''} sur la semaine)" if fr else
                  f"At the pump: diesel €{num(g['last'], lang, 3)}/L ({signed(cents, lang)} cents on the week)")
                 + ((f", SP95-E10 {num(fu['e10']['last'], lang, 3)} €/L." if fr else f", SP95-E10 €{num(fu['e10']['last'], lang, 3)}/L.") if "e10" in fu else "."))
    if b:
        sections.append({"key": "oil", "title": "Pétrole et carburants" if fr else "Oil and fuels", "icon": "fa-oil-well", "emoji": "🛢️",
                         "bullets": b, "chart": make_chart("oil", c, s, lang),
                         "source": "OilPriceAPI, EIA" + (", prix des carburants (data.economie.gouv.fr)" if fr else ", French fuel prices (data.economie.gouv.fr)")})

    b = []
    st = s["straits"]
    h = st.get("hormuz") or {}
    names = {"bab_el_mandeb": ("Bab-el-Mandeb", "Bab el-Mandeb"), "malacca": ("Malacca", "Malacca")}
    if h.get("pct") is not None:
        status = STATUS[lang].get(h["status"], "")
        tiles.append({"label": "Trafic à Ormuz" if fr else "Hormuz traffic", "value": str(h["pct"]),
                      "unit": " % de la normale" if fr else "% of normal", "change": status, "dir": "flat"})
        b.append(f"Ormuz : {h['pct']} % du trafic normal ({status}), données au {ddmm(h['date'])}." if fr else
                 f"Hormuz: {h['pct']}% of normal traffic ({status}), data as of {ddmm(h['date'])}.")
        other = [f"{names[k][0 if fr else 1]} {st[k]['pct']} %" if fr else f"{names[k][1]} {st[k]['pct']}%"
                 for k in names if (st.get(k) or {}).get("pct") is not None]
        if other:
            b.append(("Autres détroits : " if fr else "Other straits: ") + ", ".join(other) + ".")
    inc = s["incidents"]
    if inc["total"]:
        top = inc["top"]
        place = top[0] if fr else (inc["top_en"] or top[0])
        if not fr and place.startswith(("Strait", "Gulf", "Red Sea", "Northern", "Southern", "Indian", "Somali", "Arabian")):
            place = "the " + place
        all_there = top[1] == inc["total"]
        b.append((f"Incidents signalés au UKMTO : {inc['total']}, dont {inc['attacks']} attaque{'s' if inc['attacks'] > 1 else ''}, "
                  + (f"{'tous ' if inc['total'] > 1 else ''}{where_fr(place)}." if all_there else f"surtout {where_fr(place)} ({top[1]}).")) if fr else
                 (f"Incidents reported to UKMTO: {inc['total']}, including {inc['attacks']} attack{'s' if inc['attacks'] != 1 else ''}, "
                  + (f"all around {place}." if all_there else f"mostly around {place} ({top[1]}).")))
    else:
        b.append("Aucun incident en mer signalé au UKMTO cette semaine." if fr else "No incident at sea reported to UKMTO this week.")
    sections.append({"key": "sea", "title": "Routes maritimes et sécurité" if fr else "Shipping routes and security", "icon": "fa-ship",
                     "emoji": "🚢", "bullets": b, "chart": make_chart("sea", c, s, lang),
                     "source": "IMF PortWatch, UKMTO (Open Government Licence v3.0)"})

    # Contexte : les titres de la semaine (sources fiables, avec lien), dans la langue de la page
    # (sans doublon : un même sujet publié deux fois par un média n'apparaît qu'une fois)
    context = []
    for n in s["news"]:
        if n.get("lang", "en") != lang:
            continue
        words = {w for w in re.findall(r"\w+", n["title"].lower()) if len(w) > 4}
        if any(len(words & c["_w"]) >= 3 for c in context):
            continue
        context.append({"title": n["title"], "url": n["url"], "source": n["source"], "_w": words})
        if len(context) == 4:
            break
    for c in context:
        del c["_w"]

    # Titre et lecture clé : les deux plus gros mouvements de la semaine
    movers.sort(key=lambda m: abs(m[3]), reverse=True)
    top2 = movers[:2]
    if fr:
        parts = [f"{m[0]} {(SOAR_FR if m[3] > 10 else 'grimpe' if m[3] > 3 else 'progresse') if m[3] > 0 else ('chute' if m[3] < -10 else 'recule' if m[3] < -3 else 'fléchit')}"
                 for m in top2]
        headline = (lambda h: h[0].upper() + h[1:])(", ".join(parts)) if parts else "La semaine sur les marchés de l'énergie"
        reading = []
        if top2:
            reading.append("Semaine marquée par " + " et ".join(
                f"{'la hausse' if m[3] > 0 else 'le repli'} {('de l’' + m[0][2:]) if m[0].startswith('l’') else ('de ' + m[0]) if m[0].startswith(('l', 'L')) else ('du ' + m[0])} ({pct(m[3], lang)})"
                .replace("de le ", "du ").replace("de l'", "de l'") for m in top2) + ".")
        if h.get("status") in ("arret", "ferme"):
            reading.append("Le détroit d'Ormuz reste quasi fermé au trafic : un facteur de tension durable pour le pétrole et le GNL.")
        if eu and eu["ly"] is not None and eu["ly"] < -5:
            reading.append("Les stocks de gaz européens abordent l'hiver nettement en dessous de l'an dernier, ce qui rend le marché sensible au froid.")
    else:
        parts = [f"{m[1]} {('soar' if m[3] > 10 else 'jump' if m[3] > 3 else 'edge up') if m[3] > 0 else ('plunge' if m[3] < -10 else 'slip' if m[3] < -3 else 'ease')}{'' if m[1].endswith('prices') else 's'}"
                 for m in top2]
        headline = (lambda h: h[0].upper() + h[1:])(", ".join(parts)) if parts else "The week on energy markets"
        reading = []
        if top2:
            reading.append("A week marked by " + " and ".join(
                f"{'a rise' if m[3] > 0 else 'a fall'} in {m[1]} ({pct(m[3], lang)})" for m in top2) + ".")
        if h.get("status") in ("arret", "ferme"):
            reading.append("The Strait of Hormuz remains almost closed to traffic: a lasting source of tension for oil and LNG.")
        if eu and eu["ly"] is not None and eu["ly"] < -5:
            reading.append("European gas storage heads into winter well below last year, leaving the market sensitive to cold weather.")
    start, end = datetime.date.fromisoformat(s["start"]), datetime.date.fromisoformat(s["end"])
    intro = (f"Semaine du {date_long(start, lang).replace(' ' + str(start.year), '') if start.year == end.year else date_long(start, lang)} au {date_long(end, lang)} : "
             f"ce qu'il faut retenir sur l'électricité, le gaz, le pétrole et les routes maritimes." if fr else
             f"Week of {date_long(start, lang).replace(' ' + str(start.year), '') if start.year == end.year else date_long(start, lang)} to {date_long(end, lang)}: "
             f"what to remember on electricity, gas, oil and shipping routes.")
    return {"headline": headline, "intro": intro, "context": context, "tiles": tiles, "sections": sections,
            "reading": " ".join(reading)}


def yaml_value(v):
    return json.dumps(v, ensure_ascii=False)


def note_date(end):
    """Lundi 0 h (Paris) qui suit la semaine. Si la note est générée avant (essai en cours de
    semaine), on prend l'instant présent : Jekyll ne publie pas les contenus datés dans le futur."""
    monday = datetime.datetime.combine(end + datetime.timedelta(days=1), datetime.time(0, 0),
                                       tzinfo=datetime.timezone(datetime.timedelta(hours=2)))
    now = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
    return min(monday, now).strftime("%Y-%m-%d %H:%M:%S %z")


def write_note(s, c, lang, week, force):
    year, wk = week
    path = os.path.join(NOTES_DIR, f"{year}-{wk:02d}-{lang}.md")
    if os.path.exists(path) and not force:
        print(f"Note déjà présente, conservée : {path}")
        return None
    n = build(s, c, lang)
    end = datetime.date.fromisoformat(s["end"])
    title = (f"Note de marché, semaine {wk} : {n['headline'][0].lower() + n['headline'][1:]}" if lang == "fr" else
             f"Market note, week {wk}: {n['headline'][0].lower() + n['headline'][1:]}")
    front = {
        "layout": "note", "lang": lang, "ref": f"note-{year}-{wk:02d}", "title": title,
        "description": n["intro"] + " " + n["reading"], "date": note_date(end),
        "permalink": f"/blog/note-de-marche-{year}-s{wk:02d}/" if lang == "fr" else f"/en/blog/market-note-{year}-w{wk:02d}/",
        "week": wk, "year": year, "period_start": s["start"], "period_end": s["end"],
        **n,
    }
    os.makedirs(NOTES_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("---\n")
        for k, v in front.items():
            f.write(f"{k}: {yaml_value(v)}\n")
        f.write("---\n\n")
        f.write("<!-- Le mot de Tom (facultatif) : écrire ici un paragraphe en Markdown, il s'affichera en tête de la note. -->\n"
                if lang == "fr" else
                "<!-- Tom's note (optional): write a Markdown paragraph here, it will appear at the top of the note. -->\n")
    print(f"Note écrite : {path}")
    return front


def write_linkedin(front, week):
    """Texte prêt à coller sur LinkedIn, au format des notes de marché du secteur (émojis, puces)."""
    if not front:
        return
    os.makedirs(LINKEDIN_DIR, exist_ok=True)
    year, wk = week
    lines = [f"[NOTE DE MARCHÉ HEBDO] {front['headline']}", "", front["intro"], ""]
    if front["context"]:
        lines.append("🔍 CONTEXTE")
        lines += [f"• {c['title']} ({c['source']})" for c in front["context"][:3]]
        lines.append("")
    for sec in front["sections"]:
        lines.append(f"{sec['emoji']} {sec['title'].upper()}")
        lines += [f"• {b}" for b in sec["bullets"]]
        lines.append("")
    if front["reading"]:
        lines += [f"👉 Lecture clé : {front['reading']}", ""]
    lines += [f"La note complète, avec les graphiques : https://insideenergymarkets.com{front['permalink']}", "",
              "#énergie #marchésdelénergie #électricité #gaz #pétrole"]
    with open(os.path.join(LINKEDIN_DIR, f"{year}-{wk:02d}.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", help="semaine ISO, ex. 2026-W40 (par défaut : la dernière semaine complète)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if args.week:
        y, w = args.week.upper().split("-W")
        week_start = datetime.date.fromisocalendar(int(y), int(w), 1)
    else:
        today = datetime.date.today()
        week_start = today - datetime.timedelta(days=today.weekday() + 7)
    iso = week_start.isocalendar()
    week = (iso[0], iso[1])
    s = compute(week_start)
    c = chart_series(week_start)
    fr = write_note(s, c, "fr", week, args.force)
    write_note(s, c, "en", week, args.force)
    write_linkedin(fr, week)
    return 0


if __name__ == "__main__":
    sys.exit(main())
