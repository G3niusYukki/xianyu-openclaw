from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.modules.quote.models import QuoteRequest, QuoteResult


class TestCostTableUncovered:
    """Cover uncovered lines in cost_table.py."""

    def test_rank_by_route_similarity_empty(self):
        from src.modules.quote.cost_table import CostTableRepository
        repo = CostTableRepository.__new__(CostTableRepository)
        assert repo._rank_by_route_similarity([], "北京", "上海") == []

    def test_rank_by_route_similarity_no_match(self):
        from src.modules.quote.cost_table import CostRecord, CostTableRepository
        repo = CostTableRepository.__new__(CostTableRepository)
        repo.geo_resolver = MagicMock()
        records = [CostRecord(courier="圆通", origin="", destination="", first_cost=5, extra_cost=2)]
        assert repo._rank_by_route_similarity(records, "北京", "上海") == []

    def test_rank_by_route_similarity_with_match(self):
        from src.modules.quote.cost_table import CostRecord, CostTableRepository
        repo = CostTableRepository.__new__(CostTableRepository)
        repo.geo_resolver = MagicMock()
        records = [CostRecord(courier="圆通", origin="北京", destination="上海", first_cost=5, extra_cost=2)]
        result = repo._rank_by_route_similarity(records, "北京", "上海")
        assert len(result) == 1

    def test_find_candidates_route_scored_fallback(self):
        from src.modules.quote.cost_table import CostRecord, CostTableRepository
        repo = CostTableRepository.__new__(CostTableRepository)
        repo.geo_resolver = MagicMock()
        repo.geo_resolver.province_of = MagicMock(return_value="")
        repo.include_patterns = ("*.csv",)
        repo.table_dir = MagicMock()

        records = [CostRecord(courier="圆通", origin="广州", destination="深圳", first_cost=5, extra_cost=2)]
        repo._records = records
        repo._signature = (("fake", 1, 1),)
        repo._index_route = {}
        repo._index_courier_route = {}
        repo._index_destination = {}
        repo._index_courier_destination = {}

        with patch.object(repo, "_reload_if_needed"):
            with patch.object(repo, "_rank_by_route_similarity", return_value=records):
                result = repo.find_candidates("广州", "深圳")
                assert len(result) >= 1

    def test_rows_to_records_skips_missing_fields(self):
        from src.modules.quote.cost_table import CostTableRepository
        repo = CostTableRepository.__new__(CostTableRepository)
        repo.geo_resolver = MagicMock()
        rows = [
            ["快递公司", "始发地", "目的地", "首重", "续重"],
            ["圆通", "北京", "上海", "5", "2"],
            ["", "北京", "上海", "5", "2"],
            ["圆通", "", "上海", "5", "2"],
            ["圆通", "北京", "上海", "", "2"],
            ["圆通", "北京", "上海", "5", ""],
        ]
        records = repo._rows_to_records(rows, "test.csv", "csv")
        assert len(records) == 1

    def test_read_text_file_fallback_encoding(self):
        from src.modules.quote.cost_table import CostTableRepository
        import tempfile
        from pathlib import Path
        content = "快递公司,始发地,目的地,首重,续重\n圆通,北京,上海,5,2"
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="wb") as f:
            f.write(content.encode("gb18030"))
            f.flush()
            path = Path(f.name)
        try:
            result = CostTableRepository._read_text_file(path)
            assert "快递公司" in result
        finally:
            path.unlink()

    def test_read_text_file_undecodable(self):
        from src.modules.quote.cost_table import CostTableRepository
        import tempfile
        from pathlib import Path
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="wb") as f:
            f.write(bytes(range(128, 256)) * 10)
            f.flush()
            path = Path(f.name)
        try:
            result = CostTableRepository._read_text_file(path)
            assert isinstance(result, str)
        finally:
            path.unlink()

    def test_to_float_chinese_comma(self):
        from src.modules.quote.cost_table import CostTableRepository
        assert CostTableRepository._to_float("1，000.5") == 1000.5

    def test_to_float_no_match(self):
        from src.modules.quote.cost_table import CostTableRepository
        assert CostTableRepository._to_float("abc") is None


