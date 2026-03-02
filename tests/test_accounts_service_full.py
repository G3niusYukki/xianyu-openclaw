from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from src.modules.accounts.service import AccountHealth, AccountStatus, AccountsService


def _cfg(accounts):
    return SimpleNamespace(accounts=accounts)


def _make_service(tmp_path, monkeypatch, accounts):
    monkeypatch.chdir(tmp_path)
    return AccountsService(config=_cfg(accounts))


def test_load_accounts_with_env_and_masking(tmp_path, monkeypatch):
    monkeypatch.setenv("ACC_COOKIE", "A" * 60)
    svc = _make_service(
        tmp_path,
        monkeypatch,
        [{"id": "a1", "name": "主号", "cookie": "${ACC_COOKIE}", "priority": 3, "enabled": False}],
    )

    # enabled_only True -> filtered out
    assert svc.get_accounts(enabled_only=True) == []

    # enabled_only False and mask_sensitive False -> includes encrypted field only
    all_accounts = svc.get_accounts(enabled_only=False, mask_sensitive=False)
    assert len(all_accounts) == 1
    assert all_accounts[0]["priority"] == 3
    assert all_accounts[0]["enabled"] is False
    assert all_accounts[0]["cookie_encrypted"]

    raw = svc.get_account("a1", mask_sensitive=False)
    assert raw is not None and raw["cookie"] == "A" * 60

    # mask branch
    masked = svc.get_account("a1", mask_sensitive=True)
    assert masked is not None
    assert masked["cookie"].startswith("AAAAA...")


def test_load_accounts_empty_warn_and_short_mask(tmp_path, monkeypatch, capsys):
    svc = _make_service(tmp_path, monkeypatch, [])
    assert svc.accounts == []
    assert svc._mask_sensitive_data("short", show_chars=3) == "****"
    out = capsys.readouterr().out
    assert "No accounts configured" in out


def test_load_account_stats_file_success_and_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)

    stats_path = data_dir / "account_stats.json"
    stats_path.write_text(json.dumps({"a1": {"total_published": 1}}), encoding="utf-8")
    svc_ok = AccountsService(config=_cfg([]))
    assert svc_ok.account_stats["a1"]["total_published"] == 1

    stats_path.write_text("{ bad json", encoding="utf-8")
    svc_bad = AccountsService(config=_cfg([]))
    assert svc_bad.account_stats == {}
    out = capsys.readouterr().out
    assert "Failed to load account stats" in out


def test_current_account_selection_and_set_and_next(tmp_path, monkeypatch):
    svc = _make_service(
        tmp_path,
        monkeypatch,
        [
            {"id": "a1", "cookie": "B" * 60, "priority": 2},
            {"id": "a2", "cookie": "C" * 60, "priority": 1},
        ],
    )

    cur = svc.get_current_account()
    assert cur is not None and cur["id"] == "a2"

    assert svc.set_current_account("a1") is True
    assert svc.get_current_account()["id"] == "a1"
    assert svc.set_current_account("missing") is False

    nxt = svc.get_next_account()
    assert nxt is not None and nxt["id"] == "a2"


def test_get_cookie_none_and_missing_and_existing(tmp_path, monkeypatch):
    svc = _make_service(tmp_path, monkeypatch, [{"id": "a1", "cookie": "D" * 60}])
    assert svc.get_cookie("missing") is None

    svc.accounts.append({"id": "x", "cookie_encrypted": ""})
    assert svc.get_cookie("x") is None

    svc.current_account_id = "a1"
    assert svc.get_cookie() == "D" * 60


def test_add_update_enable_disable_remove_account(tmp_path, monkeypatch):
    svc = _make_service(tmp_path, monkeypatch, [{"id": "a1", "cookie": "E" * 60}])

    assert svc.add_account("a2", "F" * 60, name="次号", priority=9) is True
    assert svc.add_account("a2", "dup") is False

    assert svc.disable_account("a2") is True
    assert svc.get_account("a2", mask_sensitive=False)["status"] == AccountStatus.MAINTENANCE
    assert svc.enable_account("a2") is True
    assert svc.get_account("a2", mask_sensitive=False)["status"] == AccountStatus.ACTIVE
    assert svc.disable_account("missing") is False
    assert svc.enable_account("missing") is False

    assert svc.update_account("a2", name="改名", cookie="G" * 60, priority=1, enabled=False) is True
    updated = svc.get_account("a2", mask_sensitive=False)
    assert updated["name"] == "改名"
    assert updated["priority"] == 1
    assert updated["enabled"] is False
    assert updated["status"] == AccountStatus.MAINTENANCE
    assert updated["last_login"] is not None

    assert svc.update_account("missing", name="x") is False

    assert svc.remove_account("a2") is True
    assert svc.remove_account("a2") is False


def test_update_stats_health_and_dashboard_and_distribution(tmp_path, monkeypatch):
    svc = _make_service(
        tmp_path,
        monkeypatch,
        [
            {"id": "a1", "cookie": "H" * 60, "enabled": True},
            {"id": "a2", "cookie": "I" * 60, "enabled": True},
        ],
    )

    svc.update_account_stats("a1", "publish", success=True)
    svc.update_account_stats("a1", "polish", success=True)
    svc.update_account_stats("a1", "error", success=False)
    svc.update_account_stats("a1", "other", success=True)

    h = svc.get_account_health("a1")
    assert h["total_published"] == 1
    assert h["total_polished"] == 1
    assert h["total_errors"] == 1

    svc.account_stats["warn"] = {"health_score": 70}
    svc.account_stats["bad"] = {"health_score": 30}
    assert svc.get_account_health("warn")["health"] == AccountHealth.WARNING
    assert svc.get_account_health("bad")["health"] == AccountHealth.BAD

    svc.account_stats["a1"]["total_views"] = 12
    svc.account_stats["a1"]["total_wants"] = 5
    dash = svc.get_unified_dashboard()
    assert dash["total_accounts"] == 2
    assert dash["active_accounts"] == 2
    assert dash["total_products"] >= 1
    assert dash["total_views"] == 12
    assert dash["total_wants"] == 5
    assert len(dash["accounts_health"]) == 2

    dist = svc.distribute_publish(count=5)
    assert sum(x["count"] for x in dist) == 5
    assert svc.distribute_publish(count=0) == []

    svc.accounts.clear()
    assert svc.distribute_publish(3) == []


def test_refresh_and_validate_cookie_all_branches(tmp_path, monkeypatch, capsys):
    svc = _make_service(tmp_path, monkeypatch, [{"id": "a1", "cookie": "J" * 60}])

    assert svc.refresh_cookie("a1", "K" * 60) is True
    assert svc.refresh_cookie("missing", "x") is False

    assert svc.validate_cookie("missing") is False

    svc.update_account("a1", cookie="short")
    assert svc.validate_cookie("a1") is False

    svc.update_account("a1", cookie="L" * 60)
    assert svc.validate_cookie("a1") is True

    old = (datetime.now() - timedelta(days=8)).isoformat()
    for acc in svc.accounts:
        if acc["id"] == "a1":
            acc["last_login"] = old
    assert svc.validate_cookie("a1") is False
    out = capsys.readouterr().out
    assert "Cookie may be expired" in out


def test_get_account_none_and_get_next_no_accounts(tmp_path, monkeypatch):
    svc = _make_service(tmp_path, monkeypatch, [])
    assert svc.get_account("none") is None
    assert svc.get_current_account() is None
    assert svc.get_next_account() is None
