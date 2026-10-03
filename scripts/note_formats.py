"""Maquette des 5 formats de note de marché (A tableau de bord, B base 100, C éditorial, D 3 chiffres,
E électricité à la loupe) et de 5 textes LinkedIn, sur les données réelles d'une semaine. Le format A est celui
de generate_note.py ; les autres servent de modèles pour des notes « focus ». Usage :
  python scripts/note_formats.py <fichier.html>   (WEEK_START à régler ci-dessous ; servir le site construit
  pour que la photo /assets/img/tom.webp s'affiche)"""
import datetime
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT + "/scripts")
import generate_note as g  # noqa: E402

OUT = sys.argv[1]
WEEK_START = datetime.date(2026, 9, 28)
s = g.compute(WEEK_START)
START, END = s["start"], s["end"]
hist = g.load("market_history.json", [])
storage = g.load("gas_storage.json", {})
da = g.load("day_ahead.json", {})
fuel = g.load("fuel.json", {})
market = g.load("market.json", {})

N = lambda v, d=2: g.num(v, "fr", d)  # noqa: E731
P = lambda v, d=1: g.pct(v, "fr", d)  # noqa: E731
SG = lambda v, d=1: g.signed(v, "fr", d)  # noqa: E731
DAYS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]


def dlabel(d):
    x = datetime.date.fromisoformat(d)
    return f"{DAYS[x.weekday()]} {x.day}"


def ddmm(d):
    x = datetime.date.fromisoformat(d)
    return f"{x.day:02d}/{x.month:02d}"


def last_n(field, days=30):
    pts = [(h["date"], h[field]) for h in hist if h.get(field) is not None and h["date"] <= END]
    cut = (datetime.date.fromisoformat(END) - datetime.timedelta(days=days)).isoformat()
    return [p for p in pts if p[0] > cut]


# ---------- Chiffres de la semaine ----------
sp, br, hh = s["spot"], s["brent"], s["hh"]
spot_chg = (sp["avg"] - sp["prev_avg"]) / sp["prev_avg"] * 100
st_eu, st_fr = s["storage_eu"], s["storage_fr"]
fu = s.get("fuel", {})
us = s.get("us_stocks")
spread = s.get("spread")

spot_week = [(d, v) for d, v in g.series(hist, "spot_eur_mwh") if START <= d <= END]
brent_week = [(d, v) for d, v in g.series(hist, "brent_usd") if START <= d <= END]
hh_week = [(d, v) for d, v in g.series(hist, "henry_hub_eur_mwh") if START <= d <= END]


def stats(points, unit, week_ref=None, last_label=None):
    vals = [v for _, v in points]
    last_d, last = points[-1]
    lo = min(points, key=lambda p: p[1]); hi = max(points, key=lambda p: p[1])
    out = [("Dernier", N(last), unit, f"{dlabel(last_d)}" + (f" · {last_label}" if last_label else ""))]
    if week_ref:
        ch = (last - week_ref) / week_ref * 100
        out.append(("Sur la semaine", P(ch), "", f"{SG(last - week_ref, 2)} {unit}", "up" if ch > 0 else "down"))
    out += [("Plus bas", N(lo[1]), unit, dlabel(lo[0])), ("Plus haut", N(hi[1]), unit, dlabel(hi[0])),
            ("Moyenne", N(sum(vals) / len(vals)), unit, f"{len(vals)} jours de cotation")]
    return out


def series_obj(points, name, color, fill=True, dashed=False):
    return {"name": name, "color": color, "data": [round(v, 2) for _, v in points], "fill": fill, "dashed": dashed}


C = {"power": "#00817d", "gas": "#e8b33a", "oil": "#e8703a", "ref": "#94a3b8", "teal2": "#4fd1c5"}

spot30, brent30, hh30 = last_n("spot_eur_mwh"), last_n("brent_usd"), last_n("henry_hub_eur_mwh")

charts = {}
charts["spot30"] = {"type": "line", "unit": "€/MWh", "labels": [d for d, _ in spot30], "series": [series_obj(spot30, "Spot France", C["power"])],
                    "band": [START, END]}
charts["brent30"] = {"type": "line", "unit": "$/b", "labels": [d for d, _ in brent30], "series": [series_obj(brent30, "Brent", C["oil"])], "band": [START, END]}
charts["hh30"] = {"type": "line", "unit": "€/MWh", "labels": [d for d, _ in hh30], "series": [series_obj(hh30, "Henry Hub", C["gas"])], "band": [START, END]}


# Base 100 sur 30 jours, moyennes mobiles 7 j (même méthode que la page Marchés)
def ma7(points):
    out = []
    for i, (d, _) in enumerate(points):
        w = [v for _, v in points[max(0, i - 6): i + 1]]
        out.append((d, sum(w) / len(w)))
    return out


def base100(points):
    m = ma7(points)
    ref = m[0][1]
    return {d: v / ref * 100 for d, v in m}


b_sp, b_br, b_hh = base100(spot30), base100(brent30), base100(hh30)
labels_b = sorted(set(b_sp) | set(b_br) | set(b_hh))
charts["base100"] = {"type": "line", "unit": "", "labels": labels_b, "base": True, "series": [
    {"name": "Électricité FR", "color": C["power"], "data": [round(b_sp[d], 1) if d in b_sp else None for d in labels_b]},
    {"name": "Brent", "color": C["oil"], "data": [round(b_br[d], 1) if d in b_br else None for d in labels_b]},
    {"name": "Henry Hub", "color": C["gas"], "data": [round(b_hh[d], 1) if d in b_hh else None for d in labels_b]}]}
ranking = sorted([("Électricité FR", b_sp[max(b_sp)] - 100, C["power"]), ("Brent", b_br[max(b_br)] - 100, C["oil"]),
                  ("Henry Hub", b_hh[max(b_hh)] - 100, C["gas"])], key=lambda r: -r[1])

