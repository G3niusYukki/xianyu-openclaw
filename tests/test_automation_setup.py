"""自动化推进配置测试。"""

from pathlib import Path

from src.modules.messages.setup import AutomationSetupService


def test_automation_setup_apply_and_status(temp_dir) -> None:
    config_path = temp_dir / "config.yaml"
    config_path.write_text(
        "messages:\n  enabled: false\n",
        encoding="utf-8",
    )

    service = AutomationSetupService(config_path=str(config_path))
    result = service.apply(
        poll_interval_seconds=3.0,
        scan_limit=30,
        claim_limit=12,
        reply_target_seconds=2.5,
        feishu_enabled=True,
        feishu_webhook="https://open.feishu.cn/open-apis/bot/v2/hook/test",
        notify_on_start=True,
        heartbeat_minutes=10,
    )

    assert result["success"] is True
    assert Path(result["config_path"]).exists()
    assert result["backup_path"]

    status = service.status()
    assert status["messages_enabled"] is True
    assert status["fast_reply_enabled"] is True
    assert status["reply_target_seconds"] == 2.5
    assert status["workflow"]["poll_interval_seconds"] == 3.0
    assert status["workflow"]["scan_limit"] == 30
    assert status["workflow"]["claim_limit"] == 12
    assert status["feishu"]["enabled"] is True
    assert status["feishu"]["webhook_configured"] is True
    assert service.get_feishu_webhook().endswith("/test")


def test_automation_setup_can_keep_feishu_disabled(temp_dir) -> None:
    config_path = temp_dir / "config.yaml"
    config_path.write_text("{}", encoding="utf-8")

    service = AutomationSetupService(config_path=str(config_path))
    service.apply(
        feishu_enabled=False,
        feishu_webhook="",
    )

    status = service.status()
    assert status["messages_enabled"] is True
    assert status["feishu"]["enabled"] is False
    assert status["feishu"]["webhook_configured"] is False

