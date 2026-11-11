"""Exécution d'une zone : boucle de simulation à pas fixe, joueurs, intérêt spatial, sauvegarde."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.protocol.codec import encode_entity, encode_snapshot
from app.protocol.generated import AnimState, EntityState, InputPayload
from app.zone.movement import MoveInput, MovementConfig, step
from app.zone.persistence import PlayerStore, SavedPosition
from app.zone.session import ClientSession
from app.zone.tilemap import ZoneMap

if TYPE_CHECKING:
    from app.zone.manager import ZoneSpec

logger = logging.getLogger(__name__)

# Retard (en ticks) au-delà duquel la boucle abandonne le rattrapage et repart de maintenant.
MAX_CATCH_UP_TICKS = 5
# Code de fermeture standard « départ du serveur » (RFC 6455).
CLOSE_GOING_AWAY = 1001
# Côté (en tuiles) des cellules de la grille spatiale d'intérêt.
INTEREST_CELL_SIZE = 16
# Sans entrée appliquée pendant ce nombre de ticks, un joueur repasse en animation `idle`
# (tolère la gigue réseau : un tick sans entrée suivi d'un tick à deux entrées).
# Avance maximale (en entrées) qu'un joueur peut prendre sur l'horloge du serveur : 1 s à 20 Hz.
INPUT_CATCHUP_MARGIN = 20
IDLE_AFTER_TICKS = 4
# Période de la sauvegarde automatique des positions, en secondes.
AUTOSAVE_INTERVAL_S = 30.0


class AlreadyConnectedError(Exception):
    """Le personnage a déjà une session dans la zone (fermeture 4002)."""


class ZoneFullError(Exception):
    """La zone a atteint `max_players` (fermeture 4003)."""


@dataclass
class TickStats:
    """Durée de calcul des ticks, en millisecondes."""

    count: int = 0
    last_ms: float = 0.0
    max_ms: float = 0.0
    total_ms: float = 0.0
    # Ticks dont le calcul a dépassé la période (la simulation prend du retard).
    overruns: int = 0
    # Resynchronisations après un retard supérieur à MAX_CATCH_UP_TICKS.
    resyncs: int = 0

    @property
    def mean_ms(self) -> float:
        return self.total_ms / self.count if self.count else 0.0

    def record(self, duration_ms: float, period_ms: float) -> None:
        self.count += 1
        self.last_ms = duration_ms
        self.total_ms += duration_ms
        self.max_ms = max(self.max_ms, duration_ms)
        if duration_ms > period_ms:
            self.overruns += 1


@dataclass(slots=True)
class PlayerEntity:
    """Entité d'un joueur connecté. Position en tuiles, `aim` en radians."""

    entity_id: str
    character_id: str
    name: str
    x: float
    y: float
    aim: float
    anim: AnimState = "idle"
    # `seq` de la dernière entrée appliquée (0 : aucune).
    ack_seq: int = 0
    # Ticks consécutifs sans entrée appliquée.
    idle_ticks: int = 0
    # Budget cumulé d'entrées (anti-accélération) : depuis l'arrivée du joueur, le nombre
    # d'entrées appliquées ne dépasse jamais `ticks_alive + INPUT_CATCHUP_MARGIN`.
    ticks_alive: int = 0
    inputs_applied: int = 0

    def state(self) -> EntityState:
        return EntityState(
            id=self.entity_id, kind="player", name=self.name, x=self.x, y=self.y, aim=self.aim, anim=self.anim
        )

    def saved_position(self) -> SavedPosition:
        return SavedPosition(character_id=self.character_id, x=self.x, y=self.y, facing=self.aim)


def _snapshot_builder(ack_seq: int, entities_json: list[str]) -> Callable[[int, int], str]:
    return lambda seq, tick: encode_snapshot(seq, tick, ack_seq, entities_json)


