import sys
import os
import yaml
from loguru import logger
# from src.core.openclaw import OpenClawController
# from src.modules.listing.service import ListingService
# from src.modules.listing.utils import load_listings_from_csv

# Add src to python path to allow imports from submodules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

def load_config(config_path="config/config.yaml"):
    if not os.path.exists(config_path):
        logger.warning(f"Config file not found at {config_path}. Using defaults or example config.")
        config_path = "config/config.example.yaml"
    
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    return {}

def main():
    logger.add("logs/app.log", rotation="10 MB")
    logger.info("Starting Xianyu Automation Tool...")

    config = load_config()
    from src.core.openclaw import OpenClawController
    from src.modules.listing.service import ListingService
    from src.modules.listing.utils import load_listings_from_csv
    from src.modules.media.service import MediaService
    from src.modules.content.service import ContentService
    from src.modules.operations.service import OperationsService
    from src.modules.operations.analytics import AnalyticsService

    # Initialize OpenClaw Controller
    controller = OpenClawController(config)
    
    # Initialize Core Modules
    listing_service = ListingService(controller)
    media_service = MediaService(config)
    content_service = ContentService(config)
    analytics_service = AnalyticsService(config)
    operations_service = OperationsService(controller, analytics_service)
    
    # Check for CLI args or config to run specific tasks
    # For now, just a placeholder for the logic
    # listings = load_listings_from_csv("data/listings.csv")
    # listing_service.batch_create_listings(listings)
    
    logger.info("Initialization complete. Core modules loaded.")
    logger.info("Ready to execute tasks.")

if __name__ == "__main__":
    main()
