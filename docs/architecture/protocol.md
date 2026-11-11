# Protocole WebSocket de zone (v3)

Source unique : [`shared/protocol/protocol.json`](../../shared/protocol/protocol.json). Les types
Python (`server/app/protocol/generated.py`) et TypeScript (`client/src/generated/protocol.ts`) en
sont générés par `tools/codegen/generate.py` ; ne les modifiez jamais à la main.

## Modèle d'exécution

- Le serveur est **autoritaire** : le client envoie des intentions, le serveur simule et diffuse
  le résultat.
- Chaque zone tourne dans une `ZoneRuntime` (`server/app/zone/runtime.py`) : une boucle asyncio à
  **pas fixe** de `tick_rate` Hz (20 par défaut, réglage `DR_TICK_RATE`). Les échéances sont
  calculées depuis l'origine (`origine + n × période`) : pas de dérive cumulée. Au-delà de
  5 ticks de retard, la boucle se resynchronise au lieu d'enchaîner des ticks en rafale.
- Les **messages de jeu** (`input`) sont mis en file dans la session du client (64 au plus ; au-delà
  les **plus anciens** sont jetés) et appliqués par la zone aux ticks suivants, dans l'ordre de
  réception, **au plus `max_inputs_per_tick` (3) par joueur et par tick** (anti-accélération) :
  l'excédent attend le tick suivant.
- Les **messages de transport** (`ping`) sont traités immédiatement par la passerelle, hors
  simulation.
- À chaque tick, après les entrées, chaque joueur reçoit un `snapshot`.
- **Envoi non bloquant** : chaque message serveur est sérialisé, numéroté et placé dans la file
  sortante de la session (64 messages au plus, ≈ 3 s de snapshots) ; une tâche d'écriture par
  session la vide vers le WebSocket. La boucle de tick n'attend jamais un client : si la file est
  pleine (client qui ne lit pas assez vite), elle est vidée et la connexion fermée en **4009**.

## Enveloppe

Tous les messages sont des trames **texte** JSON (les trames binaires sont décodées en UTF-8 et
soumises aux mêmes règles).

| Sens | Forme | Règles |
| --- | --- | --- |
| Client → serveur | `{"t": string, "seq": int, "d": object}` | exactement ces trois clés ; `t` connu ; `seq` entier ≥ 0 (pas un booléen), choisi par le client (croissant conseillé) ; `d` validé strictement (aucune conversion implicite, aucun champ en trop) ; 4096 octets au plus ; `NaN`/`Infinity` refusés |
| Serveur → client | `{"t": string, "seq": int, "tick": int, "d": object}` | `seq` commence à 1 et augmente de 1 à chaque message de la connexion ; `tick` est le tick de la zone au moment de l'envoi |

Côté serveur : `decode_client` / `encode_server` dans `server/app/protocol/codec.py`.

## Cycle de connexion

```
Client                          REST                          WebSocket /ws/zone/{zone_id}
  │ POST /api/zones/{id}/join ──►│ vérifie compte, personnage, zone
  │◄── { ticket, ws_path, expires_in }   (ticket Redis, usage unique, TTL 30 s)
  │ ws://…{ws_path}?ticket=… ──────────────────────────────────►│ accept
  │                                                              │ zone connue ?        sinon 4004
  │                                                              │ GETDEL du ticket,
  │                                                              │ même zone ?          sinon 4001
  │                                                              │ personnage vivant, compte non
  │                                                              │ suspendu, même zone ? sinon 4001
  │                                                              │ déjà connecté ?      sinon 4002
  │                                                              │ place libre ?        sinon 4003
  │◄──────────────────────────────────────────────────── welcome │ (entity_id, map_id)
  │◄─────────────────────────────────────── snapshot (chaque tick)│
  │ ping / input ──────────────────────────────────────────────►│
```

- Le ticket évite de placer le JWT dans l'URL du WebSocket. Il est consommé dès qu'il est lu,
  même si la connexion est ensuite refusée (4001 pour une autre zone, 4002, 4003) : il faut en
  redemander un. Seul le refus 4004 (zone inconnue) intervient avant sa consommation.
