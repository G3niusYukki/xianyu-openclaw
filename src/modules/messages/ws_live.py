"""闲鱼 IM WebSocket 通道（参考实战可用链路）。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import random
import re
import struct
import time
from typing import Any

import httpx

from src.core.error_handler import BrowserError
from src.core.logger import get_logger

try:
    import websockets
except Exception:  # pragma: no cover - optional dependency path
    websockets = None  # type: ignore[assignment]


def parse_cookie_header(cookie_text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in re.split(r";\s*", str(cookie_text or "").strip()):
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = str(key or "").strip()
        value = str(value or "").strip()
        if key:
            result[key] = value
    return result


def generate_sign(timestamp_ms: str, token: str, data: str, app_key: str = "34839810") -> str:
    raw = f"{token}&{timestamp_ms}&{app_key}&{data}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def generate_mid() -> str:
    ts = int(time.time() * 1000)
    prefix = random.randint(100, 999)
    return f"{prefix}{ts} 0"


def generate_uuid() -> str:
    return f"-{int(time.time() * 1000)}1"


def generate_device_id(user_id: str) -> str:
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    out: list[str] = []
    for i in range(36):
        if i in {8, 13, 18, 23}:
            out.append("-")
        elif i == 14:
            out.append("4")
        elif i == 19:
            rv = random.randint(0, 15)
            out.append(chars[(rv & 0x3) | 0x8])
        else:
            out.append(chars[random.randint(0, 15)])
    return "".join(out) + "-" + str(user_id or "")


class MessagePackDecoder:
    """轻量 MessagePack 解码器（仅覆盖当前闲鱼消息场景）。"""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        self.length = len(data)

    def _read_byte(self) -> int:
        if self.pos >= self.length:
            raise ValueError("Unexpected end of data")
        value = self.data[self.pos]
        self.pos += 1
        return value

    def _read_bytes(self, count: int) -> bytes:
        if self.pos + count > self.length:
            raise ValueError("Unexpected end of data")
        buf = self.data[self.pos : self.pos + count]
        self.pos += count
        return buf

    def _read_uint8(self) -> int:
        return self._read_byte()

    def _read_uint16(self) -> int:
        return struct.unpack(">H", self._read_bytes(2))[0]

    def _read_uint32(self) -> int:
        return struct.unpack(">I", self._read_bytes(4))[0]

    def _read_uint64(self) -> int:
        return struct.unpack(">Q", self._read_bytes(8))[0]

    def _read_int8(self) -> int:
        return struct.unpack(">b", self._read_bytes(1))[0]

    def _read_int16(self) -> int:
        return struct.unpack(">h", self._read_bytes(2))[0]

    def _read_int32(self) -> int:
        return struct.unpack(">i", self._read_bytes(4))[0]

    def _read_int64(self) -> int:
        return struct.unpack(">q", self._read_bytes(8))[0]

    def _read_float32(self) -> float:
        return struct.unpack(">f", self._read_bytes(4))[0]

    def _read_float64(self) -> float:
        return struct.unpack(">d", self._read_bytes(8))[0]

    def _read_string(self, length: int) -> str:
        return self._read_bytes(length).decode("utf-8")

    def _decode_array(self, size: int) -> list[Any]:
        out: list[Any] = []
        for _ in range(size):
            out.append(self.decode_value())
        return out

    def _decode_map(self, size: int) -> dict[Any, Any]:
        out: dict[Any, Any] = {}
        for _ in range(size):
            key = self.decode_value()
            value = self.decode_value()
            out[key] = value
        return out

    def decode_value(self) -> Any:
        b = self._read_byte()
        if b <= 0x7F:
            return b
        if 0x80 <= b <= 0x8F:
            return self._decode_map(b & 0x0F)
        if 0x90 <= b <= 0x9F:
            return self._decode_array(b & 0x0F)
        if 0xA0 <= b <= 0xBF:
            return self._read_string(b & 0x1F)
        if b == 0xC0:
            return None
        if b == 0xC2:
            return False
        if b == 0xC3:
            return True
        if b == 0xC4:
            return self._read_bytes(self._read_uint8())
        if b == 0xC5:
            return self._read_bytes(self._read_uint16())
        if b == 0xC6:
            return self._read_bytes(self._read_uint32())
        if b == 0xCA:
            return self._read_float32()
        if b == 0xCB:
            return self._read_float64()
        if b == 0xCC:
            return self._read_uint8()
        if b == 0xCD:
            return self._read_uint16()
        if b == 0xCE:
            return self._read_uint32()
        if b == 0xCF:
            return self._read_uint64()
        if b == 0xD0:
            return self._read_int8()
        if b == 0xD1:
            return self._read_int16()
        if b == 0xD2:
            return self._read_int32()
        if b == 0xD3:
            return self._read_int64()
        if b == 0xD9:
            return self._read_string(self._read_uint8())
        if b == 0xDA:
            return self._read_string(self._read_uint16())
        if b == 0xDB:
            return self._read_string(self._read_uint32())
        if b == 0xDC:
            return self._decode_array(self._read_uint16())
        if b == 0xDD:
            return self._decode_array(self._read_uint32())
        if b == 0xDE:
            return self._decode_map(self._read_uint16())
        if b == 0xDF:
            return self._decode_map(self._read_uint32())
        if b >= 0xE0:
            return b - 256
        raise ValueError(f"Unknown MessagePack byte: 0x{b:02x}")

    def decode(self) -> Any:
        return self.decode_value()


def decode_sync_payload(raw_text: str) -> Any | None:
    text = "".join(ch for ch in str(raw_text or "") if ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=-_")
    if not text:
        return None
    while len(text) % 4 != 0:
        text += "="

    try:
        buf = base64.b64decode(text)
    except Exception:
        try:
            buf = base64.urlsafe_b64decode(text)
        except Exception:
            return None

    try:
        return json.loads(buf.decode("utf-8"))
    except Exception:
        pass

    try:
        return MessagePackDecoder(buf).decode()
    except Exception:
        pass

    return None


def extract_chat_event(message: Any) -> dict[str, Any] | None:
    def _pick(obj: Any, *keys: Any) -> Any:
        if not isinstance(obj, dict):
            return None
        for key in keys:
            if key in obj:
                return obj[key]
        return None

    if not isinstance(message, dict):
        return None
    body = _pick(message, "1", 1)
    if not isinstance(body, dict):
        return None
    content = _pick(body, "10", 10)
    if not isinstance(content, dict):
        return None

    text = str(_pick(content, "reminderContent", "content", "text") or "").strip()
    sender_user_id = str(_pick(content, "senderUserId", "fromUserId", "senderId") or "").strip()
    sender_name = str(_pick(content, "reminderTitle", "senderNick", "senderName") or "").strip()
    chat_ref = str(_pick(body, "2", 2, "cid", "chatId") or "").strip()
    chat_id = chat_ref.split("@")[0] if "@" in chat_ref else chat_ref
    if not text or not sender_user_id or not chat_id:
        return None

    create_time = int(time.time() * 1000)
    try:
        create_time = int(_pick(body, "5", 5, "createTime") or create_time)
    except Exception:
        pass

    reminder_url = str(_pick(content, "reminderUrl", "url") or "")
    item_id = ""
    m = re.search(r"[?&]itemId=(\d+)", reminder_url)
    if m:
        item_id = str(m.group(1))

    return {
        "chat_id": chat_id,
        "sender_user_id": sender_user_id,
        "sender_name": sender_name or "买家",
        "text": text,
        "item_id": item_id,
        "create_time": create_time,
    }


class GoofishWsTransport:
    """闲鱼消息 WebSocket 收发通道。"""

    def __init__(self, cookie_text: str, config: dict[str, Any] | None = None):
        if websockets is None:
            raise BrowserError("WebSocket transport requires `websockets`. Install: pip install websockets")

        self.logger = get_logger()
        self.config = config or {}
        self.base_url = str(self.config.get("base_url", "wss://wss-goofish.dingtalk.com/")).strip()
        self.heartbeat_interval = int(self.config.get("heartbeat_interval_seconds", 15))
        self.heartbeat_timeout = int(self.config.get("heartbeat_timeout_seconds", 5))
        self.reconnect_delay = float(self.config.get("reconnect_delay_seconds", 3.0))
        self.event_expire_ms = int(self.config.get("message_expire_ms", 5 * 60 * 1000))
        self.max_queue_size = int(self.config.get("max_queue_size", 200))
        self.queue_wait_seconds = float(self.config.get("queue_wait_seconds", 0.3))
        self.token_refresh_interval_seconds = int(self.config.get("token_refresh_interval_seconds", 3600))
        self.token_retry_seconds = int(self.config.get("token_retry_seconds", 300))

        self.cookie_text = str(cookie_text or "").strip()
        self.cookies = parse_cookie_header(self.cookie_text)
        self.my_user_id = str(self.cookies.get("unb", "") or "").strip()
        if not self.cookie_text or not self.my_user_id:
            raise BrowserError("Invalid XIANYU_COOKIE_1. Missing cookie text or `unb`.")

        self.device_id = generate_device_id(self.my_user_id)
        self._token: str = ""
        self._token_ts: float = 0.0

        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=max(10, self.max_queue_size))
        self._queue_event = asyncio.Event()
        self._session_peer: dict[str, str] = {}
        self._seen_event: dict[str, float] = {}

        self._ws: Any | None = None
        self._stop_event = asyncio.Event()
        self._run_task: asyncio.Task[Any] | None = None
        self._ready = asyncio.Event()
        self._last_heartbeat_sent = 0.0
        self._last_heartbeat_ack = 0.0

    def _base_headers(self) -> dict[str, str]:
        return {
            "accept": "application/json",
            "accept-language": "zh-CN,zh;q=0.9",
            "cache-control": "no-cache",
            "origin": "https://www.goofish.com",
            "pragma": "no-cache",
            "referer": "https://www.goofish.com/",
            "sec-ch-ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/133.0.0.0 Safari/537.36"
            ),
            "cookie": self.cookie_text,
        }

    async def _fetch_token(self) -> str:
        now = time.time()
        if self._token and (now - self._token_ts) < self.token_refresh_interval_seconds:
            return self._token

        token_cookie = str(self.cookies.get("_m_h5_tk", "") or "")
        token_seed = token_cookie.split("_")[0].strip()
        if not token_seed:
            raise BrowserError("Cookie missing `_m_h5_tk`.")

        t = str(int(time.time() * 1000))
        data_val = json.dumps(
            {"appKey": "444e9908a51d1cb236a27862abc769c9", "deviceId": self.device_id},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        params = {
            "jsv": "2.7.2",
            "appKey": "34839810",
            "t": t,
            "sign": generate_sign(t, token_seed, data_val),
            "v": "1.0",
            "type": "originaljson",
            "accountSite": "xianyu",
            "dataType": "json",
            "timeout": "20000",
            "api": "mtop.taobao.idlemessage.pc.login.token",
            "sessionOption": "AutoLoginOnly",
            "spm_cnt": "a21ybx.im.0.0",
        }

        headers = self._base_headers()
        data = {"data": data_val}
        async with httpx.AsyncClient(timeout=12.0, headers=headers) as client:
            resp = await client.post(
                "https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/",
                params=params,
                data=data,
            )
            payload = resp.json()

        ret = payload.get("ret", []) if isinstance(payload, dict) else []
        if not any("SUCCESS::调用成功" in str(item) for item in ret):
            raise BrowserError(f"Token API failed: {ret}")

        token = str(payload.get("data", {}).get("accessToken", "") or "").strip()
        if not token:
            raise BrowserError("Token API success but accessToken missing.")

        self._token = token
        self._token_ts = time.time()
        return token

    async def _send_reg(self) -> None:
        if self._ws is None:
            raise BrowserError("WebSocket not connected.")
        token = await self._fetch_token()
        reg_msg = {
            "lwp": "/reg",
            "headers": {
                "cache-header": "app-key token ua wv",
                "app-key": "444e9908a51d1cb236a27862abc769c9",
                "token": token,
                "ua": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/133.0.0.0 Safari/537.36 DingTalk(2.1.5)"
                ),
                "dt": "j",
                "wv": "im:3,au:3,sy:6",
                "sync": "0,0;0;0;",
                "did": self.device_id,
                "mid": generate_mid(),
            },
        }
        await self._ws.send(json.dumps(reg_msg, ensure_ascii=False))
        await asyncio.sleep(1.0)
        ack_diff = {
            "lwp": "/r/SyncStatus/ackDiff",
            "headers": {"mid": "5701741704675979 0"},
            "body": [
                {
                    "pipeline": "sync",
                    "tooLong2Tag": "PNM,1",
                    "channel": "sync",
                    "topic": "sync",
                    "highPts": 0,
                    "pts": int(time.time() * 1000) * 1000,
                    "seq": 0,
                    "timestamp": int(time.time() * 1000),
                }
            ],
        }
        await self._ws.send(json.dumps(ack_diff, ensure_ascii=False))

    async def _send_heartbeat(self) -> None:
        if self._ws is None:
            return
        msg = {"lwp": "/!", "headers": {"mid": generate_mid()}}
        await self._ws.send(json.dumps(msg, ensure_ascii=False))
        self._last_heartbeat_sent = time.time()

    async def _ack_packet(self, packet: dict[str, Any]) -> None:
        if self._ws is None:
            return
        headers = packet.get("headers", {})
        if not isinstance(headers, dict):
            return
        mid = headers.get("mid")
        if not mid:
            return
        ack = {"code": 200, "headers": {"mid": mid, "sid": headers.get("sid", "")}}
        for key in ("app-key", "ua", "dt"):
            if key in headers:
                ack["headers"][key] = headers[key]
        await self._ws.send(json.dumps(ack, ensure_ascii=False))

    def _cleanup_seen(self) -> None:
        now = time.time()
        expire = max(120.0, self.event_expire_ms / 1000.0 * 2.0)
        dead = [k for k, ts in self._seen_event.items() if (now - ts) > expire]
        for k in dead:
            self._seen_event.pop(k, None)

    async def _push_event(self, event: dict[str, Any]) -> None:
        chat_id = str(event.get("chat_id", "") or "")
        sender_id = str(event.get("sender_user_id", "") or "")
        text = str(event.get("text", "") or "")
        create_time = int(event.get("create_time", int(time.time() * 1000)) or int(time.time() * 1000))
        if not chat_id or not sender_id or not text:
            return

        if sender_id == self.my_user_id:
            return

        if int(time.time() * 1000) - create_time > self.event_expire_ms:
            return

        dedupe_key = hashlib.sha1(f"{chat_id}:{create_time}:{text}".encode("utf-8")).hexdigest()[:20]
        if dedupe_key in self._seen_event:
            return

        self._seen_event[dedupe_key] = time.time()
        self._cleanup_seen()

        self._session_peer[chat_id] = sender_id
        payload = {
            "session_id": chat_id,
            "peer_name": str(event.get("sender_name", "") or "买家"),
            "item_title": str(event.get("item_id", "") or ""),
            "last_message": text,
            "unread_count": 1,
            "sender_user_id": sender_id,
            "create_time": create_time,
            "source": "ws",
        }

        if self._queue.full():
            try:
                _ = self._queue.get_nowait()
            except Exception:
                pass
        await self._queue.put(payload)
        self._queue_event.set()

    async def _handle_sync(self, packet: dict[str, Any]) -> None:
        body = packet.get("body", {})
        if not isinstance(body, dict):
            return
        sync_pkg = body.get("syncPushPackage", {})
        if not isinstance(sync_pkg, dict):
            return
        data_arr = sync_pkg.get("data", [])
        if not isinstance(data_arr, list):
            return

        for item in data_arr:
            if not isinstance(item, dict):
                continue
            raw = item.get("data")
            if not raw:
                continue
            decoded = decode_sync_payload(str(raw))
            event = extract_chat_event(decoded)
            if event:
                await self._push_event(event)

    async def _run(self) -> None:
        if websockets is None:
            raise BrowserError("WebSocket transport requires `websockets`. Install: pip install websockets")

        while not self._stop_event.is_set():
            try:
                headers = self._base_headers()
                try:
                    self._ws = await websockets.connect(
                        self.base_url,
                        extra_headers=headers,
                        ping_interval=None,
                        close_timeout=5,
                        max_size=8 * 1024 * 1024,
                    )
                except TypeError as connect_error:
                    # websockets>=14 renamed `extra_headers` to `additional_headers`.
                    if "extra_headers" not in str(connect_error):
                        raise
                    self._ws = await websockets.connect(
                        self.base_url,
                        additional_headers=headers,
                        ping_interval=None,
                        close_timeout=5,
                        max_size=8 * 1024 * 1024,
                    )
                self._last_heartbeat_ack = time.time()
                self._last_heartbeat_sent = 0.0
                await self._send_reg()
                self._ready.set()
                self.logger.info("Connected to Goofish WebSocket transport")

                while not self._stop_event.is_set():
                    now = time.time()
                    if (now - self._last_heartbeat_sent) >= max(1.0, float(self.heartbeat_interval)):
                        await self._send_heartbeat()

                    if (now - self._last_heartbeat_ack) > (self.heartbeat_interval + self.heartbeat_timeout):
                        raise BrowserError("WebSocket heartbeat timeout")

                    try:
                        msg_text = await asyncio.wait_for(self._ws.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue

                    packet = json.loads(msg_text)
                    if isinstance(packet, dict):
                        if packet.get("code") == 200:
                            self._last_heartbeat_ack = time.time()
                        await self._ack_packet(packet)
                        await self._handle_sync(packet)

            except asyncio.CancelledError:  # pragma: no cover - cooperative cancel path
                break
            except Exception as exc:
                self._ready.clear()
                self.logger.warning(f"Goofish WebSocket disconnected, retrying: {exc}")
                await asyncio.sleep(max(0.5, self.reconnect_delay))
            finally:
                if self._ws is not None:
                    try:
                        await self._ws.close()
                    except Exception:
                        pass
                    self._ws = None

    async def start(self) -> None:
        if self._run_task and not self._run_task.done():
            return
        self._stop_event.clear()
        self._run_task = asyncio.create_task(self._run())

    def is_ready(self) -> bool:
        return bool(self._ready.is_set() and self._ws is not None)

    async def stop(self) -> None:
        self._stop_event.set()
        self._ready.clear()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._run_task is not None:
            self._run_task.cancel()
            try:
                await self._run_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            self._run_task = None

    async def get_unread_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        await self.start()
        if not self._ready.is_set():
            try:
                await asyncio.wait_for(self._ready.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                return []

        if self._queue.empty():
            try:
                self._queue_event.clear()
                await asyncio.wait_for(self._queue_event.wait(), timeout=max(0.05, self.queue_wait_seconds))
            except asyncio.TimeoutError:
                return []

        out: list[dict[str, Any]] = []
        seen_session: set[str] = set()
        safe_limit = max(1, int(limit or 20))
        while len(out) < safe_limit and not self._queue.empty():
            try:
                item = self._queue.get_nowait()
            except Exception:
                break
            sid = str(item.get("session_id", "") or "")
            if not sid or sid in seen_session:
                continue
            seen_session.add(sid)
            out.append(item)
        return out

    async def send_text(self, session_id: str, text: str) -> bool:
        await self.start()
        if not self._ready.is_set():
            try:
                await asyncio.wait_for(self._ready.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                return False

        if self._ws is None:
            return False

        chat_id = str(session_id or "").strip()
        to_user_id = str(self._session_peer.get(chat_id, "") or "").strip()
        if not chat_id or not to_user_id:
            self.logger.warning(f"WS send skipped: missing peer mapping for session `{chat_id}`")
            return False

        payload = {
            "contentType": 1,
            "text": {"text": str(text or "")},
        }
        content_b64 = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("utf-8")
        msg = {
            "lwp": "/r/MessageSend/sendByReceiverScope",
            "headers": {"mid": generate_mid()},
            "body": [
                {
                    "uuid": generate_uuid(),
                    "cid": f"{chat_id}@goofish",
                    "conversationType": 1,
                    "content": {"contentType": 101, "custom": {"type": 1, "data": content_b64}},
                    "redPointPolicy": 0,
                    "extension": {"extJson": "{}"},
                    "ctx": {"appVersion": "1.0", "platform": "web"},
                    "mtags": {},
                    "msgReadStatusSetting": 1,
                },
                {"actualReceivers": [f"{to_user_id}@goofish", f"{self.my_user_id}@goofish"]},
            ],
        }
        try:
            await self._ws.send(json.dumps(msg, ensure_ascii=False))
            return True
        except Exception as exc:
            self.logger.warning(f"WS send failed: {exc}")
            return False
