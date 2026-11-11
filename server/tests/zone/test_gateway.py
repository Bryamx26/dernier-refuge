"""Tests de bout en bout du WebSocket de zone (ticket REST → WebSocket → simulation)."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import time
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.api.characters import DEFAULT_ZONE_ID
from app.db.models import Account, Character
from app.protocol.generated import PROTOCOL_VERSION, SnapshotPayload
from app.zone import session as session_module
from app.zone.gateway import MAX_REJECTED_MESSAGES
from app.zone.manager import ZoneManager
from app.zone.movement import MovementConfig
from tests.zone.conftest import TEST_SPAWNS, IssueTicket, NewPlayer, RunDb

ZONE_ID = DEFAULT_ZONE_ID
CFG = MovementConfig.load()
STEP = CFG.walk_speed / 20  # un pas de marche à 20 Hz


def _url(ticket: str, zone_id: str = ZONE_ID) -> str:
    return f"/ws/zone/{zone_id}?ticket={ticket}"


def _zones(client: TestClient) -> ZoneManager:
    zones: ZoneManager = client.app.state.zones  # type: ignore[attr-defined]
    return zones


def _input(seq: int, move_x: float = 0.0, move_y: float = 0.0, *, aim: float = 0.0) -> str:
    return json.dumps(
        {
            "t": "input",
            "seq": seq,
            "d": {"move_x": move_x, "move_y": move_y, "aim": aim, "sprint": False, "attack": False},
        }
    )


class Reader:
    """Lit les messages d'une connexion en vérifiant l'enveloppe et la continuité des `seq`."""

    def __init__(self, ws: WebSocketTestSession) -> None:
        self.ws = ws
        self.seq = 0

    def next(self) -> dict[str, Any]:
        message: dict[str, Any] = self.ws.receive_json()
        assert set(message) == {"t", "seq", "tick", "d"}
        assert message["seq"] == self.seq + 1
        self.seq = message["seq"]
        if message["t"] == "snapshot":
            SnapshotPayload.model_validate(message["d"])
        return message

    def next_other(self) -> dict[str, Any]:
        """Prochain message qui n'est pas un snapshot."""
        while True:
            message = self.next()
            if message["t"] not in ("snapshot", "vitals", "inventory", "notice", "fx"):
                return message

    def snapshot(self, predicate: Callable[[dict[str, Any]], bool] = lambda d: True) -> dict[str, Any]:
        """Prochain snapshot (charge utile) vérifiant `predicate`."""
        for _ in range(400):
            message = self.next()
            if message["t"] == "snapshot" and predicate(message["d"]):
                return dict(message["d"])
        raise AssertionError("snapshot attendu non reçu")


def _entity(snapshot: dict[str, Any], name: str) -> dict[str, Any] | None:
    return next((e for e in snapshot["entities"] if e["name"] == name), None)


def _expect_close(client: TestClient, url: str, code: int) -> None:
    with pytest.raises(WebSocketDisconnect) as info, client.websocket_connect(url) as ws:
        ws.receive_json()
    assert info.value.code == code


def _wait_offline(client: TestClient, timeout: float = 3.0) -> None:
    """Attend que la passerelle ait fini de traiter la déconnexion (sauvegarde comprise)."""
    deadline = time.monotonic() + timeout
    while _zones(client).online_count(ZONE_ID) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert _zones(client).online_count(ZONE_ID) == 0


# --- Connexion ----------------------------------------------------------------------------------


