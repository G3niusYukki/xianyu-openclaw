from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image

from src.modules.media.service import MediaService
from src.modules.operations.service import OperationsService, OperationsSelectors


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    async def _noop(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", _noop)


@pytest.mark.asyncio
async def test_operations_batch_polish_warn_and_limit(monkeypatch):
    controller = Mock()
    controller.new_page = AsyncMock(return_value="p1")
    controller.navigate = AsyncMock(return_value=True)
    controller.find_elements = AsyncMock(return_value=[1, 2, 3, 4])
    controller.execute_script = AsyncMock(return_value=["id1", "id2", "id3", "id4"])
    controller.click = AsyncMock(side_effect=[True, True, True, False])
    controller.close_page = AsyncMock(return_value=True)

    analytics = Mock()
    analytics.log_operation = AsyncMock(return_value=True)

    svc = OperationsService(controller=controller, analytics=analytics)
    svc.compliance = Mock(
        evaluate_batch_polish_rate=AsyncMock(return_value={"blocked": False, "warn": True, "message": "near-limit"})
    )

    summary = await svc.batch_polish(product_ids=None, max_items=2)

    assert summary["action"] == "batch_polish"
    assert summary["total"] == 2
    assert summary["success"] == 1
    assert summary["failed"] == 1
    assert summary["details"] == [
        {"success": True, "product_id": "id1", "action": "polish"},
        {"success": False, "product_id": "id2", "action": "polish"},
    ]

    svc.compliance.evaluate_batch_polish_rate.assert_awaited_once_with("batch_polish:global")
    controller.find_elements.assert_awaited_once_with("p1", OperationsSelectors.SELLING_ITEM)
    controller.execute_script.assert_awaited_once()
    controller.close_page.assert_awaited_once_with("p1")

    # warn + summary 两类日志都应写入
    assert analytics.log_operation.await_count == 2
    first_call = analytics.log_operation.await_args_list[0]
    assert first_call.args[0] == "COMPLIANCE_WARN"
    assert first_call.kwargs["status"] == "warning"


@pytest.mark.asyncio
async def test_operations_batch_polish_exception_returns_error():
    controller = Mock()
    controller.new_page = AsyncMock(side_effect=RuntimeError("page create failed"))

    svc = OperationsService(controller=controller)
    svc.compliance = Mock(
        evaluate_batch_polish_rate=AsyncMock(return_value={"blocked": False, "warn": False, "message": "ok"})
    )

    result = await svc.batch_polish(product_ids=["x"], max_items=1)

    assert result["success"] is False
    assert result["action"] == "batch_polish"
    assert result["product_id"] is None
    assert "page create failed" in result["error"]


@pytest.mark.asyncio
async def test_operations_update_price_without_click_submit():
    controller = Mock()
    controller.new_page = AsyncMock(return_value="p2")
    controller.navigate = AsyncMock(return_value=True)
    controller.click = AsyncMock(return_value=False)
    controller.type_text = AsyncMock(return_value=True)
    controller.close_page = AsyncMock(return_value=True)

    analytics = Mock()
    analytics.log_operation = AsyncMock(return_value=True)

    svc = OperationsService(controller=controller, analytics=analytics)
    result = await svc.update_price("pid-1", 9.9, 12.3)

    assert result["success"] is False
    assert result["product_id"] == "pid-1"
    assert result["old_price"] == 12.3
    assert result["new_price"] == 9.9

    controller.type_text.assert_not_awaited()
    # 只点了一次 EDIT_PRICE
    assert controller.click.await_count == 1
    controller.close_page.assert_awaited_once_with("p2")
    analytics.log_operation.assert_awaited_once()


@pytest.mark.asyncio
async def test_operations_delist_without_confirm():
    controller = Mock()
    controller.new_page = AsyncMock(return_value="p3")
    controller.navigate = AsyncMock(return_value=True)
    controller.click = AsyncMock(return_value=True)
    controller.close_page = AsyncMock(return_value=True)

    svc = OperationsService(controller=controller)
    result = await svc.delist("pid-2", reason="库存调整", confirm=False)

    assert result["success"] is True
    assert result["reason"] == "库存调整"
    # confirm=False 时只应点击下架按钮一次
    controller.click.assert_awaited_once_with("p3", OperationsSelectors.DELIST_BUTTON)


@pytest.mark.asyncio
async def test_extract_product_ids_fallback_unknown_ids():
    controller = Mock()
    controller.execute_script = AsyncMock(return_value=[])
    svc = OperationsService(controller=controller)

    ids = await svc._extract_product_ids("pg", limit=3)

    assert ids == ["unknown_1", "unknown_2", "unknown_3"]


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
