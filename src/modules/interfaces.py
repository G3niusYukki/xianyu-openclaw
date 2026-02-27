"""
服务接口抽象层
Service Interface Layer

定义所有服务的抽象接口，实现依赖倒置原则
"""

from abc import ABC, abstractmethod
from typing import Any


class IListingService(ABC):
    """商品上架领域能力接口定义。"""

    @abstractmethod
    async def create_listing(self, listing: Any, account_id: str | None = None) -> Any:
        """
        创建并发布单个商品

        Args:
            listing: 商品信息对象
            account_id: 账号标识

        Returns:
            PublishResult: 发布结果
        """
        pass

    @abstractmethod
    async def batch_create_listings(
        self, listings: list[Any], account_id: str | None = None, delay_range: tuple = (5, 10)
    ) -> list[Any]:
        """
        批量发布商品

        Args:
            listings: 商品列表
            account_id: 账号标识
            delay_range: 发布间隔时间范围

        Returns:
            List[PublishResult]: 每个商品的发布结果
        """
        pass

    @abstractmethod
    async def update_listing(self, product_id: str, updates: dict[str, Any]) -> bool:
        """
        更新商品信息

        Args:
            product_id: 商品ID
            updates: 更新字段字典

        Returns:
            是否成功
        """
        pass

    @abstractmethod
    async def delete_listing(self, product_id: str) -> bool:
        """
        删除商品

        Args:
            product_id: 商品ID

        Returns:
            是否成功
        """
        pass

    @abstractmethod
    async def get_my_listings(self, limit: int = 50) -> list[dict[str, Any]]:
        """
        获取我的商品列表

        Args:
            limit: 返回数量限制

        Returns:
            商品列表
        """
        pass


class IContentService(ABC):
    """商品文案生成与优化能力接口定义。"""

    @abstractmethod
    def generate_title(self, product_name: str, features: list[str], category: str = "General") -> str:
        """
        生成闲鱼商品标题

        Args:
            product_name: 商品名称
            features: 商品特点列表
            category: 商品分类

        Returns:
            生成的标题
        """
        pass

    @abstractmethod
    def generate_description(
        self, product_name: str, condition: str, reason: str, tags: list[str], extra_info: str | None = None
    ) -> str:
        """
        生成闲鱼商品描述文案

        Args:
            product_name: 商品名称
            condition: 成色描述
            reason: 转手原因
            tags: 标签列表
            extra_info: 额外信息

        Returns:
            生成的描述文案
        """
        pass

    @abstractmethod
    def generate_listing_content(self, product_info: dict[str, Any]) -> dict[str, Any]:
        """
        生成完整商品发布内容

        Args:
            product_info: 商品信息字典

        Returns:
            包含title和description的字典
        """
        pass

    @abstractmethod
    def optimize_title(self, current_title: str, category: str = "General") -> str:
        """
        优化现有标题

        Args:
            current_title: 当前标题
            category: 商品分类

        Returns:
            优化后的标题
        """
        pass


class IMediaService(ABC):
    """媒体处理与图片规范化能力接口定义。"""

    @abstractmethod
    def resize_image_for_xianyu(self, image_path: str, output_path: str | None = None) -> str:
        """
        调整图片尺寸以符合闲鱼规范

        Args:
            image_path: 输入图片路径
            output_path: 输出路径

        Returns:
            处理后的图片路径
        """
        pass

    @abstractmethod
    def add_watermark(
        self, image_path: str, output_path: str | None = None, text: str | None = None, position: str = "bottom-right"
    ) -> str:
        """
        添加文字水印

        Args:
            image_path: 输入图片路径
            output_path: 输出路径
            text: 水印文字
            position: 位置

        Returns:
            处理后的图片路径
        """
        pass

    @abstractmethod
    def batch_process_images(
        self, image_paths: list[str], output_dir: str | None = None, add_watermark: bool = True
    ) -> list[str]:
        """
        批量处理图片

        Args:
            image_paths: 图片路径列表
            output_dir: 输出目录
            add_watermark: 是否添加水印

        Returns:
            处理后的图片路径列表
        """
        pass

    @abstractmethod
    def compress_image(self, image_path: str, output_path: str | None = None, quality: int = 85) -> str:
        """
        压缩图片

        Args:
            image_path: 输入图片路径
            output_path: 输出路径
            quality: 质量

        Returns:
            处理后的图片路径
        """
        pass

    @abstractmethod
    def validate_image(self, image_path: str) -> tuple:
        """
        验证图片格式和大小

        Args:
            image_path: 图片路径

        Returns:
            (是否有效, 错误信息)
        """
        pass


class IOperationsService(ABC):
    """店铺运营动作能力接口定义。"""

    @abstractmethod
    async def batch_polish(self, max_items: int = 50) -> dict[str, Any]:
        """
        批量擦亮商品

        Args:
            max_items: 最大擦亮数量

        Returns:
            擦亮结果
        """
        pass

    @abstractmethod
    async def batch_update_price(self, updates: list[dict[str, Any]]) -> dict[str, Any]:
        """
        批量更新价格

        Args:
            updates: 更新列表，格式为 [{"product_id": "xxx", "price": 100}, ...]

        Returns:
            更新结果
        """
        pass

    @abstractmethod
    async def batch_delist(self, product_ids: list[str], reason: str = "") -> dict[str, Any]:
        """
        批量下架商品

        Args:
            product_ids: 商品ID列表
            reason: 下架原因

        Returns:
            下架结果
        """
        pass

    @abstractmethod
    async def get_product_stats(self, product_id: str) -> dict[str, Any]:
        """
        获取商品统计数据

        Args:
            product_id: 商品ID

        Returns:
            商品统计数据
        """
        pass


