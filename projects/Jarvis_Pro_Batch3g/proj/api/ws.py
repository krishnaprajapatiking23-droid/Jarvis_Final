"""Minimal RFC 6455 WebSocket framing + handshake, standard library only.

These are pure functions so they are unit-testable without a network socket.
The server adapter in api/server.py uses them to push ApiService events to
the desktop UI and the Android companion.
"""

import base64
import hashlib
import json
import os
import struct
from typing import Any, Dict, Optional, Tuple

# RFC 6455 section 1.3 magic GUID. Exact value matters: a browser rejects the
# handshake if Sec-WebSocket-Accept is computed with anything else.
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

MAX_FRAME_BYTES = 1 * 1024 * 1024


class WebSocketError(Exception):
    pass


def accept_key(client_key: str) -> str:
    """Compute the Sec-WebSocket-Accept value for a client key."""
    if not client_key:
        raise WebSocketError("missing Sec-WebSocket-Key")
    digest = hashlib.sha1((client_key.strip() + GUID).encode()).digest()
    return base64.b64encode(digest).decode()


def handshake_response(headers: Dict[str, str]) -> str:
    lowered = {k.lower(): v for k, v in headers.items()}
    if lowered.get("upgrade", "").lower() != "websocket":
        raise WebSocketError("not a websocket upgrade")
    if lowered.get("sec-websocket-version", "13") != "13":
        raise WebSocketError("unsupported websocket version")
    key = accept_key(lowered.get("sec-websocket-key", ""))
    return ("HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Accept: " + key + "\r\n\r\n")


def encode_frame(payload: bytes, opcode: int = OP_TEXT, mask: bool = False) -> bytes:
    if len(payload) > MAX_FRAME_BYTES:
        raise WebSocketError("frame too large")
    header = bytearray()
    header.append(0x80 | opcode)
    length = len(payload)
    mask_bit = 0x80 if mask else 0x00
    if length < 126:
        header.append(mask_bit | length)
    elif length < 65536:
        header.append(mask_bit | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(mask_bit | 127)
        header.extend(struct.pack("!Q", length))
    if not mask:
        return bytes(header) + payload
    key = os.urandom(4)
    masked = bytes(b ^ key[i % 4] for i, b in enumerate(payload))
    return bytes(header) + key + masked


def decode_frame(data: bytes) -> Tuple[int, bytes, int]:
    """Decode one frame. Returns (opcode, payload, bytes_consumed).

    Raises WebSocketError when the buffer does not yet hold a whole frame,
    so callers can keep reading instead of mis-parsing.
    """
    if len(data) < 2:
        raise WebSocketError("incomplete frame header")
    first, second = data[0], data[1]
    if not first & 0x80:
        raise WebSocketError("fragmented frames are not supported")
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    length = second & 0x7F
    offset = 2
    if length == 126:
        if len(data) < offset + 2:
            raise WebSocketError("incomplete extended length")
        length = struct.unpack("!H", data[offset:offset + 2])[0]
        offset += 2
    elif length == 127:
        if len(data) < offset + 8:
            raise WebSocketError("incomplete extended length")
        length = struct.unpack("!Q", data[offset:offset + 8])[0]
        offset += 8
    if length > MAX_FRAME_BYTES:
        raise WebSocketError("frame too large")
    key = b""
    if masked:
        if len(data) < offset + 4:
            raise WebSocketError("incomplete mask")
        key = data[offset:offset + 4]
        offset += 4
    if len(data) < offset + length:
        raise WebSocketError("incomplete payload")
    payload = data[offset:offset + length]
    if masked:
        payload = bytes(b ^ key[i % 4] for i, b in enumerate(payload))
    return opcode, payload, offset + length


def encode_event(event: Dict[str, Any]) -> bytes:
    return encode_frame(json.dumps(event, default=str).encode("utf-8"), OP_TEXT)


def decode_message(data: bytes) -> Optional[Dict[str, Any]]:
    opcode, payload, _ = decode_frame(data)
    if opcode == OP_CLOSE:
        return None
    if opcode != OP_TEXT:
        raise WebSocketError("expected a text frame")
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise WebSocketError("invalid JSON message: " + str(exc))
    if not isinstance(parsed, dict):
        raise WebSocketError("message must be a JSON object")
    return parsed
