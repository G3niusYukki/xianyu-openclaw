from __future__ import annotations

import argparse
import json
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from src.cli import cmd_module, cmd_orders, cmd_virtual_goods


def _ns(**kwargs):
    """Build an argparse.Namespace with defaults."""
    defaults = {
        "db_path": ":memory:",
        "action": "",
        "xgj_app_key": None,
        "xgj_app_secret": None,
        "xgj_merchant_id": None,
        "xgj_base_url": None,
        "dry_run": False,
        "max_events": 20,
        "event_id": None,
        "dedupe_key": None,
        "manual_action": None,
        "order_id": None,
        "order_ids": [],
        "enabled": True,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestCmdOrders:
    @pytest.mark.asyncio
    async def test_xianguanjia_config(self):
        ns = _ns(
            action="list",
            xgj_app_key="key123",
            xgj_app_secret="secret456",
        )
        with patch("src.cli.cmd_orders.__module__", "src.cli"), \
             patch("src.modules.orders.service.OrderFulfillmentService") as MockService:
            mock_svc = MagicMock()
            mock_svc.list_orders.return_value = []
            MockService.return_value = mock_svc
            with patch("src.cli._json_out"):
                await cmd_orders(ns)
            call_kwargs = MockService.call_args
            assert "config" in call_kwargs.kwargs or (len(call_kwargs.args) > 0)

    @pytest.mark.asyncio
    async def test_service_config_applied(self):
        ns = _ns(
            action="list",
            xgj_app_key="key",
            xgj_app_secret="sec",
        )
        with patch("src.modules.orders.service.OrderFulfillmentService") as MockService:
            mock_svc = MagicMock()
            mock_svc.list_orders.return_value = []
            MockService.return_value = mock_svc
            with patch("src.cli._json_out"):
                await cmd_orders(ns)
            kwargs = MockService.call_args[1]
            assert "config" in kwargs


class TestCmdVirtualGoods:
    @pytest.mark.asyncio
    async def test_scheduler_not_callable(self):
        ns = _ns(action="scheduler")
        captured = []
        with patch("src.modules.virtual_goods.service.VirtualGoodsService") as MockVGS:
            mock_svc = MagicMock(spec=[])
            MockVGS.return_value = mock_svc
            with patch("src.cli._json_out", side_effect=lambda d: captured.append(d)):
                await cmd_virtual_goods(ns)
        assert captured[0]["ok"] is False
        assert "service_method_not_available" in captured[0]["error"]

    @pytest.mark.asyncio
    async def test_replay_missing_ids(self):
        ns = _ns(action="replay", event_id=None, dedupe_key="")
        captured = []
        with patch("src.modules.virtual_goods.service.VirtualGoodsService") as MockVGS:
            MockVGS.return_value = MagicMock()
            with patch("src.cli._json_out", side_effect=lambda d: captured.append(d)):
                await cmd_virtual_goods(ns)
        assert captured[0]["ok"] is False

    @pytest.mark.asyncio
    async def test_replay_not_available(self):
        ns = _ns(action="replay", event_id="ev1")
        captured = []
        with patch("src.modules.virtual_goods.service.VirtualGoodsService") as MockVGS:
            mock_svc = MagicMock(spec=[])
            MockVGS.return_value = mock_svc
            with patch("src.cli._json_out", side_effect=lambda d: captured.append(d)):
                await cmd_virtual_goods(ns)
        assert captured[0]["ok"] is False
        assert "service_method_not_available" in captured[0]["error"]

    @pytest.mark.asyncio
    async def test_manual_list_not_available(self):
        ns = _ns(action="manual", manual_action="list")
        captured = []
        with patch("src.modules.virtual_goods.service.VirtualGoodsService") as MockVGS:
            mock_svc = MagicMock(spec=[])
            MockVGS.return_value = mock_svc
            with patch("src.cli._json_out", side_effect=lambda d: captured.append(d)):
                await cmd_virtual_goods(ns)
        assert captured[0]["ok"] is False

    @pytest.mark.asyncio
    async def test_manual_set_missing_order_id(self):
        ns = _ns(action="manual", manual_action="set", order_id=None)
        captured = []
        with patch("src.modules.virtual_goods.service.VirtualGoodsService") as MockVGS:
            MockVGS.return_value = MagicMock()
            with patch("src.cli._json_out", side_effect=lambda d: captured.append(d)):
                await cmd_virtual_goods(ns)
        assert captured[0]["ok"] is False
        assert "Specify --order-id" in captured[0]["error"]

    @pytest.mark.asyncio
    async def test_manual_set_not_available(self):
        ns = _ns(action="manual", manual_action="set", order_id="o1")
        captured = []
        with patch("src.modules.virtual_goods.service.VirtualGoodsService") as MockVGS:
            mock_svc = MagicMock(spec=[])
            MockVGS.return_value = mock_svc
            with patch("src.cli._json_out", side_effect=lambda d: captured.append(d)):
                await cmd_virtual_goods(ns)
        assert captured[0]["ok"] is False

    @pytest.mark.asyncio
    async def test_manual_unknown_action(self):
        ns = _ns(action="manual", manual_action="bad")
        captured = []
        with patch("src.modules.virtual_goods.service.VirtualGoodsService") as MockVGS:
            MockVGS.return_value = MagicMock()
            with patch("src.cli._json_out", side_effect=lambda d: captured.append(d)):
                await cmd_virtual_goods(ns)
        assert captured[0]["ok"] is False
        assert "Unknown --manual-action" in captured[0]["error"]

    @pytest.mark.asyncio
    async def test_inspect_not_available(self):
        ns = _ns(action="inspect", event_id="ev1", order_id="o1")
        captured = []
        with patch("src.modules.virtual_goods.service.VirtualGoodsService") as MockVGS:
            mock_svc = MagicMock(spec=[])
            MockVGS.return_value = mock_svc
            with patch("src.cli._json_out", side_effect=lambda d: captured.append(d)):
                await cmd_virtual_goods(ns)
        assert captured[0]["ok"] is False

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        ns = _ns(action="nonsense")
        captured = []
        with patch("src.modules.virtual_goods.service.VirtualGoodsService") as MockVGS:
            MockVGS.return_value = MagicMock()
            with patch("src.cli._json_out", side_effect=lambda d: captured.append(d)):
                await cmd_virtual_goods(ns)
        assert captured[0]["ok"] is False
        assert "Unknown virtual-goods action" in captured[0]["error"]


class TestCookieHealth:
    @pytest.mark.asyncio
    async def test_cookie_health_action(self):
        ns = argparse.Namespace(
            action="cookie-health",
            target="all",
            tail_lines=80,
            stop_timeout=6.0,
        )
        captured = []
        mock_checker = MagicMock()
        mock_checker.check_sync.return_value = {"healthy": True}
        with patch("src.core.cookie_health.CookieHealthChecker", return_value=mock_checker), \
             patch("src.cli._json_out", side_effect=lambda d: captured.append(d)), \
             patch.dict("os.environ", {"XIANYU_COOKIE_1": "test_cookie"}):
            await cmd_module(ns)
        assert captured[0]["healthy"] is True
