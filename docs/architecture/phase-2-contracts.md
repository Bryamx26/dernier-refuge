# Phase 2 — contrats entre modules (prototype jouable)

Rédigé par l'Architecte avant l'implémentation. Objectif : une carte, un personnage animé, des
collisions, une caméra, plusieurs joueurs synchronisés dans la zone `valcendre`.

## Protocole v2 (`shared/protocol/protocol.json`, types déjà générés)

- `welcome` gagne `entity_id` (l'entité du joueur dans les snapshots) et `map_id`.
- C→S `input` : `move_x`, `move_y` ∈ [-1, 1], `aim` (radians), `sprint`. **Un message = un pas de simulation
  de durée fixe `dt = 1 / tick_rate`**. Le client en envoie un par pas (20/s). Le `seq` de l'enveloppe
  est le numéro d'entrée.
- S→C `snapshot` : `ack_seq` (dernier `seq` d'entrée appliqué pour ce joueur, 0 sinon) + `entities`
  (`EntityState` : id, kind=`player`, name, x, y, aim, anim ∈ idle/walk/run) dans un rayon de
  `interest_radius` tuiles autour du joueur, **lui compris**. Envoyé à chaque tick. Une entité absente
  n'est plus visible. Snapshots complets en phase 2 ; les deltas viendront en phase 7.

## Déplacement partagé (`shared/movement/movement.json`)

Constantes : `walk_speed` 3,0 et `sprint_speed` 5,0 tuiles/s, `player_half_size` 0,3 (boîte AABB
0,6 × 0,6 tuile centrée sur la position), `max_inputs_per_tick` 3, `interest_radius` 32.

Algorithme `step(pos, input, grid, cfg, dt) -> pos`, identique en Python (autorité) et en TypeScript
(prédiction), fonction pure :

1. Borner `move_x`, `move_y` à [-1, 1] ; si la norme dépasse 1, normaliser.
2. `speed = sprint ? sprint_speed : walk_speed` ; `dx = move_x * speed * dt` ; `dy = move_y * speed * dt`.
3. Déplacer sur X puis résoudre les collisions sur X contre les tuiles solides ; puis Y de même.
   Une tuile hors carte est solide. En cas de contact, la boîte est replacée exactement contre le bord
   de la tuile. Le détail exact (comparaisons, epsilon) est fixé par l'implémentation Python et
   **verrouillé par les fixtures**.

`shared/fixtures/movement.json` (produit par un script Python du serveur, versionné) : une liste de
cas `{ name, grid: string[] ('#' solide, '.' libre), start: {x, y}, dt, inputs: [...], expected: [{x, y}, …] }`
couvrant : déplacement libre, diagonale normalisée, sprint, mur sur chaque axe, coin, glissement le long
d'un mur, bord de carte, entrée hors bornes. Le serveur ET le client exécutent tous les cas ; tolérance
1e-9 tuile.

Côté serveur, à chaque tick et pour chaque joueur, au plus `max_inputs_per_tick` entrées en file sont
appliquées (anti-accélération) ; l'excédent reste en file (file bornée à 64, au-delà les plus anciennes
sont jetées).

## Carte (`maps/valcendre.tmj`, format JSON Tiled, généré par `tools/mapgen/`)

- Orthogonale, tuiles de 16 px, **128 × 128** tuiles, tilesets **intégrés** (pas de `.tsx` externe),
  données de calques en tableaux non compressés.
- Calques de tuiles, dans cet ordre : `ground`, `decor`, `above` (dessiné au-dessus des personnages :
  toits, cimes), et `collision` (non affiché) : toute tuile non nulle de `collision` est solide.
- Calque d'objets `spawns` : objets ponctuels de `type` `player_spawn` (au moins 8, en pixels Tiled).
- Calque d'objets `buildings` (masqué, ajouté par le World Designer, validé) : rectangle de chaque bâtiment avec `door_x`, `door_y` pour les portes de la phase 3.
- Contenu : le village de Valcendre (8 à 10 bâtiments fermés, routes, trottoirs), une forêt au nord-ouest,
  deux routes qui sortent de la carte, bords de carte infranchissables. Pas de bâtiments explorables
  à l'intérieur en phase 2 (portes en phase 3).
- Tileset unique `valcendre` : image `assets/tilesets/valcendre.png`, tuiles 16 px sans marge ni espacement.

## Assets (`assets/`, packs Kenney CC0)

| Fichier | Contenu |
| --- | --- |
| `assets/tilesets/valcendre.png` | Tuiles retenues du Roguelike City Pack (et RPG Urban Pack si besoin) |
| `assets/sprites/survivor.png` + `survivor.json` | Spritesheet d'un survivant (RPG Urban Pack) : 4 directions × 3 images de marche, 16 × 16 px ; le JSON décrit cadres et animations |
| `assets/CREDITS.md` | Pack, auteur, licence, provenance |

## Service des fichiers de jeu au client

Le client charge `GET /game/maps/<map_id>.tmj`, `/game/assets/tilesets/valcendre.png`,
`/game/assets/sprites/survivor.{png,json}`. En dev, Vite sert `maps/` et `assets/` de la racine du dépôt
sous `/game/` ; au build, ils sont copiés dans `dist/game/`. Le serveur lit `maps/valcendre.tmj` depuis
le disque (chemin `zones.map_file` relatif à la racine du dépôt, configurable par `DR_GAME_DATA_DIR`).

## Serveur de zone

- À l'ouverture du WebSocket : charger le personnage **et son compte** (refuser 4001 si compte suspendu
  ou personnage mort), créer son entité à la position enregistrée (ou au `player_spawn` le plus proche
  si la position est dans un mur).
- Envoi non bloquant : chaque session a une file sortante bornée et une tâche d'écriture ; si la file
  déborde (client trop lent), fermeture avec le code **4009** (nouveau).
- À la déconnexion et toutes les 30 s : sauvegarde de `x`, `y`, `facing` en base.

## Client

- Phaser : carte, caméra qui suit le joueur (zoom entier, rendu pixel net), sprite animé selon `anim`
  et la direction, nom au-dessus des autres joueurs, calque `above` au-dessus des personnages.
- Clavier : ZQSD **et** WASD et flèches, Maj = sprint ; orientation vers la souris.
- Prédiction locale avec `step()` partagé, réconciliation sur `ack_seq` (rejouer les entrées non
  acquittées), interpolation des autres joueurs avec 100 ms de retard.
- HUD : ping, tick, position, joueurs visibles.

## Critères de validation (plan, phase 2)

- Deux navigateurs voient le mouvement l'un de l'autre (test Playwright).
- Aucun passage à travers les murs côté serveur.
- À 150 ms de latence simulée, le joueur local reste fluide et l'écart après réconciliation est < 0,25 tuile.
- Les fixtures de déplacement passent en TypeScript et en Python.
