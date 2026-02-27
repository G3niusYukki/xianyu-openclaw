"""
定时任务调度器
Task Scheduler

提供定时任务调度功能
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.core.browser_client import BrowserError, create_browser_client
from src.core.logger import get_logger


class TaskStatus:
    """任务状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType:
    """任务类型"""

    POLISH = "polish"
    PUBLISH = "publish"
    METRICS = "metrics"
    CUSTOM = "custom"


class Task:
    """
    定时任务

    封装任务的基本信息和执行逻辑
    """

    def __init__(
        self,
        task_id: str | None = None,
        task_type: str | None = None,
        cron_expression: str | None = None,
        interval: int | None = None,
        enabled: bool = True,
        params: dict | None = None,
        name: str | None = None,
    ):
        self.task_id = task_id or str(uuid.uuid4())[:8]
        self.task_type = task_type
        self.name = name or f"Task-{self.task_id}"
        self.cron_expression = cron_expression
        self.interval = interval
        self.enabled = enabled
        self.params = params or {}
        self.status = TaskStatus.PENDING
        self.last_run: datetime | None = None
        self.last_result: dict | None = None
        self.created_at = datetime.now().isoformat()
        self.run_count = 0

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "name": self.name,
            "cron_expression": self.cron_expression,
            "interval": self.interval,
            "enabled": self.enabled,
            "params": self.params,
            "status": self.status,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_result": self.last_result,
            "run_count": self.run_count,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """从字典创建"""
        task = cls(
            task_id=data.get("task_id"),
            task_type=data.get("task_type"),
            cron_expression=data.get("cron_expression"),
            interval=data.get("interval"),
            enabled=data.get("enabled", True),
            params=data.get("params", {}),
            name=data.get("name"),
        )
        task.status = data.get("status", TaskStatus.PENDING)
        task.run_count = data.get("run_count", 0)
        task.created_at = data.get("created_at", datetime.now().isoformat())
        if data.get("last_run"):
            task.last_run = datetime.fromisoformat(data["last_run"])
        task.last_result = data.get("last_result")
        return task


