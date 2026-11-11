"""Exécution d'une zone : boucle de simulation à pas fixe et sessions connectées."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.protocol.codec import ClientEnvelope
from app.zone.session import ClientSession

if TYPE_CHECKING:
    from app.zone.manager import ZoneSpec

logger = logging.getLogger(__name__)

# Retard (en ticks) au-delà duquel la boucle abandonne le rattrapage et repart de maintenant.
MAX_CATCH_UP_TICKS = 5
# Code de fermeture standard « départ du serveur » (RFC 6455).
CLOSE_GOING_AWAY = 1001


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


class ZoneRuntime:
    """Une zone en cours d'exécution.

    La boucle avance la simulation `tick_rate` fois par seconde. Les échéances sont
    calculées depuis l'origine (`origin + n × période`) et non par cumul de `sleep`,
    ce qui évite toute dérive. Les messages de jeu des clients sont mis en file dans
    leur session et traités au tick suivant ; seul le transport (`ping`) est traité
    immédiatement par la passerelle.
    """

    def __init__(self, spec: ZoneSpec) -> None:
        self.spec = spec
        self.tick = 0
        self.stats = TickStats()
        self.period = 1.0 / spec.tick_rate
        self._sessions: dict[str, ClientSession] = {}
        self._task: asyncio.Task[None] | None = None

    # --- Cycle de vie -------------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Lance la boucle de tick dans la boucle asyncio courante."""
        if self._task is not None:
            raise RuntimeError(f"zone {self.spec.id} déjà démarrée")
        self._task = asyncio.create_task(self._run(), name=f"zone-tick:{self.spec.id}")

    async def stop(self) -> None:
        """Arrête la boucle puis ferme les connexions restantes."""
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for session in list(self._sessions.values()):
            # Le client peut déjà être parti : l'échec de fermeture est sans conséquence.
            with contextlib.suppress(Exception):
                await session.websocket.close(code=CLOSE_GOING_AWAY)
        self._sessions.clear()

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        origin = loop.time()
        step = 0
        while True:
            step += 1
            deadline = origin + step * self.period
            delay = deadline - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            elif -delay > MAX_CATCH_UP_TICKS * self.period:
                # Trop de retard (machine surchargée, pause du processus) : plutôt que d'enchaîner
                # des ticks en rafale, on repart de maintenant.
                self.stats.resyncs += 1
                logger.warning("zone %s : %.0f ms de retard, resynchronisation", self.spec.id, -delay * 1000)
                origin, step = loop.time(), 0
            started = time.perf_counter()
            try:
                self._step()
            except Exception:
                # Une erreur de simulation ne doit pas tuer la zone entière.
                logger.exception("zone %s : erreur au tick %d", self.spec.id, self.tick)
            self.stats.record((time.perf_counter() - started) * 1000, self.period * 1000)

    def _step(self) -> None:
        """Un pas de simulation."""
        self.tick += 1
        for session in self._sessions.values():
            for envelope in session.drain_inputs():
                self._handle_input(session, envelope)

    def _handle_input(self, session: ClientSession, envelope: ClientEnvelope) -> None:
        # Phase 1 : aucun message de jeu n'existe encore. La phase 2 y traitera `input`.
        logger.debug("zone %s : message %s de %s ignoré", self.spec.id, envelope.t, session.character_id)

    # --- Sessions ----------------------------------------------------------------------------

    @property
    def online_count(self) -> int:
        return len(self._sessions)

    def is_connected(self, character_id: str) -> bool:
        return character_id in self._sessions

    def register(self, session: ClientSession) -> None:
        """Inscrit une session. Lève `AlreadyConnectedError` ou `ZoneFullError`."""
        if session.character_id in self._sessions:
            raise AlreadyConnectedError(session.character_id)
        if len(self._sessions) >= self.spec.max_players:
            raise ZoneFullError(self.spec.id)
        self._sessions[session.character_id] = session

    def unregister(self, session: ClientSession) -> None:
        """Désinscrit la session si c'est bien celle enregistrée pour ce personnage."""
        if self._sessions.get(session.character_id) is session:
            del self._sessions[session.character_id]
