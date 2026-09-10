---
title: "Le GNL, nouvelle colonne vertébrale du gaz européen"
date: 2026-09-09
image: /assets/img/gnl-cargo.jpg
---

Depuis 2022, l'Europe a changé de fournisseur de gaz sans vraiment changer de dépendance. Le pipeline russe a cédé la place au méthanier américain, et cette bascule redessine en profondeur la géopolitique de l'énergie sur le continent.

## Une bascule spectaculaire en quelques années

En 2019, le gaz russe couvrait près de la moitié de l'approvisionnement gazier européen, et le GNL un peu moins d'un quart. Aujourd'hui, ces proportions se sont presque inversées : la part russe est tombée à quelques points de pourcentage, tandis que le GNL représente désormais près de la moitié du gaz consommé dans l'UE. L'Union européenne est ainsi devenue, en l'espace de trois ans, le premier importateur mondial de GNL, devant la Chine et le Japon, historiquement les plus gros acheteurs.

Mais ce basculement a un prix : une nouvelle forme de dépendance, cette fois vis-à-vis des États-Unis. Les exportations américaines vers l'Europe ont presque triplé depuis 2021, et les projections tablent sur une Europe dépendante des cargaisons américaines à hauteur de deux tiers de ses importations de GNL dès cette année, avec une trajectoire vers 80 % d'ici 2028. Le raisonnement qui a guidé la sortie du gaz russe, diversifier pour sécuriser, se heurte ainsi à une réalité plus complexe : remplacer un fournisseur unique par un autre fournisseur dominant n'élimine pas le risque de concentration, il le déplace.

## Trois bassins, deux clients

Le commerce mondial du GNL s'organise autour de trois grandes zones de production. Le bassin atlantique, tiré par les États-Unis, irrigue principalement l'Europe. Les bassins pacifique (Australie, Asie du Sud-Est) et moyen-oriental (Qatar en tête) alimentent surtout l'Asie. Cette géographie explique pourquoi l'Europe et l'Asie sont, de fait, en concurrence directe pour les mêmes cargaisons dès que l'un des deux bassins connaît une tension : une panne sur une installation américaine, un pic de demande chinoise, ou une crise dans le Golfe suffisent à faire bouger les prix des deux côtés du globe simultanément.

Le marché mondial continue par ailleurs de s'élargir : de nouveaux exportateurs comme le Canada ou la Mauritanie ont commencé à livrer leurs premières cargaisons en 2025, et l'offre mondiale devrait encore croître significativement cette année, portée par de nouvelles capacités américaines, qataries et australiennes.

## Ce que ça change concrètement

Le prix européen du gaz était déjà en partie connecté au marché mondial avant 2022, mais cette connexion s'est nettement resserrée avec la montée en puissance du GNL. Une vague de froid en Asie, un incident sur un terminal de liquéfaction américain, ou une tension dans un détroit stratégique se répercutent aujourd'hui plus vite et plus fort sur le TTF qu'à l'époque où le pipeline russe dominait les approvisionnements. C'est d'ailleurs ce qui s'est produit récemment avec les tensions autour du détroit d'Ormuz, un point de passage que le Qatar (environ 7 % seulement des importations européennes) traverse pour exporter, et dont le blocage a fait grimper les prix mondiaux bien au-delà de l'exposition directe de l'Europe à cette route précise.

## Et ensuite ?

En attendant, si vous voulez revenir sur les bases (terminaux méthaniers, stockage, rôle du gaz dans le mix électrique), l'épisode 4 du podcast pose le cadre :

{% assign ep4 = site.data.episodes | where: "number", 4 | first %}
<div class="card card--episode post-episode-card">
  <div class="card-thumb">
    <img src="{{ '/assets/img/hero.png' | relative_url }}" alt="{{ ep4.title }}">
    <span class="card-thumb-badge">EP {{ ep4.number }}</span>
  </div>
  <div class="card-body">
    <h3>{{ ep4.title }}</h3>
    <p>{{ ep4.description }}</p>
    <div class="listen-cta-wrap">
      <button type="button" class="btn-listen" aria-expanded="false">Écouter <i class="fa-solid fa-play"></i></button>
      <div class="listen-dropdown">
        <a class="spotify" href="{{ ep4.spotify }}" target="_blank"><i class="fa-brands fa-spotify"></i> Écouter sur Spotify</a>
        <a class="apple" href="{{ ep4.apple }}" target="_blank"><i class="fa-solid fa-podcast"></i> Écouter sur Apple Podcasts</a>
        <a class="linkedin" href="{{ ep4.linkedin | default: 'https://www.linkedin.com/in/tom-moulard/' }}" target="_blank"><i class="fa-brands fa-linkedin"></i> Voir sur LinkedIn</a>
      </div>
    </div>
  </div>
</div>

---

**Sources** : rapport annuel de l'ACER sur le marché du GNL (mai 2026) ; GIIGNL, *Annual Report* 2026 ; IEEFA, analyse sur la dépendance européenne au GNL américain ; Le Grand Continent, sur les flux gaziers vers l'Europe.
