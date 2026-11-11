# Crédits des assets

Politique : uniquement des packs sous licence **CC0** (domaine public) pour démarrer. Chaque pack ajouté
est listé ici avec sa source et sa licence. Un asset provisoire porte `_PLACEHOLDER` dans son nom.

| Pack | Auteur | Source | Licence | Utilisé pour |
| --- | --- | --- | --- | --- |
| Roguelike City Pack | Kenney (kenney.nl) | miroir GitHub public `shorepine/kenney` (`2d/Roguelike City Pack/Tiles`) | CC0 1.0 | `tilesets/valcendre.png` : sols, routes, trottoirs, toits, façades, portes et fenêtres, arbres, voitures, débris |
| RPG Urban Pack | Kenney (kenney.nl) | miroir GitHub public `shorepine/kenney` (`2d/RPG Urban Pack/Tiles`) | CC0 1.0 | `sprites/survivor*.png` : 4 personnages jouables |

Provenance : kenney.nl était inaccessible depuis l'environnement de développement ; les fichiers ont été
pris sur le miroir GitHub `shorepine/kenney`, dont le `LICENSE.txt` reprend la licence CC0 de Kenney.
Créditer Kenney n'est pas obligatoire (CC0) mais nous le faisons.

## Fichiers générés

Tout est produit par `tools/assets/build_assets.py` (déterministe, sorties versionnées) :

- `tilesets/valcendre.png` + `valcendre.tiles.json` : 172 tuiles 16 px, grille de 16 colonnes sans marge
  ni espacement. Le JSON donne nom → index local, la tuile d'origine (`city:NNNN`) et la couverture.
  Les tuiles du décor reçoivent un étalonnage « post-apo » (verts tirés vers l'olive, désaturation 38 %,
  luminosité 78 %, léger virage cendre). Quelques tuiles sont **dérivées** (composées à partir de tuiles
  CC0) : `solid` (marqueur du calque collision), `grass_dark_*` (sous-bois), `road_weeds_*` et
  `sidewalk_weeds` (herbe qui perce l'asphalte).
- `sprites/survivor.png`, `survivor_b`, `survivor_c`, `survivor_d` (+ `.json`) : 3 × 4 cadres de 16 px,
  couleurs d'origine (pas d'étalonnage, pour que les joueurs ressortent sur le décor sombre).

Régénérer : `python3 -I tools/assets/build_assets.py [dossier 2d des packs Kenney]`
(`--check` pour vérifier que les fichiers versionnés sont à jour).
