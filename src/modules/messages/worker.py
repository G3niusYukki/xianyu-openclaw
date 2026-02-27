"""
消息全流程常驻执行器
Message Workflow Worker
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from pathlib import Path
from typing import Any

from src.core.config import get_config
from src.core.logger import get_logger
from src.modules.messages.service import MessagesService
from src.modules.messages.sla_monitor import WorkflowSlaMonitor


class WorkflowWorker:
    """按固定间隔循环执行 auto_workflow 的常驻 worker。"""

    def __init__(self, messages_service: MessagesService, config: dict[str, Any] | None = None):
        self.messages_service = messages_service
        self.logger = get_logger()

        app_config = get_config()
        self.config = config or app_config.get_section("messages", {})

        self.interval_seconds = self._to_float(
            self.config.get("worker_interval_seconds", 15),
            default=15.0,
            min_value=0.01,
        )
        self.jitter_seconds = self._to_float(self.config.get("worker_jitter_seconds", 1.5), default=1.5, min_value=0.0)
        self.backoff_seconds = self._to_float(
            self.config.get("worker_backoff_seconds", 5),
            default=5.0,
            min_value=0.01,
        )
        self.max_backoff_seconds = self._to_float(
            self.config.get("worker_max_backoff_seconds", 120),
            default=120.0,
            min_value=0.01,
        )
        self.state_path = Path(str(self.config.get("worker_state_path", "data/workflow_worker_state.json")))
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.sla_monitor = WorkflowSlaMonitor(self.config)

        self._stop_event = asyncio.Event()

    @staticmethod
    def _to_float(raw: Any, default: float, min_value: float) -> float:
        try:
            value = float(raw)
            if value < min_value:
                return default
            return value
        except (TypeError, ValueError):
            return default

    def stop(self) -> None:
        """请求停止 worker。"""
        self._stop_event.set()

    def _write_state(self, state: dict[str, Any]) -> None:
        temp_path = self.state_path.with_suffix(f"{self.state_path.suffix}.tmp")
        temp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.state_path)

    def get_runtime_status(self) -> dict[str, Any]:
        """读取 worker 运行状态与 SLA 快照。"""
        state: dict[str, Any] = {}
        if self.state_path.exists():
            try:
                state = json.loads(self.state_path.read_text(encoding="utf-8"))
                if not isinstance(state, dict):
                    state = {}
            except Exception:
                state = {}

        sla = self.sla_monitor.get_snapshot()
        return {
            "worker_state_path": str(self.state_path),
            "worker_state": state,
            "sla_path": str(self.sla_monitor.path),
            "sla": sla,
        }

    async def _sleep_or_stop(self, seconds: float) -> bool:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=max(seconds, 0.0))
            return True
        except TimeoutError:
            return False

    async def run(
        self,
        *,
        limit: int = 20,
        dry_run: bool = False,
        interval_seconds: float | None = None,
        max_cycles: int | None = None,
        max_runtime_seconds: float | None = None,
    ) -> dict[str, Any]:
        """
        启动 worker 主循环。

        Args:
            limit: 每轮处理会话上限
            dry_run: 是否仅演练不发送
            interval_seconds: 覆盖默认执行间隔
            max_cycles: 最大循环次数，None 表示无限
            max_runtime_seconds: 最大运行时长，None 表示无限
        """
        started_at = time.time()
        started_monotonic = time.monotonic()

        interval = self._to_float(interval_seconds, default=self.interval_seconds, min_value=0.01)
        cycles_total = 0
        cycles_success = 0
        cycles_failed = 0
        consecutive_failures = 0
        last_error = ""
        latest_alerts: list[dict[str, Any]] = []

        self.logger.info(
            f"Workflow worker started (limit={limit}, dry_run={dry_run}, interval={interval:.2f}s, max_cycles={max_cycles})"
        )

        while True:
            if self._stop_event.is_set():
                break

            if max_cycles is not None and cycles_total >= max_cycles:
                break

            if max_runtime_seconds is not None:
                if time.monotonic() - started_monotonic >= max_runtime_seconds:
                    break

            cycles_total += 1
            cycle_started = time.time()

            try:
                result = await self.messages_service.auto_workflow(limit=limit, dry_run=dry_run)
                duration_seconds = time.time() - cycle_started
                cycles_success += 1
                consecutive_failures = 0
                last_error = ""
                sla_snapshot = self.sla_monitor.record_cycle(
                    cycle_status="success",
                    duration_seconds=duration_seconds,
                    cycle_result=result,
                    error="",
                )
                latest_alerts = sla_snapshot.get("alerts", []) if isinstance(sla_snapshot, dict) else []

                state = {
                    "status": "running",
                    "last_cycle_status": "success",
                    "last_cycle_at": cycle_started,
                    "cycles_total": cycles_total,
                    "cycles_success": cycles_success,
                    "cycles_failed": cycles_failed,
                    "last_error": "",
                    "last_result_summary": result.get("summary", {}),
                    "alerts": latest_alerts,
                    "updated_at": time.time(),
                }
                self._write_state(state)

                if max_cycles is not None and cycles_total >= max_cycles:
                    break

                delay = interval + (random.uniform(0, self.jitter_seconds) if self.jitter_seconds > 0 else 0.0)
                should_stop = await self._sleep_or_stop(delay)
                if should_stop:
                    break
            except Exception as e:
                cycles_failed += 1
                consecutive_failures += 1
                last_error = str(e)
                self.logger.error(f"Workflow worker cycle failed: {e}")
                duration_seconds = time.time() - cycle_started
                sla_snapshot = self.sla_monitor.record_cycle(
                    cycle_status="failed",
                    duration_seconds=duration_seconds,
                    cycle_result=None,
                    error=last_error,
                )
                latest_alerts = sla_snapshot.get("alerts", []) if isinstance(sla_snapshot, dict) else []

                state = {
                    "status": "running",
                    "last_cycle_status": "failed",
                    "last_cycle_at": cycle_started,
                    "cycles_total": cycles_total,
                    "cycles_success": cycles_success,
                    "cycles_failed": cycles_failed,
                    "last_error": last_error,
                    "alerts": latest_alerts,
                    "updated_at": time.time(),
                }
                self._write_state(state)

                if max_cycles is not None and cycles_total >= max_cycles:
                    break

                backoff = min(self.max_backoff_seconds, self.backoff_seconds * (2 ** max(consecutive_failures - 1, 0)))
                should_stop = await self._sleep_or_stop(backoff)
                if should_stop:
                    break

        ended_at = time.time()
        final_status = {
            "status": "stopped",
            "started_at": started_at,
            "stopped_at": ended_at,
            "cycles_total": cycles_total,
            "cycles_success": cycles_success,
            "cycles_failed": cycles_failed,
            "last_error": last_error,
            "alerts": latest_alerts,
            "updated_at": ended_at,
        }
        self._write_state(final_status)

        runtime_status = self.get_runtime_status()
        return {
            "action": "run_worker",
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started_at)),
            "stopped_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ended_at)),
            "duration_seconds": round(ended_at - started_at, 3),
            "cycles_total": cycles_total,
            "cycles_success": cycles_success,
            "cycles_failed": cycles_failed,
            "last_error": last_error,
            "dry_run": dry_run,
            "limit": limit,
            "interval_seconds": interval,
            "state_path": str(self.state_path),
            "alerts": latest_alerts,
            "sla_summary": (runtime_status.get("sla", {}) or {}).get("summary", {}),
        }
