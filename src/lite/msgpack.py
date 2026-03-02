"""Pure Python MessagePack decoder and Xianyu payload decode helpers."""

from __future__ import annotations

import base64
import json
import struct
from typing import Any


class MessagePackDecoder:
    """Minimal MessagePack decoder for Goofish WS packets."""

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    def _read_bytes(self, count: int) -> bytes:
        if self._pos + count > len(self._data):
            raise ValueError("unexpected end of data")
        out = self._data[self._pos : self._pos + count]
        self._pos += count
        return out

    def _read_byte(self) -> int:
        return self._read_bytes(1)[0]

    def _decode_array(self, size: int) -> list[Any]:
        return [self.decode_value() for _ in range(size)]

    def _decode_map(self, size: int) -> dict[Any, Any]:
        return {self.decode_value(): self.decode_value() for _ in range(size)}

    def decode_value(self) -> Any:
        b = self._read_byte()
        if b <= 0x7F:
            return b
        if 0x80 <= b <= 0x8F:
            return self._decode_map(b & 0x0F)
        if 0x90 <= b <= 0x9F:
            return self._decode_array(b & 0x0F)
        if 0xA0 <= b <= 0xBF:
            return self._read_bytes(b & 0x1F).decode("utf-8")
        if b == 0xC0:
            return None
        if b == 0xC2:
            return False
        if b == 0xC3:
            return True
        if b == 0xCA:
            return struct.unpack(">f", self._read_bytes(4))[0]
        if b == 0xCB:
            return struct.unpack(">d", self._read_bytes(8))[0]
        if b == 0xCC:
            return self._read_byte()
        if b == 0xCD:
            return struct.unpack(">H", self._read_bytes(2))[0]
        if b == 0xCE:
            return struct.unpack(">I", self._read_bytes(4))[0]
        if b == 0xCF:
            return struct.unpack(">Q", self._read_bytes(8))[0]
        if b == 0xD0:
            return struct.unpack(">b", self._read_bytes(1))[0]
        if b == 0xD1:
            return struct.unpack(">h", self._read_bytes(2))[0]
        if b == 0xD2:
            return struct.unpack(">i", self._read_bytes(4))[0]
        if b == 0xD3:
            return struct.unpack(">q", self._read_bytes(8))[0]
        if b == 0xD9:
            return self._read_bytes(self._read_byte()).decode("utf-8")
        if b == 0xDA:
            size = struct.unpack(">H", self._read_bytes(2))[0]
            return self._read_bytes(size).decode("utf-8")
        if b == 0xDB:
            size = struct.unpack(">I", self._read_bytes(4))[0]
            return self._read_bytes(size).decode("utf-8")
        if b == 0xDC:
            return self._decode_array(struct.unpack(">H", self._read_bytes(2))[0])
        if b == 0xDD:
            return self._decode_array(struct.unpack(">I", self._read_bytes(4))[0])
        if b == 0xDE:
            return self._decode_map(struct.unpack(">H", self._read_bytes(2))[0])
        if b == 0xDF:
            return self._decode_map(struct.unpack(">I", self._read_bytes(4))[0])
        if b >= 0xE0:
            return b - 256
        raise ValueError(f"unsupported MessagePack tag: 0x{b:02x}")

    def decode(self) -> Any:
        """Decode an object from bytes."""

        return self.decode_value()


def decrypt_payload(raw: str) -> Any | None:
    """Decode base64 payload into JSON object or MessagePack object."""

    text = "".join(ch for ch in str(raw or "") if ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=-_")
    if not text:
        return None
    while len(text) % 4:
        text += "="

    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            decoded = decoder(text)
            break
        except Exception:
            decoded = b""
    if not decoded:
        return None

    try:
        return json.loads(decoded.decode("utf-8"))
    except Exception:
        pass

    try:
        return MessagePackDecoder(decoded).decode()
    except Exception:
        return {"hex": decoded.hex()}
