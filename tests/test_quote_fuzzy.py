from pathlib import Path
from zipfile import ZipFile

from src.modules.quote.cost_table import CostTableRepository
from src.modules.quote.excel_import import ExcelAdaptiveImporter


def _make_repo_csv(tmp_path: Path, content: str) -> CostTableRepository:
    csv_path = tmp_path / "cost.csv"
    csv_path.write_text(content, encoding="utf-8")
    return CostTableRepository(table_dir=tmp_path, include_patterns=["*.csv"])


def _write_simple_xlsx(path: Path) -> None:
    shared = ["始发地", "收件城市", "首重价格", "续重价格", "快递公司", "杭州", "广州", "4.0", "2.5", "韵达快递"]
    with ZipFile(path, "w") as z:
        z.writestr(
            "[Content_Types].xml",
            """<?xml version='1.0' encoding='UTF-8'?>
<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>
  <Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/>
  <Default Extension='xml' ContentType='application/xml'/>
  <Override PartName='/xl/workbook.xml' ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'/>
  <Override PartName='/xl/worksheets/sheet1.xml' ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'/>
  <Override PartName='/xl/sharedStrings.xml' ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml'/>
</Types>""",
        )
        z.writestr(
            "_rels/.rels",
            """<?xml version='1.0' encoding='UTF-8'?>
<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>
  <Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='xl/workbook.xml'/>
</Relationships>""",
        )
        z.writestr(
            "xl/workbook.xml",
            """<?xml version='1.0' encoding='UTF-8'?>
<workbook xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main' xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'>
  <sheets><sheet name='Sheet1' sheetId='1' r:id='rId1'/></sheets>
</workbook>""",
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version='1.0' encoding='UTF-8'?>
<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>
  <Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet' Target='worksheets/sheet1.xml'/>
  <Relationship Id='rId2' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings' Target='sharedStrings.xml'/>
</Relationships>""",
        )
        z.writestr(
            "xl/sharedStrings.xml",
            "<?xml version='1.0' encoding='UTF-8'?><sst xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>"
            + "".join(f"<si><t>{s}</t></si>" for s in shared)
            + "</sst>",
        )
        z.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version='1.0' encoding='UTF-8'?>
<worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>
  <sheetData>
    <row r='1'><c r='A1' t='s'><v>0</v></c><c r='B1' t='s'><v>1</v></c><c r='C1' t='s'><v>2</v></c><c r='D1' t='s'><v>3</v></c><c r='E1' t='s'><v>4</v></c></row>
    <row r='2'><c r='A2' t='s'><v>5</v></c><c r='B2' t='s'><v>6</v></c><c r='C2' t='s'><v>7</v></c><c r='D2' t='s'><v>8</v></c><c r='E2' t='s'><v>9</v></c></row>
  </sheetData>
</worksheet>""",
        )


def test_exact_match(tmp_path: Path) -> None:
    repo = _make_repo_csv(tmp_path, "快递公司,始发地,目的地,首重,续重\n圆通,浙江,广东,3.0,2.0\n")
    rows = repo.find_candidates("浙江", "广东", courier="圆通")
    assert rows
    assert rows[0].origin == "浙江"
    assert rows[0].destination == "广东"


def test_city_province_mixed_match(tmp_path: Path) -> None:
    repo = _make_repo_csv(tmp_path, "快递公司,始发地,目的地,首重,续重\n圆通,浙江,广东,3.0,2.0\n")
    rows = repo.find_candidates("杭州", "广州", courier="圆通")
    assert rows
    assert rows[0].origin == "浙江"
    assert rows[0].destination == "广东"


def test_fuzzy_contains_match(tmp_path: Path) -> None:
    repo = _make_repo_csv(tmp_path, "快递公司,始发地,目的地,首重,续重\n圆通,上海,北京,3.0,2.0\n")
    rows = repo.find_candidates("上海市", "北京市", courier="圆通")
    assert rows
    assert rows[0].origin == "上海"


def test_excel_adaptive_import(tmp_path: Path) -> None:
    xlsx_path = tmp_path / "韵达报价.xlsx"
    _write_simple_xlsx(xlsx_path)

    importer = ExcelAdaptiveImporter()
    result = importer.import_file(xlsx_path)

    assert result.records
    row = result.records[0]
    assert row.courier == "韵达"
    assert row.origin == "杭州"
    assert row.destination == "广州"
    assert row.source_file == "韵达报价.xlsx"
