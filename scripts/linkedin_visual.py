"""
Visuels LinkedIn de la note de marché (format portrait 4:5, 1080 x 1350), générés chaque lundi après la note :
- _linkedin/AAAA-SS-1.png : titre de la semaine, 4 chiffres clés, prix de l'électricité sur 30 jours ;
- _linkedin/AAAA-SS-2.png : « Qui a le plus bougé en 30 jours ? » (base 100), seulement si les trois séries
  couvrent assez de jours.
Le premier visuel est aussi publié sur le site (assets/img/notes/AAAA-SS.png) et déclaré comme `image` de la note
française : carte de la note sur l'accueil et aperçu du lien quand la note est partagée.
Les données viennent de la note française (_notes/AAAA-SS-fr.md). La page est dessinée en HTML (même charte que
le site) puis photographiée par Chrome sans interface (installé sur les machines de GitHub Actions).

Usage : python scripts/linkedin_visual.py [--week 2026-W40]
"""
import argparse
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
NOTES_DIR = os.path.join(ROOT, "_notes")
LINKEDIN_DIR = os.path.join(ROOT, "_linkedin")
CHROMES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
           r"C:\Program Files\Google\Chrome\Application\chrome.exe",
           r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
COLORS = {"power": "#4fd1c5", "gas": "#e8b33a", "storage": "#94a3b8", "oil": "#e8703a"}


def read_note(year, wk):
    path = os.path.join(NOTES_DIR, f"{year}-{wk:02d}-fr.md")
    text = open(path, encoding="utf-8").read()
    front = text.split("---")[1]
    return {m.group(1): json.loads(m.group(2)) for m in re.finditer(r"^(\w+): (.*)$", front, re.M)}


def last_days(chart, days=30):
    """Points (date, valeur) de la première série sur les `days` derniers jours de la note."""
    pts = [(d, v) for d, v in zip(chart["labels"], chart["series"][0]["data"]) if v is not None]
    if not pts:
        return []
    cut = (datetime.date.fromisoformat(pts[-1][0]) - datetime.timedelta(days=days)).isoformat()
    return [p for p in pts if p[0] > cut]


def base100(points):
    """Moyenne mobile 7 points, ramenée à 100 au premier jour (même méthode que la page Marchés)."""
    out, ref = {}, None
    for i, (d, _) in enumerate(points):
        w = [v for _, v in points[max(0, i - 6): i + 1]]
        m = sum(w) / len(w)
        ref = ref or m
        out[d] = round(m / ref * 100, 1)
    return out


def fr_pct(v):
    s = f"{abs(v):.1f}".replace(".", ",")
    return ("+" if v > 0 else "−" if v < 0 else "") + s + " %"


