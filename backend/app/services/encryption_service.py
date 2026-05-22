"""EncryptionService — 敏感数据加密服务

Phase 8 Task 10.1: 数据加密
使用 Fernet 对称加密（基于 AES-128-CBC + HMAC-SHA256）。
"""

import base64
import hashlib
import os


class EncryptionService:
    """敏感数据加密/解密服务。

    使用 Fernet 兼容的加密方案。
    如果 cryptography 库不可用，降级为 base64 编码（仅开发环境）。
    """

    def __init__(self, key: str = ""):
        self._key = key
        self._fernet = None
        if key:
            try:
                from cryptography.fernet import Fernet

                # Derive a valid Fernet key from arbitrary string
                derived = base64.urlsafe_b64encode(
                    hashlib.sha256(key.encode()).digest()
                )
                self._fernet = Fernet(derived)
            except ImportError:
                # cryptography not installed - use fallback
                self._fernet = None

    @property
    def is_available(self) -> bool:
        """是否可用（有密钥配置）。"""
        return bool(self._key)

    def encrypt(self, data: str | bytes) -> str:
        """加密数据，返回 base64 编码的密文。"""
        if not self._key:
            raise ValueError("Encryption key not configured")

        if isinstance(data, str):
            data = data.encode("utf-8")

        if self._fernet:
            return self._fernet.encrypt(data).decode("utf-8")
        else:
            # Fallback: simple base64 (NOT secure, dev only)
            return base64.urlsafe_b64encode(data).decode("utf-8")

    def decrypt(self, encrypted: str) -> str:
        """解密数据，返回明文字符串。"""
        if not self._key:
            raise ValueError("Encryption key not configured")

        if self._fernet:
            return self._fernet.decrypt(encrypted.encode("utf-8")).decode("utf-8")
        else:
            # Fallback: simple base64
            return base64.urlsafe_b64decode(encrypted.encode("utf-8")).decode("utf-8")

    def encrypt_bytes(self, data: bytes) -> str:
        """加密字节数据，返回 base64 编码的密文。"""
        if not self._key:
            raise ValueError("Encryption key not configured")

        if self._fernet:
            return self._fernet.encrypt(data).decode("utf-8")
        else:
            return base64.urlsafe_b64encode(data).decode("utf-8")

    def decrypt_bytes(self, encrypted: str) -> bytes:
        """解密数据，返回原始字节。"""
        if not self._key:
            raise ValueError("Encryption key not configured")

        if self._fernet:
            return self._fernet.decrypt(encrypted.encode("utf-8"))
        else:
            return base64.urlsafe_b64decode(encrypted.encode("utf-8"))

    @staticmethod
    def generate_key() -> str:
        """生成随机加密密钥。"""
        try:
            from cryptography.fernet import Fernet

            return Fernet.generate_key().decode("utf-8")
        except ImportError:
            # Fallback: random 32 bytes base64
            return base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8")
