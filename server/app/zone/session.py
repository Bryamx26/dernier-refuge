"""Session d'un client connecté à une zone : débit entrant, file d'entrées, envoi non bloquant."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from collections.abc import Callable

from starlette.websockets import WebSocket

from app.protocol.codec import ClientEnvelope, encode_server
from app.protocol.generated import ProtocolModel, ServerMessageType

logger = logging.getLogger(__name__)

# Débit soutenu autorisé et rafale maximale (messages client).
DEFAULT_RATE_PER_SECOND = 60.0  # 20 input + 1 ping par seconde, avec marge pour les rafales
DEFAULT_BURST = 60
# Entrées de jeu en attente ; au-delà, les plus anciennes sont jetées (contrat phase 2).
MAX_PENDING_INPUTS = 64
# Messages serveur en attente d'écriture ; au-delà, le client est trop lent → fermeture 4009.
# 64 messages ≈ 3 s de snapshots à 20 Hz.
MAX_OUTGOING_MESSAGES = 64
# Délai laissé à l'écriture des derniers messages (et de la trame de fermeture) avant abandon.
FLUSH_TIMEOUT_S = 2.0
CLOSE_TOO_SLOW = 4009


class TokenBucket:
    """Limiteur de débit à seau de jetons."""

    def __init__(
        self,
        rate: float,
        capacity: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._rate = rate
        self._capacity = capacity
        self._clock = clock
        self._tokens = capacity
        self._updated = clock()

    def try_acquire(self) -> bool:
        """Consomme un jeton si disponible."""
        now = self._clock()
        self._tokens = min(self._capacity, self._tokens + (now - self._updated) * self._rate)
        self._updated = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False


class ClientSession:
    """Un personnage connecté.

    Envoi : `post*` sérialise et numérote le message puis le place dans une file bornée **sans
    jamais attendre** ; une tâche d'écriture (`start_writer`) la vide vers le WebSocket. Si la file
    est pleine (client qui ne lit pas assez vite), elle est vidée et la connexion fermée en 4009.
    La boucle de tick n'attend donc jamais un client.

    `tick_source` renvoie le tick courant de la zone, recopié dans chaque enveloppe envoyée.
    """

    def __init__(
        self,
        websocket: WebSocket,
        *,
        character_id: str,
        tick_source: Callable[[], int],
        rate_limiter: TokenBucket | None = None,
        max_outgoing: int | None = None,
    ) -> None:
        self.websocket = websocket
        self.character_id = character_id
        self._tick_source = tick_source
        self._rate_limiter = rate_limiter or TokenBucket(DEFAULT_RATE_PER_SECOND, DEFAULT_BURST)
        self._seq = 0
        # Entrées de jeu reçues, consommées par la zone (au plus `max_inputs_per_tick` par tick).
        self.pending_inputs: deque[ClientEnvelope] = deque(maxlen=MAX_PENDING_INPUTS)
        self.dropped_inputs = 0
        # Messages refusés (débit, protocole) depuis l'ouverture de la connexion.
        self.rejected_count = 0

        # Lu à la construction (et non à la définition) : les tests peuvent abaisser la constante.
        self._max_outgoing = max_outgoing if max_outgoing is not None else MAX_OUTGOING_MESSAGES
        self._outbox: deque[str] = deque()
        self._wakeup = asyncio.Event()
        self._writer: asyncio.Task[None] | None = None
        self._sending: asyncio.Task[None] | None = None
        # Fermeture demandée : (code, raison). Plus aucun message n'est accepté ensuite.
        self._close_request: tuple[int, str] | None = None
        # Levé quand la tâche d'écriture se termine (fermeture envoyée ou client parti).
        self.closed = asyncio.Event()

    # --- Envoi -------------------------------------------------------------------------------

    @property
    def last_seq(self) -> int:
        """Dernier numéro de séquence serveur attribué (0 si aucun)."""
        return self._seq

    @property
    def close_code(self) -> int | None:
        """Code de fermeture demandé, s'il y en a un."""
        return self._close_request[0] if self._close_request is not None else None

    def post(self, t: ServerMessageType, payload: ProtocolModel) -> bool:
        """Met un message en file d'envoi ; renvoie False s'il est abandonné (file pleine ou fermeture)."""
        return self.post_encoded(lambda seq, tick: encode_server(t, seq, tick, payload))

    def post_encoded(self, build: Callable[[int, int], str]) -> bool:
        """Comme `post`, avec une fonction `build(seq, tick) -> texte` (sérialisation optimisée)."""
        if self._close_request is not None:
            return False
        if len(self._outbox) >= self._max_outgoing:
            self._overflow()
            return False
        self._seq += 1
        self._outbox.append(build(self._seq, self._tick_source()))
        self._wakeup.set()
        return True

    def close(self, code: int, reason: str = "") -> None:
        """Demande la fermeture après écriture des messages déjà en file."""
        if self._close_request is None:
            self._close_request = (code, reason)
            self._wakeup.set()

    def _overflow(self) -> None:
        logger.warning("connexion de %s fermée : client trop lent (file sortante pleine)", self.character_id)
        self._outbox.clear()
        self._close_request = (CLOSE_TOO_SLOW, "client trop lent")
        # L'écriture en cours est probablement bloquée sur ce client : on l'abandonne.
        if self._sending is not None:
            self._sending.cancel()
        self._wakeup.set()

    def drain_outbox(self) -> list[str]:
        """Retire et renvoie les messages en attente (tests et outils, sans tâche d'écriture)."""
        pending = list(self._outbox)
        self._outbox.clear()
        return pending

    def start_writer(self) -> None:
        """Lance la tâche d'écriture dans la boucle courante."""
        if self._writer is None:
            self._writer = asyncio.create_task(self._write_loop(), name=f"ws-writer:{self.character_id}")

    async def _write_loop(self) -> None:
        try:
            while True:
                if self._outbox:
                    send = asyncio.create_task(self.websocket.send_text(self._outbox.popleft()))
                    self._sending = send
                    try:
                        await asyncio.wait({send})
                    finally:
                        self._sending = None
                        send.cancel()
                    if not send.cancelled() and send.exception() is not None:
                        return  # client parti : rien de plus à écrire
                    continue
                if self._close_request is not None:
                    code, reason = self._close_request
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(self.websocket.close(code, reason), FLUSH_TIMEOUT_S)
                    return
                self._wakeup.clear()
                await self._wakeup.wait()
        finally:
            self.closed.set()

    def abort(self) -> None:
        """Annule la tâche d'écriture sans attendre (filet de sécurité si `shutdown` est interrompu)."""
        if self._writer is not None and not self._writer.done():
            self._writer.cancel()

    async def shutdown(self) -> None:
        """Termine la tâche d'écriture : laisse finir une fermeture demandée, abandonne le reste."""
        writer = self._writer
        if writer is None:
            self.closed.set()
            return
        if self._close_request is not None and not writer.done():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(writer), FLUSH_TIMEOUT_S)
        writer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await writer

    # --- Réception ---------------------------------------------------------------------------

    def allow_message(self) -> bool:
        """Applique le limiteur de débit à un message entrant."""
        return self._rate_limiter.try_acquire()

    def enqueue_input(self, envelope: ClientEnvelope) -> None:
        """Met une entrée de jeu en file ; si la file est pleine, la plus ancienne est jetée."""
        if len(self.pending_inputs) == self.pending_inputs.maxlen:
            self.dropped_inputs += 1
        self.pending_inputs.append(envelope)
