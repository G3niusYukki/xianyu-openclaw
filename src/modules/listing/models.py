from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ListingImage:
    local_path: str
    order: int = 0
    # Processed path could be added later after media processing
    processed_path: Optional[str] = None

@dataclass
class Listing:
    title: str
    description: str
    price: float
    original_price: Optional[float] = None
    category: str = "General"
    images: List[ListingImage] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    location: Optional[str] = None
    brand: Optional[str] = None
    specifications: dict = field(default_factory=dict) # Key-value pairs for specific item specs

    def to_dict(self):
        return {
            "title": self.title,
            "description": self.description,
            "price": self.price,
            "images": [img.local_path for img in self.images],
            "tags": self.tags
        }
