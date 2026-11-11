# Conventions de développement

## Général

- Langue : documentation, commentaires et textes du jeu en français ; identifiants de code en anglais.
- Contrats d'abord : une interface entre modules (message WebSocket, route REST, schéma de contenu) est
  écrite et validée par l'Architecte avant son implémentation.
- Données et logique séparées : les valeurs de gameplay vivent dans `content/`, jamais en dur dans le code.
- Un mock ou un placeholder est toujours signalé (nom de fichier `*_PLACEHOLDER.*`, commentaire `PLACEHOLDER:`).

## Propriété des dossiers

| Rôle | Dossiers |
| --- | --- |
| Architecte | `docs/architecture/`, `shared/`, `tools/codegen/`, `docker/`, `docker-compose.yml`, `.github/`, `server/app/config.py`, `server/app/db/models.py` |
| Backend | `server/app/api/`, `server/app/auth/`, `server/app/db/` (hors modèles), `server/app/main.py`, `server/migrations/` |
| Multijoueur | `server/app/zone/`, `server/app/protocol/codec.py`, `client/src/net/` (phase 2+) |
| Frontend | `client/src/ui/`, `client/src/state/`, `client/src/api/` |
| Moteur de jeu | `client/src/game/`, `client/src/bridge/` |
| Systems / Game / World Designers | `content/`, `maps/`, `docs/design/` |
| QA | `server/tests/`, `client/src/**/*.test.ts(x)`, `e2e/`, `docs/qa/` |

Modifier les fichiers d'un autre rôle passe par l'Architecte.

## Python (`server/`)

- Python 3.12+, typage complet, `mypy --strict`, `ruff check` et `ruff format`.
- Accès base asynchrone (SQLAlchemy 2), toute évolution de schéma passe par une migration Alembic.
- Tests `pytest` ; chaque route et chaque système a ses tests.

## TypeScript (`client/`)

- `strict: true`, ESLint + Prettier, tests Vitest.
- Phaser n'importe jamais React ; React ne manipule jamais d'objets Phaser.
- `client/src/generated/` est généré : ne jamais l'éditer.

## Git

- Une branche et une pull request par phase (`phase-N-<nom>`), validée par le propriétaire du projet.
- Messages de commit en français, à l'impératif.
- La CI (contrats, serveur, client) doit être verte avant fusion.
