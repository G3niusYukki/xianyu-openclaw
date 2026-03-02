from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.lite.ws_client import LiteWsClient
from src.lite.xianyu_api import XianyuApiClient
from src.modules.compliance.center import ComplianceCenter
from src.modules.quote.providers import _normalize_markup_rules, _parse_cost_api_response
from src.modules.quote.setup import QuoteSetupService


def test_quote_setup_scan_and_load_missing_lines(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text("[]\n", encoding="utf-8")
    svc = QuoteSetupService(config_path=str(cfg))
    data, existed = svc._load_yaml()
    assert data == {} and existed is True

    cdir = tmp_path / "conf"
    cdir.mkdir()
    (cdir / "config.example.yaml").write_text("[]\n", encoding="utf-8")
    svc2 = QuoteSetupService(config_path=str(cdir / "config.yaml"))
    data2, existed2 = svc2._load_yaml()
    assert data2 == {} and existed2 is False

    costs = tmp_path / "costs"
    costs.mkdir()
    (costs / "a.csv").write_text("x", encoding="utf-8")
    stats = QuoteSetupService._scan_cost_table_dir(str(costs), ["   ", "*.csv"])
    assert stats["exists"] is True
    assert stats["file_count"] == 1


@pytest.mark.asyncio
async def test_xianyu_api_retry_continue_paths(monkeypatch) -> None:
    api = XianyuApiClient("unb=u1; _m_h5_tk=tk_seed")

    token_calls = {"n": 0}

    class TokenClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def post(self, *_a, **_k):
            token_calls["n"] += 1
            if token_calls["n"] == 1:
                raise RuntimeError("temporary network")
            return type("R", (), {"json": lambda _s: {"ret": ["SUCCESS::调用成功"], "data": {"accessToken": "tok"}}})()

    monkeypatch.setattr("src.lite.xianyu_api.httpx.AsyncClient", lambda **_k: TokenClient())
    token = await api.get_token(max_attempts=2, force_refresh=True)
    assert token == "tok"
    assert token_calls["n"] == 2

    item_calls = {"n": 0}

    class ItemClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def post(self, *_a, **_k):
            item_calls["n"] += 1
            if item_calls["n"] == 1:
                raise RuntimeError("temporary item network")
            return type("R", (), {"json": lambda _s: {"ret": ["SUCCESS::调用成功"], "data": {"id": "1"}}})()

    monkeypatch.setattr("src.lite.xianyu_api.httpx.AsyncClient", lambda **_k: ItemClient())
    payload = await api.get_item_info("1", max_attempts=2)
    assert payload.get("data", {}).get("id") == "1"
    assert item_calls["n"] == 2


@pytest.mark.asyncio
async def test_ws_client_timeout_continue_lines(monkeypatch) -> None:
    async def token_provider() -> str:
        return "t"

    c = LiteWsClient(ws_url="ws://x", cookie="unb=u1", device_id="d", my_user_id="u", token_provider=token_provider)

    class FakeWs:
        def __init__(self):
            self.n = 0

        async def send(self, _data):
            return None

        async def recv(self):
            self.n += 1
            if self.n == 1:
                await asyncio.sleep(2)
                return "{}"
            c._stop.set()
            return '{"code": 200}'

        async def close(self):
            return None

    async def connect(*_a, **_k):
        return FakeWs()

    monkeypatch.setattr("src.lite.ws_client.websockets.connect", connect)
    await asyncio.wait_for(c.run_forever(), timeout=5)


def test_quote_providers_parse_and_unreachable_note() -> None:
    parsed = _parse_cost_api_response(["not-a-dict"])
    assert parsed["provider"] is None

    normalized = _normalize_markup_rules({"yd": {"normal_first_add": 1.0}})
    assert "default" in normalized


def test_compliance_session_rate_limit_line(tmp_path: Path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text(
        """
global:
  rate_limit:
    session:
      window_seconds: 3600
      max_messages: 1
""".strip(),
        encoding="utf-8",
    )
    center = ComplianceCenter(policy_path=str(policy), db_path=str(tmp_path / "c.db"))

    first = center.evaluate_before_send("hello", actor="a", account_id="acc", session_id="sess", action="message_send")
    assert first.allowed is True

    second = center.evaluate_before_send("hello again", actor="a", account_id="acc", session_id="sess", action="message_send")
    assert second.allowed is False
    assert second.reason.startswith("session_rate_limit:")

@pytest.mark.asyncio
async def test_xianyu_api_token_missing_then_retry(monkeypatch) -> None:
    api = XianyuApiClient("unb=u1; _m_h5_tk=tk_seed")
    calls = {"n": 0}

    class RetryTokenClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def post(self, *_a, **_k):
            calls["n"] += 1
            if calls["n"] == 1:
                return type("R", (), {"json": lambda _s: {"ret": ["SUCCESS::调用成功"], "data": {}}})()
            return type("R", (), {"json": lambda _s: {"ret": ["SUCCESS::调用成功"], "data": {"accessToken": "tok2"}}})()

    monkeypatch.setattr("src.lite.xianyu_api.httpx.AsyncClient", lambda **_k: RetryTokenClient())
    tok = await api.get_token(max_attempts=2, force_refresh=True)
    assert tok == "tok2"
    assert calls["n"] == 2
