# Tests de bout en bout (Playwright)

Parcours joueur réel dans Chromium, contre une pile démarrée (API + Postgres + Redis + client Vite).
Les tests utilisent `node:test` et la bibliothèque `playwright` (pas `@playwright/test`) : aucun
traçage n'est activé (équivalent de `--trace off`).

| Fichier | Scénario |
| --- | --- |
| `tests/phase1.test.cjs` #1 | inscription → déconnexion → connexion → création d'un personnage → « Rejoindre » → le HUD affiche « En ligne », un ping en ms, un tick qui augmente, zone Valcendre à 20 Hz ; `online = 1` côté API, puis 0 après « Quitter la zone » ; aucune erreur console |
| `tests/phase1.test.cjs` #2 | deux navigateurs, deux comptes dans Valcendre en même temps → `GET /api/zones` renvoie `online = 2` ; fermeture brutale d'un navigateur → `online = 1` |
| `tests/phase2.test.cjs` #1 | deux navigateurs (A, B) + un observateur WebSocket : A marche (D), B marche (W) ; chacun reçoit dans ses trames WebSocket la trajectoire de l'autre jusqu'à sa position serveur ; HUD « Joueurs » = 3, position HUD = serveur |
| `tests/phase2.test.cjs` #2 | rejoint (64, 64) depuis le point d'apparition tiré au hasard, puis sprint et marche contre un bâtiment (poussée, glissements, coin) : aucune boîte ne recouvre une case solide du calque `collision` de `maps/valcendre.tmj` dans les snapshots serveur ; vitesse d'un client honnête ≤ 5,5 t/s |
| `tests/phase2.test.cjs` #3 | client « tricheur » : entrées hors bornes, mal typées, champ en trop, NaN, `seq` négatif → `bad_message` sans effet ; doublons ou désordre ignorés |
| `tests/phase2.test.cjs` #4 | tricheur : 100 entrées de sprint d'un coup → distance parcourue ≤ `sprint_speed × dt × (ticks écoulés + 20)` (budget cumulé du serveur) |
| `tests/phase2.test.cjs` #5 | client honnête à 20 entrées/s dont l'envoi est gelé 1 s puis délivré d'un coup : le retard d'entrées côté serveur (`seq` − `ack_seq`) revient à son niveau d'avant le gel |
| `tests/phase3.test.cjs` #1 | nouveau personnage : point d'apparition de la place, couteau en main, eau, biscuits, bandage ; HUD Survie à 100 ; clic gauche → effet `swing` du serveur ; I ouvre l'inventaire, « Boire » consomme la bouteille et affiche « Utilisé : Bouteille d'eau » ; aucune erreur console |
| `tests/phase3.test.cjs` #2 | marche jusqu'à la porte de la maison du notaire, E : barre « Fouille : … » puis message « Trouvé : … » ou « rien trouvé » (« déjà fouillé » si une exécution précédente l'a vidée) |
| `tests/phase2.test.cjs` #6 | latence ajoutée par `tools/latency-proxy.cjs` : parcours de ~11 s (marche, sprint, demi-tours, mur) ; correction HUD < 0,25 tuile (relevée toutes les 100 ms) et aucun saut de position ; ignoré sans `DR_E2E_LAG_BASE_URL` |

Les scénarios phase1 #2 et phase2 #1 supposent une zone vide au départ : utilisez un serveur dédié aux tests.
Les tests créent une dizaine de comptes : relevez la limite d'inscriptions et de connexions du serveur de
test (`DR_AUTH_RATE_LIMIT_PER_MINUTE=1000`), sinon une seconde exécution dans la minute échoue en 429.

Les outils réseau (comptes créés par l'API, client WebSocket brut, grille de collision) sont dans
`tests/net.cjs`. Ils utilisent le `WebSocket` global de Node 22 : aucune dépendance supplémentaire.

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

2. Pour le test de latence, démarrer un second Vite dont le proxy passe par le proxy de latence.
   Le test lance lui-même ce proxy sur le port 8150, vers 127.0.0.1:8000 :

   ```bash
   cd client && VITE_PROXY_TARGET=http://localhost:8150 npx vite --port 5174 &
   ```

   Le proxy fonctionne aussi seul :
   `node e2e/tools/latency-proxy.cjs --listen 8150 --target 127.0.0.1:8000 --delay 75 [--jitter 20]`
   (`--delay` est le délai **par sens**).

3. Lancer les tests (Playwright doit être résolvable : `npm i playwright` ici, ou installation
   globale avec `NODE_PATH`) :

   ```bash
   cd e2e
   NODE_PATH=$(npm root -g) npm test
   # avec le test de latence (150 ms de RTT) :
   NODE_PATH=$(npm root -g) DR_E2E_LAG_BASE_URL=http://localhost:5174 npm test
   ```

## Variables

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `DR_E2E_BASE_URL` | `http://localhost:5173` | URL du client (l'API est appelée via le proxy Vite) |
| `DR_E2E_SCREENSHOTS` | *(vide)* | Dossier où enregistrer les captures (`01-connexion.png`, `02-personnages.png`, `03-jeu-connecte.png`, `phase2-01-deux-joueurs-vue-B.png`, `phase2-02-deux-joueurs-vue-A.png`, `phase2-03-joueur-contre-batiment.png`, deviceScaleFactor 2, 1280×800) |
| `DR_E2E_LAG_BASE_URL` | *(vide : test de latence ignoré)* | URL du second Vite, dont le proxy vise le proxy de latence (ex. `http://localhost:5174`) |
| `DR_E2E_LAG_MS` | `75` | Latence ajoutée **par sens**, en ms (RTT + 2 × valeur) |
| `DR_E2E_LAG_JITTER_MS` | `0` | Gigue aléatoire par sens, en ms (l'ordre des octets est conservé) |
| `DR_E2E_LAG_PROXY_PORT` | `8150` | Port d'écoute du proxy de latence |
| `DR_E2E_API_TARGET` | `127.0.0.1:8000` | Cible du proxy de latence (uvicorn) |
| `DR_E2E_CHROMIUM` | *(Chromium de Playwright)* | Chemin d'un Chromium préinstallé (ex. `/opt/pw-browsers/chromium`) si la version de Playwright ne correspond pas aux navigateurs installés |
