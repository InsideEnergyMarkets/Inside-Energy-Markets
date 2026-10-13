"""Commerce mondial de GNL (page /gnl-monde/ et tuile de /marches/#gaz) : _data/lng_trade.json.

Source : UN Comtrade, API publique sans clé (preview), code douanier 271111 (gaz naturel liquéfié), données annuelles.
- Importations déclarées par les pays importateurs (flowCode M), par pays d'origine.
- Pour un importateur qui ne publie rien (ou seulement « zones non spécifiées », cas de l'Allemagne), on prend
  les exportations déclarées par les pays fournisseurs vers ce pays (données « miroir »).
Itinéraires estimés : plus court chemin sur un graphe de points en mer passant par les détroits ; mer Rouge
(Suez, Bab el-Mandeb) et Panama pénalisés pour 2024 et après (attaques des Houthis, sécheresse au canal).
Vérifié une fois par mois : on passe à l'année suivante quand son total déclaré atteint 95 % de l'année affichée.
En cas d'échec, on garde le fichier existant.
"""
import datetime
import heapq
import json
import math
import os
import time

import requests

PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "lng_trade.json")
API = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"

# Pays importateurs : code ONU -> (fr, en, lon, lat du terminal de regazéification principal, région d'arrivée)
IMP = {156: ("Chine", "China", 121, 31, "as"), 392: ("Japon", "Japan", 139.7, 35.4, "as"),
       410: ("Corée du Sud", "South Korea", 127.5, 36, "as"), 699: ("Inde", "India", 72.6, 21.5, "as"),
       490: ("Taïwan", "Taiwan", 120.3, 22.6, "as"), 764: ("Thaïlande", "Thailand", 101, 12.7, "as"),
       702: ("Singapour", "Singapore", 103.8, 1.3, "as"), 50: ("Bangladesh", "Bangladesh", 91.8, 21.6, "as"),
       586: ("Pakistan", "Pakistan", 67, 24.8, "as"), 608: ("Philippines", "Philippines", 121, 14, "as"),
       704: ("Viêt Nam", "Vietnam", 106.7, 10.8, "as"), 458: ("Malaisie", "Malaysia", 101, 2.5, "as"),
       360: ("Indonésie", "Indonesia", 106.8, -6.1, "as"), 344: ("Hong Kong", "Hong Kong", 114.2, 22.3, "as"),
       104: ("Myanmar", "Myanmar", 96.2, 16.6, "as"),
       792: ("Turquie", "Türkiye", 27, 38.7, "eu"), 826: ("Royaume-Uni", "United Kingdom", -2.5, 51.8, "eu"),
       251: ("France", "France", 0.5, 47.5, "eu"), 724: ("Espagne", "Spain", -3.7, 40, "eu"),
       380: ("Italie", "Italy", 12, 43, "eu"), 528: ("Pays-Bas", "Netherlands", 5, 52.3, "eu"),
       56: ("Belgique", "Belgium", 3.2, 51.3, "eu"), 276: ("Allemagne", "Germany", 8.2, 53.5, "eu"),
       616: ("Pologne", "Poland", 14.3, 53.9, "eu"), 620: ("Portugal", "Portugal", -8.8, 38, "eu"),
       300: ("Grèce", "Greece", 23, 38, "eu"), 440: ("Lituanie", "Lithuania", 21.1, 55.7, "eu"),
       246: ("Finlande", "Finland", 24, 60.2, "eu"), 191: ("Croatie", "Croatia", 14.6, 45.2, "eu"),
       470: ("Malte", "Malta", 14.5, 35.9, "eu"), 752: ("Suède", "Sweden", 17.9, 58.9, "eu"),
       76: ("Brésil", "Brazil", -43, -23, "am"), 152: ("Chili", "Chile", -71.5, -33, "am"),
       484: ("Mexique", "Mexico", -104.3, 19.1, "am"), 32: ("Argentine", "Argentina", -58, -38, "am"),
       214: ("République dominicaine", "Dominican Republic", -69.6, 18.4, "am"), 170: ("Colombie", "Colombia", -75.5, 10.4, "am"),
       388: ("Jamaïque", "Jamaica", -76.8, 17.9, "am"),
       818: ("Égypte", "Egypt", 31.3, 30, "mo"), 414: ("Koweït", "Kuwait", 48, 29, "mo"),
       784: ("Émirats arabes unis", "United Arab Emirates", 54.4, 24.5, "mo"), 400: ("Jordanie", "Jordan", 35, 29.5, "mo"),
       48: ("Bahreïn", "Bahrain", 50.6, 26.1, "mo"), 376: ("Israël", "Israel", 34.8, 32, "mo")}