def test_welcome_snapshot_ping_and_error(zone_client: TestClient, join_ticket: IssueTicket) -> None:
    ticket, character_id = join_ticket()
    with zone_client.websocket_connect(_url(ticket)) as ws:
        reader = Reader(ws)
        welcome = reader.next()
        assert welcome["t"] == "welcome"
        assert welcome["seq"] == 1
        d = welcome["d"]
        assert d["protocol_version"] == PROTOCOL_VERSION == 3
        assert (d["zone_id"], d["character_id"], d["map_id"], d["tick_rate"]) == (
            ZONE_ID,
            character_id,
            "valcendre",
            20,
        )
        assert d["entity_id"] and d["server_time"] > 0
        assert _zones(zone_client).online_count(ZONE_ID) == 1

        # Premier snapshot : le joueur lui-même, nouveau personnage placé sur un point d'apparition
        # de la carte (QA-P2-03), sans entrée acquittée.
        snapshot = reader.snapshot()
        assert snapshot["ack_seq"] == 0
        [me] = snapshot["entities"]
        assert (me["x"], me["y"]) in TEST_SPAWNS
        assert me == {
            "id": d["entity_id"],
            "kind": "player",
            "name": "Alice",
            "x": me["x"],
            "y": me["y"],
            "aim": 0.0,
            "anim": "idle",
            "health": 1.0,
        }

        ws.send_text(json.dumps({"t": "ping", "seq": 1, "d": {"client_time": 123.5}}))
        pong = reader.next_other()
        assert pong["t"] == "pong"
        assert pong["d"]["client_time"] == 123.5
        assert pong["d"]["server_time"] >= d["server_time"]

        ws.send_text("pas du json")
        assert reader.next_other()["d"]["code"] == "bad_message"
        ws.send_text(json.dumps({"t": "teleport", "seq": 2, "d": {}}))
        assert reader.next_other()["d"]["code"] == "unknown_type"
        # Bornes du schéma `input`.
        ws.send_text(_input(3, move_x=1.5))
        assert reader.next_other()["d"]["code"] == "bad_message"

        # La connexion reste ouverte après une erreur.
        ws.send_text(json.dumps({"t": "ping", "seq": 4, "d": {"client_time": 1}}))
        assert reader.next_other()["t"] == "pong"

    _wait_offline(zone_client)


def test_reused_ticket_is_refused(zone_client: TestClient, join_ticket: IssueTicket) -> None:
    ticket, _ = join_ticket()
    with zone_client.websocket_connect(_url(ticket)) as ws:
        assert Reader(ws).next()["t"] == "welcome"
    _expect_close(zone_client, _url(ticket), 4001)


@pytest.mark.parametrize("query", ["", "?ticket=", "?ticket=inconnu"])
def test_missing_or_invalid_ticket(zone_client: TestClient, query: str) -> None:
    _expect_close(zone_client, f"/ws/zone/{ZONE_ID}{query}", 4001)


@pytest.mark.parametrize("reason", ["dead", "banned"])
def test_dead_character_or_banned_account(
    zone_client: TestClient, join_ticket: IssueTicket, run_db: RunDb[Any], reason: str
) -> None:
    # Le ticket est émis avant la mort / la suspension : c'est la passerelle qui refuse.
    ticket, character_id = join_ticket()
    key = uuid.UUID(character_id)

    async def mutate(session: AsyncSession) -> None:
        if reason == "dead":
            await session.execute(update(Character).where(Character.id == key).values(is_dead=True))
        else:
            character = await session.get(Character, key)
            assert character is not None
            await session.execute(
                update(Account).where(Account.id == character.account_id).values(is_banned=True)
            )

    run_db(mutate)
    _expect_close(zone_client, _url(ticket), 4001)
    assert _zones(zone_client).online_count(ZONE_ID) == 0


def test_double_connection_is_refused(zone_client: TestClient, join_ticket: IssueTicket) -> None:
    first_ticket, _ = join_ticket()
    with zone_client.websocket_connect(_url(first_ticket)) as ws:
        reader = Reader(ws)
        assert reader.next()["t"] == "welcome"
        second_ticket, _ = join_ticket()
        _expect_close(zone_client, _url(second_ticket), 4002)
        # La première connexion n'est pas affectée.
        ws.send_text(json.dumps({"t": "ping", "seq": 1, "d": {"client_time": 1}}))
        assert reader.next_other()["t"] == "pong"
        assert _zones(zone_client).online_count(ZONE_ID) == 1


def test_unknown_zone(zone_client: TestClient, join_ticket: IssueTicket) -> None:
    ticket, _ = join_ticket()
    _expect_close(zone_client, _url(ticket, zone_id="atlantide"), 4004)
    # Le ticket n'a pas été consommé par la tentative sur une zone inconnue.
    with zone_client.websocket_connect(_url(ticket)) as ws:
        assert Reader(ws).next()["t"] == "welcome"


