# Phase 3 — contrats entre modules (zombies, combat, loot, inventaire, survie)

Rédigé par l'Architecte avant l'implémentation, mis à jour après les essais. Objectif : le MVP
jouable, un village peuplé de zombies où l'on fouille, se bat et survit.

## Découpage

| Étape | Contenu | État |
| --- | --- | --- |
| 3.1 Zombies | Un type (`rodeur`), IA serveur : errance, vue (cône, murs), proximité, ouïe, poursuite qui contourne les murs, attaque, recherche, retour à l'origine ; réapparition | fait |
| 3.2 Combat et armes | Poings, couteau, batte, pistolet, fusil à pompe : dégâts, portée, arc ou dispersion, cadence, usure, chargeur, rechargement ; le bruit attire les zombies | fait |
| 3.3 Loot et inventaire | Fouille des bâtiments à la porte, objets au sol, inventaire à emplacements, piles et poids, équipement, sauvegarde | fait |
| 3.4 Survie | Santé, faim, soif, saignement, nourriture, boissons, bandages, mort et réapparition | fait |
| 3.5 QA | Tests unitaires et Playwright, défauts reportés de la phase 2 | voir `docs/qa/phase-3.md` |

## Contenu (`content/`, YAML validé au démarrage par `server/app/content/`)

| Fichier | Contenu |
| --- | --- |
| `items.yaml` | Objets : `kind` (melee, firearm, ammo, food, drink, medical), poids, pile ; statistiques d'arme (`melee` / `firearm`) ; effets (`consume`) ; `unarmed` (poings) |
| `zombies.yaml` | Types de zombies (santé, vitesses, vue, ouïe, attaque, laisse…) et bruit des pas du joueur |
| `loot.yaml` | Durée de fouille, portée, réapprovisionnement ; nom de bâtiment → table ; tables pondérées |
| `survival.yaml` | Jauges, vitesses de faim et soif, dégâts, régénération, inventaire (emplacements, poids), équipement de départ |
| `zones/<id>.yaml` | Peuplement : graine, groupes de zombies (rectangles), réapparition, rayon protégé autour des points d'apparition |

Un fichier invalide ou une référence inconnue (objet, table, type) empêche le démarrage du serveur.

## Protocole v3 (`shared/protocol/protocol.json`)

- `EntityState` : `kind` ∈ `player`, `zombie`, `item` ; `anim` gagne `attack` et `dead` ; nouveau
  champ `health` (0 à 1). Un objet au sol est une entité `item` dont `name` est le nom affiché.
- C→S `input` gagne `attack` (gâchette tenue pendant ce pas). Le serveur applique la cadence de l'arme.
- C→S `action` `{kind, slot}` : `interact` (ramasser l'objet au sol le plus proche, sinon fouiller le
  bâtiment dont la porte est à portée), `use` (équiper / ranger une arme, consommer), `drop`, `reload`,
  `respawn`. Mise en file (16 au plus) et traitée au tick suivant.
- S→C `vitals` (santé, faim, soif, saignement, mort, action longue et son avancement) : à chaque
  changement et toutes les 10 ticks. `inventory` : à chaque changement. `notice` : message court.
  `fx` : effets du tick (`shot`, `swing`, `hit`, `blood`, `search`) dans le rayon d'intérêt.

## Règles serveur (`server/app/zone/gameplay.py`, `zombies.py`, `geometry.py`, `inventory.py`)

- Tirs : lancer de rayon exact sur la grille (DDA) ; un projectile s'arrête au premier mur ou au premier
  zombie. Mêlée : zombie vivant le plus proche dans l'arc et la portée. Les joueurs ne se blessent pas
  entre eux (Valcendre n'est pas JcJ).
- Vue des zombies : ligne de vue sur la grille de collision. Poursuite hors de vue : champ de
  distances (parcours en largeur, rayon 24, recalculé au plus toutes les 10 ticks par cible) pendant
  5 s, puis recherche à la dernière position connue, puis retour (champ de distances vers l'origine).
- Un mort ne bouge plus (ses entrées sont acquittées sans effet) ; il lâche tout son inventaire au sol.
  `respawn` : jauges pleines, équipement de départ, point d'apparition tiré au hasard.
- Un nouveau personnage (`characters.inventory` NULL) apparaît sur un point d'apparition tiré au
  hasard et reçoit l'équipement de départ (corrige QA-P2-03).
- Le déplacement du joueur n'est pas modifié par la survie (pas de ralentissement) : la prédiction
  client reste exacte. Les malus de mouvement arriveront avec les compétences.

## Persistance (migration `0002`)

`characters` gagne `health`, `hunger`, `thirst`, `bleeding`, `inventory` (JSON, NULL = jamais entré
dans le monde). Sauvegardés avec la position à la déconnexion, toutes les 30 s et à l'arrêt.

## Client

- Phaser : zombies (sprite dérivé CC0), objets au sol (carton) avec nom à moins de 2 tuiles, morts
  couchés, barres de vie des zombies blessés, traçantes, coups, impacts, sang au sol.
- Commandes : clic gauche frapper/tirer, E fouiller/ramasser, R recharger, 1 à 9 utiliser
  l'emplacement, I ou Tab inventaire.
- React : panneau Survie (jauges, saignement, arme et munitions), barre d'action, inventaire
  (Équiper/Ranger, Manger, Boire, Soigner, Jeter), messages, écran de mort avec « Réapparaître ».
