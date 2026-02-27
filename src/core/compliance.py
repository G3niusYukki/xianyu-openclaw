"""
闲鱼合规护栏
Compliance Guard

提供最小可用的规则加载、内容拦截和频率控制。
"""

import asyncio
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


class ComplianceGuard:
    """合规规则管理与执行"""

    def __init__(self, rules_path: str = "config/rules.yaml"):
        self.rules_path = Path(rules_path)
        self._rules: dict[str, Any] = {}
        self._last_action_at: dict[str, float] = {}
        self._rules_mtime: float | None = None
        self._last_reload_check: float = 0.0
        self._lock = asyncio.Lock()
        self.reload()

    def reload(self) -> None:
        """重载规则配置（重启生效，也可手动调用）"""
        defaults = {
            "mode": "block",
            "reload": {"auto_reload": True, "check_interval_seconds": 10},
            "publish": {"min_interval_seconds": 30},
            "batch_operations": {"polish_cooldown_seconds": 300},
            "content": {"banned_keywords": [], "case_sensitive": False},
        }
        if self.rules_path.exists():
            try:
                with open(self.rules_path, encoding="utf-8") as f:
                    loaded = yaml.safe_load(f) or {}
                self._rules_mtime = self.rules_path.stat().st_mtime
            except Exception:
                loaded = {}
                self._rules_mtime = None
        else:
            loaded = {}
            self._rules_mtime = None

        self._rules = defaults
        for key, value in loaded.items():
            if isinstance(value, dict) and isinstance(self._rules.get(key), dict):
                self._rules[key].update(value)
            else:
                self._rules[key] = value

    @property
    def mode(self) -> str:
        mode = str(self._rules.get("mode", "block")).lower()
        return mode if mode in {"block", "warn"} else "block"

    def _auto_reload_if_needed(self) -> None:
        reload_cfg = self._rules.get("reload", {})
        auto_reload = bool(reload_cfg.get("auto_reload", True))
        check_interval = int(reload_cfg.get("check_interval_seconds", 10))
        now = time.time()
        if not auto_reload or now - self._last_reload_check < check_interval:
            return
        self._last_reload_check = now
        if not self.rules_path.exists():
            return
        current_mtime = self.rules_path.stat().st_mtime
        if self._rules_mtime is None or current_mtime > self._rules_mtime:
            self.reload()

    def _normalized(self, text: str) -> str:
        case_sensitive = bool(self._rules.get("content", {}).get("case_sensitive", False))
        return text if case_sensitive else text.lower()

    def _keywords(self) -> list[str]:
        keywords = self._rules.get("content", {}).get("banned_keywords", [])
        if not isinstance(keywords, list):
            return []
        return [str(k).strip() for k in keywords if str(k).strip()]

    def check_content(self, *texts: str) -> tuple[bool, list[str]]:
        """检查文本内容是否命中禁词"""
        self._auto_reload_if_needed()
        joined = " ".join([t for t in texts if t])
        normalized_text = self._normalized(joined)
        hits: list[str] = []
        for kw in self._keywords():
            if self._normalized(kw) in normalized_text:
                hits.append(kw)
        return len(hits) == 0, hits

    def evaluate_content(self, *texts: str) -> dict[str, Any]:
        """评估内容是否允许发布，支持阻断/告警双模式"""
        allowed, hits = self.check_content(*texts)
        if allowed:
            return {"allowed": True, "blocked": False, "warn": False, "hits": [], "message": ""}

        message = f"内容命中合规禁词: {', '.join(hits)}"
        if self.mode == "warn":
            return {"allowed": True, "blocked": False, "warn": True, "hits": hits, "message": message}
        return {"allowed": False, "blocked": True, "warn": False, "hits": hits, "message": message}

    async def _enforce_min_interval(self, action_key: str, min_interval_seconds: int) -> tuple[bool, int]:
        now = time.time()
        async with self._lock:
            last = self._last_action_at.get(action_key, 0.0)
            remaining = int(max(0, min_interval_seconds - (now - last)))
            if remaining > 0:
                return False, remaining
            self._last_action_at[action_key] = now
            return True, 0

    async def enforce_publish_rate(self, key: str = "publish:global") -> tuple[bool, str]:
        """发布频率控制"""
        self._auto_reload_if_needed()
        min_interval = int(self._rules.get("publish", {}).get("min_interval_seconds", 30))
        allowed, remaining = await self._enforce_min_interval(key, min_interval)
        if allowed:
            return True, ""
        return False, f"发布过于频繁，请在 {remaining} 秒后重试"

    async def enforce_batch_polish_rate(self, key: str = "batch_polish:global") -> tuple[bool, str]:
        """批量擦亮冷却控制"""
        self._auto_reload_if_needed()
        cooldown = int(self._rules.get("batch_operations", {}).get("polish_cooldown_seconds", 300))
        allowed, remaining = await self._enforce_min_interval(key, cooldown)
        if allowed:
            return True, ""
        return False, f"批量擦亮冷却中，请在 {remaining} 秒后重试"

    async def evaluate_publish_rate(self, key: str = "publish:global") -> dict[str, Any]:
        """评估发布频率限制，支持阻断/告警双模式"""
        allowed, message = await self.enforce_publish_rate(key)
        if allowed:
            return {"allowed": True, "blocked": False, "warn": False, "message": ""}
        if self.mode == "warn":
            return {"allowed": True, "blocked": False, "warn": True, "message": message}
        return {"allowed": False, "blocked": True, "warn": False, "message": message}

    async def evaluate_batch_polish_rate(self, key: str = "batch_polish:global") -> dict[str, Any]:
        """评估批量擦亮冷却，支持阻断/告警双模式"""
        allowed, message = await self.enforce_batch_polish_rate(key)
        if allowed:
            return {"allowed": True, "blocked": False, "warn": False, "message": ""}
        if self.mode == "warn":
            return {"allowed": True, "blocked": False, "warn": True, "message": message}
        return {"allowed": False, "blocked": True, "warn": False, "message": message}


@lru_cache(maxsize=1)
def get_compliance_guard() -> ComplianceGuard:
    """获取合规护栏单例"""
    return ComplianceGuard()