CSS = """
body { margin:0; width:1080px; height:1350px; overflow:hidden; font-family:Inter, sans-serif; color:#fff; }
.card { width:1080px; height:1350px; box-sizing:border-box; padding:64px 64px 48px; display:flex; flex-direction:column;
  background:radial-gradient(1200px 700px at 90% -10%, rgba(0,129,125,.35), transparent 60%), linear-gradient(160deg,#1b2a6b,#0d1638); }
.brand { display:flex; justify-content:space-between; align-items:center; }
.logo { font:400 40px 'Bebas Neue'; letter-spacing:1px; } .logo em { font:italic 400 26px 'Source Serif 4', serif; color:rgba(255,255,255,.7); margin-right:8px; }
.pill { padding:10px 20px; border:2px solid rgba(255,255,255,.25); border-radius:999px; font:700 20px Inter; color:#4fd1c5; letter-spacing:.5px; text-transform:uppercase; }
h1 { font:400 92px/0.98 'Bebas Neue'; margin:54px 0 10px; letter-spacing:.5px; }
.per { margin:0 0 36px; font-size:26px; color:rgba(255,255,255,.65); }
.ks { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
.k { background:rgba(255,255,255,.06); border:2px solid rgba(255,255,255,.1); border-radius:22px; padding:22px 26px; }
.kl { margin:0; font:600 22px Inter; color:rgba(255,255,255,.7); } .kl i { display:inline-block; width:14px; height:14px; border-radius:50%; margin-right:10px; }
.kv { margin:8px 0 4px; font:700 50px/1 'JetBrains Mono'; } .kv small { font:600 22px Inter; color:rgba(255,255,255,.6); margin-left:6px; }
.kc { margin:0; font:700 24px 'JetBrains Mono'; } .kc em { font:400 19px Inter; font-style:normal; color:rgba(255,255,255,.55); margin-left:6px; }
.up { color:#3ddc97; } .down { color:#ff6b5b; } .flat { color:rgba(255,255,255,.6); }
.ch { margin-top:30px; flex:1; display:flex; flex-direction:column; background:rgba(255,255,255,.04); border-radius:22px; padding:20px 22px 12px; }
.cht { margin:0 0 8px; font:600 21px Inter; color:rgba(255,255,255,.7); } .cv { position:relative; flex:1; min-height:0; }
.rs { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin-top:22px; }
.r { background:rgba(255,255,255,.06); border:2px solid rgba(255,255,255,.1); border-radius:20px; padding:18px 20px; }
.r span { display:inline-grid; place-items:center; width:40px; height:40px; border-radius:50%; border:3px solid #e8703a; font:700 20px Inter; }
.r b { display:block; margin:12px 0 4px; font:600 22px Inter; } .r strong { font:700 40px 'JetBrains Mono'; }
.h1s { font-size:80px; margin-top:44px; }
.mcs2 { display:grid; grid-template-columns:1fr 1fr; gap:18px; flex:1; min-height:0; }
.mc { display:flex; flex-direction:column; min-height:0; background:rgba(255,255,255,.05); border:2px solid rgba(255,255,255,.1); border-radius:22px; padding:22px 24px 16px; }
.mcl { margin:0; font:700 18px Inter; letter-spacing:.8px; text-transform:uppercase; color:rgba(255,255,255,.7); } .mcl i { display:inline-block; width:13px; height:13px; border-radius:50%; margin-right:9px; }
.mcv { margin:10px 0 6px; font:700 58px/1 'JetBrains Mono'; } .mcv small { font:600 22px Inter; color:rgba(255,255,255,.6); margin-left:8px; }
.mcp { margin:0 0 14px; font:700 24px 'JetBrains Mono'; } .mcp em { font:400 18px Inter; font-style:normal; color:rgba(255,255,255,.55); margin-left:8px; }
.mcs { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
.mcs span { display:flex; flex-direction:column; padding:10px 12px; border-radius:12px; background:rgba(255,255,255,.05); font:600 15px Inter; color:rgba(255,255,255,.6); }
.mcs b { font:700 22px 'JetBrains Mono'; color:#fff; margin-top:2px; } .mcs em { font-style:normal; font-size:14px; color:rgba(255,255,255,.5); }
.mct { margin:14px 0 4px; font:600 16px Inter; color:rgba(255,255,255,.6); } .mct .lgw { display:inline-block; width:22px; height:3px; background:#fff; vertical-align:middle; margin:0 8px 0 4px; } .mcc { position:relative; flex:1; min-height:0; }
.sts { display:grid; grid-template-columns:1fr 1fr; gap:18px; margin-top:18px; }
.st { padding:16px 22px; border-radius:18px; background:rgba(255,255,255,.05); border:2px solid rgba(255,255,255,.1); }
.stv { margin:6px 0 2px; font:700 36px/1 'JetBrains Mono'; } .stv small { font:600 18px Inter; color:rgba(255,255,255,.6); margin-left:6px; }
.stv span { font:700 20px 'JetBrains Mono'; margin-left:14px; } .st em { font-style:normal; font-size:16px; color:rgba(255,255,255,.55); }
.foot { display:flex; justify-content:space-between; gap:20px; margin-top:26px; font:600 20px Inter; color:rgba(255,255,255,.55); } .foot span:first-child { color:#4fd1c5; }
"""

