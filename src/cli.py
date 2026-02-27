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
    action = args.action

    if action == "workflow-stats":
        from src.modules.messages.workflow import WorkflowStore

        store = WorkflowStore(db_path=args.workflow_db)
        _json_out(
            {
                "workflow": store.get_workflow_summary(),
                "sla": store.get_sla_summary(window_minutes=args.window_minutes or 1440),
            }
        )
        return

    from src.core.browser_client import create_browser_client
    from src.modules.messages.service import MessagesService

    client = await create_browser_client()
    try:
        service = MessagesService(controller=client)

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

        if action == "auto-workflow":
            from src.modules.messages.workflow import WorkflowWorker

            worker = WorkflowWorker(
                message_service=service,
                config={
                    "db_path": args.workflow_db,
                    "poll_interval_seconds": args.interval,
                    "scan_limit": args.limit,
                },
            )

            if args.daemon:
                result = await worker.run_forever(
                    dry_run=bool(args.dry_run),
                    max_loops=args.max_loops,
                )
            else:
                result = await worker.run_once(dry_run=bool(args.dry_run))
            _json_out(result)
            return

        _json_out({"error": f"Unknown messages action: {action}"})
    finally:
        await client.disconnect()


async def cmd_orders(args: argparse.Namespace) -> None:
    from src.modules.orders.service import OrderFulfillmentService

    service = OrderFulfillmentService(db_path=args.db_path or "data/orders.db")
    action = args.action

    if action == "upsert":
        if not args.order_id or not args.status:
            _json_out({"error": "Specify --order-id and --status"})
            return
        result = service.upsert_order(
            order_id=args.order_id,
            raw_status=args.status,
            session_id=args.session_id or "",
            quote_snapshot={"total_fee": args.quote_fee} if args.quote_fee is not None else {},
            item_type=args.item_type or "virtual",
        )
        _json_out(result)
        return

    if action == "deliver":
        if not args.order_id:
            _json_out({"error": "Specify --order-id"})
            return
        _json_out(service.deliver(order_id=args.order_id, dry_run=bool(args.dry_run)))
        return

    if action == "after-sales":
        if not args.order_id:
            _json_out({"error": "Specify --order-id"})
            return
        _json_out(service.create_after_sales_case(order_id=args.order_id, issue_type=args.issue_type or "delay"))
        return

    if action == "takeover":
        if not args.order_id:
            _json_out({"error": "Specify --order-id"})
            return
        _json_out({"order_id": args.order_id, "manual_takeover": service.set_manual_takeover(args.order_id, True)})
        return

    if action == "resume":
        if not args.order_id:
            _json_out({"error": "Specify --order-id"})
            return
        ok = service.set_manual_takeover(args.order_id, False)
        _json_out({"order_id": args.order_id, "manual_takeover": False if ok else None, "success": ok})
        return

    if action == "trace":
        if not args.order_id:
            _json_out({"error": "Specify --order-id"})
            return
        _json_out(service.trace_order(args.order_id))
        return

    _json_out({"error": f"Unknown orders action: {action}"})


async def cmd_compliance(args: argparse.Namespace) -> None:
    from src.modules.compliance.center import ComplianceCenter

    center = ComplianceCenter(policy_path=args.policy_path, db_path=args.db_path)
    action = args.action

    if action == "reload":
        center.reload()
        _json_out({"success": True, "policy_path": args.policy_path})
        return

    if action == "check":
        decision = center.evaluate_before_send(
            args.content or "",
            actor=args.actor or "cli",
            account_id=args.account_id,
            session_id=args.session_id,
            action=args.audit_action or "message_send",
        )
        _json_out(decision.to_dict())
        return

    if action == "replay":
        result = center.replay(
            account_id=args.account_id,
            session_id=args.session_id,
            blocked_only=bool(args.blocked_only),
            limit=args.limit or 50,
        )
        _json_out({"total": len(result), "events": result})
        return

    _json_out({"error": f"Unknown compliance action: {action}"})


async def cmd_ai(args: argparse.Namespace) -> None:
    from src.modules.content.service import ContentService

    service = ContentService()
    action = args.action

    if action == "cost-stats":
        _json_out(service.get_ai_cost_stats())
        return

    if action == "simulate-publish":
        title = service.generate_title(
            product_name=args.product_name or "iPhone 15 Pro",
            features=["95新", "国行", "自用"],
            category=args.category or "数码手机",
        )
        desc = service.generate_description(
            product_name=args.product_name or "iPhone 15 Pro",
            condition="95新",
            reason="升级换机",
            tags=["闲置", "自用"],
        )
        _json_out({"title": title, "description": desc, "stats": service.get_ai_cost_stats()})
        return

    _json_out({"error": f"Unknown ai action: {action}"})


