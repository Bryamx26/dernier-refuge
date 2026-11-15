# Système de personnages modulaires (paper doll)

État : étapes 1 à 7 posées, **en attente de validation de l'alignement** avant toute production en série.
Tout est généré par `tools/assets/character.py` (création originale, aucun asset externe).

## Règles d'alignement

- Canvas unique de **64 × 64 px** pour le corps et tous les équipements, origine (0, 0) en haut à gauche.
- Le personnage est de profil, tourné vers la droite ; la gauche s'obtient par miroir horizontal du canvas.
- Les pieds finissent en y = 55, la ligne de sol (contour) est en y = 56 ; le pivot du sprite est (32, 56).
- Aucun recadrage, aucun redimensionnement : un PNG se pose tel quel sur le corps.
- Un équipement est **calculé à partir des formes du corps** (mêmes coordonnées), pas dessiné à part.

## Points d'ancrage

Définis dans `ANCHORS` et exportés dans `assets/characters/character.config.json` :
tête, cou, épaules (proche / éloignée), torse, dos, bassin, mains, pieds, sol.

## Sous-calques et ordre de rendu

Chaque élément (corps ou équipement) fournit de 1 à 3 PNG : `back` (derrière le corps : bras et jambe
éloignés), `mid` (tronc, tête, jambe proche), `front` (bras proche). L'ordre complet est dans
`render_order` du fichier de configuration, par exemple une veste = manche éloignée (`torso:back`),
tronc (`torso:mid`), manche proche (`torso:front`).

## Ajouter un équipement

1. Écrire une fonction `draw_xxx()` qui renvoie ses sous-calques à partir de `body_parts()`.
2. L'inscrire dans `ITEMS` (catégorie, membres couverts, dépendances `requires` / `hides` / `conflicts`).
3. `python3 -I tools/assets/character.py --check` : tailles, ordre de rendu, membres entièrement couverts,
   aucune peau visible sous le vêtement, silhouette sans trou.
4. `python3 -I tools/assets/character.py` : écrit les PNG et régénère la configuration.

## Arborescence

```
assets/characters/
  character.config.json
  base/body.png  body_back.png  body_mid.png  body_front.png
  equipment/head/  torso/  legs/  feet/  back/  hands/  weapons/
```
