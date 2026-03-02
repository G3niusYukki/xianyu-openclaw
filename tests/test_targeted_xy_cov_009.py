from __future__ import annotations

import asyncio
import socket
from pathlib import Path

import pytest

import src.core.config as cfg_mod
import src.core.doctor as doctor
import src.setup_wizard as sw
from src.core.config import Config
from src.core.config_models import AppConfig, MessagesConfig
from src.core.error_handler import ConfigError
from src.lite.msgpack import decrypt_payload
from src.lite.ws_client import LiteWsClient
from src.lite.xianyu_api import XianyuApiClient
from src.modules.compliance.center import ComplianceCenter
from src.modules.media.utils import add_watermark
from src.modules.quote.cache import QuoteCache
from src.modules.quote.models import QuoteResult, QuoteSnapshot
from src.modules.quote.providers import _normalize_markup_rules, _parse_cost_api_response
from src.modules.quote.route import contains_match
from src.modules.quote.setup import QuoteSetupService


def test_quote_models_missing_branches() -> None:
    result = QuoteResult(
        provider="p",
        base_fee=3,
        total_fee=3,
        eta_minutes=0,
        snapshot=QuoteSnapshot(cost_source="api"),
        explain={"billing_weight_kg": "oops"},
    )
    assert result.to_dict()["snapshot"]["cost_source"] == "api"
    reply = result.compose_reply(template="{additional_units}|{eta_days}")
    assert reply.startswith("0.0|1天")
    assert QuoteResult._format_days_from_minutes(2160) == "1.5天"


@pytest.mark.asyncio
async def test_xianyu_api_retry_and_final_raise_paths(monkeypatch) -> None:
    api = XianyuApiClient("unb=u1; _m_h5_tk=tk_1")

    class FailClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def post(self, *_a, **_k):
            raise RuntimeError("net")

    monkeypatch.setattr("src.lite.xianyu_api.httpx.AsyncClient", lambda **_k: FailClient())
    with pytest.raises(ValueError, match="Token fetch failed"):
        await api.get_token(max_attempts=0)
    with pytest.raises(ValueError, match="Item detail fetch failed"):
        await api.get_item_info("1", max_attempts=0)


def test_quote_setup_load_yaml_non_dict_paths(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text("[]\n", encoding="utf-8")
    svc = QuoteSetupService(config_path=str(cfg))
    data, existed = svc._load_yaml()
    assert data == {}
    assert existed is True

    cdir = tmp_path / "c"
    cdir.mkdir()
    (cdir / "config.example.yaml").write_text("[]\n", encoding="utf-8")
    svc2 = QuoteSetupService(config_path=str(cdir / "config.yaml"))
    data2, existed2 = svc2._load_yaml()
    assert data2 == {}
    assert existed2 is False


def test_quote_provider_helper_missing_branches() -> None:
    assert "default" in _normalize_markup_rules("bad")
    assert _parse_cost_api_response("bad")["provider"] is None


def test_quote_cache_expired_eviction(monkeypatch) -> None:
    cache = QuoteCache(ttl_seconds=1, max_stale_seconds=1)
    cache.set("k", QuoteResult(provider="p", base_fee=1, total_fee=1))
    monkeypatch.setattr("src.modules.quote.cache.time.time", lambda: 9999999999)
    got, hit, stale = cache.get("k")
    assert got is None and hit is False and stale is False


def test_quote_route_contains_match_len_guard(monkeypatch) -> None:
    monkeypatch.setattr("src.modules.quote.route.GeoResolver.normalize", lambda s: str(s or "").strip())
    assert contains_match("", "广州", "杭州", "广州") is False
    assert contains_match("浙江杭州", "广东", "杭州", "广东") is True


def test_media_utils_font_fallback(monkeypatch, tmp_path: Path) -> None:
    from PIL import Image, ImageFont

    src = tmp_path / "a.png"
    out = tmp_path / "b.png"
    Image.new("RGB", (20, 20), (0, 0, 0)).save(src)
    orig = ImageFont.truetype

    def _tt(name, *a, **k):
        if str(name) == "Arial.ttf":
            raise OSError("x")
        return orig(name, *a, **k)

    monkeypatch.setattr("src.modules.media.utils.ImageFont.truetype", _tt)
    assert add_watermark(str(src), str(out), text="x") is True


def test_msgpack_double_decode_fail_returns_none(monkeypatch) -> None:
    monkeypatch.setattr("src.lite.msgpack.base64.b64decode", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("x")))
    monkeypatch.setattr("src.lite.msgpack.base64.urlsafe_b64decode", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("y")))
    assert decrypt_payload("abc") is None


