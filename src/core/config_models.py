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
    usage_mode: str = Field(default="minimal", description="AI调用模式：always|auto|minimal")
    max_calls_per_run: int = Field(default=20, ge=1, le=500, description="单次运行最大AI调用数")
    cache_ttl_seconds: int = Field(default=900, ge=30, le=86400, description="本地响应缓存TTL")
    cache_max_entries: int = Field(default=200, ge=10, le=5000, description="本地响应缓存容量")
    task_switches: dict[str, bool] = Field(
        default_factory=lambda: {
            "title": False,
            "description": False,
            "optimize_title": False,
            "seo_keywords": False,
        },
        description="任务级AI开关",
    )


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
    reply_prefix: str = Field(default="", description="回复前缀")
    default_reply: str = Field(default="您好，宝贝在的，感兴趣可以直接拍下。", description="默认回复文案")
    virtual_default_reply: str = Field(
        default="在的，这是虚拟商品，拍下后会尽快在聊天内给你处理结果。",
        description="虚拟商品场景默认回复",
    )
    virtual_product_keywords: list[str] = Field(default_factory=list, description="虚拟商品识别关键词")
    intent_rules: list[dict[str, Any]] = Field(default_factory=list, description="意图规则列表")
    keyword_replies: dict[str, str] = Field(default_factory=dict, description="关键词回复模板")
    fast_reply_enabled: bool = Field(default=False, description="是否启用快速回复链路")
    reply_target_seconds: float = Field(default=3.0, ge=0.5, le=20.0, description="自动回复目标时延")
    reuse_message_page: bool = Field(default=True, description="是否复用消息页")
    first_reply_delay_seconds: list[float] = Field(
        default_factory=lambda: [0.25, 0.9],
        description="首条回复抖动延迟范围",
    )
    inter_reply_delay_seconds: list[float] = Field(
        default_factory=lambda: [0.4, 1.2],
        description="会话间回复延迟范围",
    )
    send_confirm_delay_seconds: list[float] = Field(
        default_factory=lambda: [0.15, 0.35],
        description="发送确认后延迟范围",
    )
    quote_intent_keywords: list[str] = Field(default_factory=list, description="询价意图关键词")
    quote_missing_template: str = Field(
        default="为了给您准确报价，请补充：{fields}。",
        description="询价缺参补问模板",
    )
    quote_failed_template: str = Field(
        default="报价服务暂时繁忙，我先帮您转人工确认，确保价格准确。",
        description="报价失败降级模板",
    )
    quote: dict[str, Any] = Field(default_factory=dict, description="消息模块中的报价覆盖配置")
    workflow: dict[str, Any] = Field(default_factory=dict, description="常驻 workflow worker 配置")


class QuoteConfig(BaseModel):
    """自动报价配置模型"""

    enabled: bool = Field(default=True, description="是否启用自动报价")
    mode: str = Field(default="rule_only", description="报价模式：rule_only|provider_only|hybrid")
    ttl_seconds: int = Field(default=90, ge=1, le=3600, description="缓存 TTL")
    max_stale_seconds: int = Field(default=300, ge=0, le=86400, description="陈旧缓存允许时长")
    timeout_ms: int = Field(default=3000, ge=100, le=30000, description="provider 超时时间")
    retry_times: int = Field(default=1, ge=1, le=10, description="provider 重试次数")
    circuit_fail_threshold: int = Field(default=3, ge=1, le=20, description="熔断触发失败阈值")
    circuit_open_seconds: int = Field(default=30, ge=1, le=3600, description="熔断窗口秒数")
    safety_margin: float = Field(default=0.0, ge=0.0, le=1.0, description="报价安全系数")
    validity_minutes: int = Field(default=30, ge=1, le=1440, description="报价有效期（分钟）")
    analytics_log_enabled: bool = Field(default=True, description="是否写入报价审计日志")
    providers: dict[str, Any] = Field(default_factory=dict, description="报价 provider 配置")


class AppConfig(BaseModel):
    """应用配置模型"""

    name: str = Field(default="xianyu-openclaw", description="应用名称")
    version: str = Field(default="1.0.0", description="版本号")
    debug: bool = Field(default=False, description="调试模式")
    log_level: str = Field(default="INFO", description="日志级别")
    data_dir: str = Field(default="data", description="数据目录")
    logs_dir: str = Field(default="logs", description="日志目录")
    runtime: str = Field(default="auto", description="浏览器运行时：auto|lite|pro")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}, got {v}")
        return v

    @field_validator("runtime")
    @classmethod
    def validate_runtime(cls, v: str) -> str:
        valid_runtimes = {"auto", "lite", "pro"}
        runtime = str(v).lower().strip()
        if runtime not in valid_runtimes:
            raise ValueError(f"runtime must be one of {sorted(valid_runtimes)}, got {v}")
        return runtime


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