# Pays exportateurs : code -> (fr, en, lon, lat du terminal de liquéfaction, région d'origine)
EXP = {36: ("Australie", "Australia", 118, -20.5, "ap"), 634: ("Qatar", "Qatar", 51.5, 25.9, "me"),
       842: ("États-Unis", "United States", -93.3, 29.7, "na"), 643: ("Russie", "Russia", 72, 71, "ru"),
       458: ("Malaisie", "Malaysia", 113, 3.2, "ap"), 566: ("Nigeria", "Nigeria", 7, 4.4, "af"),
       360: ("Indonésie", "Indonesia", 117.5, 0.1, "ap"), 12: ("Algérie", "Algeria", -0.3, 35.8, "af"),
       512: ("Oman", "Oman", 59.8, 22.6, "me"), 598: ("Papouasie-Nouvelle-Guinée", "Papua New Guinea", 147, -9.5, "ap"),
       784: ("Émirats arabes unis", "United Arab Emirates", 52.5, 24.2, "me"), 780: ("Trinité-et-Tobago", "Trinidad and Tobago", -61.5, 10.4, "na"),
       579: ("Norvège", "Norway", 23.6, 70.6, "ru"), 96: ("Brunei", "Brunei", 114.6, 4.6, "ap"),
       604: ("Pérou", "Peru", -76.2, -13.5, "na"), 24: ("Angola", "Angola", 12.3, -6.1, "af"),
       508: ("Mozambique", "Mozambique", 40.5, -11, "af"), 818: ("Égypte", "Egypt", 31.3, 31.4, "af"),
       226: ("Guinée équatoriale", "Equatorial Guinea", 8.7, 3.75, "af"), 120: ("Cameroun", "Cameroon", 9.8, 2.9, "af"),
       124: ("Canada", "Canada", -128.7, 54, "na"), 266: ("Gabon", "Gabon", 9.4, -0.7, "af"),
       484: ("Mexique", "Mexico", -97.9, 22.3, "na"), 32: ("Argentine", "Argentina", -58, -38.5, "na"),
       178: ("Congo", "Congo", 11.8, -4.8, "af"), 686: ("Sénégal", "Senegal", -16.4, 16.3, "af"),
       478: ("Mauritanie", "Mauritania", -16.4, 16.3, "af")}
RU_ASIA = (143, 47)  # GNL russe vers l'Asie : Sakhaline (sinon Yamal)