JS = """
var M = ['janv.','févr.','mars','avr.','mai','juin','juil.','août','sept.','oct.','nov.','déc.'];
function fd(s) { var p = s.split('-'); return +p[2] + ' ' + M[+p[1]-1]; }
var ax = { x: { ticks: { color:'rgba(255,255,255,.6)', font:{ size:18 }, maxTicksLimit:5, maxRotation:0, callback:function(v){ return fd(this.getLabelForValue(v)); } }, grid:{ display:false } },
           y: { ticks: { color:'rgba(255,255,255,.6)', font:{ size:18 }, maxTicksLimit:5 }, grid:{ color:'rgba(255,255,255,.08)' } } };
var base = { responsive:true, maintainAspectRatio:false, animation:false, plugins:{ legend:{ display:false }, tooltip:{ enabled:false } }, scales:ax };
if (D.line) {
  var cv = document.getElementById('c'), g = cv.getContext('2d').createLinearGradient(0,0,0,420);
  g.addColorStop(0, D.line.color + '66'); g.addColorStop(1, D.line.color + '00');
  var band = { id:'b', beforeDraw:function(ch){ var x=ch.scales.x, a=D.line.labels.findIndex(function(l){ return l>=D.line.band; }); if (a<0) return;
    var x0=Math.max(x.getPixelForValue(a)-8, ch.chartArea.left), x1=ch.chartArea.right, c=ch.ctx; c.save(); c.fillStyle='rgba(232,112,58,.16)';
    c.fillRect(x0,ch.chartArea.top,x1-x0,ch.chartArea.bottom-ch.chartArea.top); c.fillStyle='#e8703a'; c.font='700 18px Inter';
    var w=c.measureText(D.line.band_label).width; c.fillText(D.line.band_label, Math.min(x0+8, x1-w-8), ch.chartArea.top+22); c.restore(); } };
  new Chart(cv, { type:'line', plugins:[band], data:{ labels:D.line.labels, datasets:[{ data:D.line.data, borderColor:D.line.color, backgroundColor:g, fill:true, tension:.35, borderWidth:4, pointRadius:0 }] }, options:base });
}
if (D.bars) {
  var vals = { id:'v', afterDatasetsDraw:function(ch){ var c=ch.ctx; c.save(); c.font='700 22px JetBrains Mono'; c.textAlign='center';
    ch.getDatasetMeta(0).data.forEach(function(b, i){ c.fillStyle = i === D.bars.hi ? '#e8703a' : 'rgba(255,255,255,.8)';
      c.fillText(String(Math.round(D.bars.data[i])), b.x, b.y - 12); }); c.restore(); } };
  var ob = JSON.parse(JSON.stringify(base)); ob.layout = { padding:{ top:34 } };
  ob.scales = { x:{ ticks:{ color:'rgba(255,255,255,.7)', font:{ size:20, weight:'600' } }, grid:{ display:false } }, y:{ display:false, beginAtZero:true } };
  new Chart(document.getElementById('c'), { type:'bar', plugins:[vals], data:{ labels:D.bars.labels, datasets:[{ data:D.bars.data, borderRadius:10,
    backgroundColor:D.bars.data.map(function(_, i){ return i === D.bars.hi ? '#e8703a' : D.bars.color + '88'; }) }] }, options:ob });
}
if (D.bars_multi) {
  D.bars_multi.forEach(function (B) {
    var cv = document.getElementById(B.id), g = cv.getContext('2d').createLinearGradient(0, 0, 0, 380);
    g.addColorStop(0, B.color + '55'); g.addColorStop(1, B.color + '00');
    var band = { id:'b', beforeDraw:function(ch){ var x=ch.scales.x, a=B.labels.findIndex(function(l){ return l>=B.band; }); if (a<0) return;
      var x0=Math.max(x.getPixelForValue(a)-6, ch.chartArea.left), x1=ch.chartArea.right, c=ch.ctx; c.save(); c.fillStyle='rgba(232,112,58,.16)';
      c.fillRect(x0,ch.chartArea.top,x1-x0,ch.chartArea.bottom-ch.chartArea.top); c.fillStyle='#e8703a'; c.font='700 15px Inter';
      var w=c.measureText(B.band_label).width; c.fillText(B.band_label, Math.max(ch.chartArea.left+4, Math.min(x0+6, x1-w-6)), ch.chartArea.top-8); c.restore(); } };
    var ds = [{ data:B.data, borderColor:B.color, backgroundColor:g, fill:true, tension:.35, borderWidth:3, pointRadius:0, spanGaps:true }];
    if (B.step) ds.push({ data:B.step, borderColor:'rgba(255,255,255,.9)', borderWidth:2.5, stepped:'middle', fill:false, pointRadius:0, spanGaps:true });
    var ol = JSON.parse(JSON.stringify(base)); ol.layout = { padding:{ top:20 } };
    ol.scales = { x:{ ticks:{ color:'rgba(255,255,255,.6)', font:{ size:14 }, maxTicksLimit:4, maxRotation:0, callback:function(v){ return fd(this.getLabelForValue(v)); } }, grid:{ display:false } },
                  y:{ ticks:{ color:'rgba(255,255,255,.6)', font:{ size:14 }, maxTicksLimit:5 }, grid:{ color:'rgba(255,255,255,.08)' } } };
    new Chart(cv, { type:'line', plugins:[band], data:{ labels:B.labels, datasets:ds }, options:ol });
  });
}
if (D.base) {
  var o = JSON.parse(JSON.stringify(base)); o.plugins.legend = { display:true, position:'top', align:'start', labels:{ color:'#fff', font:{ size:20, weight:'600' }, boxWidth:26, filter:function(i){ return i.text !== 'Base 100'; } } };
  o.scales.x.ticks.callback = ax.x.ticks.callback;
  new Chart(document.getElementById('c'), { type:'line', data:{ labels:D.base.labels, datasets:D.base.series.map(function(s){ return { label:s.name, data:s.data, borderColor:s.color, borderWidth:5, tension:.35, pointRadius:0, spanGaps:true }; })
    .concat([{ label:'Base 100', data:D.base.labels.map(function(){ return 100; }), borderColor:'rgba(255,255,255,.35)', borderDash:[6,6], borderWidth:2, pointRadius:0 }]) }, options:o });
}
document.body.setAttribute('data-ready', '1');
"""