@pytest.mark.asyncio
async def test_ws_client_cancelled_error_reraised(monkeypatch) -> None:
    async def token_provider() -> str:
        return "t"

    c = LiteWsClient(ws_url="ws://x", cookie="c", device_id="d", my_user_id="u", token_provider=token_provider)

    async def connect(*_a, **_k):
        raise asyncio.CancelledError()

    monkeypatch.setattr("src.lite.ws_client.websockets.connect", connect)
    with pytest.raises(asyncio.CancelledError):
        await c.run_forever()


def test_doctor_port_open_and_urlerror_branch(monkeypatch) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    try:
        assert doctor._check_port_open(port) is True
    finally:
        sock.close()

    monkeypatch.setattr(doctor, "resolve_runtime_mode", lambda: "pro")
    monkeypatch.setattr(doctor.Path, "exists", lambda self: True)
    monkeypatch.setattr(doctor, "_check_port_open", lambda p, **_k: p == 8091)

    def _urlerr(*_a, **_k):
        raise doctor.urllib.error.URLError("bad")

    monkeypatch.setattr(doctor.urllib.request, "urlopen", _urlerr)

    class _Cfg:
        def get_section(self, *_a, **_k):
            return {}

    monkeypatch.setattr(doctor, "get_config", lambda: _Cfg())
    checks = doctor._extra_checks(skip_quote=True)
    assert any("Dashboard API 不可用" in c["message"] for c in checks if c["name"] == "Dashboard守护状态")


def test_config_missing_lines(monkeypatch, tmp_path: Path) -> None:
    Config._instance = None
    Config._config = {}
    c = Config(config_path=str(tmp_path / "a.yaml"))
    called = {"v": False}
    monkeypatch.setattr(c, "reload", lambda *_a, **_k: called.__setitem__("v", True))
    monkeypatch.setattr(c, "_find_config_file", lambda: "b.yaml")
    c.__init__(config_path=None)
    assert called["v"] is True

    c._find_config_file = Config._find_config_file.__get__(c, Config)
    monkeypatch.setattr(cfg_mod.os.path, "exists", lambda _p: False)
    assert c._find_config_file() is None

    bad = tmp_path / "bad.yaml"
    bad.write_text("ok: 1\n", encoding="utf-8")
    import src.core.config as _cfg

    class _YErr(Exception):
        pass

    monkeypatch.setattr(_cfg.yaml, "safe_load", lambda *_a, **_k: (_ for _ in ()).throw(_cfg.yaml.YAMLError("boom")))
    with pytest.raises(ConfigError, match="Invalid YAML"):
        c._load_yaml_config(str(bad))


def test_config_models_validation_errors() -> None:
    with pytest.raises(ValueError, match="dom\|ws\|auto"):
        MessagesConfig(transport="xxx")
    with pytest.raises(ValueError, match="runtime must be one of"):
        AppConfig(runtime="bad")


def test_compliance_auto_reload_branches(tmp_path: Path) -> None:
    policy = tmp_path / "p.yaml"
    policy.write_text("reload:\n  auto_reload: false\n", encoding="utf-8")
    center = ComplianceCenter(policy_path=str(policy), db_path=str(tmp_path / "c.db"))
    center._policy_mtime = policy.stat().st_mtime
    center._auto_reload()

    policy.write_text("reload:\n  auto_reload: true\n", encoding="utf-8")
    center.reload()
    old = center._policy_mtime
    policy.write_text("version: v2\n", encoding="utf-8")
    flag = {"v": False}

    def _reload():
        flag["v"] = True

    center.reload = _reload  # type: ignore[assignment]
    center._policy_mtime = old
    center._auto_reload()
    assert flag["v"] is True


def test_setup_wizard_start_now_runs_post_checks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sw, "_read_existing_env", lambda _p: {})
    monkeypatch.setattr(sw, "_choose_gateway_provider", lambda: sw.GATEWAY_PROVIDERS[0])
    monkeypatch.setattr(sw, "_choose_content_provider", lambda: sw.CONTENT_PROVIDERS[0])
    vals = iter(["gk", "tok", "8080", "admin", "pwd", "cookie", "", "", "Y"])
    monkeypatch.setattr(sw, "_prompt", lambda *_a, **_k: next(vals))
    monkeypatch.setattr(sw, "_ensure_docker_ready", lambda: True)
    ran = {"post": False}
    monkeypatch.setattr(sw, "_run_post_start_checks", lambda _p: ran.__setitem__("post", True))

    class R:
        returncode = 0

    monkeypatch.setattr(sw.subprocess, "run", lambda *_a, **_k: R())
    assert sw.run_setup() == 0
    assert ran["post"] is True
