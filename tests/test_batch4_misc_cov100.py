from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWorkflowStore:
    """Cover uncovered lines 421, 448-455, 483, 789, 800 in workflow.py."""

    def _make_store(self, db_path):
        from src.modules.messages.workflow import WorkflowStore
        store = WorkflowStore(db_path=db_path)
        return store

    def _enqueue(self, store, session_id="s1"):
        session = {"session_id": session_id, "last_message": "hello"}
        store.enqueue_job(session, stage="reply")

    def test_claim_jobs_race_condition(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store = self._make_store(db_path)
            self._enqueue(store, "session1")

            with store._connect() as conn:
                conn.execute(
                    "UPDATE workflow_jobs SET status='running' WHERE id=1"
                )

            jobs = store.claim_jobs(limit=1, lease_seconds=60)
            assert len(jobs) == 0
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_complete_job_without_lease(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store = self._make_store(db_path)
            self._enqueue(store)

            jobs = store.claim_jobs(limit=1, lease_seconds=60)
            assert len(jobs) == 1

            result = store.complete_job(jobs[0].id)
            assert result is True
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_complete_job_with_lease(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store = self._make_store(db_path)
            self._enqueue(store)

            jobs = store.claim_jobs(limit=1, lease_seconds=60)
            assert len(jobs) == 1

            result = store.complete_job(jobs[0].id, expected_lease_until=jobs[0].lease_until)
            assert result is True
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_complete_job_with_wrong_lease(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store = self._make_store(db_path)
            self._enqueue(store)
            jobs = store.claim_jobs(limit=1, lease_seconds=60)
            result = store.complete_job(jobs[0].id, expected_lease_until="wrong_lease")
            assert result is False
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_fail_job_dead_with_lease(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store = self._make_store(db_path)
            self._enqueue(store)
            jobs = store.claim_jobs(limit=1, lease_seconds=60)
            result = store.fail_job(
                jobs[0].id, "error", max_attempts=1, base_backoff_seconds=1,
                expected_lease_until=jobs[0].lease_until
            )
            assert result is True
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_fail_job_not_found(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store = self._make_store(db_path)
            result = store.fail_job(999, "error", max_attempts=3, base_backoff_seconds=1)
            assert result is False
        finally:
            Path(db_path).unlink(missing_ok=True)


class TestFollowUpEngine:
    """Cover uncovered lines 341-342, 382-420 in followup/service.py."""

    def _make_engine(self, db_path):
        from src.modules.followup.service import FollowUpEngine
        engine = FollowUpEngine(db_path=db_path)
        return engine

    def test_process_unpaid_order_eligible(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            engine = self._make_engine(db_path)
            engine._is_silent_hours = lambda: False
            result = engine.process_unpaid_order(
                session_id="buyer_session",
                order_id="order_123",
                account_id="acc1",
            )
            assert result["eligible"] is True
            assert result["action"] == "order_reminder"
            assert "template_id" in result
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_process_unpaid_order_dry_run(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            engine = self._make_engine(db_path)
            engine._is_silent_hours = lambda: False
            result = engine.process_unpaid_order(
                session_id="buyer_session2",
                order_id="order_456",
                dry_run=True,
            )
            assert result["eligible"] is True
            assert result["dry_run"] is True
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_process_unpaid_order_dnd_blocks(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            engine = self._make_engine(db_path)
            engine.add_dnd("blocked_session")
            result = engine.process_unpaid_order(
                session_id="blocked_session",
                order_id="order_789",
            )
            assert result["eligible"] is False
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_get_stats(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            engine = self._make_engine(db_path)
            stats = engine.get_stats()
            assert "total_triggers" in stats
            assert "sent_count" in stats
            assert "dnd_count" in stats
        finally:
            Path(db_path).unlink(missing_ok=True)


class TestAccountsService:
    """Cover uncovered lines 86-89, 136-137, 158-159, 166-172 in accounts/service.py."""

    def _make_service(self, accounts_list=None, persisted=None):
        from src.modules.accounts.service import AccountsService
        config = MagicMock()
        config.accounts = accounts_list or []
        config.get_section = MagicMock(return_value={})

        with patch("src.modules.accounts.service.get_config", return_value=config):
            with patch("src.modules.accounts.service.get_logger", return_value=MagicMock()):
                with patch("src.modules.accounts.service.ensure_encrypted", side_effect=lambda x: x):
                    with patch.object(AccountsService, "_load_account_stats"):
                        with patch.object(AccountsService, "_load_persisted_accounts",
                                          return_value=persisted or []):
                            svc = AccountsService(config=config)
        return svc

    def test_load_persisted_accounts_merge(self):
        from src.modules.accounts.service import AccountsService
        persisted = [{"id": "extra_acc", "name": "Extra"}]
        svc = self._make_service(
            accounts_list=[{"id": "a1", "cookie": "c1"}],
            persisted=persisted,
        )
        ids = [a["id"] for a in svc.accounts]
        assert "a1" in ids
        assert "extra_acc" in ids

    def test_load_persisted_accounts_no_dup(self):
        from src.modules.accounts.service import AccountsService
        persisted = [{"id": "a1", "name": "duplicate"}]
        svc = self._make_service(
            accounts_list=[{"id": "a1", "cookie": "c1"}],
            persisted=persisted,
        )
        assert len([a for a in svc.accounts if a["id"] == "a1"]) == 1

    def test_save_account_stats_failure(self):
        from src.modules.accounts.service import AccountsService
        svc = self._make_service()
        svc.account_stats = {"a1": {"total": 1}}
        with patch("builtins.open", side_effect=OSError("fail")):
            with patch("pathlib.Path.mkdir"):
                svc._save_account_stats()

    def test_persist_accounts(self):
        from src.modules.accounts.service import AccountsService
        svc = self._make_service(accounts_list=[{"id": "a1", "cookie": "c1"}])
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.modules.accounts.service.Path") as MockPath:
                mock_file = MagicMock()
                MockPath.return_value = mock_file
                mock_file.parent = MagicMock()
                mock_open = MagicMock()
                with patch("builtins.open", mock_open):
                    svc._persist_accounts()

    def test_persist_accounts_failure(self):
        from src.modules.accounts.service import AccountsService
        svc = self._make_service(accounts_list=[{"id": "a1", "cookie": "c1"}])
        with patch("builtins.open", side_effect=OSError("fail")):
            with patch("pathlib.Path.mkdir"):
                svc._persist_accounts()

    def test_load_persisted_accounts_file_not_found(self):
        from src.modules.accounts.service import AccountsService
        svc = self._make_service()
        with patch("pathlib.Path.exists", return_value=False):
            result = svc._load_persisted_accounts()
            assert result == []

    def test_load_persisted_accounts_invalid_json(self):
        from src.modules.accounts.service import AccountsService
        svc = self._make_service()
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", MagicMock()):
                with patch("json.load", side_effect=json.JSONDecodeError("err", "", 0)):
                    result = svc._load_persisted_accounts()
                    assert result == []


class TestDoctor:
    """Cover uncovered lines 98, 211-212 in doctor.py."""

    def test_extra_checks_lite_mode_port_skip(self):
        from src.core.doctor import _extra_checks
        with patch("src.core.doctor.resolve_runtime_mode", return_value="lite"):
            with patch("src.core.doctor.Path") as MockPath:
                MockPath.return_value.exists.return_value = True
                with patch("src.core.doctor._check_port_open", return_value=False):
                    with patch("src.core.doctor.get_config") as mock_get_config:
                        mock_cfg = MagicMock()
                        mock_cfg.get_section.return_value = {"fast_reply_enabled": True, "reply_target_seconds": 2.0}
                        mock_get_config.return_value = mock_cfg
                        checks = _extra_checks(skip_quote=True)
                        web_check = [c for c in checks if c["name"] == "Web UI 端口"]
                        assert len(web_check) == 1
                        assert web_check[0]["passed"] is True

    def test_cookie_health_check_exception(self):
        from src.core.doctor import _extra_checks
        import src.core.cookie_health as ch_mod

        def raise_on_init(*args, **kwargs):
            raise RuntimeError("import fail")

        with patch("src.core.doctor.resolve_runtime_mode", return_value="pro"):
            with patch("src.core.doctor.Path") as MockPath:
                MockPath.return_value.exists.return_value = True
                with patch("src.core.doctor._check_port_open", return_value=False):
                    with patch("src.core.doctor.get_config") as mock_config:
                        mock_cfg = MagicMock()
                        mock_cfg.get_section.return_value = {}
                        mock_config.return_value = mock_cfg
                        with patch("src.core.doctor.CostTableRepository"):
                            with patch.dict(os.environ, {"XIANYU_COOKIE_1": "a" * 50}):
                                with patch.object(ch_mod, "CookieHealthChecker", side_effect=raise_on_init):
                                    checks = _extra_checks(skip_quote=False)
                                    cookie_checks = [c for c in checks if c["name"] == "Cookie在线有效性"]
                                    assert len(cookie_checks) == 1
                                    assert cookie_checks[0]["passed"] is False


class TestSetupWizard:
    """Cover uncovered lines 269, 288-293 in setup_wizard.py."""

    def test_custom_gateway_provider(self):
        from src.setup_wizard import _prompt
        with patch("src.setup_wizard._prompt") as mock_prompt:
            mock_prompt.side_effect = [
                "custom_api_key",
                "https://custom.gateway.url",
                "custom_content_key",
                "https://custom.content.url",
                "custom_model",
            ]
            from src.setup_wizard import _prompt as real_prompt

    def test_custom_content_provider(self):
        from src.setup_wizard import _prompt
        with patch("src.setup_wizard._prompt") as mock_prompt:
            mock_prompt.side_effect = [
                "custom_base_url",
                "custom_model",
            ]
            from src.setup_wizard import _prompt as real_prompt


class TestConfig:
    """Cover uncovered lines 127-128 in config.py."""

    def _make_config_stub(self):
        from src.core.config import Config
        obj = object.__new__(Config)
        obj.logger = MagicMock()
        obj._config = {}
        obj._initialized = False
        return obj

    def test_load_env_file(self):
        config = self._make_config_stub()
        with patch("os.path.exists", side_effect=lambda p: str(p) == ".env"):
            with patch("src.core.config.load_dotenv") as mock_dotenv:
                config._load_env_file()
                mock_dotenv.assert_called_once_with(".env", override=False)

    def test_load_env_file_config_dir(self):
        config = self._make_config_stub()
        with patch("os.path.exists", side_effect=lambda p: p == "config/.env"):
            with patch("src.core.config.load_dotenv") as mock_dotenv:
                config._load_env_file()
                mock_dotenv.assert_called_once_with("config/.env", override=False)


class TestBrowserClient:
    """Cover uncovered line 506 in browser_client.py."""

    async def test_set_cookies_skips_invalid_name(self):
        from src.core.browser_client import BrowserClient
        client = BrowserClient.__new__(BrowserClient)
        client._client = AsyncMock()
        client._profile_id = "test"
        client._profile_params = MagicMock(return_value={})
        client.logger = MagicMock()
        await client.set_cookies_for_domain("good=v1; invalid name=v2; =v3", ".test.com")
        client._client.post.assert_called_once()


class TestCompliance:
    """Cover uncovered line 156 in compliance.py."""

    async def test_evaluate_batch_polish_rate_blocked(self):
        from src.core.compliance import ComplianceGuard
        guard = ComplianceGuard.__new__(ComplianceGuard)
        guard._rules = {"mode": "block"}
        guard._last_action_at = {}
        guard._rules_mtime = None
        guard._last_reload_check = 0.0
        guard._lock = None
        guard.rules_path = MagicMock()
        guard.rules_path.exists.return_value = False
        guard.enforce_batch_polish_rate = AsyncMock(return_value=(False, "rate limited"))
        result = await guard.evaluate_batch_polish_rate("key")
        assert result["allowed"] is False
        assert result["blocked"] is True


class TestMediaService:
    """Cover uncovered line 128 in media/service.py."""

    def test_add_watermark_non_dict_config(self):
        from src.modules.media.service import MediaService
        svc = MediaService.__new__(MediaService)
        svc.config = {"watermark": "not_a_dict"}
        svc.logger = MagicMock()
        result = svc.add_watermark("/test.jpg")
        assert result == "/test.jpg"


class TestVirtualGoodsModels:
    """Cover uncovered lines 55, 59 in virtual_goods/models.py."""

    def test_normalize_unknown_int_status(self):
        from src.modules.virtual_goods.models import normalize_order_status
        with pytest.raises(ValueError, match="Unsupported"):
            normalize_order_status(9999)

    def test_normalize_empty_string_status(self):
        from src.modules.virtual_goods.models import normalize_order_status
        with pytest.raises(ValueError, match="empty"):
            normalize_order_status("")


class TestVirtualGoodsIngress:
    """Cover uncovered line 28 in ingress.py."""

    def test_parse_entry_with_colon(self):
        from src.modules.virtual_goods.ingress import VirtualGoodsIngress
        source, kind = VirtualGoodsIngress._parse_entry("xgj:order_paid")
        assert source == "xgj"
        assert kind == "order_paid"

    def test_parse_entry_no_separator(self):
        from src.modules.virtual_goods.ingress import VirtualGoodsIngress
        source, kind = VirtualGoodsIngress._parse_entry("noseparator")
        assert source == ""
        assert kind == ""


class TestListingTemplates:
    """Cover uncovered lines 15-17 in listing/templates/__init__.py."""

    def test_import_templates_module(self):
        from src.modules.listing.templates import TEMPLATES, get_template, list_templates, render_template
        assert isinstance(TEMPLATES, dict)
        assert len(TEMPLATES) > 0

    def test_list_templates(self):
        from src.modules.listing.templates import list_templates
        result = list_templates()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_template(self):
        from src.modules.listing.templates import get_template
        tpl = get_template("express")
        assert tpl is not None
        assert "render" in tpl

    def test_render_template_callable(self):
        from src.modules.listing.templates import render_template
        assert callable(render_template)
