import json
from types import SimpleNamespace

import pytest

import src.core.config as config_module
import src.core.doctor as doctor
import src.modules.content.service as content_module
from src.core.config import Config
from src.core.error_handler import ConfigError
from src.modules.content.service import ContentService


@pytest.fixture
def reset_config_singleton():
    Config._instance = None
    config_module.get_config.cache_clear()
    yield
    Config._instance = None
    config_module.get_config.cache_clear()


def test_doctor_check_port_open_invalid_and_oserror(monkeypatch):
    assert doctor._check_port_open(0) is False

    def _raise_socket(*_args, **_kwargs):
        raise OSError("socket down")

    monkeypatch.setattr(doctor.socket, "socket", _raise_socket)
    assert doctor._check_port_open(8080) is False


def test_doctor_extra_checks_non_lite_quote_needed_and_api_payload_missing(monkeypatch):
    monkeypatch.setattr(doctor, "resolve_runtime_mode", lambda: "pro")
    monkeypatch.setattr(doctor.Path, "exists", lambda self: True)
    monkeypatch.setattr(doctor, "_check_port_open", lambda *_a, **_k: True)

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"ok": True}).encode("utf-8")

    monkeypatch.setattr(doctor.urllib.request, "urlopen", lambda *_a, **_k: _Resp())

    class _Cfg:
        def get_section(self, section, default=None):
            if section == "messages":
                return {"fast_reply_enabled": True, "reply_target_seconds": 2.2}
            if section == "quote":
                return {
                    "mode": "api_cost_plus_markup",
                    "cost_table_dir": "data/quote_costs",
                    "cost_table_patterns": ["*.csv"],
                    "cost_api_url": "",
                }
            return default or {}

    class _Repo:
        def __init__(self, *_, **__):
            pass

        def get_stats(self, max_files=30):
            assert max_files == 30
            return {"total_records": 0, "files": ["cost.csv"]}

    monkeypatch.setattr(doctor, "get_config", lambda: _Cfg())
    monkeypatch.setattr(doctor, "CostTableRepository", _Repo)

    checks = doctor._extra_checks(skip_quote=False)

    web_ui = next(c for c in checks if c["name"] == "Web UI 端口")
    assert web_ui["passed"] is True
    assert web_ui["meta"]["port"] == 8080

    dashboard_daemon = next(c for c in checks if c["name"] == "Dashboard守护状态")
    assert dashboard_daemon["passed"] is False
    assert "缺少 service_status" in dashboard_daemon["message"]

    quote_source = next(c for c in checks if c["name"] == "自动报价成本源")
    assert quote_source["passed"] is False
    assert "需要成本源" in quote_source["message"]


def test_doctor_extra_checks_sla_and_quote_exceptions(monkeypatch):
    monkeypatch.setattr(doctor, "resolve_runtime_mode", lambda: "pro")
    monkeypatch.setattr(doctor.Path, "exists", lambda self: True)
    monkeypatch.setattr(doctor, "_check_port_open", lambda *_a, **_k: False)

    monkeypatch.setattr(
        doctor.urllib.request,
        "urlopen",
        lambda *_a, **_k: (_ for _ in ()).throw(doctor.urllib.error.URLError("unreachable")),
    )

    monkeypatch.setattr(doctor, "get_config", lambda: (_ for _ in ()).throw(RuntimeError("cfg broken")))
    checks = doctor._extra_checks(skip_quote=True)
    sla = next(c for c in checks if c["name"] == "消息首响SLA")
    assert sla["passed"] is False
    assert "cfg broken" in sla["message"]

    class _Cfg2:
        def get_section(self, section, default=None):
            if section == "messages":
                return {"fast_reply_enabled": False, "reply_target_seconds": 5}
            if section == "quote":
                return {"mode": "cost_table_plus_markup"}
            return default or {}

    class _BadRepo:
        def __init__(self, *_, **__):
            pass

        def get_stats(self, *_a, **_k):
            raise RuntimeError("table read failed")

    monkeypatch.setattr(doctor, "get_config", lambda: _Cfg2())
    monkeypatch.setattr(doctor, "CostTableRepository", _BadRepo)

    checks2 = doctor._extra_checks(skip_quote=False)
    quote = next(c for c in checks2 if c["name"] == "自动报价成本源")
    assert quote["passed"] is False
    assert "table read failed" in quote["message"]