async def cmd_quote(args: argparse.Namespace) -> None:
    from src.core.config import get_config
    from src.modules.quote import CostTableRepository, QuoteSetupService

    action = args.action
    config = get_config()
    quote_cfg = config.get_section("quote", {})

    if action == "health":
        repo = CostTableRepository(
            cost_table_dir=quote_cfg.get("cost_table_dir", "data/quote_costs"),
            patterns=quote_cfg.get("cost_table_patterns", ["*.xlsx", "*.csv"]),
        )
        stats = repo.get_stats(max_files=30)
        _json_out(
            {
                "mode": quote_cfg.get("mode", "rule_only"),
                "cost_table": stats,
                "api_cost_ready": bool(quote_cfg.get("cost_api_url", "")),
            }
        )
        return

    if action == "candidates":
        if not args.origin_city or not args.destination_city:
            _json_out({"error": "Specify --origin-city and --destination-city"})
            return
        repo = CostTableRepository(
            cost_table_dir=quote_cfg.get("cost_table_dir", "data/quote_costs"),
            patterns=quote_cfg.get("cost_table_patterns", ["*.xlsx", "*.csv"]),
        )
        records = repo.find_candidates(
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
                        "courier": r.courier,
                        "origin": r.origin,
                        "destination": r.destination,
                        "first_cost": r.first_cost,
                        "extra_cost": r.extra_cost,
                    }
                    for r in records
                ],
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
            origin_city=args.origin_city or "杭州",
            pricing_profile=args.pricing_profile or "normal",
            cost_table_dir=args.cost_table_dir or "data/quote_costs",
            cost_table_patterns=patterns,
            api_cost_url=args.cost_api_url or "",
            cost_api_key_env=args.cost_api_key_env or "QUOTE_COST_API_KEY",
        )
        _json_out(result)
        return

    _json_out({"error": f"Unknown quote action: {action}"})


