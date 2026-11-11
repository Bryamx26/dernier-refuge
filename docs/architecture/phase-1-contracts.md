# Phase 1 — contrats entre modules

Rédigé par l'Architecte avant l'implémentation. Toute modification de ce fichier ou de
`shared/protocol/protocol.json` passe par l'Architecte.

## Déjà en place (Architecte)

| Fichier | Contenu |
| --- | --- |
| `shared/protocol/protocol.json` | Protocole WebSocket v1 : `ping` (C→S), `welcome`, `pong`, `error` (S→C) |
| `tools/codegen/generate.py` | Génère `server/app/protocol/generated.py` et `client/src/generated/protocol.ts` (`--check` en CI) |
| `server/app/config.py` | `Settings` (préfixe d'environnement `DR_`), `get_settings()` |
| `server/app/db/base.py`, `db/models.py`, `db/session.py` | `Base`, `Account`, `Zone`, `Character`, `get_db` |
| `server/app/auth/security.py`, `auth/deps.py` | Argon2id, JWT, `CurrentAccount`, `DbSession`, `AppSettings` |
| `server/app/api/schemas.py` | Schémas Pydantic des requêtes/réponses REST |

## État applicatif (`app.state`) — défini par `server/app/main.py`

| Attribut | Type | Propriétaire |
| --- | --- | --- |
| `settings` | `app.config.Settings` | Backend |
| `engine` | `AsyncEngine` | Backend |
| `sessionmaker` | `async_sessionmaker[AsyncSession]` | Backend |
| `redis` | `redis.asyncio.Redis` (decode_responses=True) | Backend |
| `zones` | `app.zone.manager.ZoneManager` | Multijoueur (classe), Backend (création dans le lifespan) |

`create_app(settings: Settings | None = None, *, engine: AsyncEngine | None = None, redis: Redis | None = None) -> FastAPI`
permet aux tests d'injecter une base SQLite et `fakeredis`.

Lifespan : créer engine/sessionmaker/redis si non injectés → charger les lignes `zones` → `await zones.start([ZoneSpec(...)])`
→ à l'arrêt `await zones.stop()`, fermer redis et engine s'ils ont été créés par l'app.

## Interfaces Multijoueur (implémentées dans `server/app/zone/`)

```python
# app/zone/tickets.py
@dataclass(frozen=True)
class TicketInfo:
    character_id: str
    zone_id: str

async def issue_ticket(redis: Redis, *, character_id: str, zone_id: str, ttl_seconds: int) -> str: ...
async def consume_ticket(redis: Redis, ticket: str) -> TicketInfo | None:  # usage unique (GETDEL)
    ...

# app/zone/manager.py
@dataclass(frozen=True)
class ZoneSpec:
    id: str
    name: str
    max_players: int
    tick_rate: int

class ZoneManager:
    async def start(self, specs: list[ZoneSpec]) -> None: ...   # lance une boucle de tick par zone
    async def stop(self) -> None: ...
    def get(self, zone_id: str) -> ZoneRuntime | None: ...
    def online_count(self, zone_id: str) -> int: ...

# app/zone/gateway.py
router = APIRouter()   # @router.websocket("/ws/zone/{zone_id}") ; paramètre de requête `ticket`
```

### Codes de fermeture WebSocket

| Code | Signification |
| --- | --- |
| 1001 | Arrêt de la zone (serveur) |
| 4001 | Ticket absent, invalide, expiré ou pour une autre zone |
| 4002 | Personnage déjà connecté |
| 4003 | Zone pleine |
| 4004 | Zone inconnue |
| 4008 | Trop de messages refusés (abus) |

## Routes REST (Backend)

| Méthode | Chemin | Auth | Réponse |
| --- | --- | --- | --- |
| GET | `/api/health` | non | `HealthOut` |
| POST | `/api/auth/register` | non | 201 `AccountOut` ; 409 si pseudo pris |
| POST | `/api/auth/login` | non | `TokenOut` ; 401 identifiants invalides ; 403 compte suspendu |
| GET | `/api/auth/me` | oui | `AccountOut` |
| GET | `/api/characters` | oui | `list[CharacterOut]` (vivants uniquement) |
| POST | `/api/characters` | oui | 201 `CharacterOut` au point d'apparition de la zone par défaut ; 409 si nom pris ou limite atteinte |
| GET | `/api/zones` | oui | `list[ZoneOut]` (`online` via `ZoneManager.online_count`) |
| POST | `/api/zones/{zone_id}/join` | oui | `JoinZoneOut` ; 404 personnage/zone ; 409 personnage mort ou dans une autre zone |

Zone par défaut (insérée par la migration initiale) : `id="valcendre"`, nom « Valcendre », `map_file="maps/valcendre.tmj"`,
`max_players=32`, `is_pvp=false`, apparition `(64.0, 64.0)`.

## Commandes standard (utilisées par la CI)

Serveur, depuis `server/` : `uv sync`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy app`, `uv run pytest`,
`uv run alembic upgrade head`.
Client, depuis `client/` : `npm ci`, `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`.
Racine : `python tools/codegen/generate.py --check`.
