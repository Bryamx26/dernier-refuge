"""Tests du codec d'enveloppes WebSocket."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.protocol.codec import MAX_CLIENT_MESSAGE_BYTES, ProtocolError, decode_client, encode_server
from app.protocol.generated import ErrorPayload, PingPayload, PongPayload


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
