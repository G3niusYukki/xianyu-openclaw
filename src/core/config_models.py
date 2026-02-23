"""
配置模型与验证
Configuration Models and Validation

使用Pydantic进行配置验证
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator
from enum import Enum


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
    api_key: Optional[str] = Field(default=None, description="API密钥")
    base_url: Optional[str] = Field(default=None, description="API基础URL")
    model: str = Field(default="deepseek-chat", description="模型名称")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="温度参数")
    max_tokens: int = Field(default=1000, ge=1, le=4000, description="最大生成令牌数")
    timeout: int = Field(default=30, ge=1, le=120, description="API调用超时时间（秒）")
    fallback_enabled: bool = Field(default=True, description="是否启用降级策略")
    fallback_api_key: Optional[str] = Field(default=None, description="备用API密钥")
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
    polish: Optional[Dict[str, Any]] = Field(default=None, description="擦亮任务配置")
    metrics: Optional[Dict[str, Any]] = Field(default=None, description="数据采集任务配置")


class MediaConfig(BaseModel):
    """媒体处理配置模型"""
    max_image_size: int = Field(default=5242880, ge=1024, le=10485760, description="最大图片大小（字节）")
    supported_formats: List[str] = Field(
        default=["jpg", "jpeg", "png", "webp"],
        description="支持的图片格式"
    )
    output_format: str = Field(default="jpeg", description="输出格式")
    output_quality: int = Field(default=85, ge=1, le=100, description="输出质量")
    max_width: int = Field(default=1500, ge=100, le=4000, description="最大宽度")
    max_height: int = Field(default=1500, ge=100, le=4000, description="最大高度")
    watermark: Optional[Dict[str, Any]] = Field(default=None, description="水印配置")


class ContentConfig(BaseModel):
    """内容生成配置模型"""
    title: Optional[Dict[str, Any]] = Field(default=None, description="标题生成配置")
    description: Optional[Dict[str, Any]] = Field(default=None, description="描述生成配置")
    templates: Optional[Dict[str, Any]] = Field(default=None, description="模板配置")


class BrowserConfig(BaseModel):
    """浏览器配置模型"""
    headless: bool = Field(default=True, description="是否无头模式")
    user_agent: Optional[str] = Field(default=None, description="用户代理")
    viewport: Dict[str, int] = Field(
        default={"width": 1280, "height": 800},
        description="视口大小"
    )
    delay: Dict[str, float] = Field(
        default={"min": 1.0, "max": 3.0},
        description="操作延迟范围（秒）"
    )
    upload_timeout: int = Field(default=60, ge=10, le=300, description="文件上传超时时间（秒）")


class AppConfig(BaseModel):
    """应用配置模型"""
    name: str = Field(default="xianyu-openclaw", description="应用名称")
    version: str = Field(default="1.0.0", description="版本号")
    debug: bool = Field(default=False, description="调试模式")
    log_level: str = Field(default="INFO", description="日志级别")
    data_dir: str = Field(default="data", description="数据目录")
    logs_dir: str = Field(default="logs", description="日志目录")

    @validator("log_level")
    def validate_log_level(cls, v):
        """验证日志级别"""
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
    accounts: List[AccountConfig] = Field(default_factory=list)
    default_account: Optional[str] = Field(default=None, description="默认账号ID")
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    media: MediaConfig = Field(default_factory=MediaConfig)
    content: ContentConfig = Field(default_factory=ContentConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)

    @validator('default_account')
    def validate_default_account(cls, v, values):
        """验证默认账号ID是否存在"""
        if v and 'accounts' in values:
            account_ids = [acc.id for acc in values['accounts']]
            if v not in account_ids:
                raise ValueError(f'default_account "{v}" not found in accounts list')
        return v

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConfigModel':
        """从字典创建配置"""
        return cls(**data)