- Le serveur accepte toujours la poignée de main avant de vérifier : un refus avant `accept`
  apparaîtrait dans le navigateur comme un échec HTTP sans code de fermeture.
- L'entité du joueur apparaît à la position enregistrée du personnage ; si sa boîte y recoupe une
  tuile solide (ou le hors-carte), au point `player_spawn` libre le plus proche.
- À la déconnexion, la position (`x`, `y`, `facing` = dernier `aim`) est sauvegardée en base, puis la
  session est retirée de la zone (`online` de `GET /api/zones`). Les positions de tous les joueurs
  sont aussi sauvegardées en lot toutes les 30 s et à l'arrêt de la zone (tâche séparée du tick).

## Messages

### Client → serveur

| `t` | `d` | Traitement |
| --- | --- | --- |
| `ping` | `client_time` (ms, ≥ 0) | immédiat : réponse `pong` |
| `input` | `move_x`, `move_y` ∈ [-1, 1], `aim` ∈ [-7, 7] (radians), `sprint`, `attack` (gâchette tenue) | en file ; **un message = un pas de `1 / tick_rate` s** ; le `seq` de l'enveloppe est le numéro d'entrée |
| `action` | `kind` ∈ `interact`, `use`, `drop`, `reload`, `respawn` ; `slot` (-1 à 63) | file d'actions (16 au plus), traitée au tick suivant ; voir `phase-3-contracts.md` |

### Serveur → client

| `t` | `d` | Quand |
| --- | --- | --- |
| `welcome` | `protocol_version` (3), `zone_id`, `character_id`, `tick_rate`, `server_time` (ms epoch), `entity_id`, `map_id` | premier message après ouverture (`seq` 1) |
| `snapshot` | `ack_seq`, `entities: EntityState[]` | à chaque tick |
| `pong` | `client_time` (renvoyé tel quel), `server_time` | réponse à `ping` ; RTT = maintenant − `client_time` |
| `vitals` | `health`, `max_health`, `hunger`, `thirst`, `bleeding`, `dead`, `action`, `action_progress` | à chaque changement et toutes les 10 ticks |
| `inventory` | `slots: InventorySlot[]`, `capacity`, `equipped` (-1 : mains nues), `weight`, `max_weight` | à la connexion et à chaque changement |
| `fx` | `events: FxEvent[]` (`kind` ∈ shot, swing, hit, blood, search ; `x`, `y`, `x2`, `y2`) | effets du tick à moins de `interest_radius` |
| `notice` | `text` (≤ 120 caractères) | message court au joueur |
| `error` | `code`, `message` (≤ 200 caractères) | message refusé ; la connexion reste ouverte |

`EntityState` : `id` (ex. `p12`, `z4`, `i7`, stable pendant la connexion), `kind` (`player`, `zombie`,
`item`), `name` (≤ 32), `x`, `y` (tuiles, centre de la boîte), `aim` (radians), `anim` (`idle`, `walk`,
`run`, `attack`, `dead`), `health` (0 à 1). Un snapshot contient
toutes les entités dans un rayon de `interest_radius` (32) tuiles autour du joueur
(`dx² + dy² ≤ r²`), **lui compris** ; une entité absente n'est plus visible. Snapshots complets en
phase 2 (deltas en phase 7).

`anim` : déduit de la dernière entrée appliquée — `run` si elle a déplacé le joueur avec `sprint`,
`walk` si elle l'a déplacé sans, `idle` si elle ne l'a pas déplacé (mur, entrée nulle) ; sans entrée
appliquée pendant 4 ticks, `idle`.

Codes d'`error` :

| Code | Cause |
| --- | --- |
| `bad_message` | JSON invalide, enveloppe mal formée, charge utile invalide, message trop long |
| `unknown_type` | `t` absent de `protocol.json` |
| `rate_limited` | débit dépassé (seau de jetons : 60 messages/s, rafale de 60) |
| `internal` | réservé aux erreurs serveur |

## Codes de fermeture

