"""一键部署向导。"""

from __future__ import annotations

import getpass
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


@dataclass(frozen=True)
class ContentProvider:
    id: str
    title: str
    env_key: str
    hint: str
    base_url: str
    model: str


CONTENT_PROVIDERS = [
    ContentProvider(
        "deepseek",
        "DeepSeek",
        "DEEPSEEK_API_KEY",
        "sk-...",
        "https://api.deepseek.com/v1",
        "deepseek-chat",
    ),
    ContentProvider(
        "aliyun_bailian",
        "阿里云百炼（DashScope）",
        "DASHSCOPE_API_KEY",
        "sk-...",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "qwen-plus-latest",
    ),
    ContentProvider(
        "volcengine_ark",
        "火山引擎方舟（Ark）",
        "ARK_API_KEY",
        "sk-...",
        "https://ark.cn-beijing.volces.com/api/v3",
        "doubao-1.5-pro-32k-250115",
    ),
    ContentProvider(
        "minimax",
        "MiniMax",
        "MINIMAX_API_KEY",
        "sk-...",
        "https://api.minimaxi.com/v1",
        "MiniMax-Text-01",
    ),
    ContentProvider(
        "zhipu",
        "智谱（BigModel）",
        "ZHIPU_API_KEY",
        "zhipu-...",
        "https://open.bigmodel.cn/api/paas/v4",
        "glm-4-plus",
    ),
    ContentProvider("openai", "OpenAI", "OPENAI_API_KEY", "sk-...", "https://api.openai.com/v1", "gpt-4o-mini"),
    ContentProvider(
        "custom",
        "自定义（Custom Provider）",
        "AI_API_KEY",
        "自定义API Key",
        "https://api.example.com/v1",
        "custom-model",
    ),
]

ALL_SUPPORTED_KEYS = [
    "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY",
    "ARK_API_KEY",
    "ZHIPU_API_KEY",
    "MINIMAX_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "AI_PROVIDER",
    "AI_API_KEY",
    "AI_BASE_URL",
    "AI_MODEL",
    "AI_TEMPERATURE",
    "XGJ_APP_KEY",
    "XGJ_APP_SECRET",
    "XGJ_BASE_URL",
    "XIANYU_COOKIE_1",
    "XIANYU_COOKIE_2",
    "ENCRYPTION_KEY",
    "DATABASE_URL",
]


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


def _choose_content_provider() -> ContentProvider:
    print("\n请选择业务文案 AI 服务（用于标题/描述生成）:")
    for idx, provider in enumerate(CONTENT_PROVIDERS, start=1):
        print(f"{idx}) {provider.title}")

    valid = {str(i) for i in range(1, len(CONTENT_PROVIDERS) + 1)}
    while True:
        choice = input(f"输入编号 [1-{len(CONTENT_PROVIDERS)}]: ").strip()
        if choice in valid:
            return CONTENT_PROVIDERS[int(choice) - 1]
        print("输入无效，请重试。")


def _read_existing_env(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}
    values = dotenv_values(env_path)
    return {k: str(v) for k, v in values.items() if v is not None}


def _build_env_content(values: dict[str, str], content_key: str) -> str:
    lines = [
        "# 由 setup_wizard 自动生成",
        "",
        "# === Business AI Provider (used by Python services) ===",
        f"DEEPSEEK_API_KEY={values.get('DEEPSEEK_API_KEY', '')}",
        f"DASHSCOPE_API_KEY={values.get('DASHSCOPE_API_KEY', '')}",
        f"ARK_API_KEY={values.get('ARK_API_KEY', '')}",
        f"ZHIPU_API_KEY={values.get('ZHIPU_API_KEY', '')}",
        f"MINIMAX_API_KEY={values.get('MINIMAX_API_KEY', '')}",
        f"OPENAI_API_KEY={values.get('OPENAI_API_KEY', '')}",
        f"OPENAI_BASE_URL={values.get('OPENAI_BASE_URL', '')}",
        f"AI_PROVIDER={values.get('AI_PROVIDER', 'deepseek')}",
        f"AI_API_KEY={values.get('AI_API_KEY', '')}",
        f"AI_BASE_URL={values.get('AI_BASE_URL', '')}",
        f"AI_MODEL={values.get('AI_MODEL', 'deepseek-chat')}",
        f"AI_TEMPERATURE={values.get('AI_TEMPERATURE', '0.7')}",
        "",
        "# === 闲管家 ===",
        f"XGJ_APP_KEY={values.get('XGJ_APP_KEY', '')}",
        f"XGJ_APP_SECRET={values.get('XGJ_APP_SECRET', '')}",
        f"XGJ_BASE_URL={values.get('XGJ_BASE_URL', '')}",
        "",
        "# === Xianyu Cookie ===",
        f"XIANYU_COOKIE_1={values.get('XIANYU_COOKIE_1', '')}",
        f"XIANYU_COOKIE_2={values.get('XIANYU_COOKIE_2', '')}",
        "",
        "# === Cookie Encryption (optional) ===",
        f"ENCRYPTION_KEY={values.get('ENCRYPTION_KEY', '')}",
        "",
        "# === Database ===",
        f"DATABASE_URL={values.get('DATABASE_URL', 'sqlite:///data/agent.db')}",
        "",
        f"# 当前启用 Business AI Key: {content_key}",
    ]
    return "\n".join(lines) + "\n"


