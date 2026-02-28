"""轻量后台可视化与模块控制服务。"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import yaml

from src.core.config import get_config
from src.modules.messages.reply_engine import ReplyStrategyEngine
from src.modules.quote.cost_table import CostTableRepository, normalize_courier_name
from src.modules.quote.engine import AutoQuoteEngine
from src.modules.quote.models import QuoteRequest
from src.modules.quote.setup import DEFAULT_MARKUP_RULES, QuoteSetupService

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

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

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

        if act not in {"start", "stop", "restart"}:
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
        else:
            args.extend(["--stop-timeout", "6"])

        return self._run_module_cli(action=act, target=tgt, extra_args=args, timeout_seconds=120)


DEFAULT_WEIGHT_TEMPLATE = (
    "您好，{origin} 到 {destination}，按实际重量 {weight}kg 预估，"
    "{courier} 报价约 ¥{price}（{price_breakdown}）。预计时效约 {eta_days}。"
)
DEFAULT_VOLUME_TEMPLATE = (
    "您好，{origin} 到 {destination}，按体积重规则（{volume_formula}）预估，"
    "{courier} 报价约 ¥{price}（{price_breakdown}）。预计时效约 {eta_days}。"
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
    _COOKIE_IMPORT_EXTS = {".txt", ".json", ".log", ".cookies"}
    _COOKIE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")

    def __init__(self, project_root: str | Path, module_console: ModuleConsole):
        self.project_root = Path(project_root).resolve()
        self.module_console = module_console
        self._service_started_at = _now_iso()
        self._service_state: dict[str, Any] = {
            "suspended": False,
            "stopped": False,
            "updated_at": _now_iso(),
        }

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

    def get_cookie(self) -> dict[str, Any]:
        cookie = self._get_env_value("XIANYU_COOKIE_1").strip()
        return {
            "success": bool(cookie),
            "cookie": cookie,
            "length": len(cookie),
        }

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
                    pairs.append((cols[5], cols[6]))
                    continue
                if len(cols) >= 2 and cls._COOKIE_NAME_RE.fullmatch(cols[0]):
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

    def update_cookie(self, cookie: str) -> dict[str, Any]:
        parsed = self.parse_cookie_text(str(cookie or ""))
        if not parsed.get("success"):
            return parsed
        cookie_text = str(parsed.get("cookie") or "").strip()
        if not cookie_text:
            return {"success": False, "error": "Cookie string cannot be empty"}
        self._set_env_value("XIANYU_COOKIE_1", cookie_text)
        return {
            "success": True,
            "message": "Cookie updated",
            "length": len(cookie_text),
            "cookie_items": int(parsed.get("cookie_items", 0) or 0),
            "detected_format": str(parsed.get("detected_format") or "header"),
            "missing_required": parsed.get("missing_required", []),
        }

    @classmethod
    def _is_cookie_import_file(cls, filename: str) -> bool:
        return Path(filename).suffix.lower() in cls._COOKIE_IMPORT_EXTS

    @classmethod
    def _score_cookie_candidate(cls, payload: dict[str, Any]) -> tuple[int, int, int]:
        missing = payload.get("missing_required")
        missing_count = len(missing) if isinstance(missing, list) else len(cls._COOKIE_REQUIRED_KEYS)
        required_hit = max(0, len(cls._COOKIE_REQUIRED_KEYS) - missing_count)
        cookie_items = int(payload.get("cookie_items", 0) or 0)
        length = int(payload.get("length", 0) or 0)
        return required_hit, cookie_items, length

    def import_cookie_plugin_files(self, files: list[tuple[str, bytes]]) -> dict[str, Any]:
        if not files:
            return {"success": False, "error": "No files uploaded"}

        candidates: list[dict[str, Any]] = []
        imported_files: list[str] = []
        skipped_files: list[str] = []
        details: list[str] = []

        def _collect_text_candidate(source_name: str, raw: bytes) -> None:
            text = self._decode_text_bytes(raw)
            parsed = self.parse_cookie_text(text)
            if not parsed.get("success"):
                skipped_files.append(source_name)
                details.append(f"{source_name} -> {parsed.get('error', 'parse failed')}")
                return

            candidates.append(
                {
                    "source_file": source_name,
                    "parsed": parsed,
                }
            )
            imported_files.append(source_name)

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
                            if not self._is_cookie_import_file(member_name):
                                skipped_files.append(f"{file_name}:{repaired_name}")
                                continue
                            try:
                                raw = zf.read(info)
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
        return {
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
        }

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
            with sqlite3.connect(db_path) as conn:
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

    def test_reply(self, payload: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        msg_cfg = get_config().get_section("messages", {})
        engine = ReplyStrategyEngine(
            default_reply=str(msg_cfg.get("default_reply", "您好，宝贝在的，感兴趣可以直接拍下。")),
            virtual_default_reply=str(
                msg_cfg.get("virtual_default_reply", "在的，这是虚拟商品，拍下后会尽快在聊天内给你处理结果。")
            ),
            reply_prefix=str(msg_cfg.get("reply_prefix", "")),
            keyword_replies=msg_cfg.get("keyword_replies", {}),
            intent_rules=msg_cfg.get("intent_rules", []),
            virtual_product_keywords=msg_cfg.get("virtual_product_keywords", []),
        )

        message = str(payload.get("message") or payload.get("user_message") or payload.get("user_msg") or "").strip()
        item_title = str(payload.get("item_title") or payload.get("item") or payload.get("item_desc") or "").strip()
        reply = engine.generate_reply(message, item_title=item_title)

        quote_part: dict[str, Any] | None = None
        origin = str(payload.get("origin") or "").strip()
        destination = str(payload.get("destination") or "").strip()
        weight_val = payload.get("weight")

        if origin and destination and weight_val not in {None, ""}:
            try:
                req = QuoteRequest(
                    origin=origin,
                    destination=destination,
                    weight=float(weight_val),
                    courier=str(payload.get("courier") or "auto"),
                    service_level=str(payload.get("service_level") or "standard"),
                    item_type=str(payload.get("item_type") or "general"),
                )
                q_engine = AutoQuoteEngine(config=get_config().get_section("quote", {}))
                quote_result = _run_async(q_engine.get_quote(req))
                quote_part = quote_result.to_dict()
                reply = f"{reply}\n{quote_result.compose_reply(validity_minutes=int(q_engine.validity_minutes))}"
            except Exception as exc:
                quote_part = {"error": str(exc)}

        message_l = message.lower()
        intent = "general"
        if quote_part is not None or any(k in message_l for k in ("多少钱", "报价", "价格", "运费", "几块")):
            intent = "quote"

        agent = "RuleBasedReplyStrategy+AutoQuoteEngine" if quote_part is not None else "RuleBasedReplyStrategy"
        response_time_ms = (time.perf_counter() - started) * 1000
        return {
            "success": True,
            "reply": reply,
            "quote": quote_part,
            "intent": intent,
            "agent": agent,
            "response_time": response_time_ms,
        }

    def service_status(self) -> dict[str, Any]:
        module_status = self.module_console.status(window_minutes=60, limit=20)
        cookie = self.get_cookie()
        route_stats = self.route_stats()
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
        return {
            "success": True,
            "service": dict(self._service_state),
            "module": module_status,
            "cookie_exists": bool(cookie.get("success", False)),
            "cookie_valid": bool(cookie.get("success", False)),
            "cookie_length": int(cookie.get("length", 0) or 0),
            "xianyu_connected": bool(presales_process.get("alive", False)),
            "token_available": bool(cookie.get("success", False)),
            "token_error": None,
            "cookie_update_required": False,
            "user_id": None,
            "last_token_refresh": None,
            "service_start_time": self._service_started_at,
            "route_stats": route_stat_payload,
            "route_stats_by_courier": route_stats_by_courier,
            "message_stats": message_stats,
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
      <strong>0基础快速上手（建议按顺序）</strong><br>
      1. 先点“配置管理”填写 Cookie。<br>
      2. 在“路线数据”导入报价表。<br>
      3. 在“测试调试”里先验证报价与回复。<br>
      4. 回到首页启动服务，确认状态为“运行中”。<br>
      5. 用“日志查看/实时日志”排查问题。<br>
      默认面板地址：<code>http://127.0.0.1:8091</code>
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

    <button class="refresh-btn" onclick="loadStatus()">刷新所有状态</button>

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
      if (v === "suspended") return "warning";
      return "error";
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
      const modules = (data.module && data.module.modules) || {};
      const aliveCount = Number(data.alive_count || 0);
      const totalModules = Number(data.total_modules || 0);

      document.getElementById("systemStatusContent").innerHTML = [
        row("系统运行", data.system_running ? "运行中" : "未运行", statusClassByBool(!!data.system_running)),
        row("服务状态", data.service_status || "unknown", statusClassByService(data.service_status)),
        row("模块在线", formatCount(aliveCount) + " / " + formatCount(totalModules), aliveCount > 0 ? "success" : "warning"),
        row("启动时间", data.service_start_time || "-", "info")
      ].join("");

      const presalesAlive = !!((modules.presales || {}).process || {}).alive;
      document.getElementById("xianyuStatusContent").innerHTML = [
        row("Cookie存在", data.cookie_exists ? "是" : "否", statusClassByBool(!!data.cookie_exists)),
        row("Cookie长度", formatCount(data.cookie_length || 0), "info"),
        row("售前模块连接", presalesAlive ? "已连接" : "未连接", statusClassByBool(presalesAlive)),
        row("Token可用", data.token_available ? "是" : "否", statusClassByBool(!!data.token_available))
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
    }

    function loadStatus() {
      fetch("/api/status")
      .then(r => r.json())
      .then(data => {
        if (data.error) throw new Error(data.error);
        updateServiceStatus(data.service_status || "running");
        renderStatusBlocks(data);
        renderCharts(data);
      })
      .catch(err => {
        document.getElementById("systemStatusContent").innerHTML = row("错误", err.message, "error");
      });
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
          <input type="file" id="cookiePluginFile" accept=".txt,.json,.log,.cookies,.zip" multiple>
          <div class="hint">推荐：直接上传插件导出的 cookies 文件，系统会自动识别并更新。</div>
        </div>
        <div class="form-group">
          <label for="cookie">Cookie字符串</label>
          <textarea id="cookie" placeholder="支持直接粘贴表格文本 / Cookie请求头 / cookies.txt / JSON"></textarea>
        </div>
        <div class="button-group">
          <button class="btn-primary" title="上传插件导出文件并自动更新到系统 Cookie" onclick="importCookiePlugin()">上传并一键更新</button>
          <button class="btn-primary" title="保存当前输入的 Cookie 到系统配置" onclick="saveCookie()">粘贴并更新</button>
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
            <p><strong>插件安装：</strong>下载内置插件包 → 浏览器扩展页加载 <code>Get-cookies.txt-LOCALLY/src</code>。</p>
            <div class="button-group" style="margin-top: 8px;">
              <button class="btn-secondary" onclick="window.location.href='/api/download-cookie-plugin'">下载内置插件包</button>
            </div>
            <p><a href="https://github.com/kairi003/Get-cookies.txt-LOCALLY" target="_blank" rel="noopener">插件项目地址（GitHub）</a></p>
            <div class="form-group" style="margin-top: 10px;">
              <label for="cookieFile">手动导入 Cookie 文件</label>
              <input type="file" id="cookieFile" accept=".txt,.json,.log,.cookies">
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
        if (!data.success) throw new Error(data.error || "导入失败");

        document.getElementById("cookie").value = data.cookie || "";

        let text = "插件导入成功\\n";
        text += "来源文件: " + (data.source_file || "-") + "\\n";
        text += "识别格式: " + (data.detected_format || "-") + "\\n";
        text += "Cookie 项数: " + (data.cookie_items || 0) + "\\n";
        text += "字符长度: " + (data.length || 0) + "\\n";
        if ((data.missing_required || []).length > 0) {
          text += "关键字段缺失: " + data.missing_required.join(", ") + "\\n";
        } else {
          text += "关键字段检查: 通过\\n";
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
        if ((data.missing_required || []).length > 0) {
          msg += "\\n缺少关键字段: " + data.missing_required.join(", ");
        }
        showMessage(msg, "success");
        await initCookiePreview();
      } catch (err) {
        showMessage("更新Cookie失败: " + err.message, "error");
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
            raw_data = self.rfile.read(content_length)
        except Exception:
            return []

        from email import policy
        from email.parser import BytesParser

        msg = BytesParser(policy=policy.default).parsebytes(raw_data)
        items = []
        for part in msg.walk():
            if part.get_content_disposition() == "attachment":
                filename = part.get_filename()
                if filename:
                    payload = part.get_payload(decode=True)
                    items.append((filename, payload) if payload else (filename, b""))

        files: list[tuple[str, bytes]] = []
        for item in items:
            if not getattr(item, "filename", None):
                continue
            content = item.file.read() if item.file else b""
            if isinstance(content, str):
                content = content.encode("utf-8", errors="ignore")
            if not isinstance(content, (bytes, bytearray)):
                continue
            files.append((str(item.filename), bytes(content)))
        return files

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        try:
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

            if path == "/api/summary":
                self._send_json(self.repo.get_summary())
                return

            if path == "/api/trend":
                metric = (query.get("metric") or ["views"])[0]
                days = _safe_int((query.get("days") or ["30"])[0], default=30, min_value=1, max_value=120)
                self._send_json(self.repo.get_trend(metric=metric, days=days))
                return

            if path == "/api/recent-operations":
                limit = _safe_int((query.get("limit") or ["20"])[0], default=20, min_value=1, max_value=200)
                self._send_json(self.repo.get_recent_operations(limit=limit))
                return

            if path == "/api/top-products":
                limit = _safe_int((query.get("limit") or ["12"])[0], default=12, min_value=1, max_value=200)
                self._send_json(self.repo.get_top_products(limit=limit))
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
                    self._send_json({"success": False, "error": str(exc)}, status=404)
                return

            if path == "/api/get-template":
                use_default = (query.get("default") or ["false"])[0].lower() in {"1", "true", "yes"}
                self._send_json(self.mimic_ops.get_template(default=use_default))
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
                            self.wfile.write(f"data: {event}\n\n".encode("utf-8"))
                            self.wfile.flush()
                            last = text
                        time.sleep(1)
                except (BrokenPipeError, ConnectionResetError):
                    return
                return

            self._send_json({"error": "Not Found"}, status=404)
        except sqlite3.Error as e:
            self._send_json({"error": f"Database error: {e}"}, status=500)
        except Exception as e:  # pragma: no cover - safety net
            self._send_json({"error": str(e)}, status=500)

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

            if path == "/api/update-cookie":
                body = self._read_json_body()
                cookie = str(body.get("cookie") or "").strip()
                payload = self.mimic_ops.update_cookie(cookie)
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
                    payload = self.mimic_ops.import_cookie_plugin_files(files)
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

            self._send_json({"error": "Not Found"}, status=404)
        except Exception as e:  # pragma: no cover - safety net
            self._send_json({"error": str(e)}, status=500)

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