class ZoneRuntime:
    """Une zone en cours d'exécution.

    La boucle avance la simulation `tick_rate` fois par seconde. Les échéances sont
    calculées depuis l'origine (`origin + n × période`) et non par cumul de `sleep`,
    ce qui évite toute dérive. À chaque tick : application des entrées en file (au plus
    `max_inputs_per_tick` par joueur), puis envoi d'un snapshot à chaque joueur. Les envois
    sont mis en file sans attente (`ClientSession.post_encoded`) : le tick n'attend jamais un client.
    """

    def __init__(
        self,
        spec: ZoneSpec,
        *,
        zone_map: ZoneMap | None = None,
        movement: MovementConfig | None = None,
        store: PlayerStore | None = None,
        autosave_interval: float = AUTOSAVE_INTERVAL_S,
    ) -> None:
        self.spec = spec
        self.tick = 0
        self.stats = TickStats()
        self.period = 1.0 / spec.tick_rate
        # Durée simulée d'une entrée (contrat : un message `input` = un pas de 1 / tick_rate s).
        self.dt = 1.0 / spec.tick_rate
        self.map = zone_map if zone_map is not None else ZoneMap.open_area(spec.id)
        self.movement = movement if movement is not None else MovementConfig.load()
        self.store = store
        self.autosave_interval = autosave_interval
        self._sessions: dict[str, ClientSession] = {}
        self._players: dict[str, PlayerEntity] = {}
        self._entity_counter = 0
        self._task: asyncio.Task[None] | None = None
        self._autosave_task: asyncio.Task[None] | None = None

    # --- Cycle de vie -------------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Lance la boucle de tick (et la sauvegarde périodique) dans la boucle asyncio courante."""
        if self._task is not None:
            raise RuntimeError(f"zone {self.spec.id} déjà démarrée")
        self._task = asyncio.create_task(self._run(), name=f"zone-tick:{self.spec.id}")
        if self.store is not None:
            self._autosave_task = asyncio.create_task(self._autosave(), name=f"zone-save:{self.spec.id}")

    async def stop(self) -> None:
        """Arrête la boucle, sauvegarde les positions, puis ferme les connexions restantes (1001)."""
        task, self._task = self._task, None
        autosave, self._autosave_task = self._autosave_task, None
        for pending in (task, autosave):
            if pending is not None:
                pending.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await pending
        await self.save_all()
        sessions = list(self._sessions.values())
        self._sessions.clear()
        self._players.clear()
        for session in sessions:
            session.close(CLOSE_GOING_AWAY, "arrêt de la zone")
        await asyncio.gather(*(session.shutdown() for session in sessions), return_exceptions=True)

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        origin = loop.time()
        step_index = 0
        while True:
            step_index += 1
            deadline = origin + step_index * self.period
            delay = deadline - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            elif -delay > MAX_CATCH_UP_TICKS * self.period:
                # Trop de retard (machine surchargée, pause du processus) : plutôt que d'enchaîner
                # des ticks en rafale, on repart de maintenant.
                self.stats.resyncs += 1
                logger.warning("zone %s : %.0f ms de retard, resynchronisation", self.spec.id, -delay * 1000)
                origin, step_index = loop.time(), 0
            started = time.perf_counter()
            try:
                self._step()
            except Exception:
                # Une erreur de simulation ne doit pas tuer la zone entière.
                logger.exception("zone %s : erreur au tick %d", self.spec.id, self.tick)
            self.stats.record((time.perf_counter() - started) * 1000, self.period * 1000)

    async def _autosave(self) -> None:
        while True:
            await asyncio.sleep(self.autosave_interval)
            await self.save_all()

    async def save_all(self) -> None:
        """Sauvegarde en lot la position de tous les joueurs (hors tick ; erreurs journalisées)."""
        if self.store is None or not self._players:
            return
        # Copie synchrone (instantané cohérent), puis écriture asynchrone.
        positions = [player.saved_position() for player in self._players.values()]
        try:
            await self.store.save_positions(positions)
        except Exception:
            logger.exception("zone %s : échec de la sauvegarde de %d positions", self.spec.id, len(positions))

    # --- Simulation ---------------------------------------------------------------------------

    def _step(self) -> None:
        """Un pas de simulation : entrées puis snapshots."""
        self.tick += 1
        for character_id, session in self._sessions.items():
            self._apply_inputs(self._players[character_id], session)
        self._send_snapshots()

    def _apply_inputs(self, player: PlayerEntity, session: ClientSession) -> None:
        """Applique les entrées en file dans la limite du crédit du joueur (anti-accélération).

        Au plus `max_inputs_per_tick` entrées par tick, et jamais plus de `ticks_alive +
        INPUT_CATCHUP_MARGIN` entrées depuis l'arrivée du joueur : un client honnête rattrape un gel
        réseau (jusqu'à la marge), un tricheur reste à un pas par tick en moyenne.

        Une entrée dont le `seq` n'est pas strictement supérieur au dernier appliqué (doublon,
        désordre) est ignorée sans compter dans la limite.
        """
        queue = session.pending_inputs
        player.ticks_alive += 1
        budget = min(
            self.movement.max_inputs_per_tick,
            player.ticks_alive + INPUT_CATCHUP_MARGIN - player.inputs_applied,
        )
        applied = 0
        last_moved = False
        last_sprint = False
        while applied < budget and queue:
            envelope = queue.popleft()
            payload = envelope.payload
            if not isinstance(payload, InputPayload) or envelope.seq <= player.ack_seq:
                continue
            move = MoveInput(payload.move_x, payload.move_y, payload.sprint)
            x, y = step((player.x, player.y), move, self.map.grid, self.movement, self.dt)
            last_moved = x != player.x or y != player.y
            last_sprint = payload.sprint
            player.x, player.y = x, y
            player.aim = payload.aim
            player.ack_seq = envelope.seq
            applied += 1
        player.inputs_applied += applied
        if applied:
            player.idle_ticks = 0
            player.anim = ("run" if last_sprint else "walk") if last_moved else "idle"
        else:
            player.idle_ticks += 1
            if player.idle_ticks >= IDLE_AFTER_TICKS:
                player.anim = "idle"

    def _send_snapshots(self) -> None:
        """Envoie à chaque joueur les entités à moins de `interest_radius` tuiles (lui compris).

        Grille spatiale reconstruite à chaque tick : cellules de `INTEREST_CELL_SIZE` tuiles ; seules
        les cellules recoupant le carré englobant du cercle d'intérêt sont parcourues, puis la
        distance est testée (`dx² + dy² ≤ r²`). Chaque entité est sérialisée une seule fois.
        """
        if not self._sessions:
            return
        cell = INTEREST_CELL_SIZE
        radius = self.movement.interest_radius
        radius2 = radius * radius
        cells: defaultdict[tuple[int, int], list[tuple[PlayerEntity, str]]] = defaultdict(list)
        for player in self._players.values():
            key = (math.floor(player.x / cell), math.floor(player.y / cell))
            cells[key].append((player, encode_entity(player.state())))

        for character_id, session in self._sessions.items():
            me = self._players[character_id]
            visible: list[str] = []
            for cy in range(math.floor((me.y - radius) / cell), math.floor((me.y + radius) / cell) + 1):
                for cx in range(math.floor((me.x - radius) / cell), math.floor((me.x + radius) / cell) + 1):
                    for other, encoded in cells.get((cx, cy), ()):
                        dx, dy = other.x - me.x, other.y - me.y
                        if dx * dx + dy * dy <= radius2:
                            visible.append(encoded)
            session.post_encoded(_snapshot_builder(me.ack_seq, visible))

    # --- Sessions ----------------------------------------------------------------------------

    @property
    def online_count(self) -> int:
        return len(self._sessions)

    def is_connected(self, character_id: str) -> bool:
        return character_id in self._sessions

    def player(self, session: ClientSession) -> PlayerEntity | None:
        """Entité de la session, si elle est bien celle enregistrée pour ce personnage."""
        if self._sessions.get(session.character_id) is not session:
            return None
        return self._players.get(session.character_id)

    def register(
        self,
        session: ClientSession,
        *,
        name: str = "",
        position: tuple[float, float] | None = None,
        aim: float = 0.0,
    ) -> PlayerEntity:
        """Inscrit une session et crée son entité. Lève `AlreadyConnectedError` ou `ZoneFullError`.

        L'entité apparaît à `position` si elle est libre, sinon au point d'apparition libre le plus
        proche (cf. `ZoneMap.resolve_spawn`).
        """
        if session.character_id in self._sessions:
            raise AlreadyConnectedError(session.character_id)
        if len(self._sessions) >= self.spec.max_players:
            raise ZoneFullError(self.spec.id)
        x, y = self.map.resolve_spawn(position, self.movement.player_half_size)
        self._entity_counter += 1
        player = PlayerEntity(
            entity_id=f"p{self._entity_counter}",
            character_id=session.character_id,
            name=name,
            x=x,
            y=y,
            aim=aim if math.isfinite(aim) else 0.0,
        )
        self._sessions[session.character_id] = session
        self._players[session.character_id] = player
        return player

    def unregister(self, session: ClientSession) -> PlayerEntity | None:
        """Désinscrit la session (si c'est bien celle enregistrée) et renvoie son entité retirée."""
        if self._sessions.get(session.character_id) is not session:
            return None
        del self._sessions[session.character_id]
        return self._players.pop(session.character_id, None)