# Stocks UE : cette année vs l'an dernier (depuis le 1er juillet)
eu = storage.get("eu", [])
this = [p for p in eu if "2026-07-01" <= p["date"] <= END]
ly = {p["date"][5:]: p["full"] for p in eu if p["date"].startswith("2025")}
charts["storage"] = {"type": "line", "unit": "%", "labels": [p["date"] for p in this], "series": [
    {"name": "2026", "color": C["gas"], "data": [p["full"] for p in this], "fill": True},
    {"name": "2025", "color": C["ref"], "data": [ly.get(p["date"][5:]) for p in this], "dashed": True}]}

# Spot de la semaine, jour par jour, face à la moyenne de la semaine précédente
charts["spotweek"] = {"type": "bar", "unit": "€/MWh", "labels": [dlabel(d) for d, _ in spot_week],
                      "series": [series_obj(spot_week, "Spot du jour", C["power"])], "ref": round(sp["prev_avg"], 2),
                      "ref_label": "Moyenne de la semaine précédente"}

# Day-ahead : profil horaire de chaque jour, voisins
fr_days = sorted(d for d in da.get("fr", {}) if START <= d <= END)
pal = ["#4fd1c5", "#00817d", "#e8b33a", "#e8703a", "#c77dff", "#94a3b8", "#ff6b5b"]
charts["hourly"] = {"type": "line", "unit": "€/MWh", "labels": [h for h, _ in da["fr"][fr_days[0]]["hourly"]] if fr_days else [],
                    "hourly": True,
                    "series": [{"name": dlabel(d), "color": pal[i % len(pal)], "data": [v for _, v in da["fr"][d]["hourly"]], "fill": False}
                               for i, d in enumerate(fr_days)]}
NB = {"DE": "Allemagne", "BE": "Belgique", "NL": "Pays-Bas", "ES": "Espagne", "IT": "Italie", "CH": "Suisse"}
nb_avg = {}
for c, vals in da.get("neighbors", {}).items():
    v = [x for d, x in vals.items() if d in fr_days]
    if v:
        nb_avg[c] = sum(v) / len(v)
fr_avg = sum(da["fr"][d]["avg"] for d in fr_days) / len(fr_days) if fr_days else None
bars = sorted([("France", fr_avg)] + [(NB[c], v) for c, v in nb_avg.items()], key=lambda r: r[1])
charts["neighbors"] = {"type": "bar", "unit": "€/MWh", "horizontal": True, "labels": [b[0] for b in bars],
                       "series": [{"name": "Moyenne day-ahead", "color": C["power"], "data": [round(b[1], 2) for b in bars],
                                   "colors": ["#e8703a" if b[0] == "France" else "#00817d" for b in bars]}]}
hourly_profile = None
if fr_days:
    prof = [sum(da["fr"][d]["hourly"][h][1] for d in fr_days) / len(fr_days) for h in range(24)]
    hourly_profile = {"min_h": prof.index(min(prof)), "min": min(prof), "max_h": prof.index(max(prof)), "max": max(prof)}

# Gazole sur 60 jours
fh = fuel.get("history", {})
fdays = sorted(d for d in fh if d <= END)[-60:]
charts["diesel"] = {"type": "line", "unit": "€/L", "labels": fdays, "digits": 3,
                    "series": [{"name": "Gazole", "color": C["oil"], "data": [fh[d].get("gazole") for d in fdays], "fill": True}]}

# Sparklines pour la version « 3 chiffres »
charts["spk_spot"] = {"type": "line", "spark": True, "unit": "€/MWh", "labels": [d for d, _ in spot30], "series": [series_obj(spot30, "Spot", C["teal2"])]}
charts["spk_brent"] = {"type": "line", "spark": True, "unit": "$/b", "labels": [d for d, _ in brent30], "series": [series_obj(brent30, "Brent", C["oil"])]}
charts["spk_storage"] = {"type": "line", "spark": True, "unit": "%", "labels": [p["date"] for p in this], "series": [
    {"name": "2026", "color": C["gas"], "data": [p["full"] for p in this], "fill": True},
    {"name": "2025", "color": C["ref"], "data": [ly.get(p["date"][5:]) for p in this], "dashed": True}]}

# ---------- Phrases (uniquement à partir des données) ----------
up = lambda x: "hausse" if x > 0 else "baisse"  # noqa: E731
mix = s["mix"]
period = f"du {g.date_long(datetime.date.fromisoformat(START), 'fr')} au {g.date_long(datetime.date.fromisoformat(END), 'fr')}".replace(" 2026 au", " au")
headline = "L'électricité s'envole, le gaz américain recule"
reading = (f"L'électricité française a nettement monté ({P(spot_chg)} en moyenne sur la semaine), le gaz américain s'est replié "
           f"({P(hh['change'])}) et le Brent a terminé en {up(br['change'])} ({P(br['change'])}). Les stocks de gaz européens "
           f"progressent ({SG(st_eu['week'])} point en une semaine) mais restent {N(abs(st_eu['ly']), 1)} points sous leur niveau de l'an dernier.")

bul_power = [f"Spot France : {N(sp['avg'])} €/MWh en moyenne, contre {N(sp['prev_avg'])} la semaine précédente ({P(spot_chg)}).",
             f"Journée la plus chère : {g.day_label(sp['high'][0], 'fr')} ({N(sp['high'][1])} €/MWh) ; la moins chère : {g.day_label(sp['low'][0], 'fr')} ({N(sp['low'][1])} €/MWh).",
             f"Production : nucléaire {N(mix['nuclear'], 0)} %, renouvelables {N(mix['renewables'], 0)} %, gaz {N(mix['gas'], 0)} %."]
