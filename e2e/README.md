# Tests de bout en bout (Playwright)

Parcours joueur réel dans Chromium, contre une pile démarrée (API + Postgres + Redis + client Vite).
Les tests utilisent `node:test` et la bibliothèque `playwright` (pas `@playwright/test`) : aucun
traçage n'est activé (équivalent de `--trace off`).

| Fichier | Scénario |
| --- | --- |
| `tests/phase1.test.cjs` #1 | inscription → déconnexion → connexion → création d'un personnage → « Rejoindre » → le HUD affiche « En ligne », un ping en ms, un tick qui augmente, zone Valcendre à 20 Hz ; `online = 1` côté API, puis 0 après « Quitter la zone » ; aucune erreur console |
| `tests/phase1.test.cjs` #2 | deux navigateurs, deux comptes dans Valcendre en même temps → `GET /api/zones` renvoie `online = 2` ; fermeture brutale d'un navigateur → `online = 1` |

Le scénario 2 suppose une zone vide au départ : utilisez un serveur dédié aux tests.

## Lancer

1. Démarrer la pile, soit `docker compose up --build`, soit à la main :

   ```bash
   # Postgres et Redis accessibles, puis :
   cd server
   export DR_DATABASE_URL=postgresql+asyncpg://refuge:refuge@127.0.0.1:5432/refuge
   export DR_REDIS_URL=redis://127.0.0.1:6379/0
   uv run alembic upgrade head
   uv run uvicorn app.main:app --port 8000 &
   cd ../client && npm run dev &   # http://localhost:5173, proxy /api et /ws vers :8000
   ```

2. Lancer les tests (Playwright doit être résolvable : `npm i playwright` ici, ou installation
   globale avec `NODE_PATH`) :

   ```bash
   cd e2e
   NODE_PATH=$(npm root -g) npm test
   ```

## Variables

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `DR_E2E_BASE_URL` | `http://localhost:5173` | URL du client (l'API est appelée via le proxy Vite) |
| `DR_E2E_SCREENSHOTS` | *(vide)* | Dossier où enregistrer les captures (`01-connexion.png`, `02-personnages.png`, `03-jeu-connecte.png`, deviceScaleFactor 2, 1280×800) |
| `DR_E2E_CHROMIUM` | *(Chromium de Playwright)* | Chemin d'un Chromium préinstallé (ex. `/opt/pw-browsers/chromium`) si la version de Playwright ne correspond pas aux navigateurs installés |
