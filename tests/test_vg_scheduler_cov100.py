from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.modules.virtual_goods.scheduler import VirtualGoodsScheduler


def _make_service(**attrs):
    svc = MagicMock()
    for k, v in attrs.items():
        setattr(svc, k, v)
    return svc


class TestInvoke:
    def test_method_not_found(self):
        svc = MagicMock(spec=[])
        scheduler = VirtualGoodsScheduler(svc)
        with pytest.raises(AttributeError, match="service method not found"):
            scheduler._invoke(["nonexistent_method"])


class TestTimeoutScan:
    def test_attribute_error(self):
        svc = MagicMock(spec=[])
        scheduler = VirtualGoodsScheduler(svc)
        result = scheduler.timeout_scan()
        assert result["ok"] is False
        assert len(result["errors"]) > 0

    def test_resolve_exception(self):
        svc = MagicMock()
        svc.list_timeout_candidates.return_value = [{"id": "o1"}]
        svc.resolve_timeout_order.side_effect = RuntimeError("resolve fail")
        scheduler = VirtualGoodsScheduler(svc)
        result = scheduler.timeout_scan()
        assert result["ok"] is False
        assert result["metrics"]["failed"] == 1

    def test_resolve_returns_not_ok(self):
        svc = MagicMock()
        svc.list_timeout_candidates.return_value = [{"id": "o1"}]
        svc.resolve_timeout_order.return_value = {"ok": False, "error": "test"}
        scheduler = VirtualGoodsScheduler(svc)
        result = scheduler.timeout_scan()
        assert result["ok"] is False
        assert result["metrics"]["failed"] == 1


class TestCallbackReplay:
    def test_attribute_error(self):
        svc = MagicMock(spec=[])
        scheduler = VirtualGoodsScheduler(svc)
        result = scheduler.callback_replay()
        assert result["ok"] is False

    def test_unknown_event_kind(self):
        svc = MagicMock()
        svc.list_replay_callbacks.return_value = [{"event_kind": "weird"}]
        scheduler = VirtualGoodsScheduler(svc)
        result = scheduler.callback_replay()
        assert result["metrics"]["unknown_event_kind"] == 1
        assert result["ok"] is False

    def test_unknown_event_kind_with_reporter(self):
        svc = MagicMock()
        svc.list_replay_callbacks.return_value = [{"event_kind": "weird"}]
        svc.report_scheduler_anomaly = MagicMock()
        scheduler = VirtualGoodsScheduler(svc)
        result = scheduler.callback_replay()
        svc.report_scheduler_anomaly.assert_called_once()

    def test_replay_returns_not_ok(self):
        svc = MagicMock()
        svc.list_replay_callbacks.return_value = [{"event_kind": "order"}]
        svc.replay_callback.return_value = {"ok": False, "error": "replay_fail"}
        scheduler = VirtualGoodsScheduler(svc)
        result = scheduler.callback_replay()
        assert result["ok"] is False
        assert result["metrics"]["failed"] == 1

    def test_replay_exception(self):
        svc = MagicMock()
        svc.list_replay_callbacks.return_value = [{"event_kind": "order"}]
        svc.replay_callback.side_effect = RuntimeError("boom")
        scheduler = VirtualGoodsScheduler(svc)
        result = scheduler.callback_replay()
        assert result["ok"] is False
        assert result["metrics"]["failed"] == 1


class TestManualTakeoverObserve:
    def test_attribute_error(self):
        svc = MagicMock(spec=[])
        scheduler = VirtualGoodsScheduler(svc)
        result = scheduler.manual_takeover_observe()
        assert result["ok"] is False

    def test_observe_not_ok(self):
        svc = MagicMock()
        svc.list_manual_takeover_orders.return_value = [{"id": "o1"}]
        svc.observe_manual_takeover_order.return_value = {"ok": False, "error": "fail"}
        scheduler = VirtualGoodsScheduler(svc)
        result = scheduler.manual_takeover_observe()
        assert result["ok"] is False
        assert result["metrics"]["failed"] == 1

    def test_observe_escalated(self):
        svc = MagicMock()
        svc.list_manual_takeover_orders.return_value = [{"id": "o1"}]
        svc.observe_manual_takeover_order.return_value = {"ok": True, "escalated": True}
        scheduler = VirtualGoodsScheduler(svc)
        result = scheduler.manual_takeover_observe()
        assert result["metrics"]["escalated"] == 1

    def test_observe_exception(self):
        svc = MagicMock()
        svc.list_manual_takeover_orders.return_value = [{"id": "o1"}]
        svc.observe_manual_takeover_order.side_effect = RuntimeError("boom")
        scheduler = VirtualGoodsScheduler(svc)
        result = scheduler.manual_takeover_observe()
        assert result["ok"] is False
        assert result["metrics"]["failed"] == 1
