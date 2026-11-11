"""Session d'un client connecté à une zone."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable

from starlette.websockets import WebSocket

from app.protocol.codec import ClientEnvelope, encode_server
from app.protocol.generated import ProtocolModel, ServerMessageType

# Débit soutenu autorisé et rafale maximale (messages client).
DEFAULT_RATE_PER_SECOND = 30.0
DEFAULT_BURST = 30
# Messages de jeu en attente du prochain tick ; au-delà, le client est hors débit.
MAX_PENDING_INPUTS = 64


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
    """Un personnage connecté : envoi sérialisé, numérotation serveur, débit, file d'entrée.

    `tick_source` renvoie le tick courant de la zone, recopié dans chaque enveloppe envoyée.
    """

    def __init__(
        self,
        websocket: WebSocket,
        *,
        character_id: str,
        tick_source: Callable[[], int],
        rate_limiter: TokenBucket | None = None,
    ) -> None:
        self.websocket = websocket
        self.character_id = character_id
        self._tick_source = tick_source
        self._rate_limiter = rate_limiter or TokenBucket(DEFAULT_RATE_PER_SECOND, DEFAULT_BURST)
        self._send_lock = asyncio.Lock()
        self._seq = 0
        # Messages de jeu reçus, traités par la boucle de la zone au tick suivant (phase 2).
        self._inputs: deque[ClientEnvelope] = deque()
        # Messages refusés (débit, protocole) depuis l'ouverture de la connexion.
        self.rejected_count = 0

    @property
    def last_seq(self) -> int:
        """Dernier numéro de séquence serveur envoyé (0 si aucun)."""
        return self._seq

    async def send(self, t: ServerMessageType, payload: ProtocolModel) -> None:
        """Envoie un message ; les envois concurrents sont sérialisés et numérotés dans l'ordre."""
        async with self._send_lock:
            self._seq += 1
            text = encode_server(t, self._seq, self._tick_source(), payload)
            await self.websocket.send_text(text)

    def allow_message(self) -> bool:
        """Applique le limiteur de débit à un message entrant."""
        return self._rate_limiter.try_acquire()

    def enqueue_input(self, envelope: ClientEnvelope) -> bool:
        """Met un message de jeu en file pour le prochain tick. Renvoie False si la file est pleine."""
        if len(self._inputs) >= MAX_PENDING_INPUTS:
            return False
        self._inputs.append(envelope)
        return True

    def drain_inputs(self) -> list[ClientEnvelope]:
        """Retire et renvoie les messages en attente, dans l'ordre de réception."""
        pending = list(self._inputs)
        self._inputs.clear()
        return pending
