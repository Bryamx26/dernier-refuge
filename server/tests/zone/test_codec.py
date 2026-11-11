"""Tests du codec d'enveloppes WebSocket."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.protocol.codec import (
    MAX_CLIENT_MESSAGE_BYTES,
    ProtocolError,
    decode_client,
    encode_entity,
    encode_server,
    encode_snapshot,
)
from app.protocol.generated import (
    EntityState,
    ErrorPayload,
    InputPayload,
    PingPayload,
    PongPayload,
    SnapshotPayload,
)


def _raw(**envelope: Any) -> str:
    return json.dumps(envelope)


def _expect_error(raw: str | bytes, code: str) -> ProtocolError:
    with pytest.raises(ProtocolError) as info:
        decode_client(raw)
    assert info.value.code == code
    assert len(info.value.message) <= 200
    return info.value


def test_decode_ping() -> None:
    envelope = decode_client(_raw(t="ping", seq=3, d={"client_time": 12.5}))
    assert envelope.t == "ping"
    assert envelope.seq == 3
    assert envelope.payload == PingPayload(client_time=12.5)


def test_decode_accepts_bytes_and_integer_time() -> None:
    envelope = decode_client(_raw(t="ping", seq=0, d={"client_time": 7}).encode())
    assert envelope.payload == PingPayload(client_time=7.0)


@pytest.mark.parametrize(
    "raw",
    [
        "pas du json",
        "[1, 2]",
        '"ping"',
        b"\xff\xfe",
        '{"t": "ping", "seq": 1, "d": {"client_time": NaN}}',
        _raw(t="ping", seq=1),
        _raw(t="ping", seq=1, d={"client_time": 1}, extra=1),
        _raw(t=5, seq=1, d={"client_time": 1}),
        _raw(t="ping", seq=-1, d={"client_time": 1}),
        _raw(t="ping", seq=1.5, d={"client_time": 1}),
        _raw(t="ping", seq=True, d={"client_time": 1}),
        _raw(t="ping", seq="1", d={"client_time": 1}),
        _raw(t="ping", seq=1, d=[]),
        _raw(t="ping", seq=1, d={}),
        _raw(t="ping", seq=1, d={"client_time": -1}),
        _raw(t="ping", seq=1, d={"client_time": "12"}),
        _raw(t="ping", seq=1, d={"client_time": 1, "intrus": 2}),
    ],
)
def test_decode_rejects_bad_message(raw: str | bytes) -> None:
    _expect_error(raw, "bad_message")


def test_decode_rejects_unknown_type() -> None:
    error = _expect_error(_raw(t="x" * 500, seq=1, d={}), "unknown_type")
    assert "inconnu" in error.message


def test_decode_rejects_oversized_message() -> None:
    padding = "a" * MAX_CLIENT_MESSAGE_BYTES
    _expect_error(_raw(t="ping", seq=1, d={"client_time": 1, "p": padding}), "bad_message")


def test_size_limit_counts_utf8_bytes() -> None:
    # Moins de 4096 caractères mais plus de 4096 octets.
    raw = "é" * (MAX_CLIENT_MESSAGE_BYTES // 2 + 1)
    assert len(raw) < MAX_CLIENT_MESSAGE_BYTES
    error = _expect_error(raw, "bad_message")
    assert "trop long" in error.message


def test_encode_server() -> None:
    text = encode_server("pong", 4, 120, PongPayload(client_time=1.0, server_time=2.0))
    assert json.loads(text) == {
        "t": "pong",
        "seq": 4,
        "tick": 120,
        "d": {"client_time": 1.0, "server_time": 2.0},
    }


def test_encode_error_payload() -> None:
    text = encode_server("error", 1, 0, ErrorPayload(code="rate_limited", message="trop"))
    assert json.loads(text)["d"] == {"code": "rate_limited", "message": "trop"}


def test_encode_rejects_mismatched_payload() -> None:
    with pytest.raises(TypeError):
        encode_server("welcome", 1, 0, PongPayload(client_time=1.0, server_time=2.0))


def test_protocol_error_message_is_truncated() -> None:
    assert len(ProtocolError("internal", "x" * 1000).message) == 200


def test_decode_input() -> None:
    envelope = decode_client(
        _raw(t="input", seq=12, d={"move_x": -1, "move_y": 0.5, "aim": 3.1, "sprint": True, "attack": True})
    )
    assert (envelope.t, envelope.seq) == ("input", 12)
    assert envelope.payload == InputPayload(move_x=-1.0, move_y=0.5, aim=3.1, sprint=True, attack=True)


@pytest.mark.parametrize(
    "d",
    [
        {"move_x": 1.01, "move_y": 0, "aim": 0, "sprint": False, "attack": False},
        {"move_x": 0, "move_y": -2, "aim": 0, "sprint": False, "attack": False},
        {"move_x": 0, "move_y": 0, "aim": 7.5, "sprint": False, "attack": False},
        {"move_x": 0, "move_y": 0, "aim": 0, "sprint": 1, "attack": False},
        {"move_x": "0", "move_y": 0, "aim": 0, "sprint": False, "attack": False},
        {"move_x": 0, "move_y": 0, "aim": 0},
        {"move_x": 0, "move_y": 0, "aim": 0, "sprint": False, "attack": False, "dash": True},
    ],
)
def test_decode_input_out_of_bounds(d: dict[str, Any]) -> None:
    _expect_error(_raw(t="input", seq=1, d=d), "bad_message")


def test_snapshot_fast_path_matches_encode_server() -> None:
    entities = [
        EntityState(id="p1", kind="player", name="Élise", x=64.15, y=1e-7, aim=-3.0, anim="walk", health=0.5),
        EntityState(id="p2", kind="player", name="", x=0.0, y=127.7, aim=0.0, anim="idle", health=1.0),
    ]
    fast = encode_snapshot(5, 99, 3, [encode_entity(e) for e in entities])
    reference = encode_server("snapshot", 5, 99, SnapshotPayload(ack_seq=3, entities=entities))
    assert json.loads(fast) == json.loads(reference)
    assert json.loads(encode_snapshot(1, 2, 0, [])) == {
        "t": "snapshot",
        "seq": 1,
        "tick": 2,
        "d": {"ack_seq": 0, "entities": []},
    }
    with pytest.raises(ValueError):
        encode_snapshot(1, 1, -1, [])
