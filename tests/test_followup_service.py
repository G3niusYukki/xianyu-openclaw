from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.modules.followup import FollowUpEngine, FollowUpPolicy
from src.modules.followup import service as followup_service


class _FakeDateTime(datetime):
    _hour = 0

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 1, 1, cls._hour, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def engine(tmp_path):
    return FollowUpEngine(db_path=str(tmp_path / "followup.db"))


def test_followup_init_export_and_db_created(tmp_path):
    eng = FollowUpEngine(db_path=str(tmp_path / "x.db"))
    assert eng.db_path.exists()
    assert "FollowUpEngine" in __import__("src.modules.followup", fromlist=["__all__"]).__all__


def test_is_silent_hours_cross_day_and_normal(monkeypatch, engine):
    monkeypatch.setattr(followup_service, "datetime", _FakeDateTime)

    _FakeDateTime._hour = 23
    assert engine._is_silent_hours() is True
    _FakeDateTime._hour = 9
    assert engine._is_silent_hours() is False

    engine.policy = FollowUpPolicy(silent_hours_start=9, silent_hours_end=17)
    _FakeDateTime._hour = 10
    assert engine._is_silent_hours() is True
    _FakeDateTime._hour = 20
    assert engine._is_silent_hours() is False


def test_dnd_add_remove_and_query(engine):
    sid = "s1"
    assert engine._is_on_dnd_list(sid) is False
    assert engine.add_dnd(sid, "reject") is True
    assert engine._is_on_dnd_list(sid) is True
    dnd_list = engine.get_dnd_list()
    assert len(dnd_list) == 1 and dnd_list[0]["reason"] == "reject"
    assert engine.remove_dnd(sid) is True
    assert engine.remove_dnd(sid) is False


def test_check_eligibility_branches(monkeypatch, engine):
    monkeypatch.setattr(engine, "_is_on_dnd_list", lambda *_: True)
    ok, reason = engine.check_eligibility("s")
    assert (ok, reason) == (False, "do_not_disturb")

    monkeypatch.setattr(engine, "_is_on_dnd_list", lambda *_: False)
    monkeypatch.setattr(engine, "_is_silent_hours", lambda: True)
    ok, reason = engine.check_eligibility("s")
    assert (ok, reason) == (False, "silent_hours")

    monkeypatch.setattr(engine, "_is_silent_hours", lambda: False)
    monkeypatch.setattr(engine, "_get_touch_stats", lambda *_: (engine.policy.max_touches_per_day, 0))
    ok, reason = engine.check_eligibility("s")
    assert ok is False and reason.startswith("daily_limit:")

    monkeypatch.setattr(engine, "_get_touch_stats", lambda *_: (0, 10_000))
    monkeypatch.setattr(followup_service.time, "time", lambda: 10_000 + 60)
    ok, reason = engine.check_eligibility("s")
    assert ok is False and reason.startswith("cooldown:")

    monkeypatch.setattr(engine, "_get_touch_stats", lambda *_: (0, 0))
    ok, reason = engine.check_eligibility("s", last_read_at=100, last_reply_at=101)
    assert (ok, reason) == (False, "already_replied")

    ok, reason = engine.check_eligibility("s", last_read_at=101, last_reply_at=100)
    assert (ok, reason) == (True, "eligible")


def test_select_and_validate_template(engine):
    assert engine.select_template(-1) is None
    assert engine.select_template(999)["id"] == engine.templates[-1]["id"]

    bad, reason = engine.validate_template("请加我vx")
    assert bad is False and reason.startswith("forbidden_keyword:")

    bad, reason = engine.validate_template("hello world")
    assert bad is False and reason == "missing_service_keyword"

    ok, reason = engine.validate_template("您好，需要帮助请告诉我")
    assert (ok, reason) == (True, "valid")


def test_record_audit_and_stats(engine):
    rowcount = engine.record_trigger("sess", "acc", "followup", "tpl1", "sent", {"k": "v"})
    assert rowcount == 1

    logs = engine.get_audit_log(session_id="sess", account_id="acc", limit=0)
    assert len(logs) == 1
    assert logs[0]["metadata"] == {"k": "v"}

    stats = engine.get_stats()
    assert stats["total_triggers"] == 1
    assert stats["sent_count"] == 1
    assert stats["policy_version"] == "v1"


def test_process_session_noneligible_and_template_paths(monkeypatch, engine):
    monkeypatch.setattr(engine, "check_eligibility", lambda **_: (False, "x"))
    out = engine.process_session("s")
    assert out["eligible"] is False and out["reason"] == "x"

    monkeypatch.setattr(engine, "check_eligibility", lambda **_: (True, "eligible"))
    monkeypatch.setattr(engine, "_get_touch_stats", lambda *_: (0, 0))
    monkeypatch.setattr(engine, "select_template", lambda *_: None)
    out = engine.process_session("s")
    assert out["reason"] == "no_template"

    monkeypatch.setattr(engine, "select_template", lambda *_: {"id": "a", "text": "bad"})
    monkeypatch.setattr(engine, "validate_template", lambda *_: (False, "missing_service_keyword"))
    out = engine.process_session("s")
    assert out["reason"].startswith("template_invalid:")


def test_process_session_success_and_dry_run(monkeypatch, engine):
    monkeypatch.setattr(engine, "check_eligibility", lambda **_: (True, "eligible"))
    monkeypatch.setattr(engine, "_get_touch_stats", lambda *_: (1, 0))
    monkeypatch.setattr(engine, "select_template", lambda *_: {"id": "t2", "text": "您好，需要帮助可以留言"})
    monkeypatch.setattr(engine, "validate_template", lambda *_: (True, "valid"))

    calls = []

    def fake_record(**kwargs):
        calls.append(kwargs)
        return 1

    monkeypatch.setattr(engine, "record_trigger", fake_record)

    out = engine.process_session("sid", account_id="aid", dry_run=False)
    assert out["eligible"] is True and out["audit_id"] == 1
    assert calls[-1]["status"] == "sent"

    out2 = engine.process_session("sid", account_id="aid", dry_run=True)
    assert out2["dry_run"] is True
    assert calls[-1]["status"] == "dry_run"
