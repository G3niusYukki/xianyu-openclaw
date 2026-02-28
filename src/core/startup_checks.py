"""
启动健康检查
Startup Health Checks

在应用启动时验证所有关键依赖和配置是否就绪
"""

import importlib.util
import os
import platform
import shutil
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.core.logger import get_logger

logger = get_logger()


class StartupCheckResult:
    def __init__(self, name: str, passed: bool, message: str, critical: bool = True, fix_hint: str = ""):
        self.name = name
        self.passed = passed
        self.message = message
        self.critical = critical
        self.fix_hint = fix_hint


def resolve_runtime_mode() -> str:
    env_runtime = str(os.getenv("OPENCLAW_RUNTIME", "")).strip().lower()
    if env_runtime in {"auto", "lite", "pro"}:
        return env_runtime

    try:
        from src.core.config import get_config

        cfg_runtime = str(get_config().get("app.runtime", "auto")).strip().lower()
        if cfg_runtime in {"auto", "lite", "pro"}:
            return cfg_runtime
    except Exception:
        pass

    return "auto"


def check_runtime_mode() -> StartupCheckResult:
    runtime = resolve_runtime_mode()
    return StartupCheckResult("浏览器运行时", True, f"当前运行时: {runtime}", critical=False)


def check_python_version() -> StartupCheckResult:
    v = sys.version_info
    ok = v.major == 3 and v.minor >= 10
    fix_hint = ""
    if not ok:
        fix_hint = "请安装 Python 3.10 或更高版本: https://www.python.org/downloads/"
    return StartupCheckResult(
        "Python版本",
        ok,
        f"Python {v.major}.{v.minor}.{v.micro}" + ("" if ok else " (需要 3.10+)"),
        fix_hint=fix_hint,
    )


def check_docker_installed() -> StartupCheckResult:
    if shutil.which("docker") is None:
        return StartupCheckResult(
            "Docker",
            False,
            "未安装",
            critical=False,
            fix_hint="请安装 Docker Desktop: https://docs.docker.com/get-docker/",
        )
    return StartupCheckResult("Docker", True, "已安装", critical=False)


def check_docker_running() -> StartupCheckResult:
    if shutil.which("docker") is None:
        return StartupCheckResult(
            "Docker运行状态",
            False,
            "Docker未安装",
            critical=False,
            fix_hint="请先安装 Docker Desktop",
        )
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return StartupCheckResult("Docker运行状态", True, "运行中", critical=False)
        return StartupCheckResult(
            "Docker运行状态",
            False,
            "未运行",
            critical=False,
            fix_hint="请启动 Docker Desktop",
        )
    except subprocess.TimeoutExpired:
        return StartupCheckResult(
            "Docker运行状态",
            False,
            "检查超时",
            critical=False,
            fix_hint="Docker 可能未响应，请重启 Docker Desktop",
        )
    except Exception as e:
        return StartupCheckResult(
            "Docker运行状态",
            False,
            f"检查失败: {e}",
            critical=False,
            fix_hint="请确认 Docker Desktop 正常运行",
        )


