"""
Note de marché hebdomadaire, générée chaque lundi par .github/workflows/weekly-note.yml.

Calcule les chiffres de la semaine écoulée (lundi au dimanche) à partir des données du site
(_data/*.json) et écrit deux fichiers dans la collection _notes (français et anglais), plus un
texte prêt à coller pour LinkedIn dans _linkedin/ (hors site). Les phrases sont construites à
partir des chiffres (pas d'IA) : chaque valeur vient d'une source citée sur la page.

Usage : python scripts/generate_note.py [--week 2026-W40] [--force]
Par défaut, la dernière semaine complète. --force réécrit une note existante (sinon on la garde,
pour ne pas écraser un « mot de Tom » ajouté à la main).
"""
import argparse
import datetime
import json
import os
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


def write_texts(s, lang):
    """Phrases de la note dans une langue. Renvoie (chapô, tuiles, rubriques)."""
    fr = lang == "fr"
    eur = " €/MWh"
    tiles, sections, lede = [], [], []

    if "spot" in s:
        sp = s["spot"]
        tiles.append({"label": "Électricité, spot moyen" if fr else "Power, average spot",
                      "value": num(sp["avg"], lang), "unit": eur,
                      "change": pct((sp["avg"] - sp["prev_avg"]) / sp["prev_avg"] * 100, lang) if sp["prev_avg"] else None,
                      "dir": direction(sp["avg"] - sp["prev_avg"]) if sp["prev_avg"] else "flat"})
        p = []
        if fr:
            p.append(f"Le prix spot de l'électricité en France a été de {num(sp['avg'], lang)} €/MWh en moyenne cette semaine"
                     + (f", contre {num(sp['prev_avg'], lang)} €/MWh la semaine précédente ({pct((sp['avg'] - sp['prev_avg']) / sp['prev_avg'] * 100, lang)})." if sp["prev_avg"] else "."))
            p.append(f"La journée la plus chère a été {day_label(sp['high'][0], lang)} ({num(sp['high'][1], lang)} €/MWh), "
                     f"la moins chère {day_label(sp['low'][0], lang)} ({num(sp['low'][1], lang)} €/MWh).")
            if sp["negative_days"]:
                p.append(f"Le prix moyen est passé sous zéro {sp['negative_days']} jour(s).")
        else:
            p.append(f"The French power spot price averaged €{num(sp['avg'], lang)}/MWh this week"
                     + (f", against €{num(sp['prev_avg'], lang)}/MWh the week before ({pct((sp['avg'] - sp['prev_avg']) / sp['prev_avg'] * 100, lang)})." if sp["prev_avg"] else "."))
            p.append(f"The most expensive day was {day_label(sp['high'][0], lang)} (€{num(sp['high'][1], lang)}/MWh), "
                     f"the cheapest {day_label(sp['low'][0], lang)} (€{num(sp['low'][1], lang)}/MWh).")
            if sp["negative_days"]:
                p.append(f"The daily average fell below zero on {sp['negative_days']} day(s).")
        if "mix" in s:
            m = s["mix"]
            p.append(f"Côté production, le nucléaire a fourni en moyenne {num(m['nuclear'], lang, 0)} % de l'électricité, "
                     f"les renouvelables {num(m['renewables'], lang, 0)} % et le gaz {num(m['gas'], lang, 0)} %." if fr else
                     f"Nuclear supplied {num(m['nuclear'], lang, 0)}% of generation on average, "
                     f"renewables {num(m['renewables'], lang, 0)}% and gas {num(m['gas'], lang, 0)}%.")
        sections.append({"key": "power", "title": "Électricité" if fr else "Electricity", "icon": "fa-bolt",
                         "text": p, "source": "RTE, Energy-Charts / SMARD"})

    p = []
    hh = s.get("hh")
    if hh:
        tiles.append({"label": "Henry Hub", "value": num(hh["last"], lang), "unit": eur,
                      "change": pct(hh["change"], lang), "dir": direction(hh["change"])})
        p.append(f"Le gaz américain (Henry Hub) termine la semaine à {num(hh['last'], lang)} €/MWh, soit {pct(hh['change'], lang)} sur la semaine." if fr else
                 f"US gas (Henry Hub) ended the week at €{num(hh['last'], lang)}/MWh, {pct(hh['change'], lang)} over the week.")
    eu, frs = s.get("storage_eu"), s.get("storage_fr")
    if eu:
        tiles.append({"label": "Stocks de gaz UE" if fr else "EU gas storage", "value": num(eu["full"], lang, 1),
                      "unit": " %", "change": (f"{signed(eu['week'], lang)} pt" if eu["week"] is not None else None),
                      "dir": "flat"})
        if fr:
            txt = f"Les stockages européens sont remplis à {num(eu['full'], lang, 1)} %"
            if eu["week"] is not None:
                txt += f" ({'+' if eu['week'] > 0 else ''}{num(eu['week'], lang, 1)} point en une semaine)"
            if eu["ly"] is not None:
                txt += f", {num(abs(eu['ly']), lang, 1)} point{'s' if abs(eu['ly']) >= 2 else ''} {'au-dessus' if eu['ly'] > 0 else 'en dessous'} du niveau de l'an dernier à la même date"
            txt += "."
            if frs:
                txt += f" En France, le taux atteint {num(frs['full'], lang, 1)} %."
        else:
            txt = f"European storage is {num(eu['full'], lang, 1)}% full"
            if eu["week"] is not None:
                txt += f" ({'+' if eu['week'] > 0 else ''}{num(eu['week'], lang, 1)} pt in a week)"
            if eu["ly"] is not None:
                txt += f", {num(abs(eu['ly']), lang, 1)} pts {'above' if eu['ly'] > 0 else 'below'} last year's level on the same date"
            txt += "."
            if frs:
                txt += f" In France, storage stands at {num(frs['full'], lang, 1)}%."
        p.append(txt)
    if p:
        sections.append({"key": "gas", "title": "Gaz" if fr else "Gas", "icon": "fa-fire-flame-simple", "text": p,
                         "source": "OilPriceAPI, EIA, GIE AGSI+" + (", taux BCE" if fr else ", ECB rates")})

    p = []
    b = s.get("brent")
    if b:
        tiles.append({"label": "Brent", "value": num(b["last"], lang), "unit": " $/b" if not fr else " $/baril",
                      "change": pct(b["change"], lang), "dir": direction(b["change"])})
        lede.append((f"Brent {pct(b['change'], lang)} sur la semaine" if fr else f"Brent {pct(b['change'], lang)} on the week"))
        if fr:
            p.append(f"Le Brent termine la semaine à {num(b['last'], lang)} $ le baril ({pct(b['change'], lang)}), "
                     f"après un plus haut à {num(b['high'][1], lang)} $ {day_label(b['high'][0], lang)} et un plus bas à {num(b['low'][1], lang)} $ {day_label(b['low'][0], lang)}.")
        else:
            p.append(f"Brent ended the week at ${num(b['last'], lang)} a barrel ({pct(b['change'], lang)}), "
                     f"after a high of ${num(b['high'][1], lang)} on {day_label(b['high'][0], lang)} and a low of ${num(b['low'][1], lang)} on {day_label(b['low'][0], lang)}.")
    if "spread" in s:
        p.append(f"L'écart avec le WTI américain est de {num(s['spread'], lang)} $ par baril." if fr else
                 f"The spread with US WTI stands at ${num(s['spread'], lang)} a barrel.")
    us = s.get("us_stocks")
    if us:
        p.append((f"Les stocks de brut américains {'augmentent' if us['change'] > 0 else 'reculent'} de {num(abs(us['change']), lang, 1)} million{'s' if abs(us['change']) >= 2 else ''} de barils, à {num(us['mb'], lang, 1)} millions." if fr else
                  f"US crude inventories {'rose' if us['change'] > 0 else 'fell'} by {num(abs(us['change']), lang, 1)} million barrels, to {num(us['mb'], lang, 1)} million."))
    fu = s.get("fuel")
    if fu and "gazole" in fu:
        g = fu["gazole"]
        lede.append(f"gazole à {num(g['last'], lang, 3)} €/L" if fr else f"French diesel at €{num(g['last'], lang, 3)}/L")
        cents = g["change"] * 100
        p.append((f"À la pompe, le gazole coûte en moyenne {num(g['last'], lang, 3)} € le litre en France "
                  f"({signed(cents, lang)} centime{'s' if abs(cents) >= 2 else ''} sur la semaine)" if fr else
                  f"At the pump, diesel averages €{num(g['last'], lang, 3)} a litre in France "
                  f"({signed(cents, lang)} cents on the week)")
                 + ((f", l'E10 {num(fu['e10']['last'], lang, 3)} €." if fr else f", E10 €{num(fu['e10']['last'], lang, 3)}.") if "e10" in fu else "."))
    if p:
        sections.append({"key": "oil", "title": "Pétrole et carburants" if fr else "Oil and fuels", "icon": "fa-oil-well",
                         "text": p, "source": "OilPriceAPI, EIA" + (", prix des carburants (data.economie.gouv.fr)" if fr else ", French fuel prices (data.economie.gouv.fr)")})

    p = []
    st = s["straits"]
    names = {"hormuz": ("le détroit d'Ormuz", "the Strait of Hormuz"), "bab_el_mandeb": ("Bab-el-Mandeb", "Bab el-Mandeb"),
             "malacca": ("Malacca", "Malacca")}
    h = st.get("hormuz") or {}
    if h.get("pct") is not None:
        tiles.append({"label": "Trafic à Ormuz" if fr else "Hormuz traffic", "value": str(h["pct"]),
                      "unit": " % de la normale" if fr else "% of normal", "change": None, "dir": "flat"})
        status = STATUS[lang].get(h["status"], "")
        lede.append((f"Ormuz {status}" if fr else f"Hormuz {status}"))
        other = [f"{names[k][0 if fr else 1]} {st[k]['pct']} %" if fr else f"{names[k][1]} {st[k]['pct']}%"
                 for k in ("bab_el_mandeb", "malacca") if (st.get(k) or {}).get("pct") is not None]
        p.append((f"Le trafic dans le détroit d'Ormuz est à {h['pct']} % de la normale ({status}, dernières données publiées au "
                  f"{datetime.date.fromisoformat(h['date']).strftime('%d/%m')})." if fr else
                  f"Traffic through the Strait of Hormuz is at {h['pct']}% of normal ({status}, latest data published for "
                  f"{datetime.date.fromisoformat(h['date']).strftime('%d/%m')}).")
                 + ((" Ailleurs : " if fr else " Elsewhere: ") + ", ".join(other) + "." if other else ""))
    inc = s["incidents"]
    if inc["total"]:
        top = inc["top"]
        place = top[0] if fr else (inc["top_en"] or top[0])
        if not fr and place.startswith(("Strait", "Gulf", "Red Sea", "Northern", "Southern", "Indian", "Somali", "Arabian")):
            place = "the " + place
        all_there = top[1] == inc["total"]
        p.append((f"Le UKMTO a recensé {inc['total']} incident{'s' if inc['total'] > 1 else ''} en mer, dont {inc['attacks']} attaque{'s' if inc['attacks'] > 1 else ''}, "
                  + (f"{'tous' if inc['total'] > 1 else ''} {where_fr(place)}.".strip() if all_there else f"surtout {where_fr(place)} ({top[1]}).") if fr else
                  f"UKMTO recorded {inc['total']} incident{'s' if inc['total'] > 1 else ''} at sea, including {inc['attacks']} attack{'s' if inc['attacks'] != 1 else ''}, "
                  + (f"all around {place}." if all_there else f"mostly around {place} ({top[1]}).")))
    else:
        p.append("Aucun incident en mer n'a été signalé au UKMTO cette semaine." if fr else
                 "No incident at sea was reported to UKMTO this week.")
    sections.append({"key": "sea", "title": "Routes maritimes et sécurité" if fr else "Shipping routes and security",
                     "icon": "fa-ship", "text": p, "source": "IMF PortWatch, UKMTO (Open Government Licence v3.0)"})

    news = [{"title": n["title"], "url": n["url"], "source": n["source"]} for n in s["news"] if n.get("lang", "en") == lang][:5]
    lede_txt = ", ".join(lede[:3])
    lede_txt = (lede_txt[0].upper() + lede_txt[1:] + ".") if lede_txt else ""
    return lede_txt, tiles, sections, news