def test_config_load_yaml_validation_error_and_file_errors(tmp_path, reset_config_singleton, monkeypatch):
    invalid_file = tmp_path / "invalid.yaml"
    invalid_file.write_text("app:\n  log_level: INVALID\n", encoding="utf-8")

    cfg = Config(str(tmp_path / "nope.yaml"))

    with pytest.raises(ConfigError):
        cfg._load_yaml_config(str(invalid_file))

    cfg._load_yaml_config(str(tmp_path / "not-found.yaml"))
    assert cfg._config == {}

    normal_file = tmp_path / "normal.yaml"
    normal_file.write_text("app:\n  name: demo\n", encoding="utf-8")
    monkeypatch.setattr(config_module.yaml, "safe_load", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(ConfigError):
        cfg._load_yaml_config(str(normal_file))


def test_config_properties_access(reset_config_singleton, tmp_path):
    config_file = tmp_path / "minimal.yaml"
    config_file.write_text("app:\n  name: demo\n", encoding="utf-8")
    cfg = Config(str(config_file))

    assert isinstance(cfg.app, dict)
    assert isinstance(cfg.openclaw, dict)
    assert isinstance(cfg.ai, dict)
    assert isinstance(cfg.media, dict)
    assert isinstance(cfg.content, dict)
    assert isinstance(cfg.messages, dict)


def test_content_service_call_ai_exception_branches(monkeypatch):
    class _DummyTimeout(Exception):
        pass

    class _DummyAPIError(Exception):
        pass

    monkeypatch.setattr(content_module, "APITimeoutError", _DummyTimeout)
    monkeypatch.setattr(content_module, "APIError", _DummyAPIError)
    monkeypatch.setattr(ContentService, "_init_client", lambda self: None)

    svc = ContentService(config={"api_key": "k", "usage_mode": "always", "task_switches": {}})

    def _build_client(exc):
        class _Create:
            @staticmethod
            def create(**_kwargs):
                raise exc

        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=_Create.create)))

    svc.client = _build_client(_DummyTimeout("t"))
    assert svc._call_ai("prompt", task="title") is None

    svc.client = _build_client(_DummyAPIError("api"))
    assert svc._call_ai("prompt2", task="title") is None

    svc.client = _build_client(RuntimeError("unexpected"))
    assert svc._call_ai("prompt3", task="title") is None


def test_content_service_description_optimize_and_keywords_branches(monkeypatch):
    monkeypatch.setattr(ContentService, "_init_client", lambda self: None)
    svc = ContentService(config={"api_key": "k", "usage_mode": "weird", "task_switches": {}})
    svc.client = object()

    assert svc._should_call_ai("title", "short") is False

    monkeypatch.setattr(svc, "_call_ai", lambda *_a, **_k: "太短")
    desc = svc.generate_description("相机", "95新", "换设备", ["数码"])
    assert "商品详情" in desc

    monkeypatch.setattr(svc, "_call_ai", lambda *_a, **_k: "优化标题挺好的")
    assert svc.optimize_title("旧标题") == "优化标题挺好的"

    monkeypatch.setattr(svc, "_call_ai", lambda *_a, **_k: "词A, 词B, 词C")
    assert svc.generate_seo_keywords("相机", "General") == ["词A", "词B", "词C"]

    assert svc._get_sample_keywords("不存在分类") == svc._get_category_keywords("General")


def test_content_service_cache_expire_and_disabled(monkeypatch):
    monkeypatch.setattr(ContentService, "_init_client", lambda self: None)
    svc = ContentService(config={"api_key": "k", "usage_mode": "always", "task_switches": {}, "cache_max_entries": 0})
    svc._cache_set("p", "title", "x")
    assert svc._cache_get("p", "title") is None

    svc2 = ContentService(config={"api_key": "k", "usage_mode": "always", "task_switches": {}, "cache_ttl_seconds": 1})
    key = svc2._cache_key("p", "title")
    svc2._response_cache[key] = (0.0, "expired")
    assert svc2._cache_get("p", "title") is None
    assert key not in svc2._response_cache


def test_doctor_extra_checks_dashboard_api_unknown_exception(monkeypatch):
    monkeypatch.setattr(doctor, "resolve_runtime_mode", lambda: "pro")
    monkeypatch.setattr(doctor.Path, "exists", lambda self: True)
    monkeypatch.setattr(doctor, "_check_port_open", lambda *_a, **_k: True)

    def _boom(*_a, **_k):
        raise RuntimeError("json parse failed")

    monkeypatch.setattr(doctor.urllib.request, "urlopen", _boom)

    class _Cfg:
        def get_section(self, section, default=None):
            if section == "messages":
                return {"fast_reply_enabled": True, "reply_target_seconds": 2.0}
            if section == "quote":
                return {"mode": "rule_only"}
            return default or {}

    monkeypatch.setattr(doctor, "get_config", lambda: _Cfg())

    checks = doctor._extra_checks(skip_quote=True)
    dashboard_daemon = next(c for c in checks if c["name"] == "Dashboard守护状态")
    assert dashboard_daemon["passed"] is False
    assert "Dashboard API 检查失败" in dashboard_daemon["message"]


def test_content_service_generate_description_accepts_ai_long_text(monkeypatch):
    monkeypatch.setattr(ContentService, "_init_client", lambda self: None)
    svc = ContentService(config={"api_key": "k", "usage_mode": "always", "task_switches": {}})
    svc.client = object()

    long_text = "这是一段足够长的描述" * 6
    monkeypatch.setattr(svc, "_call_ai", lambda *_a, **_k: long_text)

    desc = svc.generate_description("相机", "95新", "换设备", ["数码"])
    assert desc == long_text
    assert len(desc) >= 50
