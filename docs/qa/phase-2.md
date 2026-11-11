# QA — Phase 2 (prototype jouable)

Date : 2026-11-11 · branche `phase-2-prototype` (non commitée) · agent QA.

## Verdict

> **Mise à jour après correctif** : QA-P2-01 est corrigé (tricheur limité à 5,50 t/s sur 1 s), et la
> réconciliation reste à 0,00 tuile, y compris avec de la gigue. Le correctif introduit QA-P2-08
> (moyenne) : après un gel réseau, le retard d'entrées n'est plus jamais rattrapé. Voir « Après correctif ».

**Phase 2 validée sous réserve d'un correctif serveur (QA-P2-01, gravité haute)**. Les quatre critères du
plan sont respectés et mesurés en navigateur réel, et la phase 1 ne régresse pas. Mais le test du tricheur
montre qu'un client modifié peut se déplacer **3 fois plus vite que le sprint** (15 tuiles/s), en rafale
comme en continu. C'est un trou du contrat (`max_inputs_per_tick = 3` sans budget de temps), pas une
erreur d'implémentation. Je recommande de le corriger avant la phase 3 ; le test
`tricheur : 100 entrées…` est rouge tant que ce n'est pas fait.

## Critères du plan

| Critère | Résultat | Preuve |
| --- | --- | --- |
| Deux navigateurs voient le mouvement l'un de l'autre | **OK** | e2e `phase2` #1 : A maintient D 1,5 s → serveur (observateur WebSocket) : +4,5 tuiles en x, y inchangé ; le HUD de A = la position serveur (±0,05) ; les trames WebSocket reçues par **le navigateur de B** contiennent ≥ 20 états de A, progressifs, en `walk`, dont le dernier = la position serveur. Inversement, B monte de 3 tuiles (W 1 s), et A reçoit la position finale de B. « Joueurs » = 3 sur les deux HUD. Captures `phase2-01`, `phase2-02` |
| Aucun passage à travers les murs côté serveur | **OK** | e2e `phase2` #2 : sprint et marche contre le bâtiment au sud du point d'apparition pendant 11 s (poussée, glissement est et ouest, coin, ruelle, remontée vers le bâtiment nord) ; ≥ 150 positions serveur, **0 boîte recouvrant une case solide** du calque `collision` de `maps/valcendre.tmj` ; poussé contre le mur, `y = 67,7` exactement (bord = 68). Même vérification sur tous les snapshots des tests #1, #4 (tricheur à 15 t/s) : 0 violation. Vitesse d'un client honnête sur 1 s ≤ 5,5 t/s |
| À 150 ms de latence, le joueur local reste fluide et l'écart après réconciliation est < 0,25 tuile | **OK** | e2e `phase2` #5 avec le proxy TCP `e2e/tools/latency-proxy.cjs` (75 ms par sens). Parcours de ~11 s : marche, sprint, demi-tour, poussée contre un mur, zigzag contre le mur. Erreur de correction du HUD relevée toutes les 100 ms (121 échantillons) : **max 0,00 tuile**. Aucun saut de position : le déplacement maximal entre deux échantillons est de 1,32 tuile, toujours sous la limite du sprint (marge -0,26 tuile). Même résultat à **300 ms** de RTT (0,00 t) et à 150 ms avec **±40 ms de gigue** par sens (0,00 t) |
| Fixtures de déplacement en TypeScript et en Python | **OK** | `shared/fixtures/movement.json` : 19 cas, 189 pas (libre, diagonale, sprint, murs sur chaque axe, coin, glissement, bord de carte, entrée hors bornes, couloir, sortie de mur, grand `dt`). `uv run python -m app.zone.movement_fixtures --check` → code 0 ; pytest `-k fixture` : 21 tests OK ; vitest `src/game/movement/step.test.ts` : 24 tests OK (tous les cas, tolérance 1e-9) |
| Non-régression phase 1 | **OK** | `e2e/tests/phase1.test.cjs` 2/2 OK (suite complète `npm test`) |

