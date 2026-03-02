"""Xianyu HTTP API wrapper for Lite mode."""

from __future__ import annotations

import hashlib
import json
import random
import re
import time
from typing import Any

import httpx


def parse_cookie_string(cookie_text: str) -> dict[str, str]:
    """Parse cookie header string to dict."""

    out: dict[str, str] = {}
    for part in re.split(r";\s*", str(cookie_text or "").strip()):
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            out[key] = value
    return out


def generate_sign(timestamp_ms: str, token: str, data: str, app_key: str = "34839810") -> str:
    """Generate mtop sign."""

    return hashlib.md5(f"{token}&{timestamp_ms}&{app_key}&{data}".encode("utf-8")).hexdigest()


def generate_device_id(user_id: str) -> str:
    """Generate pseudo device id compatible with goofish headers."""

    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    chunks: list[str] = []
    for i in range(36):
        if i in {8, 13, 18, 23}:
            chunks.append("-")
        elif i == 14:
            chunks.append("4")
        elif i == 19:
            rv = random.randint(0, 15)
            chunks.append(chars[(rv & 0x3) | 0x8])
        else:
            chunks.append(chars[random.randint(0, 15)])
    return "".join(chunks) + f"-{user_id}"


class XianyuApiClient:
    """Async HTTP client for login preflight, token refresh and item details."""

    def __init__(self, cookie_text: str):
        self.cookie_text = cookie_text.strip()
        self.cookies = parse_cookie_string(self.cookie_text)
        self.user_id = str(self.cookies.get("unb", "") or "").strip()
        if not self.user_id:
            raise ValueError("Invalid cookie: missing unb")
        self.device_id = generate_device_id(self.user_id)

        self._token: str = ""
        self._token_ts: float = 0.0

    def update_cookie(self, cookie_text: str) -> None:
        """Hot update cookie values and regenerate identity fields."""

        self.cookie_text = cookie_text.strip()
        self.cookies = parse_cookie_string(self.cookie_text)
        self.user_id = str(self.cookies.get("unb", "") or "").strip()
        if not self.user_id:
            raise ValueError("Invalid cookie: missing unb")
        self.device_id = generate_device_id(self.user_id)
        self._token = ""
        self._token_ts = 0.0

    def _headers(self) -> dict[str, str]:
        return {
            "accept": "application/json",
            "origin": "https://www.goofish.com",
            "referer": "https://www.goofish.com/",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/133.0.0.0 Safari/537.36"
            ),
            "cookie": self.cookie_text,
        }

    async def has_login(self) -> bool:
        """Call hasLogin endpoint before token fetch."""

        data = {
            "hid": self.cookies.get("unb", ""),
            "ltl": "true",
            "appName": "xianyu",
            "appEntrance": "web",
            "_csrf_token": self.cookies.get("XSRF-TOKEN", ""),
            "hsiz": self.cookies.get("cookie2", ""),
            "bizParams": "taobaoBizLoginFrom=web",
            "mainPage": "false",
            "isMobile": "false",
            "lang": "zh_CN",
            "fromSite": "77",
            "isIframe": "true",
            "defaultView": "hasLogin",
            "umidTag": "SERVER",
            "deviceId": self.cookies.get("cna", "") or self.device_id,
        }
        params = {"appName": "xianyu", "fromSite": "77"}

        async with httpx.AsyncClient(timeout=12.0, headers=self._headers(), cookies=self.cookies) as client:
            resp = await client.post("https://passport.goofish.com/newlogin/hasLogin.do", params=params, data=data)
            payload = resp.json()
            return bool((payload or {}).get("content", {}).get("success"))

    async def get_token(self, *, max_attempts: int = 3, force_refresh: bool = False) -> str:
        """Get access token from mtop idlemessage token API."""

        if self._token and not force_refresh and (time.time() - self._token_ts) < 3500:
            return self._token

        for attempt in range(1, max_attempts + 1):
            token_seed = str(self.cookies.get("_m_h5_tk", "")).split("_")[0].strip()
            if not token_seed:
                raise ValueError("Cookie missing _m_h5_tk")

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

            try:
                async with httpx.AsyncClient(timeout=12.0, headers=self._headers()) as client:
                    resp = await client.post(
                        "https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/",
                        params=params,
                        data={"data": data_val},
                    )
                    payload: dict[str, Any] = resp.json()
            except Exception:
                if attempt >= max_attempts:
                    raise
                continue

            ret = payload.get("ret", [])
            if not any("SUCCESS::调用成功" in str(x) for x in ret):
                if attempt >= max_attempts:
                    raise ValueError(f"Token API failed: {ret}")
                continue

            token = str(payload.get("data", {}).get("accessToken", "") or "").strip()
            if not token:
                if attempt >= max_attempts:
                    raise ValueError("Token API succeeded but accessToken missing")
                continue

            self._token = token
            self._token_ts = time.time()
            return token

        raise ValueError("Token fetch failed")

    async def get_item_info(self, item_id: str, *, max_attempts: int = 3) -> dict[str, Any]:
        """Fetch item details from mtop idle.pc.detail."""

        token_seed = str(self.cookies.get("_m_h5_tk", "")).split("_")[0].strip()
        if not token_seed:
            raise ValueError("Cookie missing _m_h5_tk")

        for attempt in range(1, max_attempts + 1):
            t = str(int(time.time() * 1000))
            data_val = json.dumps({"itemId": item_id}, ensure_ascii=False, separators=(",", ":"))
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
                "api": "mtop.taobao.idle.pc.detail",
                "sessionOption": "AutoLoginOnly",
            }
            try:
                async with httpx.AsyncClient(timeout=12.0, headers=self._headers()) as client:
                    resp = await client.post(
                        "https://h5api.m.goofish.com/h5/mtop.taobao.idle.pc.detail/1.0/",
                        params=params,
                        data={"data": data_val},
                    )
                    payload = resp.json()
            except Exception:
                if attempt >= max_attempts:
                    raise
                continue
            ret = payload.get("ret", []) if isinstance(payload, dict) else []
            if any("SUCCESS::调用成功" in str(x) for x in ret):
                return payload
            if attempt >= max_attempts:
                raise ValueError(f"Item API failed: {ret}")

        raise ValueError("Item detail fetch failed")