def _ensure_docker_ready() -> bool:
    if shutil.which("docker") is None:
        print("未检测到 docker，请先安装 Docker Desktop。")
        return False

    result = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True)
    if result.returncode != 0:
        print("检测到 docker 但 docker compose 不可用，请确认 Docker Desktop 已启动。")
        return False

    return True


def _run_post_start_checks() -> None:
    print("\n正在检查容器状态...")
    subprocess.run(["docker", "compose", "ps"], check=False)
    logs = subprocess.run(["docker", "compose", "logs", "--tail=80"], capture_output=True, text=True, check=False)
    text = logs.stdout + logs.stderr

    if "At least one AI provider API key env var is required" in text:
        print("\n[检查结果] 缺少可识别 API Key。请确认 AI Provider Key 已填写。")
        return

    print("\n启动完成。")


def run_setup() -> int:
    root = Path.cwd()
    env_path = root / ".env"

    print("=" * 56)
    print("闲鱼管家 一键部署向导")
    print("=" * 56)

    existing = _read_existing_env(env_path)

    # a. 选择 AI 服务商
    content_provider = _choose_content_provider()

    content_api_key = _prompt(
        f"请输入 {content_provider.env_key}",
        default=existing.get(content_provider.env_key, content_provider.hint),
        required=True,
    )

    # 处理 Content 自定义 provider 的额外配置
    content_base_url = content_provider.base_url
    content_model = content_provider.model
    if content_provider.id == "custom":
        content_base_url = _prompt(
            "请输入自定义 Base URL",
            default=existing.get("AI_BASE_URL", ""),
            required=True,
        )
        content_model = _prompt(
            "请输入自定义模型名称",
            default=existing.get("AI_MODEL", ""),
            required=True,
        )

    # b. 填入闲管家 AppKey/AppSecret
    xgj_app_key = _prompt(
        "请输入闲管家 XGJ_APP_KEY",
        default=existing.get("XGJ_APP_KEY", ""),
        required=True,
    )
    xgj_app_secret = _prompt(
        "请输入闲管家 XGJ_APP_SECRET",
        default=existing.get("XGJ_APP_SECRET", ""),
        required=True,
        secret=True,
    )
    xgj_base_url = _prompt(
        "请输入闲管家 XGJ_BASE_URL（可留空使用默认）",
        default=existing.get("XGJ_BASE_URL", ""),
        required=False,
    )

    # c. 粘贴闲鱼 Cookie
    cookie_1 = _prompt("粘贴 XIANYU_COOKIE_1", default=existing.get("XIANYU_COOKIE_1"), required=True)
    cookie_2 = _prompt("粘贴 XIANYU_COOKIE_2（可留空）", default=existing.get("XIANYU_COOKIE_2", ""), required=False)

    # d. 写入 .env
    merged = dict(existing)
    for key in ALL_SUPPORTED_KEYS:
        merged.setdefault(key, "")

    merged.update(
        {
            content_provider.env_key: content_api_key,
            "AI_PROVIDER": content_provider.id,
            "AI_API_KEY": content_api_key,
            "AI_BASE_URL": content_base_url,
            "AI_MODEL": content_model,
            "AI_TEMPERATURE": existing.get("AI_TEMPERATURE", "0.7"),
            "XGJ_APP_KEY": xgj_app_key,
            "XGJ_APP_SECRET": xgj_app_secret,
            "XGJ_BASE_URL": xgj_base_url,
            "XIANYU_COOKIE_1": cookie_1,
            "XIANYU_COOKIE_2": cookie_2,
        }
    )

    content = _build_env_content(merged, content_provider.env_key)
    env_path.write_text(content, encoding="utf-8")

    print(f"\n已写入配置: {env_path}")

    # e. 可选启动
    print("\n启动方式:")
    print("  1) 本地: ./start.sh")
    print("  2) Docker: docker compose up -d")
    print("  3) 稍后手动启动")
    start_choice = _prompt("请选择 [1/2/3]", default="1")
    if start_choice == "1":
        start_sh = root / "start.sh"
        if start_sh.exists():
            print("\n正在执行: ./start.sh")
            result = subprocess.run(["./start.sh"], cwd=root)
            if result.returncode != 0:
                print("启动失败，请检查日志。")
                return result.returncode
        else:
            print(f"未找到 {start_sh}，请手动执行启动命令。")
    elif start_choice == "2":
        if not _ensure_docker_ready():
            return 1
        print("\n正在执行: docker compose up -d")
        result = subprocess.run(["docker", "compose", "up", "-d"], cwd=root)
        if result.returncode != 0:
            print("容器启动失败，请执行 `docker compose logs -f` 查看日志。")
            return result.returncode
        _run_post_start_checks()
    else:
        print("\n你可以稍后手动执行: ./start.sh 或 docker compose up -d")

    return 0


def main() -> None:
    raise SystemExit(run_setup())


if __name__ == "__main__":
    main()
