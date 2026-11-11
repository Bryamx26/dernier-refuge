# Dernier Refuge

Jeu de survie zombie multijoueur en vue de dessus, jouable dans le navigateur.
Explorer, fouiller, fabriquer, combattre et survivre, seul ou en groupe, dans un monde persistant.

> Création originale. Les jeux du genre survival top-down servent d'inspiration de mécaniques uniquement.

## État

| Phase | Contenu | État |
| --- | --- | --- |
| 1. Fondations | Monorepo, Docker, API REST, WebSocket, contrats, CI | en cours |
| 2. Prototype jouable | Carte, personnage, collisions, caméra, synchro multijoueur | à venir |
| 3. Gameplay (MVP) | Zombies, combat, armes, loot, inventaire, survie | à venir |
| 4–7 | Progression, véhicules, monde persistant, optimisation | à venir |

## Démarrer

Prérequis : Docker et Docker Compose.

```bash
docker compose up --build
```

- Jeu : http://localhost:5173
- API (OpenAPI) : http://localhost:8000/docs

Développement sans Docker : voir [server/README.md](server/README.md) et [client/README.md](client/README.md).

## Organisation du dépôt

| Dossier | Rôle |
| --- | --- |
| `client/` | React (interfaces) + Phaser 3 (rendu et simulation locale), TypeScript, Vite |
| `server/` | FastAPI : API REST, serveurs de zone WebSocket autoritaires, SQLAlchemy, Alembic |
| `shared/protocol/` | Source unique du protocole WebSocket (JSON Schema) |
| `tools/codegen/` | Génère les types Python et TypeScript depuis le protocole |
| `content/` | Données de jeu (armes, objets, zombies, recettes, compétences), sans logique |
| `maps/` | Cartes Tiled |
| `assets/` | Spritesheets et sons (packs CC0, voir `assets/CREDITS.md`) |
| `docs/` | Architecture (ADR, contrats), design, rapports QA |

## Contribuer

Lire [docs/architecture/conventions.md](docs/architecture/conventions.md). Après toute modification de
`shared/protocol/protocol.json` : `python tools/codegen/generate.py`.