Mesures de latence (une ligne par exécution du test #5) :

| Latence ajoutée (proxy) | Ping HUD | Correction max | Saut max entre échantillons | Images/s |
| --- | --- | --- | --- | --- |
| 0 ms (5173, référence) | 34–44 ms | 0,00 t | — | ~20 |
| 150 ms RTT (75 ms par sens) | 206–228 ms | **0,00 t** | 1,32 t (limite 1,6) | ~20 |
| 150 ms RTT, gigue 0–40 ms par sens | 248 ms | 0,00 t ⚠ mesure invalide (bogue du proxy, voir « Après correctif ») | 1,30 t | ~20 |
| 300 ms RTT (150 ms par sens) | 381 ms | **0,00 t** | 1,30 t | ~20 |

Le ping brut du proxy, mesuré par un client Node, est de 150–153 ms. Le surplus affiché par le HUD
(+40 à +80 ms) vient du fil principal du Chromium headless, saturé par le rendu logiciel (WebGL sans GPU,
4 CPU). Pour la même raison, le rendu plafonne à ~20 images/s **avec ou sans latence** : la latence ne
dégrade pas la fluidité. Mais ce chiffre ne représente pas un vrai poste ; il faudra mesurer les images/s
sur une machine avec GPU.

Pourquoi l'erreur reste à 0 : la prédiction et le serveur exécutent le même `step()` sur la même grille,
et chaque entrée est acquittée individuellement. Une correction n'apparaît que si le serveur jette des
entrées (file de 64 pleine) ou en cas de triche. Le HUD affiche le maximum sur 3 s, au centième près, et
il est rafraîchi toutes les 200 ms.

## Tricheur (client WebSocket Node)

| Sonde | Résultat |
| --- | --- |
| `move_x = 50`, `move_y = -1e308`, `aim = 100`, `sprint = 1`, `move_x = "1"`, champ `speed` en trop, `NaN`, `seq = -1` | 8 × `error bad_message`, position inchangée, `ack_seq = 0`, connexion conservée ✔ |
| Doublons et désordre (`seq` 10 puis 5 × `seq` 5) | un seul pas appliqué (+0,15 t) ✔ |
| **100 entrées de sprint d'un coup** | 60 acceptées, 40 `rate_limited` ; **15,00 t/s pendant 1 s** (3 pas par tick), 15 tuiles parcourues ✘ |
| **3 entrées de sprint toutes les 50 ms, en continu** (60 messages/s) | **15,0 t/s** sur une fenêtre de 1 s, **0 refus** (le seau de jetons autorise 60/s) ✘ |
| Murs pendant la triche | 0 chevauchement (le balayage tuile par tuile tient même à 0,75 t/tick) ✔ |

## Résultats exacts des commandes de la CI

Racine, jobs `contracts` et `content` :

| Commande | Résultat |
| --- | --- |
| `python tools/codegen/generate.py --check` | code 0 |
| `python3 tools/mapgen/generate_valcendre.py --check` | code 0 |
| `python3 tools/mapgen/check_map.py maps/valcendre.tmj` | `OK valcendre.tmj : 128x128, 9 spawns, 10 bâtiments, 13258 cases libres dont 13245 accessibles depuis les spawns` (code 0) |
| `uv run --project server pytest tools/tests -q` | `18 passed in 0.19s` |

`server/`, job `server` (uv, Python 3.13 local ; la CI utilise 3.12) :

| Commande | Résultat |
| --- | --- |
| `uv sync --frozen` | `Checked 51 packages` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | `50 files already formatted` |
| `uv run mypy app` | `Success: no issues found in 31 source files` |
| `uv run python -m app.zone.movement_fixtures --check` | code 0 |
| `uv run pytest -q` (Postgres 16, `DR_TEST_DATABASE_URL=…@127.0.0.1:55432/refuge_test`) | `153 passed, 1 warning in 10.57s` |
| `uv run pytest -q` (SQLite) | `153 passed, 1 warning in 9.86s` |

Avertissement unique : `StarletteDeprecationWarning` (httpx + TestClient), déjà connu en phase 1.

`client/`, job `client` (Node 22.23) :

| Commande | Résultat |
| --- | --- |
| `npm ci` | code 0 ; `npm audit` : 10 vulnérabilités (8 modérées, 2 critiques, dépendances de dev, inchangé depuis la phase 1) |
| `npm run lint` | code 0 |
| `npm run typecheck` | code 0 |
| `npm run test` | `Test Files 14 passed (14)`, `Tests 94 passed (94)` |
| `npm run build` | code 0 ; `phaser` 1 208 kB (332 kB gzip), `index` 176,6 kB, `createGame` 13 kB ; `dist/game/maps/valcendre.tmj` et `dist/game/assets/` bien copiés |

## Bout en bout

Pile réelle :
- Postgres 16 (port 55432) ;
- `redis-server --port 56379` ;
- `alembic upgrade head` (`-> 0001`) ;
- `uvicorn app.main:app --port 8000` avec `DR_AUTH_RATE_LIMIT_PER_MINUTE=1000` (sinon la suite se heurte à
  la limite de 20 inscriptions ou connexions par minute et par IP dès qu'elle est relancée) ;
- `npm run dev` (5173) ;
- un second Vite (5174) dont `VITE_PROXY_TARGET=http://localhost:8150` vise le proxy de latence.

`/api/health` → `{"status":"ok","database":true,"redis":true}`.

`npm test` (suite complète, sans la variable de latence) : 7 tests, **5 OK, 1 KO (QA-P2-01 attendu), 1 ignoré** (latence).
Avec `DR_E2E_LAG_BASE_URL=http://localhost:5174`, le test de latence est **OK**.

| # | Test | Résultat |
| --- | --- | --- |
| phase1 #1 | parcours inscription → zone | OK |
| phase1 #2 | deux navigateurs, `online = 2` | OK |
| phase2 #1 | deux navigateurs voient le mouvement l'un de l'autre | OK |
| phase2 #2 | mur (sprint, glissement, coin) | OK |
| phase2 #3 | tricheur : entrées invalides, doublons | OK |
| phase2 #4 | tricheur : 100 entrées → vitesse ≤ 5,5 t/s | **KO : 15,00 t/s** (QA-P2-01) |
| phase2 #5 | latence 150 ms : correction < 0,25 t, pas de saut | OK (0,00 t) |

Sondes du plugin Vite `client/vite-plugins/gameData.ts` (traversée de chemin) : `..%2f..`, `../../`,
`%2e%2e`, `%00`, `maps%2f..` → 404 ; `/@fs/…/server/…` et `/@fs/etc/passwd` → 403 (seul `shared/` est
autorisé) ; `maps/valcendre.tmj%3F..%2f..%2fREADME.md` → 200 mais résout vers `maps/README.md`, toujours
dans le dossier. **Aucune traversée.**

## Captures (`/mnt/project-files/phase-2/`, 1280 × 800, deviceScaleFactor 2)

- `phase2-01-deux-joueurs-vue-B.png` : B (au centre), A et l'observateur sur la route, nommés.
- `phase2-02-deux-joueurs-vue-A.png` : A (au centre), B nommé au-dessus.
- `phase2-03-joueur-contre-batiment.png` : joueur poussé contre la façade nord d'un bâtiment (y = 67,7).

Ce que j'ai vu sur les captures :
- **Bon** : les noms sont lisibles (police terminal, contour noir), le HUD est net, le voile et la vignette
  posent l'ambiance sans masquer le jeu, le rendu est pixel net au zoom 3.
- Les toits sont des **aplats brun ou gris uniformes** de 9 × 10 tuiles, sans texture, sans arête ni porte.
  À l'écran, c'est le plus gros élément et le moins lisible (QA-P2-06).
- Contre la façade nord, le bas du sprite (environ 3 px) passe sous le calque `above` : les pieds sont
  coupés au bord du toit. C'est cohérent avec une vue de trois quarts, mais un peu abrupt (QA-P2-07).
- Plusieurs joueurs partagent la même variante de sprite. Le joueur local n'a aucun marqueur et ne se
  distingue d'un autre que par l'absence de nom (QA-P2-05).
- Les nouveaux personnages apparaissent tous en (64, 64), sur la ligne jaune de la route, empilés (QA-P2-03).

## Problèmes, par gravité

### Haute

- **QA-P2-01 — speed hack ×3 (contrat).**
  - Où : `server/app/zone/runtime.py:228`. La boucle applique jusqu'à `max_inputs_per_tick` (3) entrées
    par tick, sans budget de temps. Avec `server/app/zone/session.py:348-349`, le débit de 60 messages/s
    et la rafale de 60 laissent passer 3 entrées par tick **en continu**.
  - Effet : un client modifié se déplace à 15 t/s au lieu de 5 t/s, sans aucun refus du serveur. Les murs
    tiennent quand même.
  - Origine : la règle vient de `docs/architecture/phase-2-contracts.md` (« anti-accélération »). Elle
    borne la rafale, pas la moyenne.
  - Piste de correction (Architecte, puis Serveur) : un crédit d'entrées par joueur, +1 par tick et
    plafonné à 3. Le rattrapage reste possible après une gigue, mais la moyenne ne dépasse plus 1 pas par
    tick. On peut aussi abaisser le débit autorisé pour les `input`, à environ 25/s.
  - Test : `e2e/tests/phase2.test.cjs`, « tricheur : 100 entrées… ».

### Moyenne

- **QA-P2-02 — noms affichés au-dessus des toits.**
  - Où : `client/src/game/scenes/WorldScene.ts:254-265` et `:283-290`. Les étiquettes vivent sur la
    caméra d'interface, au-dessus de tout, calque `above` compris.
  - Effet : un joueur caché sous un toit ou une cime reste repéré par son nom. Sans conséquence en
    phase 2, mais ce sera une fuite d'information dès les intérieurs (phase 3) et le JcJ.
  - Piste : masquer l'étiquette quand une tuile `above` non vide couvre le sprite.

### Faible

- **QA-P2-03 — point d'apparition des nouveaux personnages.**
  - Où : `server/app/api/characters.py:52`. Les nouveaux personnages apparaissent en
    `zones.spawn_x/spawn_y` (64, 64), une position libre au milieu de la route.
  - Effet : les points `player_spawn` de la carte (58,5–64,5 × 50,5–56,5) ne servent que si la position
    est dans un mur, et tous les nouveaux joueurs sont empilés au même endroit.
  - Piste : créer le personnage sans position (null) pour que `resolve_spawn` choisisse un `player_spawn`.
- **QA-P2-04 — animation locale différente de celle vue par les autres.**
  - Où : `client/src/net/ZoneClient.ts:151-157`. L'animation locale se déduit de l'intention (touche
    enfoncée), pas du mouvement réel.
  - Effet : contre un mur, le joueur se voit marcher sur place alors que les autres le voient `idle`
    (règle serveur).
  - Piste : déduire l'animation du déplacement prédit.
- **QA-P2-05 — joueurs difficiles à distinguer.** Les variantes de sprite se répètent (`variantForId`)
  et le joueur local n'a pas de marqueur (anneau au sol, couleur).
- **QA-P2-06 — toits peu lisibles.** Ce sont des aplats uniformes (carte et tileset, World Designer).
- **QA-P2-07 — pieds coupés contre une façade nord.** Le sprite passe sous le calque `above` (voir
  capture 03). Cosmétique.

### Environnement de test (pas des défauts du dépôt)

- `/tmp/claude-0` est remis en mode 700 par l'environnement pendant la session. Postgres, qui tourne sous
  l'utilisateur `postgres`, a perdu l'accès à son dossier de données (`could not stat data directory …
  Permission denied`) et s'est arrêté. Ses données ont été déplacées dans `/tmp/dr-qa2/pgdata`.
- Chromium headless rend sans GPU : ~20 images/s et un ping HUD gonflé de 30 à 80 ms (voir plus haut).
- La limite `DR_AUTH_RATE_LIMIT_PER_MINUTE` (20 par défaut) fait échouer la suite si on la relance dans
  la minute. Pour un serveur de test, il faut la relever.

## Après correctif (QA-P2-01)

Correctif de l'Architecte dans `server/app/zone/runtime.py` : un crédit d'entrées par joueur. Il gagne
+1 par tick, plafonné à `max_inputs_per_tick` (3), et chaque entrée appliquée coûte 1. Le joueur démarre
avec le plafond plein. Pile relancée à l'identique, puis suite e2e complète rejouée avec
`DR_E2E_LAG_BASE_URL=http://localhost:5174`.

### Correction de l'outil de mesure

Avec de la gigue, `e2e/tools/latency-proxy.cjs` pouvait **réordonner des chunks TCP**. Il armait un
minuteur par chunk, et des minuteurs indépendants peuvent se déclencher dans le désordre. Le flux
WebSocket était alors corrompu : des trames JSON tronquées ont été observées dans le navigateur, avec une
« correction » de 5,11 t qui n'était due qu'au proxy. Le proxy utilise désormais une file FIFO par sens
et un seul minuteur. La mesure « gigue 40 ms » du tableau précédent est donc à ignorer ; elle est
remplacée ci-dessous. Les mesures sans gigue n'étaient pas affectées.

### Résultats

`npm test` complet (latence activée) : **8 tests, 7 OK, 1 KO**. Le KO est le nouveau test de gel réseau
(QA-P2-08, ci-dessous).

| Test | Avant | Après |
| --- | --- | --- |
| phase1 #1, #2 | OK | OK |
| phase2 #1 à #3 (deux navigateurs, mur, entrées invalides) | OK | OK (mur : client honnête ≤ 5,5 t/s, 0 chevauchement) |
| phase2 #4 tricheur (100 entrées d'un coup) | KO, 15,00 t/s | **OK, 5,50 t/s** sur 1 s : 3 pas au premier tick, puis 1 par tick. Max sur un tick : 15 t/s, un seul tick. 13 tuiles en 2,5 s. C'est exactement la borne du plafond (22 pas sur 20 ticks = sprint + 10 %) |
| phase2 #6 **gel réseau 1 s** (nouveau) | — | **KO** (QA-P2-08) |
| phase2 #7 latence 150 ms | 0,00 t | **0,00 t** |

Erreur de réconciliation max (HUD, relevé toutes les 100 ms, parcours de ~11 s), avec le crédit :

| Latence (proxy corrigé) | Ping HUD | Correction max | Excès de saut |
| --- | --- | --- | --- |
| 150 ms RTT | 255 ms | **0,00 t** | -0,07 t |
| 150 ms RTT, gigue 0–40 ms par sens (2 exécutions) | 232 / 262 ms | **0,00 t** / **0,00 t** | -0,05 / -0,24 t |
| 150 ms RTT, gigue 0–150 ms par sens | 422 ms | **0,00 t** | -0,28 t |
| 300 ms RTT | 389 ms | **0,00 t** | -0,28 t |

Sonde navigateur, zigzag de 20 s : le nombre d'entrées en vol (`seq` envoyé − `ack_seq` reçu) reste
**stable**. Il vaut 2 à 7 sans gigue ou à ±40 ms, et 11 à 17 avec des pics de 300 ms, sans dérive.
Le crédit n'a donc pas d'effet visible tant que les retards restent sous ~150 ms (plafond de 3).

### Nouveau problème

- **QA-P2-08 — Moyenne : le crédit empêche le rattrapage après un gel.**
  - Où : `server/app/zone/runtime.py`, `_apply_inputs` et `input_credit`.
  - Scénario : client honnête à 20 entrées/s ; ses envois sont bloqués 1 s, puis délivrés d'un coup (pic
    réseau, retransmission TCP, longue image côté navigateur).
  - Effet : le serveur rattrape 2 entrées, puis n'en applique plus qu'une par tick. Comme le client en
    envoie aussi une par tick, **~19 entrées (≈ 0,95 s) restent en file pour toute la session**. Mesures :
    retard de 0–2 avant le gel, 19–20 pendant les 10 s suivantes. Avant le correctif, la file se vidait
    en ~7 ticks.
  - Conséquences :
    - la position serveur, celle que voient les autres joueurs et celle qui servira au combat, est en
      retard d'autant ;
    - les gels s'additionnent jusqu'à la file de 64 entrées (3,2 s) ; au-delà, les entrées jetées
      provoquent des corrections visibles ;
    - la correction affichée au HUD reste à 0, donc le critère 3 ne détecte pas ce cas.
  - Test : `phase2.test.cjs`, « gel réseau de 1 s… » (rouge).
  - Piste : un budget **cumulé** depuis la connexion plutôt qu'un plafond de 3. Garder ≤ 3 entrées par
    tick, mais n'appliquer que si `entrées appliquées ≤ ticks écoulés depuis l'arrivée + marge` (par
    exemple 20 à 40 ticks). Un client qui n'a pas pu envoyer rattrape son retard, et un tricheur reste à
    1 pas par tick en moyenne sur toute la session. Il pourra au plus accumuler la marge en restant
    immobile, puis la dépenser à 3 pas par tick.

## Correctif final de l'Architecte (QA-P2-01 et QA-P2-08)

Le crédit par tick est remplacé par un **budget cumulé** (`server/app/zone/runtime.py`) : au plus 3 entrées
par tick, et depuis l'arrivée du joueur jamais plus de `ticks écoulés + 20` entrées appliquées
(`INPUT_CATCHUP_MARGIN`). Un client honnête ne consomme jamais la marge et rattrape un gel réseau ; un
tricheur ne gagne qu'une avance unique de 20 pas (1 s), puis reste à un pas par tick.

Rejeu complet de la suite e2e (phase 1 + phase 2, latence 150 ms activée) : **8/8 OK**.

| Mesure | Résultat |
| --- | --- |
| Tricheur, 100 entrées d'un coup | 60 acceptées, 40 `rate_limited`, distance dans le budget cumulé |
| Gel réseau de 1 s | retard d'entrées 1 avant le gel, 2 trois secondes après (rattrapé) |
| Latence 150 ms | correction max 0,00 tuile, aucun saut |

Tests unitaires ajoutés : `test_sustained_burst_is_bounded_by_cumulative_budget`,
`test_honest_client_catches_up_after_network_freeze`. Le test e2e du gel avait aussi un défaut
(lecture d'un snapshot avant le premier reçu), corrigé.
