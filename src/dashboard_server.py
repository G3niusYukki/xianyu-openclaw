"""轻量后台可视化与模块控制服务。"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import zipfile
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import yaml

from src.core.config import get_config
from src.modules.messages.service import MessagesService
from src.modules.quote.cost_table import CostTableRepository, normalize_courier_name
from src.modules.quote.setup import DEFAULT_MARKUP_RULES, QuoteSetupService
from src.modules.virtual_goods.service import VirtualGoodsService

MODULE_TARGETS = ("presales", "operations", "aftersales")


def _safe_int(value: str | None, default: int, min_value: int, max_value: int) -> int:
    try:
        if value is None:
            return default
        n = int(value)
        if n < min_value:
            return min_value
        if n > max_value:
            return max_value
        return n
    except (TypeError, ValueError):
        return default


def _error_payload(message: str, code: str = "INTERNAL_ERROR", details: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "success": False,
        "error": str(message),
        "error_code": str(code),
        "error_message": str(message),
    }
    if details is not None:
        payload["details"] = details
    return payload


def _extract_json_payload(text: str) -> Any | None:
    raw = str(text or "").strip()
    if not raw:
        return None

    try:
        return json.loads(raw)
    except Exception:
        pass

    for lch, rch in (("{", "}"), ("[", "]")):
        start = raw.find(lch)
        end = raw.rfind(rch)
        if start != -1 and end != -1 and end > start:
            candidate = raw[start : end + 1]
            try:
                return json.loads(candidate)
            except Exception:
                continue
    return None


class DashboardRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            yield conn

    def get_summary(self) -> dict[str, Any]:
        with self._connect() as conn:
            total_operations = conn.execute("SELECT COUNT(*) AS c FROM operation_logs").fetchone()["c"]
            today_operations = conn.execute(
                "SELECT COUNT(*) AS c FROM operation_logs WHERE date(timestamp)=date('now','localtime')"
            ).fetchone()["c"]
            active_products = conn.execute("SELECT COUNT(*) AS c FROM products WHERE status='active'").fetchone()["c"]
            sold_products = conn.execute("SELECT COUNT(*) AS c FROM products WHERE status='sold'").fetchone()["c"]
            total_views = conn.execute("SELECT COALESCE(SUM(views),0) AS s FROM product_metrics").fetchone()["s"]
            total_wants = conn.execute("SELECT COALESCE(SUM(wants),0) AS s FROM product_metrics").fetchone()["s"]
            total_sales = conn.execute("SELECT COALESCE(SUM(sales),0) AS s FROM product_metrics").fetchone()["s"]

        return {
            "total_operations": total_operations,
            "today_operations": today_operations,
            "active_products": active_products,
            "sold_products": sold_products,
            "total_views": total_views,
            "total_wants": total_wants,
            "total_sales": total_sales,
        }

    def get_trend(self, metric: str, days: int) -> list[dict[str, Any]]:
        allowed = {"views", "wants", "sales", "inquiries"}
        if metric not in allowed:
            metric = "views"

        start_date = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")

        sql = f"""
            SELECT date(timestamp) AS d, COALESCE(SUM({metric}),0) AS v
            FROM product_metrics
            WHERE date(timestamp) >= ?
            GROUP BY date(timestamp)
            ORDER BY d ASC
        """

        rows_by_day: dict[str, int] = {}
        with self._connect() as conn:
            for row in conn.execute(sql, (start_date,)).fetchall():
                rows_by_day[str(row["d"])] = int(row["v"])

        result = []
        for i in range(days):
            d = (datetime.now() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            result.append({"date": d, "value": rows_by_day.get(d, 0)})
        return result

    def get_recent_operations(self, limit: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT operation_type, product_id, account_id, status, timestamp
                FROM operation_logs
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [dict(row) for row in rows]

    def get_top_products(self, limit: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                  p.product_id,
                  p.title,
                  p.status,
                  COALESCE(SUM(m.views),0) AS views,
                  COALESCE(SUM(m.wants),0) AS wants,
                  COALESCE(SUM(m.sales),0) AS sales
                FROM products p
                LEFT JOIN product_metrics m ON m.product_id = p.product_id
                GROUP BY p.product_id, p.title, p.status
                ORDER BY wants DESC, views DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [dict(row) for row in rows]


class ModuleConsole:
    """通过 CLI 复用模块状态与控制能力。"""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()

    def _run_module_cli(
        self,
        action: str,
        target: str,
        extra_args: list[str] | None = None,
        timeout_seconds: int = 120,
    ) -> dict[str, Any]:
        cmd = [
            sys.executable,
            "-m",
            "src.cli",
            "module",
            "--action",
            action,
            "--target",
            target,
            *(extra_args or []),
        ]

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=max(10, int(timeout_seconds)),
            )
        except Exception as exc:
            return {
                "error": f"Module CLI execution failed: {exc}",
                "_cli_cmd": " ".join(cmd),
            }

        payload = _extract_json_payload(proc.stdout)

        if proc.returncode != 0:
            base: dict[str, Any]
            if isinstance(payload, dict):
                base = dict(payload)
            else:
                base = {"error": f"module command failed ({proc.returncode})"}
            if "error" not in base:
                stderr = (proc.stderr or "").strip()
                base["error"] = stderr or f"module command failed ({proc.returncode})"
            base["_cli_code"] = proc.returncode
            base["_cli_stderr"] = (proc.stderr or "").strip()
            base["_cli_cmd"] = " ".join(cmd)
            return base

        if isinstance(payload, dict):
            return payload

        if isinstance(payload, list):
            return {"items": payload}

        return {
            "ok": True,
            "stdout": (proc.stdout or "").strip(),
            "_cli_cmd": " ".join(cmd),
        }

    def status(self, window_minutes: int = 60, limit: int = 20) -> dict[str, Any]:
        return self._run_module_cli(
            action="status",
            target="all",
            extra_args=["--window-minutes", str(window_minutes), "--limit", str(limit)],
            timeout_seconds=90,
        )

    def logs(self, target: str, tail_lines: int = 120) -> dict[str, Any]:
        safe_target = target if target in {"all", *MODULE_TARGETS} else "all"
        return self._run_module_cli(
            action="logs",
            target=safe_target,
            extra_args=["--tail-lines", str(max(10, min(int(tail_lines), 500)))],
            timeout_seconds=90,
        )

    def check(self, skip_gateway: bool = False) -> dict[str, Any]:
        args: list[str] = []
        if bool(skip_gateway):
            args.append("--skip-gateway")
        return self._run_module_cli(action="check", target="all", extra_args=args, timeout_seconds=120)

    def control(self, action: str, target: str) -> dict[str, Any]:
        act = str(action or "").strip().lower()
        tgt = str(target or "").strip().lower()

        if act not in {"start", "stop", "restart", "recover"}:
            return {"error": f"Unsupported module action: {act}"}
        if tgt not in {"all", *MODULE_TARGETS}:
            return {"error": f"Unsupported module target: {tgt}"}

        args: list[str] = []
        if act == "start":
            args.extend(
                [
                    "--mode",
                    "daemon",
                    "--background",
                    "--interval",
                    "5",
                    "--limit",
                    "20",
                    "--claim-limit",
                    "10",
                    "--issue-type",
                    "delay",
                    "--init-default-tasks",
                ]
            )
        elif act == "restart":
            args.extend(
                [
                    "--mode",
                    "daemon",
                    "--interval",
                    "5",
                    "--limit",
                    "20",
                    "--claim-limit",
                    "10",
                    "--issue-type",
                    "delay",
                    "--stop-timeout",
                    "6",
                    "--init-default-tasks",
                ]
            )
        elif act == "recover":
            args.extend(
                [
                    "--mode",
                    "daemon",
                    "--interval",
                    "5",
                    "--limit",
                    "20",
                    "--claim-limit",
                    "10",
                    "--issue-type",
                    "delay",
                    "--stop-timeout",
                    "6",
                    "--init-default-tasks",
                ]
            )
        else:
            args.extend(["--stop-timeout", "6"])

        return self._run_module_cli(action=act, target=tgt, extra_args=args, timeout_seconds=120)


DEFAULT_WEIGHT_TEMPLATE = (
    "{origin_province}到{dest_province} {billing_weight}kg 首单价格\n"
    "{courier}: {price} 元\n"
    "预计时效：{eta_days}\n"
    "重要提示：\n"
    "体积重大于实际重量时按体积计费！"
)
DEFAULT_VOLUME_TEMPLATE = (
    "{origin_province}到{dest_province} {billing_weight}kg 首单价格\n"
    "体积重规则：{volume_formula}\n"
    "{courier}: {price} 元\n"
    "预计时效：{eta_days}\n"
    "重要提示：\n"
    "体积重大于实际重量时按体积计费！"
)


def _run_async(coro: Any) -> Any:
    """在 HTTP 线程内安全执行协程。"""

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


class MimicOps:
    """模仿 XianyuAutoAgent 的页面与操作能力。"""

    _ROUTE_FILE_EXTS = {".xlsx", ".xls", ".csv"}
    _MARKUP_FILE_EXTS = {".xlsx", ".xls", ".csv", ".json", ".yaml", ".yml", ".txt", ".md"}
    _MARKUP_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"}
    _MARKUP_REQUIRED_FIELDS = ("normal_first_add", "member_first_add", "normal_extra_add", "member_extra_add")
    _MARKUP_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
        "courier": ("运力", "快递", "快递公司", "物流", "渠道", "公司", "courier", "carrier", "name"),
        "normal_first_add": (
            "normal_first_add",
            "普通首重",
            "首重普通",
            "首重溢价普通",
            "首重加价普通",
            "first_normal",
            "normal_first",
        ),
        "member_first_add": (
            "member_first_add",
            "会员首重",
            "首重会员",
            "首重溢价会员",
            "首重加价会员",
            "first_member",
            "member_first",
            "vip_first",
        ),
        "normal_extra_add": (
            "normal_extra_add",
            "普通续重",
            "续重普通",
            "续重溢价普通",
            "续重加价普通",
            "extra_normal",
            "normal_extra",
        ),
        "member_extra_add": (
            "member_extra_add",
            "会员续重",
            "续重会员",
            "续重溢价会员",
            "续重加价会员",
            "extra_member",
            "member_extra",
            "vip_extra",
        ),
    }
    _COOKIE_REQUIRED_KEYS = ("_tb_token_", "cookie2", "sgcookie", "unb")
    _COOKIE_RECOMMENDED_KEYS = ("XSRF-TOKEN", "last_u_xianyu_web", "tfstk", "t", "cna")
    _COOKIE_DOMAIN_ALLOWLIST = ("goofish.com", "passport.goofish.com")
    _COOKIE_IMPORT_EXTS = {".txt", ".json", ".log", ".cookies", ".csv", ".tsv", ".har"}
    _COOKIE_HINT_KEYS = ("_tb_token_", "cookie2", "sgcookie", "unb", "_m_h5_tk", "_m_h5_tk_enc")
    _COOKIE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
    _ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    _LOG_TIME_RE = re.compile(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})")
    _RISK_BLOCK_PATTERNS = (
        "fail_sys_user_validate",
        "rgv587",
        "账号异常",
        "账号风险",
        "安全验证",
        "访问受限",
        "封控",
        "封禁",
    )
    _RISK_WARN_PATTERNS = (
        "http 400",
        "http 403",
        "forbidden",
        "unauthorized",
        "token api failed",
        "需要验证码",
        "验证码",
        "校验失败",
    )

    def __init__(self, project_root: str | Path, module_console: ModuleConsole):
        self.project_root = Path(project_root).resolve()
        self.module_console = module_console
        self._service_started_at = _now_iso()
        self._instance_id = f"dashboard-{os.getpid()}-{int(time.time())}"
        self._python_exec = sys.executable
        self._service_state: dict[str, Any] = {
            "suspended": False,
            "stopped": False,
            "updated_at": _now_iso(),
        }
        self._last_cookie_fp = ""
        self._last_token_error: str | None = None
        self._last_auto_recover_cookie_fp = ""
        self._last_auto_recover_at = ""
        self._last_auto_recover_result: dict[str, Any] = {}
        self._recover_lock = threading.Lock()

    @property
    def env_path(self) -> Path:
        return self.project_root / ".env"

    @property
    def logs_dir(self) -> Path:
        return self.project_root / "logs"

    @property
    def cookie_plugin_dir(self) -> Path:
        return self.project_root / "third_party" / "Get-cookies.txt-LOCALLY"

    def _read_env_lines(self) -> list[str]:
        if not self.env_path.exists():
            return []
        return self.env_path.read_text(encoding="utf-8", errors="ignore").splitlines()

    def _get_env_value(self, key: str) -> str:
        key_norm = f"{key}="
        for line in self._read_env_lines():
            if line.startswith(key_norm):
                return line[len(key_norm) :]
        return os.getenv(key, "")

    def _set_env_value(self, key: str, value: str) -> None:
        key_norm = f"{key}="
        lines = self._read_env_lines()
        updated = False
        for idx, line in enumerate(lines):
            if line.startswith(key_norm):
                lines[idx] = f"{key}={value}"
                updated = True
                break
        if not updated:
            lines.append(f"{key}={value}")
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        self.env_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        os.environ[key] = value

    @staticmethod
    def _to_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        if not text:
            return default
        return text in {"1", "true", "yes", "on", "enabled"}

    def _get_env_bool(self, key: str, default: bool = False) -> bool:
        raw = self._get_env_value(key)
        return self._to_bool(raw, default=default)

    def _get_xianguanjia_settings(self) -> dict[str, Any]:
        app_key = self._get_env_value("XGJ_APP_KEY").strip()
        app_secret = self._get_env_value("XGJ_APP_SECRET").strip()
        merchant_id = self._get_env_value("XGJ_MERCHANT_ID").strip()
        base_url = self._get_env_value("XGJ_BASE_URL").strip() or "https://open.goofish.pro"
        auto_price_enabled = self._get_env_bool("XGJ_AUTO_PRICE_ENABLED", default=True)
        auto_ship_enabled = self._get_env_bool("XGJ_AUTO_SHIP_ENABLED", default=True)
        auto_ship_on_paid = self._get_env_bool("XGJ_AUTO_SHIP_ON_PAID", default=True)
        return {
            "configured": bool(app_key and app_secret),
            "app_key": app_key,
            "app_secret": app_secret,
            "merchant_id": merchant_id,
            "base_url": base_url,
            "auto_price_enabled": auto_price_enabled,
            "auto_ship_enabled": auto_ship_enabled,
            "auto_ship_on_paid": auto_ship_on_paid,
        }

    @staticmethod
    def _mask_secret(value: str) -> str:
        text = str(value or "").strip()
        if len(text) <= 6:
            return "*" * len(text)
        return text[:3] + "*" * (len(text) - 6) + text[-3:]

    def get_xianguanjia_settings(self) -> dict[str, Any]:
        settings = self._get_xianguanjia_settings()
        return {
            "success": True,
            "configured": settings["configured"],
            "app_key": settings["app_key"],
            "app_secret_masked": self._mask_secret(settings["app_secret"]),
            "merchant_id": settings["merchant_id"],
            "base_url": settings["base_url"],
            "auto_price_enabled": settings["auto_price_enabled"],
            "auto_ship_enabled": settings["auto_ship_enabled"],
            "auto_ship_on_paid": settings["auto_ship_on_paid"],
            "callback_url": "/api/orders/callback",
        }

    def save_xianguanjia_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = dict(payload or {})
        updates = {
            "XGJ_APP_KEY": str(data.get("app_key") or self._get_env_value("XGJ_APP_KEY")).strip(),
            "XGJ_APP_SECRET": str(data.get("app_secret") or self._get_env_value("XGJ_APP_SECRET")).strip(),
            "XGJ_MERCHANT_ID": str(data.get("merchant_id") or self._get_env_value("XGJ_MERCHANT_ID")).strip(),
            "XGJ_BASE_URL": str(data.get("base_url") or self._get_env_value("XGJ_BASE_URL")).strip()
            or "https://open.goofish.pro",
            "XGJ_AUTO_PRICE_ENABLED": "1"
            if self._to_bool(data.get("auto_price_enabled"), default=self._get_env_bool("XGJ_AUTO_PRICE_ENABLED", True))
            else "0",
            "XGJ_AUTO_SHIP_ENABLED": "1"
            if self._to_bool(data.get("auto_ship_enabled"), default=self._get_env_bool("XGJ_AUTO_SHIP_ENABLED", True))
            else "0",
            "XGJ_AUTO_SHIP_ON_PAID": "1"
            if self._to_bool(data.get("auto_ship_on_paid"), default=self._get_env_bool("XGJ_AUTO_SHIP_ON_PAID", True))
            else "0",
        }
        for key, value in updates.items():
            self._set_env_value(key, value)

        saved = self.get_xianguanjia_settings()
        saved["message"] = "闲管家设置已更新"
        return saved

    def _xianguanjia_service_config(self) -> dict[str, Any]:
        settings = self._get_xianguanjia_settings()
        return {
            "xianguanjia": {
                "enabled": bool(settings["configured"]),
                "app_key": settings["app_key"],
                "app_secret": settings["app_secret"],
                "merchant_id": settings["merchant_id"] or None,
                "base_url": settings["base_url"],
            }
        }

    @property
    def runtime_config_path(self) -> Path:
        return self.project_root / "config" / "config.yaml"

    def _load_runtime_config(self) -> dict[str, Any]:
        candidate_paths = [self.runtime_config_path, self.project_root / "config" / "config.example.yaml"]
        for path in candidate_paths:
            if not path.exists():
                continue
            try:
                payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                if isinstance(payload, dict):
                    return payload
            except Exception:
                continue
        return {}

    def _save_runtime_config(self, payload: dict[str, Any]) -> None:
        self.runtime_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.runtime_config_path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def get_runtime_config_sections(self) -> dict[str, Any]:
        return {
            "ok": True,
            "sections": [
                {
                    "key": "xianguanjia",
                    "name": "闲管家开放平台",
                    "fields": [
                        {"key": "app_key", "label": "App Key", "type": "text", "required": True},
                        {"key": "app_secret", "label": "App Secret", "type": "password", "required": True},
                        {"key": "merchant_id", "label": "Seller ID / Merchant ID", "type": "text"},
                        {
                            "key": "base_url",
                            "label": "API Base URL",
                            "type": "text",
                            "default": "https://open.goofish.pro",
                        },
                    ],
                },
                {
                    "key": "ai",
                    "name": "AI 服务",
                    "fields": [
                        {
                            "key": "provider",
                            "label": "Provider",
                            "type": "select",
                            "options": [
                                "deepseek",
                                "openai",
                                "aliyun_bailian",
                                "volcengine_ark",
                                "minimax",
                                "zhipu",
                                "claude",
                            ],
                            "default": "deepseek",
                        },
                        {"key": "api_key", "label": "API Key", "type": "password", "required": True},
                        {"key": "base_url", "label": "Base URL", "type": "text"},
                        {"key": "model", "label": "Model", "type": "text"},
                        {"key": "temperature", "label": "Temperature", "type": "number", "default": 0.7},
                    ],
                },
                {
                    "key": "oss",
                    "name": "阿里云 OSS",
                    "fields": [
                        {"key": "access_key_id", "label": "Access Key ID", "type": "text"},
                        {"key": "access_key_secret", "label": "Access Key Secret", "type": "password"},
                        {"key": "bucket", "label": "Bucket", "type": "text"},
                        {"key": "endpoint", "label": "Endpoint", "type": "text"},
                        {"key": "prefix", "label": "Prefix", "type": "text", "default": "xianyu/listing/"},
                        {"key": "custom_domain", "label": "Custom Domain", "type": "text"},
                    ],
                },
                {
                    "key": "messages",
                    "name": "消息自动化",
                    "fields": [
                        {"key": "enabled", "label": "启用自动回复", "type": "toggle", "default": False},
                        {
                            "key": "transport",
                            "label": "消息通道",
                            "type": "select",
                            "options": ["ws", "auto", "dom"],
                            "default": "ws",
                        },
                        {
                            "key": "max_replies_per_run",
                            "label": "单次最大回复数",
                            "type": "number",
                            "default": 10,
                        },
                        {"key": "default_reply", "label": "默认回复", "type": "textarea"},
                        {"key": "virtual_default_reply", "label": "虚拟商品默认回复", "type": "textarea"},
                    ],
                },
            ],
        }

    def get_runtime_config(self) -> dict[str, Any]:
        cfg = get_config()
        messages_cfg = cfg.get_section("messages", {})
        xgj_settings = self._get_xianguanjia_settings()
        return {
            "ok": True,
            "config": {
                "xianguanjia": {
                    "app_key": xgj_settings["app_key"],
                    "app_secret": xgj_settings["app_secret"],
                    "merchant_id": xgj_settings["merchant_id"],
                    "base_url": xgj_settings["base_url"],
                },
                "ai": {
                    "provider": self._get_env_value("AI_PROVIDER").strip() or "deepseek",
                    "api_key": self._get_env_value("AI_API_KEY").strip(),
                    "base_url": self._get_env_value("AI_BASE_URL").strip(),
                    "model": self._get_env_value("AI_MODEL").strip(),
                    "temperature": self._get_env_value("AI_TEMPERATURE").strip() or "0.7",
                },
                "oss": {
                    "access_key_id": self._get_env_value("OSS_ACCESS_KEY_ID").strip(),
                    "access_key_secret": self._get_env_value("OSS_ACCESS_KEY_SECRET").strip(),
                    "bucket": self._get_env_value("OSS_BUCKET").strip(),
                    "endpoint": self._get_env_value("OSS_ENDPOINT").strip(),
                    "prefix": self._get_env_value("OSS_PREFIX").strip() or "xianyu/listing/",
                    "custom_domain": self._get_env_value("OSS_CUSTOM_DOMAIN").strip(),
                },
                "messages": {
                    "enabled": bool(messages_cfg.get("enabled", False)),
                    "transport": str(messages_cfg.get("transport") or "ws"),
                    "max_replies_per_run": int(messages_cfg.get("max_replies_per_run", 10) or 10),
                    "default_reply": str(messages_cfg.get("default_reply") or ""),
                    "virtual_default_reply": str(messages_cfg.get("virtual_default_reply") or ""),
                },
            },
        }

    def save_runtime_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = dict(payload or {})
        env_updates = {
            "XGJ_APP_KEY": str(((data.get("xianguanjia") or {}).get("app_key") or self._get_env_value("XGJ_APP_KEY"))).strip(),
            "XGJ_APP_SECRET": str(((data.get("xianguanjia") or {}).get("app_secret") or self._get_env_value("XGJ_APP_SECRET"))).strip(),
            "XGJ_MERCHANT_ID": str(((data.get("xianguanjia") or {}).get("merchant_id") or self._get_env_value("XGJ_MERCHANT_ID"))).strip(),
            "XGJ_BASE_URL": str(((data.get("xianguanjia") or {}).get("base_url") or self._get_env_value("XGJ_BASE_URL"))).strip()
            or "https://open.goofish.pro",
            "AI_PROVIDER": str(((data.get("ai") or {}).get("provider") or self._get_env_value("AI_PROVIDER"))).strip() or "deepseek",
            "AI_API_KEY": str(((data.get("ai") or {}).get("api_key") or self._get_env_value("AI_API_KEY"))).strip(),
            "AI_BASE_URL": str(((data.get("ai") or {}).get("base_url") or self._get_env_value("AI_BASE_URL"))).strip(),
            "AI_MODEL": str(((data.get("ai") or {}).get("model") or self._get_env_value("AI_MODEL"))).strip(),
            "AI_TEMPERATURE": str(((data.get("ai") or {}).get("temperature") or self._get_env_value("AI_TEMPERATURE"))).strip()
            or "0.7",
            "OSS_ACCESS_KEY_ID": str(((data.get("oss") or {}).get("access_key_id") or self._get_env_value("OSS_ACCESS_KEY_ID"))).strip(),
            "OSS_ACCESS_KEY_SECRET": str(((data.get("oss") or {}).get("access_key_secret") or self._get_env_value("OSS_ACCESS_KEY_SECRET"))).strip(),
            "OSS_BUCKET": str(((data.get("oss") or {}).get("bucket") or self._get_env_value("OSS_BUCKET"))).strip(),
            "OSS_ENDPOINT": str(((data.get("oss") or {}).get("endpoint") or self._get_env_value("OSS_ENDPOINT"))).strip(),
            "OSS_PREFIX": str(((data.get("oss") or {}).get("prefix") or self._get_env_value("OSS_PREFIX"))).strip()
            or "xianyu/listing/",
            "OSS_CUSTOM_DOMAIN": str(((data.get("oss") or {}).get("custom_domain") or self._get_env_value("OSS_CUSTOM_DOMAIN"))).strip(),
        }
        for key, value in env_updates.items():
            self._set_env_value(key, value)

        runtime_cfg = self._load_runtime_config()
        messages_cfg = runtime_cfg.get("messages") if isinstance(runtime_cfg.get("messages"), dict) else {}
        messages_input = data.get("messages") if isinstance(data.get("messages"), dict) else {}
        messages_cfg.update(
            {
                "enabled": self._to_bool(messages_input.get("enabled"), default=bool(messages_cfg.get("enabled", False))),
                "transport": str(messages_input.get("transport") or messages_cfg.get("transport") or "ws").strip().lower() or "ws",
                "max_replies_per_run": max(1, int(messages_input.get("max_replies_per_run") or messages_cfg.get("max_replies_per_run") or 10)),
                "default_reply": str(messages_input.get("default_reply") or messages_cfg.get("default_reply") or "").strip(),
                "virtual_default_reply": str(
                    messages_input.get("virtual_default_reply") or messages_cfg.get("virtual_default_reply") or ""
                ).strip(),
            }
        )
        runtime_cfg["messages"] = messages_cfg
        self._save_runtime_config(runtime_cfg)
        get_config().reload()

        saved = self.get_runtime_config()
        saved["message"] = "配置已更新"
        return saved

    @staticmethod
    def _extract_list_items(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ("list", "items", "rows", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, dict)]
        nested = payload.get("data")
        if isinstance(nested, dict):
            return MimicOps._extract_list_items(nested)
        return []

    @staticmethod
    def _pick_first_value(item: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in item and item.get(key) not in (None, ""):
                return item.get(key)
        return None

    def _open_platform_client(self):
        from src.integrations.xianguanjia.open_platform_client import OpenPlatformClient

        settings = self._get_xianguanjia_settings()
        if not settings["configured"]:
            return None, settings
        client = OpenPlatformClient(
            base_url=str(settings["base_url"]).strip(),
            app_key=str(settings["app_key"]).strip(),
            app_secret=str(settings["app_secret"]).strip(),
            seller_id=str(settings["merchant_id"]).strip() or None,
        )
        return client, settings

    def list_accounts(self) -> dict[str, Any]:
        from src.modules.accounts.service import AccountsService

        service = AccountsService()
        accounts = service.get_accounts(enabled_only=False, mask_sensitive=True)
        health_items = service.get_all_accounts_health()
        health_by_id = {str(item.get("account_id")): item for item in health_items if isinstance(item, dict)}
        current = service.get_current_account() or {}
        current_id = str(current.get("id") or "").strip()
        xgj_configured = bool(self._get_xianguanjia_settings().get("configured"))
        module_status = self.module_console.status(window_minutes=30, limit=5)
        modules = module_status.get("modules") if isinstance(module_status, dict) else {}
        presales_process = modules.get("presales", {}).get("process", {}) if isinstance(modules, dict) else {}
        automation_enabled = bool(presales_process.get("alive", False))

        if not accounts:
            cookie_text = self._get_env_value("XIANYU_COOKIE_1").strip()
            if cookie_text:
                accounts = [
                    {
                        "id": "default",
                        "name": "当前账号",
                        "cookie": self._mask_secret(cookie_text),
                        "enabled": True,
                        "status": "active",
                    }
                ]
                current_id = "default"
                health_by_id["default"] = {
                    "account_id": "default",
                    "health_score": 100,
                    "health": "good",
                    "last_operation": None,
                }

        payload = []
        for item in accounts:
            account_id = str(item.get("id") or "").strip()
            health = health_by_id.get(account_id, {})
            payload.append(
                {
                    "id": account_id,
                    "name": str(item.get("name") or account_id),
                    "cookie": str(item.get("cookie") or ""),
                    "enabled": bool(item.get("enabled", True)),
                    "status": str(item.get("status") or "active"),
                    "current": account_id == current_id,
                    "xgj_configured": xgj_configured,
                    "automation_enabled": automation_enabled,
                    "health_score": int(health.get("health_score", 100) or 100),
                    "health": str(health.get("health") or "good"),
                    "last_operation": health.get("last_operation"),
                }
            )

        return {"ok": True, "accounts": payload}

    def list_xianguanjia_products(
        self,
        *,
        page_no: int = 1,
        page_size: int = 20,
        query: str = "",
    ) -> dict[str, Any]:
        client, settings = self._open_platform_client()
        if client is None:
            return {"ok": False, "error": "闲管家 API 未配置", "settings": settings}

        response = client.list_products({"page_no": page_no, "page_size": page_size})
        if not response.ok:
            return {"ok": False, "error": response.error_message or "商品列表查询失败"}

        raw_data = response.data or {}
        items = self._extract_list_items(raw_data)
        query_text = str(query or "").strip().lower()
        normalized = []
        for item in items:
            product_id = str(self._pick_first_value(item, "product_id", "id", "item_id") or "").strip()
            title = str(self._pick_first_value(item, "title", "item_title", "name") or "").strip()
            if query_text and query_text not in title.lower() and query_text not in product_id.lower():
                continue
            images = item.get("images")
            if not isinstance(images, list):
                images = []
            pic_url = str(
                self._pick_first_value(item, "pic_url", "image", "cover", "cover_image", "main_image") or ""
            ).strip()
            if not pic_url and images:
                pic_url = str(images[0] or "").strip()
            normalized.append(
                {
                    **item,
                    "product_id": product_id,
                    "title": title,
                    "price": self._pick_first_value(item, "price", "sale_price", "amount"),
                    "status": self._pick_first_value(item, "status", "product_status", "item_status"),
                    "stock": self._pick_first_value(item, "stock", "inventory", "quantity"),
                    "view_count": self._pick_first_value(item, "view_count", "views"),
                    "want_count": self._pick_first_value(item, "want_count", "wants"),
                    "pic_url": pic_url,
                    "images": images,
                }
            )

        total = raw_data.get("total") if isinstance(raw_data, dict) else None
        return {
            "ok": True,
            "data": {
                "list": normalized,
                "page_no": page_no,
                "page_size": page_size,
                "total": int(total or len(normalized)),
            },
        }

    def list_xianguanjia_orders(
        self,
        *,
        page_no: int = 1,
        page_size: int = 20,
        order_status: int | None = None,
        query: str = "",
    ) -> dict[str, Any]:
        client, settings = self._open_platform_client()
        if client is None:
            return {"ok": False, "error": "闲管家 API 未配置", "settings": settings}

        payload: dict[str, Any] = {"page_no": page_no, "page_size": page_size}
        if order_status is not None:
            payload["order_status"] = int(order_status)
        response = client.list_orders(payload)
        if not response.ok:
            return {"ok": False, "error": response.error_message or "订单列表查询失败"}

        raw_data = response.data or {}
        items = self._extract_list_items(raw_data)
        query_text = str(query or "").strip().lower()
        normalized = []
        for item in items:
            order_id = str(self._pick_first_value(item, "order_id", "tid", "biz_order_id") or "").strip()
            title = str(self._pick_first_value(item, "title", "item_title", "product_title") or "").strip()
            buyer_name = str(self._pick_first_value(item, "buyer_name", "buyer_nick", "buyerNick") or "").strip()
            if query_text and all(query_text not in value.lower() for value in (order_id, title, buyer_name)):
                continue
            normalized.append(
                {
                    **item,
                    "order_id": order_id,
                    "title": title,
                    "buyer_name": buyer_name,
                    "status": self._pick_first_value(item, "status", "order_status"),
                    "total_fee": self._pick_first_value(item, "total_fee", "price", "amount"),
                    "create_time": self._pick_first_value(item, "create_time", "created_at", "gmt_create"),
                    "pic_url": self._pick_first_value(item, "pic_url", "image", "item_pic"),
                }
            )

        total = raw_data.get("total") if isinstance(raw_data, dict) else None
        return {
            "ok": True,
            "data": {
                "list": normalized,
                "page_no": page_no,
                "page_size": page_size,
                "total": int(total or len(normalized)),
            },
        }

    def publish_xianguanjia_product(self, payload: dict[str, Any]) -> dict[str, Any]:
        client, settings = self._open_platform_client()
        if client is None:
            return {"ok": False, "error": "闲管家 API 未配置", "settings": settings}
        product_id = str(payload.get("product_id") or "").strip()
        if not product_id:
            return {"ok": False, "error": "缺少商品 ID"}
        response = client.publish_product({"product_id": product_id})
        return {"ok": bool(response.ok), "data": response.data, "error": response.error_message}

    def unpublish_xianguanjia_product(self, payload: dict[str, Any]) -> dict[str, Any]:
        client, settings = self._open_platform_client()
        if client is None:
            return {"ok": False, "error": "闲管家 API 未配置", "settings": settings}
        product_id = str(payload.get("product_id") or "").strip()
        if not product_id:
            return {"ok": False, "error": "缺少商品 ID"}
        response = client.unpublish_product({"product_id": product_id})
        return {"ok": bool(response.ok), "data": response.data, "error": response.error_message}

    def modify_xianguanjia_order_price(self, payload: dict[str, Any]) -> dict[str, Any]:
        client, settings = self._open_platform_client()
        if client is None:
            return {"ok": False, "error": "闲管家 API 未配置", "settings": settings}
        order_id = str(payload.get("order_id") or "").strip()
        if not order_id:
            return {"ok": False, "error": "缺少订单号"}
        try:
            total_fee = int(payload.get("total_fee"))
        except Exception:
            return {"ok": False, "error": "缺少有效的改价金额（分）"}
        response = client.modify_order_price({"order_id": order_id, "total_fee": total_fee})
        return {"ok": bool(response.ok), "data": response.data, "error": response.error_message}

    def deliver_xianguanjia_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        client, settings = self._open_platform_client()
        if client is None:
            return {"ok": False, "error": "闲管家 API 未配置", "settings": settings}
        order_id = str(payload.get("order_id") or "").strip()
        if not order_id:
            return {"ok": False, "error": "缺少订单号"}
        response = client.delivery_order({"order_id": order_id})
        return {"ok": bool(response.ok), "data": response.data, "error": response.error_message}

    def read_generated_image(self, raw_path: str) -> tuple[bytes, str]:
        text = str(raw_path or "").strip()
        if not text:
            raise FileNotFoundError("图片路径为空")
        candidate = Path(text)
        if not candidate.is_absolute():
            candidate = (self.project_root / candidate).resolve()
        else:
            candidate = candidate.resolve()
        allowed_root = (self.project_root / "data" / "generated_images").resolve()
        if not str(candidate).startswith(str(allowed_root)):
            raise PermissionError("不允许访问该图片路径")
        if not candidate.is_file():
            raise FileNotFoundError("图片不存在")
        content_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(candidate.suffix.lower(), "application/octet-stream")
        return candidate.read_bytes(), content_type

    def retry_xianguanjia_delivery(self, payload: dict[str, Any]) -> dict[str, Any]:
        from src.modules.orders.service import OrderFulfillmentService

        settings = self._get_xianguanjia_settings()
        if not settings["configured"]:
            return _error_payload("闲管家凭证未配置", code="XGJ_NOT_CONFIGURED")

        data = dict(payload or {})
        shipping_info = data.get("shipping_info")
        if not isinstance(shipping_info, dict):
            shipping_info = {}

        for field in (
            "order_no",
            "waybill_no",
            "express_code",
            "express_name",
            "ship_name",
            "ship_mobile",
            "ship_province",
            "ship_city",
            "ship_area",
            "ship_address",
        ):
            if field in data and data.get(field) not in (None, ""):
                shipping_info[field] = data.get(field)

        order_id = str(data.get("order_id") or data.get("order_no") or "").strip()
        if not order_id:
            return _error_payload("缺少订单号", code="MISSING_ORDER_ID")

        service = OrderFulfillmentService(
            db_path=str(self.project_root / "data" / "orders.db"),
            config=self._xianguanjia_service_config(),
        )
        try:
            result = service.deliver(
                order_id=order_id,
                dry_run=self._to_bool(data.get("dry_run"), default=False),
                shipping_info=shipping_info or None,
            )
        except Exception as exc:
            return _error_payload(f"发货重试失败: {exc}", code="XGJ_RETRY_SHIP_FAILED")
        return {"success": True, **result}

    def retry_xianguanjia_price(self, payload: dict[str, Any]) -> dict[str, Any]:
        from src.modules.operations.service import OperationsService

        settings = self._get_xianguanjia_settings()
        if not settings["configured"]:
            return _error_payload("闲管家凭证未配置", code="XGJ_NOT_CONFIGURED")

        data = dict(payload or {})
        product_id = str(data.get("product_id") or data.get("productId") or "").strip()
        if not product_id:
            return _error_payload("缺少商品 ID", code="MISSING_PRODUCT_ID")

        try:
            new_price = float(data.get("new_price"))
        except Exception:
            return _error_payload("缺少有效的新价格", code="INVALID_NEW_PRICE")

        original_price_raw = data.get("original_price")
        original_price = None
        if original_price_raw not in (None, ""):
            try:
                original_price = float(original_price_raw)
            except Exception:
                return _error_payload("原价格式无效", code="INVALID_ORIGINAL_PRICE")

        service = OperationsService(config=self._xianguanjia_service_config())
        try:
            result = _run_async(service.update_price(product_id, new_price, original_price))
        except Exception as exc:
            return _error_payload(f"改价重试失败: {exc}", code="XGJ_RETRY_PRICE_FAILED")
        return {"success": bool(result.get("success")), **result}

    def handle_order_callback(self, payload: dict[str, Any]) -> dict[str, Any]:
        from src.modules.orders.service import OrderFulfillmentService

        data = dict(payload or {})
        settings = self._get_xianguanjia_settings()
        service = OrderFulfillmentService(
            db_path=str(self.project_root / "data" / "orders.db"),
            config=self._xianguanjia_service_config(),
        )
        try:
            result = service.process_callback(
                data,
                dry_run=self._to_bool(data.get("dry_run"), default=False),
                auto_deliver=bool(
                    settings["configured"] and settings["auto_ship_enabled"] and settings["auto_ship_on_paid"]
                ),
            )
        except Exception as exc:
            return _error_payload(f"回调处理失败: {exc}", code="XGJ_CALLBACK_FAILED")

        result["settings"] = {
            "configured": settings["configured"],
            "auto_ship_enabled": settings["auto_ship_enabled"],
            "auto_ship_on_paid": settings["auto_ship_on_paid"],
        }
        return result

    def _virtual_goods_service(self) -> VirtualGoodsService:
        return VirtualGoodsService(
            db_path=str(self.project_root / "data" / "orders.db"),
            config=self._xianguanjia_service_config(),
        )

    @staticmethod
    def _vg_service_metrics(result: dict[str, Any]) -> dict[str, Any]:
        metrics = result.get("metrics")
        if isinstance(metrics, dict):
            return metrics
        data = result.get("data")
        if isinstance(data, dict):
            return data
        return {}

    @staticmethod
    def _vg_int(metrics: dict[str, Any], key: str) -> int:
        try:
            return int(metrics.get(key) or 0)
        except Exception:
            return 0

    def _build_virtual_goods_dashboard_panels(
        self,
        dashboard_result: dict[str, Any],
        manual_orders: list[dict[str, Any]],
        funnel_result: dict[str, Any] | None,
        exception_result: dict[str, Any] | None,
        fulfillment_result: dict[str, Any] | None,
        product_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        metrics = self._vg_service_metrics(dashboard_result)
        errors = dashboard_result.get("errors") if isinstance(dashboard_result.get("errors"), list) else []

        _total_orders = self._vg_int(metrics, "total_orders")
        _total_callbacks = self._vg_int(metrics, "total_callbacks")
        _pending_callbacks = self._vg_int(metrics, "pending_callbacks")
        _processed_callbacks = self._vg_int(metrics, "processed_callbacks")
        failed_callbacks = self._vg_int(metrics, "failed_callbacks")
        timeout_backlog = self._vg_int(metrics, "timeout_backlog")
        unknown_event_kind = self._vg_int(metrics, "unknown_event_kind")
        timeout_seconds = self._vg_int(metrics, "timeout_seconds")

        funnel_data = (
            funnel_result.get("data")
            if isinstance(funnel_result, dict) and isinstance(funnel_result.get("data"), dict)
            else {}
        )
        funnel_stage_totals = (
            funnel_data.get("stage_totals") if isinstance(funnel_data.get("stage_totals"), dict) else {}
        )

        exception_data = (
            exception_result.get("data")
            if isinstance(exception_result, dict) and isinstance(exception_result.get("data"), dict)
            else {}
        )
        exception_items = exception_data.get("items") if isinstance(exception_data.get("items"), list) else []

        fulfillment_data = (
            fulfillment_result.get("data")
            if isinstance(fulfillment_result, dict) and isinstance(fulfillment_result.get("data"), dict)
            else {}
        )
        fulfillment_summary = (
            fulfillment_data.get("summary") if isinstance(fulfillment_data.get("summary"), dict) else {}
        )

        product_data = (
            product_result.get("data")
            if isinstance(product_result, dict) and isinstance(product_result.get("data"), dict)
            else {}
        )
        product_summary_raw = product_data.get("summary") if isinstance(product_data.get("summary"), dict) else {}

        stable_product_fields = [
            "exposure_count",
            "paid_order_count",
            "paid_amount_cents",
            "refund_order_count",
            "exception_count",
            "manual_takeover_count",
            "conversion_rate_pct",
        ]
        product_summary: dict[str, Any] = {}
        product_field_state: dict[str, str] = {}
        for key in stable_product_fields:
            if key in product_summary_raw:
                product_summary[key] = product_summary_raw.get(key)
                product_field_state[key] = "available"
            else:
                product_summary[key] = None
                product_field_state[key] = "placeholder"

        exception_pool: list[dict[str, Any]] = [x for x in exception_items if isinstance(x, dict)]
        if unknown_event_kind > 0 and not any(
            str(x.get("type") or "").upper() == "UNKNOWN_EVENT_KIND" for x in exception_pool
        ):
            exception_pool.insert(
                0,
                {
                    "priority": "P0",
                    "type": "UNKNOWN_EVENT_KIND",
                    "count": unknown_event_kind,
                    "summary": "检测到未知事件类型回调，需人工排查映射。",
                },
            )
        if failed_callbacks > 0 and not any(
            str(x.get("type") or "").upper() == "FAILED_CALLBACK" for x in exception_pool
        ):
            exception_pool.append(
                {
                    "priority": "P1",
                    "type": "FAILED_CALLBACK",
                    "count": failed_callbacks,
                    "summary": "回调处理失败，建议优先重放失败回调。",
                }
            )
        if timeout_backlog > 0 and not any(
            str(x.get("type") or "").upper() == "TIMEOUT_BACKLOG" for x in exception_pool
        ):
            exception_pool.append(
                {
                    "priority": "P1",
                    "type": "TIMEOUT_BACKLOG",
                    "count": timeout_backlog,
                    "summary": f"存在超时未处理回调（超时阈值 {timeout_seconds}s）。",
                }
            )
        for err in errors:
            if not isinstance(err, dict):
                continue
            if str(err.get("code") or "").upper() == "UNKNOWN_EVENT_KIND" and unknown_event_kind <= 0:
                exception_pool.append(
                    {
                        "priority": "P0",
                        "type": "UNKNOWN_EVENT_KIND",
                        "count": int(err.get("count") or 1),
                        "summary": str(err.get("message") or "unknown event_kind detected"),
                    }
                )

        stage_totals_int = {str(k): self._vg_int(funnel_stage_totals, str(k)) for k in funnel_stage_totals.keys()}
        funnel_total = sum(stage_totals_int.values())

        return {
            "operations_funnel_overview": {
                "stage_totals": stage_totals_int,
                "total_metric_count": int(
                    ((funnel_result.get("metrics") or {}).get("total_metric_count") or funnel_total)
                    if isinstance(funnel_result, dict)
                    else funnel_total
                ),
                "source": str((funnel_result.get("metrics") or {}).get("source") or "ops_funnel_stage_daily")
                if isinstance(funnel_result, dict)
                else "ops_funnel_stage_daily",
            },
            "exception_priority_pool": {
                "total_items": len(exception_pool),
                "items": exception_pool,
            },
            "fulfillment_efficiency": {
                "fulfilled_orders": self._vg_int(fulfillment_summary, "fulfilled_orders"),
                "failed_orders": self._vg_int(fulfillment_summary, "failed_orders"),
                "fulfillment_rate_pct": float(
                    fulfillment_summary["fulfillment_rate_pct"]
                    if "fulfillment_rate_pct" in fulfillment_summary
                    and fulfillment_summary["fulfillment_rate_pct"] is not None
                    else 0.0
                ),
                "failure_rate_pct": float(
                    fulfillment_summary["failure_rate_pct"]
                    if "failure_rate_pct" in fulfillment_summary and fulfillment_summary["failure_rate_pct"] is not None
                    else 0.0
                ),
                "avg_fulfillment_seconds": float(
                    fulfillment_summary["avg_fulfillment_seconds"]
                    if "avg_fulfillment_seconds" in fulfillment_summary
                    and fulfillment_summary["avg_fulfillment_seconds"] is not None
                    else 0.0
                ),
                "p95_fulfillment_seconds": float(
                    fulfillment_summary["p95_fulfillment_seconds"]
                    if "p95_fulfillment_seconds" in fulfillment_summary
                    and fulfillment_summary["p95_fulfillment_seconds"] is not None
                    else 0.0
                ),
            },
            "product_operations": {
                "summary": product_summary,
                "field_state": product_field_state,
                "manual_takeover_count": int(product_summary.get("manual_takeover_count") or len(manual_orders)),
                "manual_takeover_orders": [
                    {
                        "xianyu_order_id": str(item.get("xianyu_order_id") or ""),
                        "fulfillment_status": str(item.get("fulfillment_status") or ""),
                        "reason": str(item.get("reason") or ""),
                    }
                    for item in manual_orders
                ],
            },
            "drill_down": {
                "inspect_endpoint": "/api/virtual-goods/inspect-order",
                "query_key": "order_id",
                "message": "输入订单号查看成品化明细视图。",
                "actions": [
                    {"name": "claim_callback", "enabled": False, "reason": "Dashboard 为只读视图"},
                    {"name": "replay_callback", "enabled": False, "reason": "Dashboard 为只读视图"},
                    {"name": "manual_takeover", "enabled": False, "reason": "Dashboard 为只读视图"},
                ],
            },
        }

    def get_virtual_goods_metrics(self) -> dict[str, Any]:
        service = self._virtual_goods_service()
        query = getattr(service, "get_dashboard_metrics", None)
        if not callable(query):
            return _error_payload(
                "virtual_goods service query `get_dashboard_metrics` is unavailable",
                code="VG_QUERY_NOT_AVAILABLE",
            )

        result = query()
        if not isinstance(result, dict):
            return _error_payload("virtual_goods metrics payload invalid", code="VG_METRICS_INVALID")
        legacy_metrics_payload = not any(
            key in result for key in ("ok", "action", "code", "message", "data", "metrics", "errors", "ts")
        )

        manual_query = getattr(service, "list_manual_takeover_orders", None)
        manual_orders: list[dict[str, Any]] = []
        if callable(manual_query):
            raw_manual = manual_query()
            if isinstance(raw_manual, dict):
                raw_manual = raw_manual.get("data", {}).get("items", [])
            if isinstance(raw_manual, list):
                manual_orders = [x for x in raw_manual if isinstance(x, dict)]

        funnel_result = None
        if callable(getattr(service, "get_funnel_metrics", None)):
            funnel_result = service.get_funnel_metrics(limit=500)

        exception_result = None
        if callable(getattr(service, "list_priority_exceptions", None)):
            exception_result = service.list_priority_exceptions(limit=100, status="open")

        fulfillment_result = None
        if callable(getattr(service, "get_fulfillment_efficiency_metrics", None)):
            fulfillment_result = service.get_fulfillment_efficiency_metrics(limit=500)

        product_result = None
        if callable(getattr(service, "get_product_operation_metrics", None)):
            product_result = service.get_product_operation_metrics(limit=500)

        payload = {
            "success": bool(result.get("ok", True)),
            "module": "virtual_goods",
            "service_response": {
                "ok": bool(result.get("ok", True)),
                "action": str(result.get("action") or "get_dashboard_metrics"),
                "code": str(result.get("code") or "OK"),
                "message": str(result.get("message") or ""),
                "ts": str(result.get("ts") or ""),
            },
            "dashboard_panels": self._build_virtual_goods_dashboard_panels(
                result,
                manual_orders,
                funnel_result,
                exception_result,
                fulfillment_result,
                product_result,
            ),
            "manual_takeover_count": len(manual_orders),
            "generated_at": _now_iso(),
        }
        if legacy_metrics_payload:
            payload["metrics"] = dict(result)
        return payload

    def get_dashboard_readonly_aggregate(self) -> dict[str, Any]:
        """Dashboard 只读聚合接口（运营视图）。"""
        payload = self.get_virtual_goods_metrics()
        if not payload.get("success"):
            return payload

        panels = payload.get("dashboard_panels") if isinstance(payload.get("dashboard_panels"), dict) else {}
        return {
            "success": True,
            "module": "virtual_goods",
            "readonly": True,
            "service_response": payload.get("service_response", {}),
            "sections": {
                "operations_funnel_overview": panels.get("operations_funnel_overview", {}),
                "exception_priority_pool": panels.get("exception_priority_pool", {}),
                "fulfillment_efficiency": panels.get("fulfillment_efficiency", {}),
                "product_operations": panels.get("product_operations", {}),
                "drill_down": panels.get("drill_down", {}),
            },
            "generated_at": payload.get("generated_at") or _now_iso(),
        }

    def inspect_virtual_goods_order(self, order_id: str) -> dict[str, Any]:
        oid = str(order_id or "").strip()
        if not oid:
            return _error_payload("Missing order_id", code="MISSING_ORDER_ID")

        service = self._virtual_goods_service()
        inspect = getattr(service, "inspect_order", None)
        if not callable(inspect):
            return _error_payload(
                "virtual_goods service query `inspect_order` is unavailable",
                code="VG_QUERY_NOT_AVAILABLE",
            )

        try:
            result = inspect(oid)
        except TypeError:
            result = inspect(order_id=oid)
        if not isinstance(result, dict):
            return _error_payload("virtual_goods inspect payload invalid", code="VG_INSPECT_INVALID")

        data = result.get("data") if isinstance(result.get("data"), dict) else result
        order = data.get("order") if isinstance(data.get("order"), dict) else {}
        callbacks_raw = data.get("callbacks") if isinstance(data.get("callbacks"), list) else []
        exception_pool_raw = (
            data.get("exception_priority_pool") if isinstance(data.get("exception_priority_pool"), dict) else {}
        )
        exception_items_raw = (
            exception_pool_raw.get("items") if isinstance(exception_pool_raw.get("items"), list) else []
        )

        callbacks_view = [
            {
                "callback_id": int(cb.get("id") or 0),
                "external_event_id": str(cb.get("external_event_id") or ""),
                "dedupe_key": str(cb.get("dedupe_key") or ""),
                "event_kind": str(cb.get("event_kind") or ""),
                "verify_passed": bool(cb.get("verify_passed")),
                "processed": bool(cb.get("processed")),
                "attempt_count": int(cb.get("attempt_count") or 0),
                "last_process_error": str(cb.get("last_process_error") or ""),
                "created_at": str(cb.get("created_at") or ""),
                "processed_at": str(cb.get("processed_at") or ""),
            }
            for cb in callbacks_raw
            if isinstance(cb, dict)
        ]
        unknown_count = sum(
            1
            for cb in callbacks_view
            if str(cb.get("event_kind") or "").strip().lower() in {"unknown", "unknown_event_kind"}
        )

        callback_chain = [
            {
                "step": idx + 1,
                "event_kind": item.get("event_kind"),
                "verify_passed": item.get("verify_passed"),
                "processed": item.get("processed"),
                "created_at": item.get("created_at"),
                "processed_at": item.get("processed_at"),
            }
            for idx, item in enumerate(callbacks_view)
        ]
        claim_replay_trace = [
            {
                "callback_id": item.get("callback_id"),
                "external_event_id": item.get("external_event_id"),
                "dedupe_key": item.get("dedupe_key"),
                "attempt_count": item.get("attempt_count"),
                "processed": item.get("processed"),
            }
            for item in callbacks_view
        ]
        recent_errors = [
            {
                "callback_id": item.get("callback_id"),
                "error": item.get("last_process_error"),
                "event_kind": item.get("event_kind"),
                "at": item.get("processed_at") or item.get("created_at"),
            }
            for item in callbacks_view
            if str(item.get("last_process_error") or "").strip()
        ][:5]

        exception_items = [x for x in exception_items_raw if isinstance(x, dict)]
        if unknown_count > 0 and not any(
            str(x.get("type") or "").upper() == "UNKNOWN_EVENT_KIND" for x in exception_items
        ):
            exception_items.insert(
                0,
                {
                    "priority": "P0",
                    "type": "UNKNOWN_EVENT_KIND",
                    "count": unknown_count,
                    "summary": "该订单存在 unknown event_kind 回调，已纳入异常池。",
                },
            )

        inspect_payload = {
            "order": order,
            "callbacks": callbacks_raw,
        }
        return {
            "success": bool(result.get("ok", True)),
            "module": "virtual_goods",
            "order_id": oid,
            "inspect": inspect_payload,
            "service_response": {
                "ok": bool(result.get("ok", True)),
                "action": str(result.get("action") or "inspect_order"),
                "code": str(result.get("code") or "OK"),
                "message": str(result.get("message") or ""),
                "ts": str(result.get("ts") or ""),
            },
            "drill_down_view": {
                "order": {
                    "xianyu_order_id": str(order.get("xianyu_order_id") or oid),
                    "order_status": str(order.get("order_status") or ""),
                    "fulfillment_status": str(order.get("fulfillment_status") or ""),
                    "updated_at": str(order.get("updated_at") or ""),
                },
                "current_status": {
                    "xianyu_order_id": str(order.get("xianyu_order_id") or oid),
                    "order_status": str(order.get("order_status") or ""),
                    "fulfillment_status": str(order.get("fulfillment_status") or ""),
                    "updated_at": str(order.get("updated_at") or ""),
                },
                "manual_takeover": {
                    "enabled": bool(order.get("manual_takeover")),
                    "reason": str(order.get("last_error") or ""),
                },
                "callback_chain": callback_chain,
                "claim_replay_trace": claim_replay_trace,
                "recent_errors": recent_errors,
                "exception_priority_pool": {
                    "total_items": len(exception_items),
                    "items": exception_items,
                },
                "actions": [
                    {"name": "claim_callback", "enabled": False, "reason": "只读视图，不支持执行动作"},
                    {"name": "replay_callback", "enabled": False, "reason": "只读视图，不支持执行动作"},
                    {"name": "manual_takeover", "enabled": False, "reason": "只读视图，不支持执行动作"},
                ],
            },
        }

    def get_cookie(self) -> dict[str, Any]:
        cookie = self._get_env_value("XIANYU_COOKIE_1").strip()
        return {
            "success": bool(cookie),
            "cookie": cookie,
            "length": len(cookie),
        }

    @staticmethod
    def _cookie_fingerprint(cookie_text: str) -> str:
        raw = str(cookie_text or "").strip()
        if not raw:
            return ""
        return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]

    @classmethod
    def _cookie_pairs_to_text(cls, pairs: list[tuple[str, str]]) -> tuple[str, int]:
        items: list[str] = []
        seen: set[str] = set()
        for name, value in pairs:
            key = str(name or "").strip()
            val = str(value or "").strip()
            if not key or not val:
                continue
            if not cls._COOKIE_NAME_RE.fullmatch(key):
                continue
            if key in seen:
                continue
            seen.add(key)
            items.append(f"{key}={val}")
        return "; ".join(items), len(items)

    @classmethod
    def _extract_cookie_pairs_from_json(cls, raw_text: str) -> list[tuple[str, str]]:
        text = str(raw_text or "").strip()
        if not text:
            return []
        try:
            payload = json.loads(text)
        except Exception:
            return []

        pairs: list[tuple[str, str]] = []

        def _collect(items: Any) -> None:
            if not isinstance(items, list):
                return
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = item.get("name") or item.get("key")
                value = item.get("value")
                if name is None or value is None:
                    continue
                pairs.append((str(name), str(value)))

        if isinstance(payload, list):
            _collect(payload)
        elif isinstance(payload, dict):
            if "name" in payload and "value" in payload:
                pairs.append((str(payload.get("name")), str(payload.get("value"))))
            _collect(payload.get("cookies"))
            _collect(payload.get("items"))

        return pairs

    @classmethod
    def _is_allowed_cookie_domain(cls, domain: str) -> bool:
        value = str(domain or "").strip().lower().lstrip(".")
        if not value:
            return True
        return any(value.endswith(allowed) for allowed in cls._COOKIE_DOMAIN_ALLOWLIST)

    @classmethod
    def _extract_cookie_pairs_from_header(cls, raw_text: str) -> list[tuple[str, str]]:
        text = str(raw_text or "").replace("\ufeff", "").replace("\x00", "").strip()
        if not text:
            return []
        text = re.sub(r"^\s*cookie\s*:\s*", "", text, flags=re.IGNORECASE)
        parts = re.split(r";|\n", text)
        pairs: list[tuple[str, str]] = []
        for part in parts:
            seg = str(part or "").strip()
            if not seg or "=" not in seg:
                continue
            key, value = seg.split("=", 1)
            pairs.append((key.strip(), value.strip()))
        return pairs

    @classmethod
    def _extract_cookie_pairs_from_lines(cls, raw_text: str) -> list[tuple[str, str]]:
        text = str(raw_text or "").replace("\ufeff", "").replace("\x00", "")
        pairs: list[tuple[str, str]] = []
        for line in text.splitlines():
            s = str(line or "").strip()
            if not s or s.startswith("#"):
                continue

            # Netscape cookies.txt: domain, flag, path, secure, expiry, name, value
            if "\t" in s:
                cols = [c.strip() for c in s.split("\t") if c.strip()]
                if len(cols) >= 7:
                    if cls._is_allowed_cookie_domain(cols[0]):
                        pairs.append((cols[5], cols[6]))
                    continue
                if len(cols) >= 2 and cls._COOKIE_NAME_RE.fullmatch(cols[0]):
                    # DevTools 表格常见格式：name value domain ...
                    if len(cols) >= 3 and not cls._is_allowed_cookie_domain(cols[2]):
                        continue
                    pairs.append((cols[0], cols[1]))
                    continue

            cols = [c.strip() for c in s.split() if c.strip()]
            if len(cols) >= 2 and cls._COOKIE_NAME_RE.fullmatch(cols[0]):
                pairs.append((cols[0], cols[1]))
                continue

            if "=" in s:
                key, value = s.split("=", 1)
                pairs.append((key.strip(), value.strip()))
        return pairs

    @classmethod
    def parse_cookie_text(cls, text: str) -> dict[str, Any]:
        raw = str(text or "").strip()
        if not raw:
            return {"success": False, "error": "Cookie string cannot be empty"}

        candidates: list[dict[str, Any]] = []
        for source, extractor in (
            ("json", cls._extract_cookie_pairs_from_json),
            ("header", cls._extract_cookie_pairs_from_header),
            ("table_or_netscape", cls._extract_cookie_pairs_from_lines),
        ):
            cookie_text, count = cls._cookie_pairs_to_text(extractor(raw))
            if count > 0 and cookie_text:
                candidates.append({"format": source, "cookie": cookie_text, "count": count})

        if not candidates:
            return {
                "success": False,
                "error": "Unable to parse cookie text. Please use header/json/cookies.txt format.",
            }

        candidates.sort(key=lambda x: (int(x.get("count", 0)), x.get("format") == "header"), reverse=True)
        best = candidates[0]
        cookie_text = str(best["cookie"])
        count = int(best["count"])
        missing_required = [k for k in cls._COOKIE_REQUIRED_KEYS if f"{k}=" not in cookie_text]
        return {
            "success": True,
            "cookie": cookie_text,
            "length": len(cookie_text),
            "cookie_items": count,
            "detected_format": str(best["format"]),
            "missing_required": missing_required,
        }

    def _recovery_stage_label(self, stage: str) -> str:
        mapping = {
            "healthy": "链路正常",
            "token_error": "鉴权异常",
            "waiting_cookie_update": "等待更新 Cookie",
            "waiting_reconnect": "等待重连",
            "recover_triggered": "已触发自动恢复",
            "inactive": "服务未运行",
            "monitoring": "监控中",
        }
        key = str(stage or "").strip().lower()
        return mapping.get(key, "状态未知")

    def _recovery_advice(self, stage: str, token_error: str | None = None) -> str:
        s = str(stage or "").strip().lower()
        t = str(token_error or "").strip().upper()
        if s == "recover_triggered":
            return "已触发售前恢复，建议等待 5-20 秒后刷新状态。"
        if s == "waiting_reconnect":
            return "Cookie 已更新但尚未连通，可点击“售前一键恢复”立即重试。"
        if s == "waiting_cookie_update":
            if t == "FAIL_SYS_USER_VALIDATE":
                return "请在闲鱼网页重新登录后导出最新 Cookie，再执行“售前一键恢复”。"
            return "请更新 Cookie 后重试恢复。"
        if s == "token_error":
            if t == "WS_HTTP_400":
                return "连接通道异常，请先点“售前一键恢复”；若持续失败再更新 Cookie。"
            return "存在鉴权错误，建议更新 Cookie 后重连。"
        if s == "inactive":
            return "服务未运行，请先在首页启动服务。"
        if s == "healthy":
            return "当前链路可用，可正常自动回复。"
        return "监控中，请刷新状态查看最新结果。"

    def _trigger_presales_recover_after_cookie_update(self, cookie_text: str) -> dict[str, Any]:
        cookie_fp = self._cookie_fingerprint(cookie_text)
        if not cookie_fp:
            return {"triggered": False, "message": "cookie_empty"}

        result = self.module_console.control(action="recover", target="presales")
        has_error = bool(result.get("error")) if isinstance(result, dict) else True
        now = _now_iso()
        with self._recover_lock:
            self._last_auto_recover_cookie_fp = cookie_fp
            self._last_auto_recover_at = now
            self._last_auto_recover_result = result if isinstance(result, dict) else {}
            self._last_cookie_fp = cookie_fp
        return {
            "triggered": not has_error,
            "result": result,
            "at": now,
            "message": "recover_ok" if not has_error else "recover_failed",
        }

    def update_cookie(self, cookie: str, *, auto_recover: bool = False) -> dict[str, Any]:
        parsed = self.parse_cookie_text(str(cookie or ""))
        if not parsed.get("success"):
            return parsed
        cookie_text = str(parsed.get("cookie") or "").strip()
        if not cookie_text:
            return {"success": False, "error": "Cookie string cannot be empty"}
        self._set_env_value("XIANYU_COOKIE_1", cookie_text)
        diagnosis = self.diagnose_cookie(cookie_text)
        payload: dict[str, Any] = {
            "success": True,
            "message": "Cookie updated",
            "length": len(cookie_text),
            "cookie_items": int(parsed.get("cookie_items", 0) or 0),
            "detected_format": str(parsed.get("detected_format") or "header"),
            "missing_required": parsed.get("missing_required", []),
            "cookie_grade": diagnosis.get("grade", "未知"),
            "cookie_actions": diagnosis.get("actions", []),
            "cookie_diagnosis": diagnosis,
        }
        should_recover = auto_recover and str(diagnosis.get("grade") or "") != "不可用"
        if should_recover:
            recover = self._trigger_presales_recover_after_cookie_update(cookie_text)
            payload["auto_recover"] = recover
            if recover.get("triggered"):
                payload["message"] = "Cookie updated and presales recovery triggered"
            else:
                payload["message"] = "Cookie updated, but presales recovery failed"
        return payload

    @classmethod
    def _cookie_domain_filter_stats(cls, raw_text: str) -> dict[str, Any]:
        text = str(raw_text or "").replace("\ufeff", "").replace("\x00", "")
        checked = 0
        rejected = 0
        samples: list[str] = []

        def _check_domain(domain: str) -> None:
            nonlocal checked, rejected
            dom = str(domain or "").strip().lower()
            if not dom:
                return
            checked += 1
            if not cls._is_allowed_cookie_domain(dom):
                rejected += 1
                if len(samples) < 5:
                    samples.append(dom)

        # 文本行（Netscape / 表格）
        for line in text.splitlines():
            s = str(line or "").strip()
            if not s or s.startswith("#"):
                continue
            if "\t" not in s:
                continue
            cols = [c.strip() for c in s.split("\t") if c.strip()]
            if len(cols) >= 7:
                _check_domain(cols[0])
            elif len(cols) >= 3:
                _check_domain(cols[2])

        # JSON 结构中的 domain 字段
        try:
            payload = json.loads(text)
        except Exception:
            payload = None
        if payload is not None:
            queue: list[Any] = [payload]
            while queue:
                item = queue.pop()
                if isinstance(item, dict):
                    if "domain" in item:
                        _check_domain(str(item.get("domain") or ""))
                    for v in item.values():
                        if isinstance(v, (dict, list)):
                            queue.append(v)
                elif isinstance(item, list):
                    queue.extend(item)

        return {
            "allowlist": list(cls._COOKIE_DOMAIN_ALLOWLIST),
            "checked": checked,
            "rejected": rejected,
            "applied": True,
            "rejected_samples": samples,
        }

    def diagnose_cookie(self, cookie_text: str) -> dict[str, Any]:
        raw = str(cookie_text or "").strip()
        if not raw:
            return {
                "success": False,
                "grade": "不可用",
                "error": "Cookie text is empty",
                "actions": ["请先粘贴 Cookie 文本，或上传插件导出的 cookies 文件。"],
            }

        parsed = self.parse_cookie_text(raw)
        domain_filter = self._cookie_domain_filter_stats(raw)
        if not parsed.get("success"):
            return {
                "success": False,
                "grade": "不可用",
                "error": str(parsed.get("error") or "解析失败"),
                "domain_filter": domain_filter,
                "actions": [
                    "请使用 headers/json/cookies.txt 任一格式重试。",
                    "建议在登录闲鱼后立即导出 Cookie，再上传。",
                ],
            }

        normalized = str(parsed.get("cookie") or "")
        cookie_map = {k: v for k, v in self._extract_cookie_pairs_from_header(normalized)}
        required_all = [*list(self._COOKIE_REQUIRED_KEYS), "_m_h5_tk", "_m_h5_tk_enc"]
        required_present = [k for k in required_all if k in cookie_map]
        required_missing = [k for k in required_all if k not in cookie_map]
        recommended_present = [k for k in self._COOKIE_RECOMMENDED_KEYS if k in cookie_map]
        recommended_missing = [k for k in self._COOKIE_RECOMMENDED_KEYS if k not in cookie_map]
        critical_missing = [k for k in self._COOKIE_REQUIRED_KEYS if k in required_missing]
        session_missing = [k for k in ("_m_h5_tk", "_m_h5_tk_enc") if k in required_missing]

        length = int(parsed.get("length", 0) or 0)
        cookie_items = int(parsed.get("cookie_items", 0) or 0)
        grade = "可用"
        if critical_missing or cookie_items < 4:
            grade = "不可用"
        elif session_missing or length < 80:
            grade = "高风险"
        elif len(recommended_missing) >= 2:
            grade = "高风险"

        actions: list[str] = []
        if critical_missing:
            actions.append(f"缺少关键字段：{', '.join(critical_missing)}，请重新登录后导出完整 Cookie。")
        if session_missing:
            actions.append("缺少 _m_h5_tk/_m_h5_tk_enc，建议刷新页面后重新导出。")
        if domain_filter.get("rejected", 0):
            actions.append("检测到非 goofish 域 Cookie，系统已自动过滤。")
        if recommended_missing:
            actions.append(
                "缺少会话增强字段："
                + ", ".join(recommended_missing)
                + "；建议在插件中使用 Export All Cookies（全量导出）后重试。"
            )
        if grade == "可用":
            actions.append("可直接保存并在首页执行“售前一键恢复”。")

        return {
            "success": True,
            "grade": grade,
            "detected_format": str(parsed.get("detected_format") or "unknown"),
            "length": length,
            "cookie_items": cookie_items,
            "required_present": required_present,
            "required_missing": required_missing,
            "recommended_present": recommended_present,
            "recommended_missing": recommended_missing,
            "domain_filter": domain_filter,
            "actions": actions,
        }

    @classmethod
    def _is_cookie_import_file(cls, filename: str) -> bool:
        suffix = Path(filename).suffix.lower()
        if suffix in cls._COOKIE_IMPORT_EXTS:
            return True
        # 一些插件/工具导出的文件无后缀（如 `cookies`），允许走内容识别。
        return suffix == "" and bool(Path(filename).name)

    @classmethod
    def _looks_like_cookie_plugin_bundle(cls, member_names: list[str]) -> bool:
        names = [str(name or "").replace("\\", "/").strip().lower() for name in member_names if str(name or "").strip()]
        if not names:
            return False

        if any("get-cookies.txt-locally/src/manifest.json" in item for item in names):
            return True

        basenames = {Path(item).name for item in names}
        has_manifest = "manifest.json" in basenames
        has_popup = "popup.mjs" in basenames or "popup.js" in basenames
        has_background = "background.mjs" in basenames or "background.js" in basenames
        if has_manifest and (has_popup or has_background):
            return True

        # 插件源码常见特征文件，manifest + 任一特征可判定为安装包而非导出 cookie。
        plugin_markers = (
            "get-cookies.txt-locally",
            "cookie_format.mjs",
            "get_all_cookies.mjs",
            "save_to_file.mjs",
            "popup-options.css",
        )
        if has_manifest and any(any(marker in item for marker in plugin_markers) for item in names):
            return True
        return False

    @classmethod
    def _cookie_hint_hit_keys(cls, cookie_text: str) -> list[str]:
        text = str(cookie_text or "")
        hits = [k for k in cls._COOKIE_HINT_KEYS if f"{k}=" in text]
        return hits

    @classmethod
    def _score_cookie_candidate(cls, payload: dict[str, Any]) -> tuple[int, int, int]:
        missing = payload.get("missing_required")
        missing_count = len(missing) if isinstance(missing, list) else len(cls._COOKIE_REQUIRED_KEYS)
        required_hit = max(0, len(cls._COOKIE_REQUIRED_KEYS) - missing_count)
        cookie_items = int(payload.get("cookie_items", 0) or 0)
        length = int(payload.get("length", 0) or 0)
        return required_hit, cookie_items, length

    def import_cookie_plugin_files(
        self, files: list[tuple[str, bytes]], *, auto_recover: bool = False
    ) -> dict[str, Any]:
        if not files:
            return {"success": False, "error": "No files uploaded"}

        candidates: list[dict[str, Any]] = []
        imported_files: list[str] = []
        skipped_files: list[str] = []
        details: list[str] = []
        plugin_bundle_detected = False

        def _collect_text_candidate(source_name: str, raw: bytes) -> None:
            text = self._decode_text_bytes(raw)
            parsed = self.parse_cookie_text(text)
            if not parsed.get("success"):
                skipped_files.append(source_name)
                details.append(f"{source_name} -> {parsed.get('error', 'parse failed')}")
                return
            hit_keys = self._cookie_hint_hit_keys(str(parsed.get("cookie") or ""))
            if not hit_keys:
                skipped_files.append(source_name)
                details.append(f"{source_name} -> parsed but missing known keys ({', '.join(self._COOKIE_HINT_KEYS)})")
                return

            candidates.append(
                {
                    "source_file": source_name,
                    "parsed": parsed,
                    "hit_keys": hit_keys,
                }
            )
            imported_files.append(source_name)

        for filename, content in files:
            file_name = str(filename or "").strip()
            suffix = Path(file_name).suffix.lower()

            if suffix == ".zip":
                try:
                    with zipfile.ZipFile(io.BytesIO(content), mode="r") as zf:
                        member_names = [str(info.filename or "") for info in zf.infolist()]
                        if self._looks_like_cookie_plugin_bundle(member_names):
                            plugin_bundle_detected = True
                        for info in zf.infolist():
                            if info.is_dir():
                                continue
                            repaired_name = self._repair_zip_name(info.filename)
                            member_name = Path(repaired_name).name
                            if not member_name:
                                continue
                            if "__MACOSX" in repaired_name or member_name.startswith("._"):
                                skipped_files.append(f"{file_name}:{repaired_name}")
                                continue
                            if not self._is_cookie_import_file(member_name):
                                skipped_files.append(f"{file_name}:{repaired_name}")
                                continue
                            try:
                                raw = zf.read(info)
                                if not raw:
                                    skipped_files.append(f"{file_name}:{repaired_name}")
                                    details.append(f"{file_name}:{repaired_name} -> empty file")
                                    continue
                                _collect_text_candidate(f"{file_name}:{member_name}", raw)
                            except Exception as exc:
                                skipped_files.append(f"{file_name}:{repaired_name}")
                                details.append(f"{file_name}:{repaired_name} -> {exc}")
                except zipfile.BadZipFile:
                    skipped_files.append(file_name)
                    details.append(f"{file_name} -> invalid zip file")
                except Exception as exc:
                    skipped_files.append(file_name)
                    details.append(f"{file_name} -> {exc}")
                continue

            if not self._is_cookie_import_file(file_name):
                skipped_files.append(file_name)
                continue
            _collect_text_candidate(file_name, content)

        if not candidates:
            if plugin_bundle_detected:
                return {
                    "success": False,
                    "error": "Detected plugin installation bundle, not exported cookies.",
                    "hint": "请先在浏览器安装插件并导出 cookies.txt/JSON，再上传导出文件。",
                    "imported_files": imported_files,
                    "skipped_files": skipped_files,
                    "details": details,
                }
            return {
                "success": False,
                "error": "No valid cookie content found in uploaded files.",
                "imported_files": imported_files,
                "skipped_files": skipped_files,
                "details": details,
            }

        best = max(candidates, key=lambda item: self._score_cookie_candidate(item["parsed"]))
        parsed = dict(best.get("parsed", {}))
        cookie_text = str(parsed.get("cookie") or "").strip()
        if not cookie_text:
            return {
                "success": False,
                "error": "Parsed cookie is empty.",
                "imported_files": imported_files,
                "skipped_files": skipped_files,
                "details": details,
            }

        self._set_env_value("XIANYU_COOKIE_1", cookie_text)
        diagnosis = self.diagnose_cookie(cookie_text)
        payload: dict[str, Any] = {
            "success": True,
            "message": "Cookie imported from plugin export",
            "source_file": str(best.get("source_file") or ""),
            "cookie": cookie_text,
            "length": int(parsed.get("length", 0) or 0),
            "cookie_items": int(parsed.get("cookie_items", 0) or 0),
            "detected_format": str(parsed.get("detected_format") or "unknown"),
            "missing_required": parsed.get("missing_required", []),
            "imported_files": imported_files,
            "skipped_files": skipped_files,
            "details": details,
            "cookie_grade": diagnosis.get("grade", "未知"),
            "cookie_actions": diagnosis.get("actions", []),
            "cookie_diagnosis": diagnosis,
            "recognized_key_hits": best.get("hit_keys", []),
        }
        should_recover = auto_recover and str(diagnosis.get("grade") or "") != "不可用"
        if should_recover:
            recover = self._trigger_presales_recover_after_cookie_update(cookie_text)
            payload["auto_recover"] = recover
            if recover.get("triggered"):
                payload["message"] = "Cookie imported and presales recovery triggered"
            else:
                payload["message"] = "Cookie imported, but presales recovery failed"
        return payload

    def export_cookie_plugin_bundle(self) -> tuple[bytes, str]:
        base = self.cookie_plugin_dir
        src_dir = base / "src"
        if not base.exists() or not src_dir.exists():
            raise FileNotFoundError("Bundled plugin source not found under third_party/Get-cookies.txt-LOCALLY")

        include_paths = [
            "src",
            "LICENSE",
            "README.upstream.md",
            "privacy-policy.upstream.md",
            "SOURCE_INFO.txt",
        ]

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for rel in include_paths:
                target = base / rel
                if not target.exists():
                    continue
                if target.is_file():
                    zf.write(target, arcname=f"Get-cookies.txt-LOCALLY/{rel}")
                    continue
                for fp in target.rglob("*"):
                    if not fp.is_file():
                        continue
                    arc = f"Get-cookies.txt-LOCALLY/{fp.relative_to(base).as_posix()}"
                    zf.write(fp, arcname=arc)

        filename = "Get-cookies.txt-LOCALLY_bundle.zip"
        return buf.getvalue(), filename

    def _quote_dir(self) -> Path:
        cfg = get_config().get_section("quote", {})
        table_dir = str(cfg.get("cost_table_dir", "data/quote_costs"))
        path = Path(table_dir)
        if not path.is_absolute():
            path = self.project_root / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    def route_stats(self) -> dict[str, Any]:
        cfg = get_config().get_section("quote", {})
        patterns = cfg.get("cost_table_patterns", ["*.xlsx", "*.xls", "*.csv"])
        if not isinstance(patterns, list):
            patterns = ["*.xlsx", "*.xls", "*.csv"]
        for required in ("*.xlsx", "*.xls", "*.csv"):
            if required not in patterns:
                patterns.append(required)
        quote_dir = self._quote_dir()
        files = []
        latest_mtime = 0.0
        for pattern in patterns:
            for fp in quote_dir.glob(str(pattern)):
                if fp.is_file():
                    files.append(fp)
                    latest_mtime = max(latest_mtime, fp.stat().st_mtime)

        route_count = 0
        courier_set: set[str] = set()
        courier_details: dict[str, int] = {}
        parse_errors: list[str] = []

        for fp in sorted(set(files)):
            try:
                repo = CostTableRepository(table_dir=fp)
                repo.get_stats(max_files=1)
                records = getattr(repo, "_records", [])
                route_count += len(records)
                for rec in records:
                    courier = str(getattr(rec, "courier", "") or "").strip()
                    if not courier:
                        continue
                    courier_set.add(courier)
                    courier_details[courier] = int(courier_details.get(courier, 0) or 0) + 1
            except Exception as exc:
                parse_errors.append(f"{fp.name}: {exc}")

        last_updated = "-"
        if latest_mtime > 0:
            last_updated = datetime.fromtimestamp(latest_mtime).strftime("%Y-%m-%d %H:%M:%S")

        stats = {
            "couriers": len(courier_set),
            "routes": int(route_count),
            "tables": len(set(files)),
            "last_updated": last_updated,
            "courier_details": dict(sorted(courier_details.items(), key=lambda x: x[0])),
            "files": [str(p.name) for p in sorted(set(files))[:200]],
        }
        if parse_errors:
            stats["parse_error"] = " | ".join(parse_errors[:5])
        return {"success": True, "stats": stats}

    def _workflow_db_path(self) -> Path:
        messages_cfg = get_config().get_section("messages", {})
        workflow_cfg = messages_cfg.get("workflow", {}) if isinstance(messages_cfg.get("workflow"), dict) else {}
        raw = str(workflow_cfg.get("db_path", "data/workflow.db") or "data/workflow.db")
        path = Path(raw)
        if not path.is_absolute():
            path = self.project_root / path
        return path

    def _query_message_stats_from_workflow(self) -> dict[str, Any] | None:
        db_path = self._workflow_db_path()
        if not db_path.exists():
            return None

        reply_states = ("REPLIED", "QUOTED")
        ok_status = ("success", "forced")
        try:
            with closing(sqlite3.connect(db_path)) as conn:
                conn.row_factory = sqlite3.Row

                total_replied = int(
                    conn.execute(
                        """
                        SELECT COUNT(*) AS c
                        FROM session_state_transitions
                        WHERE status IN (?, ?)
                          AND to_state IN (?, ?)
                        """,
                        (ok_status[0], ok_status[1], reply_states[0], reply_states[1]),
                    ).fetchone()["c"]
                )

                today_replied = int(
                    conn.execute(
                        """
                        SELECT COUNT(*) AS c
                        FROM session_state_transitions
                        WHERE status IN (?, ?)
                          AND to_state IN (?, ?)
                          AND date(datetime(created_at), 'localtime') = date('now', 'localtime')
                        """,
                        (ok_status[0], ok_status[1], reply_states[0], reply_states[1]),
                    ).fetchone()["c"]
                )

                recent_replied = int(
                    conn.execute(
                        """
                        SELECT COUNT(*) AS c
                        FROM session_state_transitions
                        WHERE status IN (?, ?)
                          AND to_state IN (?, ?)
                          AND datetime(created_at) >= datetime('now', '-60 minutes')
                        """,
                        (ok_status[0], ok_status[1], reply_states[0], reply_states[1]),
                    ).fetchone()["c"]
                )

                total_conversations = int(conn.execute("SELECT COUNT(*) AS c FROM session_tasks").fetchone()["c"])
                total_messages = int(conn.execute("SELECT COUNT(*) AS c FROM workflow_jobs").fetchone()["c"])

                hourly_rows = conn.execute(
                    """
                    SELECT strftime('%H', datetime(created_at), 'localtime') AS h, COUNT(*) AS c
                    FROM session_state_transitions
                    WHERE status IN (?, ?)
                      AND to_state IN (?, ?)
                      AND datetime(created_at) >= datetime('now', '-24 hours')
                    GROUP BY h
                    """,
                    (ok_status[0], ok_status[1], reply_states[0], reply_states[1]),
                ).fetchall()

                daily_rows = conn.execute(
                    """
                    SELECT strftime('%Y-%m-%d', datetime(created_at), 'localtime') AS d, COUNT(*) AS c
                    FROM session_state_transitions
                    WHERE status IN (?, ?)
                      AND to_state IN (?, ?)
                      AND date(datetime(created_at), 'localtime') >= date('now', 'localtime', '-6 days')
                    GROUP BY d
                    """,
                    (ok_status[0], ok_status[1], reply_states[0], reply_states[1]),
                ).fetchall()

            hourly = {str(r["h"]): int(r["c"]) for r in hourly_rows if r["h"] is not None}
            daily = {str(r["d"]): int(r["c"]) for r in daily_rows if r["d"] is not None}
            return {
                "total_replied": total_replied,
                "today_replied": today_replied,
                "recent_replied": recent_replied,
                "total_conversations": total_conversations,
                "total_messages": total_messages,
                "hourly_replies": hourly,
                "daily_replies": daily,
            }
        except Exception:
            return None

    @staticmethod
    def _safe_filename(name: str) -> str:
        base_name = Path(str(name or "")).name
        ext = Path(base_name).suffix.lower()
        stem_raw = Path(base_name).stem
        stem = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fa5]+", "_", stem_raw).strip("_-")
        if not stem:
            stem = f"upload_{int(time.time())}"
        if ext not in MimicOps._ROUTE_FILE_EXTS:
            ext = ".xlsx"
        return f"{stem}{ext}"

    @staticmethod
    def _repair_zip_name(name: str) -> str:
        raw = str(name or "")
        if not raw:
            return raw
        try:
            return raw.encode("cp437").decode("utf-8")
        except Exception:
            pass
        for enc in ("gbk", "gb18030", "big5"):
            try:
                return raw.encode("cp437").decode(enc)
            except Exception:
                continue
        return raw

    @classmethod
    def _is_route_table_file(cls, filename: str) -> bool:
        return Path(filename).suffix.lower() in cls._ROUTE_FILE_EXTS

    def _save_route_content(self, quote_dir: Path, filename: str, content: bytes) -> str:
        base_name = Path(filename).name
        clean = self._safe_filename(base_name)
        if not self._is_route_table_file(clean):
            raise ValueError(f"Unsupported file type: {base_name}")

        target = quote_dir / clean
        if target.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            candidate = quote_dir / f"{target.stem}_{ts}{target.suffix}"
            idx = 1
            while candidate.exists():
                idx += 1
                candidate = quote_dir / f"{target.stem}_{ts}_{idx}{target.suffix}"
            target = candidate
        target.write_bytes(content)
        return target.name

    def import_route_files(self, files: list[tuple[str, bytes]]) -> dict[str, Any]:
        if not files:
            return {"success": False, "error": "No files uploaded"}
        quote_dir = self._quote_dir()
        saved: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []
        zip_count = 0
        for filename, content in files:
            file_name = str(filename or "").strip()
            suffix = Path(file_name).suffix.lower()

            if suffix == ".zip":
                zip_count += 1
                try:
                    with zipfile.ZipFile(io.BytesIO(content), mode="r") as zf:
                        for info in zf.infolist():
                            if info.is_dir():
                                continue
                            repaired_name = self._repair_zip_name(info.filename)
                            member_name = Path(repaired_name).name
                            if not member_name:
                                continue
                            if "__MACOSX" in repaired_name or member_name.startswith("._"):
                                skipped.append(repaired_name)
                                continue
                            if not self._is_route_table_file(member_name):
                                skipped.append(repaired_name)
                                continue
                            try:
                                data = zf.read(info)
                                saved_name = self._save_route_content(quote_dir, member_name, data)
                                saved.append(saved_name)
                            except Exception as exc:
                                skipped.append(repaired_name)
                                errors.append(f"{file_name}:{repaired_name} -> {exc}")
                except zipfile.BadZipFile:
                    skipped.append(file_name)
                    errors.append(f"{file_name} -> invalid zip file")
                except Exception as exc:
                    skipped.append(file_name)
                    errors.append(f"{file_name} -> {exc}")
                continue

            if self._is_route_table_file(file_name):
                try:
                    saved_name = self._save_route_content(quote_dir, file_name, content)
                    saved.append(saved_name)
                except Exception as exc:
                    skipped.append(file_name)
                    errors.append(f"{file_name} -> {exc}")
            else:
                skipped.append(file_name)

        if not saved:
            return {
                "success": False,
                "error": "No supported route files found. Use .xlsx/.xls/.csv or a .zip containing them.",
                "skipped_files": skipped,
                "details": errors,
            }

        stats = self.route_stats().get("stats", {})
        message = f"Imported {len(saved)} file(s)"
        if zip_count > 0:
            message += f" from {zip_count} zip archive(s)"
        return {
            "success": True,
            "message": message,
            "saved_files": saved,
            "skipped_files": skipped,
            "details": errors,
            "stats": stats,
        }

    def export_routes_zip(self) -> tuple[bytes, str]:
        quote_dir = self._quote_dir()
        files = sorted([*quote_dir.glob("*.xlsx"), *quote_dir.glob("*.xls"), *quote_dir.glob("*.csv")])
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for fp in files:
                zf.write(fp, arcname=fp.name)
        filename = f"routes_export_{datetime.now().strftime('%Y%m%d')}.zip"
        return buf.getvalue(), filename

    def reset_database(self, db_type: str) -> dict[str, Any]:
        target = str(db_type or "all").strip().lower()
        result: dict[str, Any] = {"success": True, "results": {}}

        if target in {"routes", "all"}:
            quote_dir = self._quote_dir()
            deleted = 0
            for fp in [*quote_dir.glob("*.xlsx"), *quote_dir.glob("*.xls"), *quote_dir.glob("*.csv")]:
                fp.unlink(missing_ok=True)
                deleted += 1
            result["results"]["routes"] = {"message": f"Deleted {deleted} cost table files"}

        if target in {"chat", "all"}:
            removed: list[str] = []
            for rel in ("data/workflow.db", "data/message_workflow_state.json", "data/messages_followup_state.json"):
                p = self.project_root / rel
                if p.exists():
                    p.unlink()
                    removed.append(rel)
            result["results"]["chat"] = {"message": f"Removed {len(removed)} chat workflow file(s)", "files": removed}

        return result

    @property
    def template_path(self) -> Path:
        return self.project_root / "config" / "templates" / "reply_templates.json"

    def get_template(self, default: bool = False) -> dict[str, Any]:
        if default:
            return {
                "success": True,
                "weight_template": DEFAULT_WEIGHT_TEMPLATE,
                "volume_template": DEFAULT_VOLUME_TEMPLATE,
            }
        if self.template_path.exists():
            try:
                data = json.loads(self.template_path.read_text(encoding="utf-8"))
                return {
                    "success": True,
                    "weight_template": str(data.get("weight_template") or DEFAULT_WEIGHT_TEMPLATE),
                    "volume_template": str(data.get("volume_template") or DEFAULT_VOLUME_TEMPLATE),
                }
            except Exception:
                pass
        return {
            "success": True,
            "weight_template": DEFAULT_WEIGHT_TEMPLATE,
            "volume_template": DEFAULT_VOLUME_TEMPLATE,
        }

    def save_template(self, weight_template: str, volume_template: str) -> dict[str, Any]:
        payload = {
            "weight_template": str(weight_template or DEFAULT_WEIGHT_TEMPLATE).strip() or DEFAULT_WEIGHT_TEMPLATE,
            "volume_template": str(volume_template or DEFAULT_VOLUME_TEMPLATE).strip() or DEFAULT_VOLUME_TEMPLATE,
            "updated_at": _now_iso(),
        }
        self.template_path.parent.mkdir(parents=True, exist_ok=True)
        self.template_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"success": True, "message": "Template saved", **payload}

    def get_replies(self) -> dict[str, Any]:
        template = self.get_template(default=False)
        return {
            "success": bool(template.get("success")),
            "replies": {
                "weight_template": str(template.get("weight_template") or DEFAULT_WEIGHT_TEMPLATE),
                "volume_template": str(template.get("volume_template") or DEFAULT_VOLUME_TEMPLATE),
            },
            "updated_at": str(template.get("updated_at") or ""),
        }

    @staticmethod
    def _decode_text_bytes(content: bytes) -> str:
        data = bytes(content or b"")
        for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk", "big5"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="ignore")

    @staticmethod
    def _markup_float(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text:
            return None
        text = text.replace("，", ",").replace(",", "")
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            return None
        try:
            return float(match.group(0))
        except ValueError:
            return None

    @staticmethod
    def _clean_markup_token(value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return ""
        text = text.replace("（", "(").replace("）", ")")
        text = re.sub(r"[\s_\-:|/\\,，;；。'\"]+", "", text)
        return text

    @classmethod
    def _normalize_markup_courier(cls, value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        if "默认" in raw or re.search(r"\bdefault\b", raw, flags=re.IGNORECASE):
            return "default"

        normalized = normalize_courier_name(raw)
        if normalized in DEFAULT_MARKUP_RULES:
            return normalized

        for courier in sorted([k for k in DEFAULT_MARKUP_RULES.keys() if k != "default"], key=len, reverse=True):
            if courier in raw:
                return courier

        noise_tokens = ("首重", "续重", "溢价", "加价", "普通", "会员", "运力", "价格", "元")
        if any(token in raw for token in noise_tokens):
            return ""

        if re.fullmatch(r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}", normalized):
            return normalized
        return ""

    @classmethod
    def _match_markup_header(cls, header: str, field: str) -> bool:
        token = cls._clean_markup_token(header)
        if not token:
            return False

        if field == "courier":
            return any(alias in token for alias in ["运力", "快递", "物流", "courier", "carrier", "渠道"])
        if field == "normal_first_add":
            return ("首重" in token or "first" in token) and ("普通" in token or "normal" in token or "普" in token)
        if field == "member_first_add":
            return ("首重" in token or "first" in token) and ("会员" in token or "member" in token or "vip" in token)
        if field == "normal_extra_add":
            return ("续重" in token or "extra" in token or "续费" in token) and (
                "普通" in token or "normal" in token or "普" in token
            )
        if field == "member_extra_add":
            return ("续重" in token or "extra" in token or "续费" in token) and (
                "会员" in token or "member" in token or "vip" in token
            )
        return False

    @classmethod
    def _resolve_markup_header_map(cls, rows: list[list[Any]]) -> tuple[dict[str, int], int]:
        max_check = min(len(rows), 10)
        best_map: dict[str, int] = {}
        best_end = -1
        best_score = 0

        for start in range(max_check):
            for span in (2, 1):
                if start + span > len(rows):
                    continue
                width = max(len(rows[idx]) for idx in range(start, start + span))
                combined_headers: dict[int, str] = {}
                for col in range(width):
                    parts: list[str] = []
                    for idx in range(start, start + span):
                        row = rows[idx]
                        if col < len(row):
                            value = str(row[col] or "").strip()
                            if value:
                                parts.append(value)
                    combined_headers[col] = " ".join(parts)

                mapping: dict[str, int] = {}
                for col, head in combined_headers.items():
                    for field in ("courier", *cls._MARKUP_REQUIRED_FIELDS):
                        if field in mapping:
                            continue
                        if cls._match_markup_header(head, field):
                            mapping[field] = col

                score = len([f for f in cls._MARKUP_REQUIRED_FIELDS if f in mapping])
                if "courier" in mapping and score >= 3 and score > best_score:
                    best_map = mapping
                    best_end = start + span - 1
                    best_score = score

        return best_map, best_end

    def _build_markup_rule(
        self, row_payload: dict[str, Any], fallback_numbers: list[float] | None = None
    ) -> dict[str, float]:
        default_row = dict(DEFAULT_MARKUP_RULES.get("default", {}))
        ordered_numbers = list(fallback_numbers or [])
        built: dict[str, float] = {}
        for idx, field in enumerate(self._MARKUP_REQUIRED_FIELDS):
            value: Any | None = row_payload.get(field)
            if value is None and idx < len(ordered_numbers):
                value = ordered_numbers[idx]
            built[field] = self._to_non_negative_float(value, default_row.get(field, 0.0))
        return built

    def _coerce_markup_row(self, value: Any) -> dict[str, float] | None:
        default_row = dict(DEFAULT_MARKUP_RULES.get("default", {}))
        if isinstance(value, dict):
            cleaned: dict[str, Any] = {}
            for k, v in value.items():
                token = self._clean_markup_token(k)
                if token:
                    cleaned[token] = v

            row_payload: dict[str, Any] = {}
            hit_count = 0
            for field in self._MARKUP_REQUIRED_FIELDS:
                aliases = [
                    self._clean_markup_token(field),
                    *[self._clean_markup_token(x) for x in self._MARKUP_FIELD_ALIASES[field]],
                ]
                value_found: Any | None = None
                for alias in aliases:
                    if alias in cleaned:
                        value_found = cleaned[alias]
                        break
                if value_found is not None:
                    hit_count += 1
                    row_payload[field] = value_found

            fallback_numbers = [n for n in (self._markup_float(v) for v in value.values()) if n is not None]
            if hit_count == 0 and len(fallback_numbers) < 4:
                return None
            return self._build_markup_rule(row_payload, fallback_numbers=fallback_numbers)

        if isinstance(value, (list, tuple)):
            nums = [n for n in (self._markup_float(x) for x in value) if n is not None]
            if len(nums) >= 4:
                return self._build_markup_rule({}, fallback_numbers=nums)
            return None

        number = self._markup_float(value)
        if number is not None:
            return self._build_markup_rule(
                {
                    "normal_first_add": number,
                    "member_first_add": default_row.get("member_first_add", 0.25),
                    "normal_extra_add": default_row.get("normal_extra_add", 0.5),
                    "member_extra_add": default_row.get("member_extra_add", 0.3),
                }
            )
        return None

    def _parse_markup_rules_from_mapping(self, mapping: Any) -> dict[str, dict[str, float]]:
        if not isinstance(mapping, dict):
            return {}
        parsed: dict[str, dict[str, float]] = {}
        for key, raw in mapping.items():
            courier = self._normalize_markup_courier(key)
            if not courier:
                continue
            row = self._coerce_markup_row(raw)
            if row is None:
                continue
            parsed[courier] = row
        return parsed

    @staticmethod
    def _split_text_rows(text: str) -> list[list[str]]:
        lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        if not lines:
            return []

        sample = lines[:8]
        delimiter_scores = {
            ",": sum(line.count(",") for line in sample),
            "\t": sum(line.count("\t") for line in sample),
            ";": sum(line.count(";") for line in sample),
            "|": sum(line.count("|") for line in sample),
        }
        delimiter = max(delimiter_scores, key=lambda d: delimiter_scores[d])
        if delimiter_scores[delimiter] <= 0:
            return []

        if delimiter == "|":
            return [[part.strip() for part in line.strip("|").split("|")] for line in lines if "|" in line]

        reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter)
        return [[str(cell or "").strip() for cell in row] for row in reader]

    def _parse_markup_rules_from_rows(self, rows: list[list[Any]]) -> dict[str, dict[str, float]]:
        if not rows:
            return {}
        mapping, header_end = self._resolve_markup_header_map(rows)
        parsed: dict[str, dict[str, float]] = {}

        data_rows = rows[header_end + 1 :] if header_end >= 0 else rows
        for row in data_rows:
            if not row or not any(str(cell or "").strip() for cell in row):
                continue

            courier = ""
            if "courier" in mapping and mapping["courier"] < len(row):
                courier = self._normalize_markup_courier(row[mapping["courier"]])
            if not courier:
                for cell in row[:2]:
                    courier = self._normalize_markup_courier(cell)
                    if courier:
                        break
            if not courier:
                continue

            row_payload: dict[str, Any] = {}
            extracted = 0
            for field in self._MARKUP_REQUIRED_FIELDS:
                col_idx = mapping.get(field)
                if col_idx is None or col_idx >= len(row):
                    continue
                n = self._markup_float(row[col_idx])
                if n is None:
                    continue
                row_payload[field] = n
                extracted += 1

            fallback_numbers = [n for n in (self._markup_float(cell) for cell in row) if n is not None]
            if extracted == 0 and len(fallback_numbers) < 4:
                continue
            parsed[courier] = self._build_markup_rule(row_payload, fallback_numbers=fallback_numbers)

        return parsed

    def _parse_markup_rules_from_text(self, text: str) -> dict[str, dict[str, float]]:
        parsed: dict[str, dict[str, float]] = {}

        row_based = self._split_text_rows(text)
        if row_based:
            parsed.update(self._parse_markup_rules_from_rows(row_based))

        lines = [str(line or "").strip() for line in str(text or "").splitlines() if str(line or "").strip()]
        pending_courier = ""
        pending_numbers: list[float] = []

        for line in lines:
            courier = self._normalize_markup_courier(line)
            numbers = [
                n for n in (self._markup_float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", line)) if n is not None
            ]

            if courier and len(numbers) >= 4:
                parsed[courier] = self._build_markup_rule({}, fallback_numbers=numbers)
                pending_courier = ""
                pending_numbers = []
                continue

            if courier:
                pending_courier = courier
                pending_numbers = list(numbers)
                continue

            if pending_courier:
                pending_numbers.extend(numbers)
                if len(pending_numbers) >= 4:
                    parsed[pending_courier] = self._build_markup_rule({}, fallback_numbers=pending_numbers)
                    pending_courier = ""
                    pending_numbers = []

        return parsed

    def _parse_markup_rules_from_json_like(self, payload: Any) -> dict[str, dict[str, float]]:
        if payload is None:
            return {}

        if isinstance(payload, dict):
            if "markup_rules" in payload:
                return self._parse_markup_rules_from_mapping(payload.get("markup_rules"))
            return self._parse_markup_rules_from_mapping(payload)

        if isinstance(payload, list):
            parsed: dict[str, dict[str, float]] = {}
            for item in payload:
                if not isinstance(item, dict):
                    continue
                courier = ""
                for alias in self._MARKUP_FIELD_ALIASES["courier"]:
                    value = item.get(alias)
                    courier = self._normalize_markup_courier(value)
                    if courier:
                        break
                if not courier:
                    for key in ("courier", "carrier", "name"):
                        courier = self._normalize_markup_courier(item.get(key))
                        if courier:
                            break
                if not courier:
                    continue
                row = self._coerce_markup_row(item)
                if row:
                    parsed[courier] = row
            return parsed
        return {}

    def _extract_text_from_image(self, content: bytes) -> str:
        try:
            from PIL import Image, ImageOps
        except Exception as exc:  # pragma: no cover - env dependent
            raise ValueError(f"Pillow unavailable: {exc}") from exc

        image = Image.open(io.BytesIO(content))
        image = ImageOps.grayscale(image)
        image = ImageOps.autocontrast(image)

        try:
            import pytesseract  # type: ignore

            text = pytesseract.image_to_string(image, lang="chi_sim+eng", config="--psm 6")
            if text.strip():
                return text
        except Exception:
            pass

        # Fallback: system tesseract CLI
        import tempfile

        temp_path = Path(tempfile.mkstemp(prefix="markup_ocr_", suffix=".png")[1])
        try:
            image.save(temp_path)
            proc = subprocess.run(
                ["tesseract", str(temp_path), "stdout", "-l", "chi_sim+eng", "--psm", "6"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            if proc.returncode != 0:
                stderr = (proc.stderr or "").strip()
                raise ValueError(f"tesseract failed ({proc.returncode}): {stderr or 'no stderr'}")
            out = str(proc.stdout or "")
            if not out.strip():
                raise ValueError("OCR result is empty")
            return out
        except FileNotFoundError as exc:  # pragma: no cover - env dependent
            raise ValueError("No OCR engine found. Install `pytesseract` or system `tesseract` first.") from exc
        finally:
            temp_path.unlink(missing_ok=True)

    def _parse_markup_rules_from_xlsx_bytes(self, content: bytes) -> dict[str, dict[str, float]]:
        import tempfile

        temp_path = Path(tempfile.mkstemp(prefix="markup_xlsx_", suffix=".xlsx")[1])
        try:
            temp_path.write_bytes(content)
            repo = CostTableRepository(table_dir=temp_path)
            rows_by_sheet = repo._iter_xlsx_rows(temp_path)
            rows: list[list[Any]] = []
            for _, sheet_rows in rows_by_sheet.items():
                rows.extend(sheet_rows)
            return self._parse_markup_rules_from_rows(rows)
        finally:
            temp_path.unlink(missing_ok=True)

    def _infer_markup_rules_from_route_table(self, filename: str, content: bytes) -> dict[str, dict[str, float]]:
        ext = Path(str(filename or "")).suffix.lower()
        if ext not in {".xlsx", ".csv"}:
            return {}

        import tempfile

        temp_path = Path(tempfile.mkstemp(prefix="route_infer_", suffix=ext)[1])
        try:
            temp_path.write_bytes(content)
            repo = CostTableRepository(table_dir=temp_path)
            repo.get_stats(max_files=1)
            records = getattr(repo, "_records", [])
            if not records:
                return {}

            default_row = dict(DEFAULT_MARKUP_RULES.get("default", {}))
            inferred: dict[str, dict[str, float]] = {}
            for rec in records:
                courier = self._normalize_markup_courier(getattr(rec, "courier", ""))
                if not courier or courier == "default":
                    continue
                inferred[courier] = dict(default_row)
            return inferred
        except Exception:
            return {}
        finally:
            temp_path.unlink(missing_ok=True)

    def _parse_markup_rules_from_file(self, filename: str, content: bytes) -> tuple[dict[str, dict[str, float]], str]:
        ext = Path(str(filename or "")).suffix.lower()
        data = bytes(content or b"")
        if ext in self._MARKUP_IMAGE_EXTS:
            text = self._extract_text_from_image(data)
            return self._parse_markup_rules_from_text(text), "image_ocr"

        if ext == ".xlsx":
            parsed = self._parse_markup_rules_from_xlsx_bytes(data)
            if parsed:
                return parsed, "excel_xml"
            inferred = self._infer_markup_rules_from_route_table(filename, data)
            if inferred:
                return inferred, "route_cost_infer"
            return {}, "excel_xml"

        if ext == ".xls":
            try:
                import pandas as pd
            except Exception as exc:  # pragma: no cover - dependency guard
                raise ValueError(f"excel parse failed: {exc}") from exc
            try:
                book = pd.read_excel(io.BytesIO(data), sheet_name=None, header=None)
            except Exception as exc:
                raise ValueError(f"excel parse failed: {exc}") from exc
            rows: list[list[Any]] = []
            for _, frame in (book or {}).items():
                if frame is None or getattr(frame, "empty", False):
                    continue
                rows.extend(frame.fillna("").values.tolist())
            parsed = self._parse_markup_rules_from_rows(rows)
            if parsed:
                return parsed, "excel"
            inferred = self._infer_markup_rules_from_route_table(filename, data)
            if inferred:
                return inferred, "route_cost_infer"
            return {}, "excel"

        text = self._decode_text_bytes(data)
        if ext == ".json":
            payload = _extract_json_payload(text)
            return self._parse_markup_rules_from_json_like(payload), "json"
        if ext in {".yaml", ".yml"}:
            payload = yaml.safe_load(text) if text.strip() else {}
            return self._parse_markup_rules_from_json_like(payload), "yaml"
        if ext in {".csv", ".txt", ".md"}:
            payload = _extract_json_payload(text)
            if payload is not None:
                parsed = self._parse_markup_rules_from_json_like(payload)
                if parsed:
                    return parsed, "json_text"
            parsed_text = self._parse_markup_rules_from_text(text)
            if parsed_text:
                return parsed_text, "text_table"
            inferred = self._infer_markup_rules_from_route_table(filename, data)
            if inferred:
                return inferred, "route_cost_infer"
            return {}, "text_table"

        raise ValueError(f"Unsupported file type: {filename}")

    def import_markup_files(self, files: list[tuple[str, bytes]]) -> dict[str, Any]:
        if not files:
            return {"success": False, "error": "No files uploaded"}

        parsed_rules: dict[str, dict[str, float]] = {}
        imported_files: list[str] = []
        skipped_files: list[str] = []
        details: list[str] = []
        formats: dict[str, int] = {}

        def _collect_one(name: str, data: bytes, source_prefix: str = "") -> None:
            file_name = str(name or "").strip()
            ext = Path(file_name).suffix.lower()
            if ext not in (self._MARKUP_FILE_EXTS | self._MARKUP_IMAGE_EXTS):
                skipped_files.append(f"{source_prefix}{file_name}")
                return
            try:
                parsed, fmt = self._parse_markup_rules_from_file(file_name, data)
                if not parsed:
                    skipped_files.append(f"{source_prefix}{file_name}")
                    details.append(f"{source_prefix}{file_name} -> no markup rule rows found")
                    return
                parsed_rules.update(parsed)
                imported_files.append(f"{source_prefix}{file_name}")
                formats[fmt] = int(formats.get(fmt, 0) or 0) + 1
            except Exception as exc:
                skipped_files.append(f"{source_prefix}{file_name}")
                details.append(f"{source_prefix}{file_name} -> {exc}")

        for filename, content in files:
            file_name = str(filename or "").strip()
            suffix = Path(file_name).suffix.lower()
            if suffix == ".zip":
                try:
                    with zipfile.ZipFile(io.BytesIO(content), mode="r") as zf:
                        for info in zf.infolist():
                            if info.is_dir():
                                continue
                            repaired_name = self._repair_zip_name(info.filename)
                            member_name = Path(repaired_name).name
                            if not member_name:
                                continue
                            if "__MACOSX" in repaired_name or member_name.startswith("._"):
                                skipped_files.append(f"{file_name}:{repaired_name}")
                                continue
                            _collect_one(member_name, zf.read(info), source_prefix=f"{file_name}:")
                except zipfile.BadZipFile:
                    skipped_files.append(file_name)
                    details.append(f"{file_name} -> invalid zip file")
                except Exception as exc:
                    skipped_files.append(file_name)
                    details.append(f"{file_name} -> {exc}")
                continue

            _collect_one(file_name, content)

        if not parsed_rules:
            return {
                "success": False,
                "error": "No valid markup rules found in uploaded files.",
                "imported_files": imported_files,
                "skipped_files": skipped_files,
                "details": details,
            }

        existing_payload = self.get_markup_rules()
        merged_rules = existing_payload.get("markup_rules", {})
        if not isinstance(merged_rules, dict):
            merged_rules = {}
        merged_rules = dict(merged_rules)
        merged_rules.update(parsed_rules)

        saved = self.save_markup_rules(merged_rules)
        if not saved.get("success"):
            return saved

        return {
            **saved,
            "imported_files": imported_files,
            "skipped_files": skipped_files,
            "details": details,
            "detected_formats": dict(sorted(formats.items(), key=lambda item: item[0])),
            "imported_couriers": [k for k in sorted(parsed_rules.keys()) if k != "default"],
        }

    @property
    def config_path(self) -> Path:
        return self.project_root / "config" / "config.yaml"

    @staticmethod
    def _to_non_negative_float(value: Any, default: float = 0.0) -> float:
        try:
            val = float(value)
            if val < 0:
                return 0.0
            return round(val, 4)
        except (TypeError, ValueError):
            return float(default)

    def _normalize_markup_rules(self, rules: Any) -> dict[str, dict[str, float]]:
        base_default = dict(DEFAULT_MARKUP_RULES.get("default", {}))
        if not isinstance(rules, dict):
            return {"default": base_default}

        normalized: dict[str, dict[str, float]] = {}
        for key, raw in rules.items():
            courier = str(key or "").strip()
            if not courier:
                continue
            payload = raw if isinstance(raw, dict) else {}
            normalized[courier] = {
                "normal_first_add": self._to_non_negative_float(
                    payload.get("normal_first_add"), base_default.get("normal_first_add", 0.5)
                ),
                "member_first_add": self._to_non_negative_float(
                    payload.get("member_first_add"), base_default.get("member_first_add", 0.25)
                ),
                "normal_extra_add": self._to_non_negative_float(
                    payload.get("normal_extra_add"), base_default.get("normal_extra_add", 0.5)
                ),
                "member_extra_add": self._to_non_negative_float(
                    payload.get("member_extra_add"), base_default.get("member_extra_add", 0.3)
                ),
            }

        if "default" not in normalized:
            normalized["default"] = base_default

        ordered: dict[str, dict[str, float]] = {"default": normalized.pop("default")}
        for key in sorted(normalized.keys()):
            ordered[key] = normalized[key]
        return ordered

    def get_markup_rules(self) -> dict[str, Any]:
        setup = QuoteSetupService(config_path=str(self.config_path))
        data, _ = setup._load_yaml()
        quote_cfg = data.get("quote", {}) if isinstance(data, dict) else {}
        rules = quote_cfg.get("markup_rules", {}) if isinstance(quote_cfg, dict) else {}
        normalized = self._normalize_markup_rules(rules if rules else DEFAULT_MARKUP_RULES)
        return {
            "success": True,
            "markup_rules": normalized,
            "couriers": [k for k in normalized.keys() if k != "default"],
            "updated_at": _now_iso(),
        }

    def save_markup_rules(self, rules: Any) -> dict[str, Any]:
        normalized = self._normalize_markup_rules(rules)
        if not normalized:
            return {"success": False, "error": "No valid markup rules"}

        setup = QuoteSetupService(config_path=str(self.config_path))
        data, existed = setup._load_yaml()
        quote_cfg = data.get("quote")
        if not isinstance(quote_cfg, dict):
            quote_cfg = {}
            data["quote"] = quote_cfg
        quote_cfg["markup_rules"] = normalized

        backup_path = setup._backup_existing_file() if existed else None
        setup._write_yaml(data)
        try:
            get_config().reload(str(self.config_path))
        except Exception:
            pass

        return {
            "success": True,
            "message": "Markup rules saved",
            "backup_path": str(backup_path) if backup_path else "",
            "markup_rules": normalized,
        }

    def _module_runtime_log(self, target: str) -> Path:
        return self.project_root / "data" / "module_runtime" / f"{target}.log"

    def list_log_files(self) -> dict[str, Any]:
        files: list[dict[str, Any]] = []
        runtime_dir = self.project_root / "data" / "module_runtime"
        conversations_dir = self.logs_dir / "conversations"

        for fp in runtime_dir.glob("*.log"):
            if not fp.is_file():
                continue
            stat = fp.stat()
            files.append(
                {
                    "name": f"runtime/{fp.name}",
                    "path": str(fp),
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "type": "runtime",
                }
            )

        for fp in self.logs_dir.glob("*.log"):
            if not fp.is_file():
                continue
            stat = fp.stat()
            files.append(
                {
                    "name": f"app/{fp.name}",
                    "path": str(fp),
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "type": "app",
                }
            )

        for fp in conversations_dir.glob("*.log"):
            if not fp.is_file():
                continue
            stat = fp.stat()
            files.append(
                {
                    "name": f"conversations/{fp.name}",
                    "path": str(fp),
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "type": "conversation",
                }
            )

        files.sort(key=lambda x: str(x.get("modified", "")), reverse=True)
        return {"success": True, "files": files}

    def _resolve_log_file(self, file_name: str) -> Path:
        name = str(file_name or "").strip()
        if name in {"presales", "operations", "aftersales"}:
            return self._module_runtime_log(name)
        if name.startswith("runtime/"):
            return self.project_root / "data" / "module_runtime" / name.replace("runtime/", "", 1)
        if name.startswith("app/"):
            return self.logs_dir / name.replace("app/", "", 1)
        if name.startswith("conversations/"):
            return self.logs_dir / "conversations" / name.replace("conversations/", "", 1)

        safe_name = Path(name).name
        app_path = self.logs_dir / safe_name
        if app_path.exists():
            return app_path
        return self.project_root / "data" / "module_runtime" / safe_name

    def read_log_content(
        self,
        file_name: str,
        tail: int = 200,
        page: int | None = None,
        size: int | None = None,
        search: str = "",
    ) -> dict[str, Any]:
        name = str(file_name or "").strip()
        if not name:
            return {"success": False, "error": "file is required"}

        fp = self._resolve_log_file(name)

        if not fp.exists():
            return {"success": False, "error": "log file not found", "file": str(fp)}

        lines = fp.read_text(encoding="utf-8", errors="ignore").splitlines()

        search_text = str(search or "").strip().lower()
        if search_text:
            lines = [line for line in lines if search_text in line.lower()]

        if page is not None or size is not None:
            page_n = max(1, int(page or 1))
            page_size = max(10, min(int(size or 100), 2000))
            total_lines = len(lines)
            total_pages = (total_lines + page_size - 1) // page_size if total_lines > 0 else 1
            if page_n > total_pages:
                page_n = total_pages
            start = (page_n - 1) * page_size
            end = start + page_size
            return {
                "success": True,
                "file": str(fp),
                "lines": lines[start:end],
                "total_lines": total_lines,
                "page": page_n,
                "total_pages": total_pages,
                "page_size": page_size,
                "search": search_text,
            }

        tail_n = max(1, min(int(tail), 5000))
        return {"success": True, "file": str(fp), "lines": lines[-tail_n:], "total_lines": len(lines)}

    @classmethod
    def _strip_ansi(cls, text: str) -> str:
        return cls._ANSI_ESCAPE_RE.sub("", str(text or "")).strip()

    @classmethod
    def _extract_log_time(cls, text: str) -> str:
        cleaned = cls._strip_ansi(text)
        m = cls._LOG_TIME_RE.search(cleaned)
        return str(m.group(1)) if m else ""

    def _risk_control_status_from_logs(self, target: str = "presales", tail_lines: int = 300) -> dict[str, Any]:
        fp = self._module_runtime_log(target)
        if not fp.exists():
            return {
                "level": "unknown",
                "label": "未检测（无日志）",
                "score": 0,
                "signals": ["日志文件不存在"],
                "last_event": "",
                "last_event_at": "",
                "checked_lines": 0,
                "source_log": str(fp),
                "updated_at": _now_iso(),
            }

        try:
            lines = fp.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception as e:
            return {
                "level": "unknown",
                "label": "未检测（读取失败）",
                "score": 0,
                "signals": [f"日志读取失败: {e}"],
                "last_event": "",
                "last_event_at": "",
                "checked_lines": 0,
                "source_log": str(fp),
                "updated_at": _now_iso(),
            }

        tail_n = max(50, min(int(tail_lines or 300), 2000))
        recent = [self._strip_ansi(line) for line in lines[-tail_n:] if str(line or "").strip()]
        if not recent:
            return {
                "level": "unknown",
                "label": "未检测（空日志）",
                "score": 0,
                "signals": ["日志内容为空"],
                "last_event": "",
                "last_event_at": "",
                "checked_lines": 0,
                "source_log": str(fp),
                "updated_at": _now_iso(),
            }

        block_hits: list[tuple[int, str]] = []
        warn_hits: list[tuple[int, str]] = []
        ws_400_lines: list[tuple[int, str]] = []
        connected_hits: list[tuple[int, str]] = []

        for idx, line in enumerate(recent):
            lowered = line.lower()
            if "connected to goofish websocket transport" in lowered:
                connected_hits.append((idx, line))
            if any(token in lowered for token in self._RISK_BLOCK_PATTERNS):
                block_hits.append((idx, line))
                continue
            if any(token in lowered for token in self._RISK_WARN_PATTERNS):
                warn_hits.append((idx, line))
            if "websocket" in lowered and "http 400" in lowered:
                ws_400_lines.append((idx, line))

        level = "normal"
        label = "正常"
        score = 0
        signals: list[str] = ["未发现封控信号"]
        last_event = recent[-1]
        if block_hits:
            level = "blocked"
            label = "疑似封控"
            score = min(100, 75 + len(block_hits) * 4)
            signals = [f"高风险信号 x{len(block_hits)}"]
            if ws_400_lines:
                signals.append(f"WebSocket HTTP 400 x{len(ws_400_lines)}")
            last_event = block_hits[-1][1]
        elif len(ws_400_lines) >= 5 or warn_hits:
            level = "warning"
            label = "风险预警"
            score = min(85, 30 + len(warn_hits) * 4 + len(ws_400_lines) * 2)
            signals = []
            if ws_400_lines:
                signals.append(f"WebSocket HTTP 400 x{len(ws_400_lines)}")
            if warn_hits:
                signals.append(f"异常告警 x{len(warn_hits)}")
            last_event = (warn_hits or ws_400_lines)[-1][1]

        last_connected_at = ""
        if connected_hits:
            last_connected_line = connected_hits[-1][1]
            last_connected_idx = connected_hits[-1][0]
            last_connected_at = self._extract_log_time(last_connected_line)
            last_risk_idx = -1
            if block_hits:
                last_risk_idx = max(last_risk_idx, block_hits[-1][0])
            if warn_hits:
                last_risk_idx = max(last_risk_idx, warn_hits[-1][0])
            if ws_400_lines:
                last_risk_idx = max(last_risk_idx, ws_400_lines[-1][0])
            if last_connected_idx > last_risk_idx >= 0:
                level = "normal"
                label = "已恢复连接"
                score = 0
                signals = ["最近已恢复连接"]
                last_event = last_connected_line

        return {
            "level": level,
            "label": label,
            "score": int(score),
            "signals": signals,
            "last_event": str(last_event)[-180:],
            "last_event_at": self._extract_log_time(last_event),
            "last_connected_at": last_connected_at,
            "checked_lines": len(recent),
            "source_log": str(fp),
            "updated_at": _now_iso(),
        }

    def test_reply(self, payload: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        msg_cfg = get_config().get_section("messages", {})
        message = str(payload.get("message") or payload.get("user_message") or payload.get("user_msg") or "").strip()
        item_title = str(payload.get("item_title") or payload.get("item") or payload.get("item_desc") or "").strip()
        origin = str(payload.get("origin") or "").strip()
        destination = str(payload.get("destination") or "").strip()
        weight_val = payload.get("weight")

        # 兼容旧测试入口：若显式提供了路线参数，则拼成自然语言输入，走与生产一致的询价解析逻辑。
        message_eval = message
        if origin and destination and weight_val not in {None, ""}:
            extras: list[str] = []
            length = payload.get("length")
            width = payload.get("width")
            height = payload.get("height")
            volume_weight = payload.get("volume_weight")
            courier = str(payload.get("courier") or "").strip()
            if length not in {None, ""} and width not in {None, ""} and height not in {None, ""}:
                extras.append(f"{length}x{width}x{height}cm")
            if volume_weight not in {None, ""}:
                extras.append(f"体积重{volume_weight}kg")
            if courier and courier.lower() != "auto":
                extras.append(courier)
            structured = f"从{origin}寄到{destination} {weight_val}kg"
            if extras:
                structured = f"{structured} {' '.join(extras)}"
            message_eval = f"{message} {structured}".strip() if message else structured

        service = MessagesService(controller=None, config=msg_cfg)
        reply, detail = _run_async(service._generate_reply_with_quote(message_eval, item_title=item_title))

        quote_part: dict[str, Any] | None = None
        if isinstance(detail, dict) and bool(detail.get("is_quote")):
            quote_result = detail.get("quote_result")
            all_couriers = detail.get("quote_all_couriers")
            if isinstance(quote_result, dict):
                quote_part = quote_result
            if isinstance(all_couriers, list):
                quote_part = {"best": quote_part or {}, "all_couriers": all_couriers}

        intent = "quote" if bool(detail.get("is_quote")) else "general"
        agent = (
            "MessagesService+AutoQuoteEngine"
            if quote_part is not None
            else ("MessagesService+RuleBasedReplyStrategy" if intent == "general" else "MessagesService")
        )
        response_time_ms = (time.perf_counter() - started) * 1000
        return {
            "success": True,
            "reply": reply,
            "quote": quote_part,
            "intent": intent,
            "agent": agent,
            "detail": detail,
            "response_time_ms": response_time_ms,
            "response_time": response_time_ms,
        }

    def _maybe_auto_recover_presales(
        self,
        *,
        service_status: str,
        token_error: str | None,
        cookie_text: str,
    ) -> dict[str, Any]:
        cookie_fp = self._cookie_fingerprint(cookie_text)
        auto_triggered = False
        reason = "monitoring"
        stage = "monitoring"
        result: dict[str, Any] = {}

        if service_status in {"stopped", "suspended"}:
            reason = "service_not_running"
            stage = "inactive"
        elif token_error != "FAIL_SYS_USER_VALIDATE":
            reason = "token_healthy_or_non_validate_error"
            stage = "healthy" if token_error is None else "token_error"
        elif not cookie_fp:
            reason = "cookie_empty"
            stage = "waiting_cookie_update"
        elif cookie_fp == self._last_auto_recover_cookie_fp:
            reason = "same_cookie_already_recovered"
            stage = "waiting_reconnect"
        elif self._last_token_error == "FAIL_SYS_USER_VALIDATE" and cookie_fp != self._last_cookie_fp:
            stage = "recover_triggered"
            reason = "cookie_updated_after_validate_error"
            with self._recover_lock:
                # 双重检查，避免并发请求重复触发 recover。
                if cookie_fp != self._last_auto_recover_cookie_fp:
                    result = self.module_console.control(action="recover", target="presales")
                    auto_triggered = not bool(result.get("error")) if isinstance(result, dict) else False
                    self._last_auto_recover_cookie_fp = cookie_fp
                    self._last_auto_recover_at = _now_iso()
                    self._last_auto_recover_result = result if isinstance(result, dict) else {}
                else:
                    reason = "same_cookie_already_recovered"
                    stage = "waiting_reconnect"
        else:
            reason = "waiting_cookie_update"
            stage = "waiting_cookie_update"

        # 更新快照，供下一轮识别“cookie 是否发生变化”。
        self._last_cookie_fp = cookie_fp
        self._last_token_error = token_error

        return {
            "stage": stage,
            "stage_label": self._recovery_stage_label(stage),
            "auto_recover_triggered": auto_triggered,
            "reason": reason,
            "advice": self._recovery_advice(stage, token_error),
            "last_auto_recover_at": self._last_auto_recover_at,
            "last_auto_recover_result": self._last_auto_recover_result,
        }

    def service_status(self) -> dict[str, Any]:
        module_status = self.module_console.status(window_minutes=60, limit=20)
        cookie = self.get_cookie()
        cookie_text = str(cookie.get("cookie", "") or "")
        route_stats = self.route_stats()
        xgj_settings = self.get_xianguanjia_settings()
        risk_control = self._risk_control_status_from_logs(target="presales", tail_lines=300)
        modules = module_status.get("modules") if isinstance(module_status, dict) else {}
        if not isinstance(modules, dict):
            modules = {}

        if self._service_state.get("stopped"):
            service_status = "stopped"
        elif self._service_state.get("suspended"):
            service_status = "suspended"
        else:
            service_status = "running"

        alive_count = int(module_status.get("alive_count", 0)) if isinstance(module_status, dict) else 0
        total_modules = (
            int(module_status.get("total_modules", len(MODULE_TARGETS)))
            if isinstance(module_status, dict)
            else len(MODULE_TARGETS)
        )

        presales_mod = modules.get("presales", {}) if isinstance(modules.get("presales"), dict) else {}
        presales_sla = presales_mod.get("sla", {}) if isinstance(presales_mod.get("sla"), dict) else {}
        presales_process = presales_mod.get("process", {}) if isinstance(presales_mod.get("process"), dict) else {}
        workflow = presales_mod.get("workflow", {}) if isinstance(presales_mod.get("workflow"), dict) else {}
        route_stat_payload = route_stats.get("stats", {}) if isinstance(route_stats, dict) else {}
        route_stats_by_courier = (
            route_stat_payload.get("courier_details", {}) if isinstance(route_stat_payload, dict) else {}
        )
        risk_level = str(risk_control.get("level", "unknown") or "unknown").lower()
        risk_signals_raw = risk_control.get("signals", [])
        risk_signals = (
            [str(x).strip() for x in risk_signals_raw if str(x).strip()] if isinstance(risk_signals_raw, list) else []
        )
        risk_signal_text = " ".join(risk_signals)
        risk_event_text = str(risk_control.get("last_event", "") or "")
        risk_text = f"{risk_signal_text} {risk_event_text}".lower()

        workflow_states = workflow.get("states", {}) if isinstance(workflow.get("states"), dict) else {}
        workflow_jobs = workflow.get("jobs", {}) if isinstance(workflow.get("jobs"), dict) else {}
        fallback_total_replied = int(workflow_states.get("REPLIED", 0) or 0) + int(
            workflow_states.get("QUOTED", 0) or 0
        )
        fallback_total_conversations = sum(int(v or 0) for v in workflow_states.values())
        fallback_total_messages = sum(int(v or 0) for v in workflow_jobs.values())
        message_stats = self._query_message_stats_from_workflow() or {
            "total_replied": fallback_total_replied,
            "today_replied": fallback_total_replied,
            "recent_replied": int(presales_sla.get("event_count", 0) or 0),
            "total_conversations": fallback_total_conversations,
            "total_messages": fallback_total_messages,
            "hourly_replies": {},
            "daily_replies": {},
        }

        token_error: str | None = None
        if "fail_sys_user_validate" in risk_text:
            token_error = "FAIL_SYS_USER_VALIDATE"
        elif "rgv587" in risk_text or "被挤爆" in risk_text:
            token_error = "RGV587_SERVER_BUSY"
        elif "token api failed" in risk_text:
            token_error = "TOKEN_API_FAILED"
        elif "websocket" in risk_text and "http 400" in risk_text:
            token_error = "WS_HTTP_400"

        cookie_update_required = bool(token_error == "FAIL_SYS_USER_VALIDATE")
        token_available = bool(cookie.get("success", False)) and token_error is None
        xianyu_connected = (
            bool(presales_process.get("alive", False)) and token_error is None and risk_level != "blocked"
        )
        if service_status == "running" and (not xianyu_connected or risk_level in {"warning", "blocked"}):
            service_status = "degraded"
        recovery = self._maybe_auto_recover_presales(
            service_status=service_status,
            token_error=token_error,
            cookie_text=cookie_text,
        )
        recovery_stage = str(recovery.get("stage") or "monitoring").strip().lower() or "monitoring"
        next_retry_at: str | None = None
        if recovery_stage in {"recover_triggered", "waiting_reconnect"}:
            last_auto_recover_at = str(recovery.get("last_auto_recover_at") or "").strip()
            if last_auto_recover_at:
                try:
                    dt = datetime.fromisoformat(last_auto_recover_at.replace("Z", "+00:00"))
                    next_retry_at = (dt + timedelta(seconds=20)).strftime("%Y-%m-%dT%H:%M:%S")
                except Exception:
                    next_retry_at = None

        user_id = None
        for key, value in self._extract_cookie_pairs_from_header(cookie_text):
            if str(key or "").strip() == "unb":
                user_id = str(value or "").strip() or None
                break

        cookie_score = 0
        cookie_state = "bad"
        if bool(cookie.get("success", False)):
            cookie_score = 60
            cookie_state = "warning"
            if token_error is None and risk_level not in {"warning", "blocked"}:
                cookie_score = 100
                cookie_state = "good"
            elif risk_level == "blocked":
                cookie_score = 20
                cookie_state = "bad"

        try:
            from src.modules.orders.service import OrderFulfillmentService

            order_summary = OrderFulfillmentService(
                db_path=str(self.project_root / "data" / "orders.db"),
                config=self._xianguanjia_service_config(),
            ).get_summary()
        except Exception:
            order_summary = {}

        accounts_summary = self.list_accounts()

        return {
            "success": True,
            "service": dict(self._service_state),
            "module": module_status,
            "cookie_exists": bool(cookie.get("success", False)),
            "cookie_valid": bool(cookie.get("success", False)),
            "cookie_length": int(cookie.get("length", 0) or 0),
            "cookie_health": {
                "score": cookie_score,
                "status": cookie_state,
                "token_error": token_error,
            },
            "xianyu_connected": xianyu_connected,
            "token_available": token_available,
            "token_error": token_error,
            "cookie_update_required": cookie_update_required,
            "user_id": user_id,
            "last_token_refresh": risk_control.get("last_event_at") if token_error is None else None,
            "service_start_time": self._service_started_at,
            "instance_id": self._instance_id,
            "project_root": str(self.project_root),
            "python_exec": self._python_exec,
            "started_at": self._service_started_at,
            "route_stats": route_stat_payload,
            "route_stats_by_courier": route_stats_by_courier,
            "message_stats": message_stats,
            "order_summary": order_summary,
            "accounts": accounts_summary.get("accounts", []),
            "xianguanjia": xgj_settings,
            "risk_control": risk_control,
            "recovery": recovery,
            "recovery_stage": recovery_stage,
            "next_retry_at": next_retry_at,
            "risk_signals": risk_signals,
            "system_running": alive_count > 0,
            "alive_count": alive_count,
            "total_modules": total_modules,
            "service_status": service_status,
        }

    def service_control(self, action: str) -> dict[str, Any]:
        act = str(action or "").strip().lower()
        if act not in {"suspend", "resume", "stop", "start"}:
            return {"success": False, "error": f"Unsupported action: {act}"}

        if act == "suspend":
            stop_result = self.module_console.control(action="stop", target="all")
            self._service_state["suspended"] = True
            self._service_state["stopped"] = False
            self._service_state["updated_at"] = _now_iso()
            return {
                "success": True,
                "action": act,
                "status": "suspended",
                "message": "服务已挂起",
                "result": stop_result,
                "service": dict(self._service_state),
            }

        if act == "stop":
            stop_result = self.module_console.control(action="stop", target="all")
            self._service_state["suspended"] = False
            self._service_state["stopped"] = True
            self._service_state["updated_at"] = _now_iso()
            return {
                "success": True,
                "action": act,
                "status": "stopped",
                "message": "服务已停止",
                "result": stop_result,
                "service": dict(self._service_state),
            }

        start_result = self.module_console.control(action="start", target="all")
        self._service_state["suspended"] = False
        self._service_state["stopped"] = False
        self._service_state["updated_at"] = _now_iso()
        return {
            "success": True,
            "action": act,
            "status": "running",
            "message": "服务已恢复运行" if act == "resume" else "服务已启动",
            "result": start_result,
            "service": dict(self._service_state),
        }

    def service_recover(self, target: str = "presales") -> dict[str, Any]:
        tgt = str(target or "presales").strip().lower()
        if tgt not in MODULE_TARGETS:
            return {"success": False, "error": f"Unsupported target: {tgt}"}

        result = self.module_console.control(action="recover", target=tgt)
        has_error = bool(result.get("error")) if isinstance(result, dict) else True
        status = self.service_status()
        return {
            "success": not has_error,
            "target": tgt,
            "action": "recover",
            "result": result,
            "service_status": status.get("service_status"),
            "xianyu_connected": bool(status.get("xianyu_connected", False)),
            "token_error": status.get("token_error"),
            "cookie_update_required": bool(status.get("cookie_update_required", False)),
            "message": "售前链路恢复完成" if not has_error else f"恢复失败: {result.get('error', 'unknown')}",
        }

    def service_auto_fix(self) -> dict[str, Any]:
        actions: list[str] = []
        status_before = self.service_status()
        svc_state = str(status_before.get("service_status") or "")

        if svc_state == "stopped":
            _ = self.service_control("start")
            actions.append("start_service")
        elif svc_state == "suspended":
            _ = self.service_control("resume")
            actions.append("resume_service")

        if bool(status_before.get("cookie_update_required", False)):
            return {
                "success": False,
                "action": "auto_fix",
                "actions": actions,
                "needs_cookie_update": True,
                "message": "当前为鉴权失效，需先更新 Cookie，系统无法自动修复此项。",
                "status_before": status_before,
                "status_after": self.service_status(),
            }

        recover = self.service_recover("presales")
        actions.append("recover_presales")
        check = self.module_console.check(skip_gateway=True)
        status_after = self.service_status()

        can_work = bool(status_after.get("xianyu_connected", False)) and not bool(
            status_after.get("cookie_update_required", False)
        )
        return {
            "success": bool(can_work),
            "action": "auto_fix",
            "actions": actions,
            "recover": recover,
            "doctor": check,
            "status_before": status_before,
            "status_after": status_after,
            "needs_cookie_update": bool(status_after.get("cookie_update_required", False)),
            "message": "自动修复完成" if can_work else "已执行自动修复，但仍需检查 Cookie 或平台风控状态。",
        }


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>XianyuAutoAgent Control Panel</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      min-height: 100vh;
      padding: 20px;
    }
    .container {
      max-width: 1200px;
      margin: 0 auto;
      background: #fff;
      border-radius: 12px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.3);
      padding: 36px;
    }
    h1 {
      color: #333;
      margin-bottom: 24px;
      font-size: 32px;
    }
    .quickstart {
      margin-bottom: 20px;
      padding: 14px 16px;
      border: 1px solid #dbeafe;
      background: #eff6ff;
      border-radius: 8px;
      color: #1e3a8a;
      font-size: 13px;
      line-height: 1.7;
    }
    .quickstart strong { color: #1d4ed8; }
    .quickstart code { background: #dbeafe; padding: 1px 5px; border-radius: 4px; }
    .action-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 12px;
      margin-bottom: 16px;
    }
    .action-btn {
      border: none;
      padding: 10px 14px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 13px;
      font-weight: 700;
      color: #fff;
      background: #3b82f6;
    }
    .action-btn.warning { background: #f59e0b; }
    .action-btn:hover { opacity: 0.92; }
    .service-box {
      margin-bottom: 26px;
      padding: 18px;
      background: #f8f9fa;
      border-radius: 8px;
      border-left: 4px solid #667eea;
    }
    .service-title {
      color: #333;
      margin-bottom: 12px;
      font-size: 20px;
      font-weight: 700;
    }
    .service-row {
      display: flex;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
    }
    .badge {
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 700;
      color: #fff;
      background: #28a745;
    }
    .service-btn {
      border: none;
      padding: 9px 16px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 600;
      transition: all 0.2s ease;
    }
    .service-btn:hover { transform: translateY(-1px); }
    .btn-suspend { background: #ffc107; color: #333; }
    .btn-resume { background: #28a745; color: #fff; }
    .btn-start { background: #1f9d55; color: #fff; }
    .btn-stop { background: #dc3545; color: #fff; }
    .service-msg {
      margin-top: 10px;
      color: #666;
      font-size: 12px;
    }
    .btn-note {
      margin-top: 8px;
      color: #6b7280;
      font-size: 12px;
      line-height: 1.6;
    }

    .module-box {
      margin-bottom: 24px;
      padding: 18px;
      background: #f8f9fa;
      border-radius: 8px;
      border-left: 4px solid #764ba2;
    }
    .module-title {
      color: #333;
      margin-bottom: 14px;
      font-size: 20px;
      font-weight: 700;
    }
    .module-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
      gap: 12px;
    }
    .module-card {
      background: #fff;
      border-radius: 8px;
      padding: 14px;
      border: 2px solid #e0e0e0;
      transition: all 0.2s ease;
      cursor: pointer;
    }
    .module-card:hover {
      border-color: #667eea;
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    .module-card h3 {
      margin-bottom: 4px;
      color: #333;
      font-size: 16px;
    }
    .module-card p { color: #666; font-size: 12px; }

    .status-box {
      background: #f8f9fa;
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 14px;
      border-left: 4px solid #667eea;
    }
    .status-box h2 {
      color: #333;
      font-size: 18px;
      margin-bottom: 12px;
    }
    .status-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 0;
      border-bottom: 1px solid #e5e7eb;
      gap: 10px;
    }
    .status-item:last-child { border-bottom: none; }
    .status-label { color: #4b5563; font-size: 14px; }
    .status-value { font-size: 14px; font-weight: 600; }
    .status-value.success { color: #28a745; }
    .status-value.warning { color: #f59e0b; }
    .status-value.error { color: #dc3545; }
    .status-value.info { color: #0ea5e9; }

    .refresh-btn {
      width: 100%;
      background: #667eea;
      color: #fff;
      border: none;
      padding: 10px 14px;
      border-radius: 6px;
      cursor: pointer;
      margin-top: 10px;
      font-weight: 600;
      font-size: 14px;
    }
    .refresh-btn:hover { background: #5568d3; }

    .charts-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
      gap: 16px;
      margin-top: 24px;
    }
    .chart-box {
      background: #fff;
      border-radius: 8px;
      padding: 16px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
      border: 1px solid #e5e7eb;
    }
    .chart-box h3 {
      color: #333;
      font-size: 16px;
      margin-bottom: 10px;
      text-align: center;
    }
    .chart-container { position: relative; height: 280px; }
    .chart-info {
      margin-bottom: 8px;
      color: #666;
      font-size: 12px;
      text-align: center;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>XianyuAutoAgent Control Panel</h1>
    <div class="quickstart">
      <strong>3步上手（推荐）</strong><br>
      1. 配置管理里导入 Cookie。<br>
      2. 配置管理里导入路线数据与加价数据。<br>
      3. 首页点“启动服务”并执行“全链路体检”。<br>
      体检失败时：先更新 Cookie，再点“售前一键恢复”。<br>
    </div>
    <div class="quickstart">
      <strong>0基础快速上手（建议按顺序）</strong><br>
      1. 先点“配置管理”填写 Cookie。<br>
      2. 在“路线数据”导入报价表。<br>
      3. 在“测试调试”里先验证报价与回复。<br>
      4. 回到首页启动服务，确认状态为“运行中”。<br>
      5. 用“日志查看/实时日志”排查问题。<br>
      默认面板地址：<code>http://127.0.0.1:8091</code>
    </div>

    <div class="status-box" style="border-left-color:#0ea5e9;">
      <h2>系统概览条</h2>
      <div id="systemOverviewStrip"></div>
    </div>

    <div class="service-box">
      <div class="service-title">服务控制</div>
      <div class="service-row">
        <span style="color:#666;font-size:14px;">服务状态：</span>
        <span id="serviceStatusBadge" class="badge">运行中</span>
        <button id="suspendBtn" class="service-btn btn-suspend" title="临时暂停自动处理消息，不会退出程序" onclick="controlService('suspend')">挂起服务</button>
        <button id="resumeBtn" class="service-btn btn-resume" title="从挂起状态恢复自动处理" onclick="controlService('resume')" style="display:none;">恢复服务</button>
        <button id="startBtn" class="service-btn btn-start" title="服务已停止时重新启动" onclick="controlService('start')" style="display:none;">启动服务</button>
        <button id="stopBtn" class="service-btn btn-stop" title="停止自动处理（需手动再启动）" onclick="controlService('stop')">关闭服务</button>
      </div>
      <div class="btn-note">按钮说明：挂起适合临时停；关闭是完全停；恢复/启动用于继续运行。</div>
      <div id="serviceStatusMessage" class="service-msg"></div>
    </div>

    <div class="module-box">
      <div class="module-title">功能模块</div>
      <div class="module-grid">
        <div class="module-card" onclick="window.location.href='/cookie'">
          <h3>配置管理</h3>
          <p>Cookie、路线数据、回复模板</p>
        </div>
        <div class="module-card" onclick="window.location.href='/test'">
          <h3>测试调试</h3>
          <p>测试自动回复与报价结果</p>
        </div>
        <div class="module-card" onclick="window.location.href='/logs'">
          <h3>日志查看</h3>
          <p>分页检索历史日志</p>
        </div>
        <div class="module-card" onclick="window.location.href='/logs/realtime'">
          <h3>实时日志</h3>
          <p>实时监控运行状态</p>
        </div>
      </div>
    </div>

    <div class="status-box">
      <h2>系统运行状况</h2>
      <div id="systemStatusContent"></div>
    </div>

    <div class="status-box">
      <h2>咸鱼客服状态</h2>
      <div id="xianyuStatusContent"></div>
    </div>

    <div class="status-box">
      <h2>路线数据情况</h2>
      <div id="routeStatusContent"></div>
    </div>

    <div class="status-box">
      <h2>消息回复统计</h2>
      <div id="messageStatusContent"></div>
    </div>

    <div class="status-box">
      <h2>Wave C 虚拟商品总览</h2>
      <div id="virtualGoodsMetricsContent"></div>
      <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
        <input id="inspectOrderId" type="text" placeholder="输入订单号查看 drill-down" style="flex:1;min-width:260px;padding:8px;border:1px solid #d1d5db;border-radius:6px;">
        <button class="action-btn" onclick="inspectVirtualGoodsOrder()">inspect_order</button>
      </div>
      <div id="virtualGoodsInspectContent" style="margin-top:10px;color:#374151;font-size:12px;line-height:1.7;white-space:pre-wrap;"></div>
    </div>

    <div class="status-box">
      <h2>闲管家自动履约</h2>
      <div id="xgjStatusContent"></div>
      <div style="margin-top:12px; display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:12px;">
        <div style="border:1px solid #e5e7eb; border-radius:8px; padding:12px; background:#f8fafc;">
          <div style="font-weight:700; margin-bottom:10px;">连接与开关</div>
          <input id="xgjAppKey" type="text" placeholder="AppKey" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <input id="xgjAppSecret" type="password" placeholder="AppSecret（留空表示不改）" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <input id="xgjMerchantId" type="text" placeholder="Merchant ID（可选）" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <input id="xgjBaseUrl" type="text" placeholder="Base URL" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <label style="display:block; margin:6px 0; color:#374151;"><input id="xgjAutoPriceEnabled" type="checkbox"> 启用 API 改价通道</label>
          <label style="display:block; margin:6px 0; color:#374151;"><input id="xgjAutoShipEnabled" type="checkbox"> 启用自动物流发货</label>
          <label style="display:block; margin:6px 0 10px; color:#374151;"><input id="xgjAutoShipOnPaid" type="checkbox"> 支付后自动触发履约</label>
          <button class="action-btn" style="width:100%;" onclick="saveXgjSettings()">保存闲管家设置</button>
        </div>
        <div style="border:1px solid #e5e7eb; border-radius:8px; padding:12px; background:#f8fafc;">
          <div style="font-weight:700; margin-bottom:10px;">手动重试改价</div>
          <input id="xgjRetryProductId" type="text" placeholder="商品 ID" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <input id="xgjRetryNewPrice" type="number" min="0" step="0.01" placeholder="新价格" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <input id="xgjRetryOldPrice" type="number" min="0" step="0.01" placeholder="原价（可选）" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <button class="action-btn" style="width:100%;" onclick="retryXgjPrice()">提交 API 改价</button>
        </div>
        <div style="border:1px solid #e5e7eb; border-radius:8px; padding:12px; background:#f8fafc;">
          <div style="font-weight:700; margin-bottom:10px;">手动重试发货</div>
          <input id="xgjRetryOrderId" type="text" placeholder="订单号" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <input id="xgjRetryWaybillNo" type="text" placeholder="物流单号" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <input id="xgjRetryExpressName" type="text" placeholder="快递公司名称（如 圆通）" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <input id="xgjRetryExpressCode" type="text" placeholder="快递编码（可选）" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <button class="action-btn warning" style="width:100%;" onclick="retryXgjShip()">提交 API 发货</button>
        </div>
      </div>
    </div>

    <div class="action-row">
      <button class="refresh-btn" onclick="loadStatus()">刷新所有状态</button>
      <button class="action-btn" onclick="runFullCheck()">全链路体检</button>
      <button class="action-btn" onclick="runAutoFix()">一键修复</button>
      <button class="action-btn warning" onclick="recoverPresales()">售前一键恢复</button>
    </div>

    <div class="status-box" id="doctorStatusBox" style="display:none;">
      <h2>全链路体检结果</h2>
      <div id="doctorStatusContent"></div>
    </div>

    <div class="charts-grid" id="chartsContainer" style="display:none;">
      <div class="chart-box">
        <h3>最近24小时回复趋势</h3>
        <div class="chart-container"><canvas id="hourlyChart"></canvas></div>
      </div>
      <div class="chart-box">
        <h3>最近7天回复统计</h3>
        <div class="chart-container"><canvas id="dailyChart"></canvas></div>
      </div>
      <div class="chart-box">
        <h3>快递公司路线分布</h3>
        <div class="chart-container"><canvas id="courierChart"></canvas></div>
      </div>
      <div class="chart-box">
        <h3>路线数据概览</h3>
        <div id="routeChartInfo" class="chart-info"></div>
        <div class="chart-container"><canvas id="routeChart"></canvas></div>
      </div>
    </div>
  </div>

  <script>
    let hourlyChart = null;
    let dailyChart = null;
    let courierChart = null;
    let routeChart = null;

    function statusClassByBool(v) {
      return v ? "success" : "error";
    }

    function statusClassByService(v) {
      if (v === "running") return "success";
      if (v === "degraded") return "warning";
      if (v === "suspended") return "warning";
      return "error";
    }

    function statusClassByRisk(level) {
      if (level === "blocked") return "error";
      if (level === "warning") return "warning";
      if (level === "normal") return "success";
      return "info";
    }

    function statusClassByRecovery(stage) {
      if (stage === "healthy") return "success";
      if (stage === "recover_triggered") return "warning";
      if (stage === "waiting_cookie_update" || stage === "waiting_reconnect") return "warning";
      if (stage === "inactive") return "info";
      return "info";
    }

    function recoveryStageText(stage, stageLabel) {
      const s = String(stage || "").trim();
      if (stageLabel) return String(stageLabel);
      if (s === "healthy") return "链路正常";
      if (s === "recover_triggered") return "已触发自动恢复";
      if (s === "waiting_cookie_update") return "等待更新 Cookie";
      if (s === "waiting_reconnect") return "等待重连";
      if (s === "token_error") return "鉴权异常";
      if (s === "inactive") return "服务未运行";
      if (s === "monitoring") return "监控中";
      return "状态未知";
    }

    function row(label, value, cls) {
      return (
        '<div class="status-item">' +
        '<span class="status-label">' + label + "</span>" +
        '<span class="status-value ' + (cls || "info") + '">' + value + "</span>" +
        "</div>"
      );
    }

    function formatCount(n) {
      const val = Number(n || 0);
      return Number.isFinite(val) ? val.toLocaleString() : "0";
    }

    function updateServiceStatus(status) {
      const badge = document.getElementById("serviceStatusBadge");
      const suspendBtn = document.getElementById("suspendBtn");
      const resumeBtn = document.getElementById("resumeBtn");
      const startBtn = document.getElementById("startBtn");
      const stopBtn = document.getElementById("stopBtn");
      const messageEl = document.getElementById("serviceStatusMessage");

      if (status === "running") {
        badge.textContent = "运行中";
        badge.style.background = "#28a745";
        suspendBtn.style.display = "inline-block";
        resumeBtn.style.display = "none";
        startBtn.style.display = "none";
        stopBtn.style.display = "inline-block";
        messageEl.textContent = "服务正在运行，正常处理消息";
      } else if (status === "degraded") {
        badge.textContent = "降级运行";
        badge.style.background = "#f59e0b";
        suspendBtn.style.display = "inline-block";
        resumeBtn.style.display = "none";
        startBtn.style.display = "none";
        stopBtn.style.display = "inline-block";
        messageEl.textContent = "服务在运行，但鉴权或风控异常导致自动回复受限";
      } else if (status === "suspended") {
        badge.textContent = "已挂起";
        badge.style.background = "#f59e0b";
        suspendBtn.style.display = "none";
        resumeBtn.style.display = "inline-block";
        startBtn.style.display = "none";
        stopBtn.style.display = "inline-block";
        messageEl.textContent = "服务已挂起，不会处理新消息";
      } else {
        badge.textContent = "已停止";
        badge.style.background = "#dc3545";
        suspendBtn.style.display = "none";
        resumeBtn.style.display = "none";
        startBtn.style.display = "inline-block";
        stopBtn.style.display = "none";
        messageEl.textContent = "服务已停止";
      }
    }

    function controlService(action) {
      if (action === "stop" && !confirm("确定要关闭服务吗？")) return;

      fetch("/api/service/control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: action })
      })
      .then(r => r.json())
      .then(data => {
        if (!data.success) throw new Error(data.error || "操作失败");
        updateServiceStatus(data.status || "running");
        loadStatus();
      })
      .catch(err => alert("操作失败: " + err.message));
    }

    function buildHourlySeries(hourlyMap) {
      const labels = [];
      const values = [];
      for (let i = 0; i < 24; i++) {
        const h = String(i).padStart(2, "0");
        labels.push(h + ":00");
        values.push(Number((hourlyMap || {})[h] || 0));
      }
      return { labels, values };
    }

    function buildDailySeries(dailyMap) {
      const localDateKey = (d) => {
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, "0");
        const day = String(d.getDate()).padStart(2, "0");
        return y + "-" + m + "-" + day;
      };
      const labels = [];
      const values = [];
      for (let i = 6; i >= 0; i--) {
        const d = new Date();
        d.setDate(d.getDate() - i);
        const key = localDateKey(d);
        labels.push((d.getMonth() + 1) + "/" + d.getDate());
        values.push(Number((dailyMap || {})[key] || 0));
      }
      return { labels, values };
    }

    function renderCharts(data) {
      const messageStats = data.message_stats || {};
      const routeByCourier = data.route_stats_by_courier || {};
      const routeStats = data.route_stats || {};
      document.getElementById("chartsContainer").style.display = "grid";

      const hourly = buildHourlySeries(messageStats.hourly_replies || {});
      const daily = buildDailySeries(messageStats.daily_replies || {});

      if (hourlyChart) hourlyChart.destroy();
      hourlyChart = new Chart(document.getElementById("hourlyChart").getContext("2d"), {
        type: "line",
        data: {
          labels: hourly.labels,
          datasets: [{
            label: "回复数",
            data: hourly.values,
            borderColor: "#667eea",
            backgroundColor: "rgba(102,126,234,0.15)",
            fill: true,
            tension: 0.35
          }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
      });

      if (dailyChart) dailyChart.destroy();
      dailyChart = new Chart(document.getElementById("dailyChart").getContext("2d"), {
        type: "bar",
        data: {
          labels: daily.labels,
          datasets: [{ label: "回复数", data: daily.values, backgroundColor: "#764ba2" }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
      });

      const courierLabels = Object.keys(routeByCourier);
      const courierData = Object.values(routeByCourier);
      if (courierChart) courierChart.destroy();
      courierChart = new Chart(document.getElementById("courierChart").getContext("2d"), {
        type: "doughnut",
        data: {
          labels: courierLabels.length ? courierLabels : ["暂无数据"],
          datasets: [{
            data: courierData.length ? courierData : [1],
            backgroundColor: ["#667eea", "#764ba2", "#f093fb", "#4facfe", "#43e97b", "#fa709a"]
          }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom" } } }
      });

      document.getElementById("routeChartInfo").textContent =
        "总路线数: " + formatCount(routeStats.routes) + " 条 | 快递公司数: " + formatCount(routeStats.couriers) + " 家";

      if (routeChart) routeChart.destroy();
      routeChart = new Chart(document.getElementById("routeChart").getContext("2d"), {
        type: "bar",
        data: {
          labels: ["快递公司", "路线总数"],
          datasets: [{
            data: [Number(routeStats.couriers || 0), Number(routeStats.routes || 0)],
            backgroundColor: ["#667eea", "#764ba2"]
          }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
      });
    }

    function renderStatusBlocks(data) {
      const routeStats = data.route_stats || {};
      const msgStats = data.message_stats || {};
      const xgj = data.xianguanjia || {};
      const modules = (data.module && data.module.modules) || {};
      const risk = data.risk_control || {};
      const aliveCount = Number(data.alive_count || 0);
      const totalModules = Number(data.total_modules || 0);

      document.getElementById("systemOverviewStrip").innerHTML = [
        row("service_status", data.service_status || "-", statusClassByService(data.service_status)),
        row("alive_count/total_modules", formatCount(aliveCount) + " / " + formatCount(totalModules), aliveCount > 0 ? "success" : "warning"),
        row("cookie_exists", data.cookie_exists ? "true" : "false", statusClassByBool(!!data.cookie_exists)),
        row("xianyu_connected", data.xianyu_connected ? "true" : "false", statusClassByBool(!!data.xianyu_connected)),
        row("token_available", data.token_available ? "true" : "false", statusClassByBool(!!data.token_available)),
        row("recovery_stage", data.recovery_stage || "-", statusClassByRecovery(data.recovery_stage || "monitoring"))
      ].join("");

      document.getElementById("systemStatusContent").innerHTML = [
        row("系统运行", data.system_running ? "运行中" : "未运行", statusClassByBool(!!data.system_running)),
        row("服务状态", data.service_status || "unknown", statusClassByService(data.service_status)),
        row("模块在线", formatCount(aliveCount) + " / " + formatCount(totalModules), aliveCount > 0 ? "success" : "warning"),
        row("启动时间", data.service_start_time || "-", "info")
      ].join("");

      const presalesAlive = !!((modules.presales || {}).process || {}).alive;
      const riskLevel = String(risk.level || "unknown");
      const riskScore = Number(risk.score || 0);
      const signalText = Array.isArray(risk.signals) && risk.signals.length ? risk.signals.join(" | ") : "-";
      const riskEvent = ((risk.last_event_at || "") + " " + (risk.last_event || "-")).trim();
      const tokenError = data.token_error || "-";
      const recovery = data.recovery || {};
      const recoveryStage = String(recovery.stage || "monitoring");
      const recoveryStageLabel = String(recovery.stage_label || "");
      const recoveryTriggered = !!recovery.auto_recover_triggered;
      const recoveryReason = String(recovery.reason || "-");
      const recoveryAdvice = String(recovery.advice || "-");
      const recoveryAt = String(recovery.last_auto_recover_at || "-");
      document.getElementById("xianyuStatusContent").innerHTML = [
        row("Cookie存在", data.cookie_exists ? "是" : "否", statusClassByBool(!!data.cookie_exists)),
        row("Cookie长度", formatCount(data.cookie_length || 0), "info"),
        row("售前模块进程", presalesAlive ? "已连接" : "未连接", statusClassByBool(presalesAlive)),
        row("闲鱼链路连接", data.xianyu_connected ? "可用" : "不可用", statusClassByBool(!!data.xianyu_connected)),
        row("Token可用", data.token_available ? "是" : "否", statusClassByBool(!!data.token_available)),
        row("Token异常", tokenError, tokenError === "-" ? "info" : "error"),
        row("需更新Cookie", data.cookie_update_required ? "是" : "否", data.cookie_update_required ? "warning" : "success"),
        row("封控状态", risk.label || "未知", statusClassByRisk(riskLevel)),
        row("风险分/信号", String(riskScore) + " / " + signalText, statusClassByRisk(riskLevel)),
        row("最近封控事件", riskEvent, riskLevel === "blocked" ? "error" : "info"),
        row("恢复阶段", recoveryStageText(recoveryStage, recoveryStageLabel), statusClassByRecovery(recoveryStage)),
        row("自动恢复触发", recoveryTriggered ? "是" : "否", recoveryTriggered ? "warning" : "info"),
        row("恢复原因", recoveryReason, "info"),
        row("建议操作", recoveryAdvice, "info"),
        row("最近恢复时间", recoveryAt, "info")
      ].join("");

      document.getElementById("routeStatusContent").innerHTML = [
        row("快递公司数", formatCount(routeStats.couriers || 0), "info"),
        row("路线总数", formatCount(routeStats.routes || 0), "info"),
        row("最后更新", routeStats.last_updated || "-", "info")
      ].join("");

      document.getElementById("messageStatusContent").innerHTML = [
        row("累计回复", formatCount(msgStats.total_replied || 0), "info"),
        row("今日回复", formatCount(msgStats.today_replied || 0), "info"),
        row("最近事件", formatCount(msgStats.recent_replied || 0), "info"),
        row("会话数量", formatCount(msgStats.total_conversations || 0), "info")
      ].join("");

      document.getElementById("xgjStatusContent").innerHTML = [
        row("凭证状态", xgj.configured ? "已配置" : "未配置", xgj.configured ? "success" : "warning"),
        row("API 地址", xgj.base_url || "-", "info"),
        row("自动改价", xgj.auto_price_enabled ? "开启" : "关闭", xgj.auto_price_enabled ? "success" : "warning"),
        row("自动发货", xgj.auto_ship_enabled ? "开启" : "关闭", xgj.auto_ship_enabled ? "success" : "warning"),
        row("支付后自动触发", xgj.auto_ship_on_paid ? "开启" : "关闭", xgj.auto_ship_on_paid ? "success" : "warning"),
        row("订单推送地址", xgj.callback_url || "/api/orders/callback", "info")
      ].join("");

      document.getElementById("xgjAppKey").value = xgj.app_key || "";
      document.getElementById("xgjMerchantId").value = xgj.merchant_id || "";
      document.getElementById("xgjBaseUrl").value = xgj.base_url || "https://open.goofish.pro";
      document.getElementById("xgjAppSecret").value = "";
      document.getElementById("xgjAutoPriceEnabled").checked = !!xgj.auto_price_enabled;
      document.getElementById("xgjAutoShipEnabled").checked = !!xgj.auto_ship_enabled;
      document.getElementById("xgjAutoShipOnPaid").checked = !!xgj.auto_ship_on_paid;
    }

    async function saveXgjSettings() {
      try {
        const res = await fetch("/api/xgj/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            app_key: document.getElementById("xgjAppKey").value.trim(),
            app_secret: document.getElementById("xgjAppSecret").value.trim(),
            merchant_id: document.getElementById("xgjMerchantId").value.trim(),
            base_url: document.getElementById("xgjBaseUrl").value.trim(),
            auto_price_enabled: document.getElementById("xgjAutoPriceEnabled").checked,
            auto_ship_enabled: document.getElementById("xgjAutoShipEnabled").checked,
            auto_ship_on_paid: document.getElementById("xgjAutoShipOnPaid").checked
          })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "保存失败");
        await loadStatus();
        alert(data.message || "闲管家设置已保存");
      } catch (err) {
        alert("保存失败: " + err.message);
      }
    }

    async function retryXgjPrice() {
      try {
        const res = await fetch("/api/xgj/retry-price", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            product_id: document.getElementById("xgjRetryProductId").value.trim(),
            new_price: document.getElementById("xgjRetryNewPrice").value.trim(),
            original_price: document.getElementById("xgjRetryOldPrice").value.trim()
          })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "改价失败");
        alert("改价成功，通道: " + (data.channel || "unknown"));
      } catch (err) {
        alert("改价失败: " + err.message);
      }
    }

    async function retryXgjShip() {
      try {
        const res = await fetch("/api/xgj/retry-ship", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            order_id: document.getElementById("xgjRetryOrderId").value.trim(),
            waybill_no: document.getElementById("xgjRetryWaybillNo").value.trim(),
            express_name: document.getElementById("xgjRetryExpressName").value.trim(),
            express_code: document.getElementById("xgjRetryExpressCode").value.trim()
          })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "发货失败");
        alert("发货结果: " + ((data.delivery && data.delivery.message) || data.status || "success"));
      } catch (err) {
        alert("发货失败: " + err.message);
      }
    }

    function renderVirtualGoodsMetrics(payload) {
      const box = document.getElementById("virtualGoodsMetricsContent");
      if (!payload || !payload.success) {
        box.innerHTML = [row("模块状态", "未就绪", "warning"), row("原因", (payload && payload.error) || "-", "info")].join("");
        return;
      }

      const panels = payload.dashboard_panels || {};
      const funnel = panels.operations_funnel_overview || {};
      const exceptionPool = panels.exception_priority_pool || {};
      const efficiency = panels.fulfillment_efficiency || {};
      const productOps = panels.product_operations || {};
      const productSummary = productOps.summary || {};
      const productFieldState = productOps.field_state || {};
      const drillDown = panels.drill_down || {};

      const exceptionItems = Array.isArray(exceptionPool.items) ? exceptionPool.items : [];
      const exceptionPreview = exceptionItems
        .slice(0, 3)
        .map((x) => [x.priority || "P1", x.type || "UNKNOWN", "x" + formatCount(x.count || 0)].join(" "))
        .join(" | ") || "-";

      const stableFields = ["exposure_count","paid_order_count","paid_amount_cents","refund_order_count","exception_count","manual_takeover_count","conversion_rate_pct"];
      const productSummaryText = stableFields.map((k) => {
        const state = productFieldState[k] || "placeholder";
        const val = productSummary[k];
        return state === "available" ? (k + "=" + String(val)) : (k + "=占位(禁用态)");
      }).join(" | ");

      const stageTotals = funnel.stage_totals || {};
      const funnelSummaryText = Object.keys(stageTotals).length
        ? Object.entries(stageTotals).map(([k, v]) => k + ":" + formatCount(v)).join(" | ")
        : "暂无漏斗数据";

      box.innerHTML = [
        row("运营漏斗总览", funnelSummaryText, "info"),
        row("异常优先级池", "数量 " + formatCount(exceptionPool.total_items || 0) + " | " + exceptionPreview, Number(exceptionPool.total_items || 0) > 0 ? "warning" : "success"),
        row("履约效率", "已履约 " + formatCount(efficiency.fulfilled_orders || 0) + " | 失败 " + formatCount(efficiency.failed_orders || 0) + " | 履约率 " + String(efficiency.fulfillment_rate_pct || 0) + "%", "info"),
        row("商品运营", productSummaryText, "info"),
        row("成品化 Drill-down", (drillDown.message || "输入订单号查看明细") + "（参数: " + (drillDown.query_key || "order_id") + "）", "info")
      ].join("");
    }

    async function inspectVirtualGoodsOrder() {
      const orderId = (document.getElementById("inspectOrderId").value || "").trim();
      const box = document.getElementById("virtualGoodsInspectContent");
      if (!orderId) {
        box.textContent = "请输入订单号";
        return;
      }
      box.textContent = "加载中...";
      try {
        const res = await fetch("/api/virtual-goods/inspect-order?order_id=" + encodeURIComponent(orderId));
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "inspect_order failed");
        const view = data.drill_down_view || {};
        const currentStatus = view.current_status || {};
        const callbackChain = Array.isArray(view.callback_chain) ? view.callback_chain : [];
        const claimReplayTrace = Array.isArray(view.claim_replay_trace) ? view.claim_replay_trace : [];
        const manualTakeover = view.manual_takeover || {};
        const recentErrors = Array.isArray(view.recent_errors) ? view.recent_errors : [];
        const exceptionPool = view.exception_priority_pool || {};
        const exceptionItems = Array.isArray(exceptionPool.items) ? exceptionPool.items : [];
        const actions = Array.isArray(view.actions) ? view.actions : [];

        const exceptionSummary = exceptionItems.map((x) => {
          return (x.priority || "P1") + " " + (x.type || "UNKNOWN") + " x" + String(x.count || 0) + " - " + (x.summary || "");
        }).join("\\n") || "无异常项";

        const callbackSummary = callbackChain.slice(0, 8).map((x) => {
          return "#" + String(x.step || 0) + " | kind=" + (x.event_kind || "-") + " | verify=" + (x.verify_passed ? "Y" : "N") + " | processed=" + (x.processed ? "Y" : "N");
        }).join("\\n") || "无回调链";

        const replaySummary = claimReplayTrace.slice(0, 8).map((x) => {
          return "callback_id=" + String(x.callback_id || 0) + " | event_id=" + (x.external_event_id || "-") + " | dedupe=" + (x.dedupe_key || "-") + " | attempt=" + String(x.attempt_count || 0);
        }).join("\\n") || "无 claim-replay 轨迹";

        const errorSummary = recentErrors.map((x) => {
          return "callback_id=" + String(x.callback_id || 0) + " | kind=" + (x.event_kind || "-") + " | error=" + (x.error || "-") + " | at=" + (x.at || "-");
        }).join("\\n") || "无最近错误";

        const actionSummary = actions.map((x) => {
          return (x.name || "action") + "=" + (x.enabled ? "enabled" : "disabled") + "(" + (x.reason || "-") + ")";
        }).join("\\n") || "无动作";

        box.textContent = [
          "【当前状态】",
          "订单号: " + (currentStatus.xianyu_order_id || orderId),
          "订单状态: " + (currentStatus.order_status || "-"),
          "履约状态: " + (currentStatus.fulfillment_status || "-"),
          "更新时间: " + (currentStatus.updated_at || "-"),
          "",
          "【异常优先级池】",
          exceptionSummary,
          "",
          "【回调链】",
          callbackSummary,
          "",
          "【claim-replay轨迹】",
          replaySummary,
          "",
          "【manual_takeover】",
          "enabled=" + (manualTakeover.enabled ? "true" : "false") + " | reason=" + (manualTakeover.reason || "-"),
          "",
          "【最近错误】",
          errorSummary,
          "",
          "【可执行动作（禁用态）】",
          actionSummary
        ].join("\\n");
      } catch (err) {
        box.textContent = "inspect_order 失败: " + err.message;
      }
    }

    function loadStatus() {
      fetch("/api/status")
      .then(r => r.json())
      .then(async data => {
        if (data.error) throw new Error(data.error);
        updateServiceStatus(data.service_status || "running");
        renderStatusBlocks(data);
        renderCharts(data);
        try {
          const vgRes = await fetch("/api/virtual-goods/metrics");
          const vgData = await vgRes.json();
          renderVirtualGoodsMetrics(vgData);
        } catch (e) {
          renderVirtualGoodsMetrics({ success: false, error: e.message || "metrics unavailable" });
        }
      })
      .catch(err => {
        document.getElementById("systemStatusContent").innerHTML = row("错误", err.message, "error");
      });
    }

    function renderDoctorStatus(data) {
      const box = document.getElementById("doctorStatusBox");
      const el = document.getElementById("doctorStatusContent");
      box.style.display = "block";

      const ready = !!data.ready;
      const blockers = Array.isArray(data.blockers) ? data.blockers : [];
      const nextSteps = Array.isArray(data.next_steps) ? data.next_steps : [];
      const summary = data.doctor_summary || {};
      const statusText = ready ? "通过" : "未通过";
      const statusClass = ready ? "success" : "error";
      const blockerNames = blockers
        .slice(0, 4)
        .map(item => {
          const target = item && item.target ? "[" + item.target + "] " : "";
          return target + String(item.name || "unknown");
        })
        .join(" | ") || "-";
      const stepText = nextSteps.slice(0, 3).join(" | ") || "无";

      el.innerHTML = [
        row("体检状态", statusText, statusClass),
        row("关键失败", String(summary.critical_failed || 0), Number(summary.critical_failed || 0) > 0 ? "error" : "success"),
        row("警告项", String(summary.warning_failed || 0), Number(summary.warning_failed || 0) > 0 ? "warning" : "success"),
        row("阻塞项", blockerNames, blockers.length > 0 ? "warning" : "success"),
        row("建议动作", stepText, "info"),
      ].join("");
    }

    async function runFullCheck() {
      try {
        const res = await fetch("/api/module/check?skip_gateway=1");
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        renderDoctorStatus(data);
      } catch (err) {
        alert("体检失败: " + err.message);
      }
    }

    async function recoverPresales() {
      try {
        const res = await fetch("/api/service/recover", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ target: "presales" })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || data.message || "恢复失败");
        await loadStatus();
        alert("售前恢复已触发。当前状态: " + (data.service_status || "unknown"));
      } catch (err) {
        alert("恢复失败: " + err.message);
      }
    }

    async function runAutoFix() {
      try {
        const res = await fetch("/api/service/auto-fix", { method: "POST" });
        const data = await res.json();
        await loadStatus();
        if (data.success) {
          alert("一键修复完成: " + (data.message || "成功"));
        } else {
          const msg = data.message || "修复未完成";
          const needCookie = data.needs_cookie_update ? "（请先更新 Cookie）" : "";
          alert("一键修复结果: " + msg + needCookie);
        }
      } catch (err) {
        alert("一键修复失败: " + err.message);
      }
    }

    loadStatus();
    setInterval(loadStatus, 10000);
  </script>
</body>
</html>
"""
MIMIC_COOKIE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>闲鱼自动客服 - Cookie管理</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      min-height: 100vh;
      padding: 20px;
    }
    .container {
      max-width: 980px;
      margin: 0 auto;
      background: white;
      border-radius: 12px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.3);
      padding: 34px;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 22px;
      padding-bottom: 18px;
      border-bottom: 2px solid #e5e7eb;
      gap: 12px;
    }
    h1 { color: #333; font-size: 28px; margin-bottom: 6px; }
    .subtitle { color: #666; font-size: 14px; }
    .back-link {
      color: #667eea;
      text-decoration: none;
      font-size: 14px;
      padding: 8px 14px;
      border-radius: 6px;
      border: 2px solid #667eea;
      transition: all 0.2s ease;
      font-weight: 600;
      white-space: nowrap;
    }
    .back-link:hover {
      background: #667eea;
      color: white;
      transform: translateY(-1px);
    }
    .info-box {
      background: #f8f9fa;
      border-left: 4px solid #667eea;
      padding: 14px;
      border-radius: 4px;
      margin-bottom: 16px;
    }
    .info-box p { margin: 4px 0; font-size: 13px; color: #4b5563; }
    .guide-card {
      background: #eff6ff;
      border: 1px solid #bfdbfe;
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 14px;
      color: #1e3a8a;
      font-size: 13px;
      line-height: 1.7;
    }
    .guide-card strong { color: #1d4ed8; }
    .cookie-help {
      border: 1px solid #dbeafe;
      border-radius: 8px;
      background: #f8fbff;
      padding: 10px 12px;
      margin-bottom: 14px;
    }
    .cookie-help summary {
      cursor: pointer;
      font-size: 13px;
      color: #1d4ed8;
      font-weight: 700;
      outline: none;
    }
    .cookie-help-content {
      margin-top: 10px;
      color: #334155;
      font-size: 12px;
      line-height: 1.75;
    }
    .cookie-help-content p { margin: 2px 0; }
    .cookie-help-tip {
      margin-top: 8px;
      padding: 8px 10px;
      border-radius: 6px;
      background: #fff7ed;
      color: #9a3412;
      border: 1px solid #fed7aa;
      font-size: 12px;
    }
    .current-cookie {
      background: #f8f9fa;
      padding: 12px;
      border-radius: 6px;
      margin-bottom: 16px;
      font-size: 12px;
      color: #666;
      word-break: break-all;
      max-height: 100px;
      overflow-y: auto;
      display: none;
    }
    .tabs {
      display: flex;
      gap: 10px;
      margin-bottom: 18px;
      border-bottom: 2px solid #e5e7eb;
      flex-wrap: wrap;
    }
    .tab {
      padding: 10px 16px;
      cursor: pointer;
      border: none;
      background: none;
      color: #6b7280;
      border-bottom: 2px solid transparent;
      font-size: 14px;
      font-weight: 600;
    }
    .tab.active {
      color: #667eea;
      border-bottom-color: #667eea;
    }
    .tab-content { display: none; }
    .tab-content.active { display: block; }
    .section {
      margin-bottom: 24px;
      padding-bottom: 20px;
      border-bottom: 1px solid #e5e7eb;
    }
    .section:last-child { border-bottom: none; }
    .section-title {
      font-size: 20px;
      color: #333;
      margin-bottom: 14px;
      padding-bottom: 8px;
      border-bottom: 2px solid #667eea;
    }
    .form-group { margin-bottom: 14px; }
    label {
      display: block;
      margin-bottom: 7px;
      color: #333;
      font-size: 14px;
      font-weight: 600;
    }
    textarea, input[type="file"] {
      width: 100%;
      padding: 12px;
      border: 2px solid #e5e7eb;
      border-radius: 6px;
      font-size: 14px;
      transition: border-color 0.2s ease;
    }
    textarea {
      font-family: "SFMono-Regular", Menlo, Consolas, monospace;
      resize: vertical;
      min-height: 150px;
    }
    textarea:focus, input[type="file"]:focus {
      outline: none;
      border-color: #667eea;
    }
    .hint { margin-top: 6px; font-size: 12px; color: #6b7280; }
    .inline-note {
      margin-top: 8px;
      color: #6b7280;
      font-size: 12px;
      line-height: 1.6;
    }
    .button-group {
      display: flex;
      gap: 10px;
      margin-top: 14px;
      flex-wrap: wrap;
    }
    button {
      border: none;
      padding: 10px 16px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 600;
      transition: all 0.2s ease;
    }
    button:disabled { opacity: 0.6; cursor: not-allowed; }
    .btn-primary {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: #fff;
    }
    .btn-secondary { background: #f3f4f6; color: #1f2937; }
    .btn-danger { background: #dc3545; color: #fff; }
    .btn-primary:hover, .btn-secondary:hover, .btn-danger:hover { transform: translateY(-1px); }
    .panel {
      margin-top: 16px;
      background: #f8f9fa;
      border-radius: 6px;
      padding: 12px;
      font-size: 13px;
      color: #374151;
      line-height: 1.6;
      display: none;
      white-space: pre-line;
    }
    .message {
      margin-top: 18px;
      padding: 12px;
      border-radius: 6px;
      font-size: 14px;
      display: none;
      white-space: pre-line;
      line-height: 1.6;
    }
    .message.success {
      background: #d4edda;
      color: #155724;
      border: 1px solid #c3e6cb;
    }
    .message.error {
      background: #f8d7da;
      color: #721c24;
      border: 1px solid #f5c6cb;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <h1>闲鱼自动客服</h1>
        <p class="subtitle">Cookie管理与系统配置</p>
      </div>
      <a href="/" class="back-link">← 返回首页</a>
    </div>

    <div class="guide-card">
      <strong>Cookie 极简流程（默认推荐）</strong><br>
      1. 上传插件导出的 <code>cookies.txt / JSON / ZIP</code>，点击“上传并一键更新”。<br>
      2. 或者直接粘贴 Cookie 字符串，点击“粘贴并更新”。<br>
      3. 更新后回首页点“刷新状态”，看连接是否正常。<br>
      需要详细说明时，再展开下方“高级选项”。
    </div>

    <div id="currentCookie" class="current-cookie"><strong>当前Cookie：</strong> <span id="currentCookieText"></span></div>

    <div class="tabs">
      <button class="tab active" onclick="switchTab('cookie', this)">Cookie</button>
      <button class="tab" onclick="switchTab('routes', this)">路线数据</button>
      <button class="tab" onclick="switchTab('markup', this)">加价数据</button>
      <button class="tab" onclick="switchTab('template', this)">回复模板</button>
    </div>

    <div id="cookieTab" class="tab-content active">
      <div class="section">
        <h2 class="section-title">Cookie管理（极简）</h2>
        <div class="form-group">
          <label for="cookiePluginFile">插件导出文件（支持多选）</label>
          <input type="file" id="cookiePluginFile" accept=".txt,.json,.log,.cookies,.csv,.tsv,.har,.zip" multiple>
          <div class="hint">推荐：上传插件导出的 cookies.txt/JSON（也支持 csv/tsv/har/zip，自动识别）。</div>
        </div>
        <div class="form-group">
          <label for="cookie">Cookie字符串</label>
          <textarea id="cookie" placeholder="支持直接粘贴表格文本 / Cookie请求头 / cookies.txt / JSON"></textarea>
        </div>
        <div class="button-group">
          <button class="btn-primary" title="上传插件导出文件并自动更新到系统 Cookie" onclick="importCookiePlugin()">上传并一键更新</button>
          <button class="btn-primary" title="保存当前输入的 Cookie 到系统配置" onclick="saveCookie()">粘贴并更新</button>
          <button class="btn-secondary" title="检测 Cookie 可用性分级与修复建议" onclick="diagnoseCookie()">诊断可用性</button>
          <button class="btn-secondary" title="读取当前已保存的 Cookie 到输入框" onclick="loadCurrentCookie()">查看当前</button>
        </div>
        <div class="inline-note">只用上面3个按钮就够用。导入成功后，回首页刷新状态即可。</div>
        <details class="cookie-help" style="margin-top: 12px;">
          <summary>Cookie 详细获取步骤（推荐按这个顺序）</summary>
          <div class="cookie-help-content">
            <p><strong>0基础 Cookie 复制方式：</strong></p>
            <ol style="margin-left: 20px; margin-top: 8px;">
              <li>登录闲鱼网页版</li>
              <li>按 F12 打开开发者工具</li>
              <li>切换到 Network（网络）标签</li>
              <li>刷新页面，点击任意请求</li>
              <li>在 Request Headers 中找到 Cookie</li>
              <li>建议确保包含关键字段：<code>_tb_token_</code>、<code>cookie2</code>、<code>sgcookie</code>、<code>unb</code></li>
            </ol>
            <p style="margin-top: 10px;"><strong>更新后如何确认生效：</strong>导入成功后，回到首页点击"刷新状态"按钮，确认账号状态正常。</p>
            <p style="margin-top: 10px;"><strong>插件一键导入并更新：</strong>在下方"高级选项"中下载内置插件包，加载后导出 Cookie，再通过"插件导出文件"按钮一键导入。</p>
          </div>
        </details>
        <details class="cookie-help" style="margin-top: 12px;">
          <summary>高级选项：插件安装与手动解析</summary>
          <div class="cookie-help-content">
            <p><strong>0基础 Cookie 复制方式：</strong>登录后按 F12，点 Network，任选一个请求，在 Request Headers 里复制整段 Cookie。</p>
            <p><strong>Cookie 详细获取步骤：</strong>打开 goofish 并登录账号 → 按 F12 打开开发者工具 → Network 任意请求复制 Cookie 请求头。</p>
            <p><strong>关键字段检查：</strong>请确认 Cookie 至少包含 <code>unb</code>、<code>_m_h5_tk</code>、<code>_m_h5_tk_enc</code>、<code>cookie2</code>、<code>_tb_token_</code>。</p>
            <p><strong>更新后如何确认生效：</strong>回到首页点击“刷新所有状态”，确认 Cookie 存在、长度正常、风险状态为低风险。</p>
            <p><strong>插件一键导入并更新：</strong>优先使用上方“上传并一键更新”，系统会自动解析 txt/json/zip 并写入配置。</p>
            <p><strong>插件安装：</strong>下载内置插件包 → 浏览器扩展页加载 <code>Get-cookies.txt-LOCALLY/src</code>。</p>
            <div class="button-group" style="margin-top: 8px;">
              <button class="btn-secondary" onclick="window.location.href='/api/download-cookie-plugin'">下载内置插件包</button>
            </div>
            <p><a href="https://github.com/kairi003/Get-cookies.txt-LOCALLY" target="_blank" rel="noopener">插件项目地址（GitHub）</a></p>
            <div class="form-group" style="margin-top: 10px;">
              <label for="cookieFile">手动导入 Cookie 文件</label>
              <input type="file" id="cookieFile" accept=".txt,.json,.log,.cookies,.csv,.tsv,.har">
            </div>
            <div class="button-group">
              <button class="btn-secondary" onclick="importCookieFile()">导入文件到输入框</button>
              <button class="btn-secondary" onclick="normalizeCookieText()">智能解析</button>
            </div>
          </div>
        </details>
        <div id="cookieParseResult" class="panel"></div>
      </div>
    </div>

    <div id="routesTab" class="tab-content">
      <div class="section">
        <h2 class="section-title">导入路线数据</h2>
        <div class="form-group">
          <label for="routeFile">选择文件（可多选）</label>
          <input type="file" id="routeFile" accept=".xlsx,.xls,.csv,.zip" multiple>
          <div class="hint">支持 Excel/CSV/ZIP（ZIP 内可放 xlsx/xls/csv），导入后立即可用于报价。</div>
        </div>
        <div class="button-group">
          <button id="importBtn" class="btn-primary" title="将你上传的成本表写入本地报价成本目录" onclick="importRoutes()">导入到成本库</button>
          <button class="btn-secondary" title="查看当前已加载路线数量/快递公司数量" onclick="loadRouteStats()">查看统计</button>
          <button class="btn-secondary" title="导出当前成本表备份，便于迁移或回滚" onclick="window.location.href='/api/export-routes'">导出ZIP</button>
        </div>
        <div class="button-group" style="margin-top: 10px;">
          <button class="btn-danger" title="清空路线数据（高风险操作）" onclick="resetDatabase('routes')">重置路线数据库</button>
          <button class="btn-danger" title="清空聊天状态（高风险操作）" onclick="resetDatabase('chat')">重置聊天记录</button>
        </div>
        <div class="inline-note">先导入，再点“查看统计”确认路线数不为0；重置仅在数据错误时使用。</div>
        <div id="routeStats" class="panel"></div>
        <div id="importResult" class="panel"></div>
      </div>
    </div>

    <div id="markupTab" class="tab-content">
      <div class="section">
        <h2 class="section-title">加价数据配置</h2>
        <div class="info-box" style="margin-bottom: 14px;">
          <p><strong>说明：</strong>这里配置“成本价 → 对外报价”的加价规则。</p>
          <p>普通/会员 分别配置 首重加价、续重加价（元）。</p>
        </div>
        <div class="form-group">
          <label for="markupFile">导入加价文件（支持多选）</label>
          <input type="file" id="markupFile" accept=".xlsx,.xls,.csv,.json,.yaml,.yml,.txt,.md,.zip,.png,.jpg,.jpeg,.bmp,.webp,.gif" multiple>
          <div class="hint">支持 Excel/CSV/JSON/YAML/TXT/ZIP/图片（OCR 自动识别）。</div>
        </div>
        <div class="button-group">
          <button class="btn-primary" title="自动识别导入加价文件并保存到配置" onclick="importMarkupFiles()">导入加价文件</button>
          <button class="btn-secondary" title="读取当前配置中的加价规则" onclick="loadMarkupRules()">加载加价规则</button>
          <button class="btn-primary" title="保存当前表格的加价规则到配置文件" onclick="saveMarkupRules()">保存加价规则</button>
        </div>
        <div class="inline-note">建议每次导入新路线后检查一次加价规则，确保报价口径一致。</div>
        <div class="form-group" style="margin-top: 14px;">
          <div style="overflow-x:auto;">
            <table id="markupTable" style="width:100%; border-collapse:collapse; min-width:760px;">
              <thead>
                <tr>
                  <th style="border:1px solid #e5e7eb; background:#f9fafb; padding:8px;">运力</th>
                  <th style="border:1px solid #e5e7eb; background:#f9fafb; padding:8px;">首重溢价(普通)</th>
                  <th style="border:1px solid #e5e7eb; background:#f9fafb; padding:8px;">首重溢价(会员)</th>
                  <th style="border:1px solid #e5e7eb; background:#f9fafb; padding:8px;">续重溢价(普通)</th>
                  <th style="border:1px solid #e5e7eb; background:#f9fafb; padding:8px;">续重溢价(会员)</th>
                </tr>
              </thead>
              <tbody id="markupTableBody"></tbody>
            </table>
          </div>
        </div>
        <div id="markupResult" class="panel"></div>
      </div>
    </div>

    <div id="templateTab" class="tab-content">
      <div class="section">
        <h2 class="section-title">回复模板管理</h2>
        <div class="info-box" style="margin-bottom: 14px;">
          <p><strong>重量版模板：</strong>按实际重量报价。</p>
          <p><strong>体积版模板：</strong>按体积重报价，可包含 {volume_formula}。</p>
          <p><strong>常用变量：</strong>{origin}/{destination}、{origin_province}/{dest_province}、{weight}/{billing_weight}、{courier}、{price}、{eta_days}、{volume_formula}</p>
          <p><strong>兼容变量：</strong>{first_price}、{remaining_price}、{volume_weight}、{additional_units}、{courier_name}、{total_price}</p>
        </div>
        <div class="form-group">
          <label for="weightTemplateContent">重量版模板</label>
          <textarea id="weightTemplateContent" rows="10"></textarea>
        </div>
        <div class="form-group">
          <label for="volumeTemplateContent">体积版模板</label>
          <textarea id="volumeTemplateContent" rows="10"></textarea>
        </div>
        <div class="button-group">
          <button class="btn-secondary" title="读取当前生效模板内容" onclick="loadCurrentTemplate()">加载当前</button>
          <button class="btn-secondary" title="将编辑区替换为系统默认模板" onclick="resetToDefault()">恢复默认</button>
          <button class="btn-primary" title="保存模板并立即生效" onclick="saveTemplate()">保存模板</button>
        </div>
        <div class="inline-note">建议先“加载当前”，修改后“保存模板”；模板会用于后续自动回复。</div>
      </div>
    </div>

    <div id="message" class="message"></div>
  </div>

  <script>
    function showMessage(text, type) {
      const el = document.getElementById("message");
      el.textContent = text;
      el.className = "message " + type;
      el.style.display = "block";
      setTimeout(() => { el.style.display = "none"; }, Math.max(3500, text.length * 35));
    }

    function switchTab(tabName, btnEl) {
      document.querySelectorAll(".tab-content").forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
      document.getElementById(tabName + "Tab").classList.add("active");
      if (btnEl) btnEl.classList.add("active");

      if (tabName === "routes") loadRouteStats();
      if (tabName === "markup") loadMarkupRules();
      if (tabName === "template") loadCurrentTemplate();
    }

    async function loadCurrentCookie() {
      try {
        const res = await fetch("/api/get-cookie");
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "未找到Cookie");
        document.getElementById("cookie").value = data.cookie || "";
        showMessage("已加载当前Cookie", "success");
      } catch (err) {
        showMessage("加载Cookie失败: " + err.message, "error");
      }
    }

    async function importCookieFile() {
      const fileInput = document.getElementById("cookieFile");
      const file = fileInput && fileInput.files ? fileInput.files[0] : null;
      if (!file) {
        showMessage("请选择 Cookie 文件", "error");
        return;
      }
      try {
        const text = await file.text();
        document.getElementById("cookie").value = text || "";
        showMessage("已导入文件内容，请点击“智能解析”", "success");
      } catch (err) {
        showMessage("读取文件失败: " + err.message, "error");
      }
    }

    async function importCookiePlugin() {
      const fileInput = document.getElementById("cookiePluginFile");
      const files = fileInput && fileInput.files ? Array.from(fileInput.files) : [];
      if (!files.length) {
        showMessage("请选择插件导出文件", "error");
        return;
      }

      const panel = document.getElementById("cookieParseResult");
      panel.style.display = "block";
      panel.textContent = "导入中...";

      const fd = new FormData();
      files.forEach(f => fd.append("file", f));

      try {
        const res = await fetch("/api/import-cookie-plugin", { method: "POST", body: fd });
        const data = await res.json();
        if (!data.success) {
          const msg = [data.error || "导入失败", data.hint || ""].filter(Boolean).join(" | ");
          throw new Error(msg);
        }

        document.getElementById("cookie").value = data.cookie || "";

        let text = "插件导入成功\\n";
        text += "来源文件: " + (data.source_file || "-") + "\\n";
        text += "识别格式: " + (data.detected_format || "-") + "\\n";
        text += "Cookie 项数: " + (data.cookie_items || 0) + "\\n";
        text += "字符长度: " + (data.length || 0) + "\\n";
        text += "可用性分级: " + (data.cookie_grade || "未知") + "\\n";
        if ((data.missing_required || []).length > 0) {
          text += "关键字段缺失: " + data.missing_required.join(", ") + "\\n";
        } else {
          text += "关键字段检查: 通过\\n";
        }
        if ((data.cookie_actions || []).length > 0) {
          text += "建议动作: " + data.cookie_actions.join(" | ") + "\\n";
        }
        const pluginRecover = data.auto_recover || {};
        if (Object.keys(pluginRecover).length > 0) {
          text += "自动恢复: " + (pluginRecover.triggered ? "已触发" : "未触发/失败") + "\\n";
          if (pluginRecover.at) {
            text += "恢复时间: " + pluginRecover.at + "\\n";
          }
          if (pluginRecover.result && pluginRecover.result.error) {
            text += "恢复错误: " + pluginRecover.result.error + "\\n";
          }
        }
        if ((data.recognized_key_hits || []).length > 0) {
          text += "识别关键字段: " + data.recognized_key_hits.join(", ") + "\\n";
        }
        if ((data.imported_files || []).length > 0) {
          text += "已识别文件: " + data.imported_files.join(", ") + "\\n";
        }
        if ((data.skipped_files || []).length > 0) {
          text += "已跳过文件: " + data.skipped_files.join(", ") + "\\n";
        }
        if ((data.details || []).length > 0) {
          text += "详细说明: " + data.details.join(" | ");
        }

        panel.textContent = text.trim();
        showMessage("插件 Cookie 导入并更新成功", "success");
        await initCookiePreview();
      } catch (err) {
        panel.textContent = "插件导入失败: " + err.message;
        showMessage("插件导入失败: " + err.message, "error");
      }
    }

    async function normalizeCookieText() {
      const raw = document.getElementById("cookie").value;
      if (!raw || !raw.trim()) {
        showMessage("请输入或导入 Cookie 文本", "error");
        return;
      }

      const panel = document.getElementById("cookieParseResult");
      panel.style.display = "block";
      panel.textContent = "解析中...";

      try {
        const res = await fetch("/api/parse-cookie", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: raw })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "解析失败");

        document.getElementById("cookie").value = data.cookie || "";

        let text = "解析成功\\n";
        text += "识别格式: " + (data.detected_format || "-") + "\\n";
        text += "Cookie 项数: " + (data.cookie_items || 0) + "\\n";
        text += "字符长度: " + (data.length || 0) + "\\n";
        if ((data.missing_required || []).length > 0) {
          text += "关键字段缺失: " + data.missing_required.join(", ");
        } else {
          text += "关键字段检查: 通过";
        }
        panel.textContent = text;
        showMessage("Cookie 文本已标准化", "success");
      } catch (err) {
        panel.textContent = "解析失败: " + err.message;
        showMessage("解析失败: " + err.message, "error");
      }
    }

    async function saveCookie() {
      const cookie = document.getElementById("cookie").value.trim();
      if (!cookie) {
        showMessage("请输入Cookie", "error");
        return;
      }
      try {
        const res = await fetch("/api/update-cookie", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cookie })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "更新失败");
        let msg = "Cookie更新成功";
        if (data.cookie_items) {
          msg += "\\n识别项数: " + data.cookie_items + "（格式: " + (data.detected_format || "-") + "）";
        }
        if (data.cookie_grade) {
          msg += "\\n可用性分级: " + data.cookie_grade;
        }
        if ((data.missing_required || []).length > 0) {
          msg += "\\n缺少关键字段: " + data.missing_required.join(", ");
        }
        if ((data.cookie_actions || []).length > 0) {
          msg += "\\n建议动作: " + data.cookie_actions.join(" | ");
        }
        const manualRecover = data.auto_recover || {};
        if (Object.keys(manualRecover).length > 0) {
          msg += "\\n自动恢复: " + (manualRecover.triggered ? "已触发" : "未触发/失败");
          if (manualRecover.result && manualRecover.result.error) {
            msg += "\\n恢复错误: " + manualRecover.result.error;
          }
        }
        showMessage(msg, "success");
        await initCookiePreview();
      } catch (err) {
        showMessage("更新Cookie失败: " + err.message, "error");
      }
    }

    async function diagnoseCookie() {
      const raw = document.getElementById("cookie").value.trim();
      if (!raw) {
        showMessage("请先粘贴 Cookie 再诊断", "error");
        return;
      }
      const panel = document.getElementById("cookieParseResult");
      panel.style.display = "block";
      panel.textContent = "诊断中...";

      try {
        const res = await fetch("/api/cookie-diagnose", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: raw })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "诊断失败");

        let text = "Cookie 诊断结果\\n";
        text += "可用性分级: " + (data.grade || "-") + "\\n";
        text += "识别格式: " + (data.detected_format || "-") + "\\n";
        text += "Cookie 项数: " + (data.cookie_items || 0) + "\\n";
        text += "字符长度: " + (data.length || 0) + "\\n";
        text += "缺失字段: " + ((data.required_missing || []).join(", ") || "无") + "\\n";
        const domainFilter = data.domain_filter || {};
        text += "域过滤: checked=" + (domainFilter.checked || 0) + ", rejected=" + (domainFilter.rejected || 0) + "\\n";
        if ((data.actions || []).length > 0) {
          text += "建议: " + data.actions.join(" | ");
        }
        panel.textContent = text.trim();
        showMessage("Cookie 诊断完成", "success");
      } catch (err) {
        panel.textContent = "诊断失败: " + err.message;
        showMessage("诊断失败: " + err.message, "error");
      }
    }

    function renderMarkupRules(rules) {
      const tbody = document.getElementById("markupTableBody");
      tbody.innerHTML = "";
      const entries = Object.entries(rules || {});
      const ordered = entries
        .filter(([k]) => k !== "default")
        .sort((a, b) => a[0].localeCompare(b[0], "zh-CN"));
      if (rules && rules.default) ordered.unshift(["default", rules.default]);

      ordered.forEach(([courier, row]) => {
        const tr = document.createElement("tr");
        const values = {
          normal_first_add: Number((row || {}).normal_first_add || 0),
          member_first_add: Number((row || {}).member_first_add || 0),
          normal_extra_add: Number((row || {}).normal_extra_add || 0),
          member_extra_add: Number((row || {}).member_extra_add || 0),
        };
        tr.innerHTML = `
          <td style="border:1px solid #e5e7eb; padding:8px; font-weight:600;">${courier}</td>
          <td style="border:1px solid #e5e7eb; padding:8px;"><input data-courier="${courier}" data-key="normal_first_add" type="number" min="0" step="0.01" value="${values.normal_first_add.toFixed(2)}" style="width:100%; padding:8px; border:1px solid #d1d5db; border-radius:4px;"></td>
          <td style="border:1px solid #e5e7eb; padding:8px;"><input data-courier="${courier}" data-key="member_first_add" type="number" min="0" step="0.01" value="${values.member_first_add.toFixed(2)}" style="width:100%; padding:8px; border:1px solid #d1d5db; border-radius:4px;"></td>
          <td style="border:1px solid #e5e7eb; padding:8px;"><input data-courier="${courier}" data-key="normal_extra_add" type="number" min="0" step="0.01" value="${values.normal_extra_add.toFixed(2)}" style="width:100%; padding:8px; border:1px solid #d1d5db; border-radius:4px;"></td>
          <td style="border:1px solid #e5e7eb; padding:8px;"><input data-courier="${courier}" data-key="member_extra_add" type="number" min="0" step="0.01" value="${values.member_extra_add.toFixed(2)}" style="width:100%; padding:8px; border:1px solid #d1d5db; border-radius:4px;"></td>
        `;
        tbody.appendChild(tr);
      });
    }

    function collectMarkupRules() {
      const rows = {};
      document.querySelectorAll("#markupTableBody input[data-courier][data-key]").forEach(input => {
        const courier = input.getAttribute("data-courier");
        const key = input.getAttribute("data-key");
        if (!rows[courier]) {
          rows[courier] = {
            normal_first_add: 0,
            member_first_add: 0,
            normal_extra_add: 0,
            member_extra_add: 0,
          };
        }
        const n = Number(input.value);
        rows[courier][key] = Number.isFinite(n) && n >= 0 ? Number(n.toFixed(4)) : 0;
      });
      return rows;
    }

    async function importMarkupFiles() {
      const fileInput = document.getElementById("markupFile");
      const panel = document.getElementById("markupResult");
      if (!fileInput.files || fileInput.files.length === 0) {
        showMessage("请选择至少一个加价文件", "error");
        return;
      }

      const fd = new FormData();
      Array.from(fileInput.files).forEach(f => fd.append("file", f));

      panel.style.display = "block";
      panel.textContent = "导入中...";

      try {
        const res = await fetch("/api/import-markup", { method: "POST", body: fd });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "导入失败");

        renderMarkupRules(data.markup_rules || {});

        let text = "导入成功\\n";
        text += "识别快递公司: " + (data.imported_couriers || []).length + "\\n";
        text += "导入文件: " + ((data.imported_files || []).join(", ") || "-") + "\\n";
        if ((data.skipped_files || []).length > 0) {
          text += "跳过文件: " + data.skipped_files.join(", ") + "\\n";
        }
        if ((data.detected_formats || {}) && Object.keys(data.detected_formats || {}).length > 0) {
          const fmt = Object.entries(data.detected_formats || {}).map(([k, v]) => `${k}:${v}`).join(", ");
          text += "识别格式: " + fmt + "\\n";
        }
        if ((data.details || []).length > 0) {
          text += "\\n详细说明: " + data.details.join(" | ");
        }
        panel.textContent = text.trim();
        showMessage("加价数据导入成功", "success");
      } catch (err) {
        panel.textContent = "导入失败: " + err.message;
        showMessage("导入加价数据失败: " + err.message, "error");
      }
    }

    async function loadMarkupRules() {
      const panel = document.getElementById("markupResult");
      panel.style.display = "block";
      panel.textContent = "加载中...";
      try {
        const res = await fetch("/api/get-markup-rules");
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "加载失败");
        renderMarkupRules(data.markup_rules || {});
        panel.textContent = "已加载加价规则，快递公司数: " + (data.couriers || []).length;
      } catch (err) {
        panel.textContent = "加载失败: " + err.message;
      }
    }

    async function saveMarkupRules() {
      const rules = collectMarkupRules();
      const panel = document.getElementById("markupResult");
      panel.style.display = "block";
      panel.textContent = "保存中...";
      try {
        const res = await fetch("/api/save-markup-rules", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ markup_rules: rules })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "保存失败");
        panel.textContent = "保存成功\\n规则数: " + Object.keys(data.markup_rules || {}).length + "\\n备份: " + (data.backup_path || "-");
        showMessage("加价规则保存成功", "success");
      } catch (err) {
        panel.textContent = "保存失败: " + err.message;
        showMessage("保存加价规则失败: " + err.message, "error");
      }
    }

    async function loadRouteStats() {
      const statsDiv = document.getElementById("routeStats");
      statsDiv.style.display = "block";
      statsDiv.textContent = "加载中...";
      try {
        const res = await fetch("/api/route-stats");
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "获取失败");
        const stats = data.stats || {};
        let text = "路线统计\\n";
        text += "快递公司数: " + (stats.couriers || 0) + "\\n";
        text += "路线总数: " + (stats.routes || 0) + "\\n";
        text += "成本表文件: " + (stats.tables || 0) + "\\n";
        text += "最后更新: " + (stats.last_updated || "-") + "\\n";
        if (stats.parse_error) {
          text += "解析提示: " + stats.parse_error + "\\n";
        }
        if (stats.courier_details && Object.keys(stats.courier_details).length > 0) {
          text += "\\n快递公司明细:\\n";
          Object.entries(stats.courier_details).forEach(([k, v]) => {
            text += "- " + k + ": " + v + "\\n";
          });
        }
        statsDiv.textContent = text;
      } catch (err) {
        statsDiv.textContent = "加载失败: " + err.message;
      }
    }

    async function importRoutes() {
      const fileInput = document.getElementById("routeFile");
      if (!fileInput.files || fileInput.files.length === 0) {
        showMessage("请选择至少一个文件", "error");
        return;
      }

      const fd = new FormData();
      for (const f of fileInput.files) fd.append("file", f);

      const btn = document.getElementById("importBtn");
      const oldText = btn.textContent;
      btn.disabled = true;
      btn.textContent = "导入中...";

      try {
        const res = await fetch("/api/import-routes", { method: "POST", body: fd });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "导入失败");

        const stats = data.stats || {};
        let text = "导入成功\\n";
        text += "文件: " + ((data.saved_files || []).join(", ") || "-") + "\\n";
        text += "快递公司数: " + (stats.couriers || 0) + "\\n";
        text += "路线总数: " + (stats.routes || 0) + "\\n";
        text += "成本表文件: " + (stats.tables || 0);
        if (stats.parse_error) {
          text += "\\n解析提示: " + stats.parse_error;
        }
        if ((data.skipped_files || []).length > 0) {
          text += "\\n\\n已跳过文件: " + data.skipped_files.join(", ");
        }
        if ((data.details || []).length > 0) {
          text += "\\n\\n详细说明: " + data.details.join(" | ");
        }

        const resultDiv = document.getElementById("importResult");
        resultDiv.style.display = "block";
        resultDiv.textContent = text;

        showMessage("路线数据导入成功", "success");
        fileInput.value = "";
        loadRouteStats();
      } catch (err) {
        showMessage("导入失败: " + err.message, "error");
      } finally {
        btn.disabled = false;
        btn.textContent = oldText;
      }
    }

    async function resetDatabase(type) {
      const typeName = type === "routes" ? "路线数据库" : "聊天记录";
      if (!confirm("确定重置" + typeName + "吗？此操作不可恢复。")) return;
      try {
        const res = await fetch("/api/reset-database", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ type })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "重置失败");
        showMessage(typeName + "重置成功", "success");
        if (type === "routes") {
          loadRouteStats();
          const resultDiv = document.getElementById("importResult");
          resultDiv.style.display = "none";
        }
      } catch (err) {
        showMessage(typeName + "重置失败: " + err.message, "error");
      }
    }

    async function loadCurrentTemplate(useDefault) {
      const qs = useDefault ? "?default=true" : "";
      try {
        const res = await fetch("/api/get-template" + qs);
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "加载失败");
        document.getElementById("weightTemplateContent").value = data.weight_template || "";
        document.getElementById("volumeTemplateContent").value = data.volume_template || "";
        showMessage(useDefault ? "已加载默认模板" : "模板加载成功", "success");
      } catch (err) {
        showMessage("模板加载失败: " + err.message, "error");
      }
    }

    function resetToDefault() {
      if (!confirm("恢复默认模板会覆盖当前内容，是否继续？")) return;
      loadCurrentTemplate(true);
    }

    async function saveTemplate() {
      const weight_template = document.getElementById("weightTemplateContent").value;
      const volume_template = document.getElementById("volumeTemplateContent").value;
      try {
        const res = await fetch("/api/save-template", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ weight_template, volume_template })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "保存失败");
        showMessage("模板保存成功", "success");
      } catch (err) {
        showMessage("模板保存失败: " + err.message, "error");
      }
    }

    async function initCookiePreview() {
      try {
        const res = await fetch("/api/get-cookie");
        const data = await res.json();
        if (!data.success || !data.cookie) return;
        document.getElementById("currentCookie").style.display = "block";
        document.getElementById("currentCookieText").textContent =
          data.cookie.slice(0, 200) + (data.cookie.length > 200 ? "..." : "");
      } catch (_) {}
    }

    initCookiePreview();
  </script>
