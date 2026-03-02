"""省市解析与混配匹配支持。"""

from __future__ import annotations

import json
import re
from pathlib import Path

_SUFFIXES = ("特别行政区", "自治区", "自治州", "地区", "省", "市", "盟", "区", "县")


class GeoResolver:
    """读取城市-省份映射并提供标准化/混配能力。"""

    def __init__(self, mapping_file: str | Path | None = None):
        default_path = Path(__file__).resolve().parents[3] / "data" / "geo" / "city_province.json"
        self.mapping_file = Path(mapping_file) if mapping_file else default_path
        self._city_to_province: dict[str, str] = {}
        self._province_aliases: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.mapping_file.exists():
            self._city_to_province = {}
            self._province_aliases = {}
            return

        payload = json.loads(self.mapping_file.read_text(encoding="utf-8"))
        city_map = payload.get("city_to_province", {}) if isinstance(payload, dict) else {}

        normalized_city_map: dict[str, str] = {}
        province_aliases: dict[str, str] = {}
        for city, province in city_map.items():
            city_name = self.normalize(city)
            province_name = self.normalize(province)
            if not city_name or not province_name:
                continue
            normalized_city_map[city_name] = province_name
            province_aliases[province_name] = province_name
            full = self.ensure_full_province_suffix(province_name)
            if full:
                province_aliases[self.normalize(full)] = province_name

        self._city_to_province = normalized_city_map
        self._province_aliases = province_aliases

    @staticmethod
    def normalize(name: str | None) -> str:
        text = re.sub(r"\s+", "", str(name or "").strip())
        if not text:
            return ""
        for suffix in _SUFFIXES:
            if text.endswith(suffix):
                return text[: -len(suffix)]
        return text

    @staticmethod
    def ensure_full_province_suffix(name: str | None) -> str:
        text = str(name or "").strip()
        if not text:
            return ""
        for suffix in ("省", "市", "自治区", "特别行政区"):
            if text.endswith(suffix):
                return text
        return f"{text}省"

    def province_of(self, name: str | None) -> str:
        normalized = self.normalize(name)
        if not normalized:
            return ""
        if normalized in self._province_aliases:
            return self._province_aliases[normalized]
        return self._city_to_province.get(normalized, "")

    def expand_city_province_candidates(self, name: str | None) -> list[str]:
        normalized = self.normalize(name)
        if not normalized:
            return []

        candidates = [normalized]
        province = self.province_of(normalized)
        if province and province not in candidates:
            candidates.append(province)
        return candidates

    def cross_candidates(self, origin: str, destination: str) -> list[tuple[str, str]]:
        origin_candidates = self.expand_city_province_candidates(origin)
        destination_candidates = self.expand_city_province_candidates(destination)
        pairs: list[tuple[str, str]] = []
        for o in origin_candidates:
            for d in destination_candidates:
                pair = (o, d)
                if pair not in pairs:
                    pairs.append(pair)
        return pairs