def page(body, data):
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@500;700&family=Source+Serif+4:ital@1&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>{CSS}</style></head><body>{body}
<script>var D = {json.dumps(data, ensure_ascii=False)};
document.fonts.ready.then(function () {{ {JS} }});</script></body></html>"""


def head(wk):
    return (f"<div class='brand'><span class='logo'><em>Inside</em>ENERGY MARKETS</span>"
            f"<span class='pill'>Note de marché · Semaine {wk}</span></div>")


def build_pages(note, wk):
    e = html.escape
    title = e(note["headline"]).replace(", ", ",<br>", 1)
    start, end = (datetime.date.fromisoformat(note[k]) for k in ("period_start", "period_end"))
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    period = (f"Semaine du {start.day}{' ' + mois[start.month - 1] if start.month != end.month else ''} au "
              f"{end.day} {mois[end.month - 1]} {end.year}")
    tiles = "".join(
        f"<div class='k'><p class='kl'><i style='background:{t.get('color', COLORS.get(t.get('key'), '#4fd1c5'))}'></i>{e(t['label'])}</p>"
        f"<p class='kv'>{e(t['value'])}<small>{e(t['unit'].strip())}</small></p>"
        f"<p class='kc {t.get('dir', 'flat')}'>{e(t.get('change') or '')}<em>{e(t.get('sub', ''))}</em></p></div>"
        for t in note["tiles"][:4])
    secs = {s["key"]: s for s in note["sections"]}
    pages = []

    def weekly(chart):
        """Moyenne de chaque semaine (au moins 5 jours cotés), 8 dernières."""
        weeks = {}
        for d, v in zip(chart["labels"], chart["series"][0]["data"]):
            if v is not None:
                weeks.setdefault(datetime.date.fromisoformat(d).isocalendar()[:2], []).append(v)
        return [(k, sum(v) / len(v)) for k, v in sorted(weeks.items()) if len(v) >= 5][-8:]

    def market_card(key, name, cid):
        """Carte façon page Marchés : moyenne de la semaine, variation, plus bas / plus haut, barres hebdo."""
        ch = secs.get(key, {}).get("chart")
        if not ch:
            return "", None
        st = {x["label"]: x for x in ch["stats"]}
        chg = st.get("Moyenne vs sem. préc.", {})
        arrow = "▲" if chg.get("dir") == "up" else "▼" if chg.get("dir") == "down" else "="
        lo, hi = st.get("Plus bas journalier", {}), st.get("Plus haut journalier", {})
        html_card = (f"<div class='mc'><p class='mcl'><i style='background:{COLORS[key]}'></i>{name}</p>"
                     f"<p class='mcv'>{e(st['Moyenne']['value'])}<small>€/MWh</small></p>"
                     f"<p class='mcp {chg.get('dir', 'flat')}'>{arrow} {e(chg.get('value', ''))}<em>vs semaine précédente</em></p>"
                     f"<div class='mcs'><span>Plus bas journalier<b>{e(lo.get('value', '-'))}</b><em>{e(lo.get('sub', ''))}</em></span>"
                     f"<span>Plus haut journalier<b>{e(hi.get('value', '-'))}</b><em>{e(hi.get('sub', ''))}</em></span></div>"
                     f"<p class='mct'>30 jours · <i class='lgw'></i>moyenne de chaque semaine</p><div class='mcc'><canvas id='{cid}'></canvas></div></div>")
        # Même graphique que la note : prix de chaque jour, moyenne de chaque semaine en marches, semaine en surbrillance
        keep = [i for i, d in enumerate(ch["labels"]) if d > (end - datetime.timedelta(days=30)).isoformat()]
        step = next((sr for sr in ch["series"] if sr.get("step")), None)
        return html_card, {"id": cid, "labels": [ch["labels"][i] for i in keep], "data": [ch["series"][0]["data"][i] for i in keep],
                           "step": [step["data"][i] for i in keep] if step else None, "color": COLORS[key],
                           "band": note["period_start"], "band_label": f"Semaine {wk}"}

    c1, b1 = market_card("power", "Électricité France · spot", "c1")
    c2, b2 = market_card("gas", "Gaz France (PEG) · spot", "c2")
    if b1 and b2:
        tl = {t.get("key"): t for t in note["tiles"]}
        strip = "".join(
            f"<div class='st'><p class='kl'><i style='background:{COLORS[k]}'></i>{e(tl[k]['label'])}</p>"
            f"<p class='stv'>{e(tl[k]['value'])}<small>{e(tl[k]['unit'].strip())}</small>"
            f"<span class='{tl[k].get('dir', 'flat')}'>{e(tl[k].get('change') or '')}</span></p><em>{e(tl[k].get('sub', ''))}</em></div>"
            for k in ("storage", "oil") if k in tl)
        body = (f"<div class='card'>{head(wk)}<h1 class='h1s'>{title}</h1><p class='per'>{period}</p>"
                f"<div class='mcs2'>{c1}{c2}</div><div class='sts'>{strip}</div>"
                "<div class='foot'><span>insideenergymarkets.com</span><span>Sources : RTE, NaTran, GIE AGSI+, OilPriceAPI (ICE)</span></div></div>")
        pages.append(page(body, {"bars_multi": [b1, b2]}))

    # Base 100 : seulement si les trois marchés couvrent au moins 15 jours de cotation
    names = {"power": "Électricité FR", "gas": "Gaz France (PEG)", "oil": "Brent"}
    series = {k: last_days(secs[k]["chart"]) for k in names if secs.get(k, {}).get("chart")}
    if len(series) == 3 and all(len(v) >= 15 for v in series.values()):
        b = {k: base100(v) for k, v in series.items()}
        labels = sorted(set().union(*[set(x) for x in b.values()]))
        moves = sorted(((names[k], v[max(v)] - 100) for k, v in b.items()), key=lambda r: -r[1])
        rank = "".join(f"<div class='r'><span>{i + 1}</span><b>{n}</b><strong class='{'up' if v > 0 else 'down'}'>{fr_pct(v)}</strong></div>"
                       for i, (n, v) in enumerate(moves))
        body = (f"<div class='card'>{head(wk)}<h1>Qui a le plus bougé<br>en 30 jours ?</h1><p class='per'>Base 100, moyennes mobiles 7 jours</p>"
                f"<div class='ch'><div class='cv'><canvas id='c'></canvas></div></div><div class='rs'>{rank}</div>"
                "<div class='foot'><span>insideenergymarkets.com</span><span>Sources : RTE, NaTran, OilPriceAPI (ICE)</span></div></div>")
        pages.append(page(body, {"base": {"labels": labels, "series": [
            {"name": names[k], "color": COLORS[k], "data": [b[k].get(d) for d in labels]} for k in names]}}))
    else:
        print("Base 100 non générée : une série couvre moins de 15 jours.")
    return pages


def find_chrome():
    for c in [os.environ.get("CHROME", "")] + CHROMES:
        if c and (shutil.which(c) or os.path.exists(c)):
            return shutil.which(c) or c
    return None


def shoot(chrome, html_path, png_path):
    url = "file:///" + os.path.abspath(html_path).replace("\\", "/").lstrip("/")
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-sandbox",
                    "--force-device-scale-factor=1", "--window-size=1080,1350", "--virtual-time-budget=15000",
                    f"--screenshot={os.path.abspath(png_path)}", url], check=True, timeout=120,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def publish_on_site(png, year, wk):
    """Copie du visuel dans assets/img/notes/ et champ `image` de la note française."""
    rel = f"/assets/img/notes/{year}-{wk:02d}.png"
    os.makedirs(os.path.join(ROOT, "assets", "img", "notes"), exist_ok=True)
    shutil.copyfile(png, os.path.join(ROOT, rel.lstrip("/")))
    path = os.path.join(NOTES_DIR, f"{year}-{wk:02d}-fr.md")
    text = open(path, encoding="utf-8").read()
    # Front matter = tout ce qui précède le deuxième « --- » ; on remplace (ou ajoute) la ligne image
    head, sep, body = text.partition("\n---\n")
    lines = [l for l in head.split("\n") if not l.startswith("image: ")]
    lines.append(f'image: "{rel}"')
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + sep + body)
    print("Visuel publié :", rel)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", help="semaine ISO, ex. 2026-W40 (par défaut : la dernière semaine complète)")
    args = ap.parse_args()
    if args.week:
        y, w = args.week.upper().split("-W")
        week_start = datetime.date.fromisocalendar(int(y), int(w), 1)
    else:
        today = datetime.date.today()
        week_start = today - datetime.timedelta(days=today.weekday() + 7)
    year, wk = week_start.isocalendar()[0], week_start.isocalendar()[1]
    try:
        note = read_note(year, wk)
    except FileNotFoundError:
        print(f"Pas de note pour la semaine {wk}, pas de visuel.")
        return 0
    chrome = find_chrome()
    if not chrome:
        print("Chrome introuvable, visuels non générés.")
        return 0
    os.makedirs(LINKEDIN_DIR, exist_ok=True)
    tmp = tempfile.mkdtemp()
    for i, doc in enumerate(build_pages(note, wk), 1):
        hp = os.path.join(tmp, f"visuel-{i}.html")
        open(hp, "w", encoding="utf-8").write(doc)
        png = os.path.join(LINKEDIN_DIR, f"{year}-{wk:02d}-{i}.png")
        shoot(chrome, hp, png)
        print("Visuel écrit :", png, os.path.getsize(png), "octets")
        if i == 1:
            publish_on_site(png, year, wk)
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
