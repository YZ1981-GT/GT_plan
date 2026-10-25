"""EncryptionService — 敏感数据加密服务

Phase 8 Task 10.1: 数据加密
使用 Fernet 对称加密（基于 AES-128-CBC + HMAC-SHA256）。

🔴 fail-closed（spec environment-hygiene-deps-and-scratch-schemas Requirement 5.1）：
旧实现在 ``cryptography`` 缺失时静默改用 **base64 编码**冒充加密（注释写「仅开发环境」，但没有任何
环境判断）—— 调用方拿到的「密文」任何人都能直接解码。现在配置了密钥却无法加密时，构造即抛错。
"""

import base64
import hashlib
import os


class EncryptionService:
    """敏感数据加密/解密服务（Fernet）。

    - 配置了密钥：必须能构造 Fernet，否则构造即抛 ``RuntimeError``（绝不降级为可逆编码）。
    - 未配置密钥：``is_available`` 为 False，任何加解密调用抛 ``ValueError``。
    """

    def __init__(self, key: str = ""):
        self._key = key
        self._fernet = None
        if key:
            try:
                from cryptography.fernet import Fernet
            except ImportError as exc:
                raise RuntimeError(
                    "EncryptionService：已配置密钥但未安装 cryptography，无法加密；"
                    "拒绝以 base64 等可逆编码冒充密文。"
                ) from exc
            # Derive a valid Fernet key from arbitrary string
            derived = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
            self._fernet = Fernet(derived)

    @property
    def is_available(self) -> bool:
        """是否可用（有密钥配置）。"""
        return bool(self._key)

    def _require_fernet(self):
        if not self._key:
            raise ValueError("Encryption key not configured")
        return self._fernet

    def encrypt(self, data: str | bytes) -> str:
        """加密数据，返回 base64 编码的密文。"""
        fernet = self._require_fernet()
        if isinstance(data, str):
            data = data.encode("utf-8")
        return fernet.encrypt(data).decode("utf-8")

    def decrypt(self, encrypted: str) -> str:
        """解密数据，返回明文字符串。"""
        return self._require_fernet().decrypt(encrypted.encode("utf-8")).decode("utf-8")

    def encrypt_bytes(self, data: bytes) -> str:
        """加密字节数据，返回 base64 编码的密文。"""
        return self._require_fernet().encrypt(data).decode("utf-8")

    def decrypt_bytes(self, encrypted: str) -> bytes:
        """解密数据，返回原始字节。"""
        return self._require_fernet().decrypt(encrypted.encode("utf-8"))

    @staticmethod
    def generate_key() -> str:
        """生成随机加密密钥。

        缺 cryptography 时的回退与 ``Fernet.generate_key()`` 同算法（32 字节 CSPRNG + urlsafe base64），
        不是安全降级。
        """
        try:
            from cryptography.fernet import Fernet

            return Fernet.generate_key().decode("utf-8")
        except ImportError:
            return base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8")
