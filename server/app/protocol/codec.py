"""Encodage et décodage des enveloppes WebSocket.

Client → serveur : ``{"t": <type>, "seq": <entier ≥ 0>, "d": <charge utile>}``
Serveur → client : ``{"t": <type>, "seq": <entier>, "tick": <entier>, "d": <charge utile>}``

Les charges utiles sont validées par les modèles Pydantic générés depuis
``shared/protocol/protocol.json`` (voir ``app/protocol/generated.py``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, NoReturn

from pydantic import ValidationError

from app.protocol.generated import (
    CLIENT_MESSAGES,
    SERVER_MESSAGES,
    ErrorCode,
    ProtocolModel,
    ServerMessageType,
)

# Taille maximale d'un message client, en octets UTF-8.
MAX_CLIENT_MESSAGE_BYTES = 4096
# Longueur maximale du champ `message` d'un `error` (cf. protocol.json).
MAX_ERROR_MESSAGE_LENGTH = 200

_ENVELOPE_KEYS = frozenset({"t", "seq", "d"})


class ProtocolError(Exception):
    """Message client refusé ; le code est renvoyé tel quel dans un message `error`."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code: ErrorCode = code
        # Tronqué pour respecter la contrainte du schéma `error.message`.
        self.message = message[:MAX_ERROR_MESSAGE_LENGTH]


@dataclass(frozen=True, slots=True)
class ClientEnvelope:
    """Message client décodé et validé."""

    t: str
    seq: int
    payload: ProtocolModel


def _reject_constant(name: str) -> NoReturn:
    # json.loads accepte NaN/Infinity par défaut, ce qui n'est pas du JSON standard.
    raise ValueError(f"constante JSON non standard : {name}")


def decode_client(raw: str | bytes) -> ClientEnvelope:
    """Décode et valide un message client. Lève `ProtocolError` s'il est refusé."""
    size = len(raw.encode("utf-8")) if isinstance(raw, str) else len(raw)
    if size > MAX_CLIENT_MESSAGE_BYTES:
        raise ProtocolError("bad_message", f"message trop long ({size} > {MAX_CLIENT_MESSAGE_BYTES} octets)")

    try:
        data: Any = json.loads(raw, parse_constant=_reject_constant)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProtocolError("bad_message", "JSON invalide") from exc

    if not isinstance(data, dict):
        raise ProtocolError("bad_message", "l'enveloppe doit être un objet JSON")
    if data.keys() != _ENVELOPE_KEYS:
        raise ProtocolError("bad_message", "l'enveloppe doit contenir exactement les clés t, seq et d")

    t, seq, d = data["t"], data["seq"], data["d"]
    if not isinstance(t, str):
        raise ProtocolError("bad_message", "`t` doit être une chaîne")
    # bool est une sous-classe d'int : on l'exclut explicitement.
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
        raise ProtocolError("bad_message", "`seq` doit être un entier positif ou nul")

    model = CLIENT_MESSAGES.get(t)
    if model is None:
        raise ProtocolError("unknown_type", f"type de message inconnu : {t[:64]}")
    if not isinstance(d, dict):
        raise ProtocolError("bad_message", "`d` doit être un objet JSON")

    try:
        # Mode strict : pas de conversion implicite (ex. "12" → 12.0).
        payload = model.model_validate(d, strict=True)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first["loc"]) or "d"
        raise ProtocolError(
            "bad_message", f"charge utile `{t}` invalide ({location} : {first['msg']})"
        ) from exc

    return ClientEnvelope(t=t, seq=seq, payload=payload)


def encode_server(t: ServerMessageType, seq: int, tick: int, payload: ProtocolModel) -> str:
    """Sérialise un message serveur. Lève `TypeError` si `payload` ne correspond pas à `t`."""
    expected = SERVER_MESSAGES.get(t)
    if expected is None or type(payload) is not expected:
        raise TypeError(f"charge utile {type(payload).__name__} incompatible avec le message `{t}`")
    envelope = {"t": t, "seq": seq, "tick": tick, "d": payload.model_dump(mode="json")}
    return json.dumps(envelope, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
