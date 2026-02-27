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
    mode: str = Field(default="rule_only", description="报价模式: rule_only | remote_then_rule")
    origin_city: str = Field(default="杭州", description="默认寄件城市")
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
        valid_modes = {"rule_only", "remote_then_rule"}
        if v not in valid_modes:
            raise ValueError(f"mode must be one of {sorted(valid_modes)}, got {v}")
        return v


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
