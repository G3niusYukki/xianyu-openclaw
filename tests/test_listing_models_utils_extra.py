from pathlib import Path

import pandas as pd

from src.modules.listing.models import Listing, ListingImage, ProductMetrics, PublishResult
from src.modules.listing.utils import load_listings_from_csv


def test_listing_models_roundtrip():
    img = ListingImage(local_path="a.jpg", order=1)
    assert img.processed_path == "a.jpg"
    assert img.to_dict()["order"] == 1

    listing = Listing(title="t", description="d", price=1.2, images="img.png")
    assert listing.images == ["img.png"]
    data = listing.to_dict()
    assert data["title"] == "t"
    assert data["price"] == 1.2

    r = PublishResult(success=True)
    assert r.success is True
    m = ProductMetrics(product_id="p1")
    assert m.product_id == "p1" and m.views == 0


def test_load_listings_from_csv_success_and_bad_row(tmp_path, monkeypatch):
    csv_path = tmp_path / "listings.csv"
    pd.DataFrame(
        [
            {
                "title": "A",
                "description": "D",
                "price": "10",
                "category": "Cat",
                "images": "a.jpg,b.jpg",
                "tags": "x,y",
            },
            {"title": "bad", "price": "oops"},
        ]
    ).to_csv(csv_path, index=False)

    printed = []
    monkeypatch.setattr("builtins.print", lambda *a, **k: printed.append(a))

    rows = load_listings_from_csv(str(csv_path))
    assert len(rows) == 1
    assert rows[0].images[0].local_path == "a.jpg"
    assert rows[0].tags == ["x", "y"]
    assert printed, "bad row should be reported"


def test_load_listings_from_csv_defaults(tmp_path):
    csv_path = tmp_path / "minimal.csv"
    Path(csv_path).write_text("title,price\nOnly,2\n", encoding="utf-8")
    rows = load_listings_from_csv(str(csv_path))
    assert rows[0].category == "General"