if hourly_profile:
    bul_power.append(f"Heure la plus chère en moyenne : {hourly_profile['max_h']} h ({N(hourly_profile['max'])} €/MWh) ; la moins chère : {hourly_profile['min_h']} h ({N(hourly_profile['min'])} €/MWh).")
bul_gas = [f"Henry Hub (États-Unis) : {N(hh['last'])} €/MWh en fin de semaine ({P(hh['change'])}), entre {N(hh['low'][1])} et {N(hh['high'][1])}.",
           f"Stocks européens : {N(st_eu['full'], 1)} % de remplissage ({SG(st_eu['week'])} point en une semaine), {N(abs(st_eu['ly']), 1)} points sous l'an dernier.",
           f"France : {N(st_fr['full'], 1)} % ({SG(st_fr['week'])} points en une semaine)."]
bul_oil = [f"Brent : {N(br['last'])} $ le baril en fin de semaine ({P(br['change'])}), entre {N(br['low'][1])} et {N(br['high'][1])} $."]
if spread:
    bul_oil.append(f"Écart Brent-WTI : {N(spread)} $ par baril.")
if us:
    bul_oil.append(f"Stocks de brut américains : {SG(us['change'])} million de barils, à {N(us['mb'], 1)} millions.")
if fu.get("gazole"):
    bul_oil.append(f"À la pompe : gazole {N(fu['gazole']['last'], 3)} €/L ({SG(fu['gazole']['change'] * 100, 1)} centime sur la semaine), SP95-E10 {N(fu['e10']['last'], 3)} €/L.")

ORMUZ = re.compile(r"ormuz|hormuz", re.I)
press = [n for n in s["news"] if n.get("lang") == "fr" and not ORMUZ.search(n["title"])][:4]

# Paragraphes (version éditoriale)
para_power = (f"Sur le marché de gros français, le prix spot a fait un bond : {N(sp['avg'])} €/MWh en moyenne cette semaine, "
              f"contre {N(sp['prev_avg'])} la semaine précédente, soit {P(spot_chg)}. Le pic a été atteint {g.day_label(sp['high'][0], 'fr')} "
              f"({N(sp['high'][1])} €/MWh) et le creux {g.day_label(sp['low'][0], 'fr')} ({N(sp['low'][1])} €/MWh). "
              f"Le nucléaire a assuré {N(mix['nuclear'], 0)} % de la production, les renouvelables {N(mix['renewables'], 0)} % et le gaz {N(mix['gas'], 0)} %.")
para_gas = (f"Côté gaz, le Henry Hub américain termine la semaine à {N(hh['last'])} €/MWh ({P(hh['change'])}). En Europe, le remplissage "
            f"des stockages continue ({N(st_eu['full'], 1)} %, {SG(st_eu['week'])} point en une semaine), mais l'écart avec l'an dernier "
            f"reste marqué : {N(abs(st_eu['ly']), 1)} points de moins à la même date. La France est mieux placée, à {N(st_fr['full'], 1)} %.")
para_oil = (f"Le Brent a reculé à {N(br['last'])} $ le baril ({P(br['change'])}), après un plus haut à {N(br['high'][1])} $ {g.day_label(br['high'][0], 'fr')}. "
            + (f"L'écart avec le WTI américain reste large, à {N(spread)} $. " if spread else "")
            + (f"À la pompe, le gazole s'établit à {N(fu['gazole']['last'], 3)} €/L." if fu.get("gazole") else ""))

# ---------- LinkedIn : 5 textes ----------
URL = "https://insideenergymarkets.com/analyses/note-de-marche-2026-s40/"
TAGS = "#énergie #marchésdelénergie #électricité #gaz #pétrole"
li = []
li.append(("1. Note structurée (format actuel, Lecture clé en tête)", "Graphique base 100 des trois marchés", f"""[NOTE DE MARCHÉ HEBDO] {headline}

👉 {reading}

⚡ ÉLECTRICITÉ
• {bul_power[0]}
• {bul_power[1]}
• {bul_power[2]}

🔥 GAZ
• {bul_gas[0]}
• {bul_gas[1]}

🛢️ PÉTROLE
• {bul_oil[0]}
• {bul_oil[-1]}

📊 La note complète, avec les graphiques : {URL}

{TAGS}"""))
li.append(("2. Les 3 chiffres de la semaine", "Trois cartes chiffres (visuel de la version D)", f"""La semaine sur les marchés de l'énergie, en 3 chiffres 👇

1️⃣ {N(sp['avg'], 0)} €/MWh
Le prix moyen de l'électricité en France cette semaine, {P(spot_chg)} sur une semaine.

2️⃣ {N(br['last'], 0)} $
Le baril de Brent en fin de semaine, {P(br['change'])}.

3️⃣ {N(st_eu['full'], 0)} %
Le remplissage des stocks de gaz européens, {N(abs(st_eu['ly']), 0)} points sous l'an dernier à la même date.

Le détail, graphiques à l'appui : {URL}

{TAGS}"""))
moves = sorted([("Électricité France (spot moyen)", spot_chg), ("Henry Hub", hh["change"]), ("Brent", br["change"])], key=lambda m: -m[1])
ups = [m for m in moves if m[1] > 0]; downs = [m for m in moves if m[1] < 0]
li.append(("3. En hausse / en baisse", "Classement base 100 (version B)", "Qui a monté, qui a baissé cette semaine sur les marchés de l'énergie ?\n\n"
           + "📈 EN HAUSSE\n" + "\n".join(f"• {n} : {P(c)}" for n, c in ups)
           + "\n\n📉 EN BAISSE\n" + "\n".join(f"• {n} : {P(c)}" for n, c in downs)
           + f"\n\n🧭 À SURVEILLER\n• Stocks de gaz UE : {N(st_eu['full'], 1)} %, {N(abs(st_eu['ly']), 1)} points sous l'an dernier à l'approche de l'hiver.\n"
           + f"• Gazole : {N(fu['gazole']['last'], 3)} €/L à la pompe.\n\n👉 Toute la note : {URL}\n\n{TAGS}"))
