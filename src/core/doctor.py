"""运行环境与配置诊断。"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Any

from src.core.config import get_config
from src.core.startup_checks import run_all_checks
from src.modules.quote import CostTableRepository

_SUGGESTIONS = {
    "Python版本": "请安装 Python 3.10+，并使用 `python3 -m venv .venv` 创建虚拟环境。",
    "OpenClaw Gateway": "请先执行 `docker compose up -d`，再重试 doctor。",
    "数据库": "请确认数据库目录可写，并检查 `config/config.yaml` 中 database.path 配置。",
    "闲鱼Cookie": "请在 `.env` 中设置有效的 `XIANYU_COOKIE_1`。",
    "Cookie有效性": "请重新抓取并更新闲鱼 Cookie，避免使用过期会话。",
    "AI服务": "可配置 `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY`，未配置将退化到模板模式。",
    ".env 文件": "请复制 `.env.example` 为 `.env`，并补齐关键配置。",
    "配置文件": "请确保 `config/config.yaml` 存在，或从 `config/config.example.yaml` 复制生成。",
    "消息首响SLA": "建议开启 `messages.fast_reply_enabled=true` 且 `reply_target_seconds<=3`。",
    "自动报价成本源": "请提供成本表（data/quote_costs）或配置 `quote.cost_api_url`。",
}


def _check_port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    if port <= 0:
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            return sock.connect_ex((host, port)) == 0
    except OSError:
        return False


def _append_check(
    checks: list[dict[str, Any]],
    *,
    name: str,
    passed: bool,
    message: str,
    critical: bool,
    suggestion: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    resolved_suggestion = ""
    if not passed:
        resolved_suggestion = suggestion or _SUGGESTIONS.get(name, "")

    checks.append(
        {
            "name": name,
            "passed": bool(passed),
            "critical": bool(critical),
            "message": message,
            "suggestion": resolved_suggestion,
            "meta": meta or {},
        }
    )


def _extra_checks(skip_quote: bool = False) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    env_exists = Path(".env").exists()
    _append_check(
        checks,
        name=".env 文件",
        passed=env_exists,
        message="已检测到 .env" if env_exists else "未检测到 .env",
        critical=False,
    )

    cfg_candidates = [Path("config/config.yaml"), Path("config/config.example.yaml")]
    cfg_path = next((path for path in cfg_candidates if path.exists()), None)
    _append_check(
        checks,
        name="配置文件",
        passed=cfg_path is not None,
        message=f"已使用配置: {cfg_path}" if cfg_path else "未找到 config/config.yaml 或 config/config.example.yaml",
        critical=True,
    )

    web_port = int(os.getenv("OPENCLAW_WEB_PORT", "8080"))
    web_listening = _check_port_open(web_port)
    _append_check(
        checks,
        name="Web UI 端口",
        passed=web_listening,
        message=f"检测到监听 127.0.0.1:{web_port}" if web_listening else f"未检测到监听 127.0.0.1:{web_port}",
        critical=False,
        suggestion="如需启动 Web UI，请执行 `docker compose up -d`。",
        meta={"port": web_port},
    )

    dashboard_port = int(os.getenv("DASHBOARD_PORT", "8091"))
    dashboard_listening = _check_port_open(dashboard_port)
    _append_check(
        checks,
        name="Dashboard 端口",
        passed=dashboard_listening,
        message=(
            f"检测到监听 127.0.0.1:{dashboard_port}"
            if dashboard_listening
            else f"未检测到监听 127.0.0.1:{dashboard_port}"
        ),
        critical=False,
        suggestion="如需可视化后台，请执行 `python3 -m src.dashboard_server --port 8091`。",
        meta={"port": dashboard_port},
    )

    try:
        config = get_config()
        messages_cfg = config.get_section("messages", {})
        fast_reply_enabled = bool(messages_cfg.get("fast_reply_enabled", False))
        reply_target_seconds = float(messages_cfg.get("reply_target_seconds", 3.0))
        sla_ok = fast_reply_enabled and reply_target_seconds <= 3.0
        _append_check(
            checks,
            name="消息首响SLA",
            passed=sla_ok,
            message=(
                f"已启用快速首响，目标 {reply_target_seconds:.2f}s"
                if sla_ok
                else f"未满足首响目标：fast_reply_enabled={fast_reply_enabled}, target={reply_target_seconds:.2f}s"
            ),
            critical=False,
            meta={
                "fast_reply_enabled": fast_reply_enabled,
                "reply_target_seconds": reply_target_seconds,
            },
        )
    except Exception as exc:
        _append_check(
            checks,
            name="消息首响SLA",
            passed=False,
            message=f"检查失败: {exc}",
            critical=False,
        )

    if skip_quote:
        return checks

    try:
        config = get_config()
        quote_cfg = config.get_section("quote", {})
        mode = str(quote_cfg.get("mode", "rule_only")).strip().lower()
        repo = CostTableRepository(
            table_dir=quote_cfg.get("cost_table_dir", "data/quote_costs"),
            include_patterns=quote_cfg.get("cost_table_patterns", ["*.xlsx", "*.csv"]),
        )
        stats = repo.get_stats(max_files=30)
        total_records = int(stats.get("total_records", 0))
        api_ready = bool(str(quote_cfg.get("cost_api_url", "")).strip())
        needs_cost_source = mode in {"cost_table_plus_markup", "api_cost_plus_markup"}
        source_ready = total_records > 0 or api_ready
        passed = (not needs_cost_source) or source_ready
        message = (
            f"mode={mode}, records={total_records}, api_ready={api_ready}"
            if passed
            else f"mode={mode} 需要成本源，但 records={total_records}, api_ready={api_ready}"
        )
        _append_check(
            checks,
            name="自动报价成本源",
            passed=passed,
            message=message,
            critical=False,
            meta={
                "mode": mode,
                "total_records": total_records,
                "api_ready": api_ready,
                "files": stats.get("files", []),
            },
        )
    except Exception as exc:
        _append_check(
            checks,
            name="自动报价成本源",
            passed=False,
            message=f"检查失败: {exc}",
            critical=False,
        )

    return checks


def run_doctor(skip_gateway: bool = False, skip_quote: bool = False) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    startup_checks = run_all_checks(skip_browser=bool(skip_gateway))
    for item in startup_checks:
        _append_check(
            checks,
            name=item.name,
            passed=item.passed,
            message=item.message,
            critical=item.critical,
        )

    checks.extend(_extra_checks(skip_quote=skip_quote))

    total = len(checks)
    passed_count = sum(1 for c in checks if c["passed"])
    failed = [c for c in checks if not c["passed"]]
    critical_failed = [c for c in failed if c["critical"]]
    warning_failed = [c for c in failed if not c["critical"]]

    next_steps: list[str] = []
    seen: set[str] = set()
    for item in failed:
        suggestion = str(item.get("suggestion", "")).strip()
        if suggestion and suggestion not in seen:
            seen.add(suggestion)
            next_steps.append(suggestion)

    return {
        "ready": len(critical_failed) == 0,
        "summary": {
            "total": total,
            "passed": passed_count,
            "failed": len(failed),
            "critical_failed": len(critical_failed),
            "warning_failed": len(warning_failed),
        },
        "checks": checks,
        "next_steps": next_steps,
    }
