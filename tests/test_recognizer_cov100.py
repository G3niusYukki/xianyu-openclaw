from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.ticketing.recognizer import (
    ITicketRecognizer,
    RegexTicketRecognizer,
    TicketRecognitionError,
    TicketSelection,
)


class TestITicketRecognizer:
    def test_abstract_cannot_instantiate(self):
        with pytest.raises(TypeError):
            ITicketRecognizer()


class TestReadText:
    @pytest.mark.asyncio
    async def test_ocr_reader_returns_text(self):
        recognizer = RegexTicketRecognizer(ocr_reader=lambda b: "some text from ocr")
        text = await recognizer._read_text(b"image data")
        assert text == "some text from ocr"

    @pytest.mark.asyncio
    async def test_ocr_reader_async(self):
        async def async_reader(b):
            return "async ocr text"
        recognizer = RegexTicketRecognizer(ocr_reader=async_reader)
        text = await recognizer._read_text(b"image data")
        assert text == "async ocr text"

    @pytest.mark.asyncio
    async def test_ocr_reader_returns_empty_fallback_bytes(self):
        recognizer = RegexTicketRecognizer(ocr_reader=lambda b: "")
        text = await recognizer._read_text("影院: 万达\n时间: 2024-01-01 14:00\n座位: 3排5座".encode("utf-8"))
        assert "影院" in text

    @pytest.mark.asyncio
    async def test_no_reader_non_utf8(self):
        recognizer = RegexTicketRecognizer()
        with pytest.raises(TicketRecognitionError, match="No OCR reader"):
            await recognizer._read_text(b"\x80\x81\x82")

    @pytest.mark.asyncio
    async def test_bytes_decode_success(self):
        recognizer = RegexTicketRecognizer()
        text = await recognizer._read_text("影院: test\n时间: 2024-01-01 14:00\n座位: 3排5座".encode("utf-8"))
        assert "影院" in text


class TestRecognizeFromText:
    def test_empty_text(self):
        recognizer = RegexTicketRecognizer()
        with pytest.raises(TicketRecognitionError, match="OCR text is empty"):
            recognizer.recognize_from_text("")

    def test_missing_required_fields(self):
        recognizer = RegexTicketRecognizer()
        with pytest.raises(TicketRecognitionError, match="Missing required"):
            recognizer.recognize_from_text("some random text without fields")

    def test_full_extraction(self):
        text = "影院: 万达影城北京店\n场次: 2024-03-15 14:30\n座位: 3排5座、3排6座"
        recognizer = RegexTicketRecognizer()
        result = recognizer.recognize_from_text(text)
        assert result.cinema
        assert result.showtime
        assert result.seat
        assert result.count >= 1


class TestExtractCinema:
    def test_labeled_cinema(self):
        text = "影院: 万达影城\n其他内容"
        result = RegexTicketRecognizer._extract_cinema(text)
        assert "万达影城" in result

    def test_inline_cinema(self):
        text = "万达影院"
        result = RegexTicketRecognizer._extract_cinema(text)
        assert "影院" in result


class TestExtractShowtime:
    def test_labeled_showtime(self):
        recognizer = RegexTicketRecognizer()
        text = "场次: 2024-03-15 14:30"
        result = recognizer._extract_showtime(text)
        assert "2024-03-15 14:30" in result

    def test_pattern_match(self):
        recognizer = RegexTicketRecognizer()
        text = "演出 2024-03-15 14:30 开始"
        result = recognizer._extract_showtime(text)
        assert result

    def test_chinese_date(self):
        recognizer = RegexTicketRecognizer()
        text = "3月15日 14:30"
        result = recognizer._extract_showtime(text)
        assert result


class TestExtractSeat:
    def test_labeled_seat(self):
        recognizer = RegexTicketRecognizer()
        text = "座位: 3排5座"
        result = recognizer._extract_seat(text)
        assert "3排5座" in result

    def test_pattern_seat(self):
        recognizer = RegexTicketRecognizer()
        text = "选座 A12、A13 确认"
        result = recognizer._extract_seat(text)
        assert result


class TestCountSeats:
    def test_empty(self):
        assert RegexTicketRecognizer._count_seats("") == 0

    def test_multiple_seats(self):
        assert RegexTicketRecognizer._count_seats("3排5座、3排6座") == 2

    def test_single_seat(self):
        assert RegexTicketRecognizer._count_seats("3排5座") == 1
