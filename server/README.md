# Serveur Dernier Refuge

Serveur autoritaire en Python : API REST (FastAPI) et serveurs de zone WebSocket, avec
PostgreSQL (SQLAlchemy async + Alembic) et Redis.

## Prérequis

- [uv](https://docs.astral.sh/uv/) et Python ≥ 3.12
- PostgreSQL 16 et Redis 7 (le plus simple : `docker compose up postgres redis` depuis la racine)

## Démarrer en local

```bash
cd server
uv sync
cp .env.example .env          # puis ajuster si besoin
uv run alembic upgrade head   # crée le schéma et la zone Valcendre
uv run uvicorn app.main:app --reload
```

- Documentation interactive de l'API : http://localhost:8000/docs (désactivée si `DR_ENV=prod`)
- Sonde de santé : `GET /api/health` (200 si base et Redis répondent, sinon 503)
- WebSocket de zone : `/ws/zone/{zone_id}?ticket=…` (ticket obtenu par `POST /api/zones/{zone_id}/join`)

La stack complète (client compris) se lance depuis la racine avec `docker compose up --build`.

## Configuration

Variables d'environnement préfixées par `DR_` (ou fichier `server/.env`), décrites dans
`app/config.py` et `.env.example`. En production, `DR_JWT_SECRET` doit être remplacé.

## Tests et qualité

```bash
uv run pytest                 # SQLite temporaire + fakeredis : aucun service requis
uv run ruff check .
uv run ruff format --check .
uv run mypy app
```

Pour exécuter la suite sur Postgres (comme la CI), pointer `DR_TEST_DATABASE_URL` vers une base
**jetable** — chaque test supprime et recrée le schéma :

```bash
DR_TEST_DATABASE_URL=postgresql+asyncpg://refuge:refuge@localhost:5432/refuge_test uv run pytest
```

Les fixtures partagées (`client`, `account`, `auth_headers`, `create_account`, `create_character`,
`settings`, `engine`, `redis`…) sont documentées dans `tests/conftest.py`.

## Migrations

L'URL de la base vient de `DR_DATABASE_URL` (aucune URL dans `alembic.ini`).

```bash
uv run alembic upgrade head                              # appliquer
uv run alembic downgrade -1                              # annuler la dernière
uv run alembic revision --autogenerate -m "description"  # générer depuis app/db/models.py
uv run alembic check                                     # vérifier que modèles et migrations concordent
```

Relire systématiquement une migration autogénérée avant de la valider. Les noms de contraintes
suivent `NAMING_CONVENTION` (`app/db/base.py`). `tests/test_migrations.py` vérifie que
`upgrade head` sur une base vierge produit exactement le schéma des modèles.

## Organisation

| Chemin | Rôle |
| --- | --- |
| `app/main.py` | `create_app()`, cycle de vie (base, Redis, boucles de zone), CORS, routeurs |
| `app/api/` | Routes REST (`/api/health`, `/api/auth`, `/api/characters`, `/api/zones`) et schémas |
| `app/auth/` | Argon2id, JWT, dépendances d'authentification |
| `app/db/` | Modèles SQLAlchemy et sessions |
| `app/zone/` | Serveurs de zone : tickets, boucles de tick, passerelle WebSocket |
| `app/protocol/` | Protocole WebSocket (généré depuis `shared/protocol/protocol.json`) |
| `migrations/` | Migrations Alembic |
