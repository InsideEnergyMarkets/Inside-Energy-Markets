# Inside Energy Markets

### 👉 Le site du podcast : **[insideenergymarkets.com](https://insideenergymarkets.com/)**

*Inside Energy Markets* est le podcast de Tom Moulard sur les coulisses des marchés de l'énergie : formation des prix de l'électricité et du gaz, GNL, géopolitique, stratégies d'achat et de couverture. Des épisodes courts, de quelques minutes, pour comprendre un sujet de marché d'un coup.

Sur le site :

- **[Épisodes](https://insideenergymarkets.com/episodes/)** à écouter directement dans le navigateur
- **[Marchés](https://insideenergymarkets.com/marches/)** : électricité en France, gaz, Brent, stocks de gaz européens, trafic dans les détroits d'Ormuz, Bab-el-Mandeb et Malacca, mis à jour automatiquement
- **[Analyses](https://insideenergymarkets.com/analyses/)** : note de marché hebdo, analyses et décryptages
- **[À propos](https://insideenergymarkets.com/about/)**

Écouter aussi sur [Spotify](https://open.spotify.com/show/4P5bMdv7UfIpFAiT7cyDJA) et [Apple Podcasts](https://podcasts.apple.com/us/podcast/inside-energy-markets/id6807057201). Suivre Tom Moulard sur [LinkedIn](https://www.linkedin.com/in/tom-moulard/).

---

## Ce dépôt

Code source du site : Jekyll sur GitHub Pages. Les données de marché, les actualités et le flux du podcast sont mis à jour automatiquement par des workflows GitHub Actions (`scripts/`, `.github/workflows/`), chaque source affichée sur le site avec sa provenance.

**Publier un article** : ajouter un fichier `_posts/AAAA-MM-JJ-titre-court.md` avec en tête :

```
---
title: "Titre de l'article"
date: 2026-09-15
image: /assets/img/mon-image.jpg
tags: [GNL, Gaz]
---
```

**Ajouter un épisode** : ajouter un bloc dans `_data/episodes.yml` (`number`, `title`, `description`, `spotify`, `apple`, `linkedin`). Le lien audio et la durée sont repris automatiquement du flux RSS du podcast.
