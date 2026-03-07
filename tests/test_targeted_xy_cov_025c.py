from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image

from src.modules.media.service import MediaService
from src.modules.operations.service import OperationsService


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    async def _noop(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", _noop)


@pytest.mark.asyncio
async def test_operations_batch_polish_returns_disabled():
    svc = OperationsService(controller=None)
    summary = await svc.batch_polish(product_ids=None, max_items=2)

    assert summary["action"] == "batch_polish"
    assert summary["total"] == 0
    assert summary["blocked"] is True
    assert "擦亮功能已停用" in summary["message"]
    assert summary["details"] == []


@pytest.mark.asyncio
async def test_operations_batch_polish_disabled_with_product_ids():
    svc = OperationsService(controller=None)
    result = await svc.batch_polish(product_ids=["x"], max_items=1)

    assert result["action"] == "batch_polish"
    assert result["blocked"] is True
    assert result["total"] == 0
    assert "擦亮功能已停用" in result["message"]


@pytest.mark.asyncio
async def test_operations_update_price_without_api_client():
    analytics = Mock()
    analytics.log_operation = AsyncMock(return_value=True)

    svc = OperationsService(controller=None, analytics=analytics)
    result = await svc.update_price("pid-1", 9.9, 12.3)

    assert result["success"] is False
    assert result["product_id"] == "pid-1"
    assert result["old_price"] == 12.3
    assert result["new_price"] == 9.9
    assert result["error"] == "api_client_not_configured"
    analytics.log_operation.assert_awaited_once()


@pytest.mark.asyncio
async def test_operations_delist_without_api_client():
    svc = OperationsService(controller=None)
    result = await svc.delist("pid-2", reason="库存调整")

    assert result["success"] is False
    assert result["action"] == "delist"
    assert result["error"] == "api_client_not_configured"


def test_media_batch_process_resize_exception_branch(tmp_path: Path, monkeypatch):
    src = tmp_path / "a.jpg"
    Image.new("RGB", (50, 50), (12, 34, 56)).save(src)

    out_dir = tmp_path / "out"
    svc = MediaService(config={"watermark": {"enabled": False}, "supported_formats": ["jpg"]})

    monkeypatch.setattr(svc, "resize_image_for_xianyu", Mock(side_effect=RuntimeError("resize boom")))

    result = svc.batch_process_images([str(src)], output_dir=str(out_dir), add_watermark=False)

    assert result == [str(src)]
    assert out_dir.exists()


def test_media_add_watermark_invalid_color_returns_original(tmp_path: Path):
    src = tmp_path / "w.jpg"
    Image.new("RGB", (80, 40), (255, 255, 255)).save(src)

    svc = MediaService(
        config={
            "supported_formats": ["jpg", "jpeg", "png"],
            "watermark": {"enabled": True, "text": "T", "color": "#ZZZZZZ", "font_size": 14},
        }
    )

    out = svc.add_watermark(str(src), position="not-a-valid-position")

    assert out == str(src)


def test_media_validate_image_unreadable_file(tmp_path: Path):
    bad_png = tmp_path / "bad.png"
    bad_png.write_text("not an image", encoding="utf-8")

    svc = MediaService(config={"supported_formats": ["png"], "max_image_size": 1024 * 1024, "watermark": {"enabled": False}})
    ok, msg = svc.validate_image(str(bad_png))

    assert ok is False
    assert "无法读取图片" in msg


def test_media_helpers_formats_and_rgb_p_mode(tmp_path: Path):
    src = tmp_path / "palette.png"
    img = Image.new("P", (10, 10))
    img.save(src)

    svc = MediaService(config={"supported_formats": ["png"], "watermark": {"enabled": False}})

    with Image.open(src) as opened:
        rgb = svc._ensure_rgb(opened)
        assert rgb.mode == "RGB"

    assert svc._get_save_format("unknown-ext") == "JPEG"


def test_media_compress_image_exception_returns_original(monkeypatch):
    svc = MediaService(config={"watermark": {"enabled": False}})

    class _Boom:
        def __enter__(self):
            raise OSError("open failed")

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    monkeypatch.setattr("src.modules.media.service.Image.open", lambda *_args, **_kwargs: _Boom())

    path = "/tmp/does-not-matter.jpg"
    out = svc.compress_image(path, quality=10)
    assert out == path
