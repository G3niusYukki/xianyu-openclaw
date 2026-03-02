# ISSUES FOUND:
# 1. [src/modules/messages/ws_live.py:859,889] asyncio.wait_for() 对 Event.wait 的 monkeypatch 若返回协程对象可能导致 "coroutine was never awaited" RuntimeWarning。
# 2. [src/cli.py:*] CLI 分发函数体量过大且高度耦合，导致覆盖率提升成本高、回归测试编写复杂。

from __future__ import annotations

import argparse
import asyncio
import base64
import json

import pytest

from src import cli
from src.core import browser_client as bc
from src.modules.messages import ws_live


class _Resp:
    def __init__(self, status_code=200, payload=None, text="", is_success=True):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.is_success = is_success
        self.content = b"img"

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_cmd_analytics_accounts_orders_compliance_ai_quote_growth(monkeypatch):
    out = []
    monkeypatch.setattr(cli, "_json_out", lambda data: out.append(data))

    class Analytics:
        async def get_dashboard_stats(self):
            return {"k": 1}

        async def get_daily_report(self):
            return {"day": 1}

        async def get_trend_data(self, metric, days):
            return {"metric": metric, "days": days}

        async def export_data(self, data_type, format):
            return f"/tmp/{data_type}.{format}"

    monkeypatch.setattr("src.modules.analytics.service.AnalyticsService", Analytics)
    await cli.cmd_analytics(argparse.Namespace(action="dashboard", metric=None, days=None, type=None, format=None))
    await cli.cmd_analytics(argparse.Namespace(action="daily", metric=None, days=None, type=None, format=None))
    await cli.cmd_analytics(argparse.Namespace(action="trend", metric="views", days=3, type=None, format=None))
    await cli.cmd_analytics(argparse.Namespace(action="export", metric=None, days=None, type="products", format="csv"))
    await cli.cmd_analytics(argparse.Namespace(action="x", metric=None, days=None, type=None, format=None))

    class Accounts:
        def get_accounts(self):
            return [{"id": "a1"}]

        def get_account_health(self, _id):
            return {"id": _id, "ok": True}

        def validate_cookie(self, _id):
            return True

        def refresh_cookie(self, _id, _cookie):
            return {"id": _id, "updated": True}

    monkeypatch.setattr("src.modules.accounts.service.AccountsService", Accounts)
    await cli.cmd_accounts(argparse.Namespace(action="list", id=None, cookie=None))
    await cli.cmd_accounts(argparse.Namespace(action="health", id=None, cookie=None))
    await cli.cmd_accounts(argparse.Namespace(action="health", id="a1", cookie=None))
    await cli.cmd_accounts(argparse.Namespace(action="validate", id=None, cookie=None))
    await cli.cmd_accounts(argparse.Namespace(action="validate", id="a1", cookie=None))
    await cli.cmd_accounts(argparse.Namespace(action="refresh-cookie", id=None, cookie=None))
    await cli.cmd_accounts(argparse.Namespace(action="refresh-cookie", id="a1", cookie="c=1"))
    await cli.cmd_accounts(argparse.Namespace(action="oops", id=None, cookie=None))

    class Orders:
        def __init__(self, db_path):
            self.db_path = db_path

        def upsert_order(self, **kwargs):
            return {"upsert": kwargs}

        def deliver(self, **kwargs):
            return {"deliver": kwargs}

        def create_after_sales_case(self, **kwargs):
            return {"after": kwargs}

        def set_manual_takeover(self, order_id, val):
            return order_id == "ok"

        def trace_order(self, order_id):
            return {"order_id": order_id}

    monkeypatch.setattr("src.modules.orders.service.OrderFulfillmentService", Orders)
    await cli.cmd_orders(argparse.Namespace(action="upsert", db_path=None, order_id=None, status=None, session_id=None, quote_fee=None, item_type=None, dry_run=False, issue_type=None))
    await cli.cmd_orders(argparse.Namespace(action="upsert", db_path=None, order_id="o1", status="paid", session_id="s1", quote_fee=12, item_type="v", dry_run=False, issue_type=None))
    await cli.cmd_orders(argparse.Namespace(action="deliver", db_path=None, order_id=None, status=None, session_id=None, quote_fee=None, item_type=None, dry_run=True, issue_type=None))
    await cli.cmd_orders(argparse.Namespace(action="deliver", db_path=None, order_id="o1", status=None, session_id=None, quote_fee=None, item_type=None, dry_run=True, issue_type=None))
    await cli.cmd_orders(argparse.Namespace(action="after-sales", db_path=None, order_id="o1", status=None, session_id=None, quote_fee=None, item_type=None, dry_run=False, issue_type="delay"))
    await cli.cmd_orders(argparse.Namespace(action="takeover", db_path=None, order_id="ok", status=None, session_id=None, quote_fee=None, item_type=None, dry_run=False, issue_type=None))
    await cli.cmd_orders(argparse.Namespace(action="resume", db_path=None, order_id="no", status=None, session_id=None, quote_fee=None, item_type=None, dry_run=False, issue_type=None))
    await cli.cmd_orders(argparse.Namespace(action="trace", db_path=None, order_id="o1", status=None, session_id=None, quote_fee=None, item_type=None, dry_run=False, issue_type=None))
    await cli.cmd_orders(argparse.Namespace(action="none", db_path=None, order_id=None, status=None, session_id=None, quote_fee=None, item_type=None, dry_run=False, issue_type=None))

    class Decision:
        def to_dict(self):
            return {"allow": True}

    class Compliance:
        def __init__(self, **_k):
            pass

        def reload(self):
            return None

        def evaluate_before_send(self, *_a, **_k):
            return Decision()

        def replay(self, **_k):
            return [{"id": 1}]

    monkeypatch.setattr("src.modules.compliance.center.ComplianceCenter", Compliance)
    await cli.cmd_compliance(argparse.Namespace(action="reload", policy_path="p", db_path="d", content=None, actor=None, account_id=None, session_id=None, audit_action=None, blocked_only=False, limit=3))
    await cli.cmd_compliance(argparse.Namespace(action="check", policy_path="p", db_path="d", content="x", actor="a", account_id="u", session_id="s", audit_action="message_send", blocked_only=False, limit=3))
    await cli.cmd_compliance(argparse.Namespace(action="replay", policy_path="p", db_path="d", content=None, actor=None, account_id=None, session_id=None, audit_action=None, blocked_only=True, limit=2))
    await cli.cmd_compliance(argparse.Namespace(action="what", policy_path="p", db_path="d", content=None, actor=None, account_id=None, session_id=None, audit_action=None, blocked_only=False, limit=2))

    class AI:
        def get_ai_cost_stats(self):
            return {"tokens": 1}

        def generate_title(self, **_k):
            return "t"

        def generate_description(self, **_k):
            return "d"

    monkeypatch.setattr("src.modules.content.service.ContentService", AI)
    await cli.cmd_ai(argparse.Namespace(action="cost-stats", product_name=None, category=None))
    await cli.cmd_ai(argparse.Namespace(action="simulate-publish", product_name="p", category="c"))
    await cli.cmd_ai(argparse.Namespace(action="bad", product_name=None, category=None))

    class Cfg:
        def get_section(self, *_a, **_k):
            return {"mode": "rule_only", "cost_table_dir": "d", "cost_table_patterns": ["*.csv"], "cost_api_url": ""}

    class Repo:
        def __init__(self, **_k):
            pass

        def get_stats(self, max_files):
            return {"files": max_files}

        def find_candidates(self, **_k):
            class R:
                courier = "c"
                origin = "o"
                destination = "d"
                first_cost = 1
                extra_cost = 2

            return [R()]

    class Setup:
        def __init__(self, config_path):
            self.path = config_path

        def apply(self, **kwargs):
            return {"ok": True, "kwargs": kwargs}

    monkeypatch.setattr("src.core.config.get_config", lambda: Cfg())
    monkeypatch.setattr("src.modules.quote.CostTableRepository", Repo)
    monkeypatch.setattr("src.modules.quote.QuoteSetupService", Setup)
    await cli.cmd_quote(argparse.Namespace(action="health", origin_city=None, destination_city=None, courier=None, limit=2, config_path=None, cost_table_patterns=None, mode=None, pricing_profile=None, cost_table_dir=None, cost_api_url=None, cost_api_key_env=None))
    await cli.cmd_quote(argparse.Namespace(action="candidates", origin_city=None, destination_city="上海", courier=None, limit=2, config_path=None, cost_table_patterns=None, mode=None, pricing_profile=None, cost_table_dir=None, cost_api_url=None, cost_api_key_env=None))
    await cli.cmd_quote(argparse.Namespace(action="candidates", origin_city="杭州", destination_city="上海", courier="圆通", limit=2, config_path=None, cost_table_patterns=None, mode=None, pricing_profile=None, cost_table_dir=None, cost_api_url=None, cost_api_key_env=None))
    await cli.cmd_quote(argparse.Namespace(action="setup", origin_city=None, destination_city=None, courier=None, limit=2, config_path="cfg", cost_table_patterns="*.xlsx,*.csv", mode="m", pricing_profile="p", cost_table_dir="dir", cost_api_url="u", cost_api_key_env="KEY"))
    await cli.cmd_quote(argparse.Namespace(action="x", origin_city=None, destination_city=None, courier=None, limit=2, config_path=None, cost_table_patterns=None, mode=None, pricing_profile=None, cost_table_dir=None, cost_api_url=None, cost_api_key_env=None))

    class Growth:
        def __init__(self, db_path):
            self.db_path = db_path

        def set_strategy_version(self, **kwargs):
            return kwargs

        def rollback_to_baseline(self, _s):
            return True

        def assign_variant(self, **kwargs):
            return kwargs

        def record_event(self, **kwargs):
            return kwargs

        def funnel_stats(self, **kwargs):
            return kwargs

        def strategy_status(self, strategy_type):
            return {"strategy_type": strategy_type}

        def strategy_history(self, strategy_type, limit):
            return [{"strategy_type": strategy_type, "limit": limit}]

        def list_experiments(self):
            return [{"id": "exp1"}]

    monkeypatch.setattr("src.modules.growth.service.GrowthService", Growth)
    await cli.cmd_growth(argparse.Namespace(action="set-strategy", db_path=None, strategy_type=None, version=None, active=False, baseline=False, experiment_id=None, subject_id=None, variants=None, stage=None, variant=None, days=7, bucket="day", limit=10))
    await cli.cmd_growth(argparse.Namespace(action="set-strategy", db_path=None, strategy_type="s", version="v1", active=True, baseline=True, experiment_id=None, subject_id=None, variants=None, stage=None, variant=None, days=7, bucket="day", limit=10))
    await cli.cmd_growth(argparse.Namespace(action="rollback", db_path=None, strategy_type=None, version=None, active=False, baseline=False, experiment_id=None, subject_id=None, variants=None, stage=None, variant=None, days=7, bucket="day", limit=10))
    await cli.cmd_growth(argparse.Namespace(action="rollback", db_path=None, strategy_type="s", version=None, active=False, baseline=False, experiment_id=None, subject_id=None, variants=None, stage=None, variant=None, days=7, bucket="day", limit=10))
    await cli.cmd_growth(argparse.Namespace(action="assign", db_path=None, strategy_type=None, version="v1", active=False, baseline=False, experiment_id=None, subject_id=None, variants="A,B", stage=None, variant=None, days=7, bucket="day", limit=10))
    await cli.cmd_growth(argparse.Namespace(action="assign", db_path=None, strategy_type=None, version="v1", active=False, baseline=False, experiment_id="e1", subject_id="u1", variants="A,B", stage=None, variant=None, days=7, bucket="day", limit=10))
    await cli.cmd_growth(argparse.Namespace(action="event", db_path=None, strategy_type=None, version="v1", active=False, baseline=False, experiment_id="e1", subject_id=None, variants="A,B", stage=None, variant="A", days=7, bucket="day", limit=10))
    await cli.cmd_growth(argparse.Namespace(action="event", db_path=None, strategy_type=None, version="v1", active=False, baseline=False, experiment_id="e1", subject_id="u1", variants="A,B", stage="lead", variant="A", days=7, bucket="day", limit=10))
    await cli.cmd_growth(argparse.Namespace(action="funnel", db_path=None, strategy_type=None, version=None, active=False, baseline=False, experiment_id=None, subject_id=None, variants=None, stage=None, variant=None, days=5, bucket="week", limit=10))
    await cli.cmd_growth(argparse.Namespace(action="strategy-status", db_path=None, strategy_type="s", version=None, active=False, baseline=False, experiment_id=None, subject_id=None, variants=None, stage=None, variant=None, days=5, bucket="week", limit=10))
    await cli.cmd_growth(argparse.Namespace(action="strategy-history", db_path=None, strategy_type="s", version=None, active=False, baseline=False, experiment_id=None, subject_id=None, variants=None, stage=None, variant=None, days=5, bucket="week", limit=10))
    await cli.cmd_growth(argparse.Namespace(action="experiments", db_path=None, strategy_type=None, version=None, active=False, baseline=False, experiment_id=None, subject_id=None, variants=None, stage=None, variant=None, days=5, bucket="week", limit=10))

    assert len(out) > 20