class TestQuoteProviders:
    """Cover uncovered lines in providers.py."""

    async def test_iquote_provider_abstract(self):
        from src.modules.quote.providers import IQuoteProvider
        with pytest.raises(TypeError):
            IQuoteProvider()

    async def test_iquote_provider_get_quote_abstract(self):
        from src.modules.quote.providers import IQuoteProvider
        class Dummy(IQuoteProvider):
            async def get_quote(self, request, timeout_ms=3000):
                return None
            async def health_check(self):
                return True
        d = Dummy()
        assert await d.health_check() is True

    async def test_remote_provider_api_request_fails(self):
        from src.modules.quote.providers import RemoteQuoteProvider, QuoteProviderError
        provider = RemoteQuoteProvider(api_url="https://test.api")
        req = QuoteRequest(origin="北京", destination="上海", weight=1.0)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=ConnectionError("fail"))
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(QuoteProviderError, match="request failed"):
                await provider.get_quote(req)

    async def test_remote_provider_api_http_error(self):
        from src.modules.quote.providers import RemoteQuoteProvider, QuoteProviderError
        provider = RemoteQuoteProvider(api_url="https://test.api")
        req = QuoteRequest(origin="北京", destination="上海", weight=1.0)
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(QuoteProviderError, match="http 500"):
                await provider.get_quote(req)

    async def test_remote_provider_api_invalid_json(self):
        from src.modules.quote.providers import RemoteQuoteProvider, QuoteProviderError
        provider = RemoteQuoteProvider(api_url="https://test.api")
        req = QuoteRequest(origin="北京", destination="上海", weight=1.0)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("bad json")
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(QuoteProviderError, match="invalid json"):
                await provider.get_quote(req)

    async def test_remote_provider_api_missing_fee(self):
        from src.modules.quote.providers import RemoteQuoteProvider, QuoteProviderError
        provider = RemoteQuoteProvider(api_url="https://test.api")
        req = QuoteRequest(origin="北京", destination="上海", weight=1.0)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"provider": "test"}}
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(QuoteProviderError, match="missing"):
                await provider.get_quote(req)

    async def test_parse_remote_quote_response_list(self):
        from src.modules.quote.providers import _parse_remote_quote_response
        result = _parse_remote_quote_response([{"total_fee": 10}])
        assert result["total_fee"] == 10

    async def test_parse_remote_quote_response_empty_list(self):
        from src.modules.quote.providers import _parse_remote_quote_response
        result = _parse_remote_quote_response([])
        assert result["total_fee"] is None

    async def test_parse_remote_quote_response_non_dict_in_list(self):
        from src.modules.quote.providers import _parse_remote_quote_response
        result = _parse_remote_quote_response(["not_dict"])
        assert result["total_fee"] is None

    async def test_parse_remote_quote_response_not_dict(self):
        from src.modules.quote.providers import _parse_remote_quote_response
        result = _parse_remote_quote_response("string")
        assert result["total_fee"] is None

    async def test_parse_remote_quote_response_non_dict_payload(self):
        from src.modules.quote.providers import _parse_remote_quote_response
        result = _parse_remote_quote_response({"data": "string_data"})
        assert isinstance(result, dict)

    def test_first_positive(self):
        from src.modules.quote.providers import _first_positive
        assert _first_positive(0, -1, 5) == 5.0
        assert _first_positive(0, 0) == 0.0
        assert _first_positive(None, None) == 0.0
        assert _first_positive(3) == 3.0


class TestQuoteEngine:
    """Cover uncovered line 297 in engine.py."""

    def test_resolve_remote_api_key_env_name_env_ref(self):
        from src.modules.quote.engine import AutoQuoteEngine
        result = AutoQuoteEngine._resolve_remote_api_key_env_name(
            {"remote_api_key": "${MY_CUSTOM_KEY}"}
        )
        assert result == "MY_CUSTOM_KEY"

    def test_resolve_remote_api_key_env_name_default(self):
        from src.modules.quote.engine import AutoQuoteEngine
        result = AutoQuoteEngine._resolve_remote_api_key_env_name({})
        assert result == "QUOTE_API_KEY"


class TestExcelImport:
    """Cover uncovered lines 60, 62 in excel_import.py."""

    def test_import_skips_incomplete_rows(self):
        from src.modules.quote.excel_import import ExcelAdaptiveImporter
        importer = ExcelAdaptiveImporter()
        rows = [
            ["快递公司", "始发地", "目的地", "首重", "续重"],
            ["", "北京", "上海", "5", "2"],
            ["圆通", "北京", "", "5", "2"],
            ["圆通", "北京", "上海", "", ""],
        ]
        with patch("pathlib.Path.exists", return_value=True):
            with patch.object(importer, "_load_rows", return_value={"sheet1": rows}):
                with patch.object(importer, "_locate_header", return_value=(
                    {"courier": 0, "origin": 1, "destination": 2, "first_cost": 3, "extra_cost": 4}, 0
                )):
                    with patch.object(importer, "_detect_courier", return_value=""):
                        result = importer.import_file("fake.xlsx")
                        assert len(result.records) == 0