# Graphe des routes maritimes : points en mer (lon, lat) et liaisons
NODES = {"USG": (-90, 26.5), "FLS": (-80.2, 24.2), "ATW": (-72, 30), "YUC": (-85.8, 21.8), "CAR": (-76, 14.5),
         "PANC": (-79.8, 9.8), "PANP": (-79.5, 7.2), "TRI": (-60.3, 11.8), "PE1": (-82, -4), "PER": (-77.6, -13.8),
         "CHL": (-73, -33), "CHS": (-76.8, -44), "CHS2": (-76.5, -53), "HORN": (-66.5, -57.6), "ARG": (-56.5, -40.5),
         "BRS": (-41, -24.5), "BRN": (-33.5, -6), "ATC": (-30, 8), "ATN": (-40, 38), "AZO": (-20, 42), "FIN": (-11, 45),
         "BIS": (-4, 46.6), "CHW": (-6.5, 50.4), "DOV": (1.6, 51.1), "NSE": (4, 53.8), "NSN": (6.5, 57.6),
         "SKA": (10.5, 57.9), "ORE": (12.3, 56.2), "BAL": (16, 55.2), "BLN": (20, 57), "GOF": (23.2, 59.6),
         "NOR": (4.5, 62), "NOR2": (13, 69.5), "HAM": (23.5, 71.4), "BAR": (42, 72), "KG": (57.5, 70.7),
         "KAR": (66, 72.6), "YAM": (72.6, 71.8), "GIBW": (-9.6, 36.6), "GIB": (-5.8, 35.95), "ALG": (0, 36.4),
         "MDW": (4, 38.2), "TYR": (10.5, 41.2), "MDC": (12.6, 36.6), "ION": (18.5, 37.5), "OTR": (18.9, 40.2),
         "ADR": (15.2, 43.4), "AEG": (24.5, 36.6), "MDE": (28, 33.6), "LEV": (33.5, 32.6), "EGY": (31.2, 31.9),
         "SUZN": (32.4, 31.4), "SUZS": (32.6, 29.6), "RED": (37.6, 21.5), "AQA": (34.9, 28.2), "BAB": (43.4, 12.6),
         "ADN": (48, 12.4), "SOM": (52.5, 2), "ARB": (61, 16), "OMN": (59.5, 22.8), "HMZ": (56.5, 26.4),
         "GLF": (52.5, 26.3), "KUW": (49.2, 28.7), "PAK": (66.3, 24.2), "INW": (70.5, 19), "SRI": (80.6, 5.3),
         "BAY": (88, 15), "BGD": (91.4, 20.8), "MLN": (96.5, 6.6), "MLC": (100.6, 3.2), "SGP": (104.3, 1.25),
         "SCW": (105.2, 6), "GTH": (101.5, 11), "VNM": (107.5, 9.8), "SCS": (112, 10), "BOR": (112.8, 4.6),
         "SCN": (116, 18), "HKG": (114.6, 21.6), "PHW": (119.6, 13.6), "LUZ": (121.4, 20.6), "TWS": (119.8, 23.4),
         "ECS": (124, 29.5), "KOR": (128.6, 33.6), "JSE": (135, 40), "JPS": (134, 31.8), "JPN": (140.2, 34.3),
         "HOK": (145.6, 42.5), "LPS": (142, 45.6), "SAK": (143.8, 46.2), "PHS": (131, 18), "PAW": (148, 6),
         "MIN": (127.6, 4.6), "CEL": (122, 3.6), "MAKN": (119, 1.2), "MAK": (118.3, -1.2), "MAKS": (117.6, -4.2),
         "JVS": (112, -5.2), "KRM": (107.6, -2.2), "JAV": (107, -5.4), "SUN": (104.8, -6.9), "LOM": (115.8, -9.2),
         "NWS": (115.8, -19), "IOE": (106, -16), "TIM": (124.5, -11.2), "BAN": (128, -5.5), "MOL": (126.4, 1),
         "PNGS": (147.4, -10.4), "CSE": (152.3, -10.3), "MXP": (-105.5, 17.8), "PCE": (-112, 12), "PCW": (165, 22),
         "CAW": (-131, 52), "NGA": (6.5, 3.4), "GOG": (2, 0.5), "GAB": (8.6, -1.8), "ANG": (11.6, -6.6), "SAT": (2, -20),
         "CGH": (18.2, -36), "AGU": (28, -35.6), "MZS": (39.5, -25), "MOZ": (41.6, -13.8), "IOW": (60, -12),
         "IOC": (82, -10), "WAF": (-18.5, 8.5), "SEN": (-17.8, 15.8), "CAN": (-16.5, 28.5), "CAT": (-19, 33)}
