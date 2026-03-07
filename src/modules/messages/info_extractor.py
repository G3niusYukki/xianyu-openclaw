"""Rule-first message info extraction with optional LLM fallback."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.modules.quote.cost_table import COURIER_ALIASES, REGION_ALIASES
from src.modules.quote.geo_resolver import GeoResolver

_LLMExtractor = Callable[[str, str], dict[str, Any]]

_ROUTE_PATTERNS = (r"(?:从)?([\u4e00-\u9fa5]{2,12})\s*(?:到|发往|寄往|发|寄|->|→|-|—|~|～)\s*([\u4e00-\u9fa5]{2,12})",)

_DIMENSION_PATTERNS = (
    r"(\d+\.?\d*)\s*[xX×*]\s*(\d+\.?\d*)\s*[xX×*]\s*(\d+\.?\d*)",
    r"长[：:]?\s*(\d+\.?\d*)(?:cm|厘米|CM)?\s*宽[：:]?\s*(\d+\.?\d*)(?:cm|厘米|CM)?\s*高[：:]?\s*(\d+\.?\d*)(?:cm|厘米|CM)?",
)

_WEIGHT_KG_PATTERN = r"(\d+\.?\d*)\s*(?:kg|KG|公斤|千克)"
_WEIGHT_JIN_PATTERN = r"(\d+\.?\d*)\s*斤"


@dataclass
class ExtractedInfo:
    origin: str | None = None
    destination: str | None = None
    weight: float | None = None
    length: float | None = None
    width: float | None = None
    height: float | None = None
    courier: str | None = None
    source: str = "regex"

    def is_complete(self) -> bool:
        return bool(self.origin and self.destination and self.weight is not None)


class InfoExtractor:
    def __init__(
        self,
        llm_extractor: _LLMExtractor | None = None,
        couriers: list[str] | None = None,
        geo_resolver: GeoResolver | None = None,
    ) -> None:
        self.llm_extractor = llm_extractor
        self.geo_resolver = geo_resolver or GeoResolver()
        if couriers:
            self._couriers = sorted({c.strip() for c in couriers if str(c).strip()}, key=len, reverse=True)
        else:
            self._couriers = sorted({v for v in COURIER_ALIASES.values() if v}, key=len, reverse=True)

    def _normalize_location(self, value: str | None) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        compact = re.sub(r"\s+", "", text)
        if compact in REGION_ALIASES:
            return REGION_ALIASES[compact]
        normalized = self.geo_resolver.normalize(compact)
        if not normalized:
            return None
        province = self.geo_resolver.province_of(normalized)
        return normalized if normalized or province else None

    @staticmethod
    def _as_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def extract_fast(self, message: str) -> ExtractedInfo:
        info = ExtractedInfo()
        msg = str(message or "").strip()
        if not msg:
            return info

        for pattern in _ROUTE_PATTERNS:
            m = re.search(pattern, msg)
            if m:
                info.origin = self._normalize_location(m.group(1))
                info.destination = self._normalize_location(m.group(2))
                break

        kg = re.search(_WEIGHT_KG_PATTERN, msg)
        if kg:
            info.weight = self._as_float(kg.group(1))
        else:
            jin = re.search(_WEIGHT_JIN_PATTERN, msg)
            if jin:
                val = self._as_float(jin.group(1))
                info.weight = val * 0.5 if val is not None else None

        for pattern in _DIMENSION_PATTERNS:
            m = re.search(pattern, msg)
            if not m:
                continue
            length = self._as_float(m.group(1))
            width = self._as_float(m.group(2))
            height = self._as_float(m.group(3))
            if None not in (length, width, height) and all(0 < v <= 1000 for v in (length, width, height)):
                info.length, info.width, info.height = length, width, height
                break

        for courier in self._couriers:
            if courier in msg:
                info.courier = courier
                break

        return info

    def extract(self, message: str, context: str = "") -> ExtractedInfo:
        fast = self.extract_fast(message)
        if fast.is_complete() or self.llm_extractor is None:
            return fast

        llm_data = self.llm_extractor(message, context) or {}
        merged = ExtractedInfo(
            origin=self._normalize_location(llm_data.get("origin")) or fast.origin,
            destination=self._normalize_location(llm_data.get("destination")) or fast.destination,
            weight=self._as_float(llm_data.get("weight")) if llm_data.get("weight") is not None else fast.weight,
            length=self._as_float(llm_data.get("length")) if llm_data.get("length") is not None else fast.length,
            width=self._as_float(llm_data.get("width")) if llm_data.get("width") is not None else fast.width,
            height=self._as_float(llm_data.get("height")) if llm_data.get("height") is not None else fast.height,
            courier=str(llm_data.get("courier") or fast.courier or "").strip() or None,
            source="llm",
        )
        return merged
