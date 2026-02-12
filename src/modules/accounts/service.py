"""
账号管理服务
Accounts Management Service

提供多闲鱼账号的统一管理功能
"""

import asyncio
import time
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from pathlib import Path

from src.core.config import get_config
from src.core.logger import get_logger


class AccountStatus:
    """账号状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    MAINTENANCE = "maintenance"


class AccountHealth:
    """账号健康度"""
    GOOD = "good"
    WARNING = "warning"
    BAD = "bad"


class AccountsService:
    """
    账号管理服务

    负责多账号的配置管理、状态监控、健康检查
    """

    def __init__(self, config: Optional[dict] = None):
        """
        初始化账号服务

        Args:
            config: 配置字典
        """
        self.config = config or get_config()
        self.logger = get_logger()

        self.accounts: List[Dict[str, Any]] = []
        self.account_stats: Dict[str, Dict] = {}
        self.current_account_id: Optional[str] = None

        self._load_accounts()
        self._load_account_stats()

    def _load_accounts(self) -> None:
        """加载账号配置"""
        accounts_config = self.config.accounts or []

        self.accounts = []
        for acc in accounts_config:
            account = {
                "id": acc.get("id", ""),
                "name": acc.get("name", acc.get("id", "")),
                "cookie": self._resolve_env(acc.get("cookie", "")),
                "priority": acc.get("priority", 1),
                "enabled": acc.get("enabled", True),
                "status": AccountStatus.ACTIVE,
                "last_login": None,
                "created_at": datetime.now().isoformat(),
            }
            self.accounts.append(account)

        if not self.accounts:
            self.logger.warning("No accounts configured")

    def _resolve_env(self, value: str) -> str:
        """解析环境变量引用"""
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            env_key = value[2:-1]
            import os
            return os.getenv(env_key, value)
        return value

    def _mask_sensitive_data(self, data: str, show_chars: int = 5) -> str:
        """
        敏感数据脱敏

        Args:
            data: 原始数据
            show_chars: 首尾显示的字符数

        Returns:
            脱敏后的数据
        """
        if not data or len(data) < show_chars * 2:
            return "****"
        return f"{data[:show_chars]}...{data[-show_chars:]}"

    def _load_account_stats(self) -> None:
        """加载账号统计"""
        stats_file = Path("data/account_stats.json")
        if stats_file.exists():
            try:
                with open(stats_file, 'r', encoding='utf-8') as f:
                    self.account_stats = json.load(f)
            except Exception as e:
                self.logger.warning(f"Failed to load account stats: {e}")
                self.account_stats = {}

    def _save_account_stats(self) -> None:
        """保存账号统计"""
        stats_file = Path("data/account_stats.json")
        stats_file.parent.mkdir(parents=True, exist_ok=True)
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(self.account_stats, f, ensure_ascii=False, indent=2)

    def get_accounts(self, enabled_only: bool = True, mask_sensitive: bool = True) -> List[Dict[str, Any]]:
        """
        获取账号列表

        Args:
            enabled_only: 只返回启用的账号
            mask_sensitive: 是否脱敏敏感信息

        Returns:
            账号列表
        """
        accounts = [acc for acc in self.accounts if not enabled_only or acc.get("enabled", True)]
        if mask_sensitive:
            accounts = [
                {**acc, "cookie": self._mask_sensitive_data(acc.get("cookie", ""))}
                for acc in accounts
            ]
        return accounts

    def get_account(self, account_id: str, mask_sensitive: bool = True) -> Optional[Dict[str, Any]]:
        """
        获取指定账号

        Args:
            account_id: 账号ID
            mask_sensitive: 是否脱敏敏感信息

        Returns:
            账号信息，不存在返回None
        """
        for acc in self.accounts:
            if acc.get("id") == account_id:
                account_dict = acc.copy()
                if mask_sensitive and "cookie" in account_dict:
                    account_dict["cookie"] = self._mask_sensitive_data(
                        account_dict["cookie"]
                    )
                return account_dict
        return None

    def set_current_account(self, account_id: str) -> bool:
        """
        设置当前账号

        Args:
            account_id: 账号ID

        Returns:
            是否成功
        """
        account = self.get_account(account_id)
        if account:
            self.current_account_id = account_id
            self.logger.info(f"Switched to account: {account.get('name')}")
            return True
        return False

    def get_current_account(self) -> Optional[Dict[str, Any]]:
        """
        获取当前账号

        Returns:
            当前账号信息
        """
        if self.current_account_id:
            return self.get_account(self.current_account_id)

        accounts = self.get_accounts()
        if accounts:
            account = min(accounts, key=lambda x: x.get("priority", 1))
            self.current_account_id = account.get("id")
            return account
        return None

    def get_cookie(self, account_id: Optional[str] = None) -> Optional[str]:
        """
        获取账号Cookie（原始值，不脱敏）

        Args:
            account_id: 账号ID，不指定使用当前账号

        Returns:
            Cookie字符串
        """
        account_id = account_id or self.current_account_id
        for acc in self.accounts:
            if acc.get("id") == account_id:
                return acc.get("cookie")
        return None

    def add_account(self, account_id: str, cookie: str, name: Optional[str] = None,
                    priority: int = 1) -> bool:
        """
        添加账号

        Args:
            account_id: 账号ID
            cookie: 登录Cookie
            name: 账号名称
            priority: 优先级

        Returns:
            是否成功
        """
        for acc in self.accounts:
            if acc.get("id") == account_id:
                self.logger.warning(f"Account {account_id} already exists")
                return False

        self.accounts.append({
            "id": account_id,
            "name": name or account_id,
            "cookie": cookie,
            "priority": priority,
            "enabled": True,
            "status": AccountStatus.ACTIVE,
            "created_at": datetime.now().isoformat(),
        })

        self.account_stats[account_id] = {
            "total_published": 0,
            "total_polished": 0,
            "total_errors": 0,
            "last_operation": None,
            "health_score": 100,
        }
        self._save_account_stats()

        self.logger.info(f"Added account: {account_id}")
        return True

    def remove_account(self, account_id: str) -> bool:
        """
        移除账号

        Args:
            account_id: 账号ID

        Returns:
            是否成功
        """
        for i, acc in enumerate(self.accounts):
            if acc.get("id") == account_id:
                self.accounts.pop(i)
                self.account_stats.pop(account_id, None)
                self._save_account_stats()
                self.logger.info(f"Removed account: {account_id}")
                return True
        return False

    def disable_account(self, account_id: str) -> bool:
        """
        禁用账号

        Args:
            account_id: 账号ID

        Returns:
            是否成功
        """
        account = self.get_account(account_id)
        if account:
            account["enabled"] = False
            account["status"] = AccountStatus.MAINTENANCE
            self.logger.info(f"Disabled account: {account_id}")
            return True
        return False

    def enable_account(self, account_id: str) -> bool:
        """
        启用账号

        Args:
            account_id: 账号ID

        Returns:
            是否成功
        """
        account = self.get_account(account_id)
        if account:
            account["enabled"] = True
            account["status"] = AccountStatus.ACTIVE
            self.logger.info(f"Enabled account: {account_id}")
            return True
        return False

    def get_next_account(self) -> Optional[Dict[str, Any]]:
        """
        获取下一个账号（按优先级轮询）

        Returns:
            下一个账号信息
        """
        accounts = self.get_accounts()
        if not accounts:
            return None

        current_index = 0
        if self.current_account_id:
            for i, acc in enumerate(accounts):
                if acc.get("id") == self.current_account_id:
                    current_index = i
                    break

        next_index = (current_index + 1) % len(accounts)
        next_account = accounts[next_index]

        self.current_account_id = next_account.get("id")
        return next_account

    def update_account_stats(self, account_id: str, operation: str,
                           success: bool = True) -> None:
        """
        更新账号统计

        Args:
            account_id: 账号ID
            operation: 操作类型
            success: 是否成功
        """
        if account_id not in self.account_stats:
            self.account_stats[account_id] = {
                "total_published": 0,
                "total_polished": 0,
                "total_errors": 0,
                "last_operation": None,
                "health_score": 100,
            }

        stats = self.account_stats[account_id]
        stats["last_operation"] = datetime.now().isoformat()

        if operation == "publish":
            stats["total_published"] += 1
        elif operation == "polish":
            stats["total_polished"] += 1
        elif operation == "error":
            stats["total_errors"] += 1

        error_rate = stats["total_errors"] / max(stats["total_published"] + stats["total_polished"], 1)
        stats["health_score"] = max(0, 100 - error_rate * 100)

        self._save_account_stats()

    def get_account_health(self, account_id: str) -> Dict[str, Any]:
        """
        获取账号健康度

        Args:
            account_id: 账号ID

        Returns:
            健康度信息
        """
        stats = self.account_stats.get(account_id, {})
        health_score = stats.get("health_score", 100)

        if health_score >= 80:
            health = AccountHealth.GOOD
        elif health_score >= 50:
            health = AccountHealth.WARNING
        else:
            health = AccountHealth.BAD

        return {
            "account_id": account_id,
            "health_score": health_score,
            "health": health,
            "total_published": stats.get("total_published", 0),
            "total_polished": stats.get("total_polished", 0),
            "total_errors": stats.get("total_errors", 0),
            "last_operation": stats.get("last_operation"),
        }

    def get_all_accounts_health(self) -> List[Dict[str, Any]]:
        """
        获取所有账号健康度

        Returns:
            账号健康度列表
        """
        return [self.get_account_health(acc["id"]) for acc in self.accounts]

    def refresh_cookie(self, account_id: str, new_cookie: str) -> bool:
        """
        刷新账号Cookie

        Args:
            account_id: 账号ID
            new_cookie: 新Cookie

        Returns:
            是否成功
        """
        account = self.get_account(account_id)
        if account:
            account["cookie"] = new_cookie
            account["last_login"] = datetime.now().isoformat()
            self.logger.info(f"Refreshed cookie for account: {account_id}")
            return True
        return False

    def validate_cookie(self, account_id: str) -> bool:
        """
        验证Cookie有效性

        Args:
            account_id: 账号ID

        Returns:
            Cookie是否有效
        """
        cookie = self.get_cookie(account_id)
        if not cookie:
            return False

        if len(cookie) < 50:
            return False

        account = self.get_account(account_id)
        if account:
            last_login = account.get("last_login")
            if last_login:
                login_time = datetime.fromisoformat(last_login)
                if datetime.now() - login_time > timedelta(days=7):
                    self.logger.warning(f"Cookie may be expired for account: {account_id}")
                    return False

        return True

    def get_unified_dashboard(self) -> Dict[str, Any]:
        """
        获取统一仪表盘

        Returns:
            所有账号的汇总数据
        """
        accounts = self.get_accounts()

        total_products = 0
        active_products = 0
        total_views = 0
        total_wants = 0

        for acc in accounts:
            stats = self.account_stats.get(acc["id"], {})
            total_products += stats.get("total_published", 0)
            total_views += stats.get("total_views", 0)
            total_wants += stats.get("total_wants", 0)

        return {
            "total_accounts": len(accounts),
            "active_accounts": len([a for a in accounts if a.get("enabled", True)]),
            "total_products": total_products,
            "total_views": total_views,
            "total_wants": total_wants,
            "accounts_health": self.get_all_accounts_health(),
        }

    def distribute_publish(self, count: int = 1) -> List[Dict[str, Any]]:
        """
        分配发布任务到多个账号

        Args:
            count: 发布数量

        Returns:
            账号分配列表
        """
        accounts = self.get_accounts()
        if not accounts:
            return []

        distribution = []
        per_account = max(1, count // len(accounts))

        for i, acc in enumerate(accounts):
            remaining = count - sum(d.get("count", 0) for d in distribution)
            if remaining <= 0:
                break
            distribution.append({
                "account": acc,
                "count": min(per_account + (1 if i < remaining % len(accounts) else 0), remaining)
            })

        return distribution