li.append(("4. Question d'accroche + pédagogie", "Profil horaire de la semaine (version E)", f"""Pourquoi l'électricité coûte-t-elle plus cher à certaines heures ? ⚡

Cette semaine en France, l'heure la plus chère en moyenne était {hourly_profile['max_h']} h ({N(hourly_profile['max'], 0)} €/MWh), la moins chère {hourly_profile['min_h']} h ({N(hourly_profile['min'], 0)} €/MWh).

💡 Le prix spot se fixe heure par heure, la veille pour le lendemain : quand la demande monte en soirée et que le solaire s'arrête, des centrales plus chères doivent démarrer, et ce sont elles qui fixent le prix.

📊 Sur la semaine :
• Spot moyen : {N(sp['avg'])} €/MWh ({P(spot_chg)})
• Nucléaire {N(mix['nuclear'], 0)} %, renouvelables {N(mix['renewables'], 0)} %, gaz {N(mix['gas'], 0)} %

Et vous, vous suivez ces prix au quotidien ? 💬

La note complète : {URL}

{TAGS}"""))
li.append(("5. Court et direct", "Graphique détaillé de l'électricité sur 30 jours (version A)", f"""⚡ {headline}.

Électricité France : {N(sp['avg'], 0)} €/MWh en moyenne ({P(spot_chg)})
Henry Hub : {N(hh['last'])} €/MWh ({P(hh['change'])})
Brent : {N(br['last'])} $ ({P(br['change'])})
Stocks de gaz UE : {N(st_eu['full'], 1)} %

Ma note de marché de la semaine, en 2 minutes 👉 {URL}

{TAGS}"""))

DATA = {"charts": charts}
esc = lambda x: x.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731


def dc(cid, title, sub, stat_rows, src, tall=False):
    st = "".join(f'<div class="dc-stat"><span>{r[0]}</span><strong class="{r[4] if len(r) > 4 else ""}">{r[1]}<small> {r[2]}</small></strong><em>{r[3]}</em></div>' for r in stat_rows)
    return (f'<div class="dc"><div class="dc-head"><h3>{title}</h3><span class="dc-pills"><b>7j</b><b class="on">30j</b><b>60j</b></span></div>'
            f'<p class="dc-sub">{sub}</p><div class="dc-chart{" dc-chart--tall" if tall else ""}"><canvas data-c="{cid}"></canvas></div>'
            f'<div class="dc-stats">{st}</div><p class="dc-src">Source : {src}</p></div>')


def ul(items):
    return "<ul class='bl'>" + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>"


def press_block():
    return ("<section class='press'><h3>Explorer la presse de la semaine</h3><ul>"
            + "".join(f"<li><a href='{n['url']}' target='_blank' rel='noopener'>{esc(n['title'])}</a> <span>{esc(n['source'])}</span></li>" for n in press)
            + "</ul></section>")


def head(eyebrow):
    return (f"<header class='nh'><p class='eb'>{eyebrow} · Semaine 40</p><h2>{headline}</h2><p class='per'>Semaine {period}</p></header>")


reading_box = f"<aside class='rd'><p class='lbl'>→ Lecture clé</p><p>{esc(reading)}</p></aside>"

spot_stats = stats(spot_week, "€/MWh")
spot_stats.insert(1, ("Moyenne vs sem. préc.", P(spot_chg), "", f"{N(sp['avg'])} contre {N(sp['prev_avg'])} €/MWh", "up" if spot_chg > 0 else "down"))
spot_stats[-1] = ("Moyenne", N(sp["avg"]), "€/MWh", "semaine 40")
# A. Tableau de bord : graphiques détaillés
A = (head("Note de marché") + reading_box
     + "<h3 class='sh'>⚡ Électricité</h3>" + ul(bul_power[:2]) + dc("spot30", "Électricité FR", "Prix spot, 30 jours (semaine en surbrillance)", spot_stats, "RTE, Energy-Charts / SMARD")
     + "<h3 class='sh'>🔥 Gaz</h3>" + ul(bul_gas[:2]) + dc("hh30", "Henry Hub", "Prix de référence américain, 30 jours", stats(hh_week, "€/MWh", hh["ref"]), "OilPriceAPI, EIA, taux BCE")
     + "<h3 class='sh'>🛢️ Pétrole</h3>" + ul(bul_oil[:2]) + dc("brent30", "Brent", "Baril de mer du Nord, 30 jours", stats(brent_week, "$/b", br["ref"]), "OilPriceAPI, EIA")
     + press_block())

# B. Base 100
rk = "".join(f"<div class='rk'><span class='rk-n' style='border-color:{c}'>{i + 1}</span><div><b>{n}</b><strong class='{'up' if v > 0 else 'down'}'>{P(v)}</strong><em>moyenne mobile 7 j, sur 30 jours</em></div></div>" for i, (n, v, c) in enumerate(ranking))
B = (head("Note de marché") + reading_box
     + "<div class='dc'><div class='dc-head'><h3>Comparaison base 100</h3><span class='dc-pills'><b class='on'>30j</b></span></div><p class='dc-sub'>Évolution relative des trois marchés sur 30 jours (moyennes mobiles 7 j, base 100 au départ)</p><div class='dc-chart dc-chart--tall'><canvas data-c='base100'></canvas></div><div class='rks'>" + rk + "</div><p class='dc-src'>Sources : RTE, OilPriceAPI, EIA</p></div>"
     + "<div class='cols3'><div><h3 class='sh'>⚡ Électricité</h3>" + ul(bul_power[:2]) + "</div><div><h3 class='sh'>🔥 Gaz</h3>" + ul(bul_gas[:2]) + "</div><div><h3 class='sh'>🛢️ Pétrole</h3>" + ul(bul_oil[:2]) + "</div></div>"
     + press_block())

