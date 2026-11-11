# QA — Phase 1 (fondations)

Date : 2026-11-11 · branche `phase-1-fondations` (non commitée) · agent QA.

## Verdict

**Phase 1 validée sous réserve** : tous les critères vérifiables ici sont OK (CI rejouée à
l'identique, Postgres réel, parcours navigateur réel à deux joueurs). Seul `docker compose up`
n'a pas pu être exécuté jusqu'au bout : le démon Docker démarre, mais Docker Hub répond
**429 Too Many Requests** et ghcr.io **Forbidden** à l'extraction des images (limitation de
l'environnement, pas du dépôt). `docker compose config` est valide. À rejouer sur un poste avec
accès aux registres avant de clore la phase.

## Critères du plan

| Critère | Résultat | Preuve |
| --- | --- | --- |
| `docker compose up` démarre tout sans erreur | **NON VÉRIFIÉ** (bloqué par l'environnement) | `docker compose config` → code 0. `docker compose up --build -d` → `failed to resolve reference "docker.io/library/redis:7-alpine": … 429 Too Many Requests` ; `docker pull ghcr.io/astral-sh/uv:0.11.32` → `… Forbidden` ; `docker build -f docker/client.Dockerfile` → `node:22-slim … 429 Too Many Requests`. Équivalent hors Docker (mêmes commandes que le `CMD` des images) : OK, voir § Bout en bout |
| Inscription et connexion REST testées | **OK** | pytest (`tests/test_auth.py`) SQLite et Postgres ; e2e scénario 1 (inscription, déconnexion, connexion via l'interface) |
| Migration initiale appliquée | **OK** | `alembic upgrade head` sur Postgres 16 : `Running upgrade -> 0001` ; tables `accounts`, `zones`, `characters`, `alembic_version` ; zone `valcendre` / Valcendre / `maps/valcendre.tmj` / 32 / non JcJ / (64, 64) ; `tests/test_migrations.py` (upgrade, downgrade, cohérence modèles) |
| Un client reçoit `welcome` et des `pong` | **OK** | e2e : HUD « En ligne », « Ping 9 ms », tick 1443 → croissant, « Fréquence 20 Hz » ; sonde WebSocket Python : `welcome` en premier message |
| Types TS et Python générés depuis les schémas | **OK** | `python tools/codegen/generate.py --check` → code 0 |
| CI exécute lint, types et tests | **OK** | `.github/workflows/ci.yml` : jobs `contracts`, `server` (ruff, ruff format, mypy, pytest sur Postgres 16), `client` (eslint, tsc, vitest, build) ; toutes les étapes rejouées localement → code 0 |

## Résultats exacts des commandes

Racine :

| Commande | Résultat |
| --- | --- |
| `python tools/codegen/generate.py --check` | code 0 |
| `docker compose config` | code 0 |
| `docker compose up --build -d` | code 1 : `Error response from daemon: unknown: failed to resolve reference "docker.io/library/redis:7-alpine": unexpected status from HEAD request to https://registry-1.docker.io/v2/library/redis/manifests/7-alpine: 429 Too Many Requests` |

`server/` (uv, Python 3.13 local ; la CI utilise 3.12) :

| Commande | Résultat |
| --- | --- |
| `uv sync --frozen` | code 0, 51 paquets |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | `41 files already formatted` |
| `uv run mypy app` | `Success: no issues found in 26 source files` |
| `uv run pytest -q` (SQLite) | `78 passed, 1 warning in 6.27s` |
| `uv run pytest -q` (Postgres 16, `DR_TEST_DATABASE_URL=…@127.0.0.1:55432/refuge_test`) | `78 passed, 1 warning in 6.30s` (228 transactions constatées sur `refuge_test` : Postgres bien utilisé) |

Avertissement unique : `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`.

`client/` (Node 22.23) :

| Commande | Résultat |
| --- | --- |
| `npm ci` | code 0 ; `npm audit` : 10 vulnérabilités (8 modérées, 2 critiques, toutes en dépendances de dev : `tinypool` via `vitest`) ; dépréciations `eslint@9.39.5`, `@testing-library/jest-dom@6.10.0` |
| `npm run lint` | code 0 |
| `npm run typecheck` | code 0 |
| `npm run test` | `7 fichiers, 43 tests passés` |
| `npm run build` | code 0 ; chunk `phaser` 1 208 kB (332 kB gzip), `index` 167 kB |

## Bout en bout

Pile réelle : Postgres 16 (port 55432), `redis-server --port 56379`, `alembic upgrade head`,
`uvicorn app.main:app --port 8000`, `npm run dev` (proxy `/api` et `/ws`). `/api/health` →
`{"status":"ok","database":true,"redis":true}` en direct et via le proxy Vite.

Tests : `e2e/tests/phase1.test.cjs` (voir `e2e/README.md`), lancés deux fois : **2/2 OK** à chaque fois.

1. Inscription → déconnexion → connexion → création de « Survivant … » → Rejoindre → HUD « En ligne »,
   ping `\d+ ms`, tick croissant sur 2,5 s, zone Valcendre, 20 Hz ; `online = 1` côté API puis `0`
   après « Quitter la zone » ; aucune erreur console.
2. Deux navigateurs Chromium, deux comptes, connexion simultanée → `GET /api/zones` : `online = 2` ;
   fermeture brutale d'un navigateur → `online = 1` (déconnexion détectée).

Sondes manuelles (serveur réel) :

| Sonde | Résultat |
| --- | --- |
| WS sans ticket | fermé 4001 ✔ |
| WS zone inconnue | fermé 4004 ✔ |
| Rejeu d'un ticket déjà consommé | fermé 4001 ✔ |
| Deux tickets pour le même personnage, deuxième connexion | fermé 4002 ✔ |
| 80 `ping` en rafale | 30 `pong`, 49 `error rate_limited`, puis fermeture 4008 ✔ (conforme au contrat) |
| JWT invalide | 401 ✔ |
| Préflight CORS depuis `https://evil.example` | 400, pas d'`Access-Control-Allow-Origin` ✔ |
| Message WS de 2 Mo | accepté en mémoire puis refusé par `error bad_message` (voir P4) |
| WS ouvert avec `Origin: https://evil.example` | accepté (voir P6) |
| 20 connexions avec mauvais mot de passe en 1,2 s | 20 × 401, aucun 429 (voir P2) |
| Inscription de `QaCase` puis `qacase` | 201 et 201 (voir P5) |

## Captures (deviceScaleFactor 2, 1280×800)

`/mnt/project-files/phase-1/01-connexion.png`, `02-personnages.png`, `03-jeu-connecte.png`.

Constat visuel : direction artistique cohérente « terminal radio post-apocalyptique » (polices pixel
Pixelify Sans / VT323, cadres à coins, scanlines, palette charbon/vert-de-gris/rouille). Ça ne
ressemble pas à une appli web générique sur les écrans de connexion et de personnages. Défauts :

| # | Écran | Défaut |
| --- | --- | --- |
| V1 | Tous | En Pixelify Sans majuscule, le **Z se lit comme un 2** : « 2ONES », « QUITTER LA 2ONE », « LIAISON DE 2ONE ». Le J de « REJOINDRE » est aussi ambigu. Changer de police pour les titres ou retoucher le glyphe |
| V2 | Connexion | « Prototype · phase 1 » (`text-charcoal-600` #353b37 sur ~#161a18) : contraste **1,5:1**, quasi illisible (`client/src/ui/screens/AuthScreen.tsx:125`) |
| V3 | Jeu | Le canvas Phaser ne montre qu'un panneau de texte de débogage qui **duplique** le HUD (zone, état, ping, tick) au centre d'un écran noir : aucun monde, aucune carte. Acceptable pour la phase 1, mais l'écran ressemble à une console de diagnostic, pas à un jeu |
| V4 | Personnages | « 1 FICHE(S) » : pluriel non géré (`CharacterScreen.tsx:124`) ; grande zone vide sous la liste à 1280×800 |
| V5 | Personnages | Le nom du personnage en Pixelify Sans casse mixte (« Survivant Eblotmmj ») a des glyphes inhabituels (E, j) ; lisible mais moins que VT323 |

Aucun texte coupé, aucun débordement constaté à 1280×800.

## Problèmes trouvés (sécurité / robustesse)

| # | Gravité | Fichier:ligne | Problème | Recommandation |
| --- | --- | --- | --- | --- |
| P1 | Moyenne | `server/app/config.py:18`, `docker-compose.yml:37` | Le secret JWT par défaut (public, dans le dépôt) est accepté même avec `DR_ENV=prod` : un déploiement qui oublie `DR_JWT_SECRET` permet à n'importe qui de forger des jetons | Refuser le démarrage si `env == "prod"` et secret par défaut (validateur Pydantic) |
| P2 | Moyenne | `server/app/api/auth.py:131`, `:117` | Aucune limite de débit sur `/api/auth/login` ni `/register` : force brute illimitée (20 essais/1,2 s mesurés) ; chaque requête coûte un Argon2id dans le pool de threads → saturation CPU facile (DoS) | Limiteur par IP et par pseudo (Redis), 429 + `Retry-After` |
| P3 | Basse | `server/app/zone/gateway.py:70-77` | Le ticket n'est pas revalidé contre l'état du compte : un compte suspendu après émission (TTL 30 s) peut entrer, et les sessions WS ouvertes d'un compte suspendu ne sont pas fermées | Prévoir une fermeture des sessions au bannissement (phase admin) |
| P4 | Basse | `docker/server.Dockerfile:15` (uvicorn sans `--ws-max-size`), `server/app/protocol/codec.py:60` | La limite de 4 096 octets n'est appliquée qu'après réception complète ; uvicorn accepte par défaut 16 Mo par message : un client peut faire allouer 16 Mo par trame (2 Mo vérifiés) | `--ws-max-size 65536` (ou config uvicorn) pour couper au niveau transport |
| P5 | Basse | `server/app/db/models.py:22`, `migrations/versions/0001_initial.py:28` | Unicité du pseudo (et du nom de personnage, `models.py:48`) sensible à la casse : `QaCase` et `qacase` coexistent → usurpation visuelle | Index unique sur `lower(username)` |
| P6 | Basse | `server/app/zone/gateway.py:61` | Pas de contrôle d'`Origin` sur le WebSocket. Atténué par le ticket (obtenu uniquement avec le Bearer), donc pas de CSWSH exploitable aujourd'hui | Vérifier `Origin` ∈ `cors_origins` par défense en profondeur |
| P7 | Basse | `docker/server.Dockerfile:15` | uvicorn journalise l'URL complète du WS, ticket compris (`"WebSocket /ws/zone/valcendre?ticket=…" [accepted]`). Risque faible (usage unique, 30 s) | Désactiver l'access log WS ou filtrer la query |
| P8 | Basse | `server/app/config.py:19`, `client/src/state/sessionStore.ts:24,28` | JWT de 24 h non révocable ; « Déconnexion » ne fait qu'oublier le jeton côté client (stocké en `sessionStorage`, exposé en cas de XSS) | Jetons plus courts + rafraîchissement, ou liste de révocation Redis |
| P9 | Basse | `docker-compose.yml:12,22`, `docker/server.Dockerfile` | Postgres (`refuge/refuge`) et Redis (sans mot de passe) publiés sur toutes les interfaces de l'hôte ; image serveur exécutée en root. Acceptable en dev | Lier à `127.0.0.1:` ; `USER` non root dans l'image |
| P10 | Info | `client/package.json` | `npm audit` : 2 critiques (`tinypool` via `vitest` 3), dev uniquement ; `eslint@9.39.5` et `@testing-library/jest-dom@6.10.0` dépréciés | Planifier la montée de `vitest`, épingler `jest-dom@6.9.1` |
| P11 | Info | `.github/workflows/ci.yml` | La CI ne lance ni les tests e2e ni une construction des images Docker (`docker compose build`) : la casse du critère « docker compose up » ne serait pas détectée | Ajouter un job `docker compose build` et, plus tard, le job e2e |

Points vérifiés sans défaut : Argon2id avec hash factice contre l'énumération par temps de réponse
(`auth.py:107-135`), JWT HS256 avec `exp`/`sub` requis, statut banni vérifié à chaque requête,
personnage d'un autre compte traité en 404 (`zones.py:117`), tickets `token_urlsafe(32)` à usage
unique (GETDEL) et liés à la zone, CORS sans credentials et à origines explicites, NaN/Infinity et
booléens refusés dans le protocole, seau de jetons et fermeture 4008, verrou `FOR UPDATE` contre
le dépassement de la limite de personnages, nettoyage de session en `finally`.

## Recommandations

1. Rejouer `docker compose up --build` sur une machine avec accès à Docker Hub/ghcr.io (ou avec un
   miroir authentifié) et ajouter `docker compose build` à la CI (P11).
2. Corriger P1 et P2 avant toute exposition publique.
3. Fixer `--ws-max-size` (P4) et l'unicité insensible à la casse (P5) pendant la phase 2, tant que la
   migration est simple.
4. Visuel : remplacer la police des titres ou le glyphe Z (V1), relever le contraste du pied de page (V2).
5. Intégrer `e2e/` en CI (services Postgres/Redis déjà présents dans le job serveur).

## Corrections appliquées après la revue QA (Architecte)

| Problème | Correction |
| --- | --- |
| Secret JWT de dev accepté en production | `Settings` refuse le démarrage si `DR_ENV=prod` avec le secret par défaut (test `test_prod_refuses_dev_secret`) |
| Pas de limite de débit sur login/register | Fenêtre fixe Redis par IP, 20 requêtes/min par défaut (`DR_AUTH_RATE_LIMIT_PER_MINUTE`), réponse 429 + `Retry-After` (test `test_login_rate_limited`) |
| Messages WebSocket jusqu'à 16 Mo acceptés par uvicorn | `--ws-max-size 65536` dans l'image serveur |
| `server_default="false"` textuel | Remplacé par `sa.false()` dans les modèles et la migration |
| Contraste du pied de page de connexion, « FICHE(S) » | Corrigés |

Restent pour la phase 2 : unicité insensible à la casse, revérification du compte à l'ouverture du WebSocket,
contrôle `Origin`, ticket dans les journaux d'accès, révocation des jetons, durcissement Docker (ports, utilisateur non root),
lisibilité du « Z » de la police de titre, e2e et construction des images en CI.
