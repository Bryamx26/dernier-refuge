"""Tests de bout en bout du WebSocket de zone (ticket REST → WebSocket)."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from app.api.characters import DEFAULT_ZONE_ID
from app.protocol.generated import PROTOCOL_VERSION
from app.zone.gateway import MAX_REJECTED_MESSAGES
from app.zone.manager import ZoneManager
from tests.zone.conftest import IssueTicket

ZONE_ID = DEFAULT_ZONE_ID


def _url(ticket: str, zone_id: str = ZONE_ID) -> str:
    return f"/ws/zone/{zone_id}?ticket={ticket}"


def _zones(client: TestClient) -> ZoneManager:
    zones: ZoneManager = client.app.state.zones  # type: ignore[attr-defined]
    return zones


def _receive(ws: WebSocketTestSession) -> dict[str, Any]:
    message: dict[str, Any] = ws.receive_json()
    assert set(message) == {"t", "seq", "tick", "d"}
    return message


def _expect_close(client: TestClient, url: str, code: int) -> None:
    with pytest.raises(WebSocketDisconnect) as info, client.websocket_connect(url) as ws:
        ws.receive_json()
    assert info.value.code == code


def test_welcome_ping_and_error(zone_client: TestClient, join_ticket: IssueTicket) -> None:
    ticket, character_id = join_ticket()
    with zone_client.websocket_connect(_url(ticket)) as ws:
        welcome = _receive(ws)
        assert welcome["t"] == "welcome"
        assert welcome["seq"] == 1
        assert welcome["d"]["protocol_version"] == PROTOCOL_VERSION
        assert welcome["d"]["zone_id"] == ZONE_ID
        assert welcome["d"]["character_id"] == character_id
        assert welcome["d"]["tick_rate"] == 20
        assert welcome["d"]["server_time"] > 0
        assert _zones(zone_client).online_count(ZONE_ID) == 1

        ws.send_text(json.dumps({"t": "ping", "seq": 1, "d": {"client_time": 123.5}}))
        pong = _receive(ws)
        assert pong["t"] == "pong"
        assert pong["seq"] == 2
        assert pong["tick"] >= welcome["tick"]
        assert pong["d"]["client_time"] == 123.5
        assert pong["d"]["server_time"] >= welcome["d"]["server_time"]

        ws.send_text("pas du json")
        error = _receive(ws)
        assert (error["t"], error["seq"], error["d"]["code"]) == ("error", 3, "bad_message")

        ws.send_text(json.dumps({"t": "teleport", "seq": 2, "d": {}}))
        assert _receive(ws)["d"]["code"] == "unknown_type"

        # La connexion reste ouverte après une erreur.
        ws.send_text(json.dumps({"t": "ping", "seq": 3, "d": {"client_time": 1}}))
        assert _receive(ws)["t"] == "pong"

    # Désinscription à la déconnexion.
    assert _zones(zone_client).online_count(ZONE_ID) == 0


def test_reused_ticket_is_refused(zone_client: TestClient, join_ticket: IssueTicket) -> None:
    ticket, _ = join_ticket()
    with zone_client.websocket_connect(_url(ticket)) as ws:
        assert _receive(ws)["t"] == "welcome"
    _expect_close(zone_client, _url(ticket), 4001)


@pytest.mark.parametrize("query", ["", "?ticket=", "?ticket=inconnu"])
def test_missing_or_invalid_ticket(zone_client: TestClient, query: str) -> None:
    _expect_close(zone_client, f"/ws/zone/{ZONE_ID}{query}", 4001)


def test_double_connection_is_refused(zone_client: TestClient, join_ticket: IssueTicket) -> None:
    first_ticket, _ = join_ticket()
    with zone_client.websocket_connect(_url(first_ticket)) as ws:
        assert _receive(ws)["t"] == "welcome"
        second_ticket, _ = join_ticket()
        _expect_close(zone_client, _url(second_ticket), 4002)
        # La première connexion n'est pas affectée.
        ws.send_text(json.dumps({"t": "ping", "seq": 1, "d": {"client_time": 1}}))
        assert _receive(ws)["t"] == "pong"
        assert _zones(zone_client).online_count(ZONE_ID) == 1


def test_unknown_zone(zone_client: TestClient, join_ticket: IssueTicket) -> None:
    ticket, _ = join_ticket()
    _expect_close(zone_client, _url(ticket, zone_id="atlantide"), 4004)
    # Le ticket n'a pas été consommé par la tentative sur une zone inconnue.
    with zone_client.websocket_connect(_url(ticket)) as ws:
        assert _receive(ws)["t"] == "welcome"


def test_full_zone(zone_client: TestClient, join_ticket: IssueTicket) -> None:
    zone = _zones(zone_client).get(ZONE_ID)
    assert zone is not None
    zone.spec = dataclasses.replace(zone.spec, max_players=0)
    ticket, _ = join_ticket()
    _expect_close(zone_client, _url(ticket), 4003)


def test_abuse_closes_connection(zone_client: TestClient, join_ticket: IssueTicket) -> None:
    ticket, _ = join_ticket()
    with pytest.raises(WebSocketDisconnect) as info, zone_client.websocket_connect(_url(ticket)) as ws:
        assert _receive(ws)["t"] == "welcome"
        for _ in range(MAX_REJECTED_MESSAGES):
            ws.send_text("{}")
        for _ in range(MAX_REJECTED_MESSAGES - 1):
            assert _receive(ws)["t"] == "error"
        ws.receive_json()
    assert info.value.code == 4008
    assert _zones(zone_client).online_count(ZONE_ID) == 0


def test_rate_limit(zone_client: TestClient, join_ticket: IssueTicket) -> None:
    ticket, _ = join_ticket()
    ping = json.dumps({"t": "ping", "seq": 1, "d": {"client_time": 1}})
    with zone_client.websocket_connect(_url(ticket)) as ws:
        assert _receive(ws)["t"] == "welcome"
        # Rafale bien supérieure au seau (30 jetons) : une partie est refusée.
        burst = 40
        for _ in range(burst):
            ws.send_text(ping)
        replies = [_receive(ws) for _ in range(burst)]
        limited = [r for r in replies if r["t"] == "error"]
        assert limited and all(r["d"]["code"] == "rate_limited" for r in limited)
        assert len(replies) - len(limited) >= 30
