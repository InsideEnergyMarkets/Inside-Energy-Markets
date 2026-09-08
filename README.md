# Inside Energy Markets — site

Site Jekyll pour le podcast et le blog "Inside Energy Markets".

## Mettre le site en ligne (une seule fois)

1. Crée un nouveau repo GitHub, par ex. `inside-energy-markets` (public).
2. Dans l'onglet "Add file → Upload files" du repo, glisse-dépose **tout le contenu** de ce dossier (pas le dossier lui-même, son contenu).
3. Va dans **Settings → Pages**.
4. Sous "Build and deployment", choisis Source = **Deploy from a branch**, Branch = **main**, dossier = **/ (root)**. Sauvegarde.
5. Attends 1-2 minutes, le site sera en ligne à `https://TON-PSEUDO.github.io/inside-energy-markets/`.

Si tu veux que le site soit à la racine (`TON-PSEUDO.github.io` sans `/inside-energy-markets/`), nomme le repo exactement `TON-PSEUDO.github.io`.

## Publier un nouvel article de blog

1. Dans le dossier `_posts/`, crée un nouveau fichier nommé :
   `AAAA-MM-JJ-titre-court-sans-accents.md`
   (ex : `2026-09-15-marche-gnl-europe.md`)
2. Colle ce bloc en haut du fichier, puis ton texte en dessous :

```
---
title: "Ton titre ici"
date: 2026-09-15
---

Ton article ici, en Markdown (# titres, **gras**, listes avec -, etc.)
```

3. Ajoute/commit le fichier sur GitHub (tu peux le faire directement dans l'interface web, bouton "Add file" ou en éditant depuis le dossier `_posts`).
4. Le site se régénère automatiquement en 1-2 minutes, l'article apparaît sur `/blog/` et sur l'accueil.

## Ajouter/modifier un épisode

Édite `_data/episodes.yml` — chaque épisode est un bloc avec `number`, `title`, `description`, `spotify`, `apple`.

## À faire avant mise en ligne

- Remplacer les liens Spotify/Apple Podcasts placeholder (`_data/episodes.yml`, `_layouts/default.html`) par tes vrais liens une fois le flux RSS actif.
- Remplacer le lien LinkedIn placeholder par ton profil.
- `assets/img/hero.png` est ta pochette de podcast — tu peux la remplacer par une autre image si besoin (même nom de fichier).

## Tester en local (optionnel, si tu veux prévisualiser avant de publier)

Nécessite Ruby installé :
```
bundle install
bundle exec jekyll serve
```
Puis ouvre `http://localhost:4000`.
