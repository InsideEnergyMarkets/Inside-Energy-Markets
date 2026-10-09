# Inside Energy Markets

Site du podcast Inside Energy Markets (Tom Moulard) : épisodes, blog et données de marché
de l'énergie mises à jour automatiquement. Jekyll sur GitHub Pages.

- Repo : InsideEnergyMarkets/Inside-Energy-Markets (branche `main` = site en ligne)
- En ligne : https://insideenergymarkets.com/ (domaine Infomaniak, zone DNS gérée par Tom : A/AAAA GitHub Pages,
  `www` en CNAME, TXT de vérification GitHub ; fichier `CNAME` à la racine, baseurl vide).
  L'ancienne adresse insideenergymarkets.github.io/Inside-Energy-Markets/ redirige vers le domaine.
- Répondre en français.

## Règles de Tom (à respecter)

- Jamais de tiret cadratin (—) dans le contenu écrit.
- Pas de scraping de sites tiers sans API ou flux officiel (refusés : worldoilmonitor.com,
  hormuz.data-tracking.net, Yahoo Finance non officiel, pages HTML de l'UKMTO).
- Chaque donnée affiche sa source, sobrement (pas de mentions de fréquence de mise à jour,
  pas de rubrique « Sources et méthode », pas de disclaimers sous le bandeau d'actus).
- Repli systématique : si une source échoue, on garde la dernière valeur connue.
- Montrer un aperçu avant de commiter sur `main` (sauf petits changements quand Tom dit
  « pousse directement »). Regrouper les vérifications, éviter les allers-retours inutiles.
- Code couleur des variations de prix : hausse en vert, baisse en rouge (convention des marchés, demandée par Tom
  en oct. 2026 ; exception : stocks de gaz vs an dernier).
- Charte (ne pas réintroduire d'autres styles) : marine = structure, sarcelle `#00817d` = actions et liens
  (`#4fd1c5` sur fond sombre), orange = « en direct » et sélection, vert / rouge = hausse / baisse seulement.
  Boutons pilule : `.btn-primary` (sarcelle plein), `.btn-ghost` (contour), `.btn-listen` (petit, cartes).
  Liens d'action : petite pilule avec un chevron Font Awesome dans un `<span aria-hidden="true">`
  (`<i class="fa-solid fa-chevron-right ico-arr"></i>` ; retour `fa-chevron-left` ; lien externe `fa-arrow-up-right-from-square ico-arr ico-ext` ; fenêtres et tuiles internes : chevron),
  jamais les caractères → ← ↗ (`.section-head a`, `.mk-open`, `.inc-all`). Les flèches de contenu (« 179 → 180 ») restent.
  Chiffres et dates dans la langue de la page (`| replace: ".", dec`, `{% include date.html date=… %}`).
- TTF et JKM quotidiens : payants chez OilPriceAPI (offre Developer, 19 $/mois ; l'offre gratuite ne couvre que
  WTI, Brent, Henry Hub, Waha). Absents tant que Tom n'a pas pris l'offre. Le PEG vient de NaTran (le code PEG d'OilPriceAPI était non fiable).

## Environnement local (Windows)

- Python 3.11 : `C:/Users/tommo/AppData/Local/Programs/Python/Python311/python.exe` (pas dans le PATH de Bash).
  `PYTHONIOENCODING=utf-8` pour afficher les accents.
- `gh` connecté (compte InsideEnergyMarkets, scope workflow) : lancer des workflows, lire les logs.
  Dans PowerShell, recharger le PATH : `$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")`.
- Identité git du repo : Tom Moulard <325581313+InsideEnergyMarkets@users.noreply.github.com> (adresse masquée
  GitHub, réglée dans .git/config ; ne jamais commiter avec l'adresse KEDGE, qui serait publique).
- Pas de Ruby/Jekyll en local. Pour un aperçu fidèle : pousser une branche `apercu-*`,
  le workflow `preview-build.yml` construit le site (artefact « site »), puis
  `gh run download <id> -n site -D <dossier>` et servir `<dossier>`
  avec `python -m http.server 8769` (URL : http://127.0.0.1:8769/).
- Les crons commitent sur `main` : toujours `git pull --rebase` avant de pousser ;
  en cas de conflit sur `_data/*.json`, garder la version de `main` (plus récente).
- Pièges vus : dans Bash, utiliser des heredocs (`git commit -F - <<'EOF'`), pas la syntaxe
  PowerShell `@'...'@` ; PowerShell 5.1 lit les .ps1 sans BOM en ANSI (accents cassés) ;
  `Remove-Item` sur un chemin contenant `/marches/` est bloqué (passer par Bash `rm -rf`).

## Deux langues (FR à la racine, EN sous /en/)

- Chaque page = un fichier court par langue (`index.html` / `en/index.html`, `marches/` / `en/markets/`,
  `episodes/`, `analyses/` (`en/analysis/`), `about/`) qui inclut le même gabarit `_includes/pages/<page>.html`.
  Front matter : `ref` (relie les deux versions pour le sélecteur FR | EN et les `hreflang`), `lang` via
  les `defaults` de `_config.yml` (tout ce qui est sous `en/` est en anglais).
- Textes : `_data/i18n.yml` (sections `fr` et `en`, mêmes clés ; `js:` pour les scripts du layout, lus via
  `window.iemT`). Chaque gabarit commence par `{% include i18n.html %}` : `lang`, `t`, `u` (adresses des pages),
  `dec` (séparateur décimal : `| replace: ".", dec`). Marqueurs à remplacer : `%n`, `%m`, `%y`
  (jamais `{n}` : les accolades cassent Liquid dans `{{ }}`).
- Ancres de /marches/ traduites (`t.ids.*` : `#electricite` / `#electricity`...).
- Données : `date_label_en` (Brent, HH, spot), `place_en` / `vessel_type_en` (incidents), `lang` (actus :
  la version anglaise n'affiche que les titres en anglais), `title_en` / `description_en` (episodes.yml),
  `value_en` / `text_en` (chokepoints_context.yml).
- Articles : un fichier par langue (`_posts/` et `en/_posts/`), même `ref`. Un nouvel article doit avoir sa
  traduction, sinon le sélecteur renvoie vers l'accueil de l'autre langue.
- Le podcast est en français : mention sur les pages anglaises (épisodes, accueil, bloc « Listen »).

## Référencement

- Titre de l'accueil orienté recherche (« Le podcast de Tom Moulard sur les marchés de l'énergie »).
- Google Search Console et Bing Webmaster Tools (importé depuis la Search Console) : gérés par Tom.
- IndexNow (Bing, Yandex...) : clé `ba5fdc11ee8578d5540c332e9933f73f.txt` à la racine (hors sitemap). Après un
  nouvel article ou une nouvelle page, envoyer les adresses du sitemap en POST à `https://api.indexnow.org/indexnow`
  (`host`, `key`, `keyLocation` = URL complète du fichier clé, `urlList`) ; réponse 200 ou 202 = accepté.

## Structure

- `index.html` : accueil (hero podcast avec pastille photo de Tom, bandeau d'actus (titre suivant arrivant par le haut)
  + tapis roulant de cotations `quotes-strip.html` (prix, repères, détroits), derniers épisodes, « Le point marchés »
  en tableau de cotations : une ligne par marché liée à sa rubrique de /marches/, courbe 30 j via
  `_includes/sparkline.html` (SVG calculé en Liquid depuis `market_history.json`), ligne incidents 30 j ;
  derniers articles, puis bloc `_includes/podcast-cta.html` « Écouter / Venir en invité », aussi sur À propos et /episodes/ ;
  partout (accueil, /episodes/, À propos) `contact=true` remplace « Venir en invité » par la carte « Échangeons » avec la photo).
- `marches/index.html` (option C : tableau de bord + détail en fenêtre `<dialog class="mk-dialog">`
  ouverte par `[data-dialog]`) : sommaire collant, rubriques dans cet ordre :
  `#electricite` (carte prix + mix), `#gaz` (Henry Hub quotidien + stocks de gaz UE/France ; tuiles
  « Le gaz dans le monde sur 10 ans » et « Exportations de GNL » en fenêtre), `#petrole` (Brent +
  graphique Ormuz / Brent 12 mois), `#routes-maritimes` (3 fiches compactes avec carte MarineTraffic,
  détail 90 j en fenêtre), `#securite` (carte des incidents + chiffres 30 j).
  Règle de cohérence : à l'écran, seulement des données récentes ; les séries mensuelles en retard
  (FMI, EIA) vont dans une fenêtre, présentées comme tendance de fond.
- Navigation Turbo (`@hotwired/turbo` via jsDelivr, dans `<head>`, cache désactivé) : les liens internes
  ne rechargent pas la fenêtre, le lecteur (`#pl-root`, `data-turbo-permanent`, audio détaché `new Audio()`)
  continue d'une page à l'autre. Les scripts du `<body>` sont rejoués à chaque page : les écouteurs globaux
  sont dans le bloc `if (!window.iemApp)`, les minuteurs dans `window.iemTimers`. Scripts externes (Leaflet,
  GoatCounter) à mettre dans `<head>`, jamais dans une page. GoatCounter compte les pages sur `turbo:load`.
- `_layouts/default.html` : nav, footer, Chart.js et tous les scripts (graphiques, vue agrandie,
  base 100, cartes AIS, bandeau d'actus, carte Leaflet des incidents, sommaire).
  Vérifier la fermeture des IIFE `})();` après chaque modification.
- Rubrique « Analyses » / « Analysis » (ex-Blog ; adresses /analyses/ et /en/analysis/, anciennes /blog/ redirigées par jekyll-redirect-from) : en tête la note de marché de la semaine
  (`id="notes"`), puis les articles, puis les notes précédentes. Pas de pages /notes/.
- Note de marché hebdo : `scripts/generate_note.py` (workflow `weekly-note.yml`, lundi 05:00 UTC, puis IndexNow) écrit
  `_notes/AAAA-SS-fr.md` / `-en.md` (collection, gabarit `_layouts/note.html`, permaliens `/analyses/note-de-marche-AAAA-sSS/`
  et `/en/analysis/market-note-AAAA-wSS/`) et `_linkedin/AAAA-SS.txt` (texte LinkedIn), puis `scripts/linkedin_visual.py` dessine les visuels LinkedIn
  (`_linkedin/AAAA-SS-1.png` : cartes Électricité et Gaz France façon page Marchés, courbe 30 j + moyenne hebdo en marches,
  bandeau stocks UE / Brent ; copié dans `assets/img/notes/AAAA-SS.png` = `image` de la note FR, carte de l'accueil et og:image ; `-2.png` base 100 si chaque série couvre 15 jours) en HTML photographié par
  Chrome sans interface ; résumé du workflow (texte + images) et artefact « linkedin » à télécharger. Format inspiré des notes hebdo de
  fournisseurs (titre, contexte d'actus, rubriques à puces + graphique `canvas[data-nt-chart]`, « Lecture clé »).
  Phrases construites depuis les données uniquement. Le corps du fichier = « Le mot de Tom » (facultatif).
  Mix de la semaine : production réelle au quart d'heure (Energy-Charts `public_power`), jamais les instantanés du site
  (un relevé le soir, sans solaire). Brent : « dernier cours » (relevé OilPriceAPI), pas le règlement officiel ICE.
  Moyennes : électricité et PEG = moyenne simple des moyennes journalières de la semaine contre celle de la semaine
  précédente ; Brent = clôture contre clôture.
  Format retenu (A, oct. 2026) : Lecture clé, tuiles, puis par rubrique (électricité, gaz PEG, pétrole) 3 puces et un graphique
  détaillé (60 j stockés, boutons 7/30/60 j, 30 par défaut) (`chart.type: detail`, fond marine, semaine en surbrillance, 5 chiffres), presse en bas. Pas d'Ormuz ni de
  détroits (données PortWatch en retard). Autres formats gardés pour des notes « focus » : `scripts/note_formats.py`
  (B base 100, C éditorial, D 3 chiffres, E électricité à la loupe) + 5 textes LinkedIn. LinkedIn retenu : titre,
  Lecture clé, une ligne-chiffre par marché (⚡ 🔥 🛢️), lien.
  Une note existante n'est jamais écrasée (sauf `--force`).
- Pages de référence (SEO, FAQ + FAQPage) : `/prix-baril-brent/`, `/prix-gazole/`, `/stocks-gaz-europe/` (+ EN),
  gabarit `_includes/pages/reference.html`, blocs partagés avec /marches/ dans `_includes/blocks/`.
- Articles : article le plus récent « à la une », étiquettes (`tags:` dans le front matter), temps de lecture
  (`reading-time.html`), partage LinkedIn, encadré auteur, article précédent / suivant. Flux RSS `/feed.xml`
  (jekyll-feed) gardé sans bouton visible (Tom n'en veut pas).
- À propos : chiffres du podcast calculés depuis `podcast.json` (mois de lancement forcé par `podcast_start` dans `_config.yml`), parcours sans dates (à compléter par Tom),
  sujets, blocs « Écouter » et « Invité ». Adresse e-mail jamais en clair : `data-contact` = adresse à l'envers
  en base64, reconstituée au clic par le script du layout.
- `_includes/` : `episode-card.html` (carte épisode retournable : « Écouter » montre les liens au dos ;
  utilisée sur l'accueil, /episodes/ et dans les articles ; la carte prend la hauteur de sa plus grande face,
  fondu au lieu de la rotation 3D sur écran tactile), `date.html`, `market-card.html` (carte prix retournable), `price-change.html` (flèche vs cours
  précédent), `chokepoint.html` (fiche compacte + fenêtre de détail) + `chokepoint-kpi.html`, `incidents.html`,
  `news-ticker.html`.
- `assets/css/style.css` : fichier unique et long. Après chaque modification, vérifier que les
  accolades sont équilibrées (une `}` manquante a déjà cassé tout le CSS sans erreur visible).
- Liquid (Jekyll 3 de GitHub Pages) : `market.chokepoints[parts[0]]` ne marche pas, passer par
  une variable intermédiaire (`assign k = parts[0]`).

## Données (`_data/`, générées automatiquement)

`scripts/fetch_market_data.py` (workflow `update-market-data.yml`, cron 0/6/12/18 h UTC) :
- `market.json` : prix du jour + `date_label`, `change_pct` / `prev_value` / `prev_date`.
  - Brent et Henry Hub : OilPriceAPI (date = `as_of`, week-end ramené au vendredi) = contrats à terme du premier mois
    (Brent ICE, `NATURAL_GAS_USD` = Henry Hub NYMEX, PAS le spot). Jamais mélangés avec le spot EIA : en cas d'échec,
    dernière valeur connue ; l'historique ne contient que des valeurs OilPriceAPI (rattrapage `past_month` en moyennes
    journalières : refusé en offre gratuite (402), désactivé via `_data/oilprice_backfill.json` ; l'historique se constitue jour
    après jour depuis le 25/09/2026). En attendant, le spot EIA (`brent_year.json`) est tracé en pointillés « pour contexte »
    sur les graphiques Brent (`context` dans mktChartData, 2e série de la note) ; il n'entre jamais dans les chiffres.
  - Gaz France (PEG, zone TRF depuis la fusion des zones en 2018) : prix moyen journalier publié par NaTran (ex-GRTgaz),
    export CSV de la plateforme Smart (`smart.natrangroupe.com/api/v1/fr/prix_bourse/export/ZONE.csv`, sans clé) :
    moyenne pondérée de tous les produits échangés sur EEX pour la journée gazière. `market.peg`, `peg_eur_mwh` dans
    l'historique. Remplace le Henry Hub partout (accueil, tapis, note, LinkedIn, rubrique Gaz) ; Henry Hub = tuile secondaire.
  - Spot électricité : RTE Wholesale Market v3 (ne renvoie que le jour en cours ; moyenne des
    prix quart d'heure de la journée).
  - Mix et CO2 : RTE éCO2mix (`where=nucleaire is not null` obligatoire), parts triées.
  - Détroits : IMF PortWatch (moyenne des 5 derniers jours publiés ; normale = moyenne
    janv.-oct. 2023 ; publication hebdo, ~1 semaine de retard ; statut fluide >= 80 %, partiel >= 40 %, ferme >= 15 %, arret en dessous = « Quasi à l'arrêt »).
- Gaz affiché en €/MWh : taux de référence BCE (API data-api.ecb.europa.eu, sans clé) dans `fx.json`
  (quotidien 400 j, mensuel 11 ans) ; Henry Hub `price_eur_mwh` / `henry_hub_eur_mwh`, FMI champ `e` de
  `gas_world.json`. Les valeurs $/MMBtu restent stockées. 1 MMBtu = 0,29307107 MWh.
- `market_history.json` : 60 j, chaque prix à sa date de cotation avec sa source ; pas de
  Brent/HH le week-end ; l'EIA comble les trous (15 derniers jours, sans écraser).
- `chokepoints_history.json` (90 j par détroit + `hormuz_year`), `brent_year.json` (EIA 12 mois),
  `weekly_summary.json`, `lng_exports.json` (EIA N9133US2, 25 mois, en Bcf/j),
  `gas_world.json` (FMI via FRED, CSV officiel fredgraph.csv sans clé : PNGASEUUSDM Europe, PNGASJPUSDM
  Asie, PNGASUSUSDM États-Unis, 10 ans, $/MMBtu, ~2 mois de retard ; citer « FMI via FRED »),
  `gas_storage.json` (GIE AGSI+, secret GIE_API_KEY en en-tête `x-key` : remplissage UE et France depuis
  le 1er janvier de l'an dernier ; compte GIE « All platforms », donc ALSI et IIP aussi accessibles),
  `chokepoints_context.yml` (chiffres EIA fixes, mis à jour à la main).
- Prix day-ahead (ENTSO-E, secret ENTSOE_API_KEY) : `day_ahead.json` (France au quart d'heure résumé par heure,
  pays voisins, 7 jours). Page `/prix-electricite-demain/` + tuile en fenêtre dans #electricite.
- Pétrole : `market.wti` (OilPriceAPI WTI_USD, repli EIA RWTC), `oil_year.json` (Brent/WTI EIA 12 mois),
  `us_crude_stocks.json` (EIA WCESTUS1 hebdo), `oil_balance.json` (EIA STEO PAPR_WORLD / PATC_WORLD,
  24 mois + prévisions, pointillés à partir du mois en cours), `fuel.json` (pompe : flux instantané
  DGCCRF sur data.economie.gouv.fr, Licence Ouverte, sans clé, stations mises à jour depuis 7 j,
  historique quotidien 120 j), `fuel_taxes.yml` (TICPE et TVA, tenus à la main, à vérifier chaque année).
  #petrole : Brent à gauche (même DA qu'élec et gaz), offre/demande mondiales à droite, tuiles WTI,
  stocks US, Ormuz/Brent, prix à la pompe (décomposition du litre de gazole).

`scripts/fetch_news.py` (workflow `update-news.yml`, toutes les 2 h à la demi-heure) :
- `podcast.json` : flux RSS public du podcast `https://anchor.fm/s/10edf0868/podcast/rss` (Spotify for Creators,
  trouvé via l'API iTunes lookup id 6807057201) : lien audio, durée, date par numéro d'épisode. Alimente le lecteur
  intégré (barre en bas + grande vue, script dans `_layouts/default.html`, boutons `[data-play]` au dos des cartes
  et de la pochette du hero, qui prend le dernier épisode présent dans le flux). Un épisode absent du flux
  (ex. EP 10 en attente) n'a ni durée ni « Écouter ici ». Les écoutes passent par Spotify for Creators (stats).
- `news.json` : flux RSS (FEEDS dans le script) : spécialisés énergie non filtrés (Le Monde Énergies, Connaissance
  des Énergies, EIA, Commission européenne) et généralistes filtrés sur le titre (Guardian, BBC, Al Jazeera, France 24,
  Le Monde) ; « Iran » seul exige un terme énergie. 14 titres par langue, 3 par source, 5 jours.
  Testés et indisponibles : AIE, CRE, OPEP, IRENA, Ofgem, ENTSO-E.
- `incidents.json` : flux UKMTO `https://sccd.royalnavy.mod.uk/api/ukmto/all` (celui de leur
  carte ; Open Government Licence v3.0, citer « UKMTO · Open Government Licence v3.0 »), 12 mois,
  lieux et types traduits, noms de navires anonymisés donc non affichés, stats 30 j.

`scripts/backfill_history.py` (workflow manuel) : EIA pour Brent/HH, Energy-Charts (SMARD) pour
l'historique du spot.

Secrets GitHub : EIA_API_KEY, RTE_BASE64_KEY, OILPRICEAPI_KEY, GIE_API_KEY (+ RTE_CLIENT_ID/SECRET, AISSTREAM_API_KEY inutilisé).

## Pistes étudiées et écartées

- AIS en direct gratuit (AISStream) : 0 navire à Ormuz et Bab-el-Mandeb (pas de stations).
- Historique OilPriceAPI `past_month` : ~100 ticks par page, trop de requêtes (quota 50/jour).
- GDELT (429 depuis GitHub, bruité), NGA ASAM (API 404), ACLED (événements à 12 mois de retard
  en gratuit, republication interdite), fond de carte CARTO (clé requise ; on garde OSM filtré).
- Cartes MarineTraffic : intérieur non personnalisable (iframe) ; seul le cadrage et l'habillage.
- OilPriceAPI TTF/JKM/PEG : codes `DUTCH_TTF_EUR`, `JKM_LNG_USD`, `NATURAL_GAS_PEG_EUR` ; historique quotidien via
  `past_month|past_year?by_code=A,B&interval=daily` (une requête pour plusieurs codes). Testé pendant l'essai
  « professional » (fin vers le 04/10/2026), payant ensuite. Le code complet est dans l'historique git
  (branche apercu-gaz, commit « rubriques Pétrole et Gaz séparées, TTF en référence »).

## En cours / à venir

- Migration vers Cloudflare Pages (pour passer le dépôt en privé ; Tom ne veut plus que le code apparaisse dans
  les moteurs de recherche). Prête et inactive : `.github/actions/build-deploy` (construit avec le Jekyll de
  GitHub Pages et envoie en direct, ne compte pas dans les 500 constructions Cloudflare), `deploy-site.yml` (push sur
  main), données et note hebdo publient elles-mêmes si elles ont changé, aperçus sur `<branche>.insideenergymarkets.pages.dev`,
  `cloudflare-setup.yml` (création du projet, une fois). Étapes restantes : Tom crée le compte, le jeton (Cloudflare Pages :
  Edit) et les secrets `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` ; lancer `cloudflare-setup.yml` ; vérifier
  insideenergymarkets.pages.dev ; domaine personnalisé dans Cloudflare + DNS chez Infomaniak (Tom) ; dépôt privé ;
  désactiver GitHub Pages ; retrait de la page GitHub dans Bing/Google. Quota Actions en privé gratuit : 2 000 min/mois
  (estimation ~1 000) ; si besoin, actus toutes les 3 h ou petit budget de dépassement.

- TTF quotidien si Tom prend l'offre OilPriceAPI Developer (question posée à leur support) : il irait en tête
  de la rubrique Gaz, au-dessus des stocks.
- Pistes GIE : ALSI (terminaux GNL européens), IIP (indisponibilités, pour les signaux).
- Capacités de liquéfaction : pas d'API EIA (fichier Excel).
- Pages épisode illustrées (collection `_transcripts`, gabarit `_layouts/episode.html`, transcription Whisper
  repliée en bas) : EP 10 en aperçu sur la branche `apercu-episode-10`, en attente de relecture par l'invité.
- Simulateur éducatif (tout fictif) prêt sur la branche `apercu-simulateur`, gardé HORS du site pour l'instant
  (décision de Tom) : /simulateur/ et /en/simulator/, onglets Positions (Brent, Henry Hub, navires au trait),
  Arbitrage WTI → Brent (fret et durée = hypothèses du joueur), Raffineur (marge 3-2-1, EIA New York),
  carnet « pourquoi », localStorage. P&L : gain vert, perte rouge (validé par Tom). La branche contient aussi
  l'ajout essence/diesel EIA dans oil_year.json. À rebaser sur main avant publication.
- Pistes notées : guide « Acheter son énergie en entreprise », page « Les métiers des marchés de l'énergie »,
  note hebdo archivée sur le site (newsletter LinkedIn).
- Plus tard : système de signaux (détroit fermé / mouvement de prix), `analyze_history.py`,
  note hebdo `generate_note.py`, ajout du WTI (spread Brent-WTI), paper trading (mis de côté).