</body>
</html>
"""
MIMIC_TEST_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Test LLM Reply</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      min-height: 100vh;
      padding: 20px;
    }
    .container {
      max-width: 1100px;
      margin: 0 auto;
      background: #fff;
      border-radius: 12px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.3);
      padding: 34px;
    }
    h1 { color: #333; margin-bottom: 8px; font-size: 28px; }
    .subtitle { color: #666; margin-bottom: 18px; font-size: 14px; }
    .guide-card {
      background: #eff6ff;
      border: 1px solid #bfdbfe;
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 16px;
      color: #1e3a8a;
      font-size: 13px;
      line-height: 1.7;
    }
    .guide-card strong { color: #1d4ed8; }
    .nav-links {
      margin-bottom: 22px;
      padding-bottom: 14px;
      border-bottom: 1px solid #e5e7eb;
    }
    .nav-links a {
      color: #667eea;
      text-decoration: none;
      margin-right: 18px;
      font-size: 14px;
      font-weight: 600;
    }
    .nav-links a:hover { text-decoration: underline; }
    .form-group { margin-bottom: 16px; }
    label {
      display: block;
      margin-bottom: 8px;
      color: #333;
      font-weight: 600;
      font-size: 14px;
    }
    textarea, input {
      width: 100%;
      padding: 12px;
      border: 2px solid #e5e7eb;
      border-radius: 6px;
      font-size: 14px;
      font-family: inherit;
      transition: border-color 0.2s ease;
    }
    textarea {
      resize: vertical;
      min-height: 120px;
      font-family: "SFMono-Regular", Menlo, Consolas, monospace;
    }
    textarea:focus, input:focus {
      outline: none;
      border-color: #667eea;
    }
    .row {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 12px;
    }
    .btn {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: #fff;
      border: none;
      border-radius: 6px;
      padding: 12px 16px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      min-width: 160px;
    }
    .btn:disabled { opacity: 0.6; cursor: not-allowed; }
    .btn-row { display: flex; gap: 10px; flex-wrap: wrap; }
    .btn-secondary {
      background: #f3f4f6;
      color: #1f2937;
      border: none;
      border-radius: 6px;
      padding: 12px 16px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
    }
    .hint {
      margin-top: 6px;
      color: #6b7280;
      font-size: 12px;
      line-height: 1.5;
    }
    .result-box {
      margin-top: 18px;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      overflow: hidden;
      display: none;
    }
    .result-head {
      padding: 10px 14px;
      background: #f8f9fa;
      border-bottom: 1px solid #e5e7eb;
      color: #374151;
      font-size: 13px;
      display: flex;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
    }
    .result-content {
      padding: 14px;
      white-space: pre-wrap;
      line-height: 1.7;
      color: #111827;
    }
    .result-json {
      margin-top: 10px;
      background: #111827;
      color: #d1fae5;
      border-radius: 6px;
      padding: 12px;
      max-height: 260px;
      overflow: auto;
      font-size: 12px;
      white-space: pre;
      display: none;
    }
    .error {
      margin-top: 12px;
      color: #b91c1c;
      background: #fee2e2;
      border: 1px solid #fecaca;
      border-radius: 6px;
      padding: 10px;
      display: none;
      white-space: pre-line;
    }
    @media (max-width: 860px) {
      .row { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>测试调试</h1>
    <p class="subtitle">用于验证售前回复、报价输出、上下文串联效果（不发送到真实买家）。</p>
    <div class="guide-card">
      <strong>新手测试顺序：</strong> 先点“填充示例”→ 再点“生成回复”→ 查看“意图/代理/耗时”→ 满意后再上线自动回复。
    </div>

    <div class="nav-links">
      <a href="/">首页</a>
      <a href="/cookie">配置管理</a>
      <a href="/logs">日志查看</a>
      <a href="/logs/realtime">实时日志</a>
    </div>

    <div class="form-group">
      <label for="userMsg">买家消息</label>
      <textarea id="userMsg" placeholder="例如：安徽到广州3kg圆通多少钱？"></textarea>
    </div>

    <div class="form-group">
      <label for="itemDesc">商品描述（可选）</label>
      <input id="itemDesc" placeholder="例如：代下单快递服务，自动报价" />
    </div>

    <div class="row">
      <div class="form-group">
        <label for="origin">始发地</label>
        <input id="origin" placeholder="安徽" />
      </div>
      <div class="form-group">
        <label for="destination">目的地</label>
        <input id="destination" placeholder="广州" />
      </div>
      <div class="form-group">
        <label for="weight">重量(kg)</label>
        <input id="weight" placeholder="3" />
      </div>
    </div>

    <div class="row">
      <div class="form-group">
        <label for="courier">快递（可选）</label>
        <input id="courier" placeholder="圆通" />
      </div>
      <div class="form-group">
        <label for="serviceLevel">服务等级</label>
        <input id="serviceLevel" placeholder="standard" />
      </div>
      <div class="form-group">
        <label for="itemType">商品类型</label>
        <input id="itemType" placeholder="general" />
      </div>
    </div>

    <div class="form-group">
      <label for="context">上下文(JSON，可选)</label>
      <textarea id="context" style="min-height: 100px;" placeholder='例如：[{"role":"user","content":"在吗"},{"role":"assistant","content":"在的亲"}]'></textarea>
      <p class="hint">如果不填，系统将使用当前输入单轮测试。填入合法JSON数组可模拟多轮对话。</p>
    </div>

    <div class="btn-row">
      <button id="submitBtn" class="btn" title="调用回复/报价引擎进行一次完整测试" onclick="generateReply()">生成回复</button>
      <button class="btn-secondary" title="自动填入可跑通的演示数据" onclick="fillDemo()">填充示例</button>
      <button class="btn-secondary" title="查看完整返回JSON，便于排查字段问题" onclick="toggleRaw()">显示/隐藏原始JSON</button>
      <button class="btn-secondary" title="清空本页所有输入与结果" onclick="clearAll()">清空</button>
    </div>

    <div id="errorBox" class="error"></div>

    <div id="resultBox" class="result-box">
      <div id="resultMeta" class="result-head"></div>
      <div id="resultContent" class="result-content"></div>
      <pre id="rawJson" class="result-json"></pre>
    </div>
  </div>

  <script>
    function showError(msg) {
      const box = document.getElementById("errorBox");
      box.textContent = msg || "";
      box.style.display = msg ? "block" : "none";
    }

    function parseContext() {
      const raw = document.getElementById("context").value.trim();
      if (!raw) return [];
      try {
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
      } catch (err) {
        throw new Error("context JSON 解析失败: " + err.message);
      }
    }

    function fillDemo() {
      document.getElementById("userMsg").value = "安徽到广州3kg圆通多少钱";
      document.getElementById("itemDesc").value = "快递代下单服务";
      document.getElementById("origin").value = "安徽";
      document.getElementById("destination").value = "广州";
      document.getElementById("weight").value = "3";
      document.getElementById("courier").value = "圆通";
      document.getElementById("context").value = "";
    }

    function toggleRaw() {
      const raw = document.getElementById("rawJson");
      raw.style.display = raw.style.display === "block" ? "none" : "block";
    }

    function clearAll() {
      ["userMsg", "itemDesc", "origin", "destination", "weight", "courier", "serviceLevel", "itemType", "context"].forEach(id => {
        document.getElementById(id).value = "";
      });
      showError("");
      document.getElementById("resultBox").style.display = "none";
      document.getElementById("rawJson").style.display = "none";
      document.getElementById("rawJson").textContent = "";
    }

    async function generateReply() {
      showError("");
      const submitBtn = document.getElementById("submitBtn");
      const originalText = submitBtn.textContent;

      const userMsg = document.getElementById("userMsg").value.trim();
      if (!userMsg) {
        showError("请先输入买家消息");
        return;
      }

      let context = [];
      try {
        context = parseContext();
      } catch (err) {
        showError(err.message);
        return;
      }

      const payload = {
        user_msg: userMsg,
        item_desc: document.getElementById("itemDesc").value.trim(),
        context: context,
        message: userMsg,
        item_title: document.getElementById("itemDesc").value.trim(),
        origin: document.getElementById("origin").value.trim(),
        destination: document.getElementById("destination").value.trim(),
        weight: document.getElementById("weight").value.trim(),
        courier: document.getElementById("courier").value.trim(),
        service_level: document.getElementById("serviceLevel").value.trim(),
        item_type: document.getElementById("itemType").value.trim()
      };

      submitBtn.disabled = true;
      submitBtn.textContent = "生成中...";

      try {
        const res = await fetch("/api/test-reply", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "生成失败");

        const resultBox = document.getElementById("resultBox");
        const resultMeta = document.getElementById("resultMeta");
        const resultContent = document.getElementById("resultContent");
        const rawJson = document.getElementById("rawJson");

        resultMeta.innerHTML =
          "<span><strong>意图：</strong>" + (data.intent || "-") + "</span>" +
          "<span><strong>代理：</strong>" + (data.agent || "-") + "</span>" +
          "<span><strong>响应时间：</strong>" + (Number(data.response_time || 0).toFixed(2)) + "ms</span>";

        resultContent.textContent = data.reply || "(空回复)";
        rawJson.textContent = JSON.stringify(data, null, 2);
        resultBox.style.display = "block";
      } catch (err) {
        showError("生成回复失败: " + err.message);
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = originalText;
      }
    }
  </script>
</body>
</html>
"""
MIMIC_LOGS_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>日志查看 - XianyuAutoAgent</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f5f5f5;
      padding: 20px;
    }
    .container {
      max-width: 1400px;
      margin: 0 auto;
      background: #fff;
      border-radius: 8px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.1);
      padding: 30px;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      padding-bottom: 20px;
      border-bottom: 2px solid #e0e0e0;
      gap: 12px;
    }
    .guide-card {
      background: #eff6ff;
      border: 1px solid #bfdbfe;
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 14px;
      color: #1e3a8a;
      font-size: 13px;
      line-height: 1.7;
    }
    .guide-card strong { color: #1d4ed8; }
    .guide-card {
      background: #eff6ff;
      border: 1px solid #bfdbfe;
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 14px;
      color: #1e3a8a;
      font-size: 13px;
      line-height: 1.7;
    }
    .guide-card strong { color: #1d4ed8; }
    h1 { color: #333; font-size: 28px; }
    .nav-link {
      color: #667eea;
      text-decoration: none;
      font-size: 14px;
      padding: 10px 20px;
      border-radius: 6px;
      border: 2px solid #667eea;
      transition: all 0.2s ease;
      font-weight: 600;
      display: inline-block;
      white-space: nowrap;
    }
    .nav-link:hover {
      background: #667eea;
      color: #fff;
      transform: translateY(-1px);
    }
    .file-selector { margin-bottom: 14px; }
    .file-selector select {
      width: 100%;
      padding: 10px;
      border: 2px solid #e0e0e0;
      border-radius: 6px;
      font-size: 14px;
      background: white;
    }
    .search-bar {
      display: flex;
      gap: 10px;
      margin-bottom: 14px;
      flex-wrap: wrap;
    }
    .search-bar input {
      flex: 1;
      min-width: 260px;
      padding: 10px;
      border: 2px solid #e0e0e0;
      border-radius: 6px;
      font-size: 14px;
    }
    .search-bar button {
      padding: 10px 16px;
      border: none;
      border-radius: 6px;
      background: #667eea;
      color: #fff;
      cursor: pointer;
      font-size: 14px;
      font-weight: 600;
    }
    .search-bar button.secondary { background: #6b7280; }
    .search-bar button:hover { opacity: 0.92; }
    .log-viewer {
      background: #1e1e1e;
      color: #d4d4d4;
      padding: 16px;
      border-radius: 6px;
      font-family: "Courier New", monospace;
      font-size: 13px;
      line-height: 1.55;
      min-height: 520px;
      max-height: 68vh;
      overflow-y: auto;
      white-space: pre-wrap;
      word-break: break-word;
      border: 1px solid #111827;
    }
    .log-line { margin-bottom: 2px; }
    .log-line.highlight {
      background: #fde047;
      color: #111827;
      border-radius: 2px;
      padding: 1px 3px;
    }
    .loading {
      text-align: center;
      padding: 36px;
      color: #9ca3af;
    }
    .pagination {
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 10px;
      margin-top: 16px;
      flex-wrap: wrap;
    }
    .pagination button {
      padding: 8px 14px;
      border: 1px solid #e5e7eb;
      background: white;
      border-radius: 4px;
      cursor: pointer;
      font-size: 13px;
    }
    .pagination button:disabled { opacity: 0.5; cursor: not-allowed; }
    .pagination span { color: #4b5563; font-size: 13px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>日志查看</h1>
      <a href="/" class="nav-link">← 返回首页</a>
    </div>
    <div class="guide-card">
      <strong>使用说明：</strong> 先选日志文件，再用搜索定位关键词（如报价、错误、超时），分页查看历史记录。
    </div>

    <div class="file-selector">
      <select id="logFileSelect">
        <option value="">加载中...</option>
      </select>
    </div>

    <div class="search-bar">
      <input type="text" id="searchInput" placeholder="搜索日志内容...">
      <button title="按关键词过滤当前日志文件" onclick="searchLogs()">搜索</button>
      <button class="secondary" title="清空关键词并恢复默认列表" onclick="clearSearch()">清除</button>
      <button class="secondary" title="重新加载日志文件列表" onclick="loadLogFiles()">刷新文件</button>
    </div>

    <div id="logViewer" class="log-viewer">
      <div class="loading">请选择日志文件</div>
    </div>

    <div class="pagination">
      <button id="prevBtn" title="查看上一页日志" onclick="previousPage()" disabled>上一页</button>
      <span id="pageInfo">第 0 页，共 0 页</span>
      <button id="nextBtn" title="查看下一页日志" onclick="nextPage()" disabled>下一页</button>
    </div>
  </div>

  <script>
    let currentFile = "";
    let currentPage = 1;
    let totalPages = 1;
    let searchKeyword = "";
    const pageSize = 120;

    function formatSize(bytes) {
      const n = Number(bytes || 0);
      if (n < 1024) return n + " B";
      if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
      return (n / (1024 * 1024)).toFixed(1) + " MB";
    }

    function escapeHtml(text) {
      const div = document.createElement("div");
      div.textContent = text;
      return div.innerHTML;
    }

    function loadLogFiles() {
      fetch("/api/logs/files")
        .then(r => r.json())
        .then(data => {
          const select = document.getElementById("logFileSelect");
          select.innerHTML = '<option value="">请选择日志文件</option>';
          (data.files || []).forEach(file => {
            const option = document.createElement("option");
            option.value = file.name;
            const modified = file.modified ? (" | " + file.modified.replace("T", " ").slice(0, 19)) : "";
            option.textContent = file.name + " (" + formatSize(file.size) + ")" + modified;
            select.appendChild(option);
          });

          if (!currentFile && (data.files || []).length > 0) {
            currentFile = data.files[0].name;
            select.value = currentFile;
            loadLogs();
          }
        })
        .catch(err => {
          document.getElementById("logViewer").innerHTML = '<div class="loading">文件列表加载失败: ' + escapeHtml(err.message || String(err)) + '</div>';
        });
    }

    document.getElementById("logFileSelect").addEventListener("change", (e) => {
      currentFile = e.target.value;
      currentPage = 1;
      if (currentFile) {
        loadLogs();
      } else {
        document.getElementById("logViewer").innerHTML = '<div class="loading">请选择日志文件</div>';
      }
    });

    function loadLogs() {
      if (!currentFile) return;
      document.getElementById("logViewer").innerHTML = '<div class="loading">加载中...</div>';
      const url =
        "/api/logs/content?file=" + encodeURIComponent(currentFile) +
        "&page=" + currentPage +
        "&size=" + pageSize +
        "&search=" + encodeURIComponent(searchKeyword);

      fetch(url)
        .then(r => r.json())
        .then(data => {
          if (!data.success) throw new Error(data.error || "读取失败");
          renderLines(data.lines || []);
          currentPage = Number(data.page || 1);
          totalPages = Number(data.total_pages || 1);
          updatePagination();
        })
        .catch(err => {
          document.getElementById("logViewer").innerHTML = '<div class="loading">加载失败: ' + escapeHtml(err.message || String(err)) + '</div>';
          totalPages = 1;
          currentPage = 1;
          updatePagination();
        });
    }

    function renderLines(lines) {
      const viewer = document.getElementById("logViewer");
      if (!lines.length) {
        viewer.innerHTML = '<div class="loading">没有找到日志内容</div>';
        return;
      }

      const keyword = searchKeyword.trim().toLowerCase();
      let html = "";
      lines.forEach(line => {
        const escaped = escapeHtml(line);
        const cls = keyword && line.toLowerCase().includes(keyword) ? "log-line highlight" : "log-line";
        html += '<div class="' + cls + '">' + escaped + '</div>';
      });
      viewer.innerHTML = html;
      viewer.scrollTop = 0;
    }

    function searchLogs() {
      searchKeyword = document.getElementById("searchInput").value.trim();
      currentPage = 1;
      if (currentFile) loadLogs();
    }

    function clearSearch() {
      searchKeyword = "";
      document.getElementById("searchInput").value = "";
      currentPage = 1;
      if (currentFile) loadLogs();
    }

    function previousPage() {
      if (currentPage > 1) {
        currentPage--;
        loadLogs();
      }
    }

    function nextPage() {
      if (currentPage < totalPages) {
        currentPage++;
        loadLogs();
      }
    }

    function updatePagination() {
      document.getElementById("prevBtn").disabled = currentPage <= 1;
      document.getElementById("nextBtn").disabled = currentPage >= totalPages;
      document.getElementById("pageInfo").textContent = "第 " + currentPage + " 页，共 " + totalPages + " 页";
    }

    document.getElementById("searchInput").addEventListener("keypress", (e) => {
      if (e.key === "Enter") searchLogs();
    });

    loadLogFiles();
  </script>
</body>
</html>
"""

MIMIC_LOGS_REALTIME_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>实时日志 - XianyuAutoAgent</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f5f5f5;
      padding: 20px;
    }
    .container {
      max-width: 1400px;
      margin: 0 auto;
      background: #fff;
      border-radius: 8px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.1);
      padding: 30px;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      padding-bottom: 20px;
      border-bottom: 2px solid #e0e0e0;
      gap: 12px;
    }
    h1 { color: #333; font-size: 28px; }
    .nav-link {
      color: #667eea;
      text-decoration: none;
      font-size: 14px;
      padding: 10px 20px;
      border-radius: 6px;
      border: 2px solid #667eea;
      transition: all 0.2s ease;
      font-weight: 600;
      display: inline-block;
      white-space: nowrap;
    }
    .nav-link:hover {
      background: #667eea;
      color: #fff;
      transform: translateY(-1px);
    }
    .controls {
      display: flex;
      gap: 10px;
      margin-bottom: 14px;
      flex-wrap: wrap;
      align-items: center;
    }
    .controls select {
      min-width: 280px;
      padding: 10px;
      border: 2px solid #e0e0e0;
      border-radius: 6px;
      font-size: 14px;
      background: #fff;
    }
    .controls button {
      padding: 10px 16px;
      border: none;
      border-radius: 6px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 600;
    }
    .btn-start { background: #28a745; color: #fff; }
    .btn-stop { background: #dc3545; color: #fff; }
    .btn-clear { background: #6b7280; color: #fff; }
    .btn-refresh { background: #667eea; color: #fff; }
    .status {
      padding: 10px;
      border-radius: 6px;
      margin-bottom: 14px;
      font-size: 14px;
      font-weight: 600;
    }
    .status.connected {
      background: #d4edda;
      color: #155724;
      border: 1px solid #c3e6cb;
    }
    .status.disconnected {
      background: #f8d7da;
      color: #721c24;
      border: 1px solid #f5c6cb;
    }
    .log-viewer {
      background: #1e1e1e;
      color: #d4d4d4;
      padding: 16px;
      border-radius: 6px;
      font-family: "Courier New", monospace;
      font-size: 13px;
      line-height: 1.55;
      height: 620px;
      overflow-y: auto;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .log-line { margin-bottom: 2px; }
    .log-line.error { color: #f48771; }
    .log-line.warning { color: #dcdcaa; }
    .log-line.info { color: #4ec9b0; }
    .log-line.debug { color: #9cdcfe; }
    .meta { margin-top: 8px; font-size: 12px; color: #6b7280; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>实时日志</h1>
      <a href="/" class="nav-link">← 返回首页</a>
    </div>
    <div class="guide-card">
      <strong>使用说明：</strong> 先选日志源，点击“开始”进入实时监控。排查结束后点“停止”，避免无意义刷新占用资源。
    </div>

    <div class="controls">
      <select id="logFileSelect"></select>
      <button class="btn-refresh" title="重新加载可选日志源" onclick="refreshLogFiles()">刷新文件</button>
      <button class="btn-start" title="连接SSE日志流并持续刷新" onclick="startStream()">开始</button>
      <button class="btn-stop" title="断开实时流连接" onclick="stopStream()">停止</button>
      <button class="btn-clear" title="仅清空页面显示，不删除真实日志" onclick="clearLogs()">清空</button>
    </div>

    <div id="status" class="status disconnected">未连接</div>
    <div id="logViewer" class="log-viewer"></div>
    <div id="meta" class="meta">等待连接...</div>
  </div>

  <script>
    let eventSource = null;
    let running = false;

    function escapeHtml(text) {
      const div = document.createElement("div");
      div.textContent = text;
      return div.innerHTML;
    }

    function statusClass(line) {
      const l = String(line || "").toLowerCase();
      if (l.includes("error") || l.includes("失败") || l.includes("exception")) return "error";
      if (l.includes("warn") || l.includes("warning") || l.includes("超时")) return "warning";
      if (l.includes("debug") || l.includes("调试")) return "debug";
      return "info";
    }

    function setStatus(connected, text) {
      const status = document.getElementById("status");
      status.className = "status " + (connected ? "connected" : "disconnected");
      status.textContent = text;
    }

    function getSelectedFile() {
      const select = document.getElementById("logFileSelect");
      return select.value || "presales";
    }

    function refreshLogFiles() {
      fetch("/api/logs/files")
        .then(r => r.json())
        .then(data => {
          const select = document.getElementById("logFileSelect");
          const oldVal = select.value;
          select.innerHTML = "";

          const fallback = ["presales", "operations", "aftersales"];
          let files = (data.files || []).map(f => f.name);
          if (!files.length) files = fallback;

          files.forEach(name => {
            const option = document.createElement("option");
            option.value = name;
            option.textContent = name;
            select.appendChild(option);
          });

          if (oldVal && files.includes(oldVal)) {
            select.value = oldVal;
          } else if (files.includes("runtime/presales.log")) {
            select.value = "runtime/presales.log";
          } else {
            select.selectedIndex = 0;
          }
        })
        .catch(() => {
          const select = document.getElementById("logFileSelect");
          if (!select.options.length) {
            ["presales", "operations", "aftersales"].forEach(name => {
              const option = document.createElement("option");
              option.value = name;
              option.textContent = name;
              select.appendChild(option);
            });
            select.value = "presales";
          }
        });
    }

    function renderLines(lines) {
      const viewer = document.getElementById("logViewer");
      let html = "";
      (lines || []).forEach(line => {
        html += '<div class="log-line ' + statusClass(line) + '">' + escapeHtml(line) + '</div>';
      });
      viewer.innerHTML = html || '<div class="log-line info">暂无日志...</div>';
      viewer.scrollTop = viewer.scrollHeight;
    }

    function stopStream() {
      running = false;
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
      setStatus(false, "已停止");
    }

    function startStream() {
      stopStream();
      running = true;
      const file = getSelectedFile();
      const url = "/api/logs/realtime/stream?file=" + encodeURIComponent(file) + "&tail=300";

      setStatus(false, "连接中...");
      document.getElementById("meta").textContent = "连接地址: " + url;

      eventSource = new EventSource(url);
      eventSource.onopen = () => {
        if (!running) return;
        setStatus(true, "已连接: " + file);
      };
      eventSource.onmessage = (ev) => {
        if (!running) return;
        try {
          const data = JSON.parse(ev.data || "{}");
          renderLines(data.lines || []);
          document.getElementById("meta").textContent = "最近更新: " + (data.updated_at || new Date().toLocaleString());
        } catch (_) {}
      };
      eventSource.onerror = () => {
        if (!running) return;
        setStatus(false, "连接中断，2秒后重试...");
        setTimeout(() => {
          if (running) startStream();
        }, 2000);
      };
    }

    function clearLogs() {
      document.getElementById("logViewer").innerHTML = "";
      document.getElementById("meta").textContent = "日志已清空";
    }

    refreshLogFiles();
    setTimeout(startStream, 250);
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    repo: DashboardRepository
    module_console: ModuleConsole
    mimic_ops: MimicOps

    def _send_json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, html: str, status: int = 200) -> None:
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes(self, data: bytes, content_type: str, status: int = 200, download_name: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        self.wfile.write(data)

    def _handle_listing_preview(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            from src.modules.listing.auto_publish import AutoPublishService

            service = AutoPublishService(config=self.mimic_ops._xianguanjia_service_config())
            return _run_async(service.generate_preview(body))
        except Exception as exc:
            return {"ok": False, "step": "error", "error": str(exc)}

    def _handle_listing_publish(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            from src.integrations.xianguanjia.open_platform_client import OpenPlatformClient
            from src.modules.listing.auto_publish import AutoPublishService

            cfg = self.mimic_ops._xianguanjia_service_config().get("xianguanjia", {})
            app_key = str(cfg.get("app_key", "")).strip()
            app_secret = str(cfg.get("app_secret", "")).strip()
            if not app_key or not app_secret:
                return {"ok": False, "step": "init", "error": "闲管家 API 未配置"}

            api_client = OpenPlatformClient(
                base_url=str(cfg.get("base_url", "https://open.goofish.pro")).strip(),
                app_key=app_key,
                app_secret=app_secret,
                seller_id=str(cfg.get("merchant_id", "")).strip() or None,
            )
            service = AutoPublishService(api_client=api_client, config=self.mimic_ops._xianguanjia_service_config())
            preview_data = body.get("preview_data")
            if isinstance(preview_data, dict):
                return _run_async(service.publish_from_preview(preview_data))
            return _run_async(service.publish(body))
        except Exception as exc:
            return {"ok": False, "step": "error", "error": str(exc)}

    def _read_json_body(self) -> dict[str, Any]:
        try:
            content_len = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_len = 0
        if content_len <= 0:
            return {}
        raw = self.rfile.read(content_len)
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _read_multipart_files(self) -> list[tuple[str, bytes]]:
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            return []
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0:
                return []
            raw_data = self.rfile.read(content_length)
        except Exception:
            return []
        if not raw_data:
            return []

        from email import policy
        from email.parser import BytesParser

        # 构造 MIME 外壳，让 parsebytes 可以解析仅 body 的 multipart 数据。
        if raw_data.lstrip().lower().startswith(b"content-type:"):
            mime_raw = raw_data
        else:
            mime_raw = b"".join(
                [
                    f"Content-Type: {content_type}\r\n".encode("utf-8", errors="ignore"),
                    b"MIME-Version: 1.0\r\n\r\n",
                    raw_data,
                ]
            )

        try:
            msg = BytesParser(policy=policy.default).parsebytes(mime_raw)
        except Exception:
            return []

        files: list[tuple[str, bytes]] = []
        for part in msg.walk():
            if part.is_multipart():
                continue
            disposition = str(part.get_content_disposition() or "").strip().lower()
            if disposition not in {"attachment", "form-data"}:
                continue
            filename = part.get_filename()
            if not filename:
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                payload = b""
            if isinstance(payload, str):
                payload = payload.encode("utf-8", errors="ignore")
            if isinstance(payload, bytearray):
                payload = bytes(payload)
            if not isinstance(payload, bytes):
                continue
            files.append((str(filename), payload))
        return files

    def _legacy_dashboard_payload(self, path: str, query: dict[str, list[str]]) -> dict[str, Any]:
        if path == "/api/summary":
            return self.repo.get_summary()
        if path == "/api/trend":
            metric = (query.get("metric") or ["views"])[0]
            days = _safe_int((query.get("days") or ["30"])[0], default=30, min_value=1, max_value=120)
            return self.repo.get_trend(metric=metric, days=days)
        if path == "/api/recent-operations":
            limit = _safe_int((query.get("limit") or ["20"])[0], default=20, min_value=1, max_value=200)
            return self.repo.get_recent_operations(limit=limit)
        limit = _safe_int((query.get("limit") or ["12"])[0], default=12, min_value=1, max_value=200)
        return self.repo.get_top_products(limit=limit)

    def _aggregate_dashboard_payload(self, path: str) -> dict[str, Any] | None:
        # React workbench relies on the stable legacy shape of /api/summary,/api/trend and related endpoints.
        # The richer virtual-goods aggregate payload remains available on /api/dashboard.
        return None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        try:
            if path == "/healthz":
                db_ok = False
                try:
                    with self.repo._connect() as conn:
                        conn.execute("SELECT 1")
                    db_ok = True
                except Exception:
                    pass

                # Module liveness via quick status check
                modules_summary: dict[str, str] = {}
                try:
                    status_payload = self.mimic_ops.service_status()
                    if isinstance(status_payload, dict):
                        modules_summary = {
                            "system_running": "alive" if status_payload.get("system_running") else "dead",
                            "alive_count": str(status_payload.get("alive_count", 0)),
                            "total_modules": str(status_payload.get("total_modules", 0)),
                        }
                except Exception:
                    modules_summary = {"error": "status_check_failed"}

                started = getattr(self.mimic_ops, "_service_started_at", "")
                uptime_seconds = 0
                if started:
                    try:
                        start_dt = datetime.strptime(started, "%Y-%m-%dT%H:%M:%S")
                        uptime_seconds = int((datetime.now() - start_dt).total_seconds())
                    except Exception:
                        pass

                self._send_json(
                    {
                        "status": "ok" if db_ok else "degraded",
                        "timestamp": _now_iso(),
                        "database": "writable" if db_ok else "error",
                        "modules": modules_summary,
                        "uptime_seconds": uptime_seconds,
                    }
                )
                return

            if path == "/":
                self._send_html(DASHBOARD_HTML)
                return

            if path == "/cookie":
                self._send_html(MIMIC_COOKIE_HTML)
                return

            if path == "/test":
                self._send_html(MIMIC_TEST_HTML)
                return

            if path == "/logs":
                self._send_html(MIMIC_LOGS_HTML)
                return

            if path == "/logs/realtime":
                self._send_html(MIMIC_LOGS_REALTIME_HTML)
                return

            if path in {"/api/summary", "/api/trend", "/api/recent-operations", "/api/top-products"}:
                # Wave D legacy dashboard endpoints are backed by virtual_goods_service.get_dashboard_metrics.
                payload = self._aggregate_dashboard_payload(path)
                if isinstance(payload, dict):
                    status = 200 if payload.get("success") else 400
                    self._send_json(payload, status=status)
                    return

                self._send_json(self._legacy_dashboard_payload(path, query))
                return

            if path == "/api/module/status":
                window = _safe_int((query.get("window") or ["60"])[0], default=60, min_value=1, max_value=10080)
                limit = _safe_int((query.get("limit") or ["20"])[0], default=20, min_value=1, max_value=200)
                payload = self.module_console.status(window_minutes=window, limit=limit)
                status = 200 if not payload.get("error") else 500
                self._send_json(payload, status=status)
                return

            if path == "/api/module/check":
                skip_gateway = (query.get("skip_gateway") or ["0"])[0] in {"1", "true", "yes"}
                payload = self.module_console.check(skip_gateway=skip_gateway)
                status = 200 if not payload.get("error") else 500
                self._send_json(payload, status=status)
                return

            if path == "/api/module/logs":
                target = str((query.get("target") or ["all"])[0]).strip().lower()
                tail = _safe_int((query.get("tail") or ["120"])[0], default=120, min_value=10, max_value=500)
                payload = self.module_console.logs(target=target, tail_lines=tail)
                status = 200 if not payload.get("error") else 500
                self._send_json(payload, status=status)
                return

            if path == "/api/config":
                self._send_json(self.mimic_ops.get_runtime_config())
                return

            if path == "/api/config/sections":
                self._send_json(self.mimic_ops.get_runtime_config_sections())
                return

            if path == "/api/accounts":
                self._send_json(self.mimic_ops.list_accounts())
                return

            if path == "/api/status":
                self._send_json(self.mimic_ops.service_status())
                return

            if path == "/api/get-cookie":
                self._send_json(self.mimic_ops.get_cookie())
                return

            if path == "/api/route-stats":
                self._send_json(self.mimic_ops.route_stats())
                return

            if path == "/api/export-routes":
                data, filename = self.mimic_ops.export_routes_zip()
                self._send_bytes(data=data, content_type="application/zip", download_name=filename)
                return

            if path == "/api/download-cookie-plugin":
                try:
                    data, filename = self.mimic_ops.export_cookie_plugin_bundle()
                    self._send_bytes(data=data, content_type="application/zip", download_name=filename)
                except FileNotFoundError as exc:
                    self._send_json(_error_payload(str(exc), code="NOT_FOUND"), status=404)
                return

            if path == "/api/get-template":
                use_default = (query.get("default") or ["false"])[0].lower() in {"1", "true", "yes"}
                self._send_json(self.mimic_ops.get_template(default=use_default))
                return

            if path == "/api/replies":
                self._send_json(self.mimic_ops.get_replies())
                return

            if path == "/api/get-markup-rules":
                self._send_json(self.mimic_ops.get_markup_rules())
                return

            if path == "/api/logs/files":
                self._send_json(self.mimic_ops.list_log_files())
                return

            if path == "/api/logs/content":
                file_name = str((query.get("file") or [""])[0]).strip()
                tail = _safe_int((query.get("tail") or ["200"])[0], default=200, min_value=1, max_value=5000)
                page_raw = (query.get("page") or [None])[0]
                size_raw = (query.get("size") or [None])[0]
                search = str((query.get("search") or [""])[0]).strip()
                if page_raw is not None or size_raw is not None or search:
                    page = _safe_int(
                        str(page_raw) if page_raw is not None else None, default=1, min_value=1, max_value=100000
                    )
                    size = _safe_int(
                        str(size_raw) if size_raw is not None else None, default=100, min_value=10, max_value=2000
                    )
                    payload = self.mimic_ops.read_log_content(
                        file_name=file_name,
                        page=page,
                        size=size,
                        search=search,
                    )
                else:
                    payload = self.mimic_ops.read_log_content(file_name=file_name, tail=tail)
                self._send_json(payload, status=200 if payload.get("success") else 404)
                return

            if path == "/api/logs/realtime/stream":
                file_name = str((query.get("file") or ["presales"])[0]).strip()
                tail = _safe_int((query.get("tail") or ["200"])[0], default=200, min_value=1, max_value=1000)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()

                last = ""
                try:
                    for _ in range(180):
                        payload = self.mimic_ops.read_log_content(file_name=file_name, tail=tail)
                        lines = (
                            payload.get("lines", [])
                            if payload.get("success")
                            else [payload.get("error", "log not found")]
                        )
                        text = "\n".join(lines)
                        if text != last:
                            event = json.dumps(
                                {"success": True, "lines": lines, "updated_at": _now_iso()}, ensure_ascii=False
                            )
                            self.wfile.write(f"data: {event}\n\n".encode())
                            self.wfile.flush()
                            last = text
                        time.sleep(1)
                except (BrokenPipeError, ConnectionResetError):
                    return
                return

            if path == "/api/virtual-goods/metrics":
                payload: dict[str, Any]
                metrics_query = getattr(self.mimic_ops, "get_virtual_goods_metrics", None)
                if callable(metrics_query):
                    result = metrics_query()
                    payload = (
                        result if isinstance(result, dict) else _error_payload("virtual_goods metrics payload invalid")
                    )
                else:
                    aggregate_query = getattr(self.mimic_ops, "get_dashboard_readonly_aggregate", None)
                    aggregate = aggregate_query() if callable(aggregate_query) else None
                    if isinstance(aggregate, dict):
                        payload = {
                            "success": bool(aggregate.get("success")),
                            "module": "virtual_goods",
                            "readonly": True,
                            "service_response": aggregate.get("service_response", {}),
                            "dashboard_panels": aggregate.get("sections", {}),
                            "generated_at": aggregate.get("generated_at", ""),
                        }
                        if not payload["success"]:
                            payload = aggregate
                    else:
                        payload = _error_payload(
                            "virtual_goods metrics endpoint unavailable", code="VG_QUERY_NOT_AVAILABLE"
                        )
                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            if path == "/api/dashboard":
                aggregate = self.mimic_ops.get_dashboard_readonly_aggregate()
                self._send_json(aggregate, status=200 if aggregate.get("success") else 400)
                return

            if path == "/api/virtual-goods/inspect-order":
                order_id = str((query.get("order_id") or query.get("xianyu_order_id") or [""])[0]).strip()
                payload = self.mimic_ops.inspect_virtual_goods_order(order_id)
                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            if path == "/api/xgj/products":
                page_no = _safe_int((query.get("page_no") or ["1"])[0], default=1, min_value=1, max_value=9999)
                page_size = _safe_int((query.get("page_size") or ["20"])[0], default=20, min_value=1, max_value=200)
                search = str((query.get("search") or [""])[0]).strip()
                payload = self.mimic_ops.list_xianguanjia_products(
                    page_no=page_no,
                    page_size=page_size,
                    query=search,
                )
                self._send_json(payload, status=200 if payload.get("ok") else 400)
                return

            if path == "/api/xgj/orders":
                page_no = _safe_int((query.get("page_no") or ["1"])[0], default=1, min_value=1, max_value=9999)
                page_size = _safe_int((query.get("page_size") or ["20"])[0], default=20, min_value=1, max_value=200)
                status_raw = str((query.get("order_status") or [""])[0]).strip()
                order_status = int(status_raw) if status_raw.isdigit() else None
                search = str((query.get("search") or [""])[0]).strip()
                payload = self.mimic_ops.list_xianguanjia_orders(
                    page_no=page_no,
                    page_size=page_size,
                    order_status=order_status,
                    query=search,
                )
                self._send_json(payload, status=200 if payload.get("ok") else 400)
                return

            if path == "/api/listing/templates":
                from src.modules.listing.templates import list_templates

                self._send_json({"ok": True, "templates": list_templates()})
                return

            if path == "/api/generated-image":
                raw_path = str((query.get("path") or [""])[0]).strip()
                try:
                    data, content_type = self.mimic_ops.read_generated_image(raw_path)
                except FileNotFoundError as exc:
                    self._send_json(_error_payload(str(exc), code="NOT_FOUND"), status=404)
                    return
                except PermissionError as exc:
                    self._send_json(_error_payload(str(exc), code="FORBIDDEN"), status=403)
                    return
                self._send_bytes(data=data, content_type=content_type)
                return

            self._send_json(_error_payload("Not Found", code="NOT_FOUND"), status=404)
        except sqlite3.Error as e:
            self._send_json(_error_payload(f"Database error: {e}", code="DATABASE_ERROR"), status=500)
        except Exception as e:  # pragma: no cover - safety net
            self._send_json(_error_payload(str(e), code="INTERNAL_ERROR"), status=500)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/api/module/control":
                body = self._read_json_body()
                action = str(body.get("action") or "").strip().lower()
                target = str(body.get("target") or "all").strip().lower()
                payload = self.module_console.control(action=action, target=target)
                status = 200 if not payload.get("error") else 400
                self._send_json(payload, status=status)
                return

            if path == "/api/service/control":
                body = self._read_json_body()
                action = str(body.get("action") or "").strip().lower()
                payload = self.mimic_ops.service_control(action=action)
                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            if path == "/api/service/recover":
                body = self._read_json_body()
                target = str(body.get("target") or "presales").strip().lower()
                payload = self.mimic_ops.service_recover(target=target)
                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            if path == "/api/service/auto-fix":
                payload = self.mimic_ops.service_auto_fix()
                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            if path == "/api/config":
                body = self._read_json_body()
                payload = self.mimic_ops.save_runtime_config(body)
                self._send_json(payload, status=200 if payload.get("ok") else 400)
                return

            if path == "/api/update-cookie":
                body = self._read_json_body()
                cookie = str(body.get("cookie") or "").strip()
                payload = self.mimic_ops.update_cookie(cookie, auto_recover=True)
                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            if path == "/api/import-cookie-plugin":
                try:
                    files = self._read_multipart_files()
                except Exception as exc:
                    self._send_json(
                        {
                            "success": False,
                            "error": "Failed to parse upload body. Please retry with txt/json/zip exports.",
                            "details": str(exc),
                        },
                        status=400,
                    )
                    return

                try:
                    payload = self.mimic_ops.import_cookie_plugin_files(files, auto_recover=True)
                except Exception as exc:
                    self._send_json(
                        {
                            "success": False,
                            "error": "Cookie import processing failed.",
                            "details": str(exc),
                        },
                        status=400,
                    )
                    return

                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            if path == "/api/parse-cookie":
                body = self._read_json_body()
                cookie_text = str(body.get("text") or body.get("cookie") or "").strip()
                payload = self.mimic_ops.parse_cookie_text(cookie_text)
                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            if path == "/api/cookie-diagnose":
                body = self._read_json_body()
                cookie_text = str(body.get("text") or body.get("cookie") or "").strip()
                payload = self.mimic_ops.diagnose_cookie(cookie_text)
                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            if path == "/api/import-routes":
                try:
                    files = self._read_multipart_files()
                except Exception as exc:
                    self._send_json(
                        {
                            "success": False,
                            "error": "Failed to parse upload body. Please retry with xlsx/xls/csv/zip files.",
                            "details": str(exc),
                        },
                        status=400,
                    )
                    return

                try:
                    payload = self.mimic_ops.import_route_files(files)
                except Exception as exc:
                    self._send_json(
                        {
                            "success": False,
                            "error": "Import processing failed.",
                            "details": str(exc),
                        },
                        status=400,
                    )
                    return

                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            if path == "/api/import-markup":
                try:
                    files = self._read_multipart_files()
                except Exception as exc:
                    self._send_json(
                        {
                            "success": False,
                            "error": "Failed to parse upload body. Please retry with markup files.",
                            "details": str(exc),
                        },
                        status=400,
                    )
                    return

                try:
                    payload = self.mimic_ops.import_markup_files(files)
                except Exception as exc:
                    self._send_json(
                        {
                            "success": False,
                            "error": "Import processing failed.",
                            "details": str(exc),
                        },
                        status=400,
                    )
                    return

                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            if path == "/api/reset-database":
                body = self._read_json_body()
                db_type = str(body.get("type") or "all")
                payload = self.mimic_ops.reset_database(db_type=db_type)
                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            if path == "/api/save-template":
                body = self._read_json_body()
                payload = self.mimic_ops.save_template(
                    weight_template=str(body.get("weight_template") or ""),
                    volume_template=str(body.get("volume_template") or ""),
                )
                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            if path == "/api/save-markup-rules":
                body = self._read_json_body()
                payload = self.mimic_ops.save_markup_rules(body.get("markup_rules"))
                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            if path == "/api/test-reply":
                body = self._read_json_body()
                payload = self.mimic_ops.test_reply(body)
                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            if path == "/api/xgj/settings":
                body = self._read_json_body()
                payload = self.mimic_ops.save_xianguanjia_settings(body)
                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            if path == "/api/xgj/retry-price":
                body = self._read_json_body()
                payload = self.mimic_ops.retry_xianguanjia_price(body)
                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            if path == "/api/xgj/retry-ship":
                body = self._read_json_body()
                payload = self.mimic_ops.retry_xianguanjia_delivery(body)
                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            if path == "/api/orders/callback":
                body = self._read_json_body()
                payload = self.mimic_ops.handle_order_callback(body)
                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            if path == "/api/virtual-goods/inspect-order":
                body = self._read_json_body()
                order_id = str(body.get("order_id") or body.get("xianyu_order_id") or "").strip()
                payload = self.mimic_ops.inspect_virtual_goods_order(order_id)
                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            if path == "/api/xgj/product/publish":
                body = self._read_json_body()
                payload = self.mimic_ops.publish_xianguanjia_product(body)
                self._send_json(payload, status=200 if payload.get("ok") else 400)
                return

            if path == "/api/xgj/product/unpublish":
                body = self._read_json_body()
                payload = self.mimic_ops.unpublish_xianguanjia_product(body)
                self._send_json(payload, status=200 if payload.get("ok") else 400)
                return

            if path == "/api/xgj/order/modify-price":
                body = self._read_json_body()
                payload = self.mimic_ops.modify_xianguanjia_order_price(body)
                self._send_json(payload, status=200 if payload.get("ok") else 400)
                return

            if path == "/api/xgj/order/deliver":
                body = self._read_json_body()
                payload = self.mimic_ops.deliver_xianguanjia_order(body)
                self._send_json(payload, status=200 if payload.get("ok") else 400)
                return

            if path == "/api/listing/preview":
                body = self._read_json_body()
                payload = self._handle_listing_preview(body)
                self._send_json(payload, status=200 if payload.get("ok") else 400)
                return

            if path == "/api/listing/publish":
                body = self._read_json_body()
                payload = self._handle_listing_publish(body)
                self._send_json(payload, status=200 if payload.get("ok") else 400)
                return

            self._send_json(_error_payload("Not Found", code="NOT_FOUND"), status=404)
        except Exception as e:  # pragma: no cover - safety net
            self._send_json(_error_payload(str(e), code="INTERNAL_ERROR"), status=500)

    def log_message(self, format: str, *args: Any) -> None:
        return


def run_server(host: str = "127.0.0.1", port: int = 8091, db_path: str | None = None) -> None:
    config = get_config()
    resolved_db = db_path or config.database.get("path", "data/agent.db")

    Path(resolved_db).parent.mkdir(parents=True, exist_ok=True)
    DashboardHandler.repo = DashboardRepository(resolved_db)
    DashboardHandler.module_console = ModuleConsole(project_root=Path(__file__).resolve().parents[1])
    DashboardHandler.mimic_ops = MimicOps(
        project_root=Path(__file__).resolve().parents[1],
        module_console=DashboardHandler.module_console,
    )

    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Dashboard running: http://{host}:{port}")
    print(f"Using database: {resolved_db}")
    server.serve_forever()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="闲鱼后台可视化服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8091, help="监听端口")
    parser.add_argument("--db-path", default=None, help="数据库路径（默认读取配置）")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_server(host=args.host, port=args.port, db_path=args.db_path)


if __name__ == "__main__":
    main()
