import pandas as pd
from typing import List
from .models import Listing, ListingImage

def load_listings_from_csv(file_path: str) -> List[Listing]:
    """
    Load listings from a CSV file.
    Expected columns: title, description, price, category, images (comma separated paths)
    """
    df = pd.read_csv(file_path)
    listings = []
    
    for _, row in df.iterrows():
        try:
            images = []
            if "images" in row and pd.notna(row["images"]):
                image_paths = str(row["images"]).split(",")
                for i, path in enumerate(image_paths):
                    images.append(ListingImage(local_path=path.strip(), order=i))

            listing = Listing(
                title=row.get("title", "Untitled"),
                description=row.get("description", ""),
                price=float(row.get("price", 0.0)),
                category=row.get("category", "General"),
                images=images,
                tags=str(row.get("tags", "")).split(",") if pd.notna(row.get("tags")) else []
            )
            listings.append(listing)
        except Exception as e:
            print(f"Error parsing row: {row}. Error: {e}")
            
    return listings