class IAnalyticsService(ABC):
    """数据采集、分析与报表能力接口定义。"""

    @abstractmethod
    async def log_operation(
        self,
        operation_type: str,
        product_id: str | None = None,
        account_id: str | None = None,
        details: dict | None = None,
        status: str = "success",
        error_message: str | None = None,
    ) -> int:
        """
        记录操作日志

        Args:
            operation_type: 操作类型
            product_id: 商品ID
            account_id: 账号ID
            details: 详细信息
            status: 状态
            error_message: 错误信息

        Returns:
            日志ID
        """
        pass

    @abstractmethod
    async def get_dashboard_stats(self) -> dict[str, Any]:
        """
        获取仪表盘统计

        Returns:
            统计数据
        """
        pass

    @abstractmethod
    async def get_trend_data(self, metric: str = "views", days: int = 30) -> list[dict[str, Any]]:
        """
        获取趋势数据

        Args:
            metric: 指标类型
            days: 天数

        Returns:
            趋势数据列表
        """
        pass

    @abstractmethod
    async def export_data(self, data_type: str = "products", format: str = "csv", filepath: str | None = None) -> str:
        """
        导出数据

        Args:
            data_type: 数据类型
            format: 导出格式
            filepath: 文件路径

        Returns:
            导出文件路径
        """
        pass


class IAccountsService(ABC):
    """账号管理与健康状态能力接口定义。"""

    @abstractmethod
    def get_accounts(self, enabled_only: bool = True, mask_sensitive: bool = True) -> list[dict[str, Any]]:
        """
        获取账号列表

        Args:
            enabled_only: 只返回启用的账号
            mask_sensitive: 是否脱敏敏感信息

        Returns:
            账号列表
        """
        pass

    @abstractmethod
    def get_account(self, account_id: str, mask_sensitive: bool = True) -> dict[str, Any] | None:
        """
        获取指定账号

        Args:
            account_id: 账号ID
            mask_sensitive: 是否脱敏敏感信息

        Returns:
            账号信息
        """
        pass

    @abstractmethod
    def get_cookie(self, account_id: str | None = None) -> str | None:
        """
        获取账号Cookie

        Args:
            account_id: 账号ID

        Returns:
            Cookie字符串
        """
        pass

    @abstractmethod
    def set_current_account(self, account_id: str) -> bool:
        """
        设置当前账号

        Args:
            account_id: 账号ID

        Returns:
            是否成功
        """
        pass

    @abstractmethod
    def get_current_account(self) -> dict[str, Any] | None:
        """
        获取当前账号

        Returns:
            当前账号信息
        """
        pass

    @abstractmethod
    def update_account_stats(self, account_id: str, operation: str, success: bool = True) -> None:
        """
        更新账号统计

        Args:
            account_id: 账号ID
            operation: 操作类型
            success: 是否成功
        """
        pass

    @abstractmethod
    def get_account_health(self, account_id: str) -> dict[str, Any]:
        """
        获取账号健康度

        Args:
            account_id: 账号ID

        Returns:
            健康度信息
        """
        pass


class ISchedulerService(ABC):
    """定时任务调度能力接口定义。"""

    @abstractmethod
    def create_task(
        self,
        task_type: str,
        name: str | None = None,
        cron_expression: str | None = None,
        interval: int | None = None,
        params: dict | None = None,
    ) -> Any:
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
        pass

    @abstractmethod
    async def execute_task(self, task: Any) -> dict[str, Any]:
        """
        执行任务

        Args:
            task: 任务对象

        Returns:
            执行结果
        """
        pass

    @abstractmethod
    async def start(self) -> None:
        """
        启动调度器

        Returns:
            None
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """
        停止调度器

        Returns:
            None
        """
        pass

    @abstractmethod
    def get_scheduler_status(self) -> dict[str, Any]:
        """
        获取调度器状态

        Returns:
            状态信息
        """
        pass


class IMonitorService(ABC):
    """异常监控与告警能力接口定义。"""

    @abstractmethod
    async def raise_alert(
        self,
        alert_type: str,
        title: str,
        message: str,
        source: str = "",
        details: dict | None = None,
        auto_resolve: bool = False,
    ) -> Any:
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
        pass

    @abstractmethod
    async def resolve_alert(self, alert_id: str) -> bool:
        """
        手动解除告警

        Args:
            alert_id: 告警ID

        Returns:
            是否成功
        """
        pass

    @abstractmethod
    async def get_active_alerts(self, level: str | None = None) -> list[Any]:
        """
        获取活跃告警

        Args:
            level: 级别过滤

        Returns:
            告警列表
        """
        pass

    @abstractmethod
    async def get_alert_summary(self) -> dict[str, Any]:
        """
        获取告警摘要

        Returns:
            告警统计
        """
        pass