def test_full_zone(zone_client: TestClient, join_ticket: IssueTicket) -> None:
    zone = _zones(zone_client).get(ZONE_ID)
    assert zone is not None
    zone.spec = dataclasses.replace(zone.spec, max_players=0)
    ticket, _ = join_ticket()
    _expect_close(zone_client, _url(ticket), 4003)


# --- Abus ---------------------------------------------------------------------------------------


def test_abuse_closes_connection(zone_client: TestClient, join_ticket: IssueTicket) -> None:
    ticket, _ = join_ticket()
    with pytest.raises(WebSocketDisconnect) as info, zone_client.websocket_connect(_url(ticket)) as ws:
        reader = Reader(ws)
        assert reader.next()["t"] == "welcome"
        for _ in range(MAX_REJECTED_MESSAGES):
            ws.send_text("{}")
        for _ in range(MAX_REJECTED_MESSAGES - 1):
            assert reader.next_other()["t"] == "error"
        reader.next_other()
    assert info.value.code == 4008
    _wait_offline(zone_client)


def test_rate_limit(zone_client: TestClient, join_ticket: IssueTicket) -> None:
    ticket, _ = join_ticket()
    ping = json.dumps({"t": "ping", "seq": 1, "d": {"client_time": 1}})
    with zone_client.websocket_connect(_url(ticket)) as ws:
        reader = Reader(ws)
        assert reader.next()["t"] == "welcome"
        # Rafale bien supérieure au seau (60 jetons) : une partie est refusée.
        burst = 80
        for _ in range(burst):
            ws.send_text(ping)
        replies = [reader.next_other() for _ in range(burst)]
        limited = [r for r in replies if r["t"] == "error"]
        assert limited and all(r["d"]["code"] == "rate_limited" for r in limited)
        assert len(replies) - len(limited) >= 60


# --- Simulation ---------------------------------------------------------------------------------


def test_input_is_acknowledged_in_snapshot(zone_client: TestClient, join_ticket: IssueTicket) -> None:
    ticket, _ = join_ticket()
    with zone_client.websocket_connect(_url(ticket)) as ws:
        reader = Reader(ws)
        assert reader.next()["t"] == "welcome"
        start = _entity(reader.snapshot(), "Alice")
        assert start is not None
        for seq in (1, 2, 3, 4):
            ws.send_text(_input(seq, move_x=1.0, aim=0.5))
        snapshot = reader.snapshot(lambda d: d["ack_seq"] == 4)
        me = _entity(snapshot, "Alice")
        assert me is not None
        assert me["x"] == pytest.approx(start["x"] + 4 * STEP, abs=1e-9)
        assert me["y"] == start["y"]
        assert me["aim"] == 0.5


def test_two_clients_see_each_other_move(
    zone_client: TestClient, join_ticket: IssueTicket, new_player: NewPlayer
) -> None:
    alice_ticket, _ = join_ticket()
    bob_ticket, _ = new_player("second", "Bob")()
    with (
        zone_client.websocket_connect(_url(alice_ticket)) as alice_ws,
        zone_client.websocket_connect(_url(bob_ticket)) as bob_ws,
    ):
        alice, bob = Reader(alice_ws), Reader(bob_ws)
        alice_id = alice.next()["d"]["entity_id"]
        bob_id = bob.next()["d"]["entity_id"]
        assert alice_id != bob_id
        # Chacun voit l'autre : on les place au même endroit (les nouveaux personnages
        # apparaissent sur des points tirés au hasard, parfois hors du rayon d'intérêt).
        zone = _zones(zone_client).get(ZONE_ID)
        assert zone is not None
        for player in zone._players.values():
            player.x, player.y = TEST_SPAWNS[0]
        seen = alice.snapshot(lambda d: _entity(d, "Bob") is not None)
        assert {e["id"] for e in seen["entities"]} == {alice_id, bob_id}
        start = bob.snapshot(lambda d: (e := _entity(d, "Alice")) is not None and e["y"] == TEST_SPAWNS[0][1])
        start_y = _entity(start, "Alice")["y"]  # type: ignore[index]

        for seq in range(1, 6):
            alice_ws.send_text(_input(seq, move_y=-1.0))
        moved = bob.snapshot(
            lambda d: (e := _entity(d, "Alice")) is not None and e["y"] < start_y - 4.5 * STEP
        )
        alice_seen = _entity(moved, "Alice")
        assert alice_seen is not None and alice_seen["id"] == alice_id
        assert alice_seen["y"] == pytest.approx(start_y - 5 * STEP, abs=1e-9)
        assert alice_seen["anim"] in ("walk", "idle")


