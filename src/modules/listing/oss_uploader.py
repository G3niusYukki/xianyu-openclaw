"""阿里云 OSS 上传器 — 将本地图片上传到 OSS 获取公网 URL。

闲管家商品创建 API 要求图片为公网 URL，
本模块将 Playwright 截图生成的本地 PNG 上传到阿里云 OSS。

配置来源（优先级从高到低）:
1. 函数参数 config dict
2. 环境变量 OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET / OSS_BUCKET / OSS_ENDPOINT
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from src.core.logger import get_logger

logger = get_logger()


class OSSUploader:
    """阿里云 OSS 上传封装。"""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.access_key_id = str(cfg.get("access_key_id") or os.getenv("OSS_ACCESS_KEY_ID", "")).strip()
        self.access_key_secret = str(cfg.get("access_key_secret") or os.getenv("OSS_ACCESS_KEY_SECRET", "")).strip()
        self.bucket_name = str(cfg.get("bucket") or os.getenv("OSS_BUCKET", "")).strip()
        self.endpoint = str(cfg.get("endpoint") or os.getenv("OSS_ENDPOINT", "")).strip()
        self.prefix = str(cfg.get("prefix", "xianyu/listing/")).strip()
        self.custom_domain = str(cfg.get("custom_domain", "")).strip()
        self._bucket = None

    @property
    def configured(self) -> bool:
        return bool(self.access_key_id and self.access_key_secret and self.bucket_name and self.endpoint)

    def _get_bucket(self):
        if self._bucket is not None:
            return self._bucket
        try:
            import oss2
        except ImportError as exc:
            raise RuntimeError(
                "oss2 package is required for OSS upload. Install: pip install oss2"
            ) from exc

        auth = oss2.Auth(self.access_key_id, self.access_key_secret)
        self._bucket = oss2.Bucket(auth, self.endpoint, self.bucket_name)
        return self._bucket

    def upload(self, local_path: str | Path) -> str:
        """上传本地文件到 OSS，返回公网 URL。"""
        if not self.configured:
            raise ValueError(
                "OSS not configured. Set OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET, "
                "OSS_BUCKET, OSS_ENDPOINT environment variables or pass config dict."
            )

        path = Path(local_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {local_path}")

        ext = path.suffix or ".png"
        object_key = f"{self.prefix}{uuid.uuid4().hex}{ext}"

        bucket = self._get_bucket()
        bucket.put_object_from_file(object_key, str(path))
        logger.info(f"Uploaded {path.name} -> {object_key}")

        if self.custom_domain:
            return f"https://{self.custom_domain}/{object_key}"

        endpoint_host = self.endpoint.replace("https://", "").replace("http://", "")
        return f"https://{self.bucket_name}.{endpoint_host}/{object_key}"

    def upload_batch(self, local_paths: list[str | Path]) -> list[str]:
        """批量上传，返回 URL 列表。"""
        urls = []
        for p in local_paths:
            try:
                url = self.upload(p)
                urls.append(url)
            except Exception as e:
                logger.error(f"Failed to upload {p}: {e}")
        return urls
