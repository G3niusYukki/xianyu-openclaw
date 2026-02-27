"""合规策略中心测试。"""

from pathlib import Path

from src.modules.compliance.center import ComplianceCenter


def _write_policy(path: Path) -> None:
    path.write_text(
        """
version: "v_test"
reload:
  auto_reload: true
  check_interval_seconds: 0
global:
  whitelist: ["官方渠道"]
  blacklist: ["私下交易"]
  stop_words: ["微信"]
  rate_limit:
    account:
      window_seconds: 60
      max_messages: 2
    session:
      window_seconds: 60
      max_messages: 2
accounts:
  acc1:
    blacklist: ["拉群"]
sessions:
  s1:
    stop_words: ["二维码"]
""",
        encoding="utf-8",
    )


def test_compliance_center_hierarchical_override_and_block(temp_dir) -> None:
    policy = temp_dir / "policies.yaml"
    db = temp_dir / "compliance.db"
    _write_policy(policy)
    center = ComplianceCenter(policy_path=str(policy), db_path=str(db))

    d1 = center.evaluate_before_send("加我微信聊", account_id="acc1", session_id="s0")
    d2 = center.evaluate_before_send("可以拉群沟通", account_id="acc1", session_id="s0")
    d3 = center.evaluate_before_send("这是二维码", account_id="acc1", session_id="s1")

    assert d1.blocked is True
    assert d1.reason == "high_risk_stop_word"
    assert d2.blocked is True
    assert d2.policy_scope == "account:acc1"
    assert d3.blocked is True
    assert d3.policy_scope == "session:s1"


def test_compliance_center_rate_limit_and_replay(temp_dir) -> None:
    policy = temp_dir / "policies.yaml"
    db = temp_dir / "compliance.db"
    _write_policy(policy)
    center = ComplianceCenter(policy_path=str(policy), db_path=str(db))

    ok1 = center.evaluate_before_send("第一条", account_id="acc2", session_id="s2")
    ok2 = center.evaluate_before_send("第二条", account_id="acc2", session_id="s2")
    blocked = center.evaluate_before_send("第三条", account_id="acc2", session_id="s2")

    assert ok1.allowed is True
    assert ok2.allowed is True
    assert blocked.blocked is True
    assert "rate_limit" in blocked.reason

    replay = center.replay(account_id="acc2", limit=10)
    blocked_only = center.replay(account_id="acc2", blocked_only=True, limit=10)

    assert len(replay) == 3
    assert len(blocked_only) == 1
    assert blocked_only[0]["decision"].startswith("session_rate_limit") or blocked_only[0]["decision"].startswith(
        "account_rate_limit"
    )