async def cmd_growth(args: argparse.Namespace) -> None:
    from src.modules.growth.service import GrowthService

    service = GrowthService(db_path=args.db_path or "data/growth.db")
    action = args.action

    if action == "set-strategy":
        if not args.strategy_type or not args.version:
            _json_out({"error": "Specify --strategy-type and --version"})
            return
        _json_out(
            service.set_strategy_version(
                strategy_type=args.strategy_type,
                version=args.version,
                active=bool(args.active),
                baseline=bool(args.baseline),
            )
        )
        return

    if action == "rollback":
        if not args.strategy_type:
            _json_out({"error": "Specify --strategy-type"})
            return
        _json_out({"rolled_back": service.rollback_to_baseline(args.strategy_type)})
        return

    if action == "assign":
        if not args.experiment_id or not args.subject_id:
            _json_out({"error": "Specify --experiment-id and --subject-id"})
            return
        variants = tuple((args.variants or "A,B").split(","))
        _json_out(
            service.assign_variant(
                experiment_id=args.experiment_id,
                subject_id=args.subject_id,
                variants=variants,
                strategy_version=args.version,
            )
        )
        return

    if action == "event":
        if not args.subject_id or not args.stage:
            _json_out({"error": "Specify --subject-id and --stage"})
            return
        _json_out(
            service.record_event(
                subject_id=args.subject_id,
                stage=args.stage,
                experiment_id=args.experiment_id,
                variant=args.variant,
                strategy_version=args.version,
            )
        )
        return

    if action == "funnel":
        _json_out(service.funnel_stats(days=args.days or 7, bucket=args.bucket or "day"))
        return

    if action == "compare":
        if not args.experiment_id:
            _json_out({"error": "Specify --experiment-id"})
            return
        _json_out(
            service.compare_variants(
                experiment_id=args.experiment_id,
                from_stage=args.from_stage or "inquiry",
                to_stage=args.to_stage or "ordered",
            )
        )
        return

    _json_out({"error": f"Unknown growth action: {action}"})


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
        choices=["list-unread", "reply", "auto-reply", "auto-workflow", "workflow-stats"],
    )
    p.add_argument("--limit", type=int, default=20, help="最多处理会话数")
    p.add_argument("--session-id", help="会话 ID（reply 时必填）")
    p.add_argument("--text", help="回复内容（reply 时必填）")
    p.add_argument("--dry-run", action="store_true", help="仅生成回复，不真正发送")
    p.add_argument("--daemon", action="store_true", help="常驻运行 workflow worker")
    p.add_argument("--max-loops", type=int, default=None, help="daemon 模式下最多循环次数")
    p.add_argument("--interval", type=float, default=5.0, help="worker 轮询间隔（秒）")
    p.add_argument("--workflow-db", default=None, help="workflow 数据库路径")
    p.add_argument("--window-minutes", type=int, default=1440, help="SLA 统计窗口（分钟）")

    # orders
    p = sub.add_parser("orders", help="订单履约")
    p.add_argument(
        "--action",
        required=True,
        choices=["upsert", "deliver", "after-sales", "takeover", "resume", "trace"],
    )
    p.add_argument("--order-id", help="订单 ID")
    p.add_argument("--status", help="原始订单状态")
    p.add_argument("--session-id", help="关联会话 ID")
    p.add_argument("--item-type", choices=["virtual", "physical"], default="virtual", help="订单类型")
    p.add_argument("--quote-fee", type=float, default=None, help="关联报价金额")
    p.add_argument("--issue-type", default="delay", help="售后类型：delay/refund/quality")
    p.add_argument("--db-path", default="data/orders.db", help="订单数据库路径")
    p.add_argument("--dry-run", action="store_true", help="仅模拟执行")

    # compliance
    p = sub.add_parser("compliance", help="合规策略中心")
    p.add_argument("--action", required=True, choices=["reload", "check", "replay"])
    p.add_argument("--policy-path", default="config/compliance_policies.yaml", help="策略配置路径")
    p.add_argument("--db-path", default="data/compliance.db", help="合规审计库路径")
    p.add_argument("--content", default="", help="待检查内容")
    p.add_argument("--actor", default="cli", help="执行者标识")
    p.add_argument("--account-id", default=None, help="账号ID")
    p.add_argument("--session-id", default=None, help="会话ID")
    p.add_argument("--audit-action", default="message_send", help="审计动作类型")
    p.add_argument("--blocked-only", action="store_true", help="仅查看拦截事件")

    # ai
    p = sub.add_parser("ai", help="AI 调用降本与统计")
    p.add_argument("--action", required=True, choices=["cost-stats", "simulate-publish"])
    p.add_argument("--product-name", default="iPhone 15 Pro", help="模拟商品名")
    p.add_argument("--category", default="数码手机", help="模拟商品分类")

    # quote
    p = sub.add_parser("quote", help="自动报价诊断与配置")
    p.add_argument("--action", required=True, choices=["health", "candidates", "setup"])
    p.add_argument("--origin-city", default=None, help="始发地城市")
    p.add_argument("--destination-city", default=None, help="目的地城市")
    p.add_argument("--courier", default=None, help="快递公司")
    p.add_argument("--limit", type=int, default=20, help="候选数量上限")
    p.add_argument("--mode", default=None, help="报价模式（setup）")
    p.add_argument("--pricing-profile", default="normal", help="加价档位 normal/member（setup）")
    p.add_argument("--cost-table-dir", default="data/quote_costs", help="成本价表目录（setup）")
    p.add_argument("--cost-table-patterns", default="*.xlsx,*.csv", help="成本表匹配规则（setup）")
    p.add_argument("--cost-api-url", default="", help="成本价接口 URL（setup）")
    p.add_argument("--cost-api-key-env", default="QUOTE_COST_API_KEY", help="成本接口 Key 环境变量名（setup）")
    p.add_argument("--config-path", default="config/config.yaml", help="配置文件路径（setup）")

    # growth
    p = sub.add_parser("growth", help="增长实验与漏斗")
    p.add_argument(
        "--action",
        required=True,
        choices=["set-strategy", "rollback", "assign", "event", "funnel", "compare"],
    )
    p.add_argument("--db-path", default="data/growth.db", help="增长数据库路径")
    p.add_argument("--strategy-type", default=None, help="策略类型（reply/quote/followup）")
    p.add_argument("--version", default=None, help="策略版本")
    p.add_argument("--active", action="store_true", help="设置为当前生效版本")
    p.add_argument("--baseline", action="store_true", help="标记为基线版本")
    p.add_argument("--experiment-id", default=None, help="实验ID")
    p.add_argument("--subject-id", default=None, help="主体ID（会话/用户）")
    p.add_argument("--variants", default="A,B", help="变体列表，逗号分隔")
    p.add_argument("--variant", default=None, help="事件所属变体")
    p.add_argument("--stage", default=None, help="漏斗阶段")
    p.add_argument("--days", type=int, default=7, help="漏斗窗口天数")
    p.add_argument("--bucket", choices=["day", "week"], default="day", help="聚合粒度")
    p.add_argument("--from-stage", default="inquiry", help="转化起始阶段")
    p.add_argument("--to-stage", default="ordered", help="转化目标阶段")

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
        "orders": cmd_orders,
        "compliance": cmd_compliance,
        "ai": cmd_ai,
        "quote": cmd_quote,
        "growth": cmd_growth,
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
