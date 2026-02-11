import os
from loguru import logger
from .utils import resize_image_for_xianyu, add_watermark

class MediaService:
    def __init__(self, config):
        self.config = config
        self.output_dir = "data/processed_images"
        os.makedirs(self.output_dir, exist_ok=True)

    def process_listing_images(self, image_paths: list[str], title_text: str = None) -> list[str]:
        """
        Process a list of images for a listing: resize and optional watermark.
        Returns the paths of processed images.
        """
        processed_paths = []
        for path in image_paths:
            if not os.path.exists(path):
                logger.warning(f"Image not found: {path}")
                continue
            
            filename = os.path.basename(path)
            processed_path = os.path.join(self.output_dir, f"processed_{filename}")
            
            # Resize
            if resize_image_for_xianyu(path, processed_path):
                # Optional: Add Watermark
                if title_text:
                     # Re-open processed to add watermark
                     # In a real pipeline, we'd chain operations in memory
                     add_watermark(processed_path, processed_path, text=title_text[:10]) 
                
                processed_paths.append(processed_path)
            else:
                 logger.warning(f"Failed to process {path}")

        return processed_paths