EDGES = """USG FLS; USG YUC; FLS ATW; YUC CAR; CAR PANC; PANC PANP; CAR TRI; ATW TRI; TRI BRN; TRI ATC; PANP PE1; PE1 PER;
PER CHL; CHL CHS; CHS CHS2; CHS2 HORN; HORN ARG; ARG BRS; BRS BRN; BRN ATC; ATC ATW; ATW ATN; ATN AZO; AZO FIN; FIN BIS;
FIN CHW; BIS CHW; CHW DOV; DOV NSE; NSE NSN; NSN SKA; SKA ORE; ORE BAL; BAL BLN; BLN GOF; NSN NOR; NOR NOR2; NOR2 HAM;
HAM BAR; BAR KG; KG KAR; KAR YAM; AZO GIBW; FIN GIBW; GIBW GIB; GIB ALG; ALG MDW; MDW TYR; MDW MDC; TYR MDC; MDC ION;
ION OTR; OTR ADR; ION AEG; ION MDE; AEG MDE; MDE EGY; MDE LEV; LEV EGY; EGY SUZN; SUZN SUZS; SUZS RED; RED AQA; RED BAB;
BAB ADN; ADN ARB; ADN SOM; ARB OMN; OMN HMZ; HMZ GLF; GLF KUW; ARB PAK; ARB INW; PAK INW; INW SRI; ARB SRI; SRI BAY;
BAY BGD; SRI MLN; BAY MLN; MLN MLC; MLC SGP; SGP SCW; SCW GTH; SCW VNM; SCW SCS; SGP BOR; BOR SCS; SCS SCN; VNM SCS;
SCN HKG; SCN PHW; SCN LUZ; HKG TWS; LUZ TWS; TWS ECS; LUZ ECS; LUZ PHS; ECS KOR; KOR JSE; KOR JPS; ECS JPS; JPS JPN;
JPN HOK; HOK SAK; SAK LPS; LPS JSE; PHS JPS; PHS JPN; PHS PAW; PAW JPN; PAW MIN; MIN CEL; CEL MAKN; MAKN MAK; MAK MAKS;
MAKS LOM; MAKS JVS; JVS KRM; KRM SGP; KRM SCW; JVS JAV; JAV SUN; SUN IOE; LOM IOE; LOM NWS; NWS IOE; NWS TIM; TIM BAN;
BAN MOL; MOL MIN; PNGS CSE; CSE PAW; PANP MXP; MXP PCE; PANP PCE; PE1 PCE; PCE PCW; PCW JPN; PCW PHS; PCW PAW; CAW PCW;
CAW PCE; NGA GOG; GAB GOG; ANG GAB; ANG SAT; GOG SAT; GOG WAF; WAF SEN; SEN CAN; CAN CAT; CAT GIBW; CAT AZO; WAF ATC;
SAT CGH; SAT BRS; CGH AGU; AGU MZS; MZS MOZ; MOZ SOM; MOZ IOW; IOW ARB; IOW SRI; AGU IOW; AGU IOC; IOC SRI; IOC SUN;
IOC IOE; IOW IOC"""
PENALTY = {("SUZN", "SUZS"): 40000, ("RED", "BAB"): 40000, ("PANC", "PANP"): 12000}
ATT_E = {36: "NWS", 634: "GLF", 842: "USG", 643: "YAM", 458: "BOR", 566: "NGA", 360: "MAK", 12: "ALG", 512: "OMN",
         598: "PNGS", 784: "GLF", 780: "TRI", 579: "HAM", 96: "BOR", 604: "PER", 24: "ANG", 508: "MOZ", 818: "EGY",
         226: "NGA", 120: "NGA", 124: "CAW", 266: "GAB", 484: "MXP", 32: "ARG", 178: "ANG", 686: "SEN", 478: "SEN"}
ATT_I = {156: "ECS", 392: "JPN", 410: "KOR", 699: "INW", 490: "TWS", 764: "GTH", 702: "SGP", 50: "BGD", 586: "PAK",
         414: "KUW", 792: "AEG", 826: "CHW", 251: "BIS", 724: "GIB", 380: "TYR", 528: "NSE", 56: "DOV", 276: "NSE",
         616: "BAL", 620: "GIBW", 300: "AEG", 440: "BLN", 246: "GOF", 191: "ADR", 76: "BRS", 152: "CHL", 484: "MXP",
         818: "EGY", 608: "PHW", 704: "VNM", 458: "MLC", 360: "JAV", 784: "GLF", 400: "AQA", 32: "ARG", 344: "HKG",
         104: "BAY", 470: "MDC", 752: "BLN", 214: "CAR", 170: "CAR", 388: "CAR", 48: "GLF", 376: "LEV"}
