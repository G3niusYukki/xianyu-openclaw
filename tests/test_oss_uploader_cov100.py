from __future__ import annotations

import os
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.modules.listing.oss_uploader import OSSUploader


class TestOSSUploaderInit:
    def test_init_with_config(self):
        cfg = {
            "access_key_id": "ak",
            "access_key_secret": "sk",
            "bucket": "mybucket",
            "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
            "prefix": "img/",
            "custom_domain": "cdn.example.com",
        }
        u = OSSUploader(cfg)
        assert u.access_key_id == "ak"
        assert u.access_key_secret == "sk"
        assert u.bucket_name == "mybucket"
        assert u.endpoint == "https://oss-cn-hangzhou.aliyuncs.com"
        assert u.prefix == "img/"
        assert u.custom_domain == "cdn.example.com"

    def test_init_from_env(self, monkeypatch):
        monkeypatch.setenv("OSS_ACCESS_KEY_ID", "eak")
        monkeypatch.setenv("OSS_ACCESS_KEY_SECRET", "esk")
        monkeypatch.setenv("OSS_BUCKET", "ebucket")
        monkeypatch.setenv("OSS_ENDPOINT", "https://oss.example.com")
        u = OSSUploader()
        assert u.access_key_id == "eak"
        assert u.access_key_secret == "esk"
        assert u.bucket_name == "ebucket"
        assert u.endpoint == "https://oss.example.com"
        assert u.prefix == "xianyu/listing/"
        assert u.custom_domain == ""

    def test_init_defaults(self, monkeypatch):
        monkeypatch.delenv("OSS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("OSS_ACCESS_KEY_SECRET", raising=False)
        monkeypatch.delenv("OSS_BUCKET", raising=False)
        monkeypatch.delenv("OSS_ENDPOINT", raising=False)
        u = OSSUploader()
        assert u.access_key_id == ""
        assert u._bucket is None


class TestConfiguredProperty:
    def test_configured_true(self):
        u = OSSUploader({"access_key_id": "a", "access_key_secret": "b", "bucket": "c", "endpoint": "d"})
        assert u.configured is True

    def test_configured_false_missing_key(self):
        u = OSSUploader({"access_key_id": "a"})
        assert u.configured is False


class TestGetBucket:
    def test_cached_bucket(self):
        u = OSSUploader()
        sentinel = object()
        u._bucket = sentinel
        assert u._get_bucket() is sentinel

    def test_creates_bucket_with_oss2(self):
        fake_oss2 = types.ModuleType("oss2")
        mock_auth = MagicMock()
        mock_bucket = MagicMock()
        fake_oss2.Auth = MagicMock(return_value=mock_auth)
        fake_oss2.Bucket = MagicMock(return_value=mock_bucket)

        u = OSSUploader({"access_key_id": "ak", "access_key_secret": "sk", "bucket": "bk", "endpoint": "ep"})
        with patch.dict("sys.modules", {"oss2": fake_oss2}):
            result = u._get_bucket()
        assert result is mock_bucket
        fake_oss2.Auth.assert_called_once_with("ak", "sk")
        fake_oss2.Bucket.assert_called_once_with(mock_auth, "ep", "bk")

    def test_raises_when_oss2_missing(self):
        u = OSSUploader({"access_key_id": "ak", "access_key_secret": "sk", "bucket": "bk", "endpoint": "ep"})
        with patch.dict("sys.modules", {"oss2": None}):
            with pytest.raises(RuntimeError, match="oss2 package is required"):
                u._get_bucket()


class TestUpload:
    def test_upload_not_configured(self, tmp_path):
        u = OSSUploader()
        with pytest.raises(ValueError, match="OSS not configured"):
            u.upload(tmp_path / "x.png")

    def test_upload_file_not_found(self):
        u = OSSUploader({"access_key_id": "a", "access_key_secret": "b", "bucket": "c", "endpoint": "d"})
        with pytest.raises(FileNotFoundError):
            u.upload("/nonexistent/file.png")

    def test_upload_success_custom_domain(self, tmp_path):
        f = tmp_path / "img.png"
        f.write_bytes(b"\x89PNG")
        u = OSSUploader({
            "access_key_id": "a", "access_key_secret": "b",
            "bucket": "c", "endpoint": "https://oss.example.com",
            "custom_domain": "cdn.example.com",
        })
        mock_bucket = MagicMock()
        u._bucket = mock_bucket
        url = u.upload(f)
        assert url.startswith("https://cdn.example.com/")
        mock_bucket.put_object_from_file.assert_called_once()

    def test_upload_success_no_custom_domain(self, tmp_path):
        f = tmp_path / "img.jpg"
        f.write_bytes(b"\xff\xd8")
        u = OSSUploader({
            "access_key_id": "a", "access_key_secret": "b",
            "bucket": "mybkt", "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
        })
        mock_bucket = MagicMock()
        u._bucket = mock_bucket
        url = u.upload(f)
        assert "mybkt.oss-cn-hangzhou.aliyuncs.com" in url
        assert url.endswith(".jpg")

    def test_upload_no_extension(self, tmp_path):
        f = tmp_path / "noext"
        f.write_bytes(b"data")
        u = OSSUploader({
            "access_key_id": "a", "access_key_secret": "b",
            "bucket": "bk", "endpoint": "https://oss.example.com",
        })
        u._bucket = MagicMock()
        url = u.upload(f)
        assert url.endswith(".png") or "noext" not in url


class TestUploadBatch:
    def test_batch_success_and_failure(self, tmp_path):
        f1 = tmp_path / "a.png"
        f1.write_bytes(b"\x89PNG")
        f2 = tmp_path / "b.png"
        f2.write_bytes(b"\x89PNG")

        u = OSSUploader({
            "access_key_id": "a", "access_key_secret": "b",
            "bucket": "bk", "endpoint": "https://oss.example.com",
        })
        mock_bucket = MagicMock()
        mock_bucket.put_object_from_file.side_effect = [None, Exception("boom")]
        u._bucket = mock_bucket
        urls = u.upload_batch([str(f1), str(f2)])
        assert len(urls) == 1

    def test_batch_empty(self):
        u = OSSUploader({
            "access_key_id": "a", "access_key_secret": "b",
            "bucket": "bk", "endpoint": "https://oss.example.com",
        })
        u._bucket = MagicMock()
        assert u.upload_batch([]) == []
