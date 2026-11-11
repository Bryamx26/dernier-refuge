"""Tests de la boucle de tick, du registre de sessions et du limiteur de débit."""

from __future__ import annotations

import asyncio
from typing import cast

import pytest
from starlette.websockets import WebSocket

from app.protocol.codec import ClientEnvelope
from app.protocol.generated import PingPayload
from app.zone.manager import ZoneManager, ZoneSpec
from app.zone.runtime import AlreadyConnectedError, ZoneFullError, ZoneRuntime
from app.zone.session import MAX_PENDING_INPUTS, ClientSession, TokenBucket


def _spec(*, tick_rate: int = 20, max_players: int = 2) -> ZoneSpec:
    return ZoneSpec(id="test", name="Test", max_players=max_players, tick_rate=tick_rate)


def _session(character_id: str) -> ClientSession:
    # Le WebSocket n'est pas utilisé par ces tests (aucun envoi).
    return ClientSession(cast(WebSocket, object()), character_id=character_id, tick_source=lambda: 0)


async def test_tick_advances_at_tick_rate() -> None:
    zone = ZoneRuntime(_spec(tick_rate=50))
    loop = asyncio.get_running_loop()
    zone.start()
    started = loop.time()
    await asyncio.sleep(0.5)
    elapsed = loop.time() - started
    await zone.stop()
    expected = elapsed * 50
    # Marge large pour les machines de CI chargées ; la dérive, elle, serait cumulative.
    assert expected * 0.8 <= zone.tick <= expected + 1
    assert zone.stats.count == zone.tick
    assert zone.stats.max_ms >= zone.stats.mean_ms >= 0


async def test_stop_is_clean_and_idempotent() -> None:
    zone = ZoneRuntime(_spec())
    zone.start()
    assert zone.running
    await asyncio.sleep(0.12)
    await zone.stop()
    assert not zone.running
    tick = zone.tick
    await asyncio.sleep(0.12)
    assert zone.tick == tick
    await zone.stop()


async def test_start_twice_is_refused() -> None:
    zone = ZoneRuntime(_spec())
    zone.start()
    try:
        with pytest.raises(RuntimeError):
            zone.start()
    finally:
        await zone.stop()


async def test_loop_survives_step_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    zone = ZoneRuntime(_spec(tick_rate=50))
    calls = 0

    def failing_step() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("boum")

    monkeypatch.setattr(zone, "_step", failing_step)
    zone.start()
    await asyncio.sleep(0.1)
    assert zone.running
    await zone.stop()
    assert calls >= 2


async def test_inputs_are_drained_on_tick() -> None:
    zone = ZoneRuntime(_spec())
    session = _session("c1")
    zone.register(session)
    assert session.enqueue_input(ClientEnvelope(t="ping", seq=1, payload=PingPayload(client_time=0)))
    zone._step()
    assert zone.tick == 1
    assert session.drain_inputs() == []


def test_input_queue_is_bounded() -> None:
    session = _session("c1")
    envelope = ClientEnvelope(t="ping", seq=1, payload=PingPayload(client_time=0))
    assert all(session.enqueue_input(envelope) for _ in range(MAX_PENDING_INPUTS))
    assert not session.enqueue_input(envelope)
    assert len(session.drain_inputs()) == MAX_PENDING_INPUTS


def test_register_rules() -> None:
    zone = ZoneRuntime(_spec(max_players=2))
    first = _session("c1")
    zone.register(first)
    with pytest.raises(AlreadyConnectedError):
        zone.register(_session("c1"))
    zone.register(_session("c2"))
    with pytest.raises(ZoneFullError):
        zone.register(_session("c3"))
    assert zone.online_count == 2

    # Désinscrire une session qui n'est pas celle enregistrée ne retire rien.
    zone.unregister(_session("c1"))
    assert zone.is_connected("c1")
    zone.unregister(first)
    assert not zone.is_connected("c1")
    assert zone.online_count == 1


async def test_manager_lifecycle() -> None:
    manager = ZoneManager()
    await manager.start([_spec()])
    zone = manager.get("test")
    assert zone is not None and zone.running
    assert manager.get("absente") is None
    assert manager.online_count("test") == 0
    assert manager.online_count("absente") == 0
    with pytest.raises(ValueError):
        await manager.start([_spec()])
    await manager.stop()
    assert not zone.running
    assert manager.get("test") is None


def test_token_bucket() -> None:
    now = 0.0
    bucket = TokenBucket(rate=30, capacity=30, clock=lambda: now)
    assert sum(bucket.try_acquire() for _ in range(40)) == 30
    now = 0.1  # 3 jetons regagnés
    assert sum(bucket.try_acquire() for _ in range(10)) == 3
    now = 100.0  # plafonné à la capacité
    assert sum(bucket.try_acquire() for _ in range(100)) == 30
