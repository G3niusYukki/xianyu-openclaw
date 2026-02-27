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
    python -m src.cli messages --action auto-followup --limit 20 --dry-run
    python -m src.cli messages --action auto-workflow --limit 20 --dry-run
    python -m src.cli messages --action run-worker --limit 20 --interval-seconds 15
    python -m src.cli messages --action workflow-status
    python -m src.cli messages --action workflow-transition --session-id s1 --stage ORDERED --force-state
    python -m src.cli quote --action health
    python -m src.cli quote --action doctor
    python -m src.cli quote --action preview --message "寄到上海 2kg 圆通 报价"
    python -m src.cli quote --action setup --mode cost_table_plus_markup --origin-city 安徽 --cost-table-dir data/quote_costs
"""

import argparse
import asyncio
from dataclasses import asdict
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
    from src.modules.messages.worker import WorkflowWorker

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

        if action == "auto-followup":
            result = await service.auto_followup_read_no_reply(limit=args.limit or 20, dry_run=bool(args.dry_run))
            _json_out(result)
            return

        if action == "auto-workflow":
            result = await service.auto_workflow(limit=args.limit or 20, dry_run=bool(args.dry_run))
            _json_out(result)
            return

        if action == "run-worker":
            worker = WorkflowWorker(messages_service=service)
            result = await worker.run(
                limit=args.limit or 20,
                dry_run=bool(args.dry_run),
                interval_seconds=args.interval_seconds,
                max_cycles=args.max_cycles,
                max_runtime_seconds=args.max_runtime_seconds,
            )
            _json_out(result)
            return

        if action == "workflow-status":
            worker = WorkflowWorker(messages_service=service)
            _json_out(worker.get_runtime_status())
            return

        if action == "workflow-transition":
            if not args.session_id or not args.stage:
                _json_out({"error": "Specify --session-id and --stage"})
                return
            result = service.transition_workflow_stage(
                args.session_id,
                args.stage,
                force=bool(args.force_state),
                metadata={"event": "manual_cli_transition"},
            )
            _json_out(result)
            return

        _json_out({"error": f"Unknown messages action: {action}"})
    finally:
        await client.disconnect()


async def cmd_quote(args: argparse.Namespace) -> None:
    from src.modules.quote.service import QuoteService
    from src.modules.quote.setup import QuoteSetupService

    service = QuoteService()
    action = args.action

    if action == "health":
        mode = str(service.config.get("mode", "rule_only"))
        stats = service.get_cost_table_stats(max_files=30)
        _json_out(
            {
                "mode": mode,
                "origin_city": service.config.get("origin_city", "杭州"),
                "pricing_profile": service.config.get("pricing_profile", "normal"),
                "cost_table": stats,
                "api_cost_ready": bool(str(service.config.get("cost_api_url", "")).strip()),
                "remote_quote_ready": bool(str(service.config.get("remote_api_url", "")).strip()),
            }
        )
        return

    if action == "doctor":
        mode = str(service.config.get("mode", "rule_only"))
        stats = service.get_cost_table_stats(max_files=30)
        api_url = str(service.config.get("cost_api_url", "")).strip()
        checks: list[dict[str, Any]] = []

        if mode in {"cost_table_plus_markup", "api_cost_plus_markup"}:
            checks.append(
                {
                    "name": "cost_table_files",
                    "ok": bool(stats.get("exists") and int(stats.get("file_count", 0)) > 0),
                    "message": f"检测到成本表文件数: {int(stats.get('file_count', 0))}",
                }
            )

        if mode == "api_cost_plus_markup":
            checks.append(
                {
                    "name": "cost_api_url",
                    "ok": bool(api_url),
                    "message": "已配置 cost_api_url" if api_url else "未配置 cost_api_url",
                }
            )

        if mode == "rule_only":
            checks.append(
                {
                    "name": "mode_warning",
                    "ok": True,
                    "message": "当前是 rule_only，适合演示，不建议用于真实成本报价。",
                }
            )

        ok_count = sum(1 for item in checks if bool(item.get("ok")))
        overall_ok = ok_count == len(checks) if checks else True
        suggestions = []
        if mode in {"cost_table_plus_markup", "api_cost_plus_markup"} and int(stats.get("file_count", 0)) == 0:
            suggestions.append("请先把成本价表放到 quote.cost_table_dir，并执行 quote setup。")
        if mode == "api_cost_plus_markup" and not api_url:
            suggestions.append("请设置 quote.cost_api_url，或改用 cost_table_plus_markup。")
        if not suggestions:
            suggestions.append("当前报价配置可用，可直接执行 quote preview 做抽样验证。")

        _json_out(
            {
                "mode": mode,
                "overall_ok": overall_ok,
                "checks": checks,
                "suggestions": suggestions,
                "cost_table": stats,
            }
        )
        return

    if action == "candidates":
        if not args.origin_city or not args.destination_city:
            _json_out({"error": "Specify --origin-city and --destination-city"})
            return
        records = service.cost_table_repo.find_candidates(
            origin=args.origin_city,
            destination=args.destination_city,
            courier=args.courier,
            limit=max(args.limit or 20, 1),
        )
        _json_out(
            {
                "total": len(records),
                "origin_city": args.origin_city,
                "destination_city": args.destination_city,
                "courier": args.courier or "",
                "candidates": [
                    {
                        "courier": item.courier,
                        "origin": item.origin,
                        "destination": item.destination,
                        "first_cost": item.first_cost,
                        "extra_cost": item.extra_cost,
                        "throw_ratio": item.throw_ratio,
                        "source_file": item.source_file,
                        "source_sheet": item.source_sheet,
                    }
                    for item in records
                ],
            }
        )
        return

    if action == "preview":
        if not args.message:
            _json_out({"error": "Specify --message"})
            return

        parsed = service.parse_quote_request(args.message, item_title=args.item_title or "")
        quote, source = await service.compute_quote(parsed)
        first_reply = service.build_first_reply(parsed)
        quote_message = service.build_quote_message(quote, parsed.request) if quote else ""
        _json_out(
            {
                "is_quote_intent": parsed.is_quote_intent,
                "missing_fields": parsed.missing_fields,
                "request": asdict(parsed.request),
                "first_reply": first_reply,
                "quote_source": source,
                "quote_result": asdict(quote) if quote is not None else None,
                "quote_message": quote_message,
            }
        )
        return

    if action == "setup":
        setup_service = QuoteSetupService(config_path=args.config_path or "config/config.yaml")
        patterns = []
        raw_patterns = str(args.cost_table_patterns or "*.xlsx,*.csv")
        for item in raw_patterns.split(","):
            text = item.strip()
            if text:
                patterns.append(text)

        result = setup_service.apply(
            mode=args.mode or "cost_table_plus_markup",
            origin_city=args.origin_city,
            pricing_profile=args.pricing_profile or "normal",
            cost_table_dir=args.cost_table_dir or "data/quote_costs",
            cost_table_patterns=patterns,
            api_cost_url=args.cost_api_url or "",
            cost_api_key_env=args.cost_api_key_env or "QUOTE_COST_API_KEY",
            api_fallback_to_table_parallel=not bool(args.disable_fast_fallback),
            api_prefer_max_wait_seconds=float(args.api_prefer_max_wait_seconds or 1.2),
        )
        _json_out(result)
        return

    _json_out({"error": f"Unknown quote action: {action}"})


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
    p.add_argument(
        "--action",
        required=True,
        choices=[
            "list-unread",
            "reply",
            "auto-reply",
            "auto-followup",
            "auto-workflow",
            "run-worker",
            "workflow-status",
            "workflow-transition",
        ],
    )
    p.add_argument("--limit", type=int, default=20, help="最多处理会话数")
    p.add_argument("--session-id", help="会话 ID（reply 时必填）")
    p.add_argument("--text", help="回复内容（reply 时必填）")
    p.add_argument("--stage", help="状态机目标状态（workflow-transition 时必填）")
    p.add_argument("--force-state", action="store_true", help="强制状态迁移（workflow-transition）")
    p.add_argument("--dry-run", action="store_true", help="仅生成回复，不真正发送")
    p.add_argument("--interval-seconds", type=float, default=None, help="worker 轮询间隔（仅 run-worker）")
    p.add_argument("--max-cycles", type=int, default=None, help="worker 最大循环次数（仅 run-worker）")
    p.add_argument(
        "--max-runtime-seconds",
        type=float,
        default=None,
        help="worker 最大运行时长（仅 run-worker）",
    )

    # quote
    p = sub.add_parser("quote", help="自动报价诊断与预览")
    p.add_argument("--action", required=True, choices=["health", "doctor", "preview", "candidates", "setup"])
    p.add_argument("--message", help="买家消息文本（preview 时必填）")
    p.add_argument("--item-title", default="", help="商品标题（preview 可选）")
    p.add_argument("--origin-city", help="始发地（candidates 时必填）")
    p.add_argument("--destination-city", help="目的地（candidates 时必填）")
    p.add_argument("--courier", help="快递公司（candidates 可选）")
    p.add_argument("--limit", type=int, default=20, help="候选数量上限（candidates）")
    p.add_argument("--mode", help="报价模式（setup）")
    p.add_argument("--pricing-profile", default="normal", help="加价档位 normal/member（setup）")
    p.add_argument("--cost-table-dir", help="成本价表目录（setup）")
    p.add_argument("--cost-table-patterns", default="*.xlsx,*.csv", help="成本表匹配规则（setup，逗号分隔）")
    p.add_argument("--cost-api-url", default="", help="成本价接口 URL（setup）")
    p.add_argument("--cost-api-key-env", default="QUOTE_COST_API_KEY", help="成本接口 Key 的环境变量名（setup）")
    p.add_argument("--api-prefer-max-wait-seconds", type=float, default=1.2, help="API 优先等待窗口秒数（setup）")
    p.add_argument("--disable-fast-fallback", action="store_true", help="关闭 API 慢时快速回退（setup）")
    p.add_argument("--config-path", default="config/config.yaml", help="配置文件路径（setup）")

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
        "quote": cmd_quote,
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
