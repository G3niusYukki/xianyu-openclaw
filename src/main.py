"""
闲鱼自动化工具 - 主入口
Xianyu Automation Tool - Main Entry Point

基于OpenClaw框架的闲鱼自动化运营工具
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import get_config
from src.core.logger import get_logger


async def main():
    """主函数"""
    config = get_config()
    logger = get_logger()

    logger.info(f"Starting {config.app.get('name', 'xianyu-openclaw')} v{config.app.get('version', '1.0.0')}")

    try:
        from src.modules.accounts.service import AccountsService  # noqa: F401
        from src.modules.analytics.service import AnalyticsService  # noqa: F401
        from src.modules.content.service import ContentService  # noqa: F401
        from src.modules.listing.service import ListingService  # noqa: F401
        from src.modules.media.service import MediaService  # noqa: F401
        from src.modules.messages.service import MessagesService  # noqa: F401
        from src.modules.operations.service import OperationsService  # noqa: F401
        from src.modules.orders.service import OrderFulfillmentService  # noqa: F401
        from src.modules.quote.engine import AutoQuoteEngine  # noqa: F401

        logger.success("All modules loaded successfully")
        logger.info("Tool is ready for use")

    except ImportError as e:
        logger.error(f"Failed to load modules: {e}")


def run():
    """运行入口"""
    asyncio.run(main())


if __name__ == "__main__":
    run()
