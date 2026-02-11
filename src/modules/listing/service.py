from loguru import logger
import time
from .models import Listing
from ...core.openclaw import OpenClawController

class ListingService:
    """
    Service to handle Xianyu product listing operations.
    """
    def __init__(self, controller: OpenClawController):
        self.controller = controller

    def create_listing(self, listing: Listing):
        """
        Automates the process of creating a new listing on Xianyu.
        """
        logger.info(f"Starting listing creation for: {listing.title}")
        
        # 1. Navigate to Publish Page
        # Note: Actual URL or navigation logic depends on Xianyu Web/App structure
        self.controller.navigate("https://www.goofish.com/publish") # Placeholder URL
        # wait for page load
        time.sleep(2)

        # 2. Upload Images
        # Assuming there's an input type='file' usually hidden or a specific button
        if listing.images:
            for img in listing.images:
                path_to_upload = img.processed_path if img.processed_path else img.local_path
                self.controller.upload_file("input[type='file']", path_to_upload)
                # Wait for upload
                time.sleep(1)

        # 3. Fill Title and Description
        self.controller.type_text("#title-input", listing.title)
        self.controller.type_text("#desc-input", listing.description)

        # 4. Fill Price
        # This might require switching to a price setting modal
        self.controller.type_text("#price-input", str(listing.price))

        # 5. Submit
        # self.controller.click("#publish-btn")
        
        logger.info("Listing script executed (Dry Run).")
        return True

    def batch_create_listings(self, listings: list[Listing]):
        """
        Process multiple listings sequentially.
        """
        results = []
        for item in listings:
            try:
                success = self.create_listing(item)
                results.append({"title": item.title, "status": "success" if success else "failed"})
                # Random delay between listings to avoid risk
                time.sleep(5) 
            except Exception as e:
                logger.error(f"Failed to list {item.title}: {e}")
                results.append({"title": item.title, "status": "error", "message": str(e)})
        return results
