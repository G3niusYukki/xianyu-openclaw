"""
商品数据模型
Listing Models

定义商品相关的数据结构
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class ListingImage:
    """商品图片"""
    local_path: str
    order: int = 0
    processed_path: Optional[str] = None

    def __post_init__(self):
        if self.processed_path is None:
            self.processed_path = self.local_path

    def to_dict(self):
        return {
            "local_path": self.local_path,
            "processed_path": self.processed_path,
            "order": self.order
        }


@dataclass
class Listing:
    """商品信息"""
    title: str
    description: str
    price: float
    original_price: Optional[float] = None
    category: str = "General"
    images: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    location: Optional[str] = None
    brand: Optional[str] = None
    specifications: dict = field(default_factory=dict)
    status: str = "draft"
    product_id: Optional[str] = None
    product_url: Optional[str] = None
    account_id: Optional[str] = None
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
            "tags": self.tags,
            "location": self.location,
            "brand": self.brand,
            "specifications": self.specifications,
            "status": self.status,
            "product_id": self.product_id,
            "product_url": self.product_url,
            "account_id": self.account_id,
        }


@dataclass
class PublishResult:
    """发布结果"""
    success: bool
    product_id: Optional[str] = None
    product_url: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ProductMetrics:
    """商品指标"""
    product_id: str
    views: int = 0
    wants: int = 0
    inquiries: int = 0
    sales: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