def check_port_available(port: int = 8080) -> StartupCheckResult:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        sock.close()
        return StartupCheckResult(
            f"端口 {port}",
            True,
            "可用",
            critical=False,
        )
    except OSError:
        return StartupCheckResult(
            f"端口 {port}",
            False,
            "已被占用",
            critical=False,
            fix_hint=f"请关闭占用端口 {port} 的程序，或在 .env 中设置 OPENCLAW_WEB_PORT 为其他端口",
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
        return StartupCheckResult(
            "OpenClaw Gateway",
            False,
            f"响应异常 (HTTP {resp.status_code})",
            fix_hint="请检查容器状态: docker compose ps",
        )
    except httpx.ConnectError:
        return StartupCheckResult(
            "OpenClaw Gateway",
            False,
            "无法连接。请确认 OpenClaw Gateway 正在运行 (docker compose ps)",
            fix_hint="请执行: docker compose up -d",
        )
    except Exception as e:
        return StartupCheckResult(
            "OpenClaw Gateway",
            False,
            f"检查失败: {e}",
            fix_hint="请确认 Docker 容器正常运行: docker compose ps",
        )


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
        return StartupCheckResult(
            "数据库",
            False,
            f"不可用: {e}",
            fix_hint="请确认 data/ 目录有写入权限",
        )


def check_data_directories() -> StartupCheckResult:
    dirs = ["data", "logs", "data/processed_images"]
    missing = []
    for d in dirs:
        p = Path(d)
        p.mkdir(parents=True, exist_ok=True)
        if not p.is_dir() or not os.access(str(p), os.W_OK):
            missing.append(d)

    if missing:
        return StartupCheckResult(
            "数据目录",
            False,
            f"无法写入: {', '.join(missing)}",
            fix_hint="请确认当前用户对项目目录有写入权限",
        )
    return StartupCheckResult("数据目录", True, "所有目录可写")


def check_ai_config() -> StartupCheckResult:
    gateway_keys = [
        os.getenv("ANTHROPIC_API_KEY"),
        os.getenv("OPENAI_API_KEY"),
        os.getenv("MOONSHOT_API_KEY"),
        os.getenv("MINIMAX_API_KEY"),
        os.getenv("ZAI_API_KEY"),
    ]
    valid_gateway = any(k and len(k) > 10 and not k.startswith("sk-...") for k in gateway_keys)

    content_keys = [
        os.getenv("DEEPSEEK_API_KEY"),
        os.getenv("DASHSCOPE_API_KEY"),
        os.getenv("ARK_API_KEY"),
        os.getenv("ZHIPU_API_KEY"),
        os.getenv("AI_API_KEY"),
    ]
    valid_content = any(k and len(k) > 10 and not k.startswith("sk-...") for k in content_keys)

    if valid_gateway and valid_content:
        return StartupCheckResult("AI服务", True, "Gateway 与 Content API Key 已配置", critical=False)
    if valid_gateway:
        return StartupCheckResult(
            "AI服务",
            True,
            "Gateway API Key 已配置（Content 未配置，将使用模板降级）",
            critical=False,
        )
    return StartupCheckResult(
        "AI服务",
        False,
        "API Key 未配置。AI内容生成将使用模板降级",
        critical=False,
        fix_hint="请在 .env 中配置至少一个 AI API Key（如 ANTHROPIC_API_KEY 或 OPENAI_API_KEY）",
    )


def check_cookies_configured() -> StartupCheckResult:
    cookie_1 = os.getenv("XIANYU_COOKIE_1", "")
    if cookie_1 and cookie_1 != "your_cookie_here" and len(cookie_1) > 20:
        return StartupCheckResult("闲鱼Cookie", True, "至少1个Cookie已配置")
    return StartupCheckResult(
        "闲鱼Cookie",
        False,
        "未配置有效Cookie。浏览器操作将无法执行。请在 .env 中设置 XIANYU_COOKIE_1",
        fix_hint="请获取闲鱼 Cookie 并设置到 .env 文件的 XIANYU_COOKIE_1 变量",
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
            fix_hint="请在 .env 中配置 XIANYU_COOKIE_1",
        )

    has_session_fields = any(key in cookie_1 for key in ["_tb_token_", "cookie2", "sgcookie", "unb"])
    if not has_session_fields:
        return StartupCheckResult(
            "Cookie有效性",
            False,
            "Cookie 格式异常，缺少关键字段 (_tb_token_, cookie2 等)。请重新获取",
            critical=False,
            fix_hint="请重新获取闲鱼 Cookie，确保包含完整的会话信息",
        )

    return StartupCheckResult("Cookie有效性", True, "Cookie格式正常", critical=False)


def check_env_file() -> StartupCheckResult:
    env_path = Path(".env")
    if not env_path.exists():
        example_path = Path(".env.example")
        if example_path.exists():
            return StartupCheckResult(
                ".env 配置文件",
                False,
                "不存在（.env.example 存在）",
                fix_hint="请复制 .env.example 为 .env 并填写配置: cp .env.example .env",
            )
        return StartupCheckResult(
            ".env 配置文件",
            False,
            "不存在",
            fix_hint="请运行配置向导: python3 -m src.setup_wizard",
        )
    return StartupCheckResult(".env 配置文件", True, "存在")


def check_dependencies() -> StartupCheckResult:
    required = ["dotenv", "httpx", "yaml", "loguru"]
    missing = []
    for pkg in required:
        if importlib.util.find_spec(pkg) is None:
            missing.append(pkg)

    if missing:
        return StartupCheckResult(
            "Python 依赖",
            False,
            f"缺少依赖: {', '.join(missing)}",
            critical=False,
            fix_hint="请安装依赖: pip install -r requirements.txt",
        )
    return StartupCheckResult("Python 依赖", True, "核心依赖已安装", critical=False)
def check_lite_browser_dependency() -> StartupCheckResult:
    try:
        import playwright  # noqa: F401

        return StartupCheckResult("Lite 浏览器驱动", True, "Playwright 已安装", critical=True)
    except Exception:
        return StartupCheckResult(
            "Lite 浏览器驱动",
            False,
            "未安装 Playwright。请执行: pip install playwright && playwright install chromium",
            critical=True,
        )


def run_all_checks(skip_browser: bool = False, include_docker: bool = True) -> list[StartupCheckResult]:
    """运行所有启动检查"""
    runtime = resolve_runtime_mode()
    results = [
        check_runtime_mode(),
        check_python_version(),
        check_env_file(),
        check_dependencies(),
        check_data_directories(),
        check_database_writable(),
        check_ai_config(),
        check_cookies_configured(),
        check_cookie_expiration(),
    ]

    if include_docker:
        results.extend(
            [
                check_docker_installed(),
                check_docker_running(),
            ]
        )

    if skip_browser:
        port = int(os.getenv("OPENCLAW_WEB_PORT", "8080"))
        results.append(check_port_available(port))
        return results

    if runtime == "pro":
        results.append(check_gateway_reachable())
        port = int(os.getenv("OPENCLAW_WEB_PORT", "8080"))
        results.append(check_port_available(port))
        return results

    if runtime == "lite":
        results.append(check_lite_browser_dependency())
        port = int(os.getenv("OPENCLAW_WEB_PORT", "8080"))
        results.append(check_port_available(port))
        return results

    # auto 模式：优先探测 gateway，失败则检查 lite 依赖。
    gateway = check_gateway_reachable()
    if gateway.passed:
        results.append(gateway)
    else:
        results.append(
            StartupCheckResult(
                "OpenClaw Gateway",
                False,
                f"{gateway.message}（auto 模式将尝试 lite 回退）",
                critical=False,
            )
        )
        results.append(check_lite_browser_dependency())

    port = int(os.getenv("OPENCLAW_WEB_PORT", "8080"))
    results.append(check_port_available(port))

    return results


def print_startup_report(results: list[StartupCheckResult]) -> bool:
    """打印启动检查报告，返回是否所有关键检查通过"""
    logger.info("=" * 56)
    logger.info("闲鱼自动化工具 - 启动检查")
    logger.info("=" * 56)

    all_critical_passed = True
    fix_hints: list[str] = []

    for r in results:
        icon = "✅" if r.passed else ("⚠️" if not r.critical else "❌")
        logger.info(f"  {icon} {r.name}: {r.message}")
        if not r.passed and r.critical:
            all_critical_passed = False
        if not r.passed and r.fix_hint:
            fix_hints.append(f"  • {r.name}: {r.fix_hint}")

    logger.info("=" * 56)
    if all_critical_passed:
        logger.success("所有关键检查通过，系统可以启动")
    else:
        logger.error("存在关键检查未通过，部分功能可能不可用")

    if fix_hints:
        logger.info("")
        logger.info("修复建议:")
        for hint in fix_hints:
            logger.info(hint)

    logger.info("=" * 56)

    return all_critical_passed


def generate_doctor_report() -> dict[str, Any]:
    """生成诊断报告（供 CLI 使用）"""
    results = run_all_checks(skip_browser=False, include_docker=True)
    report = {
        "platform": platform.platform(),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "timestamp": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
        "checks": [],
        "all_passed": True,
        "critical_failures": [],
        "fix_hints": [],
    }

    for r in results:
        report["checks"].append(
            {
                "name": r.name,
                "passed": r.passed,
                "message": r.message,
                "critical": r.critical,
                "fix_hint": r.fix_hint,
            }
        )
        if not r.passed:
            if r.critical:
                report["all_passed"] = False
                report["critical_failures"].append(r.name)
            if r.fix_hint:
                report["fix_hints"].append({"check": r.name, "hint": r.fix_hint})

    return report