def note_date(end):
    """Lundi 0 h (Paris) qui suit la semaine. Si la note est générée avant (essai en cours de
    semaine), on prend l'instant présent : Jekyll ne publie pas les contenus datés dans le futur."""
    monday = datetime.datetime.combine(end + datetime.timedelta(days=1), datetime.time(0, 0),
                                       tzinfo=datetime.timezone(datetime.timedelta(hours=2)))
    now = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
    return min(monday, now).strftime("%Y-%m-%d %H:%M:%S %z")


def yaml_value(v):
    return json.dumps(v, ensure_ascii=False)


def write_note(s, lang, week, force):
    year, wk = week
    slug = f"{year}-s{wk:02d}" if lang == "fr" else f"{year}-w{wk:02d}"
    path = os.path.join(NOTES_DIR, f"{year}-{wk:02d}-{lang}.md")
    if os.path.exists(path) and not force:
        print(f"Note déjà présente, conservée : {path}")
        return None
    lede, tiles, sections, news = write_texts(s, lang)
    start, end = datetime.date.fromisoformat(s["start"]), datetime.date.fromisoformat(s["end"])
    title = (f"Note de marché, semaine {wk} : du {date_long(start, lang)} au {date_long(end, lang)}" if lang == "fr" else
             f"Market note, week {wk}: {date_long(start, lang)} to {date_long(end, lang)}")
    if lang == "fr" and start.year == end.year:
        title = f"Note de marché, semaine {wk} : du {start.day}{'er' if start.day == 1 else ''} {MONTHS['fr'][start.month - 1] if start.month != end.month else ''} au {date_long(end, lang)}".replace("  ", " ")
    front = {
        "layout": "note", "lang": lang, "ref": f"note-{year}-{wk:02d}", "title": title,
        "description": lede, "date": note_date(end),
        "permalink": f"/notes/{slug}/" if lang == "fr" else f"/en/notes/{slug}/",
        "week": wk, "year": year, "period_start": s["start"], "period_end": s["end"],
        "lede": lede, "tiles": tiles, "sections": sections, "news": news,
    }
    os.makedirs(NOTES_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("---\n")
        for k, v in front.items():
            f.write(f"{k}: {yaml_value(v)}\n")
        f.write("---\n")
        f.write("\n" if lang == "fr" else "\n")
        f.write("<!-- Le mot de Tom (facultatif) : écrire ici un paragraphe en Markdown, il s'affichera en tête de la note. -->\n"
                if lang == "fr" else
                "<!-- Tom's note (optional): write a Markdown paragraph here, it will appear at the top of the note. -->\n")
    print(f"Note écrite : {path}")
    return front


def write_linkedin(front, week):
    if not front:
        return
    os.makedirs(LINKEDIN_DIR, exist_ok=True)
    year, wk = week
    lines = [front["title"], "", front["lede"], ""]
    for t in front["tiles"]:
        lines.append(f"• {t['label']} : {t['value']}{t['unit']}" + (f" ({t['change']})" if t.get("change") else ""))
    lines += ["", f"La note complète : https://insideenergymarkets.com{front['permalink']}", "",
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
    fr = write_note(s, "fr", week, args.force)
    write_note(s, "en", week, args.force)
    write_linkedin(fr, week)
    return 0


if __name__ == "__main__":
    sys.exit(main())