# C. Éditorial
C_ = (head("La lettre des marchés")
      + f"<p class='lede'>{esc(reading)}</p>"
      + f"<h3 class='sh'>Électricité : une semaine plus chère</h3><p>{esc(para_power)}</p>"
      + "<figure class='lc'><div class='lc-chart'><canvas data-c='spotweek'></canvas></div><figcaption>Prix spot jour par jour, face à la moyenne de la semaine précédente · RTE</figcaption></figure>"
      + f"<h3 class='sh'>Gaz : l'Europe remplit, mais en retard</h3><p>{esc(para_gas)}</p>"
      + "<figure class='lc'><div class='lc-chart'><canvas data-c='storage'></canvas></div><figcaption>Remplissage des stocks de gaz de l'UE, 2026 face à 2025 · GIE AGSI+</figcaption></figure>"
      + f"<blockquote class='pq'>{N(abs(st_eu['ly']), 1)} points de stockage de moins que l'an dernier à la même date.</blockquote>"
      + f"<h3 class='sh'>Pétrole : le Brent recule</h3><p>{esc(para_oil)}</p>"
      + "<figure class='lc'><div class='lc-chart'><canvas data-c='diesel'></canvas></div><figcaption>Prix moyen du gazole en France, 60 jours · data.economie.gouv.fr</figcaption></figure>"
      + press_block())

# D. 3 chiffres
big = [("spk_spot", "Électricité France", N(sp["avg"], 0), "€/MWh", P(spot_chg), spot_chg, "moyenne de la semaine"),
       ("spk_brent", "Brent", N(br["last"]), "$/b", P(br["change"]), br["change"], "fin de semaine"),
       ("spk_storage", "Stocks de gaz UE", N(st_eu["full"], 1), "%", f"{SG(st_eu['ly'])} pts", st_eu["ly"], "vs l'an dernier, même date")]
cards = "".join(f"<div class='bn'><p class='bn-l'>{l}</p><p class='bn-v'>{v}<small> {u}</small></p><p class='bn-c {'up' if x > 0 else 'down'}'>{c} <em>{e}</em></p><div class='bn-s'><canvas data-c='{cid}'></canvas></div></div>" for cid, l, v, u, c, x, e in big)
tomorrow = sorted(da.get("fr", {}))[-1] if da.get("fr") else None
watch = []
if tomorrow:
    t = da["fr"][tomorrow]
    watch.append(f"Prix day-ahead du {g.day_label(tomorrow, 'fr')} : {N(t['avg'])} €/MWh en moyenne, pointe à {t['max']['hour']} h ({N(t['max']['value'])} €/MWh).")
watch.append(f"Stocks de gaz : au rythme de la semaine ({SG(st_eu['week'])} point), l'UE reste nettement sous l'an dernier.")
if us:
    watch.append(f"Stocks de brut américains : {N(us['mb'], 1)} millions de barils, publication EIA chaque mercredi.")
D = (head("Note de marché") + "<div class='bns'>" + cards + "</div>"
     + "<div class='cols2'><div class='box'><h3 class='sh'>📌 À retenir</h3>" + ul([bul_power[0], bul_gas[0], bul_oil[0]]) + "</div>"
     + "<div class='box'><h3 class='sh'>👀 À surveiller</h3>" + ul(watch) + "</div></div>" + press_block())

# E. Électricité à la loupe + tableau jour par jour
rows = ""
bd = dict(brent_week); hd = dict(hh_week)
for d, v in spot_week:
    dd = da.get("fr", {}).get(d)
    rows += (f"<tr><td>{dlabel(d)}</td><td class='hm' style='--a:{max(0.08, min(1, (v - sp['low'][1]) / max(1, sp['high'][1] - sp['low'][1])))}'>{N(v)}</td>"
             f"<td>{(dd['min']['hour'] + ' h · ' + N(dd['min']['value'])) if dd else '-'}</td><td>{(dd['max']['hour'] + ' h · ' + N(dd['max']['value'])) if dd else '-'}</td>"
             f"<td>{N(bd[d]) if d in bd else '-'}</td><td>{N(hd[d]) if d in hd else '-'}</td></tr>")
E = (head("Note de marché") + reading_box
     + "<h3 class='sh'>La semaine jour par jour</h3><div class='tw'><table class='wt'><thead><tr><th>Jour</th><th>Spot France €/MWh</th><th>Heure la moins chère</th><th>Heure la plus chère</th><th>Brent $</th><th>Henry Hub €/MWh</th></tr></thead><tbody>"
     + rows + "</tbody></table></div><p class='dc-src'>Sources : RTE, ENTSO-E, OilPriceAPI</p>"
     + "<div class='dc'><div class='dc-head'><h3>Électricité heure par heure</h3></div><p class='dc-sub'>Prix day-ahead France, chaque jour de la semaine</p><div class='dc-chart dc-chart--tall'><canvas data-c='hourly'></canvas></div><p class='dc-src'>Source : ENTSO-E</p></div>"
     + "<div class='dc'><div class='dc-head'><h3>La France face à ses voisins</h3></div><p class='dc-sub'>Prix day-ahead moyen de la semaine</p><div class='dc-chart'><canvas data-c='neighbors'></canvas></div><p class='dc-src'>Source : ENTSO-E</p></div>"
     + "<h3 class='sh'>Gaz et pétrole</h3>" + ul([bul_gas[0], bul_gas[1], bul_oil[0]]) + press_block())

