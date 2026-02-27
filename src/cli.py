"""
闲鱼自动化工具 CLI

供 OpenClaw Agent 通过 bash tool 调用的命令行接口。
所有命令输出结构化 JSON，方便 Agent 解析结果。

用法:
    python -m src.cli publish --title "..." --price 5999 --images img1.jpg img2.jpg
    python -m src.cli polish --all --max 50
    python -m src.cli polish --id item_123456
    python -m src.cli price --id item_123456 --price 4999
    python -m src.cli delist --id item_123456
    python -m src.cli relist --id item_123456
    python -m src.cli analytics --action dashboard
    python -m src.cli analytics --action daily
    python -m src.cli analytics --action trend --metric views --days 30
    python -m src.cli accounts --action list
    python -m src.cli accounts --action health --id account_1
    python -m src.cli messages --action auto-reply --limit 20 --dry-run
"""

import argparse
import asyncio
import json
import sys
from typing import Any


def _json_out(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


async def cmd_publish(args: argparse.Namespace) -> None:
    from src.core.browser_client import create_browser_client
    from src.modules.listing.models import Listing
    from src.modules.listing.service import ListingService

    client = await create_browser_client()
    try:
        service = ListingService(controller=client)
        listing = Listing(
            title=args.title,
            description=args.description or "",
            price=args.price,
            original_price=args.original_price,
            category=args.category or "其他闲置",
            images=args.images or [],
            tags=args.tags or [],
        )
        result = await service.create_listing(listing)
        _json_out(
            {
                "success": result.success,
                "product_id": result.product_id,
                "product_url": result.product_url,
                "error": result.error_message,
            }
        )
    finally:
        await client.disconnect()


async def cmd_polish(args: argparse.Namespace) -> None:
    from src.core.browser_client import create_browser_client
    from src.modules.operations.service import OperationsService

    client = await create_browser_client()
    try:
        service = OperationsService(controller=client)
        if args.all:
            result = await service.batch_polish(max_items=args.max)
        elif args.id:
            result = await service.polish_listing(args.id)
        else:
            _json_out({"error": "Specify --all or --id <product_id>"})
            return
        _json_out(result)
    finally:
        await client.disconnect()


async def cmd_price(args: argparse.Namespace) -> None:
    from src.core.browser_client import create_browser_client
    from src.modules.operations.service import OperationsService

    client = await create_browser_client()
    try:
        service = OperationsService(controller=client)
        result = await service.update_price(args.id, args.price, args.original_price)
        _json_out(result)
    finally:
        await client.disconnect()


async def cmd_delist(args: argparse.Namespace) -> None:
    from src.core.browser_client import create_browser_client
    from src.modules.operations.service import OperationsService

    client = await create_browser_client()
    try:
        service = OperationsService(controller=client)
        result = await service.delist(args.id, reason=args.reason or "不卖了")
        _json_out(result)
    finally:
        await client.disconnect()


async def cmd_relist(args: argparse.Namespace) -> None:
    from src.core.browser_client import create_browser_client
    from src.modules.operations.service import OperationsService

    client = await create_browser_client()
    try:
        service = OperationsService(controller=client)
        result = await service.relist(args.id)
        _json_out(result)
    finally:
        await client.disconnect()


async def cmd_analytics(args: argparse.Namespace) -> None:
    from src.modules.analytics.service import AnalyticsService

    service = AnalyticsService()
    action = args.action

    if action == "dashboard":
        result = await service.get_dashboard_stats()
    elif action == "daily":
        result = await service.get_daily_report()
    elif action == "trend":
        result = await service.get_trend_data(
            metric=args.metric or "views",
            days=args.days or 30,
        )
    elif action == "export":
        filepath = await service.export_data(
            data_type=args.type or "products",
            format=args.format or "csv",
        )
        result = {"filepath": filepath}
    else:
        result = {"error": f"Unknown analytics action: {action}"}

    _json_out(result)


async def cmd_accounts(args: argparse.Namespace) -> None:
    from src.modules.accounts.service import AccountsService

    service = AccountsService()
    action = args.action

    if action == "list":
        result = service.get_accounts()
    elif action == "health":
        if not args.id:
            _json_out({"error": "Specify --id <account_id>"})
            return
        result = service.get_account_health(args.id)
    elif action == "validate":
        if not args.id:
            _json_out({"error": "Specify --id <account_id>"})
            return
        result = {"valid": service.validate_cookie(args.id)}
    elif action == "refresh-cookie":
        if not args.id or not args.cookie:
            _json_out({"error": "Specify --id and --cookie"})
            return
        result = service.refresh_cookie(args.id, args.cookie)
    else:
        result = {"error": f"Unknown accounts action: {action}"}

    _json_out(result)


async def cmd_messages(args: argparse.Namespace) -> None:
    from src.core.browser_client import create_browser_client
    from src.modules.messages.service import MessagesService

    client = await create_browser_client()
    try:
        service = MessagesService(controller=client)
        action = args.action

        if action == "list-unread":
            result = await service.get_unread_sessions(limit=args.limit or 20)
            _json_out({"total": len(result), "sessions": result})
            return

        if action == "reply":
            if not args.session_id or not args.text:
                _json_out({"error": "Specify --session-id and --text"})
                return
            sent = await service.reply_to_session(args.session_id, args.text)
            _json_out(
                {
                    "session_id": args.session_id,
                    "reply": args.text,
                    "success": bool(sent),
                }
            )
            return

        if action == "auto-reply":
            result = await service.auto_reply_unread(limit=args.limit or 20, dry_run=bool(args.dry_run))
            _json_out(result)
            return

        _json_out({"error": f"Unknown messages action: {action}"})
    finally:
        await client.disconnect()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xianyu-cli",
        description="闲鱼自动化工具 CLI — 供 OpenClaw Agent 调用",
    )
    sub = parser.add_subparsers(dest="command", help="可用命令")

    # publish
    p = sub.add_parser("publish", help="发布商品")
    p.add_argument("--title", required=True, help="商品标题")
    p.add_argument("--price", type=float, required=True, help="售价")
    p.add_argument("--description", default="", help="商品描述")
    p.add_argument("--original-price", type=float, default=None, help="原价")
    p.add_argument("--category", default="其他闲置", help="分类")
    p.add_argument("--images", nargs="*", default=[], help="图片路径列表")
    p.add_argument("--tags", nargs="*", default=[], help="标签列表")

    # polish
    p = sub.add_parser("polish", help="擦亮商品")
    p.add_argument("--all", action="store_true", help="擦亮所有商品")
    p.add_argument("--id", help="擦亮指定商品")
    p.add_argument("--max", type=int, default=50, help="最大擦亮数量")

    # price
    p = sub.add_parser("price", help="调整价格")
    p.add_argument("--id", required=True, help="商品 ID")
    p.add_argument("--price", type=float, required=True, help="新价格")
    p.add_argument("--original-price", type=float, default=None, help="原价")

    # delist
    p = sub.add_parser("delist", help="下架商品")
    p.add_argument("--id", required=True, help="商品 ID")
    p.add_argument("--reason", default="不卖了", help="下架原因")

    # relist
    p = sub.add_parser("relist", help="重新上架")
    p.add_argument("--id", required=True, help="商品 ID")

    # analytics
    p = sub.add_parser("analytics", help="数据分析")
    p.add_argument("--action", required=True, choices=["dashboard", "daily", "trend", "export"])
    p.add_argument("--metric", default="views", help="趋势指标")
    p.add_argument("--days", type=int, default=30, help="天数")
    p.add_argument("--type", default="products", help="导出类型")
    p.add_argument("--format", default="csv", help="导出格式")

    # accounts
    p = sub.add_parser("accounts", help="账号管理")
    p.add_argument("--action", required=True, choices=["list", "health", "validate", "refresh-cookie"])
    p.add_argument("--id", help="账号 ID")
    p.add_argument("--cookie", help="新的 Cookie 值")

    # messages
    p = sub.add_parser("messages", help="消息自动回复")
    p.add_argument("--action", required=True, choices=["list-unread", "reply", "auto-reply"])
    p.add_argument("--limit", type=int, default=20, help="最多处理会话数")
    p.add_argument("--session-id", help="会话 ID（reply 时必填）")
    p.add_argument("--text", help="回复内容（reply 时必填）")
    p.add_argument("--dry-run", action="store_true", help="仅生成回复，不真正发送")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "publish": cmd_publish,
        "polish": cmd_polish,
        "price": cmd_price,
        "delist": cmd_delist,
        "relist": cmd_relist,
        "analytics": cmd_analytics,
        "accounts": cmd_accounts,
        "messages": cmd_messages,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    try:
        asyncio.run(handler(args))
    except KeyboardInterrupt:
        pass
    except Exception as e:
        _json_out({"error": str(e)})
        sys.exit(1)


if __name__ == "__main__":
    main()
