from __future__ import annotations

import argparse
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import cli


@pytest.mark.asyncio
async def test_cmd_analytics_all_actions(monkeypatch):
    out = []

    class S:
        async def get_dashboard_stats(self):
            return {"dashboard": True}

        async def get_daily_report(self):
            return {"daily": True}

        async def get_trend_data(self, metric, days):
            return {"metric": metric, "days": days}

        async def export_data(self, data_type, format):
            return f"/tmp/{data_type}.{format}"

    monkeypatch.setattr("src.modules.analytics.service.AnalyticsService", lambda: S())
    monkeypatch.setattr("src.cli._json_out", lambda d: out.append(d))

    await cli.cmd_analytics(argparse.Namespace(action="dashboard"))
    await cli.cmd_analytics(argparse.Namespace(action="daily"))
    await cli.cmd_analytics(argparse.Namespace(action="trend", metric="views", days=7))
    await cli.cmd_analytics(argparse.Namespace(action="export", type="products", format="csv"))
    await cli.cmd_analytics(argparse.Namespace(action="???"))

    assert out[0]["dashboard"] is True
    assert out[1]["daily"] is True
    assert out[2]["days"] == 7
    assert out[3]["filepath"].endswith("products.csv")
    assert "Unknown analytics action" in out[4]["error"]


@pytest.mark.asyncio
async def test_cmd_accounts_actions(monkeypatch):
    out = []

    class S:
        def get_accounts(self):
            return [{"id": "a1"}]

        def get_account_health(self, account_id):
            return {"id": account_id, "healthy": True}

        def validate_cookie(self, account_id):
            return account_id == "ok"

        def refresh_cookie(self, account_id, cookie):
            return {"id": account_id, "cookie": cookie}

    monkeypatch.setattr("src.modules.accounts.service.AccountsService", lambda: S())
    monkeypatch.setattr("src.cli._json_out", lambda d: out.append(d))

    await cli.cmd_accounts(argparse.Namespace(action="list", id=None, cookie=None))
    await cli.cmd_accounts(argparse.Namespace(action="health", id=None, cookie=None))
    await cli.cmd_accounts(argparse.Namespace(action="health", id="a1", cookie=None))
    await cli.cmd_accounts(argparse.Namespace(action="validate", id="ok", cookie=None))
    await cli.cmd_accounts(argparse.Namespace(action="refresh-cookie", id="a1", cookie="c=1"))
    await cli.cmd_accounts(argparse.Namespace(action="refresh-cookie", id="a1", cookie=None))
    await cli.cmd_accounts(argparse.Namespace(action="x", id=None, cookie=None))

    assert out[0] == [{"id": "a1"}]
    assert "Specify --id" in out[1]["error"]
    assert out[2]["healthy"] is True
    assert out[3]["valid"] is True
    assert out[4]["cookie"] == "c=1"
    assert "--id and --cookie" in out[5]["error"]
    assert "Unknown accounts action" in out[6]["error"]


@pytest.mark.asyncio
async def test_cmd_orders_actions(monkeypatch):
    out = []

    class S:
        def __init__(self, db_path):
            self.db_path = db_path

        def upsert_order(self, **kwargs):
            return {"op": "upsert", **kwargs}

        def deliver(self, **kwargs):
            return {"op": "deliver", **kwargs}

        def create_after_sales_case(self, **kwargs):
            return {"op": "after", **kwargs}

        def set_manual_takeover(self, order_id, flag):
            return not (order_id == "bad" and flag is False)

        def trace_order(self, order_id):
            return {"order_id": order_id}

    monkeypatch.setattr("src.modules.orders.service.OrderFulfillmentService", S)
    monkeypatch.setattr("src.cli._json_out", lambda d: out.append(d))

    await cli.cmd_orders(argparse.Namespace(action="upsert", order_id=None, status="paid", session_id=None, quote_fee=None, item_type=None, db_path=None))
    await cli.cmd_orders(argparse.Namespace(action="upsert", order_id="o1", status="paid", session_id="s1", quote_fee=5.0, item_type="virtual", db_path=None))
    await cli.cmd_orders(argparse.Namespace(action="deliver", order_id="o1", dry_run=True, db_path=None))
    await cli.cmd_orders(argparse.Namespace(action="after-sales", order_id="o1", issue_type="delay", db_path=None))
    await cli.cmd_orders(argparse.Namespace(action="takeover", order_id="o1", db_path=None))
    await cli.cmd_orders(argparse.Namespace(action="resume", order_id="bad", db_path=None))
    await cli.cmd_orders(argparse.Namespace(action="trace", order_id="o1", db_path=None))
    await cli.cmd_orders(argparse.Namespace(action="???", order_id="o1", db_path=None))

    assert "--order-id and --status" in out[0]["error"]
    assert out[1]["op"] == "upsert"
    assert out[2]["op"] == "deliver"
    assert out[3]["op"] == "after"
    assert out[4]["manual_takeover"] is True
    assert out[5]["success"] is False
    assert out[6]["order_id"] == "o1"
    assert "Unknown orders action" in out[7]["error"]


