# ADR 0001 — Stack technique

- Statut : accepté (2026-11-11)

## Contexte

Jeu multijoueur temps réel dans le navigateur, serveur autoritaire, projet appelé à grossir.

## Décision

- Client : React 18 + TypeScript + Vite pour l'interface, Phaser 3 pour le rendu, Zustand pour l'état UI,
  Tailwind CSS pour le style des écrans.
- Serveur : Python 3.12, FastAPI (REST + WebSocket), Pydantic 2, SQLAlchemy 2 asynchrone, Alembic.
- Données : PostgreSQL 16 (persistant), Redis 7 (temporaire).
- Outillage : Docker Compose, GitHub Actions, pytest, Vitest, ruff, mypy, ESLint.

## Conséquences

- La logique de déplacement existera en TypeScript (prédiction) et en Python (autorité) : elle sera
  minimale, pure, et vérifiée par des jeux de tests partagés (phase 2).
- La performance de la boucle Python est à surveiller dès la phase 3 (budget : 25 ms par tick).
