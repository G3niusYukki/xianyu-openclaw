"""
闲鱼自动化工具 - 主入口
Xianyu Automation Tool - Main Entry Point

基于OpenClaw框架的闲鱼自动化运营工具
"""

import asyncio
import sys
import os
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
        from src.modules.listing.service import ListingService
        from src.modules.media.service import MediaService
        from src.modules.content.service import ContentService
        from src.modules.operations.service import OperationsService
        from src.modules.analytics.service import AnalyticsService
        from src.modules.accounts.service import AccountsService

        logger.success("All modules loaded successfully")
        logger.info("Tool is ready for use")

    except ImportError as e:
        logger.error(f"Failed to load modules: {e}")


def run():
    """运行入口"""
    asyncio.run(main())


if __name__ == "__main__":
    run()
