"""Tests de la boucle de tick, de la simulation des joueurs et de l'intérêt spatial."""

from __future__ import annotations

import asyncio
import json
import math
import random
import time
from typing import Any, cast

import pytest
from starlette.websockets import WebSocket

from app.protocol.codec import ClientEnvelope
from app.protocol.generated import InputPayload, PingPayload, SnapshotPayload
from app.zone.manager import ZoneManager, ZoneSpec
from app.zone.movement import CollisionGrid, MovementConfig
from app.zone.persistence import CharacterRecord, SavedCharacter
from app.zone.runtime import (
    INPUT_CATCHUP_MARGIN,
    AlreadyConnectedError,
    PlayerEntity,
    ZoneFullError,
    ZoneRuntime,
)
from app.zone.session import MAX_PENDING_INPUTS, ClientSession, TokenBucket
from app.zone.tilemap import MapLoadError, ZoneMap

CFG = MovementConfig.load()
DT = 0.05


class MemoryStore:
    """`PlayerStore` en mémoire."""

    def __init__(self) -> None:
        self.saves: list[list[SavedCharacter]] = []

    async def load_character(self, character_id: str) -> CharacterRecord | None:
        return None

    async def save_characters(self, positions: list[SavedCharacter]) -> None:
        self.saves.append(list(positions))


