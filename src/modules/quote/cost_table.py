"""
成本价表加载与查询
Cost Table Loader for Quote Service
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

XML_NS_MAIN = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
XML_NS_OFFICE_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
XML_NS_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"

COURIER_ALIASES = {
    "圆通": "圆通",
    "圆通快递": "圆通",
    "韵达": "韵达",
    "韵达快递": "韵达",
    "中通": "中通",
    "中通快递": "中通",
    "申通": "申通",
    "申通快递": "申通",
    "菜鸟": "菜鸟裹裹",
    "菜鸟裹裹": "菜鸟裹裹",
    "极兔": "极兔",
    "极兔速递": "极兔",
    "德邦": "德邦",
    "德邦快递": "德邦",
    "顺丰": "顺丰",
    "顺丰速运": "顺丰",
    "京东": "京东",
    "京东物流": "京东",
    "邮政": "邮政",
    "中国邮政": "邮政",
    "ems": "邮政",
}

REGION_ALIASES = {
    "北京": "北京",
    "北京市": "北京",
    "上海": "上海",
    "上海市": "上海",
    "天津": "天津",
    "天津市": "天津",
    "重庆": "重庆",
    "重庆市": "重庆",
    "河北": "河北",
    "河北省": "河北",
    "山西": "山西",
    "山西省": "山西",
    "辽宁": "辽宁",
    "辽宁省": "辽宁",
    "吉林": "吉林",
    "吉林省": "吉林",
    "黑龙江": "黑龙江",
    "黑龙江省": "黑龙江",
    "江苏": "江苏",
    "江苏省": "江苏",
    "浙江": "浙江",
    "浙江省": "浙江",
    "安徽": "安徽",
    "安徽省": "安徽",
    "福建": "福建",
    "福建省": "福建",
    "江西": "江西",
    "江西省": "江西",
    "山东": "山东",
    "山东省": "山东",
    "河南": "河南",
    "河南省": "河南",
    "湖北": "湖北",
    "湖北省": "湖北",
    "湖南": "湖南",
    "湖南省": "湖南",
    "广东": "广东",
    "广东省": "广东",
    "海南": "海南",
    "海南省": "海南",
    "四川": "四川",
    "四川省": "四川",
    "贵州": "贵州",
    "贵州省": "贵州",
    "云南": "云南",
    "云南省": "云南",
    "陕西": "陕西",
    "陕西省": "陕西",
    "甘肃": "甘肃",
    "甘肃省": "甘肃",
    "青海": "青海",
    "青海省": "青海",
    "台湾": "台湾",
    "台湾省": "台湾",
    "内蒙古": "内蒙古",
    "内蒙古自治区": "内蒙古",
    "广西": "广西",
    "广西壮族自治区": "广西",
    "西藏": "西藏",
    "西藏自治区": "西藏",
    "宁夏": "宁夏",
    "宁夏回族自治区": "宁夏",
    "新疆": "新疆",
    "新疆维吾尔自治区": "新疆",
    "香港": "香港",
    "香港特别行政区": "香港",
    "澳门": "澳门",
    "澳门特别行政区": "澳门",
}

CITY_TO_REGION = {
    "北京": "北京",
    "上海": "上海",
    "天津": "天津",
    "重庆": "重庆",
    "石家庄": "河北",
    "太原": "山西",
    "沈阳": "辽宁",
    "长春": "吉林",
    "哈尔滨": "黑龙江",
    "南京": "江苏",
    "杭州": "浙江",
    "合肥": "安徽",
    "福州": "福建",
    "南昌": "江西",
    "济南": "山东",
    "郑州": "河南",
    "武汉": "湖北",
    "长沙": "湖南",
    "广州": "广东",
    "深圳": "广东",
    "海口": "海南",
    "成都": "四川",
    "贵阳": "贵州",
    "昆明": "云南",
    "西安": "陕西",
    "兰州": "甘肃",
    "西宁": "青海",
    "呼和浩特": "内蒙古",
    "南宁": "广西",
    "拉萨": "西藏",
    "银川": "宁夏",
    "乌鲁木齐": "新疆",
}

PROVINCE_SET = set(REGION_ALIASES.values())


def normalize_courier_name(name: str | None) -> str:
    raw = str(name or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    if lowered in COURIER_ALIASES:
        return COURIER_ALIASES[lowered]
    if raw in COURIER_ALIASES:
        return COURIER_ALIASES[raw]
    compact = raw.replace("速递", "").replace("物流", "").replace("快递", "").strip()
    if compact in COURIER_ALIASES:
        return COURIER_ALIASES[compact]
    return compact or raw


def normalize_location_name(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    text = re.sub(r"\s+", "", text)
    if text in REGION_ALIASES:
        return REGION_ALIASES[text]

    city = text
    for suffix in ("省", "市", "盟", "地区", "自治州", "自治区", "特别行政区", "区", "县"):
        if city.endswith(suffix):
            city = city[: -len(suffix)]
            break

    if city in REGION_ALIASES:
        return REGION_ALIASES[city]

    if city in CITY_TO_REGION:
        return city

    return city


def region_of_location(value: str | None) -> str:
    name = normalize_location_name(value)
    if not name:
        return ""
    if name in PROVINCE_SET:
        return name
    return CITY_TO_REGION.get(name, "")


@dataclass(slots=True)
class CostRecord:
    courier: str
    origin: str
    destination: str
    first_cost: float
    extra_cost: float
    throw_ratio: float | None = None
    source_file: str = ""
    source_sheet: str = ""


class CostTableRepository:
    """加载并查询成本价表（xlsx/csv）。"""

    _HEADER_ALIASES = {
        "courier": {"快递公司", "物流公司", "承运商"},
        "origin": {"始发地", "寄件地", "发件地", "发货地", "始发城市"},
        "destination": {"目的地", "收件地", "收件地址", "收件城市", "到达地"},
        "first_cost": {"首重", "首重1kg", "首重1kg", "首重价", "首重价格", "首重1kg价"},
        "extra_cost": {"续重", "续重1kg", "续重1kg", "续重价", "续重价格", "续重1kg价"},
        "throw_ratio": {"抛比", "抛重比", "材积比", "体积系数"},
    }

    def __init__(self, table_dir: str | Path, include_patterns: list[str] | None = None):
        self.table_dir = Path(table_dir)
        self.include_patterns = tuple(include_patterns or ["*.xlsx", "*.csv"])

        self._records: list[CostRecord] = []
        self._signature: tuple[tuple[str, int, int], ...] = ()

        self._index_route: dict[tuple[str, str], list[CostRecord]] = {}
        self._index_courier_route: dict[tuple[str, str, str], list[CostRecord]] = {}
        self._index_destination: dict[str, list[CostRecord]] = {}
        self._index_courier_destination: dict[tuple[str, str], list[CostRecord]] = {}

    def find_candidates(
        self,
        origin: str,
        destination: str,
        courier: str | None = None,
        limit: int = 24,
    ) -> list[CostRecord]:
        self._reload_if_needed()
        if not self._records:
            return []

        origin_norm = normalize_location_name(origin)
        destination_norm = normalize_location_name(destination)
        if not origin_norm or not destination_norm:
            return []

        courier_norm = normalize_courier_name(courier) if courier else ""

        if courier_norm:
            exact = self._index_courier_route.get((courier_norm, origin_norm, destination_norm), [])
            if exact:
                return self._sort_candidates(exact)[:limit]

            dest_pool = self._index_courier_destination.get((courier_norm, destination_norm), [])
            scored = self._rank_by_origin_similarity(dest_pool, origin_norm)
            return scored[:limit]

        exact = self._index_route.get((origin_norm, destination_norm), [])
        if exact:
            return self._sort_candidates(exact)[:limit]

        dest_pool = self._index_destination.get(destination_norm, [])
        scored = self._rank_by_origin_similarity(dest_pool, origin_norm)
        return scored[:limit]

    def _reload_if_needed(self) -> None:
        files = self._collect_files()
        signature = self._build_signature(files)
        if signature == self._signature:
            return

        records: list[CostRecord] = []
        for path in files:
            suffix = path.suffix.lower()
            if suffix == ".csv":
                records.extend(self._load_csv(path))
            elif suffix == ".xlsx":
                records.extend(self._load_xlsx(path))

        self._records = records
        self._signature = signature
        self._rebuild_indexes(records)

    def _collect_files(self) -> list[Path]:
        if self.table_dir.is_file():
            return [self.table_dir]
        if not self.table_dir.exists():
            return []

        files: list[Path] = []
        for pattern in self.include_patterns:
            files.extend(self.table_dir.glob(pattern))
        return sorted(set(p for p in files if p.is_file()))

    @staticmethod
    def _build_signature(files: list[Path]) -> tuple[tuple[str, int, int], ...]:
        signature: list[tuple[str, int, int]] = []
        for path in files:
            stat = path.stat()
            signature.append((str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size)))
        return tuple(signature)

    def _rebuild_indexes(self, records: list[CostRecord]) -> None:
        self._index_route = {}
        self._index_courier_route = {}
        self._index_destination = {}
        self._index_courier_destination = {}

        for record in records:
            courier = normalize_courier_name(record.courier)
            origin = normalize_location_name(record.origin)
            destination = normalize_location_name(record.destination)
            if not courier or not origin or not destination:
                continue

            self._index_route.setdefault((origin, destination), []).append(record)
            self._index_courier_route.setdefault((courier, origin, destination), []).append(record)
            self._index_destination.setdefault(destination, []).append(record)
            self._index_courier_destination.setdefault((courier, destination), []).append(record)

    @staticmethod
    def _sort_candidates(records: list[CostRecord]) -> list[CostRecord]:
        return sorted(records, key=lambda r: (r.first_cost + r.extra_cost, r.first_cost, r.extra_cost, r.courier))

    def _rank_by_origin_similarity(self, records: list[CostRecord], origin_norm: str) -> list[CostRecord]:
        if not records:
            return []

        ranked: list[tuple[int, CostRecord]] = []
        for record in records:
            row_origin = normalize_location_name(record.origin)
            score = self._origin_similarity(origin_norm, row_origin)
            if score <= 0:
                continue
            ranked.append((score, record))

        if not ranked:
            return []

        ranked.sort(key=lambda item: (-item[0], item[1].first_cost + item[1].extra_cost, item[1].first_cost))
        return [record for _, record in ranked]

    @staticmethod
    def _origin_similarity(request_origin: str, row_origin: str) -> int:
        if not request_origin or not row_origin:
            return 0
        if request_origin == row_origin:
            return 4
        if request_origin in row_origin or row_origin in request_origin:
            return 3

        request_region = region_of_location(request_origin)
        row_region = region_of_location(row_origin)
        if request_region and row_region and request_region == row_region:
            if request_origin in PROVINCE_SET or row_origin in PROVINCE_SET:
                return 2

        if len(request_origin) >= 2 and len(row_origin) >= 2 and request_origin[:2] == row_origin[:2]:
            return 1
        return 0

    def _load_csv(self, path: Path) -> list[CostRecord]:
        text = self._read_text_file(path)
        if not text:
            return []
        reader = csv.reader(io.StringIO(text))
        rows = [row for row in reader if any(str(col).strip() for col in row)]
        return self._rows_to_records(rows, source_file=path.name, source_sheet="csv")

    @staticmethod
    def _read_text_file(path: Path) -> str:
        data = path.read_bytes()
        for encoding in ("utf-8-sig", "gb18030", "gbk"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return ""

    def _load_xlsx(self, path: Path) -> list[CostRecord]:
        rows_by_sheet = self._iter_xlsx_rows(path)
        records: list[CostRecord] = []
        for sheet_name, rows in rows_by_sheet.items():
            records.extend(self._rows_to_records(rows, source_file=path.name, source_sheet=sheet_name))
        return records

    def _rows_to_records(self, rows: list[list[str]], source_file: str, source_sheet: str) -> list[CostRecord]:
        if not rows:
            return []

        header_row_index = -1
        header_map: dict[str, int] = {}
        for idx, row in enumerate(rows):
            header_map = self._resolve_header_map(row)
            if {"courier", "origin", "destination", "first_cost", "extra_cost"}.issubset(set(header_map.keys())):
                header_row_index = idx
                break

        if header_row_index < 0:
            return []

        records: list[CostRecord] = []
        for row in rows[header_row_index + 1 :]:
            courier = self._cell_text(row, header_map.get("courier"))
            origin = self._cell_text(row, header_map.get("origin"))
            destination = self._cell_text(row, header_map.get("destination"))
            first_cost = self._cell_float(row, header_map.get("first_cost"))
            extra_cost = self._cell_float(row, header_map.get("extra_cost"))
            throw_ratio = self._cell_float(row, header_map.get("throw_ratio"))

            if not courier or not origin or not destination:
                continue
            if first_cost is None or extra_cost is None:
                continue

            records.append(
                CostRecord(
                    courier=normalize_courier_name(courier),
                    origin=origin.strip(),
                    destination=destination.strip(),
                    first_cost=first_cost,
                    extra_cost=extra_cost,
                    throw_ratio=throw_ratio,
                    source_file=source_file,
                    source_sheet=source_sheet,
                )
            )
        return records

    @classmethod
    def _resolve_header_map(cls, headers: list[Any]) -> dict[str, int]:
        mapped: dict[str, int] = {}
        cleaned_aliases: dict[str, set[str]] = {}
        for key, aliases in cls._HEADER_ALIASES.items():
            cleaned_aliases[key] = {cls._clean_header(alias) for alias in aliases}

        for index, raw in enumerate(headers):
            cell = cls._clean_header(raw)
            if not cell:
                continue
            for key, aliases in cleaned_aliases.items():
                if key in mapped:
                    continue
                if cell in aliases:
                    mapped[key] = index
                    continue
                if key in {"first_cost", "extra_cost"}:
                    # 兼容 "首重1KG"/"续重1KG" 等变体
                    if key == "first_cost" and "首重" in cell:
                        mapped[key] = index
                    if key == "extra_cost" and "续重" in cell:
                        mapped[key] = index
        return mapped

    @staticmethod
    def _clean_header(value: Any) -> str:
        text = str(value or "").strip().lower()
        return re.sub(r"\s+", "", text)

    @staticmethod
    def _cell_text(row: list[Any], index: int | None) -> str:
        if index is None or index < 0 or index >= len(row):
            return ""
        return str(row[index] or "").strip()

    @staticmethod
    def _cell_float(row: list[Any], index: int | None) -> float | None:
        if index is None or index < 0 or index >= len(row):
            return None
        return CostTableRepository._to_float(row[index])

    @staticmethod
    def _to_float(value: Any) -> float | None:
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

    def _iter_xlsx_rows(self, path: Path) -> dict[str, list[list[str]]]:
        result: dict[str, list[list[str]]] = {}
        with zipfile.ZipFile(path) as archive:
            shared_strings = self._read_shared_strings(archive)
            sheet_paths = self._read_sheet_paths(archive)

            for sheet_name, sheet_path in sheet_paths:
                if sheet_path not in archive.namelist():
                    continue
                sheet_rows = self._read_sheet_rows(archive, sheet_path, shared_strings)
                if sheet_rows:
                    result[sheet_name] = sheet_rows
        return result

    def _read_sheet_paths(self, archive: zipfile.ZipFile) -> list[tuple[str, str]]:
        workbook_xml = "xl/workbook.xml"
        rel_xml = "xl/_rels/workbook.xml.rels"
        if workbook_xml not in archive.namelist() or rel_xml not in archive.namelist():
            return []

        workbook_root = ET.fromstring(archive.read(workbook_xml))
        rel_root = ET.fromstring(archive.read(rel_xml))

        rel_map: dict[str, str] = {}
        for rel in rel_root.findall(f"{XML_NS_PKG_REL}Relationship"):
            rel_id = rel.attrib.get("Id", "")
            target = rel.attrib.get("Target", "")
            if not rel_id or not target:
                continue
            if target.startswith("/"):
                rel_map[rel_id] = target.lstrip("/")
            else:
                rel_map[rel_id] = target if target.startswith("xl/") else f"xl/{target}"

        sheet_paths: list[tuple[str, str]] = []
        for sheet in workbook_root.findall("m:sheets/m:sheet", XML_NS_MAIN):
            name = sheet.attrib.get("name", "").strip()
            rel_id = sheet.attrib.get(XML_NS_OFFICE_REL, "")
            target = rel_map.get(rel_id, "")
            if name and target:
                sheet_paths.append((name, target))
        return sheet_paths

    def _read_shared_strings(self, archive: zipfile.ZipFile) -> list[str]:
        shared_xml = "xl/sharedStrings.xml"
        if shared_xml not in archive.namelist():
            return []
        root = ET.fromstring(archive.read(shared_xml))
        values: list[str] = []
        for item in root.findall("m:si", XML_NS_MAIN):
            parts = [node.text or "" for node in item.findall(".//m:t", XML_NS_MAIN)]
            values.append("".join(parts))
        return values

    def _read_sheet_rows(
        self,
        archive: zipfile.ZipFile,
        sheet_path: str,
        shared_strings: list[str],
    ) -> list[list[str]]:
        root = ET.fromstring(archive.read(sheet_path))
        rows: list[list[str]] = []
        for row in root.findall("m:sheetData/m:row", XML_NS_MAIN):
            row_values: dict[int, str] = {}
            for cell in row.findall("m:c", XML_NS_MAIN):
                ref = cell.attrib.get("r", "")
                col = "".join(ch for ch in ref if ch.isalpha())
                if not col:
                    continue
                col_index = self._excel_col_to_index(col)
                value = self._read_cell_value(cell, shared_strings)
                row_values[col_index] = value

            if not row_values:
                continue
            max_col = max(row_values.keys())
            normalized = [row_values.get(i, "") for i in range(1, max_col + 1)]
            if any(str(cell).strip() for cell in normalized):
                rows.append(normalized)
        return rows

    @staticmethod
    def _read_cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
        cell_type = cell.attrib.get("t", "")
        if cell_type == "s":
            node = cell.find("m:v", XML_NS_MAIN)
            if node is None or node.text is None:
                return ""
            try:
                idx = int(node.text)
            except ValueError:
                return ""
            if 0 <= idx < len(shared_strings):
                return shared_strings[idx]
            return ""

        if cell_type == "inlineStr":
            texts = [node.text or "" for node in cell.findall(".//m:t", XML_NS_MAIN)]
            return "".join(texts)

        node = cell.find("m:v", XML_NS_MAIN)
        return node.text if node is not None and node.text is not None else ""

    @staticmethod
    def _excel_col_to_index(col: str) -> int:
        number = 0
        for char in col:
            if "A" <= char <= "Z":
                number = number * 26 + (ord(char) - ord("A") + 1)
            elif "a" <= char <= "z":
                number = number * 26 + (ord(char) - ord("a") + 1)
        return number
