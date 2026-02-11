"""
闲鱼账号管理技能
Xianyu Accounts Skill

提供多账号管理和定时任务功能
"""

from openclaw.agent.skill import AgentSkill
from typing import Dict, Any, List, Optional
from datetime import datetime


class XianyuAccountsSkill(AgentSkill):
    """
    账号管理技能

    提供多闲鱼账号的统一管理和调度功能
    """

    name = "xianyu-accounts"
    description = "Manage multiple Xianyu accounts, scheduled tasks, and system monitoring"

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        """
        执行账号管理操作

        Args:
            action: 操作类型
            **kwargs: 操作参数
        """
        action_map = {
            "list": self._list_accounts,
            "status": self._get_status,
            "health": self._get_health,
            "switch": self._switch_account,
            "dashboard": self._get_unified_dashboard,
            "create_task": self._create_task,
            "list_tasks": self._list_tasks,
            "run_task": self._run_task,
            "delete_task": self._delete_task,
            "scheduler_status": self._get_scheduler_status,
            "alerts": self._get_alerts,
            "resolve_alert": self._resolve_alert,
            "health_check": self._run_health_check,
            "distribute": self._distribute_publish,
        }

        if action in action_map:
            return await action_map[action](kwargs)
        else:
            return {"status": "error", "message": f"Unknown action: {action}"}

    async def _list_accounts(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        列出所有账号
        """
        try:
            from src.modules.accounts.service import AccountsService

            service = AccountsService()
            accounts = service.get_accounts()

            return {
                "status": "success",
                "action": "list",
                "total": len(accounts),
                "accounts": [
                    {
                        "id": acc.get("id"),
                        "name": acc.get("name"),
                        "enabled": acc.get("enabled"),
                        "priority": acc.get("priority"),
                        "status": acc.get("status"),
                    }
                    for acc in accounts
                ]
            }

        except ImportError:
            return {"status": "success", "action": "list", "accounts": [], "mock": True}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _get_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取指定账号状态
        """
        account_id = params.get("account_id")

        try:
            from src.modules.accounts.service import AccountsService

            service = AccountsService()
            account = service.get_account(account_id)

            if not account:
                return {"status": "error", "message": f"Account not found: {account_id}"}

            health = service.get_account_health(account_id)

            return {
                "status": "success",
                "action": "status",
                "account": {
                    "id": account.get("id"),
                    "name": account.get("name"),
                    "enabled": account.get("enabled"),
                    "priority": account.get("priority"),
                    "status": account.get("status"),
                },
                "health": health
            }

        except ImportError:
            return {"status": "success", "action": "status", "mock": True}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _get_health(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取所有账号健康度
        """
        try:
            from src.modules.accounts.service import AccountsService

            service = AccountsService()
            health_list = service.get_all_accounts_health()

            return {
                "status": "success",
                "action": "health",
                "accounts_health": health_list
            }

        except ImportError:
            return {"status": "success", "action": "health", "mock": True}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _switch_account(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        切换当前账号
        """
        account_id = params.get("account_id")

        if not account_id:
            return {"status": "error", "message": "Account ID required"}

        try:
            from src.modules.accounts.service import AccountsService

            service = AccountsService()
            success = service.set_current_account(account_id)

            if success:
                return {
                    "status": "success",
                    "action": "switch",
                    "account_id": account_id,
                    "message": f"Switched to account: {account_id}"
                }
            else:
                return {"status": "error", "message": f"Failed to switch to: {account_id}"}

        except ImportError:
            return {"status": "success", "action": "switch", "account_id": account_id, "mock": True}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _get_unified_dashboard(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取统一仪表盘
        """
        try:
            from src.modules.accounts.service import AccountsService

            service = AccountsService()
            dashboard = service.get_unified_dashboard()

            return {
                "status": "success",
                "action": "dashboard",
                "data": dashboard
            }

        except ImportError:
            return {"status": "success", "action": "dashboard", "mock": True}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _create_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建定时任务
        """
        task_type = params.get("task_type")
        cron_expression = params.get("cron_expression")
        name = params.get("name")

        if not task_type:
            return {"status": "error", "message": "Task type required"}

        try:
            from src.modules.accounts.scheduler import Scheduler, TaskType

            scheduler = Scheduler()

            if task_type == "polish":
                max_items = params.get("max_items", 50)
                task = scheduler.create_polish_task(
                    cron_expression=cron_expression or "0 9 * * *",
                    max_items=max_items
                )
            elif task_type == "metrics":
                metrics_types = params.get("metrics_types", ["views", "wants"])
                task = scheduler.create_metrics_task(
                    cron_expression=cron_expression or "0 */4 * * *",
                    metrics_types=metrics_types
                )
            elif task_type == "custom":
                task = scheduler.create_task(
                    task_type=TaskType.CUSTOM,
                    name=name,
                    cron_expression=cron_expression,
                    params=params.get("params", {})
                )
            else:
                return {"status": "error", "message": f"Unknown task type: {task_type}"}

            return {
                "status": "success",
                "action": "create_task",
                "task_id": task.task_id,
                "task_type": task.task_type,
                "name": task.name,
                "cron_expression": task.cron_expression,
            }

        except ImportError:
            return {"status": "success", "action": "create_task", "mock": True}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _list_tasks(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        列出定时任务
        """
        try:
            from src.modules.accounts.scheduler import Scheduler

            scheduler = Scheduler()
            tasks = scheduler.list_tasks(enabled_only=params.get("enabled_only", False))

            return {
                "status": "success",
                "action": "list_tasks",
                "total": len(tasks),
                "tasks": [t.to_dict() for t in tasks]
            }

        except ImportError:
            return {"status": "success", "action": "list_tasks", "tasks": [], "mock": True}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _run_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        立即运行任务
        """
        task_id = params.get("task_id")

        if not task_id:
            return {"status": "error", "message": "Task ID required"}

        try:
            from src.modules.accounts.scheduler import Scheduler

            scheduler = Scheduler()
            result = await scheduler.run_task_now(task_id)

            return {
                "status": result.get("success", False) and "success" or "error",
                "action": "run_task",
                "message": result.get("message", "")
            }

        except ImportError:
            return {"status": "success", "action": "run_task", "mock": True}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _delete_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        删除任务
        """
        task_id = params.get("task_id")

        if not task_id:
            return {"status": "error", "message": "Task ID required"}

        try:
            from src.modules.accounts.scheduler import Scheduler

            scheduler = Scheduler()
            success = scheduler.delete_task(task_id)

            return {
                "status": "success" if success else "error",
                "action": "delete_task",
                "task_id": task_id
            }

        except ImportError:
            return {"status": "success", "action": "delete_task", "mock": True}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _get_scheduler_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取调度器状态
        """
        try:
            from src.modules.accounts.scheduler import Scheduler

            scheduler = Scheduler()
            status = scheduler.get_scheduler_status()

            return {
                "status": "success",
                "action": "scheduler_status",
                "data": status
            }

        except ImportError:
            return {"status": "success", "action": "scheduler_status", "mock": True}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _get_alerts(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取活跃告警
        """
        try:
            from src.modules.accounts.monitor import Monitor

            monitor = Monitor()
            level = params.get("level")
            alerts = monitor.get_active_alerts(level)

            summary = monitor.get_alert_summary()

            return {
                "status": "success",
                "action": "alerts",
                "alerts": [a.to_dict() for a in alerts],
                "summary": summary
            }

        except ImportError:
            return {"status": "success", "action": "alerts", "mock": True}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _resolve_alert(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        解除告警
        """
        alert_id = params.get("alert_id")

        if not alert_id:
            return {"status": "error", "message": "Alert ID required"}

        try:
            from src.modules.accounts.monitor import Monitor

            monitor = Monitor()
            success = monitor.resolve_alert(alert_id)

            return {
                "status": "success" if success else "error",
                "action": "resolve_alert",
                "alert_id": alert_id
            }

        except ImportError:
            return {"status": "success", "action": "resolve_alert", "mock": True}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _run_health_check(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        运行健康检查
        """
        try:
            from src.modules.accounts.monitor import HealthChecker

            checker = HealthChecker()
            result = await checker.run_health_check()

            return {
                "status": "success",
                "action": "health_check",
                "result": result
            }

        except ImportError:
            return {"status": "success", "action": "health_check", "mock": True}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _distribute_publish(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        分配发布任务到多个账号
        """
        count = params.get("count", 1)

        try:
            from src.modules.accounts.service import AccountsService

            service = AccountsService()
            distribution = service.distribute_publish(count)

            return {
                "status": "success",
                "action": "distribute",
                "count": count,
                "distribution": [
                    {
                        "account_id": d["account"].get("id"),
                        "name": d["account"].get("name"),
                        "count": d["count"]
                    }
                    for d in distribution
                ]
            }

        except ImportError:
            return {"status": "success", "action": "distribute", "mock": True}
        except Exception as e:
            return {"status": "error", "message": str(e)}
