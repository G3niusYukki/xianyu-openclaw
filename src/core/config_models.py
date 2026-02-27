"""
配置模型与验证
Configuration Models and Validation

使用Pydantic进行配置验证
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Provider(str, Enum):
    """AI提供商枚举"""

    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    CLAUDE = "claude"


class OpenClawConfig(BaseModel):
    """OpenClaw配置模型"""

    host: str = "localhost"
    port: int = Field(default=9222, ge=1, le=65535, description="OpenClaw服务端口")
    timeout: int = Field(default=30, ge=1, le=300, description="连接超时时间（秒）")
    retry_times: int = Field(default=3, ge=0, le=10, description="重试次数")


class AIConfig(BaseModel):
    """AI服务配置模型"""

    provider: Provider = Provider.DEEPSEEK
    api_key: str | None = Field(default=None, description="API密钥")
    base_url: str | None = Field(default=None, description="API基础URL")
    model: str = Field(default="deepseek-chat", description="模型名称")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="温度参数")
    max_tokens: int = Field(default=1000, ge=1, le=4000, description="最大生成令牌数")
    timeout: int = Field(default=30, ge=1, le=120, description="API调用超时时间（秒）")
    fallback_enabled: bool = Field(default=True, description="是否启用降级策略")
    fallback_api_key: str | None = Field(default=None, description="备用API密钥")
    fallback_model: str = Field(default="gpt-3.5-turbo", description="备用模型")
    usage_mode: str = Field(default="minimal", description="AI调用策略: always | auto | minimal")
    max_calls_per_run: int = Field(default=20, ge=1, le=1000, description="单次运行最多AI调用次数")
    cache_enabled: bool = Field(default=True, description="是否启用AI响应缓存")
    cache_path: str = Field(default="data/ai_response_cache.json", description="AI缓存文件路径")
    cache_ttl_seconds: int = Field(default=86400, ge=60, le=2592000, description="AI缓存有效期（秒）")
    cache_max_entries: int = Field(default=2000, ge=100, le=200000, description="缓存最大条目数")
    task_ai_enabled: dict[str, bool] = Field(
        default_factory=lambda: {
            "title": False,
            "description": False,
            "optimize_title": True,
            "seo_keywords": True,
        },
        description="各任务是否允许AI（minimal/auto 模式下生效）",
    )

    @field_validator("usage_mode")
    @classmethod
    def validate_usage_mode(cls, v: str) -> str:
        value = (v or "").strip().lower()
        valid_modes = {"always", "auto", "minimal"}
        if value not in valid_modes:
            raise ValueError(f"usage_mode must be one of {sorted(valid_modes)}, got {v}")
        return value


class DatabaseConfig(BaseModel):
    """数据库配置模型"""

    type: str = Field(default="sqlite", description="数据库类型")
    path: str = Field(default="data/agent.db", description="数据库路径")
    max_connections: int = Field(default=5, ge=1, le=20, description="最大连接数")
    timeout: int = Field(default=30, ge=1, le=300, description="数据库操作超时时间（秒）")


class AccountConfig(BaseModel):
    """账号配置模型"""

    id: str = Field(..., description="账号ID")
    name: str = Field(..., description="账号名称")
    cookie: str = Field(..., description="登录Cookie")
    priority: int = Field(default=1, ge=1, le=100, description="优先级")
    enabled: bool = Field(default=True, description="是否启用")


class SchedulerConfig(BaseModel):
    """调度器配置模型"""

    enabled: bool = Field(default=True, description="是否启用调度器")
    timezone: str = Field(default="Asia/Shanghai", description="时区")
    polish: dict[str, Any] | None = Field(default=None, description="擦亮任务配置")
    metrics: dict[str, Any] | None = Field(default=None, description="数据采集任务配置")


class MediaConfig(BaseModel):
    """媒体处理配置模型"""

    max_image_size: int = Field(default=5242880, ge=1024, le=10485760, description="最大图片大小（字节）")
    supported_formats: list[str] = Field(default=["jpg", "jpeg", "png", "webp"], description="支持的图片格式")
    output_format: str = Field(default="jpeg", description="输出格式")
    output_quality: int = Field(default=85, ge=1, le=100, description="输出质量")
    max_width: int = Field(default=1500, ge=100, le=4000, description="最大宽度")
    max_height: int = Field(default=1500, ge=100, le=4000, description="最大高度")
    watermark: dict[str, Any] | None = Field(default=None, description="水印配置")


class ContentConfig(BaseModel):
    """内容生成配置模型"""

    title: dict[str, Any] | None = Field(default=None, description="标题生成配置")
    description: dict[str, Any] | None = Field(default=None, description="描述生成配置")
    templates: dict[str, Any] | None = Field(default=None, description="模板配置")


class BrowserConfig(BaseModel):
    """浏览器配置模型"""

    headless: bool = Field(default=True, description="是否无头模式")
    user_agent: str | None = Field(default=None, description="用户代理")
    viewport: dict[str, int] = Field(default={"width": 1280, "height": 800}, description="视口大小")
    delay: dict[str, float] = Field(default={"min": 1.0, "max": 3.0}, description="操作延迟范围（秒）")
    upload_timeout: int = Field(default=60, ge=10, le=300, description="文件上传超时时间（秒）")


class MessagesConfig(BaseModel):
    """消息自动回复配置模型"""

    enabled: bool = Field(default=False, description="是否启用消息自动回复")
    max_replies_per_run: int = Field(default=10, ge=1, le=200, description="单次最多自动回复数量")
    fast_first_reply_enabled: bool = Field(default=True, description="是否启用快速首响")
    first_reply_target_seconds: float = Field(default=3.0, ge=0.5, le=30, description="首响目标时延（秒）")
    reuse_message_page: bool = Field(default=True, description="是否复用消息页以降低时延")
    first_reply_delay_seconds: list[float] = Field(
        default_factory=lambda: [0.25, 0.8],
        description="首响前随机延迟区间（秒）",
    )
    inter_reply_delay_seconds: list[float] = Field(
        default_factory=lambda: [0.4, 1.2],
        description="多会话回复间隔区间（秒）",
    )
    send_confirm_delay_seconds: list[float] = Field(
        default_factory=lambda: [0.15, 0.35],
        description="发送后确认等待区间（秒）",
    )
    followup_quote_enabled: bool = Field(default=True, description="是否启用询价二阶段回复")
    followup_quote_delay_seconds: list[float] = Field(
        default_factory=lambda: [0.6, 1.5],
        description="首响后报价补充消息延迟区间（秒）",
    )
    read_no_reply_followup_enabled: bool = Field(default=False, description="是否启用已读未回合规跟进")
    read_no_reply_limit_per_run: int = Field(default=20, ge=1, le=200, description="单次最多处理已读未回会话")
    read_no_reply_min_elapsed_seconds: int = Field(
        default=300,
        ge=30,
        le=86400,
        description="首响后达到该时长才允许跟进（秒）",
    )
    read_no_reply_min_interval_seconds: int = Field(
        default=1800,
        ge=30,
        le=86400,
        description="同会话两次跟进最小间隔（秒）",
    )
    read_no_reply_max_per_session: int = Field(default=1, ge=1, le=5, description="单会话最多跟进次数")
    read_no_reply_templates: list[str] = Field(default_factory=list, description="已读未回跟进话术模板")
    read_no_reply_stop_keywords: list[str] = Field(default_factory=list, description="触发停发的关键词")
    fulfillment_confirm_enabled: bool = Field(default=True, description="是否启用下单/付款履约确认")
    order_intent_keywords: list[str] = Field(default_factory=list, description="订单确认意图关键词")
    fulfillment_ack_template: str = Field(
        default="收到你的订单，我这边开始处理，结果会优先在闲鱼聊天内同步，请耐心等我一下。",
        description="履约确认回复模板",
    )
    followup_state_path: str = Field(
        default="data/messages_followup_state.json",
        description="会话跟进状态存储文件",
    )
    followup_state_max_sessions: int = Field(default=5000, ge=100, le=200000, description="跟进状态最大保留会话数")
    workflow_state_enabled: bool = Field(default=True, description="是否启用会话工作流状态机")
    workflow_state_path: str = Field(default="data/message_workflow_state.json", description="状态机存储文件路径")
    workflow_state_max_sessions: int = Field(default=5000, ge=100, le=200000, description="状态机最大保留会话数")
    worker_enabled: bool = Field(default=False, description="是否启用常驻消息工作流 worker")
    worker_interval_seconds: float = Field(default=15.0, ge=0.01, le=3600, description="worker 轮询间隔（秒）")
    worker_jitter_seconds: float = Field(default=1.5, ge=0, le=60, description="worker 轮询抖动（秒）")
    worker_backoff_seconds: float = Field(default=5.0, ge=0.01, le=600, description="worker 失败退避基数（秒）")
    worker_max_backoff_seconds: float = Field(default=120.0, ge=0.01, le=3600, description="worker 最大退避（秒）")
    worker_state_path: str = Field(default="data/workflow_worker_state.json", description="worker 状态文件路径")
    worker_sla_enabled: bool = Field(default=True, description="是否启用 worker SLA 监控")
    worker_sla_path: str = Field(default="data/workflow_sla_metrics.json", description="worker SLA 数据文件路径")
    worker_sla_window_size: int = Field(default=500, ge=10, le=50000, description="SLA 统计窗口大小（轮次）")
    worker_alert_min_samples: int = Field(default=10, ge=1, le=10000, description="触发告警的最小样本数")
    worker_alert_failure_rate_threshold: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="失败率告警阈值",
    )
    worker_alert_first_reply_within_target_ratio_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="首响达标率告警阈值",
    )
    worker_alert_cycle_p95_seconds: float = Field(
        default=20.0,
        ge=0.1,
        le=600.0,
        description="工作流周期时延 P95 告警阈值（秒）",
    )
    reply_prefix: str = Field(default="", description="回复前缀")
    default_reply: str = Field(default="您好，宝贝在的，感兴趣可以直接拍下。", description="默认回复文案")
    virtual_default_reply: str = Field(
        default="在的，这是虚拟商品，拍下后会尽快在聊天内给你处理结果。",
        description="虚拟商品场景默认回复",
    )
    virtual_product_keywords: list[str] = Field(default_factory=list, description="虚拟商品识别关键词")
    intent_rules: list[dict[str, Any]] = Field(default_factory=list, description="意图规则列表")
    keyword_replies: dict[str, str] = Field(default_factory=dict, description="关键词回复模板")


class QuoteConfig(BaseModel):
    """自动报价配置模型"""

    enabled: bool = Field(default=True, description="是否启用自动报价")
    mode: str = Field(
        default="rule_only",
        description="报价模式: rule_only | remote_then_rule | cost_table_plus_markup | api_cost_plus_markup",
    )
    origin_city: str = Field(default="杭州", description="默认寄件城市")
    pricing_profile: str = Field(default="normal", description="加价档位: normal | member")
    preferred_couriers: list[str] = Field(default_factory=list, description="优先承运商列表（未指定快递时生效）")
    cost_table_dir: str = Field(default="data/quote_costs", description="成本价表目录")
    cost_table_patterns: list[str] = Field(default_factory=lambda: ["*.xlsx", "*.csv"], description="成本表匹配规则")
    markup_rules: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="加价规则（按快递公司与档位）",
    )
    cost_api_url: str = Field(default="", description="成本价接口 URL")
    cost_api_key: str = Field(default="", description="成本价接口密钥")
    cost_api_timeout_seconds: int = Field(default=3, ge=1, le=30, description="成本价接口超时（秒）")
    cost_api_headers: dict[str, str] = Field(default_factory=dict, description="成本价接口额外请求头")
    api_fallback_to_table_parallel: bool = Field(
        default=True,
        description="API 报价时是否启用本地成本表并行快速回退",
    )
    api_prefer_max_wait_seconds: float = Field(
        default=1.2,
        ge=0.1,
        le=10.0,
        description="等待 API 报价的优先窗口（秒），超时后优先返回本地成本表报价",
    )
    currency: str = Field(default="CNY", description="币种")
    first_weight_kg: float = Field(default=1.0, ge=0.1, le=10.0, description="首重公斤数")
    first_price: float = Field(default=8.0, ge=0, le=9999, description="首重价格")
    extra_per_kg: float = Field(default=2.5, ge=0, le=9999, description="续重每公斤价格")
    service_fee: float = Field(default=1.0, ge=0, le=9999, description="服务费")
    urgency_fee: float = Field(default=4.0, ge=0, le=9999, description="加急附加费")
    inter_city_extra: float = Field(default=2.0, ge=-9999, le=9999, description="跨城附加费")
    remote_extra: float = Field(default=6.0, ge=0, le=9999, description="偏远地区附加费")
    remote_keywords: list[str] = Field(
        default_factory=lambda: ["新疆", "西藏", "青海", "甘肃", "内蒙古", "海南"],
        description="偏远地区关键词",
    )
    eta_same_city_minutes: int = Field(default=90, ge=10, le=1440, description="同城预计时效（分钟）")
    eta_inter_city_minutes: int = Field(default=360, ge=30, le=10080, description="跨城预计时效（分钟）")
    valid_minutes: int = Field(default=15, ge=1, le=1440, description="报价有效期（分钟）")
    remote_api_url: str = Field(default="", description="远端报价接口 URL")
    remote_api_key: str = Field(default="", description="远端报价接口密钥")
    timeout_seconds: int = Field(default=3, ge=1, le=30, description="远端报价接口超时（秒）")

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        valid_modes = {
            "rule_only",
            "remote_then_rule",
            "cost_table_plus_markup",
            "api_cost_plus_markup",
        }
        if v not in valid_modes:
            raise ValueError(f"mode must be one of {sorted(valid_modes)}, got {v}")
        return v

    @field_validator("pricing_profile")
    @classmethod
    def validate_pricing_profile(cls, v: str) -> str:
        profile = (v or "").strip().lower()
        if profile in {"normal", "member"}:
            return profile
        raise ValueError(f"pricing_profile must be one of ['normal', 'member'], got {v}")


class AppConfig(BaseModel):
    """应用配置模型"""

    name: str = Field(default="xianyu-openclaw", description="应用名称")
    version: str = Field(default="1.0.0", description="版本号")
    debug: bool = Field(default=False, description="调试模式")
    log_level: str = Field(default="INFO", description="日志级别")
    data_dir: str = Field(default="data", description="数据目录")
    logs_dir: str = Field(default="logs", description="日志目录")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}, got {v}")
        return v


class ConfigModel(BaseModel):
    """完整配置模型"""

    app: AppConfig = Field(default_factory=AppConfig)
    openclaw: OpenClawConfig = Field(default_factory=OpenClawConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    accounts: list[AccountConfig] = Field(default_factory=list)
    default_account: str | None = Field(default=None, description="默认账号ID")
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    media: MediaConfig = Field(default_factory=MediaConfig)
    content: ContentConfig = Field(default_factory=ContentConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    messages: MessagesConfig = Field(default_factory=MessagesConfig)
    quote: QuoteConfig = Field(default_factory=QuoteConfig)

    @field_validator("default_account")
    @classmethod
    def validate_default_account(cls, v: str | None) -> str | None:
        return v

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConfigModel":
        """从字典创建配置"""
        return cls(**data)
