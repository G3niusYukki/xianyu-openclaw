"""
示例脚本
Examples

演示如何使用闲鱼自动化工具
"""

from .demo import demo_listing_creation, demo_batch_publish
from .demo import demo_content_generation, demo_media_processing
from .demo import demo_operations, demo_data_analytics, demo_accounts
from .demo_browser import (
    demo_browser_connection,
    demo_publish_flow,
    demo_polish_flow,
    demo_price_update,
    demo_navigation,
    demo_element_operations
)

__all__ = [
    "demo_listing_creation",
    "demo_batch_publish",
    "demo_content_generation",
    "demo_media_processing",
    "demo_operations",
    "demo_data_analytics",
    "demo_accounts",
    "demo_browser_connection",
    "demo_publish_flow",
    "demo_polish_flow",
    "demo_price_update",
    "demo_navigation",
    "demo_element_operations",
]
