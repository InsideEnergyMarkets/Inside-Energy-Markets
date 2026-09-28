# Inside Energy Markets

Site du podcast Inside Energy Markets (Tom Moulard) : épisodes, blog et données de marché
de l'énergie mises à jour automatiquement. Jekyll sur GitHub Pages.

- Repo : InsideEnergyMarkets/Inside-Energy-Markets (branche `main` = site en ligne)
- En ligne : https://insideenergymarkets.github.io/Inside-Energy-Markets/ (baseurl `/Inside-Energy-Markets`)
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
- Code couleur des variations de prix : hausse en rouge, baisse en vert.
- Charte (ne pas réintroduire d'autres styles) : marine = structure, sarcelle `#00817d` = actions et liens
  (`#4fd1c5` sur fond sombre), orange = « en direct » et sélection, rouge / vert = hausse / baisse seulement.
  Boutons pilule : `.btn-primary` (sarcelle plein), `.btn-ghost` (contour), `.btn-listen` (petit, cartes).
  Liens d'action « … → » : petite pilule avec la flèche dans un `<span>` (`.section-head a`, `.mk-open`, `.inc-all`).
  Chiffres et dates dans la langue de la page (`| replace: ".", dec`, `{% include date.html date=… %}`).
- TTF et JKM quotidiens : payants chez OilPriceAPI (offre Developer, 19 $/mois ; l'offre gratuite ne couvre que
  WTI, Brent, Henry Hub, Waha). Absents tant que Tom n'a pas pris l'offre. Le PEG (France) est exclu : non fiable.

## Environnement local (Windows)

- Python 3.11 : `C:/Users/tommo/AppData/Local/Programs/Python/Python311/python.exe` (pas dans le PATH de Bash).
  `PYTHONIOENCODING=utf-8` pour afficher les accents.
- `gh` connecté (compte InsideEnergyMarkets, scope workflow) : lancer des workflows, lire les logs.
  Dans PowerShell, recharger le PATH : `$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")`.
- Identité git du repo : Tom Moulard <tom.moulard@kedgebs.com>.
- Pas de Ruby/Jekyll en local. Pour un aperçu fidèle : pousser une branche `apercu-*`,
  le workflow `preview-build.yml` construit le site (artefact « site »), puis
  `gh run download <id> -n site -D <dossier>/Inside-Energy-Markets` et servir `<dossier>`
  avec `python -m http.server 8769` (URL : http://127.0.0.1:8769/Inside-Energy-Markets/).
- Les crons commitent sur `main` : toujours `git pull --rebase` avant de pousser ;
  en cas de conflit sur `_data/*.json`, garder la version de `main` (plus récente).
- Pièges vus : dans Bash, utiliser des heredocs (`git commit -F - <<'EOF'`), pas la syntaxe
  PowerShell `@'...'@` ; PowerShell 5.1 lit les .ps1 sans BOM en ANSI (accents cassés) ;
  `Remove-Item` sur un chemin contenant `/marches/` est bloqué (passer par Bash `rm -rf`).

## Deux langues (FR à la racine, EN sous /en/)

- Chaque page = un fichier court par langue (`index.html` / `en/index.html`, `marches/` / `en/markets/`,
  `episodes/`, `blog/`, `about/`) qui inclut le même gabarit `_includes/pages/<page>.html`.
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

- `index.html` : accueil (hero podcast, bandeau d'actus, derniers épisodes, « Le point marchés »
  en tableau de cotations : une ligne par marché liée à sa rubrique de /marches/, courbe 30 j via
  `_includes/sparkline.html` (SVG calculé en Liquid depuis `market_history.json`), ligne incidents 30 j ;
  derniers articles, puis bloc `_includes/podcast-cta.html` « Écouter / Venir en invité », aussi sur À propos et /episodes/).
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
- Blog : article le plus récent « à la une », étiquettes (`tags:` dans le front matter), temps de lecture
  (`reading-time.html`), partage LinkedIn, encadré auteur, article précédent / suivant. Flux RSS `/feed.xml`
  (jekyll-feed) gardé sans bouton visible (Tom n'en veut pas).
- À propos : chiffres du podcast calculés depuis `podcast.json`, parcours sans dates (à compléter par Tom),
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
  - Brent et Henry Hub : OilPriceAPI (date = `as_of`, week-end ramené au vendredi), repli EIA.
    `NATURAL_GAS_USD` = spot Henry Hub. Brent OilPriceAPI = future ICE front-month (EIA = spot).
  - Spot électricité : RTE Wholesale Market v3 (ne renvoie que le jour en cours ; moyenne des
    prix quart d'heure de la journée).
  - Mix et CO2 : RTE éCO2mix (`where=nucleaire is not null` obligatoire), parts triées.
  - Détroits : IMF PortWatch (moyenne des 5 derniers jours publiés ; normale = moyenne
    janv.-oct. 2023 ; publication hebdo, ~1 semaine de retard ; statut fluide >= 80 %, partiel >= 40 %).
- `market_history.json` : 60 j, chaque prix à sa date de cotation avec sa source ; pas de
  Brent/HH le week-end ; l'EIA comble les trous (15 derniers jours, sans écraser).
- `chokepoints_history.json` (90 j par détroit + `hormuz_year`), `brent_year.json` (EIA 12 mois),
  `weekly_summary.json`, `lng_exports.json` (EIA N9133US2, 25 mois, en Bcf/j),
  `gas_world.json` (FMI via FRED, CSV officiel fredgraph.csv sans clé : PNGASEUUSDM Europe, PNGASJPUSDM
  Asie, PNGASUSUSDM États-Unis, 10 ans, $/MMBtu, ~2 mois de retard ; citer « FMI via FRED »),
  `gas_storage.json` (GIE AGSI+, secret GIE_API_KEY en en-tête `x-key` : remplissage UE et France depuis
  le 1er janvier de l'an dernier ; compte GIE « All platforms », donc ALSI et IIP aussi accessibles),
  `chokepoints_context.yml` (chiffres EIA fixes, mis à jour à la main).

`scripts/fetch_news.py` (workflow `update-news.yml`, toutes les 2 h à la demi-heure) :
- `podcast.json` : flux RSS public du podcast `https://anchor.fm/s/10edf0868/podcast/rss` (Spotify for Creators,
  trouvé via l'API iTunes lookup id 6807057201) : lien audio, durée, date par numéro d'épisode. Alimente le lecteur
  intégré (barre en bas + grande vue, script dans `_layouts/default.html`, boutons `[data-play]` au dos des cartes
  et de la pochette du hero, qui prend le dernier épisode présent dans le flux). Un épisode absent du flux
  (ex. EP 10 en attente) n'a ni durée ni « Écouter ici ». Les écoutes passent par Spotify for Creators (stats).
- `news.json` : titres RSS d'Al Jazeera, France 24, Le Monde, EIA, BBC filtrés sur le titre
  (« Iran » seul exige un terme énergie/maritime), 3 derniers jours.
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

- TTF quotidien si Tom prend l'offre OilPriceAPI Developer (question posée à leur support) : il irait en tête
  de la rubrique Gaz, au-dessus des stocks.
- Pistes GIE : ALSI (terminaux GNL européens), IIP (indisponibilités, pour les signaux).
- Capacités de liquéfaction : pas d'API EIA (fichier Excel).
- Plus tard : système de signaux (détroit fermé / mouvement de prix), `analyze_history.py`,
  note hebdo `generate_note.py`, ajout du WTI (spread Brent-WTI), paper trading (mis de côté).
