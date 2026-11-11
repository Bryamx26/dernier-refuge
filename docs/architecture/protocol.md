# Protocole WebSocket de zone (v1)

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
- Les **messages de jeu** (à partir de la phase 2 : `input`, …) sont mis en file dans la session
  du client (64 au plus) et traités par la zone **au tick suivant**, dans l'ordre de réception.
- Les **messages de transport** (`ping`) sont traités immédiatement par la passerelle, hors
  simulation.

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
  │                                                              │ déjà connecté ?      sinon 4002
  │                                                              │ place libre ?        sinon 4003
  │◄──────────────────────────────────────────────────── welcome │
  │ ping / messages de jeu ────────────────────────────────────►│
```

- Le ticket évite de placer le JWT dans l'URL du WebSocket. Il est consommé dès qu'il est lu,
  même si la connexion est ensuite refusée (4001 pour une autre zone, 4002, 4003) : il faut en
  redemander un. Seul le refus 4004 (zone inconnue) intervient avant sa consommation.
- Le serveur accepte toujours la poignée de main avant de vérifier : un refus avant `accept`
  apparaîtrait dans le navigateur comme un échec HTTP sans code de fermeture.
- À la déconnexion, la session est retirée de la zone (`online` de `GET /api/zones`).

## Messages

### Client → serveur

| `t` | `d` | Traitement |
| --- | --- | --- |
| `ping` | `client_time` (ms, ≥ 0) | immédiat : réponse `pong` |

### Serveur → client

| `t` | `d` | Quand |
| --- | --- | --- |
| `welcome` | `protocol_version`, `zone_id`, `character_id`, `tick_rate`, `server_time` (ms epoch) | premier message après ouverture |
| `pong` | `client_time` (renvoyé tel quel), `server_time` | réponse à `ping` ; RTT = maintenant − `client_time` |
| `error` | `code`, `message` (≤ 200 caractères) | message refusé ; la connexion reste ouverte |

Codes d'`error` :

| Code | Cause |
| --- | --- |
| `bad_message` | JSON invalide, enveloppe mal formée, charge utile invalide, message trop long |
| `unknown_type` | `t` absent de `protocol.json` |
| `rate_limited` | débit dépassé (seau de jetons : 30 messages/s, rafale de 30) ou file d'entrée pleine |
| `internal` | réservé aux erreurs serveur |

## Codes de fermeture

| Code | Signification |
| --- | --- |
| 1001 | Arrêt du serveur ou de la zone |
| 4001 | Ticket absent, invalide, expiré, déjà utilisé ou pour une autre zone |
| 4002 | Personnage déjà connecté |
| 4003 | Zone pleine |
| 4004 | Zone inconnue |
| 4008 | Trop de messages refusés : le 50ᵉ refus (débit ou protocole, cumulés sur la connexion) ferme la connexion au lieu d'envoyer un `error` |

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
     dans `ZoneRuntime._handle_input` (`server/app/zone/runtime.py`) ;
   - message serveur → `await session.send("<t>", <Payload>(...))` ; `encode_server` vérifie que
     le type du payload correspond à `t`.
4. **Client** : gérer le message dans `client/src/net/` avec les types générés.
5. **Tester** : décodage/validation dans `server/tests/zone/test_codec.py`, comportement de bout
   en bout dans `server/tests/zone/test_gateway.py`, et les tests client correspondants.
   Incrémenter `version` dans `protocol.json` pour tout changement incompatible.