CHOKE = {"HMZ": ("Ormuz", "Hormuz"), "MLC": ("Malacca", "Malacca"), "BAB": ("Bab el-Mandeb", "Bab el-Mandeb"),
         "SUZN": ("Suez", "Suez"), "PANC": ("Panama", "Panama"), "CGH": ("Cap de Bonne-Espérance", "Cape of Good Hope"),
         "GIB": ("Gibraltar", "Gibraltar"), "DOV": ("Pas de Calais", "Dover Strait"), "LOM": ("Lombok", "Lombok")}


def _get(params):
    for attempt in range(4):
        try:
            r = requests.get(API, params=params, timeout=90)
            if r.status_code == 429:
                raise RuntimeError("429")
            r.raise_for_status()
            return r.json().get("data", [])
        except Exception as e:
            print(f"Comtrade, nouvel essai ({e})")
            time.sleep(8 * (attempt + 1))
    raise RuntimeError("Comtrade indisponible")


def _mt(row):
    return (row.get("netWgt") or row.get("qty") or 0) / 1e9  # kg -> millions de tonnes


def fetch_matrix(year):
    """{(exportateur, importateur): Mt} pour une année."""
    out, declared = {}, set()
    imps = list(IMP)
    for k in range(0, len(imps), 4):
        chunk = imps[k:k + 4]
        rows = _get({"reporterCode": ",".join(map(str, chunk)), "period": year, "cmdCode": "271111", "flowCode": "M",
                     "partnerCode": ",".join(map(str, EXP))})
        for r in rows:
            mt = _mt(r)
            if r["reporterCode"] != r["partnerCode"] and mt >= 0.05:
                out[(r["partnerCode"], r["reporterCode"])] = mt
                declared.add(r["reporterCode"])
        time.sleep(2)
    missing = [c for c in IMP if c not in declared]
    exps = list(EXP)
    if missing:  # données miroir : exportations déclarées vers les importateurs silencieux
        for k in range(0, len(exps), 5):
            chunk = exps[k:k + 5]
            rows = _get({"reporterCode": ",".join(map(str, chunk)), "period": year, "cmdCode": "271111",
                         "flowCode": "X", "partnerCode": ",".join(map(str, missing))})
            for r in rows:
                mt = _mt(r)
                if r["reporterCode"] != r["partnerCode"] and mt >= 0.05:
                    out[(r["reporterCode"], r["partnerCode"])] = mt
            time.sleep(2)
    return out, sorted(declared), missing


def _hav(a, b):
    la1, la2, dl = math.radians(a[1]), math.radians(b[1]), math.radians(b[0] - a[0])
    return 6371 * math.acos(max(-1, min(1, math.sin(la1) * math.sin(la2) + math.cos(la1) * math.cos(la2) * math.cos(dl))))


def _graph():
    g = {k: [] for k in NODES}
    for e in EDGES.replace("\n", " ").split(";"):
        a, b = e.split()
        c = _hav(NODES[a], NODES[b]) + PENALTY.get((a, b), PENALTY.get((b, a), 0))
        g[a].append((b, c)); g[b].append((a, c))
    return g


def _route(g, s, t):
    dist, prev, q = {s: 0}, {}, [(0, s)]
    while q:
        d, u = heapq.heappop(q)
        if u == t:
            break
        if d > dist[u]:
            continue
        for v, c in g[u]:
            if d + c < dist.get(v, 1e18):
                dist[v] = d + c; prev[v] = u; heapq.heappush(q, (d + c, v))
    p = [t]
    while p[-1] != s:
        p.append(prev[p[-1]])
    return p[::-1]