@pytest.mark.asyncio
async def test_cmd_compliance_doctor_quote_growth_automation(monkeypatch):
    out = []

    class Decision:
        def to_dict(self):
            return {"allow": True}

    class Center:
        def __init__(self, **_kwargs):
            pass

        def reload(self):
            return None

        def evaluate_before_send(self, *_a, **_k):
            return Decision()

        def replay(self, **_kwargs):
            return [{"id": 1}]

    class QuoteRepo:
        def __init__(self, **_kwargs):
            pass

        def get_stats(self, max_files=30):
            return {"files": max_files}

        def find_candidates(self, **_kwargs):
            return [SimpleNamespace(courier="YTO", origin="A", destination="B", first_cost=1, extra_cost=2)]

    class QuoteSetup:
        def __init__(self, **_kwargs):
            pass

        def apply(self, **kwargs):
            return {"ok": True, "patterns": kwargs["cost_table_patterns"]}

    class Growth:
        def __init__(self, **_kwargs):
            pass

        def set_strategy_version(self, **kwargs):
            return kwargs

        def rollback_to_baseline(self, strategy_type):
            return strategy_type == "price"

        def assign_variant(self, **kwargs):
            return kwargs

        def record_event(self, **kwargs):
            return kwargs

        def funnel_stats(self, **kwargs):
            return kwargs

        def compare_variants(self, **kwargs):
            return kwargs

    class SetupSvc:
        def __init__(self, **_kwargs):
            pass

        def status(self):
            return {"status": "ok"}

        def apply(self, **kwargs):
            return kwargs

        def get_feishu_webhook(self):
            return "https://hook"

    class Notifier:
        def __init__(self, webhook_url):
            self.webhook_url = webhook_url

        async def send_text(self, _text):
            return True

    monkeypatch.setattr("src.modules.compliance.center.ComplianceCenter", Center)
    monkeypatch.setattr("src.core.doctor.run_doctor", lambda **_k: {"ready": False, "summary": {"warning_failed": 1}})
    monkeypatch.setattr("src.core.config.get_config", lambda: SimpleNamespace(get_section=lambda *_a, **_k: {"mode": "rule_only"}))
    monkeypatch.setattr("src.modules.quote.CostTableRepository", QuoteRepo)
    monkeypatch.setattr("src.modules.quote.QuoteSetupService", QuoteSetup)
    monkeypatch.setattr("src.modules.growth.service.GrowthService", Growth)
    monkeypatch.setattr("src.modules.messages.setup.AutomationSetupService", SetupSvc)
    monkeypatch.setattr("src.modules.messages.notifications.FeishuNotifier", Notifier)
    monkeypatch.setattr("src.cli._json_out", lambda d: out.append(d))

    await cli.cmd_compliance(argparse.Namespace(action="reload", policy_path="p", db_path="d"))
    await cli.cmd_compliance(argparse.Namespace(action="check", content="x", actor="a", account_id="id", session_id="s", audit_action="send", policy_path="p", db_path="d"))
    await cli.cmd_compliance(argparse.Namespace(action="replay", account_id="id", session_id="s", blocked_only=True, limit=1, policy_path="p", db_path="d"))

    with pytest.raises(SystemExit):
        await cli.cmd_doctor(argparse.Namespace(skip_gateway=False, skip_quote=False, strict=True))

    await cli.cmd_quote(argparse.Namespace(action="health"))
    await cli.cmd_quote(argparse.Namespace(action="candidates", origin_city="杭州", destination_city="上海", courier=None, limit=1))
    await cli.cmd_quote(argparse.Namespace(action="setup", config_path="c", mode="m", origin_city="o", pricing_profile="p", cost_table_dir="d", cost_table_patterns="*.csv,*.xlsx", cost_api_url="", cost_api_key_env="KEY"))

    await cli.cmd_growth(argparse.Namespace(action="set-strategy", strategy_type="price", version="v1", active=True, baseline=False, db_path=None))
    await cli.cmd_growth(argparse.Namespace(action="rollback", strategy_type="price", db_path=None))
    await cli.cmd_growth(argparse.Namespace(action="assign", experiment_id="e", subject_id="u", variants="A,B", version="v", db_path=None))
    await cli.cmd_growth(argparse.Namespace(action="event", subject_id="u", stage="inquiry", experiment_id="e", variant="A", version="v", db_path=None))
    await cli.cmd_growth(argparse.Namespace(action="funnel", days=3, bucket="day", db_path=None))
    await cli.cmd_growth(argparse.Namespace(action="compare", experiment_id="e", from_stage="inquiry", to_stage="ordered", db_path=None))

    await cli.cmd_automation(argparse.Namespace(action="status", config_path="x"))
    await cli.cmd_automation(argparse.Namespace(action="setup", config_path="x", enable_feishu=False, feishu_webhook="", poll_interval=1, scan_limit=2, claim_limit=3, reply_target_seconds=4, notify_on_start=True, disable_notify_on_alert=False, disable_notify_recovery=True, heartbeat_minutes=5))
    await cli.cmd_automation(argparse.Namespace(action="test-feishu", config_path="x", feishu_webhook="", message="hi"))

    assert out[0]["success"] is True
    assert out[1]["allow"] is True
    assert out[2]["total"] == 1
    assert any(item.get("total") == 1 for item in out if isinstance(item, dict))
    assert any(item.get("ok") is True for item in out if isinstance(item, dict))
    assert any(item.get("strategy_type") == "price" for item in out if isinstance(item, dict))
    assert out[-1]["success"] is True


@pytest.mark.asyncio
async def test_cmd_messages_workflow_transition_force(monkeypatch):
    out = []

    class Store:
        def __init__(self, db_path=None):
            self.db_path = db_path

        def transition_state(self, **_k):
            return False

        def force_state(self, **_k):
            return True

        def get_session(self, sid):
            return {"sid": sid}

    monkeypatch.setattr("src.modules.messages.workflow.WorkflowStore", Store)
    monkeypatch.setattr("src.cli._resolve_workflow_state", lambda _s: SimpleNamespace(value="inquiry"))
    monkeypatch.setattr("src.cli._json_out", lambda d: out.append(d))

    await cli.cmd_messages(argparse.Namespace(action="workflow-transition", session_id="s1", stage="inquiry", workflow_db="db", force_state=True))
    assert out[-1]["forced"] is True