variants = [("A", "Tableau de bord", "Les graphiques détaillés de la page Marchés (fond marine, 5 chiffres), un par marché, avec deux puces de texte au-dessus.", A),
            ("B", "Base 100", "Un grand graphique qui compare les trois marchés sur 30 jours, un classement, puis trois colonnes de texte.", B),
            ("C", "Éditorial", "Une vraie lettre : paragraphes rédigés, graphiques clairs entre les paragraphes, une citation chiffrée.", C_),
            ("D", "Les 3 chiffres", "Trois grands chiffres avec leur mini-courbe, puis « À retenir » et « À surveiller » (prix de demain, stocks).", D),
            ("E", "Électricité à la loupe", "Un tableau jour par jour coloré, le profil heure par heure de la semaine et la France face à ses voisins.", E)]

tabs = "".join(f"<button type='button' data-tab='{k}'{' class=on' if i == 0 else ''}><b>{k}</b> {n}</button>" for i, (k, n, _, _) in enumerate(variants))
panes = "".join(f"<section class='pane' id='v{k}'{'' if i == 0 else ' hidden'}><p class='vdesc'><b>Version {k} · {n}</b> : {d}</p><article class='note'>{h}</article></section>" for i, (k, n, d, h) in enumerate(variants))
lis = "".join(f"<div class='li'><div class='li-top'><b>{esc(t)}</b><span>Visuel suggéré : {esc(v)}</span><button type='button' data-copy='{i}'>Copier</button></div>"
              f"<div class='li-card'><div class='li-who'><img src='/assets/img/tom.webp' alt=''><div><b>Tom Moulard</b><small>Inside Energy Markets</small></div></div><pre id='li{i}'>{esc(txt)}</pre></div></div>"
              for i, (t, v, txt) in enumerate(li))

html = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Note de marché : 5 formats</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@500;700&family=Source+Serif+4:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
:root {{ --navy:#17255f; --deep:#0d1638; --teal:#00817d; --teal2:#4fd1c5; --line:#d8e1e6; --ink:#1a2433; --mut:#5a6b7b; }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:#f4f7f9; color:var(--ink); font:16px/1.6 Inter, sans-serif; }}
.top {{ background:var(--navy); color:#fff; padding:22px 16px 0; position:sticky; top:0; z-index:5; }}
.top h1 {{ font:400 34px 'Bebas Neue'; margin:0 0 4px; letter-spacing:.5px; }} .top p {{ margin:0 0 14px; color:rgba(255,255,255,.7); font-size:14px; }}
.wrap {{ max-width:980px; margin:0 auto; }}
.tabs {{ display:flex; gap:6px; flex-wrap:wrap; }} .tabs button {{ border:0; border-radius:10px 10px 0 0; padding:9px 14px; background:rgba(255,255,255,.08); color:#fff; font:600 13px Inter; cursor:pointer; }}
.tabs button b {{ color:#e8703a; margin-right:4px; }} .tabs button.on {{ background:#f4f7f9; color:var(--navy); }}
main {{ padding:22px 16px 60px; }} .vdesc {{ background:#fff7e6; border:1px solid #f3d9a4; border-radius:10px; padding:10px 14px; font-size:14px; }}
.note {{ background:#fff; border:1px solid var(--line); border-radius:18px; padding:30px clamp(16px,4vw,40px); margin-top:14px; }}
.nh .eb {{ font:700 12px Inter; letter-spacing:.6px; text-transform:uppercase; color:var(--teal); margin:0; }}
.nh h2 {{ font:400 clamp(30px,5vw,44px)/1 'Bebas Neue'; color:var(--navy); margin:6px 0 4px; }} .nh .per {{ color:var(--mut); margin:0 0 18px; font-size:14px; }}
.rd {{ background:var(--navy); color:#fff; border-radius:14px; padding:16px 20px; margin:0 0 22px; }} .rd .lbl {{ font:700 12px Inter; text-transform:uppercase; letter-spacing:.5px; color:var(--teal2); margin:0 0 6px; }} .rd p:last-child {{ margin:0; }}
.sh {{ font:700 19px Inter; color:var(--navy); margin:26px 0 8px; }}
.bl {{ margin:0 0 14px; padding-left:18px; }} .bl li {{ margin:4px 0; }}
.dc {{ background:linear-gradient(160deg,#1b2a6b,#0d1638); color:#fff; border-radius:18px; padding:20px 22px; margin:12px 0 8px; }}
.dc-head {{ display:flex; justify-content:space-between; align-items:center; gap:10px; }} .dc h3 {{ font:400 28px 'Bebas Neue'; margin:0; letter-spacing:.4px; }}
.dc-pills b {{ display:inline-block; padding:4px 10px; border-radius:8px; border:1px solid rgba(255,255,255,.2); font:700 12px Inter; margin-left:4px; }} .dc-pills b.on {{ background:#e8703a; border-color:#e8703a; }}
.dc-sub {{ margin:2px 0 10px; color:rgba(255,255,255,.6); font-size:13px; }}
.dc-chart {{ position:relative; height:240px; }} .dc-chart--tall {{ height:300px; }}
.dc-stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:10px; margin-top:14px; }}
.dc-stat {{ background:rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.1); border-radius:12px; padding:12px 14px; }}
.dc-stat span {{ display:block; font-size:12px; color:rgba(255,255,255,.6); }} .dc-stat strong {{ display:block; font:700 20px 'JetBrains Mono'; margin:4px 0 2px; }} .dc-stat small {{ font:600 11px Inter; color:rgba(255,255,255,.55); }}
.dc-stat em {{ font-style:normal; font-size:12px; color:rgba(255,255,255,.55); }}
.up {{ color:#3ddc97 !important; }} .down {{ color:#ff6b5b !important; }}
.note .bn-c.up {{ color:#1f8a55 !important; }} .note .bn-c.down {{ color:#c53030 !important; }}
.dc-src {{ font-size:12px; color:rgba(255,255,255,.5); margin:10px 0 0; }} .note > .dc-src {{ color:var(--mut); }}
.rks {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:10px; margin-top:12px; }}
.rk {{ display:flex; gap:12px; align-items:center; background:rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.1); border-radius:12px; padding:12px; }}
.rk-n {{ width:30px; height:30px; border-radius:50%; border:2px solid; display:grid; place-items:center; font-weight:700; flex:none; }}
.rk b {{ display:block; font-size:13px; }} .rk strong {{ font:700 20px 'JetBrains Mono'; }} .rk em {{ display:block; font-style:normal; font-size:11px; color:rgba(255,255,255,.5); }}
.cols3 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:18px; }} .cols2 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; margin-top:18px; }}
.box {{ border:1px solid var(--line); border-radius:14px; padding:4px 18px 8px; }} .box .sh {{ margin-top:14px; }}
.lede {{ font:400 20px/1.55 'Source Serif 4', serif; color:var(--navy); border-left:4px solid var(--teal); padding-left:16px; }}
.note p {{ }} article.note > p {{ font-family:'Source Serif 4', serif; font-size:17.5px; }}
.lc {{ margin:14px 0 20px; border:1px solid var(--line); border-radius:14px; padding:14px; }} .lc-chart {{ position:relative; height:230px; }} .lc figcaption {{ font-size:12px; color:var(--mut); margin-top:8px; }}
.pq {{ margin:22px 0; padding:18px 22px; border-radius:14px; background:#eef8f7; font:600 22px/1.35 'Source Serif 4', serif; color:var(--teal); }}
.bns {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:14px; }}
.bn {{ background:linear-gradient(160deg,#1b2a6b,#0d1638); color:#fff; border-radius:18px; padding:18px 18px 10px; }}
.bn-l {{ margin:0; font:700 12px Inter; text-transform:uppercase; letter-spacing:.5px; color:rgba(255,255,255,.65); }}
.bn-v {{ margin:6px 0 0; font:700 40px/1 'JetBrains Mono'; }} .bn-v small {{ font:600 14px Inter; color:rgba(255,255,255,.6); }}
.bn .bn-c {{ margin:6px 0 8px; font:700 15px 'JetBrains Mono'; }} .bn .bn-c.up {{ color:#3ddc97 !important; }} .bn .bn-c.down {{ color:#ff6b5b !important; }} .bn-c em {{ font:400 12px Inter; font-style:normal; color:rgba(255,255,255,.55); }}
.bn-s {{ position:relative; height:70px; }}
.tw {{ overflow-x:auto; }} .wt {{ width:100%; border-collapse:collapse; font-size:14px; min-width:620px; }} .wt th {{ text-align:left; font:700 11px Inter; text-transform:uppercase; letter-spacing:.4px; color:var(--mut); padding:8px; border-bottom:2px solid var(--line); }}
.wt td {{ padding:9px 8px; border-bottom:1px solid var(--line); font-family:'JetBrains Mono'; font-size:13.5px; }} .wt td:first-child {{ font-family:Inter; font-weight:600; }}
.wt td.hm {{ background:rgba(0,129,125,var(--a)); color:#0d1638; font-weight:700; }}
.press {{ margin-top:30px; border-top:1px solid var(--line); padding-top:6px; }} .press h3 {{ font:700 17px Inter; color:var(--navy); }} .press ul {{ padding-left:18px; }} .press li {{ margin:6px 0; }} .press a {{ color:var(--navy); }} .press span {{ font-size:12px; color:var(--mut); }}
h2.lih {{ font:400 40px 'Bebas Neue'; color:var(--navy); margin:50px 0 6px; }} .lip {{ color:var(--mut); margin:0 0 16px; }}
.lis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:16px; }}
.li-top {{ display:flex; flex-wrap:wrap; align-items:center; gap:4px 10px; margin-bottom:8px; }} .li-top b {{ font-size:15px; color:var(--navy); flex:1 1 100%; }} .li-top span {{ font-size:12px; color:var(--mut); flex:1; }}
.li-top button {{ border:1px solid var(--teal); background:#fff; color:var(--teal); border-radius:999px; padding:3px 12px; font:600 12px Inter; cursor:pointer; }}
.li-card {{ background:#fff; border:1px solid var(--line); border-radius:12px; padding:14px; }} .li-who {{ display:flex; gap:10px; align-items:center; margin-bottom:10px; }} .li-who img {{ width:40px; height:40px; border-radius:50%; object-fit:cover; }} .li-who small {{ display:block; color:var(--mut); font-size:12px; }}
.li-card pre {{ white-space:pre-wrap; font:14px/1.5 Inter; margin:0; max-height:420px; overflow:auto; }}
</style></head><body>
<div class="top"><div class="wrap"><h1>Note de marché : 5 formats</h1><p>Données réelles de la semaine 40 (semaine en cours, arrêtée au vendredi). Sans Ormuz ni détroits. Les textes LinkedIn sont en bas.</p><nav class="tabs">{tabs}</nav></div></div>
<main><div class="wrap">{panes}
<h2 class="lih">LinkedIn : 5 textes</h2><p class="lip">Même direction artistique (emojis de rubrique, puces), cinq façons d'accrocher. Chaque texte peut être accompagné d'une image tirée de la note.</p>
<div class="lis">{lis}</div></div></main>
<script>
var D = {json.dumps(DATA, ensure_ascii=False)};
var MOIS = ['janv.','févr.','mars','avr.','mai','juin','juil.','août','sept.','oct.','nov.','déc.'];
function fd(s) {{ var p = s.split('-'); return +p[2] + ' ' + MOIS[+p[1]-1]; }}
function fmt(v, d) {{ return v == null ? '' : v.toLocaleString('fr-FR', {{ minimumFractionDigits: d, maximumFractionDigits: d }}); }}
var made = {{}};
function draw(cv) {{
  var id = cv.getAttribute('data-c'), c = D.charts[id]; if (!c || made[id + cv.closest('.pane').id]) return;
  made[id + cv.closest('.pane').id] = true;
  var dark = !!cv.closest('.dc, .bn'), tick = dark ? 'rgba(255,255,255,.55)' : '#5a6b7b', grid = dark ? 'rgba(255,255,255,.07)' : 'rgba(23,37,95,.07)';
  var digits = c.digits || (c.unit === '%' ? 1 : 2);
  var isDate = c.labels.length && /^\\d{{4}}-/.test(c.labels[0]);
  var ds = c.series.map(function (s) {{
    var ctx = cv.getContext('2d'), gr = ctx.createLinearGradient(0, 0, 0, 300); gr.addColorStop(0, s.color + '55'); gr.addColorStop(1, s.color + '00');
    return {{ label: s.name, data: s.data, borderColor: s.color, backgroundColor: c.type === 'bar' ? (s.colors || s.color) : gr,
      fill: c.type !== 'bar' && s.fill !== false && !s.dashed && !c.base, borderDash: s.dashed ? [5,4] : [], tension: 0.35, borderWidth: c.spark ? 2 : 2.5,
      pointRadius: 0, pointHoverRadius: 4, spanGaps: true, borderRadius: 6 }};
  }});
  if (c.ref != null) ds.push({{ type: 'line', label: c.ref_label, data: c.labels.map(function () {{ return c.ref; }}), borderColor: '#94a3b8', borderDash: [4,4], borderWidth: 1.5, pointRadius: 0, fill: false }});
  if (c.base) ds.push({{ type: 'line', label: 'Base 100', data: c.labels.map(function () {{ return 100; }}), borderColor: 'rgba(255,255,255,.35)', borderDash: [3,4], borderWidth: 1, pointRadius: 0, fill: false }});
  var band = c.band ? {{ id: 'band', beforeDraw: function (ch) {{
    var x = ch.scales.x, a = c.labels.indexOf(c.band[0]), b = c.labels.length - 1;
    for (var i = 0; i < c.labels.length; i++) {{ if (c.labels[i] >= c.band[0]) {{ a = i; break; }} }}
    if (a < 0) return; var ctx = ch.ctx; ctx.save(); ctx.fillStyle = 'rgba(232,112,58,.12)';
    ctx.fillRect(x.getPixelForValue(a) - 6, ch.chartArea.top, x.getPixelForValue(b) - x.getPixelForValue(a) + 12, ch.chartArea.bottom - ch.chartArea.top);
    ctx.fillStyle = 'rgba(232,112,58,.9)'; ctx.font = '600 11px Inter'; ctx.fillText('Semaine 40', x.getPixelForValue(a) - 2, ch.chartArea.top + 12); ctx.restore(); }} }} : null;
  new Chart(cv, {{ type: c.type, data: {{ labels: c.labels, datasets: ds }}, plugins: band ? [band] : [],
    options: {{ responsive: true, maintainAspectRatio: false, animation: false, indexAxis: c.horizontal ? 'y' : 'x',
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{ legend: {{ display: !c.spark && (ds.length > 1), position: 'bottom', labels: {{ color: tick, boxWidth: 12, font: {{ size: 11 }} }} }},
        tooltip: {{ enabled: !c.spark, callbacks: {{ title: function (it) {{ return it.length && isDate ? fd(it[0].label) : (it.length ? it[0].label + (c.hourly ? ' h' : '') : ''); }},
          label: function (x) {{ var v = c.horizontal ? x.parsed.x : x.parsed.y; return x.dataset.label + ' : ' + fmt(v, c.base ? 1 : digits) + ' ' + (c.base ? '' : c.unit); }} }} }} }},
      scales: c.spark ? {{ x: {{ display: false }}, y: {{ display: false }} }} : {{
        x: {{ ticks: {{ color: tick, font: {{ size: 11 }}, maxTicksLimit: c.horizontal ? 6 : 8, maxRotation: 0, callback: function (v) {{ var l = this.getLabelForValue(v); return c.horizontal ? v : (isDate ? fd(l) : l + (c.hourly ? ' h' : '')); }} }}, grid: {{ display: !!c.horizontal, color: grid }} }},
        y: {{ ticks: {{ color: tick, font: {{ size: 11 }} }}, grid: {{ color: c.horizontal ? 'transparent' : grid }}, beginAtZero: !!c.horizontal }} }} }} }});
}}
function show(k) {{
  document.querySelectorAll('.tabs button').forEach(function (b) {{ b.classList.toggle('on', b.getAttribute('data-tab') === k); }});
  document.querySelectorAll('.pane').forEach(function (p) {{ p.hidden = p.id !== 'v' + k; }});
  document.querySelectorAll('#v' + k + ' canvas[data-c]').forEach(draw);
}}
document.querySelectorAll('.tabs button').forEach(function (b) {{ b.addEventListener('click', function () {{ show(b.getAttribute('data-tab')); window.scrollTo(0, 0); }}); }});
document.querySelectorAll('[data-copy]').forEach(function (b) {{ b.addEventListener('click', function () {{
  navigator.clipboard.writeText(document.getElementById('li' + b.getAttribute('data-copy')).textContent); b.textContent = 'Copié'; setTimeout(function () {{ b.textContent = 'Copier'; }}, 1500); }}); }});
show('A');
</script></body></html>"""
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w", encoding="utf-8").write(html)
print("ok", OUT, len(html))
for t, v, txt in li:
    assert "—" not in txt
assert "—" not in html
