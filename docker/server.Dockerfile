# Image du serveur (API REST + serveurs de zone).
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /srv/server

# Dépendances d'abord, pour profiter du cache Docker.
COPY server/pyproject.toml server/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Données de jeu lues par le serveur : protocole, déplacement, cartes.
COPY shared/ /srv/shared/
COPY maps/ /srv/maps/
COPY server/ ./
ENV DR_GAME_DATA_DIR=/srv
ENV PATH="/opt/venv/bin:$PATH"
EXPOSE 8000
# Applique les migrations puis démarre l'API.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --ws-max-size 65536"]
