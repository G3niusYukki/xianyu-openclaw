from PIL import Image, ImageDraw, ImageFont, ImageOps
import cv2
import os
from loguru import logger

def resize_image_for_xianyu(image_path: str, output_path: str, target_size=(800, 800)):
    """
    Resize image to target size, maintaining aspect ratio and padding with white/blurred background if needed.
    """
    try:
        with Image.open(image_path) as img:
            img.thumbnail(target_size, Image.Resampling.LANCZOS)
            
            # Create a new image with the target size and white background
            new_img = Image.new("RGB", target_size, (255, 255, 255))
            
            # Paste the resized image onto the center
            left = (target_size[0] - img.width) // 2
            top = (target_size[1] - img.height) // 2
            new_img.paste(img, (left, top))
            
            new_img.save(output_path, quality=95)
            logger.info(f"Resized image saved to {output_path}")
            return True
    except Exception as e:
        logger.error(f"Failed to resize image {image_path}: {e}")
        return False

def add_watermark(image_path: str, output_path: str, text: str = "Xianyu"):
    """
    Add a simple text watermark to the image.
    """
    try:
        with Image.open(image_path) as img:
            draw = ImageDraw.Draw(img)
            # Load font (using default if custom not available)
            # In production, use a specific font file
            try:
                font = ImageFont.truetype("Arial.ttf", size=36)
            except IOError:
                font = ImageFont.load_default()
            
            # Calculate text size and position
            # draw.textbbox is available in newer Pillow versions
            # For compatibility, we might just put it in bottom right
            
            width, height = img.size
            
            # simple positioning: bottom right
            draw.text((width - 150, height - 50), text, fill=(255, 255, 255, 128), font=font)
            
            img.save(output_path)
            logger.info(f"Watermarked image saved to {output_path}")
            return True
    except Exception as e:
        logger.error(f"Failed to watermark image {image_path}: {e}")
        return False
