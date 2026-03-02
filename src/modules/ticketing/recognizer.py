"""Ticket screenshot recognizer."""

from __future__ import annotations

import asyncio
import inspect
import re
from abc import ABC, abstractmethod
from collections.abc import Callable

from .models import TicketSelection


class TicketRecognitionError(RuntimeError):
    """Raised when a screenshot cannot be converted into a usable request."""


class ITicketRecognizer(ABC):
    """Recognizer interface."""

    @abstractmethod
    async def recognize(self, image_bytes: bytes, mime_type: str = "image/png") -> TicketSelection:
        pass


class RegexTicketRecognizer(ITicketRecognizer):
    """OCR-text-first recognizer with simple regex extraction."""

    _DATETIME_PATTERNS = (
        r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\s+\d{1,2}:\d{2})",
        r"(\d{1,2}[-/.]\d{1,2}\s+\d{1,2}:\d{2})",
        r"(\d{1,2}月\d{1,2}日\s*\d{1,2}:\d{2})",
    )
    _SEAT_PATTERNS = (
        r"((?:\d+排\d+座)(?:[、,，/\s]+(?:\d+排\d+座))*)",
        r"((?:[A-Z]\d+)(?:[、,，/\s]+(?:[A-Z]\d+))*)",
    )

    def __init__(self, ocr_reader: Callable[[bytes], str] | Callable[[bytes], object] | None = None) -> None:
        self.ocr_reader = ocr_reader

    async def recognize(self, image_bytes: bytes, mime_type: str = "image/png") -> TicketSelection:
        text = await self._read_text(image_bytes)
        return self.recognize_from_text(text)

    async def _read_text(self, image_bytes: bytes) -> str:
        if self.ocr_reader is not None:
            result = self.ocr_reader(image_bytes)
            if inspect.isawaitable(result):
                result = await result
            text = str(result or "").strip()
            if text:
                return text

        try:
            text = image_bytes.decode("utf-8").strip()
            if text:
                return text
        except UnicodeDecodeError:
            pass

        raise TicketRecognitionError("No OCR reader configured and image bytes are not plain text")

    def recognize_from_text(self, text: str) -> TicketSelection:
        raw_text = str(text or "").strip()
        if not raw_text:
            raise TicketRecognitionError("OCR text is empty")

        cinema = self._extract_cinema(raw_text)
        showtime = self._extract_showtime(raw_text)
        seat = self._extract_seat(raw_text)
        count = self._count_seats(seat)
        confidence = self._estimate_confidence(cinema=cinema, showtime=showtime, seat=seat)

        if not cinema or not showtime or not seat:
            raise TicketRecognitionError("Missing required ticket fields from screenshot text")

        return TicketSelection(
            cinema=cinema,
            showtime=showtime,
            seat=seat,
            count=count,
            intent="ticket_booking",
            confidence=confidence,
            raw_text=raw_text,
        )

    @staticmethod
    def _extract_cinema(text: str) -> str:
        labeled = re.search(r"(?:影院|影城)[:：]?\s*([^\n]+)", text, flags=re.IGNORECASE)
        if labeled:
            return labeled.group(1).strip()

        for line in [line.strip() for line in text.splitlines() if line.strip()]:
            if any(token in line for token in ("影院", "影城")):
                return line
        return ""

    def _extract_showtime(self, text: str) -> str:
        labeled = re.search(r"(?:场次|时间|开场)[:：]?\s*([^\n]+)", text, flags=re.IGNORECASE)
        if labeled:
            return labeled.group(1).strip()

        for pattern in self._DATETIME_PATTERNS:
            matched = re.search(pattern, text)
            if matched:
                return matched.group(1).strip()
        return ""

    def _extract_seat(self, text: str) -> str:
        labeled = re.search(r"(?:座位|座席)[:：]?\s*([^\n]+)", text, flags=re.IGNORECASE)
        if labeled:
            return labeled.group(1).strip()

        for pattern in self._SEAT_PATTERNS:
            matched = re.search(pattern, text)
            if matched:
                return re.sub(r"\s+", "", matched.group(1).strip())
        return ""

    @staticmethod
    def _count_seats(seat: str) -> int:
        text = re.sub(r"\s+", "", str(seat or ""))
        if not text:
            return 0
        normalized = re.sub(r"[、，/]", ",", text)
        return len([part for part in normalized.split(",") if part]) or 1

    @staticmethod
    def _estimate_confidence(*, cinema: str, showtime: str, seat: str) -> float:
        score = 0.0
        if cinema:
            score += 0.34
        if showtime:
            score += 0.33
        if seat:
            score += 0.33
        return round(score, 2)