class Scheduler:
    """
    任务调度器

    管理定时任务的创建、调度和执行
    """

    def __init__(self):
        self.logger = get_logger()
        self.tasks: dict[str, Task] = {}
        self.running_tasks: dict[str, asyncio.Task] = {}
        self.task_file = Path("data/scheduler_tasks.json")
        self._load_tasks()
        self._scheduler_task: asyncio.Task | None = None

    def _load_tasks(self) -> None:
        """加载任务配置"""
        if self.task_file.exists():
            try:
                with open(self.task_file, encoding="utf-8") as f:
                    data = json.load(f)
                    for task_data in data:
                        task = Task.from_dict(task_data)
                        self.tasks[task.task_id] = task
                self.logger.info(f"Loaded {len(self.tasks)} tasks")
            except Exception as e:
                self.logger.warning(f"Failed to load tasks: {e}")

    def _save_tasks(self) -> None:
        """保存任务配置"""
        self.task_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.task_file, "w", encoding="utf-8") as f:
            json.dump([t.to_dict() for t in self.tasks.values()], f, ensure_ascii=False, indent=2)

    def create_task(
        self,
        task_type: str,
        name: str | None = None,
        cron_expression: str | None = None,
        interval: int | None = None,
        params: dict | None = None,
    ) -> Task:
        """
        创建定时任务

        Args:
            task_type: 任务类型
            name: 任务名称
            cron_expression: Cron表达式
            interval: 执行间隔（秒）
            params: 任务参数

        Returns:
            创建的任务
        """
        task = Task(
            task_id=str(uuid.uuid4())[:8],
            task_type=task_type,
            name=name or f"{task_type.title()}-{datetime.now().strftime('%H%M%S')}",
            cron_expression=cron_expression,
            interval=interval,
            enabled=True,
            params=params or {},
        )

        self.tasks[task.task_id] = task
        self._save_tasks()
        self.logger.info(f"Created task: {task.name} ({task.task_id})")

        return task

    def create_polish_task(self, cron_expression: str = "0 9 * * *", max_items: int = 50) -> Task:
        """
        创建擦亮任务

        Args:
            cron_expression: Cron表达式，默认每天上午9点
            max_items: 最大擦亮数量

        Returns:
            创建的任务
        """
        return self.create_task(
            task_type=TaskType.POLISH,
            name="Auto Polish",
            cron_expression=cron_expression,
            params={"max_items": max_items},
        )

    def create_metrics_task(self, cron_expression: str = "0 */4 * * *", metrics_types: list[str] | None = None) -> Task:
        """
        创建数据采集任务

        Args:
            cron_expression: Cron表达式，默认每4小时
            metrics_types: 采集指标类型

        Returns:
            创建的任务
        """
        return self.create_task(
            task_type=TaskType.METRICS,
            name="Metrics Collection",
            cron_expression=cron_expression,
            params={"metrics_types": metrics_types or ["views", "wants"]},
        )

    def get_task(self, task_id: str) -> Task | None:
        """
        获取任务

        Args:
            task_id: 任务ID

        Returns:
            任务对象
        """
        return self.tasks.get(task_id)

    def list_tasks(self, enabled_only: bool = False) -> list[Task]:
        """
        列出所有任务

        Args:
            enabled_only: 只返回启用的任务

        Returns:
            任务列表
        """
        if enabled_only:
            return [t for t in self.tasks.values() if t.enabled]
        return list(self.tasks.values())

    def update_task(self, task_id: str, **kwargs) -> bool:
        """
        更新任务

        Args:
            task_id: 任务ID
            **kwargs: 更新字段

        Returns:
            是否成功
        """
        task = self.get_task(task_id)
        if not task:
            return False

        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)

        self._save_tasks()
        return True

    def delete_task(self, task_id: str) -> bool:
        """
        删除任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功
        """
        if task_id in self.tasks:
            del self.tasks[task_id]
            self._save_tasks()
            return True
        return False

    async def execute_task(self, task: Task) -> dict[str, Any]:
        """
        执行任务

        Args:
            task: 任务对象

        Returns:
            执行结果
        """
        task.status = TaskStatus.RUNNING
        task.last_run = datetime.now()
        self._save_tasks()

        self.logger.info(f"Executing task: {task.name}")

        result = {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "started_at": datetime.now().isoformat(),
            "success": False,
            "message": "",
        }

        try:
            if task.task_type == TaskType.POLISH:
                result = await self._execute_polish(task.params)
            elif task.task_type == TaskType.PUBLISH:
                result = await self._execute_publish(task.params)
            elif task.task_type == TaskType.METRICS:
                result = await self._execute_metrics(task.params)
            else:
                result["message"] = f"Unknown task type: {task.task_type}"

            task.status = TaskStatus.COMPLETED
            task.run_count += 1

        except Exception as e:
            task.status = TaskStatus.FAILED
            result["success"] = False
            result["message"] = str(e)
            result["error"] = str(e)
            self.logger.error(f"Task {task.name} failed: {e}")

        task.last_result = result
        self._save_tasks()

        return result

    async def _execute_polish(self, params: dict) -> dict[str, Any]:
        """执行擦亮任务"""
        client = None
        try:
            from src.modules.operations.service import OperationsService

            client = await create_browser_client()
            service = OperationsService(controller=client)
            max_items = params.get("max_items", 50)
            result = await service.batch_polish(max_items=max_items)

            return {"success": True, "message": f"Polished {result.get('success', 0)} items", "details": result}
        except BrowserError as e:
            return {
                "success": False,
                "message": "Browser connection failed",
                "error_code": "BROWSER_CONNECT_FAILED",
                "error": str(e),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "error_code": "POLISH_EXECUTION_FAILED"}
        finally:
            if client:
                await client.disconnect()

    async def _execute_publish(self, params: dict) -> dict[str, Any]:
        """执行发布任务"""
        client = None
        try:
            from src.modules.listing.models import Listing
            from src.modules.listing.service import ListingService

            listings_data = params.get("listings", [])
            if not listings_data:
                return {"success": False, "message": "No listings to publish"}

            client = await create_browser_client()
            service = ListingService(controller=client)
            listings = [Listing(**listing) for listing in listings_data]
            results = await service.batch_create_listings(listings)

            success_count = sum(1 for r in results if r.success)

            return {
                "success": True,
                "message": f"Published {success_count}/{len(results)} items",
                "details": [{"id": r.product_id, "success": r.success} for r in results],
            }
        except BrowserError as e:
            return {
                "success": False,
                "message": "Browser connection failed",
                "error_code": "BROWSER_CONNECT_FAILED",
                "error": str(e),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "error_code": "PUBLISH_EXECUTION_FAILED"}
        finally:
            if client:
                await client.disconnect()

    async def _execute_metrics(self, params: dict) -> dict[str, Any]:
        """执行数据采集任务"""
        try:
            from src.modules.analytics.service import AnalyticsService

            service = AnalyticsService()

            return {"success": True, "message": "Metrics collected", "stats": await service.get_dashboard_stats()}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def run_task_now(self, task_id: str) -> dict[str, Any]:
        """
        立即运行任务

        Args:
            task_id: 任务ID

        Returns:
            执行结果
        """
        task = self.get_task(task_id)
        if not task:
            return {"success": False, "message": f"Task not found: {task_id}"}

        if task_id in self.running_tasks:
            return {"success": False, "message": "Task is already running"}

        async def wrapper():
            await self.execute_task(task)
            self.running_tasks.pop(task_id, None)

        self.running_tasks[task_id] = asyncio.create_task(wrapper())
        return {"success": True, "message": f"Task started: {task.name}"}

    def _should_run(self, task: Task) -> bool:
        """检查任务是否应该执行"""
        if not task.enabled:
            return False

        if task.task_id in self.running_tasks:
            return False

        if not task.last_run:
            return True

        if task.cron_expression:
            try:
                next_run = self._get_next_cron_run(task.cron_expression, task.last_run)
                return datetime.now() >= next_run
            except (ValueError, IndexError) as e:
                self.logger.debug(f"Invalid cron expression: {e}")
                return False

        if task.interval:
            next_run = task.last_run + timedelta(seconds=task.interval)
            return datetime.now() >= next_run

        return False

    def _get_next_cron_run(self, cron_expr: str, last_run: datetime) -> datetime:
        """获取下一次Cron执行时间"""
        try:
            parts = cron_expr.split()
            if len(parts) != 5:
                raise ValueError("Invalid cron expression")

            _minute, _hour, _day, _month, _weekday = parts
            next_time = last_run + timedelta(hours=1)

            return next_time
        except (ValueError, IndexError) as e:
            self.logger.debug(f"Error parsing cron expression: {e}")
            return last_run + timedelta(hours=1)

    async def start(self) -> None:
        """启动调度器"""
        self.logger.info("Starting scheduler...")
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        self.logger.info("Scheduler started")

    async def stop(self) -> None:
        """停止调度器"""
        self.logger.info("Stopping scheduler...")
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass

        for task_id in list(self.running_tasks.keys()):
            self.running_tasks[task_id].cancel()

        self.logger.info("Scheduler stopped")

    async def _scheduler_loop(self) -> None:
        """调度器主循环"""
        self.logger.info("Scheduler loop started")

        while True:
            try:
                for task in self.tasks.values():
                    if self._should_run(task):
                        self.logger.info(f"Triggering task: {task.name}")
                        await self.run_task_now(task.task_id)

                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(60)

    def get_scheduler_status(self) -> dict[str, Any]:
        """
        获取调度器状态

        Returns:
            状态信息
        """
        tasks = self.list_tasks()
        running = len([t for t in tasks if t.status == TaskStatus.RUNNING])

        return {
            "total_tasks": len(tasks),
            "enabled_tasks": len([t for t in tasks if t.enabled]),
            "running_tasks": running,
            "tasks": [t.to_dict() for t in tasks],
        }
