"""闲管家集成层响应模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class XianGuanJiaResponse:
    """标准化后的闲管家响应。"""

    ok: bool
    data: Any
    error_code: str | None
    error_message: str
    retryable: bool
    request_id: str | None
    http_status: int | None
    raw_payload: Any

    @classmethod
    def success(
        cls,
        *,
        data: Any,
        request_id: str | None = None,
        http_status: int | None = None,
        raw_payload: Any = None,
    ) -> XianGuanJiaResponse:
        return cls(
            ok=True,
            data=data,
            error_code=None,
            error_message="",
            retryable=False,
            request_id=request_id,
            http_status=http_status,
            raw_payload=raw_payload,
        )

    @classmethod
    def failure(
        cls,
        *,
        error_code: str | None,
        error_message: str,
        retryable: bool,
        data: Any = None,
        request_id: str | None = None,
        http_status: int | None = None,
        raw_payload: Any = None,
    ) -> XianGuanJiaResponse:
        return cls(
            ok=False,
            data=data,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
            request_id=request_id,
            http_status=http_status,
            raw_payload=raw_payload,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "retryable": self.retryable,
            "request_id": self.request_id,
            "http_status": self.http_status,
            "raw_payload": self.raw_payload,
        }
