"""Goofish WebSocket client for Lite mode (connect, heartbeat, reconnect, send/recv)."""

from __future__ import annotations

import asyncio
import base64
import json
import random
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

import websockets

from .msgpack import decrypt_payload


def generate_mid() -> str:
    """Generate websocket message id."""

    return f"{random.randint(100, 999)}{int(time.time() * 1000)} 0"


def generate_uuid() -> str:
    """Generate websocket body uuid."""

    return f"-{int(time.time() * 1000)}1"


class LiteWsClient:
    """Async websocket transport with auto reconnect."""

    def __init__(
        self,
        *,
        ws_url: str,
        cookie: str,
        device_id: str,
        my_user_id: str,
        token_provider: Callable[[], Awaitable[str]],
        heartbeat_interval: int = 15,
        heartbeat_timeout: int = 8,
        reconnect_base_delay: float = 2.0,
        reconnect_backoff: float = 1.8,
        reconnect_max_delay: float = 45.0,
        message_expire_ms: int = 300000,
    ):
        self.ws_url = ws_url
        self.cookie = cookie
        self.device_id = device_id
        self.my_user_id = my_user_id
        self.token_provider = token_provider
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.reconnect_base_delay = reconnect_base_delay
        self.reconnect_backoff = reconnect_backoff
        self.reconnect_max_delay = reconnect_max_delay
        self.message_expire_ms = message_expire_ms

        self._ws: Any | None = None
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=300)
        self._stop = asyncio.Event()
        self._session_peer: dict[str, str] = {}
        self._last_heartbeat_send = 0.0
        self._last_heartbeat_ack = 0.0

    def _headers(self) -> dict[str, str]:
        return {
            "cookie": self.cookie,
            "origin": "https://www.goofish.com",
            "referer": "https://www.goofish.com/",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/133.0.0.0 Safari/537.36"
            ),
        }

    async def _register(self) -> None:
        if self._ws is None:
            raise RuntimeError("websocket not connected")

        token = await self.token_provider()
        reg = {
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
        await self._ws.send(json.dumps(reg, ensure_ascii=False))
        await asyncio.sleep(0.8)
        await self._ws.send(
            json.dumps(
                {
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
                },
                ensure_ascii=False,
            )
        )

    async def _send_heartbeat(self) -> None:
        if self._ws is None:
            return
        await self._ws.send(json.dumps({"lwp": "/!", "headers": {"mid": generate_mid()}}, ensure_ascii=False))
        self._last_heartbeat_send = time.time()

    async def _ack_packet(self, packet: dict[str, Any]) -> None:
        if self._ws is None:
            return
        headers = packet.get("headers")
        if not isinstance(headers, dict) or not headers.get("mid"):
            return
        ack = {"code": 200, "headers": {"mid": headers["mid"], "sid": headers.get("sid", "")}}
        for key in ("app-key", "ua", "dt"):
            if key in headers:
                ack["headers"][key] = headers[key]
        await self._ws.send(json.dumps(ack, ensure_ascii=False))

    def _extract_event(self, decoded: Any) -> dict[str, Any] | None:
        if not isinstance(decoded, dict):
            return None

        body = decoded.get("1") or decoded.get(1)
        if not isinstance(body, dict):
            return None
        content = body.get("10") or body.get(10)
        if not isinstance(content, dict):
            return None

        text = str(content.get("reminderContent") or content.get("text") or "").strip()
        sender = str(content.get("senderUserId") or content.get("senderId") or "").strip()
        sender_name = str(content.get("reminderTitle") or "买家")
        cid = str(body.get("2") or body.get(2) or "").split("@")[0]
        if not text or not sender or not cid:
            return None

        if sender == self.my_user_id:
            return None

        create_time = int(time.time() * 1000)
        try:
            create_time = int(body.get("5") or body.get(5) or create_time)
        except Exception:
            pass
        if (int(time.time() * 1000) - create_time) > self.message_expire_ms:
            return None

        url = str(content.get("reminderUrl") or "")
        item_id = ""
        m = re.search(r"[?&]itemId=(\d+)", url)
        if m:
            item_id = m.group(1)

        self._session_peer[cid] = sender
        return {
            "chat_id": cid,
            "sender_user_id": sender,
            "sender_name": sender_name,
            "text": text,
            "item_id": item_id,
            "create_time": create_time,
        }

    async def _handle_sync(self, packet: dict[str, Any]) -> None:
        body = packet.get("body", {})
        sync = body.get("syncPushPackage", {}) if isinstance(body, dict) else {}
        data_arr = sync.get("data", []) if isinstance(sync, dict) else []
        if not isinstance(data_arr, list):
            return

        for entry in data_arr:
            if not isinstance(entry, dict):
                continue
            raw_data = entry.get("data")
            if not raw_data:
                continue
            decoded = decrypt_payload(str(raw_data))
            event = self._extract_event(decoded)
            if event is None:
                continue
            if self._event_queue.full():
                _ = self._event_queue.get_nowait()
            await self._event_queue.put(event)

    async def run_forever(self) -> None:
        """Run websocket lifecycle until stop() is called."""

        retry = 0
        while not self._stop.is_set():
            try:
                try:
                    self._ws = await websockets.connect(
                        self.ws_url,
                        extra_headers=self._headers(),
                        ping_interval=None,
                        close_timeout=5,
                        max_size=8 * 1024 * 1024,
                    )
                except TypeError:
                    self._ws = await websockets.connect(
                        self.ws_url,
                        additional_headers=self._headers(),
                        ping_interval=None,
                        close_timeout=5,
                        max_size=8 * 1024 * 1024,
                    )

                self._last_heartbeat_ack = time.time()
                await self._register()
                retry = 0

                while not self._stop.is_set():
                    now = time.time()
                    if now - self._last_heartbeat_send >= float(self.heartbeat_interval):
                        await self._send_heartbeat()
                    if now - self._last_heartbeat_ack > float(self.heartbeat_interval + self.heartbeat_timeout):
                        raise RuntimeError("heartbeat timeout")

                    try:
                        raw = await asyncio.wait_for(self._ws.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    packet = json.loads(raw)
                    if isinstance(packet, dict):
                        if packet.get("code") == 200:
                            self._last_heartbeat_ack = time.time()
                        await self._ack_packet(packet)
                        await self._handle_sync(packet)

            except asyncio.CancelledError:
                raise
            except Exception:
                retry += 1
                delay = min(
                    self.reconnect_base_delay * (self.reconnect_backoff ** max(0, retry - 1)) + random.uniform(0, 1),
                    self.reconnect_max_delay,
                )
                await asyncio.sleep(delay)
            finally:
                if self._ws is not None:
                    try:
                        await self._ws.close()
                    except Exception:
                        pass
                    self._ws = None

    async def next_event(self) -> dict[str, Any]:
        """Wait and return next incoming chat event."""

        return await self._event_queue.get()

    async def send_text(self, chat_id: str, to_user_id: str, text: str) -> bool:
        """Send text reply to buyer."""

        if self._ws is None:
            return False

        payload = {"contentType": 1, "text": {"text": text}}
        payload_b64 = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("utf-8")
        msg = {
            "lwp": "/r/MessageSend/sendByReceiverScope",
            "headers": {"mid": generate_mid()},
            "body": [
                {
                    "uuid": generate_uuid(),
                    "cid": f"{chat_id}@goofish",
                    "conversationType": 1,
                    "content": {"contentType": 101, "custom": {"type": 1, "data": payload_b64}},
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
        except Exception:
            return False

    async def stop(self) -> None:
        """Stop run loop and close websocket."""

        self._stop.set()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
