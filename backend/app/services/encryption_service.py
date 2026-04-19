"""数据加密服务 — Fernet 对称加密

Phase 8 Task 10.1: 数据加密
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os

logger = logging.getLogger(__name__)


class EncryptionService:
    """Fernet 对称加密服务。"""

    def __init__(self, key: str | None = None):
        self._key = key or self._get_key_from_config()
        self._cipher = None
        if self._key:
            self._init_cipher()

    def _get_key_from_config(self) -> str:
        """从配置获取加密密钥。"""
        try:
            from app.core.config import settings
            return settings.ENCRYPTION_KEY
        except Exception:
            return ""

    def _init_cipher(self):
        """初始化 Fernet cipher。"""
        try:
            from cryptography.fernet import Fernet
            # Ensure key is valid Fernet key (32 url-safe base64 bytes)
            if len(self._key) < 32:
                # Derive a proper key from the provided string
                key_bytes = hashlib.sha256(self._key.encode()).digest()
                fernet_key = base64.urlsafe_b64encode(key_bytes)
            else:
                fernet_key = self._key.encode() if isinstance(self._key, str) else self._key
            self._cipher = Fernet(fernet_key)
        except ImportError:
            logger.warning("cryptography 库未安装，加密功能不可用")
            self._cipher = None
        except Exception as e:
            logger.warning("Fernet 初始化失败: %s", e)
            self._cipher = None

    @property
    def is_available(self) -> bool:
        return self._cipher is not None

    def encrypt(self, data: str) -> str:
        """加密字符串，返回 base64 编码的密文。"""
        if not self._cipher:
            raise RuntimeError("加密服务不可用（密钥未配置或 cryptography 未安装）")
        return self._cipher.encrypt(data.encode("utf-8")).decode("utf-8")

    def decrypt(self, encrypted: str) -> str:
        """解密 base64 编码的密文。"""
        if not self._cipher:
            raise RuntimeError("加密服务不可用")
        return self._cipher.decrypt(encrypted.encode("utf-8")).decode("utf-8")

    def encrypt_bytes(self, data: bytes) -> bytes:
        """加密字节数据。"""
        if not self._cipher:
            raise RuntimeError("加密服务不可用")
        return self._cipher.encrypt(data)

    def decrypt_bytes(self, encrypted: bytes) -> bytes:
        """解密字节数据。"""
        if not self._cipher:
            raise RuntimeError("加密服务不可用")
        return self._cipher.decrypt(encrypted)

    @staticmethod
    def generate_key() -> str:
        """生成新的 Fernet 密钥。"""
        try:
            from cryptography.fernet import Fernet
            return Fernet.generate_key().decode("utf-8")
        except ImportError:
            # Fallback: generate a base64-encoded 32-byte key
            return base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8")