class FakeWebSocket:
    """WebSocket factice : enregistre les envois et la fermeture."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.close_code: int | None = None

    async def send_text(self, text: str) -> None:
        self.sent.append(text)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.close_code = code


def _spec(*, tick_rate: int = 20, max_players: int = 2) -> ZoneSpec:
    return ZoneSpec(id="test", name="Test", max_players=max_players, tick_rate=tick_rate)


def _zone(rows: list[str] | None = None, *, max_players: int = 64, **kwargs: Any) -> ZoneRuntime:
    zone_map = None
    if rows is not None:
        zone_map = ZoneMap(map_id="t", grid=CollisionGrid.from_rows(rows), spawns=[(1.5, 1.5)])
    return ZoneRuntime(_spec(max_players=max_players), zone_map=zone_map, movement=CFG, **kwargs)


def _session(character_id: str) -> ClientSession:
    return ClientSession(
        cast(WebSocket, FakeWebSocket()),
        character_id=character_id,
        tick_source=lambda: 0,
        max_outgoing=10_000,
    )


def _input(seq: int, move_x: float = 0.0, move_y: float = 0.0, *, sprint: bool = False) -> ClientEnvelope:
    return ClientEnvelope(
        t="input",
        seq=seq,
        payload=InputPayload(move_x=move_x, move_y=move_y, aim=0.5, sprint=sprint, attack=False),
    )


def _snapshots(session: ClientSession) -> list[dict[str, Any]]:
    # Les messages de jeu (vitals, inventory, notice, fx) sont ignorés ici.
    messages = [m for m in (json.loads(text) for text in session.drain_outbox()) if m["t"] == "snapshot"]
    for m in messages:
        SnapshotPayload.model_validate(m["d"])  # conforme au schéma
    return messages


def _anim(player: PlayerEntity) -> str:
    # Lecture via une fonction : évite le rétrécissement de type de mypy entre deux ticks.
    return player.anim


def _visible(session: ClientSession) -> dict[str, dict[str, Any]]:
    """Entités du dernier snapshot reçu, par nom."""
    last = _snapshots(session)[-1]
    return {entity["name"]: entity for entity in last["d"]["entities"]}


# --- Boucle de tick -----------------------------------------------------------------------------


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


# --- Sessions -----------------------------------------------------------------------------------


def test_input_queue_drops_oldest() -> None:
    session = _session("c1")
    for seq in range(1, MAX_PENDING_INPUTS + 11):
        session.enqueue_input(_input(seq))
    assert len(session.pending_inputs) == MAX_PENDING_INPUTS
    assert session.dropped_inputs == 10
    assert session.pending_inputs[0].seq == 11


def test_register_rules() -> None:
    zone = _zone(max_players=2)
    first = _session("c1")
    player = zone.register(first, name="Alice", position=(10.0, 12.0), aim=1.0)
    assert (player.x, player.y, player.aim, player.name) == (10.0, 12.0, 1.0, "Alice")
    with pytest.raises(AlreadyConnectedError):
        zone.register(_session("c1"))
    second = zone.register(_session("c2"))
    assert second.entity_id != player.entity_id
    with pytest.raises(ZoneFullError):
        zone.register(_session("c3"))
    assert zone.online_count == 2

    # Désinscrire une session qui n'est pas celle enregistrée ne retire rien.
    assert zone.unregister(_session("c1")) is None
    assert zone.is_connected("c1")
    assert zone.unregister(first) is player
    assert not zone.is_connected("c1")
    assert zone.player(first) is None
    assert zone.online_count == 1


def test_spawn_in_wall_uses_nearest_spawn() -> None:
    rows = ["#########", "#.......#", "#..###..#", "#.......#", "#########"]
    grid = CollisionGrid.from_rows(rows)
    zone = ZoneRuntime(
        _spec(), zone_map=ZoneMap(map_id="t", grid=grid, spawns=[(1.5, 1.5), (7.5, 3.5)]), movement=CFG
    )
    in_wall = zone.register(_session("a"), position=(5.4, 2.5))
    assert (in_wall.x, in_wall.y) == (7.5, 3.5)
    free = zone.register(_session("b"), position=(2.0, 3.0))
    assert (free.x, free.y) == (2.0, 3.0)


# --- Simulation ---------------------------------------------------------------------------------


def test_inputs_move_player_and_ack() -> None:
    zone = _zone()
    session = _session("c1")
    player = zone.register(session, name="Alice", position=(10.0, 10.0))
    zone._step()
    first = _snapshots(session)[-1]["d"]
    assert first["ack_seq"] == 0
    assert first["entities"] == [
        {
            "id": player.entity_id,
            "kind": "player",
            "name": "Alice",
            "x": 10.0,
            "y": 10.0,
            "aim": 0.0,
            "anim": "idle",
            "health": 1.0,
        }
    ]

    session.enqueue_input(_input(1, 1.0, 0.0))
    zone._step()
    snapshot = _snapshots(session)[-1]["d"]
    assert snapshot["ack_seq"] == 1
    me = snapshot["entities"][0]
    assert me["x"] == pytest.approx(10.0 + CFG.walk_speed * DT)
    assert (me["aim"], me["anim"]) == (0.5, "walk")
    # Les messages non-`input` éventuellement en file sont ignorés.
    session.enqueue_input(ClientEnvelope(t="ping", seq=2, payload=PingPayload(client_time=0)))
    zone._step()
    assert _snapshots(session)[-1]["d"]["ack_seq"] == 1


def test_anti_speedhack_three_inputs_per_tick() -> None:
    zone = _zone()
    session = _session("c1")
    player = zone.register(session, position=(10.0, 10.0))
    for seq in range(1, 11):
        session.enqueue_input(_input(seq, 1.0, 0.0, sprint=True))
    zone._step()
    assert player.ack_seq == CFG.max_inputs_per_tick == 3
    assert player.x == pytest.approx(10.0 + 3 * CFG.sprint_speed * DT)
    assert len(session.pending_inputs) == 7
    for _ in range(3):
        zone._step()
    assert player.ack_seq == 10
    assert player.x == pytest.approx(10.0 + 10 * CFG.sprint_speed * DT)
    assert [s["d"]["ack_seq"] for s in _snapshots(session)] == [3, 6, 9, 10]


def test_stale_and_duplicate_inputs_are_ignored() -> None:
    zone = _zone()
    session = _session("c1")
    player = zone.register(session, position=(10.0, 10.0))
    for seq in (5, 5, 3, 0, 6):
        session.enqueue_input(_input(seq, 1.0, 0.0))
    zone._step()
    # 5 et 6 appliquées ; les doublons et retours en arrière ne comptent pas dans la limite.
    assert player.ack_seq == 6
    assert player.x == pytest.approx(10.0 + 2 * CFG.walk_speed * DT)


def test_wall_is_impassable_with_extreme_inputs() -> None:
    rows = ["..........", "......#...", "......#...", "......#...", ".........."]
    zone = _zone(rows)
    session = _session("c1")
    player = zone.register(session, position=(2.5, 2.5))
    seq = 0
    for _ in range(100):
        for _ in range(MAX_PENDING_INPUTS):
            seq += 1
            session.enqueue_input(_input(seq, 1.0, 0.0, sprint=True))
        zone._step()
        assert player.x <= 6.0 - CFG.player_half_size
    assert player.x == 6.0 - CFG.player_half_size
    # Bord de carte : impossible de sortir.
    for _ in range(200):
        seq += 1
        session.enqueue_input(_input(seq, 0.0, -1.0, sprint=True))
        zone._step()
    assert player.y == CFG.player_half_size


def test_anim_states() -> None:
    zone = _zone(["....", "...."])
    session = _session("c1")
    player = zone.register(session, position=(1.5, 1.0))
    session.enqueue_input(_input(1, 1.0, 0.0, sprint=True))
    zone._step()
    assert _anim(player) == "run"
    session.enqueue_input(_input(2, 1.0, 0.0))
    zone._step()
    assert _anim(player) == "walk"
    # Contre le bord : l'entrée n'a pas déplacé le joueur → idle.
    for seq in range(3, 30):
        session.enqueue_input(_input(seq, 1.0, 0.0))
        zone._step()
    assert _anim(player) == "idle"
    session.enqueue_input(_input(30, -1.0, 0.0))
    zone._step()
    assert _anim(player) == "walk"
    # Sans entrée : reste `walk` quelques ticks (gigue réseau), puis `idle`.
    zone._step()
    assert _anim(player) == "walk"
    for _ in range(5):
        zone._step()
    assert _anim(player) == "idle"


def test_two_players_see_each_other_moving() -> None:
    zone = _zone()
    alice, bob = _session("a"), _session("b")
    zone.register(alice, name="Alice", position=(10.0, 10.0))
    zone.register(bob, name="Bob", position=(14.0, 10.0))
    zone._step()
    assert set(_visible(alice)) == set(_visible(bob)) == {"Alice", "Bob"}
    alice.enqueue_input(_input(1, 0.0, 1.0))
    zone._step()
    seen = _visible(bob)["Alice"]
    assert seen["y"] == pytest.approx(10.0 + CFG.walk_speed * DT)
    assert seen["anim"] == "walk"


def test_interest_radius() -> None:
    radius = CFG.interest_radius
    zone = ZoneRuntime(_spec(max_players=8), zone_map=ZoneMap.open_area("t", 256), movement=CFG)
    center = _session("centre")
    zone.register(center, name="centre", position=(100.0, 100.0))
    zone.register(_session("dedans"), name="dedans", position=(100.0 + radius - 0.01, 100.0))
    zone.register(_session("limite"), name="limite", position=(100.0, 100.0 - radius))
    zone.register(_session("dehors"), name="dehors", position=(100.0 + radius * 0.75, 100.0 + radius * 0.75))
    zone.register(_session("loin"), name="loin", position=(10.0, 10.0))
    zone._step()
    assert set(_visible(center)) == {"centre", "dedans", "limite"}


def test_interest_matches_brute_force() -> None:
    rng = random.Random(7)
    zone = ZoneRuntime(_spec(max_players=60), zone_map=ZoneMap.open_area("t", 200), movement=CFG)
    sessions: dict[str, ClientSession] = {}
    positions: dict[str, tuple[float, float]] = {}
    for index in range(60):
        name = f"j{index}"
        sessions[name] = _session(name)
        positions[name] = (rng.uniform(1, 199), rng.uniform(1, 199))
        zone.register(sessions[name], name=name, position=positions[name])
    zone._step()
    r2 = CFG.interest_radius**2
    for name, session in sessions.items():
        x, y = positions[name]
        expected = {o for o, (ox, oy) in positions.items() if (ox - x) ** 2 + (oy - y) ** 2 <= r2}
        assert set(_visible(session)) == expected


# --- Persistance --------------------------------------------------------------------------------


async def test_autosave_and_stop_save_positions() -> None:
    store = MemoryStore()
    zone = _zone(store=store, autosave_interval=0.05)
    socket = FakeWebSocket()
    session = ClientSession(cast(WebSocket, socket), character_id="c1", tick_source=lambda: zone.tick)
    zone.register(session, position=(10.0, 10.0), aim=0.25)
    session.start_writer()
    zone.start()
    await asyncio.sleep(0.18)
    assert len(store.saves) >= 2
    saved = store.saves[0]
    assert len(saved) == 1
    assert (saved[0].character_id, saved[0].x, saved[0].y, saved[0].facing) == ("c1", 10.0, 10.0, 0.25)
    assert saved[0].inventory["slots"], "équipement de départ sauvegardé"
    count = len(store.saves)
    await zone.stop()
    # Sauvegarde finale à l'arrêt, puis fermeture 1001 après les snapshots déjà en file.
    assert len(store.saves) == count + 1
    assert socket.close_code == 1001
    kinds = {json.loads(text)["t"] for text in socket.sent}
    assert "snapshot" in kinds and kinds <= {"snapshot", "vitals", "inventory"}
    assert zone.online_count == 0


# --- Gestionnaire -------------------------------------------------------------------------------


async def test_manager_lifecycle() -> None:
    manager = ZoneManager()
    await manager.start([_spec()])
    zone = manager.get("test")
    assert zone is not None and zone.running
    assert zone.map.map_id == "test"
    assert manager.get("absente") is None
    assert manager.online_count("test") == 0
    assert manager.online_count("absente") == 0
    with pytest.raises(ValueError):
        await manager.start([_spec()])
    await manager.stop()
    assert not zone.running
    assert manager.get("test") is None


async def test_manager_requires_map(tmp_path: Any) -> None:
    spec = ZoneSpec(id="z", name="Z", max_players=4, tick_rate=20, map_file="maps/absente.tmj")
    manager = ZoneManager(data_dir=tmp_path)
    # Le fichier de constantes est lu dans le dossier de données : on le fournit.
    (tmp_path / "shared" / "movement").mkdir(parents=True)
    (tmp_path / "shared" / "movement" / "movement.json").write_text(
        json.dumps(
            {
                "walk_speed": 3,
                "sprint_speed": 5,
                "player_half_size": 0.3,
                "max_inputs_per_tick": 3,
                "interest_radius": 32,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(MapLoadError, match="introuvable"):
        await manager.start([spec])
    assert manager.get("z") is None

    lenient = ZoneManager(data_dir=tmp_path, allow_missing_maps=True)
    await lenient.start([spec])
    zone = lenient.get("z")
    assert zone is not None and zone.map.map_id == "absente" and zone.map.width == 128
    await lenient.stop()


def test_token_bucket() -> None:
    now = 0.0
    bucket = TokenBucket(rate=30, capacity=30, clock=lambda: now)
    assert sum(bucket.try_acquire() for _ in range(40)) == 30
    now = 0.1  # 3 jetons regagnés
    assert sum(bucket.try_acquire() for _ in range(10)) == 3
    now = 100.0  # plafonné à la capacité
    assert sum(bucket.try_acquire() for _ in range(100)) == 30


# --- Performance --------------------------------------------------------------------------------


def measure_tick_ms(players: int = 50, ticks: int = 200, *, spread: float = 24.0) -> float:
    """Tick moyen (ms) : `players` joueurs groupés (tous se voient), une entrée chacun par tick."""
    rng = random.Random(3)
    zone = ZoneRuntime(_spec(max_players=players), zone_map=ZoneMap.open_area("perf", 128), movement=CFG)
    sessions = []
    for index in range(players):
        session = _session(f"c{index}")
        zone.register(
            session,
            name=f"Joueur{index}",
            position=(64 + rng.uniform(-spread, spread) / 2, 64 + rng.uniform(-spread, spread) / 2),
        )
        sessions.append(session)
    total = 0.0
    for tick in range(1, ticks + 1):
        for session in sessions:
            angle = rng.uniform(0, 2 * math.pi)
            session.enqueue_input(_input(tick, math.cos(angle), math.sin(angle), sprint=tick % 2 == 0))
        started = time.perf_counter()
        zone._step()
        total += time.perf_counter() - started
        for session in sessions:
            session.drain_outbox()
    return total / ticks * 1000


def test_tick_performance_50_players() -> None:
    mean_ms = measure_tick_ms()
    print(f"\ntick moyen, 50 joueurs se voyant tous : {mean_ms:.3f} ms")
    # Budget : 50 ms par tick à 20 Hz ; marge très large pour les CI lentes.
    assert mean_ms < 25.0


def test_sustained_burst_is_bounded_by_cumulative_budget() -> None:
    """QA-P2-01 : 3 entrées par tick en continu ne dépassent pas ticks écoulés + marge."""
    zone = _zone()
    session = _session("c1")
    player = zone.register(session, position=(10.0, 10.0))
    seq = 0
    for _ in range(60):
        for _ in range(3):
            seq += 1
            session.enqueue_input(_input(seq, 0.0, 0.0))
        zone._step()
    assert player.inputs_applied == 60 + INPUT_CATCHUP_MARGIN


def test_honest_client_catches_up_after_network_freeze() -> None:
    """QA-P2-08 : après 1 s sans rien recevoir, les 20 entrées en retard sont rattrapées."""
    zone = _zone()
    session = _session("c1")
    player = zone.register(session, position=(10.0, 10.0))
    seq = 0
    for _ in range(20):  # une entrée par tick
        seq += 1
        session.enqueue_input(_input(seq, 0.0, 0.0))
        zone._step()
    for _ in range(20):  # gel : rien n'arrive
        zone._step()
    for _ in range(20):  # tout arrive d'un coup
        seq += 1
        session.enqueue_input(_input(seq, 0.0, 0.0))
    for _ in range(10):  # puis le client reprend son rythme
        seq += 1
        session.enqueue_input(_input(seq, 0.0, 0.0))
        zone._step()
    assert player.ack_seq == seq
    assert not session.pending_inputs


async def test_attack_fx_and_game_messages_reach_the_client() -> None:
    """Régression : les effets émis pendant les entrées (coup) sont envoyés, puis vidés."""
    zone = _zone()
    socket = FakeWebSocket()
    session = ClientSession(cast(WebSocket, socket), character_id="c1", tick_source=lambda: zone.tick)
    player = zone.register(session, position=(10.0, 10.0))
    assert player.survivor.inventory.equipped >= 0, "arme de départ en main"
    session.enqueue_input(
        ClientEnvelope(
            t="input", seq=1, payload=InputPayload(move_x=0, move_y=0, aim=0.0, sprint=False, attack=True)
        )
    )
    zone._step()
    kinds = [json.loads(text)["t"] for text in session.drain_outbox()]
    assert {"snapshot", "inventory", "vitals", "fx"} <= set(kinds)
    assert zone.game.fx == []
