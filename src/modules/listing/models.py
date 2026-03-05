"""
商品数据模型
Listing Models

定义商品相关的数据结构
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass
class ListingImage:
    """商品图片"""

    local_path: str
    order: int = 0
    processed_path: str | None = None

    def __post_init__(self):
        if self.processed_path is None:
            self.processed_path = self.local_path

    def to_dict(self):
        return {"local_path": self.local_path, "processed_path": self.processed_path, "order": self.order}


def generate_internal_listing_id() -> str:
    """生成真实 internal_listing_id（可用于映射主表主键）。"""
    return f"lst_{uuid4().hex}"


@dataclass
class Listing:
    """商品信息"""

    title: str
    description: str
    price: float
    original_price: float | None = None
    category: str = "General"
    images: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    location: str | None = None
    brand: str | None = None
    specifications: dict = field(default_factory=dict)
    status: str = "draft"
    product_id: str | None = None
    product_url: str | None = None
    internal_listing_id: str | None = None
    account_id: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if isinstance(self.images, str):
            self.images = [self.images]

    def to_dict(self):
        return {
            "title": self.title,
            "description": self.description,
            "price": self.price,
            "original_price": self.original_price,
            "category": self.category,
            "images": self.images,
            "features": self.features,
            "tags": self.tags,
            "location": self.location,
            "brand": self.brand,
            "specifications": self.specifications,
            "status": self.status,
            "product_id": self.product_id,
            "product_url": self.product_url,
            "internal_listing_id": self.internal_listing_id,
            "account_id": self.account_id,
        }


@dataclass
class PublishResult:
    """发布结果"""

    success: bool
    product_id: str | None = None
    product_url: str | None = None
    internal_listing_id: str | None = None
    error_message: str | None = None
    # Wave D 统一执行契约字段（保持向后兼容）
    ok: bool | None = None
    action: str = "publish"
    code: str = "OK"
    message: str = "ok"
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    ts: str = field(default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        if self.ok is None:
            self.ok = bool(self.success)
        if not self.data:
            self.data = {
                "xianyu_product_id": self.product_id,
                "internal_listing_id": self.internal_listing_id,
                "channel": "unknown",
                "mapping_status": "inactive",
                "code": self.code,
                "message": self.message,
            }
        if self.error_message and not self.errors:
            self.errors = [{"code": self.code if not self.success else "ERROR", "message": self.error_message}]


@dataclass
class ProductMetrics:
    """商品指标"""

    product_id: str
    views: int = 0
    wants: int = 0
    inquiries: int = 0
    sales: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
