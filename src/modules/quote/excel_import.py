"""Excel 自适应导入：列名变体识别 + 快递公司自动检测。"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from src.modules.quote.cost_table import CostRecord, CostTableRepository, normalize_courier_name
from src.modules.quote.geo_resolver import GeoResolver


@dataclass(slots=True)
class ImportResult:
    records: list[CostRecord]
    detected_couriers: list[str]


class ExcelAdaptiveImporter:
    _HEADER_ALIASES = {
        "courier": {"快递公司", "物流公司", "承运商"},
        "origin": {"始发地", "寄件地", "发件地", "始发城市", "出发地"},
        "destination": {"目的地", "收件地", "收件城市", "到达地"},
        "first_cost": {"首重", "首重1kg", "首重价格", "首重价"},
        "extra_cost": {"续重", "续重1kg", "续重价格", "续重价"},
        "throw_ratio": {"抛比", "抛重比", "材积比", "体积系数"},
    }

    def __init__(self) -> None:
        self.geo = GeoResolver()

    def import_file(self, excel_path: str | Path) -> ImportResult:
        path = Path(excel_path)
        if not path.exists():
            raise FileNotFoundError(path)

        rows_by_sheet = self._load_rows(path)
        records: list[CostRecord] = []
        couriers: list[str] = []

        for sheet_name, rows in rows_by_sheet.items():
            if not rows:
                continue
            header_map, head_idx = self._locate_header(rows)
            if head_idx < 0:
                continue

            sheet_courier = self._detect_courier(rows, sheet_name, path.name, header_map, head_idx)
            if sheet_courier and sheet_courier not in couriers:
                couriers.append(sheet_courier)

            for row in rows[head_idx + 1 :]:
                courier = normalize_courier_name(self._cell(row, header_map.get("courier")) or sheet_courier)
                origin = self.geo.normalize(self._cell(row, header_map.get("origin")))
                destination = self.geo.normalize(self._cell(row, header_map.get("destination")))
                first_cost = self._to_float(self._cell(row, header_map.get("first_cost")))
                extra_cost = self._to_float(self._cell(row, header_map.get("extra_cost")))
                throw_ratio = self._to_float(self._cell(row, header_map.get("throw_ratio")))
                if not courier or not origin or not destination:
                    continue
                if first_cost is None or extra_cost is None:
                    continue
                records.append(
                    CostRecord(
                        courier=courier,
                        origin=origin,
                        destination=destination,
                        first_cost=first_cost,
                        extra_cost=extra_cost,
                        throw_ratio=throw_ratio,
                        source_file=path.name,
                        source_sheet=sheet_name,
                    )
                )

        return ImportResult(records=records, detected_couriers=couriers)

    def _load_rows(self, path: Path) -> dict[str, list[list[str]]]:
        if path.suffix.lower() == ".csv":
            with path.open("r", encoding="utf-8") as f:
                return {"csv": [row for row in csv.reader(f)]}
        repo = CostTableRepository(table_dir=path)
        return repo._iter_xlsx_rows(path)

    def _locate_header(self, rows: list[list[str]]) -> tuple[dict[str, int], int]:
        for idx, row in enumerate(rows):
            mapped = self._resolve_header_map(row)
            required = {"origin", "destination", "first_cost", "extra_cost"}
            if required.issubset(mapped):
                return mapped, idx
        return {}, -1

    def _detect_courier(
        self,
        rows: list[list[str]],
        sheet_name: str,
        file_name: str,
        header_map: dict[str, int],
        header_idx: int,
    ) -> str:
        courier_col = header_map.get("courier")
        if courier_col is not None:
            for row in rows[header_idx + 1 :]:
                value = normalize_courier_name(self._cell(row, courier_col))
                if value:
                    return value

        from_sheet = normalize_courier_name(sheet_name)
        if from_sheet and not sheet_name.lower().startswith("sheet"):
            return from_sheet

        hints = ["圆通", "韵达", "中通", "申通", "顺丰", "京东", "极兔", "德邦", "邮政"]
        for name in hints:
            if name in file_name:
                return name
        return ""

    def _resolve_header_map(self, headers: list[str]) -> dict[str, int]:
        mapped: dict[str, int] = {}
        cleaned_aliases = {k: {self._clean(a) for a in v} for k, v in self._HEADER_ALIASES.items()}
        for idx, value in enumerate(headers):
            cell = self._clean(value)
            if not cell:
                continue
            for key, aliases in cleaned_aliases.items():
                if key in mapped:
                    continue
                if cell in aliases or (key == "first_cost" and "首重" in cell) or (key == "extra_cost" and "续重" in cell):
                    mapped[key] = idx
        return mapped

    @staticmethod
    def _clean(value: object) -> str:
        return str(value or "").strip().lower().replace(" ", "")

    @staticmethod
    def _cell(row: list[str], index: int | None) -> str:
        if index is None or index < 0 or index >= len(row):
            return ""
        return str(row[index] or "").strip()

    @staticmethod
    def _to_float(value: object) -> float | None:
        text = str(value or "").strip().replace(",", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
