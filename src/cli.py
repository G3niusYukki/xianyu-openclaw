"""
闲鱼自动化工具 CLI

供 OpenClaw Agent 通过 bash tool 调用的命令行接口。
所有命令输出结构化 JSON，方便 Agent 解析结果。

用法:
    python -m src.cli automation --action setup --enable-feishu --feishu-webhook "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
    python -m src.cli automation --action status
    python -m src.cli doctor --strict
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
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def _json_out(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _module_check_summary(target: str, doctor_report: dict[str, Any]) -> dict[str, Any]:
    from src.core.startup_checks import resolve_runtime_mode

    runtime = resolve_runtime_mode()
    checks = doctor_report.get("checks", [])
    check_map = {str(item.get("name", "")): item for item in checks}

    required_names = {"Python版本", "数据库", "配置文件", "闲鱼Cookie"}
    if target == "presales":
        required_names.add("消息首响SLA")

    required_checks = [check_map[name] for name in required_names if name in check_map]
    blockers = [item for item in required_checks if not bool(item.get("passed", False))]

    gateway_item = check_map.get("OpenClaw Gateway")
    lite_item = check_map.get("Lite 浏览器驱动")

    if runtime == "pro":
        if gateway_item is not None:
            required_checks.append(gateway_item)
            if not bool(gateway_item.get("passed", False)):
                blockers.append(gateway_item)
    elif runtime == "lite":
        if lite_item is not None:
            required_checks.append(lite_item)
            if not bool(lite_item.get("passed", False)):
                blockers.append(lite_item)
    else:
        # auto: gateway/lite 任一可用即通过，二者都不可用才阻塞。
        browser_ready = bool(gateway_item and gateway_item.get("passed", False)) or bool(
            lite_item and lite_item.get("passed", False)
        )
        if gateway_item is not None:
            required_checks.append(gateway_item)
        if lite_item is not None:
            required_checks.append(lite_item)
        if not browser_ready:
            blockers.append(
                {
                    "name": "浏览器运行时",
                    "passed": False,
                    "critical": True,
                    "message": "auto 模式下 OpenClaw Gateway 与 Lite 驱动均不可用",
                    "suggestion": (
                        "启动 Gateway（docker compose up -d）或安装 Playwright"
                        "（pip install playwright && playwright install chromium）。"
                    ),
                    "meta": {"runtime": runtime},
                }
            )

    return {
        "target": target,
        "runtime": runtime,
        "ready": len(blockers) == 0,
        "required_checks": required_checks,
        "blockers": blockers,
        "next_steps": doctor_report.get("next_steps", []),
        "doctor_summary": doctor_report.get("summary", {}),
    }


_MODULE_RUNTIME_DIR = Path("data/module_runtime")


def _module_state_path(target: str) -> Path:
    _MODULE_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    return _MODULE_RUNTIME_DIR / f"{target}.json"


def _module_log_path(target: str) -> Path:
    _MODULE_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    return _MODULE_RUNTIME_DIR / f"{target}.log"


def _read_module_state(target: str) -> dict[str, Any]:
    path = _module_state_path(target)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_module_state(target: str, data: dict[str, Any]) -> None:
    path = _module_state_path(target)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _build_module_start_command(target: str, args: argparse.Namespace) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "src.cli",
        "module",
        "--action",
        "start",
        "--target",
        target,
        "--mode",
        "daemon",
    ]

    if args.max_loops:
        cmd.extend(["--max-loops", str(args.max_loops)])
    if args.interval:
        cmd.extend(["--interval", str(args.interval)])

    if target == "presales":
        cmd.extend(["--limit", str(args.limit), "--claim-limit", str(args.claim_limit)])
        if args.workflow_db:
            cmd.extend(["--workflow-db", str(args.workflow_db)])
        if bool(args.dry_run):
            cmd.append("--dry-run")
    elif target == "operations":
        if bool(args.init_default_tasks):
            cmd.append("--init-default-tasks")
        if bool(args.skip_polish):
            cmd.append("--skip-polish")
        if bool(args.skip_metrics):
            cmd.append("--skip-metrics")
        if args.polish_max_items:
            cmd.extend(["--polish-max-items", str(args.polish_max_items)])
        if args.polish_cron:
            cmd.extend(["--polish-cron", str(args.polish_cron)])
        if args.metrics_cron:
            cmd.extend(["--metrics-cron", str(args.metrics_cron)])
    else:
        cmd.extend(["--limit", str(args.limit), "--issue-type", str(args.issue_type or "delay")])
        if args.orders_db:
            cmd.extend(["--orders-db", str(args.orders_db)])
        if bool(args.include_manual):
            cmd.append("--include-manual")
        if bool(args.dry_run):
            cmd.append("--dry-run")

    return cmd


def _start_background_module(target: str, args: argparse.Namespace) -> dict[str, Any]:
    state = _read_module_state(target)
    old_pid = int(state.get("pid", 0) or 0)
    if old_pid > 0 and _process_alive(old_pid):
        return {
            "target": target,
            "started": False,
            "reason": "already_running",
            "pid": old_pid,
            "log_file": str(_module_log_path(target)),
        }

    cmd = _build_module_start_command(target=target, args=args)
    log_file = _module_log_path(target)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handle = open(log_file, "a", encoding="utf-8")
    handle.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] start target={target} cmd={' '.join(cmd)}\n")
    handle.flush()

    popen_kwargs: dict[str, Any] = {
        "stdout": handle,
        "stderr": handle,
        "cwd": os.getcwd(),
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        popen_kwargs["preexec_fn"] = os.setsid

    proc = subprocess.Popen(cmd, **popen_kwargs)
    handle.close()
    state = {
        "target": target,
        "pid": proc.pid,
        "log_file": str(log_file),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "command": cmd,
    }
    _write_module_state(target, state)
    return {"target": target, "started": True, "pid": proc.pid, "log_file": str(log_file)}


def _stop_background_module(target: str, timeout_seconds: float = 6.0) -> dict[str, Any]:
    state = _read_module_state(target)
    pid = int(state.get("pid", 0) or 0)
    if pid <= 0:
        return {"target": target, "stopped": False, "reason": "not_running"}
    if not _process_alive(pid):
        return {"target": target, "stopped": False, "reason": "pid_not_alive", "pid": pid}

    try:
        if os.name == "nt":
            os.kill(pid, signal.SIGTERM)
        else:
            os.killpg(pid, signal.SIGTERM)
    except Exception as exc:
        return {"target": target, "stopped": False, "reason": f"signal_failed: {exc}", "pid": pid}

    start = time.time()
    while time.time() - start <= timeout_seconds:
        if not _process_alive(pid):
            return {"target": target, "stopped": True, "pid": pid}
        time.sleep(0.2)

    try:
        if os.name == "nt":
            os.kill(pid, signal.SIGKILL)
        else:
            os.killpg(pid, signal.SIGKILL)
    except Exception:
        pass

    return {"target": target, "stopped": not _process_alive(pid), "pid": pid, "forced": True}


def _module_process_status(target: str) -> dict[str, Any]:
    state = _read_module_state(target)
    pid = int(state.get("pid", 0) or 0)
    alive = _process_alive(pid) if pid > 0 else False
    return {
        "pid": pid if pid > 0 else None,
        "alive": alive,
        "log_file": state.get("log_file", str(_module_log_path(target))),
        "started_at": state.get("started_at", ""),
    }


def _module_logs(target: str, tail_lines: int = 80) -> dict[str, Any]:
    log_file = _module_log_path(target)
    if not log_file.exists():
        return {"target": target, "log_file": str(log_file), "lines": []}

    lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    return {"target": target, "log_file": str(log_file), "lines": lines[-max(int(tail_lines), 1) :]}


def _resolve_workflow_state(stage: str | None) -> Any:
    if not stage:
        return None

    from src.modules.messages.workflow import WorkflowState

    normalized = stage.strip().lower().replace("-", "_")
    aliases = {
        "new": WorkflowState.NEW,
        "replied": WorkflowState.REPLIED,
        "reply": WorkflowState.REPLIED,
        "quoted": WorkflowState.QUOTED,
        "quote": WorkflowState.QUOTED,
        "followed": WorkflowState.FOLLOWED,
        "followup": WorkflowState.FOLLOWED,
        "follow_up": WorkflowState.FOLLOWED,
        "ordered": WorkflowState.ORDERED,
        "order": WorkflowState.ORDERED,
        "closed": WorkflowState.CLOSED,
        "close": WorkflowState.CLOSED,
        "manual": WorkflowState.MANUAL,
        "takeover": WorkflowState.MANUAL,
    }
    return aliases.get(normalized)


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

    if action in {"workflow-stats", "workflow-status"}:
        from src.modules.messages.workflow import WorkflowStore

        store = WorkflowStore(db_path=args.workflow_db)
        _json_out(
            {
                "workflow": store.get_workflow_summary(),
                "sla": store.get_sla_summary(window_minutes=args.window_minutes or 1440),
            }
        )
        return

    if action == "workflow-transition":
        from src.modules.messages.workflow import WorkflowStore

        if not args.session_id or not args.stage:
            _json_out({"error": "Specify --session-id and --stage"})
            return

        target_state = _resolve_workflow_state(args.stage)
        if target_state is None:
            _json_out({"error": f"Unknown workflow stage: {args.stage}"})
            return

        store = WorkflowStore(db_path=args.workflow_db)
        ok = store.transition_state(
            session_id=args.session_id,
            to_state=target_state,
            reason="cli_workflow_transition",
            metadata={"source": "cli", "requested_stage": args.stage},
        )
        forced = False
        if not ok and bool(args.force_state):
            ok = store.force_state(
                session_id=args.session_id,
                to_state=target_state,
                reason="cli_workflow_transition_force",
                metadata={"source": "cli", "requested_stage": args.stage, "force_state": True},
            )
            forced = bool(ok)

        _json_out(
            {
                "session_id": args.session_id,
                "target_state": target_state.value,
                "success": bool(ok),
                "forced": forced,
                "session": store.get_session(args.session_id),
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


async def cmd_doctor(args: argparse.Namespace) -> None:
    from src.core.doctor import run_doctor

    report = run_doctor(skip_gateway=bool(args.skip_gateway), skip_quote=bool(args.skip_quote))
    strict = bool(args.strict)
    strict_ready = bool(report.get("ready", False)) and report.get("summary", {}).get("warning_failed", 0) == 0

    output = {
        **report,
        "strict": strict,
        "strict_ready": strict_ready,
    }
    _json_out(output)

    if not output["ready"] or (strict and not strict_ready):
        raise SystemExit(2)


async def cmd_automation(args: argparse.Namespace) -> None:
    from src.modules.messages.notifications import FeishuNotifier
    from src.modules.messages.setup import AutomationSetupService

    action = args.action
    setup_service = AutomationSetupService(config_path=args.config_path or "config/config.yaml")

    if action == "status":
        _json_out(setup_service.status())
        return

    if action == "setup":
        feishu_enabled = bool(args.enable_feishu or str(args.feishu_webhook or "").strip())
        result = setup_service.apply(
            poll_interval_seconds=float(args.poll_interval or 5.0),
            scan_limit=int(args.scan_limit or 20),
            claim_limit=int(args.claim_limit or 10),
            reply_target_seconds=float(args.reply_target_seconds or 3.0),
            feishu_enabled=feishu_enabled,
            feishu_webhook=str(args.feishu_webhook or "").strip(),
            notify_on_start=bool(args.notify_on_start),
            notify_on_alert=not bool(args.disable_notify_on_alert),
            notify_recovery=not bool(args.disable_notify_recovery),
            heartbeat_minutes=int(args.heartbeat_minutes or 30),
        )
        _json_out(result)
        return

    if action == "test-feishu":
        webhook = str(args.feishu_webhook or "").strip() or setup_service.get_feishu_webhook()
        if not webhook:
            _json_out({"error": "No feishu webhook configured. Use --feishu-webhook or run automation setup first."})
            raise SystemExit(2)

        notifier = FeishuNotifier(webhook_url=webhook)
        text = str(args.message or "【闲鱼自动化】飞书通知测试成功")
        ok = await notifier.send_text(text)
        _json_out({"success": ok, "message": text})
        if not ok:
            raise SystemExit(2)
        return

    _json_out({"error": f"Unknown automation action: {action}"})


async def _start_presales_module(args: argparse.Namespace) -> dict[str, Any]:
    from src.core.browser_client import create_browser_client
    from src.modules.messages.service import MessagesService
    from src.modules.messages.workflow import WorkflowWorker

    client = await create_browser_client()
    try:
        service = MessagesService(controller=client)
        worker = WorkflowWorker(
            message_service=service,
            config={
                "db_path": args.workflow_db,
                "poll_interval_seconds": args.interval,
                "scan_limit": args.limit,
                "claim_limit": args.claim_limit,
            },
        )
        if args.mode == "daemon":
            result = await worker.run_forever(
                dry_run=bool(args.dry_run),
                max_loops=args.max_loops,
            )
        else:
            result = await worker.run_once(dry_run=bool(args.dry_run))
        return {"target": "presales", "mode": args.mode, "result": result}
    finally:
        await client.disconnect()


def _init_default_operation_tasks(args: argparse.Namespace) -> dict[str, Any]:
    from src.core.config import get_config
    from src.modules.accounts.scheduler import Scheduler, TaskType

    scheduler = Scheduler()
    created: list[dict[str, Any]] = []

    if not bool(args.init_default_tasks):
        return {"scheduler": scheduler, "created": created}

    tasks = scheduler.list_tasks()
    has_polish = any(t.task_type == TaskType.POLISH for t in tasks)
    has_metrics = any(t.task_type == TaskType.METRICS for t in tasks)

    cfg = get_config().get_section("scheduler", {})
    polish_cfg = cfg.get("polish", {}) if isinstance(cfg.get("polish"), dict) else {}
    metrics_cfg = cfg.get("metrics", {}) if isinstance(cfg.get("metrics"), dict) else {}

    if not args.skip_polish and not has_polish:
        cron_expr = str(args.polish_cron or polish_cfg.get("cron") or "0 9 * * *")
        task = scheduler.create_polish_task(cron_expression=cron_expr, max_items=int(args.polish_max_items or 50))
        created.append({"task_id": task.task_id, "task_type": task.task_type, "name": task.name})

    if not args.skip_metrics and not has_metrics:
        cron_expr = str(args.metrics_cron or metrics_cfg.get("cron") or "0 */4 * * *")
        task = scheduler.create_metrics_task(cron_expression=cron_expr)
        created.append({"task_id": task.task_id, "task_type": task.task_type, "name": task.name})

    return {"scheduler": scheduler, "created": created}


async def _start_operations_module(args: argparse.Namespace) -> dict[str, Any]:
    from src.modules.accounts.scheduler import TaskType

    setup = _init_default_operation_tasks(args)
    scheduler = setup["scheduler"]
    created = setup["created"]

    if args.mode == "once":
        task_results = []
        for task in scheduler.list_tasks(enabled_only=True):
            if args.skip_polish and task.task_type == TaskType.POLISH:
                continue
            if args.skip_metrics and task.task_type == TaskType.METRICS:
                continue
            task_results.append(await scheduler.execute_task(task))

        success = sum(1 for item in task_results if bool(item.get("success", False)))
        return {
            "target": "operations",
            "mode": "once",
            "created_tasks": created,
            "executed_tasks": len(task_results),
            "success_tasks": success,
            "failed_tasks": len(task_results) - success,
            "results": task_results,
        }

    await scheduler.start()
    loops = 0
    try:
        while True:
            loops += 1
            if args.max_loops and loops >= args.max_loops:
                break
            await asyncio.sleep(max(1.0, float(args.interval or 30.0)))
    finally:
        await scheduler.stop()

    return {
        "target": "operations",
        "mode": "daemon",
        "loops": loops,
        "created_tasks": created,
        "status": scheduler.get_scheduler_status(),
    }


async def _run_aftersales_once(args: argparse.Namespace, message_service: Any | None = None) -> dict[str, Any]:
    from src.modules.orders.service import OrderFulfillmentService

    service = OrderFulfillmentService(db_path=args.orders_db or "data/orders.db")
    cases = service.list_orders(
        status="after_sales",
        limit=max(int(args.limit or 20), 1),
        include_manual=bool(args.include_manual),
    )

    details: list[dict[str, Any]] = []
    for case in cases:
        order_id = str(case.get("order_id", ""))
        session_id = str(case.get("session_id", ""))
        issue_type = str(args.issue_type or "delay")
        reply_text = service.generate_after_sales_reply(issue_type=issue_type)

        sent = False
        reason = ""
        if not session_id:
            reason = "missing_session_id"
        elif bool(args.dry_run):
            sent = True
            reason = "dry_run"
        elif message_service is None:
            reason = "message_service_unavailable"
        else:
            sent = await message_service.reply_to_session(session_id, reply_text)
            reason = "sent" if sent else "send_failed"

        service.record_after_sales_followup(
            order_id=order_id,
            issue_type=issue_type,
            reply_text=reply_text,
            sent=sent,
            dry_run=bool(args.dry_run),
            reason=reason,
            session_id=session_id,
        )
        details.append(
            {
                "order_id": order_id,
                "session_id": session_id,
                "manual_takeover": bool(case.get("manual_takeover", False)),
                "issue_type": issue_type,
                "reply_template": reply_text,
                "sent": sent,
                "reason": reason,
            }
        )

    success = sum(1 for item in details if bool(item.get("sent", False)))
    return {
        "target": "aftersales",
        "total_cases": len(cases),
        "success_cases": success,
        "failed_cases": len(cases) - success,
        "dry_run": bool(args.dry_run),
        "details": details,
    }


async def _start_aftersales_module(args: argparse.Namespace) -> dict[str, Any]:
    from src.core.browser_client import create_browser_client
    from src.modules.messages.service import MessagesService
    from src.modules.orders.service import OrderFulfillmentService

    service = OrderFulfillmentService(db_path=args.orders_db or "data/orders.db")
    if args.mode == "once":
        if bool(args.dry_run):
            result = await _run_aftersales_once(args, message_service=None)
        else:
            client = await create_browser_client()
            try:
                message_service = MessagesService(controller=client)
                result = await _run_aftersales_once(args, message_service=message_service)
            finally:
                await client.disconnect()

        return {
            "target": "aftersales",
            "mode": "once",
            "result": result,
            "summary": service.get_summary(),
        }

    loops = 0
    batches: list[dict[str, Any]] = []
    if bool(args.dry_run):
        while True:
            loops += 1
            batch = await _run_aftersales_once(args, message_service=None)
            batches.append(
                {
                    "loop": loops,
                    "total_cases": batch.get("total_cases", 0),
                    "success_cases": batch.get("success_cases", 0),
                    "failed_cases": batch.get("failed_cases", 0),
                }
            )
            if args.max_loops and loops >= args.max_loops:
                break
            await asyncio.sleep(max(1.0, float(args.interval or 30.0)))
    else:
        client = await create_browser_client()
        try:
            message_service = MessagesService(controller=client)
            while True:
                loops += 1
                batch = await _run_aftersales_once(args, message_service=message_service)
                batches.append(
                    {
                        "loop": loops,
                        "total_cases": batch.get("total_cases", 0),
                        "success_cases": batch.get("success_cases", 0),
                        "failed_cases": batch.get("failed_cases", 0),
                    }
                )
                if args.max_loops and loops >= args.max_loops:
                    break
                await asyncio.sleep(max(1.0, float(args.interval or 30.0)))
        finally:
            await client.disconnect()

    return {
        "target": "aftersales",
        "mode": "daemon",
        "loops": loops,
        "batches": batches,
        "summary": service.get_summary(),
    }


async def cmd_module(args: argparse.Namespace) -> None:
    from src.core.doctor import run_doctor
    from src.modules.accounts.scheduler import Scheduler
    from src.modules.messages.workflow import WorkflowStore
    from src.modules.orders.service import OrderFulfillmentService

    action = args.action
    target = args.target

    if action == "check":
        report = run_doctor(
            skip_gateway=bool(args.skip_gateway),
            skip_quote=(target != "presales"),
        )
        summary = _module_check_summary(target=target, doctor_report=report)
        _json_out(summary)
        if bool(args.strict) and not summary["ready"]:
            raise SystemExit(2)
        return

    if action == "status":
        if target == "presales":
            store = WorkflowStore(db_path=args.workflow_db)
            _json_out(
                {
                    "target": target,
                    "process": _module_process_status(target),
                    "workflow": store.get_workflow_summary(),
                    "sla": store.get_sla_summary(window_minutes=args.window_minutes or 1440),
                }
            )
            return

        if target == "aftersales":
            service = OrderFulfillmentService(db_path=args.orders_db or "data/orders.db")
            preview = service.list_orders(
                status="after_sales",
                limit=max(int(args.limit or 20), 1),
                include_manual=True,
            )
            _json_out(
                {
                    "target": target,
                    "process": _module_process_status(target),
                    "summary": service.get_summary(),
                    "recent_after_sales_cases": [
                        {
                            "order_id": item.get("order_id"),
                            "session_id": item.get("session_id"),
                            "manual_takeover": bool(item.get("manual_takeover", False)),
                            "updated_at": item.get("updated_at", ""),
                        }
                        for item in preview
                    ],
                }
            )
            return

        scheduler = Scheduler()
        _json_out(
            {
                "target": target,
                "process": _module_process_status(target),
                "scheduler": scheduler.get_scheduler_status(),
            }
        )
        return

    if action == "start":
        if bool(args.background):
            if args.mode != "daemon":
                _json_out({"error": "background start only supports --mode daemon"})
                raise SystemExit(2)
            _json_out(_start_background_module(target=target, args=args))
            return

        if target == "presales":
            result = await _start_presales_module(args)
        elif target == "operations":
            result = await _start_operations_module(args)
        else:
            result = await _start_aftersales_module(args)
        _json_out(result)
        return

    if action == "stop":
        _json_out(_stop_background_module(target=target, timeout_seconds=float(args.stop_timeout or 6.0)))
        return

    if action == "restart":
        stopped = _stop_background_module(target=target, timeout_seconds=float(args.stop_timeout or 6.0))
        started = _start_background_module(target=target, args=args)
        _json_out({"target": target, "stopped": stopped, "started": started})
        return

    if action == "logs":
        _json_out(_module_logs(target=target, tail_lines=int(args.tail_lines or 80)))
        return

    _json_out({"error": f"Unknown module action: {action}"})


async def cmd_quote(args: argparse.Namespace) -> None:
    from src.core.config import get_config
    from src.modules.quote import CostTableRepository, QuoteSetupService

    action = args.action
    config = get_config()
    quote_cfg = config.get_section("quote", {})

    if action == "health":
        repo = CostTableRepository(
            table_dir=quote_cfg.get("cost_table_dir", "data/quote_costs"),
            include_patterns=quote_cfg.get("cost_table_patterns", ["*.xlsx", "*.csv"]),
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
            table_dir=quote_cfg.get("cost_table_dir", "data/quote_costs"),
            include_patterns=quote_cfg.get("cost_table_patterns", ["*.xlsx", "*.csv"]),
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
        choices=[
            "list-unread",
            "reply",
            "auto-reply",
            "auto-workflow",
            "workflow-stats",
            "workflow-status",
            "workflow-transition",
        ],
    )
    p.add_argument("--limit", type=int, default=20, help="最多处理会话数")
    p.add_argument("--session-id", help="会话 ID（reply 时必填）")
    p.add_argument("--text", help="回复内容（reply 时必填）")
    p.add_argument("--stage", help="工作流目标阶段（workflow-transition 时必填）")
    p.add_argument("--force-state", action="store_true", help="非法迁移时强制写入状态")
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

    # doctor
    p = sub.add_parser("doctor", help="运行系统自检并输出修复建议")
    p.add_argument("--skip-gateway", action="store_true", help="跳过 OpenClaw Gateway 连通性检查")
    p.add_argument("--skip-quote", action="store_true", help="跳过自动报价成本源检查")
    p.add_argument("--strict", action="store_true", help="警告也按失败处理（返回非0）")

    # automation
    p = sub.add_parser("automation", help="自动化推进配置与飞书接入")
    p.add_argument("--action", required=True, choices=["setup", "status", "test-feishu"])
    p.add_argument("--config-path", default="config/config.yaml", help="配置文件路径")
    p.add_argument("--poll-interval", type=float, default=5.0, help="workflow 轮询间隔（秒）")
    p.add_argument("--scan-limit", type=int, default=20, help="每轮扫描会话数")
    p.add_argument("--claim-limit", type=int, default=10, help="每轮最大认领任务数")
    p.add_argument("--reply-target-seconds", type=float, default=3.0, help="自动首响目标时延（秒）")
    p.add_argument("--enable-feishu", action="store_true", help="启用飞书 webhook 通知")
    p.add_argument("--feishu-webhook", default="", help="飞书机器人 webhook URL")
    p.add_argument("--notify-on-start", action="store_true", help="worker 启动时发送通知")
    p.add_argument("--disable-notify-on-alert", action="store_true", help="关闭 SLA 告警通知")
    p.add_argument("--disable-notify-recovery", action="store_true", help="关闭告警恢复通知")
    p.add_argument("--heartbeat-minutes", type=int, default=30, help="心跳通知周期（分钟，0=关闭）")
    p.add_argument("--message", default="【闲鱼自动化】飞书通知测试成功", help="test-feishu 测试消息")

    # module
    p = sub.add_parser("module", help="模块化可用性检查与启动（售前/运营/售后）")
    p.add_argument("--action", required=True, choices=["check", "status", "start", "stop", "restart", "logs"])
    p.add_argument("--target", required=True, choices=["presales", "operations", "aftersales"])
    p.add_argument("--strict", action="store_true", help="check 未通过时返回非0")
    p.add_argument("--mode", choices=["once", "daemon"], default="once", help="start 运行模式")
    p.add_argument("--background", action="store_true", help="start 时后台运行（仅 daemon）")
    p.add_argument("--skip-gateway", action="store_true", help="check 时跳过网关连通性")
    p.add_argument("--window-minutes", type=int, default=1440, help="status 时 SLA 统计窗口（分钟）")
    p.add_argument("--workflow-db", default=None, help="presales workflow 数据库路径")
    p.add_argument("--orders-db", default="data/orders.db", help="aftersales 订单数据库路径")
    p.add_argument("--limit", type=int, default=20, help="presales 扫描会话数 / aftersales 处理工单数")
    p.add_argument("--claim-limit", type=int, default=10, help="presales 每轮认领任务数")
    p.add_argument("--interval", type=float, default=5.0, help="轮询间隔（秒）")
    p.add_argument("--dry-run", action="store_true", help="presales/aftersales 仅生成回复不发送")
    p.add_argument("--issue-type", default="delay", help="aftersales 售后类型：delay/refund/quality")
    p.add_argument("--include-manual", action="store_true", help="aftersales 包含人工接管订单")
    p.add_argument("--max-loops", type=int, default=None, help="daemon 模式下最多循环次数")
    p.add_argument("--init-default-tasks", action="store_true", help="operations 自动初始化默认任务")
    p.add_argument("--skip-polish", action="store_true", help="operations 跳过擦亮任务")
    p.add_argument("--skip-metrics", action="store_true", help="operations 跳过数据任务")
    p.add_argument("--polish-max-items", type=int, default=50, help="默认擦亮任务最大数量")
    p.add_argument("--polish-cron", default="", help="默认擦亮任务 cron")
    p.add_argument("--metrics-cron", default="", help="默认数据任务 cron")
    p.add_argument("--tail-lines", type=int, default=80, help="logs 返回行数")
    p.add_argument("--stop-timeout", type=float, default=6.0, help="stop/restart 等待进程退出超时（秒）")

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
        "doctor": cmd_doctor,
        "automation": cmd_automation,
        "module": cmd_module,
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
