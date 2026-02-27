"""
内容生成服务
Content Generation Service

提供AI驱动的商品标题和描述生成功能
"""

import hashlib
import json
import os
import time
from pathlib import Path
from threading import Lock
from typing import Any

from openai import APIError, APITimeoutError, AsyncOpenAI, OpenAI

from src.core.compliance import get_compliance_guard
from src.core.config import get_config
from src.core.logger import get_logger


class ContentService:
    """
    内容生成服务

    集成大语言模型，生成高质量的商品标题和描述文案
    """

    def __init__(self, config: dict | None = None):
        """
        初始化内容生成服务

        Args:
            config: 配置字典
        """
        self.config = config or get_config().ai
        self.logger = get_logger()
        self.compliance = get_compliance_guard()

        self.api_key = self.config.get("api_key") or os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        self.base_url = self.config.get("base_url") or os.getenv("OPENAI_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL")
        self.model = self.config.get("model", "deepseek-chat")
        self.temperature = self.config.get("temperature", 0.7)
        self.max_tokens = self.config.get("max_tokens", 1000)
        self.timeout = self.config.get("timeout", 30)
        self.fallback_enabled = self.config.get("fallback_enabled", True)
        self.fallback_model = self.config.get("fallback_model", "gpt-3.5-turbo")

        self.usage_mode = self._normalize_usage_mode(str(self.config.get("usage_mode", "minimal")))
        self.max_calls_per_run = self._safe_int(self.config.get("max_calls_per_run", 20), default=20, minimum=1)
        self.cache_enabled = bool(self.config.get("cache_enabled", True))
        self.cache_ttl_seconds = self._safe_int(
            self.config.get("cache_ttl_seconds", 86400),
            default=86400,
            minimum=60,
        )
        self.cache_max_entries = self._safe_int(
            self.config.get("cache_max_entries", 2000),
            default=2000,
            minimum=100,
        )
        self.cache_path = Path(str(self.config.get("cache_path", "data/ai_response_cache.json")))
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_lock = Lock()
        self._ai_calls_made = 0

        default_task_ai_enabled = {
            "title": False,
            "description": False,
            "optimize_title": True,
            "seo_keywords": True,
        }
        configured_task_flags = self.config.get("task_ai_enabled", {})
        if isinstance(configured_task_flags, dict):
            merged_task_flags = {
                **default_task_ai_enabled,
                **{str(k): bool(v) for k, v in configured_task_flags.items()},
            }
        else:
            merged_task_flags = default_task_ai_enabled
        self.task_ai_enabled = merged_task_flags

        self.client: OpenAI | None = None
        self.async_client: AsyncOpenAI | None = None

        self._init_client()

    def _init_client(self) -> None:
        """初始化AI客户端"""
        if self.api_key:
            try:
                self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
                self.async_client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
                self.logger.success("AI client initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize AI client: {e}")
                self.client = None
        else:
            self.logger.warning("AI API Key not found. Content generation will use templates.")

    @staticmethod
    def _normalize_usage_mode(value: str) -> str:
        mode = (value or "").strip().lower()
        return mode if mode in {"always", "auto", "minimal"} else "minimal"

    @staticmethod
    def _safe_int(value: Any, default: int, minimum: int) -> int:
        try:
            parsed = int(value)
            if parsed < minimum:
                return default
            return parsed
        except (TypeError, ValueError):
            return default

    def _is_task_ai_enabled(self, task: str) -> bool:
        return bool(self.task_ai_enabled.get(task, False))

    def _is_necessary_title_generation(self, product_name: str, features: list[str]) -> bool:
        if len(str(product_name).strip()) >= 12:
            return True
        if len(features) >= 3:
            return True
        return any(len(str(item).strip()) >= 8 for item in features)

    def _is_necessary_description_generation(
        self,
        condition: str,
        tags: list[str],
        extra_info: str | None,
    ) -> bool:
        condition_text = str(condition or "")
        risk_terms = ["瑕疵", "拆修", "进水", "磕碰", "暗病", "异常"]
        if any(term in condition_text for term in risk_terms):
            return True
        if len(tags) >= 4:
            return True
        if extra_info and len(str(extra_info).strip()) >= 8:
            return True
        return False

    def _should_use_ai(self, task: str, payload: dict[str, Any] | None = None) -> bool:
        if not self.client:
            return False

        if self._ai_calls_made >= self.max_calls_per_run:
            self.logger.warning(
                f"AI call budget exhausted in current run: {self._ai_calls_made}/{self.max_calls_per_run}. Using templates."
            )
            return False

        mode = self.usage_mode
        if mode == "always":
            return True

        if not self._is_task_ai_enabled(task):
            return False

        payload = payload or {}
        if task in {"optimize_title", "seo_keywords"}:
            return True

        if task == "title":
            return self._is_necessary_title_generation(
                str(payload.get("product_name", "")),
                payload.get("features", []) if isinstance(payload.get("features", []), list) else [],
            )

        if task == "description":
            return self._is_necessary_description_generation(
                condition=str(payload.get("condition", "")),
                tags=payload.get("tags", []) if isinstance(payload.get("tags", []), list) else [],
                extra_info=payload.get("extra_info"),
            )

        return mode == "auto"

    def _build_cache_key(self, task: str, prompt: str, max_tokens: int) -> str:
        raw = f"{self.model}|{task}|{max_tokens}|{prompt}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _read_cache_locked(self) -> dict[str, Any]:
        if not self.cache_path.exists():
            return {}
        try:
            content = self.cache_path.read_text(encoding="utf-8").strip()
            if not content:
                return {}
            data = json.loads(content)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write_cache_locked(self, data: dict[str, Any]) -> None:
        temp_path = self.cache_path.with_suffix(f"{self.cache_path.suffix}.tmp")
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.cache_path)

    def _cache_get(self, cache_key: str) -> str | None:
        if not self.cache_enabled:
            return None

        now = time.time()
        with self._cache_lock:
            data = self._read_cache_locked()
            entry = data.get(cache_key)
            if not isinstance(entry, dict):
                return None

            ts = float(entry.get("ts") or 0)
            if ts <= 0 or now - ts > self.cache_ttl_seconds:
                data.pop(cache_key, None)
                self._write_cache_locked(data)
                return None

            value = entry.get("value")
            if isinstance(value, str) and value.strip():
                return value
            return None

    def _cache_set(self, cache_key: str, value: str) -> None:
        if not self.cache_enabled or not value:
            return

        now = time.time()
        with self._cache_lock:
            data = self._read_cache_locked()
            data[cache_key] = {"value": value, "ts": now}

            if len(data) > self.cache_max_entries:
                sorted_items = sorted(
                    data.items(),
                    key=lambda item: float(item[1].get("ts") or 0) if isinstance(item[1], dict) else 0,
                    reverse=True,
                )
                data = dict(sorted_items[: self.cache_max_entries])

            self._write_cache_locked(data)

    def _call_ai_once(self, *, model: str, prompt: str, max_tokens: int) -> str | None:
        if not self.client:
            return None

        if self._ai_calls_made >= self.max_calls_per_run:
            return None

        self._ai_calls_made += 1
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=max_tokens,
                timeout=self.timeout,
            )
            return response.choices[0].message.content.strip()
        except APITimeoutError as e:
            self.logger.error(f"AI call timeout after {self.timeout}s: {e}")
            return None
        except APIError as e:
            self.logger.error(f"AI API error: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected AI call error: {e}")
            return None

    def _call_ai(
        self,
        prompt: str,
        max_tokens: int | None = None,
        *,
        task: str = "generic",
    ) -> str | None:
        """
        调用AI生成内容（带预算控制与缓存）

        Args:
            prompt: 提示词
            max_tokens: 最大token数
            task: 任务名，用于缓存与策略

        Returns:
            生成的内容，失败返回None
        """
        if not self.client:
            return None

        token_limit = int(max_tokens or self.max_tokens)
        cache_key = self._build_cache_key(task=task, prompt=prompt, max_tokens=token_limit)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        result = self._call_ai_once(model=self.model, prompt=prompt, max_tokens=token_limit)

        if not result and self.fallback_enabled and self.fallback_model and self.fallback_model != self.model:
            result = self._call_ai_once(model=self.fallback_model, prompt=prompt, max_tokens=token_limit)

        if result:
            self._cache_set(cache_key, result)

        return result

    def generate_title(self, product_name: str, features: list[str], category: str = "General") -> str:
        """
        生成闲鱼商品标题

        Args:
            product_name: 商品名称
            features: 商品特点列表
            category: 商品分类

        Returns:
            生成的标题
        """
        default_title = self._default_title(product_name, features)

        if not self._should_use_ai(
            "title",
            payload={"product_name": product_name, "features": features},
        ):
            return default_title

        keywords = self._get_category_keywords(category)
        prompt = (
            "你是闲鱼文案助手。生成1条15-25字中文标题，真实自然，避免夸张。"
            f"商品:{product_name};特点:{', '.join(features)};分类:{category};"
            f"关键词:{', '.join(keywords[:3])};只输出标题。"
        )
        result = self._call_ai(prompt, max_tokens=40, task="title")

        if result and 5 <= len(result) <= 30:
            return result

        return default_title

    def _default_title(self, product_name: str, features: list[str]) -> str:
        """生成默认标题"""
        feature_str = " ".join(features[:2]) if features else ""
        return f"【转卖】{product_name} {feature_str}".strip()[:25]

    def _get_category_keywords(self, category: str) -> list[str]:
        """获取分类热搜关键词"""
        keywords = {
            "数码手机": ["自用", "闲置", "正品", "国行", "原装", "95新", "便宜出"],
            "电脑办公": ["办公", "游戏", "高性能", "低价", "成色新"],
            "家电": ["家用", "闲置", "几乎全新", "保修期内"],
            "服饰鞋包": ["专柜", "正品", "全新", "闲置", "白菜价"],
            "美妆护肤": ["正品", "保真", "闲置", "临期特惠"],
            "家居": ["二手", "搬家急出", "几乎没用过"],
            "General": ["闲置", "便宜出", "自用", "转让"],
        }
        return keywords.get(category, keywords["General"])

    def _get_sample_keywords(self, category: str) -> list[str]:
        """兼容旧接口：返回分类关键词样本"""
        return self._get_category_keywords(category)

    def generate_description(
        self,
        product_name: str,
        condition: str,
        reason: str,
        tags: list[str],
        extra_info: str | None = None,
    ) -> str:
        """
        生成闲鱼商品描述文案

        Args:
            product_name: 商品名称
            condition: 成色描述
            reason: 转手原因
            tags: 标签列表
            extra_info: 额外信息

        Returns:
            生成的描述文案
        """
        default_desc = self._default_description(product_name, condition, reason, tags)

        if not self._should_use_ai(
            "description",
            payload={
                "condition": condition,
                "tags": tags,
                "extra_info": extra_info,
            },
        ):
            return default_desc

        prompt = (
            "写一段100-180字闲鱼商品描述，语气真实，包含成色、使用/瑕疵、交易说明。"
            f"商品:{product_name};成色:{condition};原因:{reason};"
            f"标签:{', '.join(tags)};补充:{extra_info or '无'}。"
            "输出正文，不要分点编号。"
        )
        result = self._call_ai(prompt, max_tokens=220, task="description")

        if result and len(result) >= 50:
            return result

        return default_desc

    def _default_description(self, product_name: str, condition: str, reason: str, tags: list[str]) -> str:
        """生成默认描述"""
        return f"""出闲置 {product_name}，成色{condition}。

{reason}，所以转让。

商品详情：
- 成色：{condition}
- 交易说明：走闲鱼，诚心要的私聊"""

    def generate_listing_content(self, product_info: dict[str, Any]) -> dict[str, Any]:
        """
        生成完整商品发布内容

        Args:
            product_info: 商品信息字典

        Returns:
            包含title和description的字典
        """
        product_name = product_info.get("name", "商品")
        features = product_info.get("features", [])
        category = product_info.get("category", "General")
        condition = product_info.get("condition", "95新")
        reason = product_info.get("reason", "用不上")
        tags = product_info.get("tags", [])
        extra_info = product_info.get("extra_info")

        title = self.generate_title(product_name, features, category)
        description = self.generate_description(product_name, condition, reason, tags, extra_info)
        review = self.review_before_publish(title, description)
        return {"title": title, "description": description, "compliance": review}

    def review_before_publish(self, title: str, description: str) -> dict[str, Any]:
        """
        发布前文本审查

        Returns:
            {"allowed": bool, "hits": list[str], "message": str}
        """
        decision = self.compliance.evaluate_content(title, description)
        return {
            "allowed": decision["allowed"],
            "blocked": decision["blocked"],
            "warn": decision["warn"],
            "hits": decision["hits"],
            "message": decision["message"],
            "mode": self.compliance.mode,
        }

    def optimize_title(self, current_title: str, category: str = "General") -> str:
        """
        优化现有标题

        Args:
            current_title: 当前标题
            category: 商品分类

        Returns:
            优化后的标题
        """
        if not self._should_use_ai("optimize_title", payload={"title": current_title, "category": category}):
            return current_title

        keywords = self._get_category_keywords(category)
        prompt = (
            "优化闲鱼标题，保持核心信息不变，15-25字，真实自然。"
            f"原标题:{current_title};分类:{category};关键词:{', '.join(keywords[:4])};"
            "只输出优化后标题。"
        )

        result = self._call_ai(prompt, max_tokens=32, task="optimize_title")

        if result and 5 <= len(result) <= 30:
            return result

        return current_title

    def generate_seo_keywords(self, product_name: str, category: str) -> list[str]:
        """
        生成SEO优化关键词

        Args:
            product_name: 商品名称
            category: 商品分类

        Returns:
            关键词列表
        """
        if not self._should_use_ai("seo_keywords", payload={"product_name": product_name, "category": category}):
            return self._get_category_keywords(category)

        prompt = (
            "给出5-8个闲鱼搜索关键词，按热度排序，用逗号分隔。"
            f"商品:{product_name};分类:{category}。"
        )

        result = self._call_ai(prompt, max_tokens=60, task="seo_keywords")

        if result:
            normalized = result.replace("，", ",")
            keywords = [k.strip() for k in normalized.split(",")]
            cleaned = [k for k in keywords if k]
            if cleaned:
                return cleaned[:8]

        return self._get_category_keywords(category)
