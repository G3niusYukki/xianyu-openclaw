"""轻量后台可视化与模块控制服务。"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import io
import json
import mimetypes
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

import logging

import yaml

from src.core.config import get_config
from src.dashboard.repository import DashboardRepository
from src.dashboard.module_console import ModuleConsole, MODULE_TARGETS
from src.dashboard.config_service import (
    read_system_config as _read_system_config,
    write_system_config as _write_system_config,
    CONFIG_SECTIONS as _CONFIG_SECTIONS,
    _ALLOWED_CONFIG_SECTIONS,
    _SENSITIVE_CONFIG_KEYS,
    mask_sensitive as _mask_config_sensitive,
    update_config as _update_config,
)
from src.modules.messages.service import MessagesService
from src.modules.quote.cost_table import CostTableRepository, normalize_courier_name
from src.modules.quote.setup import DEFAULT_MARKUP_RULES, QuoteSetupService
from src.modules.virtual_goods.service import VirtualGoodsService

logger = logging.getLogger(__name__)


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
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=5000")

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

        cookie_health_info: dict[str, Any] = {"healthy": False, "message": "未检查", "score": 0}
        try:
            from src.core.cookie_health import CookieHealthChecker

            if cookie_text:
                _ck_checker = CookieHealthChecker(cookie_text, timeout_seconds=5.0)
                _ck_result = _ck_checker.check_sync(force=False)
                cookie_health_info = {
                    "healthy": bool(_ck_result.get("healthy")),
                    "message": _ck_result.get("message", ""),
                    "score": 100 if _ck_result.get("healthy") else 0,
                }
            else:
                cookie_health_info = {"healthy": False, "message": "Cookie 未配置", "score": 0}
        except Exception:
            pass

        return {
            "success": True,
            "service": dict(self._service_state),
            "module": module_status,
            "cookie_exists": bool(cookie.get("success", False)),
            "cookie_valid": bool(cookie.get("success", False)),
            "cookie_length": int(cookie.get("length", 0) or 0),
            "cookie_health": cookie_health_info,
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


# -- Embedded HTML moved to src/dashboard/embedded_html.py --
def _get_embedded_html(name: str) -> str:
    from src.dashboard.embedded_html import (
        DASHBOARD_HTML,
        MIMIC_COOKIE_HTML,
        MIMIC_TEST_HTML,
        MIMIC_LOGS_HTML,
        MIMIC_LOGS_REALTIME_HTML,
    )

    return {
        "DASHBOARD_HTML": DASHBOARD_HTML,
        "MIMIC_COOKIE_HTML": MIMIC_COOKIE_HTML,
        "MIMIC_TEST_HTML": MIMIC_TEST_HTML,
        "MIMIC_LOGS_HTML": MIMIC_LOGS_HTML,
        "MIMIC_LOGS_REALTIME_HTML": MIMIC_LOGS_REALTIME_HTML,
    }[name]


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
        """生成自动上架预览。"""
        try:
            import asyncio
            from src.modules.listing.auto_publish import AutoPublishService

            service = AutoPublishService(config=self._xianguanjia_service_config())
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(service.generate_preview(body))
            finally:
                loop.close()
        except Exception as e:
            return {"ok": False, "step": "error", "error": str(e)}

    def _handle_listing_publish(self, body: dict[str, Any]) -> dict[str, Any]:
        """执行自动上架。"""
        try:
            import asyncio
            from src.modules.listing.auto_publish import AutoPublishService
            from src.integrations.xianguanjia.open_platform_client import OpenPlatformClient

            cfg = self._xianguanjia_service_config().get("xianguanjia", {})
            app_key = str(cfg.get("app_key", "")).strip()
            app_secret = str(cfg.get("app_secret", "")).strip()
            if not app_key or not app_secret:
                return {"ok": False, "step": "init", "error": "闲管家 API 未配置"}

            api_client = OpenPlatformClient(
                base_url=str(cfg.get("base_url", "https://open.goofish.pro")).strip(),
                app_key=app_key,
                app_secret=app_secret,
            )
            service = AutoPublishService(
                api_client=api_client,
                config=self._xianguanjia_service_config(),
            )

            preview_data = body.get("preview_data")
            loop = asyncio.new_event_loop()
            try:
                if preview_data and isinstance(preview_data, dict):
                    return loop.run_until_complete(service.publish_from_preview(preview_data))
                return loop.run_until_complete(service.publish(body))
            finally:
                loop.close()
        except Exception as e:
            return {"ok": False, "step": "error", "error": str(e)}

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
        aggregate_query = getattr(self.mimic_ops, "get_dashboard_readonly_aggregate", None)
        if not callable(aggregate_query):
            return None

        aggregate = aggregate_query()
        if not isinstance(aggregate, dict):
            return None
        if not aggregate.get("success"):
            return aggregate

        sections = aggregate.get("sections") if isinstance(aggregate.get("sections"), dict) else {}
        panel_map = {
            "/api/summary": "operations_funnel_overview",
            "/api/trend": "fulfillment_efficiency",
            "/api/recent-operations": "exception_priority_pool",
            "/api/top-products": "product_operations",
        }
        key = panel_map.get(path, "operations_funnel_overview")
        panel_payload = sections.get(key) if isinstance(sections.get(key), dict) else {}
        return {
            "success": True,
            "readonly": True,
            "source": "virtual_goods_service.get_dashboard_metrics",
            "view": key,
            "data": panel_payload,
        }

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

            if path in {"/", "/cookie", "/test", "/logs", "/logs/realtime"}:
                self._serve_spa_file(path)
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

            if path == "/api/listing/templates":
                from src.modules.listing.templates import list_templates

                self._send_json({"ok": True, "templates": list_templates()})
                return

            if path == "/api/health/check":
                import time as _t

                result: dict[str, Any] = {"timestamp": _now_iso()}

                cookie_info: dict[str, Any] = {"ok": False, "message": "未检查"}
                try:
                    from src.core.cookie_health import CookieHealthChecker

                    cookie_text = os.environ.get("XIANYU_COOKIE_1", "")
                    if not cookie_text:
                        ck = self.mimic_ops.get_cookie()
                        cookie_text = str(ck.get("cookie", "") or "")
                    checker = CookieHealthChecker(cookie_text, timeout_seconds=8.0)
                    ck_result = checker.check_sync(force=True)
                    cookie_info = {"ok": bool(ck_result.get("healthy")), "message": ck_result.get("message", "")}
                except Exception as exc:
                    cookie_info = {"ok": False, "message": f"检查异常: {exc}"}
                result["cookie"] = cookie_info

                ai_info: dict[str, Any] = {"ok": False, "message": "未配置"}
                try:
                    ai_key = os.environ.get("AI_API_KEY", "")
                    ai_base = os.environ.get("AI_BASE_URL", "")
                    ai_model = os.environ.get("AI_MODEL", "")
                    if not ai_key or not ai_base:
                        try:
                            _sys_cfg_path = (
                                Path(__file__).resolve().parents[1] / "server" / "data" / "system_config.json"
                            )
                            if _sys_cfg_path.exists():
                                _sys_cfg = json.loads(_sys_cfg_path.read_text(encoding="utf-8"))
                                ai_cfg = _sys_cfg.get("ai", {})
                                ai_key = ai_key or str(ai_cfg.get("api_key", "") or "")
                                ai_base = ai_base or str(ai_cfg.get("base_url", "") or "")
                                ai_model = ai_model or str(ai_cfg.get("model", "") or "")
                        except Exception:
                            pass
                    ai_model = ai_model or "qwen-plus"
                    if ai_key and ai_base:
                        t0 = _t.time()
                        import httpx

                        chat_url = ai_base.rstrip("/") + "/chat/completions"
                        with httpx.Client(timeout=8.0) as hc:
                            resp = hc.post(
                                chat_url,
                                headers={"Authorization": f"Bearer {ai_key}", "Content-Type": "application/json"},
                                json={
                                    "model": ai_model,
                                    "max_tokens": 1,
                                    "messages": [{"role": "user", "content": "hi"}],
                                },
                            )
                        latency = int((_t.time() - t0) * 1000)
                        if resp.status_code == 200:
                            ai_info = {"ok": True, "message": "连通", "latency_ms": latency}
                        else:
                            _status_msgs = {401: "API Key 无效", 403: "无权访问", 429: "请求过频"}
                            _msg = _status_msgs.get(resp.status_code, f"HTTP {resp.status_code}")
                            ai_info = {"ok": False, "message": _msg, "latency_ms": latency}
                    else:
                        ai_info = {"ok": False, "message": "API Key 或 Base URL 未配置"}
                except Exception as exc:
                    ai_info = {"ok": False, "message": f"检查异常: {type(exc).__name__}"}
                result["ai"] = ai_info

                # XGJ connectivity check (migrated from Node.js)
                xgj_info: dict[str, Any] = {"ok": False, "message": "未检查"}
                try:
                    sys_cfg = _read_system_config()
                    xgj_cfg = sys_cfg.get("xianguanjia", {})
                    xgj_app_key = str(xgj_cfg.get("app_key", "") or os.environ.get("XGJ_APP_KEY", ""))
                    xgj_app_secret = str(xgj_cfg.get("app_secret", "") or os.environ.get("XGJ_APP_SECRET", ""))
                    xgj_base = str(
                        xgj_cfg.get("base_url", "") or os.environ.get("XGJ_BASE_URL", "https://open.goofish.pro")
                    )
                    if not xgj_app_key or not xgj_app_secret:
                        xgj_info = {"ok": False, "message": "AppKey 或 AppSecret 未配置"}
                    else:
                        from src.integrations.xianguanjia.signing import sign_open_platform_request as _xgj_sign

                        xgj_ts = str(int(time.time()))
                        xgj_body = json.dumps({"method": "health.check"})
                        xgj_sign_val = _xgj_sign(
                            app_key=xgj_app_key, app_secret=xgj_app_secret, timestamp=xgj_ts, body=xgj_body
                        )
                        xgj_t0 = _t.time()
                        import httpx as _hx2

                        xgj_resp = _hx2.post(
                            f"{xgj_base}/api/open/proxy",
                            content=xgj_body,
                            headers={
                                "Content-Type": "application/json",
                                "x-app-key": xgj_app_key,
                                "x-timestamp": xgj_ts,
                                "x-sign": xgj_sign_val,
                            },
                            timeout=8.0,
                        )
                        xgj_latency = int((_t.time() - xgj_t0) * 1000)
                        if xgj_resp.status_code < 500:
                            xgj_info = {"ok": True, "message": "连通", "latency_ms": xgj_latency}
                        else:
                            xgj_info = {
                                "ok": False,
                                "message": f"HTTP {xgj_resp.status_code}",
                                "latency_ms": xgj_latency,
                            }
                except Exception as exc:
                    xgj_info = {"ok": False, "message": f"检查异常: {type(exc).__name__}"}
                result["xgj"] = xgj_info

                result["node"] = {"ok": True, "message": "已合并至 Python"}
                result["services"] = {"python": {"ok": True, "message": "运行中"}}
                self._send_json(result)
                return

            if path == "/api/cookie/auto-grab/status":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                grabber = getattr(DashboardHandler, "_cookie_grabber", None)
                try:
                    for _ in range(600):
                        if grabber is not None:
                            p = grabber.progress
                            event = json.dumps(
                                {
                                    "stage": p.stage.value if hasattr(p.stage, "value") else str(p.stage),
                                    "message": p.message,
                                    "hint": p.hint,
                                    "progress": p.progress,
                                    "error": p.error,
                                },
                                ensure_ascii=False,
                            )
                            self.wfile.write(f"data: {event}\n\n".encode())
                            self.wfile.flush()
                            if p.stage.value in {"success", "failed", "cancelled"}:
                                break
                        else:
                            event = json.dumps(
                                {"stage": "idle", "message": "未在运行", "hint": "", "progress": 0, "error": ""},
                                ensure_ascii=False,
                            )
                            self.wfile.write(f"data: {event}\n\n".encode())
                            self.wfile.flush()
                            break
                        time.sleep(0.5)
                except (BrokenPipeError, ConnectionResetError):
                    return
                return

            if path == "/api/cookie/auto-refresh/status":
                refresher = getattr(DashboardHandler, "_cookie_auto_refresher", None)
                if refresher is None:
                    self._send_json(
                        {
                            "enabled": False,
                            "interval_minutes": 0,
                            "message": "自动刷新未启用（设置 COOKIE_AUTO_REFRESH=true 启用）",
                        }
                    )
                else:
                    from dataclasses import asdict

                    s = refresher.status()
                    self._send_json(asdict(s))
                return

            # ---------- Config CRUD (migrated from Node.js) ----------
            if path == "/api/config":
                self._send_json({"ok": True, "config": _read_system_config()})
                return

            if path == "/api/config/sections":
                self._send_json({"ok": True, "sections": _CONFIG_SECTIONS})
                return

            # ---------- SPA static file serving ----------
            if path.startswith("/api/"):
                self._send_json(_error_payload("Not Found", code="NOT_FOUND"), status=404)
                return

            self._serve_spa_file(path)

        except sqlite3.Error as e:
            self._send_json(_error_payload(f"Database error: {e}", code="DATABASE_ERROR"), status=500)
        except Exception as e:  # pragma: no cover - safety net
            self._send_json(_error_payload(str(e), code="INTERNAL_ERROR"), status=500)

    def _serve_spa_file(self, path: str) -> None:
        """Serve React SPA static files from client/dist/."""
        dist_dir = Path(__file__).resolve().parents[1] / "client" / "dist"
        if not dist_dir.exists():
            self._send_html(_get_embedded_html("DASHBOARD_HTML"))
            return

        file_path = dist_dir / path.lstrip("/")
        if file_path.is_file():
            content_type, _ = mimetypes.guess_type(str(file_path))
            content_type = content_type or "application/octet-stream"
            data = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            if "/assets/" in path:
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            self.wfile.write(data)
            return

        index_html = dist_dir / "index.html"
        if index_html.is_file():
            self._send_html(index_html.read_text(encoding="utf-8"))
        else:
            self._send_html(_get_embedded_html("DASHBOARD_HTML"))

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/config":
                body = self._read_json_body()
                current = _read_system_config()
                for section, values in body.items():
                    if section not in _ALLOWED_CONFIG_SECTIONS:
                        continue
                    if not isinstance(values, dict):
                        continue
                    clean: dict[str, Any] = {}
                    for k, v in values.items():
                        if not isinstance(k, str) or k.startswith("__"):
                            continue
                        if any(s in k.lower() for s in _SENSITIVE_CONFIG_KEYS) and isinstance(v, str) and "****" in v:
                            continue
                        clean[k] = v
                    current[section] = {**(current.get(section) or {}), **clean}
                _write_system_config(current)
                self._send_json({"ok": True, "message": "Configuration updated", "config": current})
                return

            self._send_json(_error_payload("Not Found", code="NOT_FOUND"), status=404)
        except Exception as e:
            self._send_json(_error_payload(str(e), code="INTERNAL_ERROR"), status=500)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/api/ai/test":
                import time as _t

                body = self._read_json_body()
                ai_key = str(body.get("api_key") or "").strip()
                ai_base = str(body.get("base_url") or "").strip()
                ai_model = str(body.get("model") or "").strip() or "qwen-plus"
                if not ai_key or not ai_base:
                    self._send_json({"ok": False, "message": "请填写 API Key 和 API 地址"})
                    return
                try:
                    t0 = _t.time()
                    import httpx

                    chat_url = ai_base.rstrip("/") + "/chat/completions"
                    with httpx.Client(timeout=10.0) as hc:
                        resp = hc.post(
                            chat_url,
                            headers={"Authorization": f"Bearer {ai_key}", "Content-Type": "application/json"},
                            json={"model": ai_model, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]},
                        )
                    latency = int((_t.time() - t0) * 1000)
                    if resp.status_code == 200:
                        self._send_json({"ok": True, "message": f"连接成功（延迟 {latency}ms）", "latency_ms": latency})
                    else:
                        detail = ""
                        try:
                            detail = resp.json().get("error", {}).get("message", "")
                        except Exception:
                            pass
                        status_msgs = {
                            401: "API Key 无效或已过期，请检查后重试",
                            403: "API Key 无权访问该模型",
                            404: f"模型 {ai_model} 不存在，请检查模型名称",
                            429: "请求过于频繁，请稍后再试",
                        }
                        msg = status_msgs.get(resp.status_code, f"HTTP {resp.status_code}")
                        if detail:
                            msg += f"（{detail}）"
                        self._send_json({"ok": False, "message": msg, "latency_ms": latency})
                except Exception as exc:
                    self._send_json({"ok": False, "message": f"连接异常: {type(exc).__name__}: {exc}"})
                return

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

            if path == "/api/cookie/validate":
                body = self._read_json_body()
                cookie_text = str(body.get("cookie") or body.get("text") or "").strip()
                if not cookie_text:
                    self._send_json({"ok": False, "grade": "F", "message": "Cookie 不能为空"}, status=400)
                    return
                diagnosis = self.mimic_ops.diagnose_cookie(cookie_text)
                grade = diagnosis.get("grade", "F")
                self._send_json(
                    {
                        "ok": grade in ("A", "B"),
                        "grade": grade,
                        "message": diagnosis.get("message", ""),
                        "actions": diagnosis.get("actions", []),
                        "required_present": diagnosis.get("required_present", []),
                        "required_missing": diagnosis.get("required_missing", []),
                        "cookie_items": diagnosis.get("cookie_items", 0),
                    }
                )
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

            if path == "/api/cookie/auto-grab":
                import threading
                from src.core.cookie_grabber import CookieGrabber

                if getattr(DashboardHandler, "_cookie_grab_running", False):
                    self._send_json({"ok": False, "error": "已有获取任务在运行"}, status=409)
                    return

                grabber = CookieGrabber()
                DashboardHandler._cookie_grabber = grabber
                DashboardHandler._cookie_grab_running = True

                def _run_grab() -> None:
                    import asyncio

                    loop = asyncio.new_event_loop()
                    try:
                        result = loop.run_until_complete(grabber.auto_grab())
                        DashboardHandler._cookie_grab_result = {
                            "ok": result.ok,
                            "source": result.source,
                            "message": result.message,
                            "error": result.error,
                        }
                    except Exception as exc:
                        DashboardHandler._cookie_grab_result = {"ok": False, "error": str(exc)}
                    finally:
                        loop.close()
                        DashboardHandler._cookie_grab_running = False

                t = threading.Thread(target=_run_grab, daemon=True)
                t.start()
                self._send_json({"ok": True, "message": "Cookie 获取任务已启动，请通过 SSE 接口监听进度"})
                return

            if path == "/api/cookie/auto-grab/cancel":
                grabber = getattr(DashboardHandler, "_cookie_grabber", None)
                if grabber is not None:
                    grabber.cancel()
                    self._send_json({"ok": True, "message": "已取消"})
                else:
                    self._send_json({"ok": False, "error": "没有正在运行的获取任务"})
                return

            if path == "/api/notifications/test":
                body = self._read_json_body()
                channel = str(body.get("channel", "")).strip()
                webhook_url = str(body.get("webhook_url", "")).strip()
                if not channel or not webhook_url:
                    self._send_json({"ok": False, "error": "缺少 channel 或 webhook_url"}, status=400)
                    return

                import asyncio

                test_msg = "【闲鱼自动化】通知测试\n如果你看到这条消息，说明通知配置成功！"

                async def _send() -> bool:
                    if channel == "feishu":
                        from src.modules.messages.notifications import FeishuNotifier

                        return await FeishuNotifier(webhook_url).send_text(test_msg)
                    elif channel == "wechat":
                        from src.modules.messages.notifications import WeChatNotifier

                        return await WeChatNotifier(webhook_url).send_text(test_msg)
                    return False

                loop = asyncio.new_event_loop()
                try:
                    ok = loop.run_until_complete(_send())
                finally:
                    loop.close()

                if ok:
                    self._send_json({"ok": True, "message": "测试消息发送成功"})
                else:
                    self._send_json({"ok": False, "error": "发送失败，请检查 Webhook URL 是否正确"}, status=400)
                return

            # ---------- XGJ proxy (migrated from Node.js) ----------
            if path == "/api/xgj/proxy":
                body = self._read_json_body()
                api_path = str(body.get("apiPath") or body.get("path") or "")
                req_body = body.get("body") or body.get("payload") or {}
                if not api_path or not api_path.startswith("/api/open/"):
                    self._send_json({"error": "Invalid apiPath"}, status=400)
                    return
                cfg = _read_system_config()
                xgj = cfg.get("xianguanjia", {})
                app_key = str(xgj.get("app_key", ""))
                app_secret = str(xgj.get("app_secret", ""))
                base_url = str(xgj.get("base_url", "") or "https://open.goofish.pro")
                mode = str(xgj.get("mode", "self_developed"))
                seller_id = str(xgj.get("seller_id", ""))
                if not app_key or not app_secret:
                    self._send_json(
                        {"ok": False, "error": "闲管家 API 未配置，请在设置中配置 AppKey 和 AppSecret"}, status=400
                    )
                    return
                payload_str = json.dumps(req_body, ensure_ascii=False)
                ts = str(int(time.time()))
                from src.integrations.xianguanjia.signing import sign_open_platform_request, sign_business_request

                if mode == "business" and seller_id:
                    sign = sign_business_request(
                        app_key=app_key, app_secret=app_secret, seller_id=seller_id, timestamp=ts, body=payload_str
                    )
                else:
                    sign = sign_open_platform_request(
                        app_key=app_key, app_secret=app_secret, timestamp=ts, body=payload_str
                    )
                try:
                    import httpx

                    url = f"{base_url}{api_path}"
                    with httpx.Client(timeout=15.0) as hc:
                        resp = hc.post(
                            url,
                            params={"appid": app_key, "timestamp": ts, "sign": sign},
                            content=payload_str,
                            headers={"Content-Type": "application/json"},
                        )
                    self._send_json({"ok": True, "data": resp.json()})
                except Exception as exc:
                    logger.error("XGJ proxy error: %s", exc)
                    self._send_json({"ok": False, "error": str(exc)}, status=500)
                return

            if path in {"/api/xgj/order/receive", "/api/xgj/product/receive"}:
                content_len = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(content_len) if content_len > 0 else b""
                body_str = raw_body.decode("utf-8") if raw_body else ""
                cfg = _read_system_config()
                xgj = cfg.get("xianguanjia", {})
                app_key = str(xgj.get("app_key", ""))
                app_secret = str(xgj.get("app_secret", ""))
                if not app_key or not app_secret:
                    self._send_json({"code": 1, "msg": "Not configured"}, status=400)
                    return
                parsed_url = urlparse(self.path)
                qs = parse_qs(parsed_url.query)
                sign_val = qs.get("sign", [""])[0]
                try:
                    body_data = json.loads(body_str) if body_str else {}
                except Exception:
                    body_data = {}
                ts_val = str(body_data.get("timestamp") or (qs.get("timestamp", [""])[0]))
                now = int(time.time())
                try:
                    if abs(now - int(ts_val)) > 300:
                        self._send_json({"error": "Timestamp expired"}, status=400)
                        return
                except (ValueError, TypeError):
                    self._send_json({"error": "Invalid timestamp"}, status=400)
                    return
                from src.integrations.xianguanjia.signing import verify_open_platform_callback_signature

                if not verify_open_platform_callback_signature(
                    app_key=app_key, app_secret=app_secret, timestamp=ts_val, sign=sign_val, body=body_str
                ):
                    self._send_json({"code": 401, "msg": "Invalid signature"}, status=401)
                    return
                payload = self.mimic_ops.handle_order_callback(body_data)
                self._send_json(payload, status=200 if payload.get("success") else 400)
                return

            self._send_json(_error_payload("Not Found", code="NOT_FOUND"), status=404)
        except Exception as e:  # pragma: no cover - safety net
            self._send_json(_error_payload(str(e), code="INTERNAL_ERROR"), status=500)

    def log_message(self, format: str, *args: Any) -> None:
        return


def run_server(host: str = "127.0.0.1", port: int = 8091, db_path: str | None = None) -> None:
    import signal

    config = get_config()
    resolved_db = db_path or config.database.get("path", "data/agent.db")

    Path(resolved_db).parent.mkdir(parents=True, exist_ok=True)
    DashboardHandler.repo = DashboardRepository(resolved_db)
    DashboardHandler.module_console = ModuleConsole(project_root=Path(__file__).resolve().parents[1])
    DashboardHandler.mimic_ops = MimicOps(
        project_root=Path(__file__).resolve().parents[1],
        module_console=DashboardHandler.module_console,
    )

    # Cookie 静默自动刷新
    auto_refresh_enabled = os.environ.get("COOKIE_AUTO_REFRESH", "true").lower() in ("true", "1", "yes")
    refresher = None
    if auto_refresh_enabled:
        from src.core.cookie_grabber import CookieAutoRefresher

        interval = int(os.environ.get("COOKIE_REFRESH_INTERVAL", "30"))
        mimic_ops = DashboardHandler.mimic_ops

        def _on_refreshed(cookie: str) -> None:
            try:
                mimic_ops.update_cookie(cookie, auto_recover=True)
            except Exception as exc:
                logger.error(f"Cookie 自动刷新回调失败: {exc}")

        refresher = CookieAutoRefresher(interval_minutes=interval, on_refreshed=_on_refreshed)
        refresher.start()
        DashboardHandler._cookie_auto_refresher = refresher

    server = ThreadingHTTPServer((host, port), DashboardHandler)

    def _shutdown(signum, frame):
        logger.info("收到信号 %s，正在关闭...", signum)
        if refresher:
            refresher.stop()
        server.shutdown()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("Dashboard running: http://%s:%s", host, port)
    logger.info("Using database: %s", resolved_db)
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
