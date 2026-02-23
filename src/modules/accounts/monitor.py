"""
异常监控与告警系统
Monitoring and Alert System

提供异常监控、告警通知和自动恢复功能
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum

from src.core.config import get_config
from src.core.logger import get_logger


class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertChannel(Enum):
    """告警渠道"""
    LOG = "log"
    FILE = "file"
    WEBHOOK = "webhook"


class Alert:
    """
    告警信息
    """

    def __init__(self, alert_id: str = None, level: str = AlertLevel.INFO.value,
                 title: str = "", message: str = "", source: str = "",
                 details: Dict = None, auto_resolve: bool = False):
        self.alert_id = alert_id or f"alert_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.level = level
        self.title = title
        self.message = message
        self.source = source
        self.details = details or {}
        self.auto_resolve = auto_resolve
        self.status = "active"
        self.created_at = datetime.now().isoformat()
        self.resolved_at: Optional[str] = None

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "alert_id": self.alert_id,
            "level": self.level,
            "title": self.title,
            "message": self.message,
            "source": self.source,
            "details": self.details,
            "auto_resolve": self.auto_resolve,
            "status": self.status,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }


class Monitor:
    """
    监控管理器

    负责异常监控、告警管理和自动恢复
    """

    def __init__(self, config: Optional[dict] = None):
        """
        初始化监控器

        Args:
            config: 配置字典
        """
        self.config = config or get_config()
        self.logger = get_logger()

        self._alerts: List[Alert] = []
        self._alert_callbacks: List[Callable] = []
        self.alert_file = Path("data/alerts.json")

        self._alerts_lock = asyncio.Lock()
        self._file_lock = asyncio.Lock()

        self._load_alerts()

        self.monitoring_rules = self._default_rules()
        self.auto_recovery_actions = self._default_recovery_actions()

    def _default_rules(self) -> Dict[str, Any]:
        """默认监控规则"""
        return {
            "browser_connection": {
                "max_failures": 3,
                "window_minutes": 10,
                "level": AlertLevel.ERROR,
            },
            "publish_failure": {
                "max_failures": 5,
                "window_minutes": 60,
                "level": AlertLevel.WARNING,
            },
            "account_locked": {
                "max_failures": 1,
                "window_minutes": 0,
                "level": AlertLevel.CRITICAL,
            },
            "rate_limit": {
                "max_failures": 10,
                "window_minutes": 5,
                "level": AlertLevel.WARNING,
            },
        }

    def _default_recovery_actions(self) -> Dict[str, List[Callable]]:
        """默认恢复动作"""
        return {
            "browser_connection": [
                self._action_reconnect_browser,
            ],
            "publish_failure": [
                self._action_wait_and_retry,
            ],
            "rate_limit": [
                self._action_wait_longer,
            ],
        }

    def _load_alerts(self) -> None:
        """加载历史告警"""
        if self.alert_file.exists():
            try:
                with open(self.alert_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._alerts = [Alert(**a) for a in data]
                self.logger.info(f"Loaded {len(self._alerts)} alerts")
            except Exception as e:
                self.logger.warning(f"Failed to load alerts: {e}")
                self._alerts = []

    async def _save_alerts(self) -> None:
        """保存告警（异步版本，使用锁）"""
        async with self._file_lock:
            self.alert_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.alert_file, 'w', encoding='utf-8') as f:
                json.dump([a.to_dict() for a in self._alerts], f, ensure_ascii=False, indent=2)

    def _save_alerts_sync(self) -> None:
        """保存告警（同步版本，不使用锁，用于__init__）"""
        self.alert_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.alert_file, 'w', encoding='utf-8') as f:
            json.dump([a.to_dict() for a in self._alerts], f, ensure_ascii=False, indent=2)

    def register_callback(self, callback: Callable[[Alert], None]) -> None:
        """
        注册告警回调

        Args:
            callback: 回调函数
        """
        self.alert_callbacks.append(callback)

    async def _trigger_callbacks(self, alert: Alert) -> None:
        """触发回调"""
        for callback in self.alert_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(alert)
                else:
                    callback(alert)
            except Exception as e:
                self.logger.error(f"Alert callback error: {e}")

    async def raise_alert(self, alert_type: str, title: str, message: str,
                    source: str = "", details: Dict = None,
                    auto_resolve: bool = False) -> Alert:
        """
        触发告警

        Args:
            alert_type: 告警类型
            title: 告警标题
            message: 告警消息
            source: 来源
            details: 详细信息
            auto_resolve: 是否自动恢复

        Returns:
            告警对象
        """
        rule = self.monitoring_rules.get(alert_type, {})
        level = rule.get("level", AlertLevel.INFO.value)

        alert = Alert(
            alert_id=f"alert_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            level=level.value if isinstance(level, AlertLevel) else level,
            title=title,
            message=message,
            source=source,
            details=details or {},
            auto_resolve=auto_resolve,
        )

        async with self._alerts_lock:
            self._alerts.append(alert)

        await self._save_alerts()

        self.logger.warning(f"[{alert.level.upper()}] {title}: {message}")

        asyncio.create_task(self._trigger_callbacks(alert))

        if alert.auto_resolve:
            asyncio.create_task(self._auto_resolve_alert(alert))

        return alert

    async def _auto_resolve_alert(self, alert: Alert) -> None:
        """自动恢复告警"""
        await asyncio.sleep(300)

        async with self._alerts_lock:
            for a in self._alerts:
                if a.alert_id == alert.alert_id:
                    a.status = "resolved"
                    a.resolved_at = datetime.now().isoformat()
                    alert = a
                    break

        await self._save_alerts()

        self.logger.info(f"Auto-resolved alert: {alert.alert_id}")

    async def check_condition(self, condition_type: str, check_func: Callable,
                            context: Dict = None) -> None:
        """
        检查条件并触发告警

        Args:
            condition_type: 条件类型
            check_func: 检查函数
            context: 上下文
        """
        rule = self.monitoring_rules.get(condition_type)
        if not rule:
            return

        try:
            should_alert = await check_func(context) if asyncio.iscoroutinefunction(check_func) else check_func(context)

            if should_alert:
                recent_failures = self._count_recent_failures(condition_type, rule.get("window_minutes", 10))

                if recent_failures >= rule.get("max_failures", 3):
                    await self.raise_alert(
                        alert_type=condition_type,
                        title=f"Multiple {condition_type} failures detected",
                        message=f"Failed {recent_failures} times in last {rule.get('window_minutes')} minutes",
                        source=condition_type,
                        details={
                            "condition_type": condition_type,
                            "failure_count": recent_failures,
                            "window_minutes": rule.get("window_minutes"),
                            **(context or {})
                        },
                        auto_resolve=True
                    )

        except Exception as e:
            self.logger.error(f"Condition check error: {e}")

    def _count_recent_failures(self, condition_type: str, window_minutes: int) -> int:
        """计算近期失败次数"""
        window_start = datetime.now() - timedelta(minutes=window_minutes)
        return len([
            a for a in self._alerts
            if a.source == condition_type
            and a.status == "active"
            and datetime.fromisoformat(a.created_at) >= window_start
        ])

    async def _action_reconnect_browser(self, alert: Alert) -> None:
        """重新连接浏览器"""
        self.logger.info("Attempting to reconnect browser...")
        try:
            from src.core.browser_client import BrowserClient

            client = BrowserClient()
            connected = await client.connect()

            if connected:
                self.logger.info("Browser reconnected successfully")
            else:
                self.logger.error("Failed to reconnect browser")

        except Exception as e:
            self.logger.error(f"Browser reconnection error: {e}")

    async def _action_wait_and_retry(self, alert: Alert) -> None:
        """等待后重试"""
        self.logger.info("Waiting before retry...")
        await asyncio.sleep(300)

    async def _action_wait_longer(self, alert: Alert) -> None:
        """等待更长时间"""
        self.logger.info("Waiting longer due to rate limiting...")
        await asyncio.sleep(1800)

    async def resolve_alert(self, alert_id: str) -> bool:
        """
        手动解除告警

        Args:
            alert_id: 告警ID

        Returns:
            是否成功
        """
        async with self._alerts_lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id:
                    alert.status = "resolved"
                    alert.resolved_at = datetime.now().isoformat()
                    await self._save_alerts()
                    return True
        return False

    async def get_active_alerts(self, level: str = None) -> List[Alert]:
        """
        获取活跃告警

        Args:
            level: 级别过滤

        Returns:
            告警列表
        """
        async with self._alerts_lock:
            alerts = [a for a in self._alerts if a.status == "active"]
        if level:
            alerts = [a for a in alerts if a.level == level]
        return alerts

    async def get_alert_summary(self) -> Dict[str, Any]:
        """
        获取告警摘要

        Returns:
            告警统计
        """
        async with self._alerts_lock:
            active = [a for a in self._alerts if a.status == "active"]
            resolved = [a for a in self._alerts if a.status == "resolved"]

            by_level = {}
            for alert in active:
                by_level[alert.level] = by_level.get(alert.level, 0) + 1

            return {
                "total_alerts": len(self._alerts),
                "active_alerts": len(active),
                "resolved_alerts": len(resolved),
                "by_level": by_level,
                "recent_alerts": [a.to_dict() for a in active[-10:]],
            }

    async def cleanup_old_alerts(self, days: int = 30) -> int:
        """
        清理旧告警

        Args:
            days: 保留天数

        Returns:
            清理数量
        """
        cutoff = datetime.now() - timedelta(days=days)
        old_count = 0

        async with self._alerts_lock:
            old_count = len(self._alerts)
            self._alerts = [
                a for a in self._alerts
                if a.status == "active" or datetime.fromisoformat(a.created_at) >= cutoff
            ]
            old_count = old_count - len(self._alerts)

        await self._save_alerts()
        return old_count


class HealthChecker:
    """
    健康检查器

    定期检查系统各组件健康状态
    """

    def __init__(self):
        self.logger = get_logger()
        self.monitor = Monitor()
        self.last_check: Optional[datetime] = None
        self.check_interval = 300

    async def check_browser_connection(self) -> bool:
        """检查浏览器连接"""
        try:
            from src.core.browser_client import BrowserClient

            client = BrowserClient()
            connected = await client.connect()

            if not connected:
                self.monitor.raise_alert(
                    alert_type="browser_connection",
                    title="Browser connection failed",
                    message="Cannot connect to OpenClaw browser",
                    source="health_check",
                )

            return connected

        except Exception as e:
            self.monitor.raise_alert(
                alert_type="browser_connection",
                title="Browser connection error",
                message=str(e),
                source="health_check",
            )
            return False

    async def check_account_status(self) -> List[Dict]:
        """检查账号状态"""
        try:
            from src.modules.accounts.service import AccountsService

            service = AccountsService()
            accounts = service.get_accounts()

            issues = []
            for acc in accounts:
                if not service.validate_cookie(acc["id"]):
                    issues.append({
                        "account_id": acc["id"],
                        "issue": "Invalid cookie",
                        "severity": "high"
                    })

            if issues:
                self.monitor.raise_alert(
                    alert_type="account_status",
                    title="Account status issues detected",
                    message=f"{len(issues)} accounts have issues",
                    source="health_check",
                    details={"issues": issues},
                )

            return issues

        except Exception as e:
            self.logger.error(f"Account check error: {e}")
            return []

    async def run_health_check(self) -> Dict[str, Any]:
        """
        运行健康检查

        Returns:
            检查结果
        """
        self.last_check = datetime.now()
        self.logger.info("Running health check...")

        results = {
            "timestamp": self.last_check.isoformat(),
            "checks": {},
        }

        results["checks"]["browser"] = {
            "status": "healthy" if await self.check_browser_connection() else "unhealthy",
        }

        account_issues = await self.check_account_status()
        results["checks"]["accounts"] = {
            "status": "healthy" if not account_issues else "warning",
            "issues": account_issues,
        }

        return results