def build(year, matrix):
    g = _graph()
    flows, used = [], set()
    for (e, i), mt in sorted(matrix.items(), key=lambda x: -x[1]):
        if e not in EXP or i not in IMP:
            continue
        a = (EXP[e][2], EXP[e][3])
        s = ATT_E[e]
        if e == 643 and IMP[i][2] > 90:
            a, s = RU_ASIA, "SAK"
        via = _route(g, s, ATT_I[i]) if s != ATT_I[i] else [s]
        used.update(via)
        flows.append({"f": e, "t": i, "mt": round(mt, 2), "a": list(a), "b": [IMP[i][2], IMP[i][3]],
                      "re": EXP[e][4], "ri": IMP[i][4], "via": via})
    total = sum(f["mt"] for f in flows)
    by_e, by_eu = {}, {}
    for f in flows:
        by_e[f["f"]] = by_e.get(f["f"], 0) + f["mt"]
        if f["ri"] == "eu":
            by_eu[f["f"]] = by_eu.get(f["f"], 0) + f["mt"]
    eu = sum(by_eu.values())
    choke = {k: round(sum(f["mt"] for f in flows if k in f["via"]), 1) for k in CHOKE}
    us = by_e.get(842, 0)
    summary = {
        "total": round(total, 1),
        "top_exp": [{"fr": EXP[c][0], "en": EXP[c][1], "mt": round(v, 1), "share": round(v / total * 100, 1)}
                    for c, v in sorted(by_e.items(), key=lambda x: -x[1])[:5]],
        "eu_mt": round(eu, 1),
        "eu_top": [{"fr": EXP[c][0], "en": EXP[c][1], "share": round(v / eu * 100, 1)}
                   for c, v in sorted(by_eu.items(), key=lambda x: -x[1])[:4]] if eu else [],
        "us_eu_share": round(sum(f["mt"] for f in flows if f["f"] == 842 and f["ri"] == "eu") / us * 100, 1) if us else 0,
        "hormuz": choke["HMZ"], "hormuz_share": round(choke["HMZ"] / total * 100, 1) if total else 0,
    }
    names = {f"e{c}": [v[0], v[1]] for c, v in EXP.items()}
    names.update({f"i{c}": [v[0], v[1]] for c, v in IMP.items()})
    return {"year": int(year), "checked": datetime.date.today().isoformat(), "names": names,
            "nodes": {k: list(NODES[k]) for k in sorted(used)},
            "choke": [{"k": k, "fr": v[0], "en": v[1], "p": list(NODES[k]), "mt": choke[k]} for k, v in CHOKE.items()],
            "flows": flows, "summary": summary}


def update(force=False):
    """Appelé par fetch_market_data.py : au plus une vérification par mois."""
    try:
        with open(PATH, encoding="utf-8") as f:
            cur = json.load(f)
    except Exception:
        cur = None
    today = datetime.date.today()
    if cur and not force:
        last = datetime.date.fromisoformat(cur.get("checked", "2000-01-01"))
        if (today - last).days < 30:
            return
    try:
        if cur and cur["year"] < today.year - 1:
            m, _, _ = fetch_matrix(cur["year"] + 1)
            new = build(cur["year"] + 1, m)
            if new["summary"]["total"] >= 0.95 * cur["summary"]["total"]:
                cur = new
                print(f"GNL : passage à {cur['year']}")
        elif not cur:
            m, _, _ = fetch_matrix(today.year - 2)
            cur = build(today.year - 2, m)
        cur["checked"] = today.isoformat()
    except Exception as e:
        print(f"Erreur commerce de GNL (Comtrade) : {e}")
        if not cur:
            return
        cur["checked"] = today.isoformat()
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    import sys
    y = int(sys.argv[1]) if len(sys.argv) > 1 else datetime.date.today().year - 2
    m, declared, missing = fetch_matrix(y)
    d = build(y, m)
    print(y, "total", d["summary"]["total"], "flux", len(d["flows"]), "importateurs silencieux", missing)
    print(json.dumps(d["summary"], ensure_ascii=False))
    print({c["fr"]: c["mt"] for c in d["choke"]})
    if "--write" in sys.argv:
        with open(PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
