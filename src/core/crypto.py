"""
敏感数据加密模块
Sensitive Data Encryption

提供 Cookie 等敏感信息的加密/解密能力，使用 Fernet 对称加密。
密钥来自环境变量 ENCRYPTION_KEY，首次运行时自动生成。
"""

import base64
import hashlib
import os
from pathlib import Path

from src.core.logger import get_logger

logger = get_logger()

_KEY_ENV = "ENCRYPTION_KEY"
_KEY_FILE = "data/.encryption_key"


def _derive_key(passphrase: str) -> bytes:
    """从口令派生 32 字节 Fernet 密钥"""
    digest = hashlib.sha256(passphrase.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_or_create_key() -> bytes:
    """获取或创建加密密钥"""
    env_key = os.getenv(_KEY_ENV)
    if env_key:
        return _derive_key(env_key)

    key_path = Path(_KEY_FILE)
    if key_path.exists():
        # 检查文件权限，确保只有所有者可读写
        try:
            import stat

            file_stat = key_path.stat()
            file_mode = stat.filemode(file_stat.st_mode)
            # 检查是否过于宽松（组或其他用户有读写权限）
            if file_stat.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
                logger.warning(
                    f"Key file {_KEY_FILE} has overly permissive permissions ({file_mode}). Run: chmod 600 {_KEY_FILE}"
                )
        except Exception as e:
            logger.debug(f"Could not check key file permissions: {e}")
        return key_path.read_bytes().strip()

    try:
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
    except ImportError:
        key = base64.urlsafe_b64encode(os.urandom(32))

    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(key)

    # 设置安全的文件权限（仅所有者可读写）
    try:
        import stat

        key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
        logger.info(f"Generated new encryption key (saved to {_KEY_FILE} with permissions 600)")
    except Exception as e:
        logger.warning(f"Could not set restrictive permissions on key file: {e}")
        logger.info(f"Generated new encryption key (saved to {_KEY_FILE})")

    return key


def encrypt_value(plaintext: str) -> str:
    """加密字符串，返回 base64 编码的密文"""
    try:
        from cryptography.fernet import Fernet

        f = Fernet(_get_or_create_key())
        return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    except ImportError:
        logger.warning("cryptography 未安装，Cookie 将以明文存储。建议执行: pip install cryptography")
        return plaintext


def decrypt_value(ciphertext: str) -> str:
    """解密 base64 编码的密文，返回明文"""
    try:
        from cryptography.fernet import Fernet

        f = Fernet(_get_or_create_key())
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except ImportError:
        logger.warning("cryptography 未安装，Cookie 将以明文存储。建议执行: pip install cryptography")
        return ciphertext
    except Exception:
        return ciphertext


def is_encrypted(value: str) -> bool:
    """检查值是否已加密（Fernet 密文以 gAAAAA 开头）"""
    return value.startswith("gAAAAA")


def ensure_encrypted(value: str) -> str:
    """如果值未加密则加密，已加密则返回原值"""
    if not value or is_encrypted(value):
        return value
    return encrypt_value(value)


def ensure_decrypted(value: str) -> str:
    """如果值已加密则解密，未加密则返回原值"""
    if not value or not is_encrypted(value):
        return value
    return decrypt_value(value)
