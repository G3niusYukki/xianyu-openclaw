from __future__ import annotations

import importlib.util
import secrets
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import customtkinter as ctk


def _load_setup_wizard():
    """Load setup_wizard module directly from file to avoid src/__init__.py import chain.

    src/__init__.py imports heavy modules (httpx, etc.) that are excluded from the
    PyInstaller bundle. Loading setup_wizard.py by filepath sidesteps the package
    __init__ entirely.
    """
    wizard_path = Path(__file__).resolve().parent / "setup_wizard.py"
    if not wizard_path.exists():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            wizard_path = Path(meipass) / "src" / "setup_wizard.py"
    spec = importlib.util.spec_from_file_location("setup_wizard", wizard_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    # Register in sys.modules BEFORE exec so that `from __future__ import annotations`
    # + @dataclass can resolve type hints via typing.get_type_hints().
    sys.modules["setup_wizard"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_sw = _load_setup_wizard()
ALL_SUPPORTED_KEYS = _sw.ALL_SUPPORTED_KEYS
CONTENT_PROVIDERS = _sw.CONTENT_PROVIDERS
GATEWAY_PROVIDERS = _sw.GATEWAY_PROVIDERS
_build_env_content = _sw._build_env_content
_read_existing_env = _sw._read_existing_env


DOCKER_INSTALLER_URL = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def _mask_secret(value: str) -> str:
    value = value.strip()
    if not value:
        return "（未填写）"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}****{value[-4:]}"


class PlaceholderText:
    def __init__(self, textbox: ctk.CTkTextbox, placeholder: str) -> None:
        self.textbox = textbox
        self.placeholder = placeholder
        self.active = False
        self._set_placeholder()
        self.textbox.bind("<FocusIn>", self._on_focus_in)
        self.textbox.bind("<FocusOut>", self._on_focus_out)

    def _set_placeholder(self) -> None:
        self.active = True
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", self.placeholder)
        self.textbox.configure(text_color="gray70")

    def _on_focus_in(self, _event: object) -> None:
        if self.active:
            self.textbox.delete("1.0", "end")
            self.textbox.configure(text_color="gray90")
            self.active = False

    def _on_focus_out(self, _event: object) -> None:
        if not self.textbox.get("1.0", "end").strip():
            self._set_placeholder()

    def get(self) -> str:
        if self.active:
            return ""
        return self.textbox.get("1.0", "end").strip()

    def set(self, value: str) -> None:
        self.textbox.delete("1.0", "end")
        if value.strip():
            self.textbox.insert("1.0", value)
            self.textbox.configure(text_color="gray90")
            self.active = False
        else:
            self._set_placeholder()


class WindowsLauncherApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.runtime_root = _runtime_root()
        self.project_root = Path.cwd()
        self.env_path = self.project_root / ".env"
        self.existing_values = _read_existing_env(self.env_path)

        self.title("闲鱼 API-first 一键部署")
        self.geometry("800x650")
        self.minsize(760, 620)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.gateway_provider_var = ctk.StringVar(value=GATEWAY_PROVIDERS[0].id)
        self.content_provider_var = ctk.StringVar(value=CONTENT_PROVIDERS[0].id)

        self.gateway_key_var = ctk.StringVar(value="")
        self.content_key_var = ctk.StringVar(value="")

        self.custom_gateway_base_url_var = ctk.StringVar(value=self.existing_values.get("CUSTOM_GATEWAY_BASE_URL", ""))
        self.custom_content_base_url_var = ctk.StringVar(value=self.existing_values.get("AI_BASE_URL", ""))
        self.custom_content_model_var = ctk.StringVar(value=self.existing_values.get("AI_MODEL", ""))

        self.token_var = ctk.StringVar(value=self.existing_values.get("OPENCLAW_GATEWAY_TOKEN", secrets.token_hex(32)))
        self.password_var = ctk.StringVar(value=self.existing_values.get("AUTH_PASSWORD", ""))
        self.username_var = ctk.StringVar(value=self.existing_values.get("AUTH_USERNAME", "admin"))
        self.port_var = ctk.StringVar(value=self.existing_values.get("FRONTEND_PORT", "5173"))
        self.password_masked = True

        self.docker_ready = False
        self.docker_skipped = False
        self.deploy_running = False

        self.status_var = ctk.StringVar(value="")
        self.status_color = "gray80"

        self.page_container = ctk.CTkFrame(self)
        self.page_container.pack(fill="both", expand=True, padx=18, pady=18)

        self.pages: list[ctk.CTkFrame] = []
        self.current_page = 0

        self._build_pages()
        self._apply_existing_values()
        self.show_page(0)
        self.after(200, self._detect_docker_async)

    def _build_pages(self) -> None:
        self.pages = [
            self._build_page_welcome(),
            self._build_page_gateway(),
            self._build_page_content(),
            self._build_page_auth(),
            self._build_page_cookie(),
            self._build_page_confirm(),
        ]
        for page in self.pages:
            page.grid(row=0, column=0, sticky="nsew")
        self.page_container.grid_rowconfigure(0, weight=1)
        self.page_container.grid_columnconfigure(0, weight=1)

    def _build_page_welcome(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.page_container)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(7, weight=1)

        ctk.CTkLabel(frame, text="闲鱼 API-first 一键部署向导", font=ctk.CTkFont(size=30, weight="bold")).grid(
            row=0, column=0, padx=30, pady=(30, 8), sticky="w"
        )
        ctk.CTkLabel(frame, text="v6.1.0", text_color="gray70").grid(row=1, column=0, padx=30, pady=(0, 20), sticky="w")

        ctk.CTkLabel(
            frame,
            text="将引导你完成 Docker 检测、AI 配置、鉴权与 Cookie 设置。",
            text_color="gray80",
        ).grid(row=2, column=0, padx=30, pady=(0, 18), sticky="w")

        self.docker_status_dot = ctk.CTkLabel(frame, text="●", text_color="red")
        self.docker_status_dot.grid(row=3, column=0, padx=(30, 0), pady=(0, 8), sticky="w")
        self.docker_status_text = ctk.CTkLabel(frame, text="正在检测 Docker...", text_color="gray85")
        self.docker_status_text.grid(row=3, column=0, padx=(52, 30), pady=(0, 8), sticky="w")

        self.docker_error_text = ctk.CTkLabel(frame, text="", text_color="#ff6f6f", wraplength=700, justify="left")
        self.docker_error_text.grid(row=4, column=0, padx=30, pady=(0, 12), sticky="w")

        self.download_docker_btn = ctk.CTkButton(
            frame,
            text="下载 Docker Desktop",
            command=lambda: webbrowser.open(DOCKER_INSTALLER_URL),
            width=180,
        )
        self.download_docker_btn.grid(row=5, column=0, padx=30, pady=(0, 8), sticky="w")
        self.download_docker_btn.grid_remove()

        nav = ctk.CTkFrame(frame, fg_color="transparent")
        nav.grid(row=8, column=0, padx=30, pady=24, sticky="ew")
        nav.grid_columnconfigure(0, weight=1)

        self.skip_docker_btn = ctk.CTkButton(
            nav,
            text="跳过检测",
            fg_color="transparent",
            hover=False,
            text_color="#7fb8ff",
            command=self._skip_docker_check,
            width=90,
        )
        self.skip_docker_btn.grid(row=0, column=0, sticky="w")

        self.next_from_welcome_btn = ctk.CTkButton(
            nav, text="下一步", width=140, state="disabled", command=self._goto_next
        )
        self.next_from_welcome_btn.grid(row=0, column=1, sticky="e")
        return frame

    def _build_page_gateway(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.page_container)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(6, weight=1)

        ctk.CTkLabel(frame, text="第 2 步：主 AI 服务", font=ctk.CTkFont(size=24, weight="bold")).grid(
            row=0, column=0, padx=30, pady=(30, 12), sticky="w"
        )

        ctk.CTkLabel(frame, text="请选择主 AI 服务，用于消息回复、策略判断和文本生成。", text_color="gray80").grid(
            row=1, column=0, padx=30, pady=(0, 18), sticky="w"
        )

        self.gateway_option = ctk.CTkOptionMenu(
            frame,
            values=[provider.title for provider in GATEWAY_PROVIDERS],
            command=self._on_gateway_title_selected,
            width=420,
        )
        self.gateway_option.grid(row=2, column=0, padx=30, pady=(0, 18), sticky="w")

        self.gateway_key_label = ctk.CTkLabel(frame, text="API 密钥", font=ctk.CTkFont(size=14, weight="bold"))
        self.gateway_key_label.grid(row=3, column=0, padx=30, pady=(0, 8), sticky="w")
        self.gateway_key_entry = ctk.CTkEntry(frame, width=520, textvariable=self.gateway_key_var)
        self.gateway_key_entry.grid(row=4, column=0, padx=30, pady=(0, 6), sticky="w")
        self.gateway_hint_label = ctk.CTkLabel(frame, text="", text_color="gray70")
        self.gateway_hint_label.grid(row=5, column=0, padx=30, pady=(0, 10), sticky="w")

        self.gateway_custom_url_label = ctk.CTkLabel(frame, text="Base URL", font=ctk.CTkFont(size=14, weight="bold"))
        self.gateway_custom_url_label.grid(row=6, column=0, padx=30, pady=(0, 8), sticky="w")
        self.gateway_custom_url_entry = ctk.CTkEntry(frame, width=520, textvariable=self.custom_gateway_base_url_var)
        self.gateway_custom_url_entry.grid(row=7, column=0, padx=30, pady=(0, 6), sticky="w")
        self.gateway_custom_url_label.grid_remove()
        self.gateway_custom_url_entry.grid_remove()

        self.gateway_error_label = ctk.CTkLabel(frame, text="", text_color="#ff6f6f")
        self.gateway_error_label.grid(row=8, column=0, padx=30, pady=(0, 4), sticky="w")

        nav = ctk.CTkFrame(frame, fg_color="transparent")
        nav.grid(row=9, column=0, padx=30, pady=24, sticky="ew")
        nav.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(nav, text="上一步", width=140, command=self._goto_prev).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(nav, text="下一步", width=140, command=self._validate_gateway_and_next).grid(
            row=0, column=1, sticky="e"
        )
        return frame

    def _build_page_content(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.page_container)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(7, weight=1)

        ctk.CTkLabel(frame, text="第 3 步：业务 AI 服务", font=ctk.CTkFont(size=24, weight="bold")).grid(
            row=0, column=0, padx=30, pady=(30, 12), sticky="w"
        )
        ctk.CTkLabel(frame, text="用于标题与描述生成的业务文案模型配置。", text_color="gray80").grid(
            row=1, column=0, padx=30, pady=(0, 18), sticky="w"
        )

        self.content_option = ctk.CTkOptionMenu(
            frame,
            values=[provider.title for provider in CONTENT_PROVIDERS],
            command=self._on_content_title_selected,
            width=420,
        )
        self.content_option.grid(row=2, column=0, padx=30, pady=(0, 18), sticky="w")

        self.content_key_label = ctk.CTkLabel(frame, text="API 密钥", font=ctk.CTkFont(size=14, weight="bold"))
        self.content_key_label.grid(row=3, column=0, padx=30, pady=(0, 8), sticky="w")
        self.content_key_entry = ctk.CTkEntry(frame, width=520, textvariable=self.content_key_var)
        self.content_key_entry.grid(row=4, column=0, padx=30, pady=(0, 6), sticky="w")
        self.content_hint_label = ctk.CTkLabel(frame, text="", text_color="gray70")
        self.content_hint_label.grid(row=5, column=0, padx=30, pady=(0, 4), sticky="w")
        self.content_shared_label = ctk.CTkLabel(frame, text="", text_color="#7fb8ff")
        self.content_shared_label.grid(row=6, column=0, padx=30, pady=(0, 10), sticky="w")

        self.content_custom_url_label = ctk.CTkLabel(frame, text="Base URL", font=ctk.CTkFont(size=14, weight="bold"))
        self.content_custom_url_label.grid(row=7, column=0, padx=30, pady=(0, 8), sticky="w")
        self.content_custom_url_entry = ctk.CTkEntry(frame, width=520, textvariable=self.custom_content_base_url_var)
        self.content_custom_url_entry.grid(row=8, column=0, padx=30, pady=(0, 6), sticky="w")
        self.content_custom_model_label = ctk.CTkLabel(frame, text="模型名称", font=ctk.CTkFont(size=14, weight="bold"))
        self.content_custom_model_label.grid(row=9, column=0, padx=30, pady=(0, 8), sticky="w")
        self.content_custom_model_entry = ctk.CTkEntry(frame, width=520, textvariable=self.custom_content_model_var)
        self.content_custom_model_entry.grid(row=10, column=0, padx=30, pady=(0, 6), sticky="w")
        self.content_custom_url_label.grid_remove()
        self.content_custom_url_entry.grid_remove()
        self.content_custom_model_label.grid_remove()
        self.content_custom_model_entry.grid_remove()

        self.content_error_label = ctk.CTkLabel(frame, text="", text_color="#ff6f6f")
        self.content_error_label.grid(row=11, column=0, padx=30, pady=(0, 4), sticky="w")

        nav = ctk.CTkFrame(frame, fg_color="transparent")
        nav.grid(row=12, column=0, padx=30, pady=24, sticky="ew")
        nav.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(nav, text="上一步", width=140, command=self._goto_prev).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(nav, text="下一步", width=140, command=self._validate_content_and_next).grid(
            row=0, column=1, sticky="e"
        )
        return frame

    def _build_page_auth(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.page_container)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(10, weight=1)

        ctk.CTkLabel(frame, text="第 4 步：鉴权与端口", font=ctk.CTkFont(size=24, weight="bold")).grid(
            row=0, column=0, padx=30, pady=(30, 12), sticky="w"
        )

        ctk.CTkLabel(frame, text="兼容旧变量 OPENCLAW_GATEWAY_TOKEN（可留空）", font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=0, padx=30, pady=(0, 6), sticky="w"
        )
        ctk.CTkEntry(frame, width=620, textvariable=self.token_var).grid(
            row=2, column=0, padx=30, pady=(0, 12), sticky="w"
        )

        ctk.CTkLabel(frame, text="AUTH_PASSWORD", font=ctk.CTkFont(weight="bold")).grid(
            row=3, column=0, padx=30, pady=(0, 6), sticky="w"
        )
        pw_wrap = ctk.CTkFrame(frame, fg_color="transparent")
        pw_wrap.grid(row=4, column=0, padx=30, pady=(0, 12), sticky="w")
        self.password_entry = ctk.CTkEntry(pw_wrap, width=500, textvariable=self.password_var, show="*")
        self.password_entry.grid(row=0, column=0, padx=(0, 12), sticky="w")
        self.toggle_password_btn = ctk.CTkButton(pw_wrap, text="显示", width=90, command=self._toggle_password)
        self.toggle_password_btn.grid(row=0, column=1, sticky="w")

        ctk.CTkLabel(frame, text="AUTH_USERNAME", font=ctk.CTkFont(weight="bold")).grid(
            row=5, column=0, padx=30, pady=(0, 6), sticky="w"
        )
        ctk.CTkEntry(frame, width=360, textvariable=self.username_var).grid(
            row=6, column=0, padx=30, pady=(0, 12), sticky="w"
        )

        ctk.CTkLabel(frame, text="FRONTEND_PORT", font=ctk.CTkFont(weight="bold")).grid(
            row=7, column=0, padx=30, pady=(0, 6), sticky="w"
        )
        ctk.CTkEntry(frame, width=220, textvariable=self.port_var).grid(
            row=8, column=0, padx=30, pady=(0, 12), sticky="w"
        )

        self.auth_error_label = ctk.CTkLabel(frame, text="", text_color="#ff6f6f")
        self.auth_error_label.grid(row=9, column=0, padx=30, pady=(0, 8), sticky="w")

        nav = ctk.CTkFrame(frame, fg_color="transparent")
        nav.grid(row=11, column=0, padx=30, pady=24, sticky="ew")
        nav.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(nav, text="上一步", width=140, command=self._goto_prev).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(nav, text="下一步", width=140, command=self._validate_auth_and_next).grid(
            row=0, column=1, sticky="e"
        )
        return frame

    def _build_page_cookie(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.page_container)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(6, weight=1)

        ctk.CTkLabel(frame, text="第 5 步：闲鱼 Cookie", font=ctk.CTkFont(size=24, weight="bold")).grid(
            row=0, column=0, padx=30, pady=(30, 12), sticky="w"
        )
        ctk.CTkLabel(
            frame,
            text="打开 goofish.com → 登录 → F12 → Network → 复制 Cookie",
            text_color="gray80",
        ).grid(row=1, column=0, padx=30, pady=(0, 12), sticky="w")

        ctk.CTkLabel(frame, text="XIANYU_COOKIE_1", font=ctk.CTkFont(weight="bold")).grid(
            row=2, column=0, padx=30, pady=(0, 6), sticky="w"
        )
        self.cookie_1_box = ctk.CTkTextbox(frame, width=700, height=130)
        self.cookie_1_box.grid(row=3, column=0, padx=30, pady=(0, 10), sticky="w")
        self.cookie_1_placeholder = PlaceholderText(self.cookie_1_box, "从浏览器复制的完整 Cookie...")

        ctk.CTkLabel(frame, text="XIANYU_COOKIE_2（可选）", font=ctk.CTkFont(weight="bold")).grid(
            row=4, column=0, padx=30, pady=(0, 6), sticky="w"
        )
        self.cookie_2_box = ctk.CTkTextbox(frame, width=700, height=70)
        self.cookie_2_box.grid(row=5, column=0, padx=30, pady=(0, 10), sticky="w")
        self.cookie_2_placeholder = PlaceholderText(self.cookie_2_box, "可留空")

        self.cookie_error_label = ctk.CTkLabel(frame, text="", text_color="#ff6f6f")
        self.cookie_error_label.grid(row=6, column=0, padx=30, pady=(0, 8), sticky="w")

        nav = ctk.CTkFrame(frame, fg_color="transparent")
        nav.grid(row=7, column=0, padx=30, pady=24, sticky="ew")
        nav.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(nav, text="上一步", width=140, command=self._goto_prev).grid(
            row=0, column=0, padx=(0, 10), sticky="w"
        )
        ctk.CTkButton(
            nav, text="跳过，稍后配置", width=160, fg_color="transparent", border_width=1, command=self._skip_cookie
        ).grid(row=0, column=1, padx=(0, 10), sticky="e")
        ctk.CTkButton(nav, text="下一步", width=140, command=self._validate_cookie_and_next).grid(
            row=0, column=2, sticky="e"
        )
        return frame

    def _build_page_confirm(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.page_container)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="第 6 步：确认并部署", font=ctk.CTkFont(size=24, weight="bold")).grid(
            row=0, column=0, padx=30, pady=(20, 10), sticky="w"
        )

        self.summary_box = ctk.CTkTextbox(frame, width=700, height=240)
        self.summary_box.grid(row=1, column=0, padx=30, pady=(0, 10), sticky="nsew")
        self.summary_box.configure(state="disabled")

        action_frame = ctk.CTkFrame(frame, fg_color="transparent")
        action_frame.grid(row=2, column=0, padx=30, pady=(0, 10), sticky="ew")
        action_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.back_btn = ctk.CTkButton(action_frame, text="上一步", width=140, command=self._goto_prev)
        self.back_btn.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.generate_only_btn = ctk.CTkButton(action_frame, text="仅生成配置", width=160, command=self._generate_only)
        self.generate_only_btn.grid(row=0, column=1, padx=10)

        self.deploy_btn = ctk.CTkButton(action_frame, text="生成配置并启动", width=180, command=self._deploy)
        self.deploy_btn.grid(row=0, column=2, padx=(10, 0), sticky="e")

        self.progress = ctk.CTkProgressBar(frame, mode="indeterminate")
        self.progress.grid(row=3, column=0, padx=30, pady=(10, 10), sticky="ew")
        self.progress.grid_remove()

        self.result_label = ctk.CTkLabel(
            frame, textvariable=self.status_var, text_color="gray80", wraplength=700, justify="left"
        )
        self.result_label.grid(row=4, column=0, padx=30, pady=(0, 8), sticky="w")

        bottom = ctk.CTkFrame(frame, fg_color="transparent")
        bottom.grid(row=5, column=0, padx=30, pady=(0, 16), sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)
        self.open_browser_btn = ctk.CTkButton(bottom, text="打开浏览器", width=140, command=self._open_web)
        self.open_browser_btn.grid(row=0, column=0, sticky="w")
        self.open_browser_btn.grid_remove()
        self.show_logs_btn = ctk.CTkButton(bottom, text="查看日志", width=140, command=self._show_logs)
        self.show_logs_btn.grid(row=0, column=1, sticky="e")
        self.show_logs_btn.grid_remove()
        return frame

    def show_page(self, index: int) -> None:
        self.current_page = index
        self.pages[index].tkraise()
        if index == 2:
            self._sync_content_key_state()
        if index == 5:
            self._render_summary()

    def _goto_next(self) -> None:
        if self.current_page < len(self.pages) - 1:
            self.show_page(self.current_page + 1)

    def _goto_prev(self) -> None:
        if self.current_page > 0:
            self.show_page(self.current_page - 1)

    def _set_status(self, text: str, color: str = "gray85") -> None:
        self.status_var.set(text)
        self.result_label.configure(text_color=color)

    def _provider_by_gateway_id(self, provider_id: str):
        return next(item for item in GATEWAY_PROVIDERS if item.id == provider_id)

    def _provider_by_content_id(self, provider_id: str):
        return next(item for item in CONTENT_PROVIDERS if item.id == provider_id)

    def _on_gateway_title_selected(self, selected_title: str) -> None:
        for provider in GATEWAY_PROVIDERS:
            if provider.title == selected_title:
                self.gateway_provider_var.set(provider.id)
                break
        self._render_gateway_field()
        self._sync_content_key_state()

    def _on_content_title_selected(self, selected_title: str) -> None:
        for provider in CONTENT_PROVIDERS:
            if provider.title == selected_title:
                self.content_provider_var.set(provider.id)
                break
        self._render_content_field()
        self._sync_content_key_state()

    def _render_gateway_field(self) -> None:
        provider = self._provider_by_gateway_id(self.gateway_provider_var.get())
        self.gateway_option.set(provider.title)
        self.gateway_key_label.configure(text=f"{provider.env_key}")
        self.gateway_key_entry.configure(placeholder_text=provider.hint)
        if provider.id == "custom":
            self.gateway_hint_label.configure(text="提示：配置自定义 OpenAI 兼容的主 AI Provider")
            self.gateway_custom_url_label.grid()
            self.gateway_custom_url_entry.grid()
        else:
            self.gateway_hint_label.configure(text=f"提示：{provider.hint}")
            self.gateway_custom_url_label.grid_remove()
            self.gateway_custom_url_entry.grid_remove()

    def _render_content_field(self) -> None:
        provider = self._provider_by_content_id(self.content_provider_var.get())
        self.content_option.set(provider.title)
        self.content_key_label.configure(text=f"{provider.env_key}")
        self.content_key_entry.configure(placeholder_text=provider.hint)
        if provider.id == "custom":
            self.content_hint_label.configure(text="提示：配置自定义 OpenAI 兼容的 Content Provider")
            self.content_custom_url_label.grid()
            self.content_custom_url_entry.grid()
            self.content_custom_model_label.grid()
            self.content_custom_model_entry.grid()
        else:
            self.content_hint_label.configure(text=f"提示：{provider.hint}")
            self.content_custom_url_label.grid_remove()
            self.content_custom_url_entry.grid_remove()
            self.content_custom_model_label.grid_remove()
            self.content_custom_model_entry.grid_remove()

    def _sync_content_key_state(self) -> None:
        gateway = self._provider_by_gateway_id(self.gateway_provider_var.get())
        content = self._provider_by_content_id(self.content_provider_var.get())
        if gateway.env_key == content.env_key:
            self.content_key_var.set(self.gateway_key_var.get())
            self.content_key_entry.configure(state="disabled")
            self.content_shared_label.configure(text="与网关共用同一密钥")
        else:
            self.content_key_entry.configure(state="normal")
            self.content_shared_label.configure(text="")

    def _apply_existing_values(self) -> None:
        existing = self.existing_values
        gateway_choice = GATEWAY_PROVIDERS[0]
        for provider in GATEWAY_PROVIDERS:
            if existing.get(provider.env_key):
                gateway_choice = provider
                break

        content_choice = CONTENT_PROVIDERS[0]
        existing_provider = existing.get("AI_PROVIDER", "")
        for provider in CONTENT_PROVIDERS:
            if provider.id == existing_provider or existing.get(provider.env_key):
                content_choice = provider
                if provider.id == existing_provider:
                    break

        self.gateway_provider_var.set(gateway_choice.id)
        self.content_provider_var.set(content_choice.id)

        self.gateway_key_var.set(existing.get(gateway_choice.env_key, ""))
        self.content_key_var.set(existing.get(content_choice.env_key, ""))

        self.custom_gateway_base_url_var.set(existing.get("CUSTOM_GATEWAY_BASE_URL", ""))
        self.custom_content_base_url_var.set(existing.get("AI_BASE_URL", ""))
        self.custom_content_model_var.set(existing.get("AI_MODEL", ""))

        self._render_gateway_field()
        self._render_content_field()

        self.cookie_1_placeholder.set(existing.get("XIANYU_COOKIE_1", ""))
        self.cookie_2_placeholder.set(existing.get("XIANYU_COOKIE_2", ""))
        self._sync_content_key_state()
        self.gateway_key_var.trace_add("write", self._on_gateway_key_change)

    def _on_gateway_key_change(self, *_args: object) -> None:
        self._sync_content_key_state()

    def _skip_docker_check(self) -> None:
        self.docker_skipped = True
        self.next_from_welcome_btn.configure(state="normal")
        self.docker_status_dot.configure(text_color="#f6c85f")
        self.docker_status_text.configure(text="已跳过 Docker 检测")
        self.docker_error_text.configure(text="")
        self.download_docker_btn.grid_remove()

    def _detect_docker_async(self) -> None:
        self.docker_status_text.configure(text="正在检测 Docker 与 Compose...", text_color="gray85")

        def worker() -> None:
            ok = True
            error = ""
            if shutil.which("docker") is None:
                ok = False
                error = "未检测到 Docker，请先安装并启动 Docker Desktop。"
            else:
                result = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    ok = False
                    error = "检测到 Docker，但 docker compose 不可用。请确认 Docker Desktop 已启动。"

            self.after(0, lambda: self._on_docker_checked(ok, error))

        threading.Thread(target=worker, daemon=True).start()

    def _on_docker_checked(self, ok: bool, error: str) -> None:
        self.docker_ready = ok
        if ok:
            self.docker_status_dot.configure(text_color="#49c16d")
            self.docker_status_text.configure(text="Docker 已就绪", text_color="#8ad9a0")
            self.docker_error_text.configure(text="")
            self.download_docker_btn.grid_remove()
            self.next_from_welcome_btn.configure(state="normal")
        else:
            self.docker_status_dot.configure(text_color="#ff6f6f")
            self.docker_status_text.configure(text="未检测到 Docker", text_color="#ff8d8d")
            self.docker_error_text.configure(text=error)
            self.download_docker_btn.grid()
            if not self.docker_skipped:
                self.next_from_welcome_btn.configure(state="disabled")

    def _validate_gateway_and_next(self) -> None:
        self.gateway_error_label.configure(text="")
        if not self.gateway_key_var.get().strip():
            self.gateway_error_label.configure(text="请填写主 AI 服务 API 密钥")
            return
        provider = self._provider_by_gateway_id(self.gateway_provider_var.get())
        if provider.id == "custom" and not self.custom_gateway_base_url_var.get().strip():
            self.gateway_error_label.configure(text="自定义 Provider 需要填写 Base URL")
            return
        self._goto_next()

    def _validate_content_and_next(self) -> None:
        self.content_error_label.configure(text="")
        self._sync_content_key_state()
        if not self.content_key_var.get().strip():
            self.content_error_label.configure(text="请填写业务文案服务 API 密钥")
            return
        provider = self._provider_by_content_id(self.content_provider_var.get())
        if provider.id == "custom":
            if not self.custom_content_base_url_var.get().strip():
                self.content_error_label.configure(text="自定义 Provider 需要填写 Base URL")
                return
            if not self.custom_content_model_var.get().strip():
                self.content_error_label.configure(text="自定义 Provider 需要填写模型名称")
                return
        self._goto_next()

    def _toggle_password(self) -> None:
        self.password_masked = not self.password_masked
        if self.password_masked:
            self.password_entry.configure(show="*")
            self.toggle_password_btn.configure(text="显示")
        else:
            self.password_entry.configure(show="")
            self.toggle_password_btn.configure(text="隐藏")

    def _validate_auth_and_next(self) -> None:
        self.auth_error_label.configure(text="")
        password = self.password_var.get().strip()
        username = self.username_var.get().strip()
        port = self.port_var.get().strip()

        if not password:
            self.auth_error_label.configure(text="AUTH_PASSWORD 不能为空")
            return
        if not username:
            self.auth_error_label.configure(text="AUTH_USERNAME 不能为空")
            return
        if not port.isdigit() or not (1 <= int(port) <= 65535):
            self.auth_error_label.configure(text="FRONTEND_PORT 需为 1-65535 的数字")
            return
        self._goto_next()

    def _validate_cookie_and_next(self) -> None:
        self.cookie_error_label.configure(text="")
        if not self.cookie_1_placeholder.get():
            self.cookie_error_label.configure(text="请填写 XIANYU_COOKIE_1")
            return
        self._goto_next()

    def _skip_cookie(self) -> None:
        self.cookie_1_placeholder.set("")
        self.cookie_2_placeholder.set("")
        self._goto_next()

    def _collect_merged_values(self) -> tuple[dict[str, str], object, object]:
        existing = dict(self.existing_values)
        merged = dict(existing)
        for key in ALL_SUPPORTED_KEYS:
            merged.setdefault(key, "")

        for key in (
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "MOONSHOT_API_KEY",
            "MINIMAX_API_KEY",
            "ZAI_API_KEY",
            "CUSTOM_GATEWAY_API_KEY",
            "DEEPSEEK_API_KEY",
            "DASHSCOPE_API_KEY",
            "ARK_API_KEY",
            "ZHIPU_API_KEY",
            "AI_API_KEY",
        ):
            merged[key] = ""

        gateway = self._provider_by_gateway_id(self.gateway_provider_var.get())
        content = self._provider_by_content_id(self.content_provider_var.get())

        gateway_api_key = self.gateway_key_var.get().strip()
        content_api_key = self.content_key_var.get().strip()

        merged[gateway.env_key] = gateway_api_key
        merged[content.env_key] = content_api_key

        custom_gateway_base_url = self.custom_gateway_base_url_var.get().strip()
        custom_content_base_url = self.custom_content_base_url_var.get().strip()
        custom_content_model = self.custom_content_model_var.get().strip()

        if content.id == "custom":
            content_base_url = custom_content_base_url
            content_model = custom_content_model
        else:
            content_base_url = content.base_url
            content_model = content.model

        merged.update(
            {
                "OPENCLAW_GATEWAY_TOKEN": self.token_var.get().strip(),
                "AUTH_PASSWORD": self.password_var.get().strip(),
                "AUTH_USERNAME": self.username_var.get().strip(),
                "FRONTEND_PORT": self.port_var.get().strip(),
                "XIANYU_COOKIE_1": self.cookie_1_placeholder.get(),
                "XIANYU_COOKIE_2": self.cookie_2_placeholder.get(),
                "AI_PROVIDER": content.id,
                "AI_API_KEY": content_api_key,
                "AI_BASE_URL": content_base_url,
                "AI_MODEL": content_model,
                "AI_TEMPERATURE": existing.get("AI_TEMPERATURE", "0.7"),
                "OPENAI_BASE_URL": existing.get("OPENAI_BASE_URL", ""),
                "CUSTOM_GATEWAY_BASE_URL": custom_gateway_base_url,
            }
        )
        return merged, gateway, content

    def _write_env_file(self) -> tuple[bool, str]:
        try:
            merged, gateway, content = self._collect_merged_values()
            text = _build_env_content(merged, gateway.env_key, content.env_key)
            self.env_path.write_text(text, encoding="utf-8")
            return True, f"已写入配置文件：{self.env_path}"
        except Exception as exc:
            return False, f"写入 .env 失败：{exc}"

    def _render_summary(self) -> None:
        merged, gateway, content = self._collect_merged_values()
        lines = [
            "请确认以下配置：",
            "",
            f"主 AI 服务：{gateway.title}",
            f"主 AI 密钥：{_mask_secret(merged.get(gateway.env_key, ''))}",
        ]
        if gateway.id == "custom":
            lines.append(f"网关 Base URL：{merged.get('CUSTOM_GATEWAY_BASE_URL', '')}")
        lines.extend(
            [
                f"业务服务：{content.title}",
                f"业务密钥：{_mask_secret(merged.get(content.env_key, ''))}",
                f"业务模型：{merged.get('AI_MODEL', '')}",
            ]
        )
        if content.id == "custom":
            lines.append(f"业务 Base URL：{merged.get('AI_BASE_URL', '')}")
        lines.extend(
            [
                f"服务端口：{merged.get('FRONTEND_PORT', '')}",
                f"后台账号：{merged.get('AUTH_USERNAME', '')}",
                f"后台密码：{_mask_secret(merged.get('AUTH_PASSWORD', ''))}",
                f"Cookie 1：{_mask_secret(merged.get('XIANYU_COOKIE_1', ''))}",
                f"Cookie 2：{_mask_secret(merged.get('XIANYU_COOKIE_2', ''))}",
                "",
                "确认后可选择仅生成配置，或直接生成并启动容器。",
            ]
        )

        self.summary_box.configure(state="normal")
        self.summary_box.delete("1.0", "end")
        self.summary_box.insert("1.0", "\n".join(lines))
        self.summary_box.configure(state="disabled")

    def _generate_only(self) -> None:
        ok, msg = self._write_env_file()
        if ok:
            self._set_status(f"{msg}\n你可以稍后手动执行：docker compose up -d", "#8ad9a0")
            self.show_logs_btn.grid_remove()
            self.open_browser_btn.grid_remove()
        else:
            self._set_status(msg, "#ff8d8d")

    def _set_deploy_controls(self, running: bool) -> None:
        self.deploy_running = running
        state = "disabled" if running else "normal"
        self.deploy_btn.configure(state=state)
        self.generate_only_btn.configure(state=state)

    def _deploy(self) -> None:
        if self.deploy_running:
            return
        ok, msg = self._write_env_file()
        if not ok:
            self._set_status(msg, "#ff8d8d")
            return

        self._set_deploy_controls(True)
        self._set_status(f"{msg}\n正在执行 docker compose up -d，请稍候...", "gray85")
        self.show_logs_btn.grid_remove()
        self.open_browser_btn.grid_remove()
        self.progress.grid()
        self.progress.start()

        def worker() -> None:
            try:
                result = subprocess.run(
                    ["docker", "compose", "--env-file", str(self.env_path), "up", "-d"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                stdout = (result.stdout or "").strip()
                stderr = (result.stderr or "").strip()
                self.after(0, lambda: self._on_deploy_finished(result.returncode, stdout, stderr))
            except Exception as exc:
                err = exc
                self.after(0, lambda: self._on_deploy_exception(err))

        threading.Thread(target=worker, daemon=True).start()

    def _on_deploy_finished(self, code: int, stdout: str, stderr: str) -> None:
        self.progress.stop()
        self.progress.grid_remove()
        self._set_deploy_controls(False)

        if code != 0:
            detail = stderr or stdout or "未知错误"
            self._set_status(f"启动失败，请检查配置或 Docker 状态。\n错误详情：{detail}", "#ff8d8d")
            self.show_logs_btn.grid()
            self.open_browser_btn.grid_remove()
            return

        port = self.port_var.get().strip()
        self._set_status("容器启动中，正在检查状态...", "gray85")
        self.after(3000, lambda: self._check_container_status(port))

    def _on_deploy_exception(self, exc: Exception) -> None:
        self.progress.stop()
        self.progress.grid_remove()
        self._set_deploy_controls(False)
        self._set_status(f"执行启动命令时出现异常：{exc}", "#ff8d8d")
        self.show_logs_btn.grid()

    def _check_container_status(self, port: str) -> None:
        def worker() -> None:
            try:
                import time

                time.sleep(2)

                result = subprocess.run(
                    ["docker", "compose", "--env-file", str(self.env_path), "ps", "--format", "json"],
                    capture_output=True,
                    text=True,
                    check=False,
                )

                if result.returncode != 0:
                    self.after(
                        0,
                        lambda: self._set_status(
                            f"启动完成！访问地址：http://localhost:{port}\n（注意：无法获取容器状态，请手动检查）",
                            "#8ad9a0",
                        ),
                    )
                    self.after(0, self.open_browser_btn.grid)
                    return

                output = result.stdout or ""
                if '"Restarting"' in output or "restarting" in output.lower():
                    logs_result = subprocess.run(
                        ["docker", "compose", "--env-file", str(self.env_path), "logs", "--tail=30"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    logs = (logs_result.stdout or "") + (logs_result.stderr or "")
                    error_msg = "容器正在重启，可能原因：\n"
                    if "At least one AI provider API key" in logs:
                        error_msg += "• AI Key未配置：请在第2步配置主 AI 的 API Key\n"
                    elif "pairing required" in logs.lower():
                        error_msg += "• 需要设备配对：请在PowerShell执行配对命令\n"
                    elif "cookie" in logs.lower() and ("missing" in logs.lower() or "invalid" in logs.lower()):
                        error_msg += "• Cookie无效：请在第5步配置有效的闲鱼Cookie\n"
                    else:
                        error_msg += "• 配置错误或其他问题，请查看日志\n"

                    error_msg += "\n查看日志了解详情。"

                    self.after(0, lambda: self._set_status(error_msg, "#ff8d8d"))
                    self.after(0, self.show_logs_btn.grid)
                    self.after(0, self.open_browser_btn.grid_remove)
                else:
                    self.after(0, lambda: self._set_status(f"启动完成！访问地址：http://localhost:{port}", "#8ad9a0"))
                    self.after(0, self.open_browser_btn.grid)
                    self.after(0, self.show_logs_btn.grid_remove)

            except Exception:
                self.after(0, lambda: self._set_status(f"启动完成！访问地址：http://localhost:{port}", "#8ad9a0"))
                self.after(0, self.open_browser_btn.grid)

        threading.Thread(target=worker, daemon=True).start()

    def _open_web(self) -> None:
        webbrowser.open(f"http://localhost:{self.port_var.get().strip()}")

    def _show_logs(self) -> None:
        self._set_status("正在读取 docker compose logs --tail=80 ...", "gray85")

        def worker() -> None:
            try:
                result = subprocess.run(
                    ["docker", "compose", "--env-file", str(self.env_path), "logs", "--tail=80"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                text = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
                self.after(0, lambda: self._open_logs_window(text.strip() or "暂无日志输出"))
            except Exception as exc:
                err = exc
                self.after(0, lambda: self._open_logs_window(f"读取日志失败：{err}"))

        threading.Thread(target=worker, daemon=True).start()

    def _open_logs_window(self, text: str) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("容器日志")
        dialog.geometry("860x520")
        dialog.minsize(760, 420)
        dialog.transient(self)

        box = ctk.CTkTextbox(dialog)
        box.pack(fill="both", expand=True, padx=12, pady=12)
        box.insert("1.0", text)
        box.configure(state="disabled")


def main() -> None:
    _ = _runtime_root()
    app = WindowsLauncherApp()
    app.mainloop()


if __name__ == "__main__":
    main()