@pytest.mark.asyncio
async def test_browser_client_more_branches():
    c = bc.BrowserClient()
    c._client = type("C", (), {})()

    async def bad_get(*_a, **_k):
        return _Resp(status_code=500)

    async def ok_get(*_a, **_k):
        return _Resp(status_code=200)

    c._client.get = bad_get
    assert await c.get_cookies() == []
    c._client.get = ok_get
    assert await c.get_cookies() == {}

    async def bad_post(*_a, **_k):
        raise RuntimeError("x")

    async def ok_post(*_a, **_k):
        return _Resp(200)

    c._client.post = ok_post
    assert await c.add_cookie("p", {"name": "a"}) is True
    assert await c.delete_cookies("p") is True
    c._client.post = bad_post
    assert await c.add_cookie("p", {"name": "a"}) is False
    assert await c.delete_cookies("p") is False

    called = {}

    async def cap_post(*_a, **kwargs):
        called["json"] = kwargs.get("json")
        return _Resp(200)

    c._client.post = cap_post
    await c.set_cookies_for_domain("invalid line")
    await c.set_cookies_for_domain("a=1; b=2")
    assert len(called["json"]["cookies"]) == 2


@pytest.mark.asyncio
async def test_ws_live_more_branches(monkeypatch):
    class W:
        async def connect(self, *_a, **_k):
            raise RuntimeError("stub")

    monkeypatch.setattr(ws_live, "websockets", W())

    assert ws_live.parse_cookie_header(" a=1; b=2 ;broken ") == {"a": "1", "b": "2"}
    assert ws_live.decode_sync_payload("") is None

    raw = base64.b64encode(json.dumps({"ok": 1}).encode()).decode()
    assert ws_live.decode_sync_payload(raw) == {"ok": 1}

    t = ws_live.GoofishWsTransport(cookie_text="unb=1001; _m_h5_tk=t_x; cookie2=c")
    t._session_peer["c1"] = "u2"

    class WsObj:
        def __init__(self):
            self.sent = []

        async def send(self, data):
            self.sent.append(json.loads(data))

        async def recv(self):
            t._stop_event.set()
            return json.dumps({"code": 200, "headers": {"mid": "m1", "sid": "s1", "app-key": "k", "ua": "u", "dt": "j"}})

        async def close(self):
            return None

    async def fake_connect(*_a, **_k):
        return WsObj()

    monkeypatch.setattr(ws_live.websockets, "connect", fake_connect)

    async def _noop():
        return None

    monkeypatch.setattr(t, "_send_reg", _noop)

    await t._run()
    assert t._last_disconnect_reason == ""

    t._ws = WsObj()
    ok = await t.send_text("c1", "hello")
    assert ok is True

    # trigger _push_event filters
    await t._push_event({"chat_id": "", "sender_user_id": "", "text": ""})
    await t._push_event({"chat_id": "c1", "sender_user_id": t.my_user_id, "text": "x", "create_time": 1})
    await t._push_event({"chat_id": "c1", "sender_user_id": "u2", "text": "x", "create_time": 1})

    assert ws_live.extract_chat_event({"1": {"10": {"text": "t", "senderUserId": "u"}, "2": "c@goofish"}})