def test_position_saved_on_disconnect_and_restored(
    zone_client: TestClient, join_ticket: IssueTicket, run_db: RunDb[Any]
) -> None:
    ticket, character_id = join_ticket()
    with zone_client.websocket_connect(_url(ticket)) as ws:
        reader = Reader(ws)
        assert reader.next()["t"] == "welcome"
        start = _entity(reader.snapshot(), "Alice")
        assert start is not None
        for seq in range(1, 9):
            ws.send_text(_input(seq, move_x=1.0, move_y=1.0, aim=1.25))
        final = _entity(reader.snapshot(lambda d: d["ack_seq"] == 8), "Alice")
        assert final is not None
        ws.close()
        _wait_offline(zone_client)

    async def load(session: AsyncSession) -> Character | None:
        return await session.get(Character, uuid.UUID(character_id))

    saved = run_db(load)
    assert saved is not None
    assert (saved.x, saved.y, saved.facing) == (final["x"], final["y"], 1.25)
    assert saved.x > start["x"]
    assert saved.inventory is not None and saved.inventory["slots"], "inventaire sauvegardé"

    ticket, _ = join_ticket()
    with zone_client.websocket_connect(_url(ticket)) as ws:
        reader = Reader(ws)
        assert reader.next()["t"] == "welcome"
        restored = _entity(reader.snapshot(), "Alice")
        assert restored is not None
        assert (restored["x"], restored["y"], restored["aim"]) == (final["x"], final["y"], 1.25)


def test_position_in_wall_moves_to_nearest_spawn(
    zone_client: TestClient, join_ticket: IssueTicket, run_db: RunDb[Any]
) -> None:
    ticket, character_id = join_ticket()

    async def move_into_wall(session: AsyncSession) -> None:
        # Bloc solide de la carte de test (tuiles 70..72 × 60..68) ; spawn le plus proche (66,5 ; 64,5).
        await session.execute(
            update(Character)
            .where(Character.id == uuid.UUID(character_id))
            .values(x=71.0, y=64.0, inventory={"equipped": -1, "slots": []})
        )

    run_db(move_into_wall)
    with zone_client.websocket_connect(_url(ticket)) as ws:
        reader = Reader(ws)
        assert reader.next()["t"] == "welcome"
        me = _entity(reader.snapshot(), "Alice")
        assert me is not None
        assert (me["x"], me["y"]) == TEST_SPAWNS[0]


def test_slow_client_is_closed_with_4009(
    zone_client: TestClient, join_ticket: IssueTicket, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Client qui ne lit plus : ses envois bloquent, la file sortante déborde → 4009, le tick continue."""
    monkeypatch.setattr(session_module, "MAX_OUTGOING_MESSAGES", 8)
    original = WebSocket.send_text

    async def stalled_send(self: WebSocket, data: str) -> None:
        # Seul `welcome` passe ; ensuite le « réseau » ne prend plus rien (client qui ne lit pas).
        if json.loads(data)["t"] == "welcome":
            await original(self, data)
            return
        await asyncio.Event().wait()

    monkeypatch.setattr(WebSocket, "send_text", stalled_send)
    zone = _zones(zone_client).get(ZONE_ID)
    assert zone is not None
    ticket, _ = join_ticket()
    with pytest.raises(WebSocketDisconnect) as info, zone_client.websocket_connect(_url(ticket)) as ws:
        assert ws.receive_json()["t"] == "welcome"
        tick_at_welcome = zone.tick
        ws.receive_json()
    assert info.value.code == 4009
    # 1 message en cours d'envoi + 8 en file + 1 de trop (snapshots, plus `inventory` et `vitals` au
    # premier tick) : la zone a continué de tourner pendant plusieurs ticks.
    assert zone.tick >= tick_at_welcome + 6
    _wait_offline(zone_client)
    assert zone.running
