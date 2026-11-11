"""Tests de l'envoi non bloquant des sessions (file sortante, tâche d'écriture, 4009)."""

from __future__ import annotations

import asyncio
import json
from typing import cast

from starlette.websockets import WebSocket

from app.protocol.generated import PongPayload
from app.zone.session import CLOSE_TOO_SLOW, ClientSession


class BlockingWebSocket:
    """Client qui ne lit plus : chaque envoi après les `accept_sends` premiers reste bloqué."""

    def __init__(self, accept_sends: int = 0) -> None:
        self.accept_sends = accept_sends
        self.sent: list[str] = []
        self.close_code: int | None = None
        self.blocked = asyncio.Event()

    async def send_text(self, text: str) -> None:
        if len(self.sent) >= self.accept_sends:
            self.blocked.set()
            await asyncio.Event().wait()  # jamais levé
        self.sent.append(text)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.close_code = code


class BrokenWebSocket:
    async def send_text(self, text: str) -> None:
        raise RuntimeError("client parti")

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        raise RuntimeError("client parti")


def _pong(value: float) -> PongPayload:
    return PongPayload(client_time=value, server_time=0)


def _session(websocket: object, max_outgoing: int = 4) -> ClientSession:
    return ClientSession(
        cast(WebSocket, websocket), character_id="c1", tick_source=lambda: 7, max_outgoing=max_outgoing
    )


async def test_post_is_numbered_and_written_in_order() -> None:
    socket = BlockingWebSocket(accept_sends=100)
    session = _session(socket, max_outgoing=10)
    for value in range(3):
        assert session.post("pong", _pong(value))
    session.start_writer()
    session.close(4008, "fin")
    await asyncio.wait_for(session.closed.wait(), 1)
    messages = [json.loads(text) for text in socket.sent]
    assert [(m["seq"], m["tick"], m["d"]["client_time"]) for m in messages] == [
        (1, 7, 0),
        (2, 7, 1),
        (3, 7, 2),
    ]
    # Fermeture après écriture des messages en file ; plus rien n'est accepté ensuite.
    assert socket.close_code == 4008
    assert not session.post("pong", _pong(9))
    await session.shutdown()


async def test_slow_client_is_closed_with_4009_without_blocking() -> None:
    socket = BlockingWebSocket(accept_sends=1)
    session = _session(socket, max_outgoing=4)
    session.start_writer()
    assert session.post("pong", _pong(0))
    assert session.post("pong", _pong(1))
    await asyncio.wait_for(socket.blocked.wait(), 1)
    # Le premier message est écrit, le second bloque ; la file (4) se remplit sans jamais attendre.
    accepted = [session.post("pong", _pong(i)) for i in range(2, 8)]
    assert accepted == [True] * 4 + [False, False]
    assert session.close_code == CLOSE_TOO_SLOW
    await asyncio.wait_for(session.closed.wait(), 1)
    assert socket.close_code == CLOSE_TOO_SLOW
    assert len(socket.sent) == 1
    await session.shutdown()


async def test_writer_stops_when_client_is_gone() -> None:
    session = _session(BrokenWebSocket())
    session.start_writer()
    session.post("pong", _pong(0))
    await asyncio.wait_for(session.closed.wait(), 1)
    await session.shutdown()


async def test_shutdown_without_close_cancels_writer() -> None:
    socket = BlockingWebSocket(accept_sends=0)
    session = _session(socket)
    session.start_writer()
    session.post("pong", _pong(0))
    await asyncio.wait_for(socket.blocked.wait(), 1)
    await asyncio.wait_for(session.shutdown(), 1)
    assert session.closed.is_set()
    assert socket.close_code is None