| Code | Signification |
| --- | --- |
| 1001 | Arrêt du serveur ou de la zone |
| 4001 | Ticket absent, invalide, expiré, déjà utilisé ou pour une autre zone ; personnage introuvable, mort ou dans une autre zone ; compte suspendu |
| 4002 | Personnage déjà connecté |
| 4003 | Zone pleine |
| 4004 | Zone inconnue |
| 4008 | Trop de messages refusés : le 50ᵉ refus (débit ou protocole, cumulés sur la connexion) ferme la connexion au lieu d'envoyer un `error` |
| 4009 | Client trop lent : file sortante pleine (64 messages en attente) |

## Entrées, acquittement et réconciliation

Le client simule localement avec la **même** fonction `step()` que le serveur
(`server/app/zone/movement.py`, port TypeScript `client/src/game/movement/`, verrouillés par
`shared/fixtures/movement.json`) :

1. À chaque pas client (20/s), il construit l'entrée, l'applique localement (prédiction), la garde
   dans une liste « non acquittées » avec son numéro, et l'envoie (`input`, `seq` = numéro).
2. Les numéros d'entrée doivent commencer à 1 et être **strictement croissants** sur la connexion :
   le serveur ignore toute entrée dont le `seq` n'est pas supérieur au dernier appliqué (doublon,
   désordre), sans la compter dans la limite par tick. `ack_seq = 0` signifie « aucune entrée
   appliquée ». Les numéros repartent de 1 à chaque connexion.
3. Chaque `snapshot` donne `ack_seq` et la position serveur du joueur (son entité `entity_id`)
   **après** application de l'entrée `ack_seq`. Le client repart de cette position, retire les
   entrées `≤ ack_seq`, puis **rejoue** les entrées restantes avec `step()` (`dt = 1 / tick_rate`).
   Sans triche ni perte, l'écart est nul (tolérance 1e-9 tuile).
4. Les autres entités sont affichées par interpolation, avec un retard d'environ 100 ms.

Une entrée jetée parce que la file serveur était pleine n'est jamais acquittée individuellement :
la suivante appliquée l'acquitte implicitement (le client la retire au rejeu, la position serveur
fait foi).

## Déplacement (`step`)

Constantes : `shared/movement/movement.json`. Algorithme de référence documenté dans
`server/app/zone/movement.py` : axes bornés à [-1, 1] puis normalisés si `mx² + my² > 1`
(`sqrt`, pas `hypot`) ; `dx = mx × vitesse × dt` ; déplacement sur X puis sur Y, balayage tuile par
tuile, recalage exact contre le bord de la tuile solide ; hors carte = solide ; recouvrement testé
avec `floor(bas + 1e-9)` / `floor(haut − 1e-9)`. Toute modification passe par une régénération des
fixtures (`uv run python -m app.zone.movement_fixtures`, depuis `server/`) et le client.

## Ajouter un message

1. **Contrat** : décrire le message dans `shared/protocol/protocol.json` (section `client` ou
   `server`), avec le sous-ensemble de JSON Schema accepté par le générateur. Validation de
   l'Architecte.
2. **Générer** : `python tools/codegen/generate.py` à la racine, puis committer les deux fichiers
   générés (la CI vérifie avec `--check`).
3. **Serveur** :
   - message client de transport → nouvelle branche dans `_dispatch`
     (`server/app/zone/gateway.py`) ;
   - message client de jeu → rien à faire côté passerelle (mise en file automatique) ; le traiter
     dans `ZoneRuntime._apply_inputs` (`server/app/zone/runtime.py`) ;
   - message serveur → `session.post("<t>", <Payload>(...))` (non bloquant) ; `encode_server`
     vérifie que le type du payload correspond à `t`.
4. **Client** : gérer le message dans `client/src/net/` avec les types générés.
5. **Tester** : décodage/validation dans `server/tests/zone/test_codec.py`, comportement de bout
   en bout dans `server/tests/zone/test_gateway.py`, et les tests client correspondants.
   Incrémenter `version` dans `protocol.json` pour tout changement incompatible.
