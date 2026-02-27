"""
自动报价快速配置
Quote setup utility for low-threshold onboarding
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

DEFAULT_MARKUP_RULES: dict[str, dict[str, float]] = {
    "default": {
        "normal_first_add": 0.50,
        "member_first_add": 0.25,
        "normal_extra_add": 0.50,
        "member_extra_add": 0.30,
    },
    "圆通": {
        "normal_first_add": 0.56,
        "member_first_add": 0.30,
        "normal_extra_add": 0.50,
        "member_extra_add": 0.30,
    },
    "韵达": {
        "normal_first_add": 0.87,
        "member_first_add": 0.57,
        "normal_extra_add": 0.40,
        "member_extra_add": 0.30,
    },
    "中通": {
        "normal_first_add": 0.60,
        "member_first_add": 0.30,
        "normal_extra_add": 0.60,
        "member_extra_add": 0.40,
    },
    "申通": {
        "normal_first_add": 0.50,
        "member_first_add": 0.25,
        "normal_extra_add": 0.50,
        "member_extra_add": 0.30,
    },
    "菜鸟裹裹": {
        "normal_first_add": 0.50,
        "member_first_add": 0.25,
        "normal_extra_add": 0.50,
        "member_extra_add": 0.30,
    },
    "极兔": {
        "normal_first_add": 0.50,
        "member_first_add": 0.25,
        "normal_extra_add": 0.50,
        "member_extra_add": 0.30,
    },
    "德邦": {
        "normal_first_add": 0.70,
        "member_first_add": 0.40,
        "normal_extra_add": 0.50,
        "member_extra_add": 0.30,
    },
    "顺丰": {
        "normal_first_add": 0.20,
        "member_first_add": 0.20,
        "normal_extra_add": 0.30,
        "member_extra_add": 0.30,
    },
    "京东": {
        "normal_first_add": 0.70,
        "member_first_add": 0.30,
        "normal_extra_add": 0.50,
        "member_extra_add": 0.30,
    },
    "邮政": {
        "normal_first_add": 0.50,
        "member_first_add": 0.25,
        "normal_extra_add": 0.50,
        "member_extra_add": 0.40,
    },
}

SUPPORTED_MODES = {
    "rule_only",
    "remote_then_rule",
    "cost_table_plus_markup",
    "api_cost_plus_markup",
}


class QuoteSetupService:
    """对 config/config.yaml 进行一键报价配置。"""

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = Path(config_path)

    def apply(
        self,
        *,
        mode: str,
        origin_city: str | None,
        pricing_profile: str,
        cost_table_dir: str,
        cost_table_patterns: list[str] | None = None,
        api_cost_url: str | None = None,
        cost_api_key_env: str = "QUOTE_COST_API_KEY",
        api_fallback_to_table_parallel: bool = True,
        api_prefer_max_wait_seconds: float = 1.2,
    ) -> dict[str, Any]:
        mode_norm = str(mode or "").strip()
        if mode_norm not in SUPPORTED_MODES:
            raise ValueError(f"Unsupported quote mode: {mode_norm}")

        pricing_profile_norm = str(pricing_profile or "normal").strip().lower()
        if pricing_profile_norm not in {"normal", "member"}:
            raise ValueError("pricing_profile must be one of: normal, member")

        patterns = cost_table_patterns or ["*.xlsx", "*.csv"]
        normalized_patterns = [str(item).strip() for item in patterns if str(item).strip()]
        if not normalized_patterns:
            normalized_patterns = ["*.xlsx", "*.csv"]

        data, existed = self._load_yaml()
        quote_cfg = data.get("quote")
        if not isinstance(quote_cfg, dict):
            quote_cfg = {}
            data["quote"] = quote_cfg

        quote_cfg["enabled"] = True
        quote_cfg["mode"] = mode_norm
        if origin_city:
            quote_cfg["origin_city"] = str(origin_city).strip()
        quote_cfg["pricing_profile"] = pricing_profile_norm
        quote_cfg["cost_table_dir"] = str(cost_table_dir).strip() or "data/quote_costs"
        quote_cfg["cost_table_patterns"] = normalized_patterns
        quote_cfg["api_fallback_to_table_parallel"] = bool(api_fallback_to_table_parallel)
        quote_cfg["api_prefer_max_wait_seconds"] = float(api_prefer_max_wait_seconds)

        markup_rules = quote_cfg.get("markup_rules")
        if not isinstance(markup_rules, dict) or not markup_rules:
            quote_cfg["markup_rules"] = DEFAULT_MARKUP_RULES

        if mode_norm == "api_cost_plus_markup":
            if api_cost_url:
                quote_cfg["cost_api_url"] = str(api_cost_url).strip()
            if cost_api_key_env:
                quote_cfg["cost_api_key"] = f"${{{cost_api_key_env}}}"

        backup_path = self._backup_existing_file() if existed else None
        self._write_yaml(data)

        table_stats = self._scan_cost_table_dir(
            quote_cfg.get("cost_table_dir", "data/quote_costs"),
            quote_cfg.get("cost_table_patterns", ["*.xlsx", "*.csv"]),
        )

        return {
            "success": True,
            "config_path": str(self.config_path),
            "backup_path": str(backup_path) if backup_path else "",
            "mode": mode_norm,
            "quote": {
                "origin_city": quote_cfg.get("origin_city", ""),
                "pricing_profile": quote_cfg.get("pricing_profile", "normal"),
                "cost_table_dir": quote_cfg.get("cost_table_dir", "data/quote_costs"),
                "cost_table_patterns": quote_cfg.get("cost_table_patterns", ["*.xlsx", "*.csv"]),
                "cost_api_url": quote_cfg.get("cost_api_url", ""),
                "api_fallback_to_table_parallel": quote_cfg.get("api_fallback_to_table_parallel", True),
                "api_prefer_max_wait_seconds": quote_cfg.get("api_prefer_max_wait_seconds", 1.2),
            },
            "cost_table": table_stats,
        }

    def _load_yaml(self) -> tuple[dict[str, Any], bool]:
        if self.config_path.exists():
            raw = self.config_path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw) or {}
            if not isinstance(data, dict):
                data = {}
            return data, True

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        example_path = self.config_path.parent / "config.example.yaml"
        if example_path.exists():
            raw = example_path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw) or {}
            if not isinstance(data, dict):
                data = {}
            return data, False
        return {}, False

    def _backup_existing_file(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = self.config_path.with_name(f"{self.config_path.name}.bak.{stamp}")
        backup_path.write_text(self.config_path.read_text(encoding="utf-8"), encoding="utf-8")
        return backup_path

    def _write_yaml(self, data: dict[str, Any]) -> None:
        payload = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        self.config_path.write_text(payload, encoding="utf-8")

    @staticmethod
    def _scan_cost_table_dir(cost_table_dir: str, patterns: list[str] | tuple[str, ...] | None) -> dict[str, Any]:
        base = Path(cost_table_dir)
        if not base.exists():
            return {"exists": False, "file_count": 0, "files": []}
        if base.is_file():
            return {"exists": True, "file_count": 1, "files": [base.name]}

        include_patterns = patterns if isinstance(patterns, (list, tuple)) else ["*.xlsx", "*.csv"]
        files: list[Path] = []
        for pattern in include_patterns:
            text = str(pattern).strip()
            if not text:
                continue
            files.extend(base.glob(text))
        unique_files = sorted({item for item in files if item.is_file()})
        return {"exists": True, "file_count": len(unique_files), "files": [item.name for item in unique_files[:30]]}
