"""核心模块行为测试。"""

from unittest.mock import AsyncMock

import pytest

from src.core.error_handler import BrowserError
from src.modules.listing.service import ListingService, XianyuSelectors
from src.modules.media.service import MediaService
from src.modules.operations.service import OperationsService


def test_listing_selectors_publish_page() -> None:
    selectors = XianyuSelectors()
    assert selectors.PUBLISH_PAGE == "https://www.goofish.com/sell"


@pytest.mark.asyncio
async def test_select_category_clicks_mapped_option(mock_controller) -> None:
    service = ListingService(controller=mock_controller)

    await service._step_select_category("page_test_id", "数码手机")

    mock_controller.click.assert_any_call("page_test_id", service.selectors.CATEGORY_SELECT)
    assert mock_controller.execute_script.await_count >= 1
    script = mock_controller.execute_script.await_args_list[-1].args[1]
    assert "手机" in script


@pytest.mark.asyncio
async def test_select_condition_clicks_target_option(mock_controller) -> None:
    service = ListingService(controller=mock_controller)

    await service._step_select_condition("page_test_id", ["99新", "国行"])

    mock_controller.click.assert_any_call("page_test_id", service.selectors.CONDITION_SELECT)
    assert mock_controller.execute_script.await_count >= 1


@pytest.mark.asyncio
async def test_batch_polish_requires_controller() -> None:
    service = OperationsService(controller=None)
    with pytest.raises(BrowserError):
        await service.batch_polish(max_items=5)


@pytest.mark.asyncio
async def test_batch_polish_uses_real_ids_and_counts_failures(mock_controller) -> None:
    service = OperationsService(controller=mock_controller)
    service.compliance._last_action_at.clear()

    mock_controller.find_elements = AsyncMock(return_value=[{"idx": 1}, {"idx": 2}, {"idx": 3}])
    mock_controller.execute_script = AsyncMock(return_value=["item_a", "item_b", "item_c"])

    state = {"polish_clicks": 0}

    async def click_side_effect(_page_id, selector):
        if selector == service.selectors.POLISH_BUTTON:
            state["polish_clicks"] += 1
            return state["polish_clicks"] != 2
        if selector == service.selectors.POLISH_CONFIRM:
            return True
        return True

    mock_controller.click = AsyncMock(side_effect=click_side_effect)

    result = await service.batch_polish(max_items=3)

    assert result["total"] == 3
    assert result["success"] == 2
    assert result["failed"] == 1
    assert [item["product_id"] for item in result["details"]] == ["item_a", "item_b", "item_c"]


def test_media_save_format_mapping_case_insensitive() -> None:
    service = MediaService()
    assert service._get_save_format("PNG") == "PNG"
    assert service._get_save_format("webp") == "WEBP"
