"""
启动健康检查
Startup Health Checks

在应用启动时验证所有关键依赖和配置是否就绪
"""

import os
import sqlite3
import sys
from pathlib import Path

from src.core.logger import get_logger

logger = get_logger()


class StartupCheckResult:
    def __init__(self, name: str, passed: bool, message: str, critical: bool = True):
        self.name = name
        self.passed = passed
        self.message = message
        self.critical = critical


def check_python_version() -> StartupCheckResult:
    v = sys.version_info
    ok = v.major == 3 and v.minor >= 10
    return StartupCheckResult(
        "Python版本",
        ok,
        f"Python {v.major}.{v.minor}.{v.micro}" + ("" if ok else " (需要 3.10+)"),
    )


def check_gateway_reachable() -> StartupCheckResult:
    try:
        import httpx

        host = os.getenv("OPENCLAW_GATEWAY_HOST", "127.0.0.1")
        port = int(os.getenv("OPENCLAW_GATEWAY_PORT", "18789"))
        browser_port = port + 2
        url = f"http://{host}:{browser_port}/"
        resp = httpx.get(url, timeout=5)
        if resp.status_code == 200:
            return StartupCheckResult("OpenClaw Gateway", True, f"可连接 ({host}:{browser_port})")
        return StartupCheckResult("OpenClaw Gateway", False, f"响应异常 (HTTP {resp.status_code})")
    except httpx.ConnectError:
        return StartupCheckResult(
            "OpenClaw Gateway",
            False,
            "无法连接。请确认 OpenClaw Gateway 正在运行 (docker compose ps)",
        )
    except Exception as e:
        return StartupCheckResult("OpenClaw Gateway", False, f"检查失败: {e}")


def check_database_writable() -> StartupCheckResult:
    from src.core.config import get_config

    try:
        cfg = get_config()
        db_path = cfg.database.get("path", "data/agent.db")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, timeout=5)
        conn.execute("SELECT 1")
        conn.close()
        return StartupCheckResult("数据库", True, f"可读写 ({db_path})")
    except Exception as e:
        return StartupCheckResult("数据库", False, f"不可用: {e}")


def check_data_directories() -> StartupCheckResult:
    dirs = ["data", "logs", "data/processed_images"]
    missing = []
    for d in dirs:
        p = Path(d)
        p.mkdir(parents=True, exist_ok=True)
        if not p.is_dir() or not os.access(str(p), os.W_OK):
            missing.append(d)

    if missing:
        return StartupCheckResult("数据目录", False, f"无法写入: {', '.join(missing)}")
    return StartupCheckResult("数据目录", True, "所有目录可写")


def check_ai_config() -> StartupCheckResult:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if api_key and len(api_key) > 10 and not api_key.startswith("sk-..."):
        return StartupCheckResult("AI服务", True, "API Key 已配置", critical=False)
    return StartupCheckResult(
        "AI服务",
        False,
        "API Key 未配置。AI内容生成将使用模板降级",
        critical=False,
    )


def check_cookies_configured() -> StartupCheckResult:
    cookie_1 = os.getenv("XIANYU_COOKIE_1", "")
    if cookie_1 and cookie_1 != "your_cookie_here" and len(cookie_1) > 20:
        return StartupCheckResult("闲鱼Cookie", True, "至少1个Cookie已配置")
    return StartupCheckResult(
        "闲鱼Cookie",
        False,
        "未配置有效Cookie。浏览器操作将无法执行。请在 .env 中设置 XIANYU_COOKIE_1",
    )


def check_cookie_expiration() -> StartupCheckResult:
    """检查 Cookie 是否可能已过期（简单的格式和长度检查）"""
    cookie_1 = os.getenv("XIANYU_COOKIE_1", "")
    if not cookie_1 or cookie_1 == "your_cookie_here":
        return StartupCheckResult(
            "Cookie有效性",
            False,
            "未配置Cookie",
            critical=False,
        )

    has_session_fields = any(key in cookie_1 for key in ["_tb_token_", "cookie2", "sgcookie", "unb"])
    if not has_session_fields:
        return StartupCheckResult(
            "Cookie有效性",
            False,
            "Cookie 格式异常，缺少关键字段 (_tb_token_, cookie2 等)。请重新获取",
            critical=False,
        )

    return StartupCheckResult("Cookie有效性", True, "Cookie格式正常", critical=False)


def run_all_checks(skip_browser: bool = False) -> list[StartupCheckResult]:
    """运行所有启动检查"""
    results = [
        check_python_version(),
        check_data_directories(),
        check_database_writable(),
        check_ai_config(),
        check_cookies_configured(),
        check_cookie_expiration(),
    ]

    if not skip_browser:
        results.append(check_gateway_reachable())

    return results


def print_startup_report(results: list[StartupCheckResult]) -> bool:
    """打印启动检查报告，返回是否所有关键检查通过"""
    logger.info("=" * 50)
    logger.info("闲鱼自动化工具 - 启动检查")
    logger.info("=" * 50)

    all_critical_passed = True
    for r in results:
        icon = "✅" if r.passed else ("⚠️" if not r.critical else "❌")
        logger.info(f"  {icon} {r.name}: {r.message}")
        if not r.passed and r.critical:
            all_critical_passed = False

    logger.info("=" * 50)
    if all_critical_passed:
        logger.success("所有关键检查通过，系统可以启动")
    else:
        logger.error("存在关键检查未通过，部分功能可能不可用")
    logger.info("=" * 50)

    return all_critical_passed
