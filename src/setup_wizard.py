"""一键部署向导。"""

from __future__ import annotations

import getpass
import shutil
import subprocess
from pathlib import Path

from dotenv import dotenv_values


def _prompt(text: str, default: str | None = None, required: bool = False, secret: bool = False) -> str:
    while True:
        hint = ""
        if default:
            hint = " [已设置]" if secret else f" [{default}]"
        raw = getpass.getpass(f"{text}{hint}: ") if secret else input(f"{text}{hint}: ")
        value = raw.strip()
        if not value and default is not None:
            value = default
        if required and not value:
            print("该项为必填，请重新输入。")
            continue
        return value


def _choose_provider() -> tuple[str, str]:
    print("\n请选择 AI 服务商:")
    print("1) Anthropic（推荐）")
    print("2) OpenAI")
    print("3) DeepSeek")

    while True:
        choice = input("输入编号 [1/2/3]: ").strip()
        if choice in {"1", "2", "3"}:
            break
        print("请输入 1 / 2 / 3")

    mapping = {
        "1": ("ANTHROPIC_API_KEY", "sk-ant-..."),
        "2": ("OPENAI_API_KEY", "sk-..."),
        "3": ("DEEPSEEK_API_KEY", "sk-..."),
    }
    return mapping[choice]


def _read_existing_env(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}
    values = dotenv_values(env_path)
    return {k: str(v) for k, v in values.items() if v is not None}


def _build_env_content(values: dict[str, str], provider_key: str) -> str:
    lines = [
        "# 由 setup_wizard 自动生成",
        "",
        "# === AI Provider (at least one required) ===",
        f"ANTHROPIC_API_KEY={values.get('ANTHROPIC_API_KEY', '')}",
        f"OPENAI_API_KEY={values.get('OPENAI_API_KEY', '')}",
        f"DEEPSEEK_API_KEY={values.get('DEEPSEEK_API_KEY', '')}",
        "",
        "# === OpenClaw Gateway ===",
        f"OPENCLAW_GATEWAY_TOKEN={values.get('OPENCLAW_GATEWAY_TOKEN', '')}",
        f"OPENCLAW_WEB_PORT={values.get('OPENCLAW_WEB_PORT', '8080')}",
        f"AUTH_PASSWORD={values.get('AUTH_PASSWORD', '')}",
        f"AUTH_USERNAME={values.get('AUTH_USERNAME', 'admin')}",
        "",
        "# === Xianyu Cookie ===",
        f"XIANYU_COOKIE_1={values.get('XIANYU_COOKIE_1', '')}",
        f"XIANYU_COOKIE_2={values.get('XIANYU_COOKIE_2', '')}",
        "",
        "# === Cookie Encryption (optional) ===",
        f"ENCRYPTION_KEY={values.get('ENCRYPTION_KEY', '')}",
        "",
        "# === AI for content generation (used by Python services) ===",
        f"DEEPSEEK_BASE_URL={values.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')}",
        f"AI_MODEL={values.get('AI_MODEL', 'deepseek-chat')}",
        f"AI_TEMPERATURE={values.get('AI_TEMPERATURE', '0.7')}",
        "",
        "# === Database ===",
        f"DATABASE_URL={values.get('DATABASE_URL', 'sqlite:///data/agent.db')}",
        "",
        f"# 当前启用 AI Key: {provider_key}",
    ]
    return "\n".join(lines) + "\n"


def _ensure_docker_ready() -> bool:
    if shutil.which("docker") is None:
        print("未检测到 docker，请先安装 Docker Desktop。")
        return False

    cmd = ["docker", "compose", "version"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("检测到 docker 但 docker compose 不可用，请确认版本。")
        return False

    return True


def run_setup() -> int:
    root = Path.cwd()
    env_path = root / ".env"

    print("=" * 56)
    print("闲鱼 OpenClaw 一键部署向导")
    print("=" * 56)

    existing = _read_existing_env(env_path)

    provider_key, provider_hint = _choose_provider()
    api_key = _prompt(
        f"请输入 {provider_key}",
        default=existing.get(provider_key, provider_hint),
        required=True,
        secret=True,
    )

    token = _prompt("设置 OPENCLAW_GATEWAY_TOKEN", default=existing.get("OPENCLAW_GATEWAY_TOKEN"), required=True)
    password = _prompt(
        "设置 AUTH_PASSWORD（后台登录密码）",
        default=existing.get("AUTH_PASSWORD"),
        required=True,
        secret=True,
    )
    username = _prompt("设置 AUTH_USERNAME", default=existing.get("AUTH_USERNAME", "admin"), required=True)
    web_port = _prompt("设置 OPENCLAW_WEB_PORT", default=existing.get("OPENCLAW_WEB_PORT", "8080"), required=True)

    cookie_1 = _prompt("粘贴 XIANYU_COOKIE_1", default=existing.get("XIANYU_COOKIE_1"), required=True)
    cookie_2 = _prompt("粘贴 XIANYU_COOKIE_2（可留空）", default=existing.get("XIANYU_COOKIE_2", ""), required=False)

    merged = dict(existing)
    merged.update(
        {
            "ANTHROPIC_API_KEY": "",
            "OPENAI_API_KEY": "",
            "DEEPSEEK_API_KEY": "",
            provider_key: api_key,
            "OPENCLAW_GATEWAY_TOKEN": token,
            "AUTH_PASSWORD": password,
            "AUTH_USERNAME": username,
            "OPENCLAW_WEB_PORT": web_port,
            "XIANYU_COOKIE_1": cookie_1,
            "XIANYU_COOKIE_2": cookie_2,
        }
    )

    content = _build_env_content(merged, provider_key)
    env_path.write_text(content, encoding="utf-8")

    print(f"\n已写入配置: {env_path}")

    start_now = _prompt("是否立即启动容器？[Y/n]", default="Y")
    if start_now.lower() in {"", "y", "yes"}:
        if not _ensure_docker_ready():
            return 1
        print("\n正在执行: docker compose up -d")
        result = subprocess.run(["docker", "compose", "up", "-d"])
        if result.returncode != 0:
            print("容器启动失败，请执行 `docker compose logs -f` 查看日志。")
            return result.returncode

        print(f"\n启动成功。请打开: http://localhost:{web_port}")
        print("后台可视化可执行: python -m src.dashboard_server --port 8091")
    else:
        print("\n你可以稍后手动执行: docker compose up -d")

    return 0


def main() -> None:
    raise SystemExit(run_setup())


if __name__ == "__main__":
    main()
