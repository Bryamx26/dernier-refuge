# QA — Phase 3 (zombies, combat, loot, inventaire, survie)

Date : 2026-11-11 · branche `claude/project-thread-lrc1fh` (PR #3).

## Verdict

**Phase 3 fonctionnelle de bout en bout** sur une pile réelle (Postgres 16, Redis, uvicorn, Vite,
Chromium). Les cinq étapes du découpage sont livrées. Restent des limites assumées (plus bas).
`docker compose up` n'a toujours pas pu être lancé ici (registres Docker inaccessibles) ; l'image
serveur copie désormais `content/`.

## Commandes

| Commande | Résultat |
| --- | --- |
| `python tools/codegen/generate.py --check` | code 0 (protocole v3) |
| `uv run ruff check .`, `ruff format --check .`, `mypy app` | OK |
| `uv run pytest -q` (server) | 177 tests OK, dont 21 nouveaux dans `tests/zone/test_gameplay.py` |
| `uv run pytest tools/tests -q` | 18 OK |
| `python3 -I tools/assets/build_assets.py --check <kenney/2d>` | code 0 |
| `npm run lint`, `typecheck`, `test`, `build` (client) | OK, 97 tests Vitest |
| `e2e`, `npm test` (phases 1, 2 et 3) | 10 tests OK, dont latence 150 ms avec `DR_E2E_LAG_BASE_URL` |

## Couverture des tests serveur (`test_gameplay.py`)

Contenu valide et refus d'un contenu invalide ; inventaire (piles, emplacements, poids, JSON, entrées
corrompues) ; lancer de rayon, ligne de vue, champ de distances ; zombie qui voit devant mais pas
derrière un mur ni dans son dos, qui entend un tir, contourne un mur pour attaquer, tue un joueur
(inventaire lâché, réapparition), abandonne au-delà de sa laisse, rentre chez lui en contournant un
mur ; placement déterministe loin des points d'apparition ; pistolet arrêté par un mur, chargeur vide
puis rechargement, mêlée limitée à l'arc, arme qui casse ; fouille puis bâtiment vide, fouille annulée
en bougeant, jeter et ramasser ; faim, soif, déshydratation, saignement, bandage ; coût d'un tick sur
Valcendre peuplée (8 joueurs, 45 zombies) sous 10 ms.

## Essais dans le navigateur

- Combat au couteau contre les rôdeurs de la route de l'ouest : coups, impacts, cadavre couché, sang au
  sol, saignement signalé et soigné au bandage.
- Fouille de la maison du notaire : barre de progression, puis « Trouvé : Batte de baseball, Conserve de
  haricots, Bouteille d'eau » ; inventaire mis à jour.
- Captures (1280 × 800, échelle 2) : `/mnt/project-files/phase-3/01-combat-zombies.png`,
  `02-fouille.png`, `03-inventaire-butin.png`.

## Corrigé pendant les essais

| Problème | Correction |
| --- | --- |
| Les effets des coups (`swing`, `hit`) étaient effacés avant l'envoi | La zone vide les effets après envoi ; test de non-régression `test_attack_fx_and_game_messages_reach_the_client` |
| Un nouveau joueur mourait en quelques secondes, aux poings | Couteau de départ en main, poings à 9 dégâts, rôdeur à 8 dégâts toutes les 1,5 s |
| Un zombie bloqué en rentrant s'installait sur place, jusqu'à camper la place du village | Retour par champ de distances vers l'origine, plus d'installation |
| Groupe de la route de l'ouest à 11 tuiles des points d'apparition | `spawn_safe_radius: 18` dans `content/zones/valcendre.yaml`, groupe décalé vers l'ouest |
| QA-P2-03 : nouveaux personnages empilés en (64, 64) | Point d'apparition tiré au hasard pour un personnage jamais entré dans le monde |

## Limites connues (à reprendre)

1. **Pas d'intérieurs** : on fouille à la porte, on n'entre pas. Les intérieurs (portes, toits masqués)
   demandent de régénérer la carte ; à planifier avec la phase monde.
2. Un seul type de zombie et pas de JcJ (Valcendre est une zone non JcJ).
3. La faim et la soif ne ralentissent pas le joueur (la prédiction client resterait exacte, mais le
   contrat de déplacement devrait changer) : prévu avec les compétences.
4. Les bâtiments fouillés et les objets au sol ne sont pas persistés : ils repartent à zéro au redémarrage
   du serveur. Les zombies aussi.
5. QA-P2-02 (noms visibles au-dessus des toits) toujours ouvert ; sans intérieurs, l'effet reste limité.
6. Équilibrage à affiner en jouant : dégâts, nombre de zombies (45), vitesse de poursuite (3,3 t/s,
   plus rapide que la marche, plus lente que le sprint).
