"""
媒体处理服务
Media Processing Service

提供闲鱼商品图片的自动化处理功能
"""

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.core.config import get_config
from src.core.logger import get_logger


class MediaService:
    """
    媒体处理服务

    负责商品图片的尺寸调整、压缩、水印添加等处理
    """

    def __init__(self, config: dict | None = None):
        """
        初始化媒体处理服务

        Args:
            config: 配置字典
        """
        self.config = config or get_config().media
        self.logger = get_logger()
        self.supported_formats = self.config.get("supported_formats", ["jpg", "jpeg", "png", "webp"])
        self.max_size = (self.config.get("max_width", 1500), self.config.get("max_height", 1500))
        self.output_format = self.config.get("output_format", "JPEG")
        self.output_quality = self.config.get("output_quality", 85)

        self.output_dir = "data/processed_images"
        os.makedirs(self.output_dir, exist_ok=True)

    def resize_image_for_xianyu(self, image_path: str, output_path: str | None = None) -> str:
        """
        调整图片尺寸以符合闲鱼规范

        Args:
            image_path: 输入图片路径
            output_path: 输出路径，不指定则覆盖原文件

        Returns:
            处理后的图片路径
        """
        try:
            with Image.open(image_path) as img:
                original_format = img.format
                img = self._smart_resize(img)
                img = self._ensure_rgb(img)

                if output_path is None:
                    output_path = image_path

                ext = Path(output_path).suffix.lower()[1:] or original_format.lower()
                save_format = self._get_save_format(ext)

                img.save(output_path, format=save_format, quality=self.output_quality, optimize=True)

                self.logger.debug(f"Resized image: {image_path}")
                return output_path

        except Exception as e:
            self.logger.error(f"Failed to resize image {image_path}: {e}")
            return image_path

    def _smart_resize(self, img: Image.Image) -> Image.Image:
        """
        智能调整尺寸，保持宽高比
        """
        original_width, original_height = img.size
        max_width, max_height = self.max_size

        if original_width <= max_width and original_height <= max_height:
            return img

        ratio = min(max_width / original_width, max_height / original_height)
        new_width = int(original_width * ratio)
        new_height = int(original_height * ratio)

        return img.resize((new_width, new_height), Image.LANCZOS)

    def _ensure_rgb(self, img: Image.Image) -> Image.Image:
        """
        确保图片为RGB模式
        """
        if img.mode in ("RGBA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            return background
        return img.convert("RGB")

    def _get_save_format(self, ext: str) -> str:
        """获取保存格式"""
        format_map = {
            "jpg": "JPEG",
            "jpeg": "JPEG",
            "png": "PNG",
            "webp": "WEBP",
        }
        return format_map.get(ext.lower(), "JPEG")

    def add_watermark(
        self, image_path: str, output_path: str | None = None, text: str | None = None, position: str = "bottom-right"
    ) -> str:
        """
        添加文字水印

        Args:
            image_path: 输入图片路径
            output_path: 输出路径
            text: 水印文字
            position: 位置 (top-left, top-right, bottom-left, bottom-right, center)

        Returns:
            处理后的图片路径
        """
        watermark_config = self.config.get("watermark", {})
        if not watermark_config.get("enabled", False):
            return image_path

        text = text or watermark_config.get("text", "闲鱼助手")
        position = position or watermark_config.get("position", "bottom-right")

        try:
            with Image.open(image_path) as img:
                img = self._ensure_rgb(img)
                draw = ImageDraw.Draw(img)

                width, height = img.size
                font_size = watermark_config.get("font_size", 24)
                font_color = watermark_config.get("color", "#FFFFFF")

                try:
                    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
                except OSError as e:
                    self.logger.debug(f"Failed to load custom font: {e}")
                    font = ImageFont.load_default()

                text_bbox = draw.textbbox((0, 0), text, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]

                margin = 20
                positions = {
                    "top-left": (margin, margin),
                    "top-right": (width - text_width - margin, margin),
                    "bottom-left": (margin, height - text_height - margin),
                    "bottom-right": (width - text_width - margin, height - text_height - margin),
                    "center": ((width - text_width) // 2, (height - text_height) // 2),
                }

                x, y = positions.get(position, positions["bottom-right"])

                r, g, b = self._hex_to_rgb(font_color)
                draw.text((x, y), text, fill=(r, g, b), font=font)

                if output_path is None:
                    output_path = image_path

                img.save(output_path, format=self._get_save_format(Path(output_path).suffix.lower()[1:]))
                self.logger.debug(f"Added watermark to: {image_path}")
                return output_path

        except Exception as e:
            self.logger.error(f"Failed to add watermark: {e}")
            return image_path

    def _hex_to_rgb(self, hex_color: str) -> tuple[int, int, int]:
        """Hex颜色转RGB"""
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

    def batch_process_images(
        self, image_paths: list[str], output_dir: str | None = None, add_watermark: bool = True
    ) -> list[str]:
        """
        批量处理图片

        Args:
            image_paths: 图片路径列表
            output_dir: 输出目录
            add_watermark: 是否添加水印

        Returns:
            处理后的图片路径列表
        """
        if output_dir:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
        else:
            output_dir = self.output_dir

        processed_paths = []

        for i, image_path in enumerate(image_paths):
            if not os.path.exists(image_path):
                self.logger.warning(f"Image not found: {image_path}")
                continue

            filename = Path(image_path).stem
            ext = Path(image_path).suffix or ".jpg"

            output_path = os.path.join(output_dir, f"{filename}_processed{ext}")

            try:
                processed = self.resize_image_for_xianyu(image_path, output_path)
                if add_watermark:
                    processed = self.add_watermark(processed)
                processed_paths.append(processed)
                self.logger.info(f"Processed image {i + 1}/{len(image_paths)}: {image_path}")
            except Exception as e:
                self.logger.error(f"Failed to process image {image_path}: {e}")
                processed_paths.append(image_path)

        return processed_paths

    def compress_image(self, image_path: str, output_path: str | None = None, quality: int = 85) -> str:
        """
        压缩图片

        Args:
            image_path: 输入图片路径
            output_path: 输出路径
            quality: 质量 (1-100)

        Returns:
            处理后的图片路径
        """
        try:
            with Image.open(image_path) as img:
                img = self._ensure_rgb(img)
                if output_path is None:
                    output_path = image_path
                img.save(output_path, quality=quality, optimize=True)
                return output_path
        except Exception as e:
            self.logger.error(f"Failed to compress image {image_path}: {e}")
            return image_path

    def validate_image(self, image_path: str) -> tuple[bool, str]:
        """
        验证图片格式和大小

        Args:
            image_path: 图片路径

        Returns:
            (是否有效, 错误信息)
        """
        if not os.path.exists(image_path):
            return False, "文件不存在"

        ext = Path(image_path).suffix.lower()[1:]
        if ext not in self.supported_formats:
            return False, f"不支持的图片格式: {ext}"

        max_size_bytes = self.config.get("max_image_size", 5 * 1024 * 1024)
        file_size = os.path.getsize(image_path)
        if file_size > max_size_bytes:
            return False, f"图片过大: {file_size / 1024 / 1024:.2f}MB"

        try:
            with Image.open(image_path) as img:
                if img.mode == "CMYK":
                    return False, "不支持CMYK色彩模式"
        except Exception as e:
            return False, f"无法读取图片: {e}"

        return True, ""
