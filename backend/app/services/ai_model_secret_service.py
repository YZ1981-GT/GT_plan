"""AI 模型凭证服务。

数据库只存带版本前缀的 Fernet 密文。明文只在写入加密和单次出站请求构造期间存在，
不得进入 ORM 响应、日志或异常文本。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from app.core.config import settings
from app.services.encryption_service import EncryptionService

_ENVELOPE_PREFIX = "v1:"


class CredentialEncryptionUnavailable(ValueError):
    """服务端未配置可用加密密钥。"""


class CredentialDecryptError(ValueError):
    """存量密文损坏、版本未知或密钥不匹配。"""


class _SecretModel(Protocol):
    api_key_ciphertext: str | None
    api_key_updated_at: datetime | None


def _encryption() -> EncryptionService:
    service = EncryptionService(settings.ENCRYPTION_KEY)
    if not service.is_available:
        raise CredentialEncryptionUnavailable(
            "服务端未配置 ENCRYPTION_KEY，拒绝保存外部模型 API Key"
        )
    return service


def encrypt_api_key(api_key: str) -> str:
    """加密非空 API Key，返回版本化 envelope。"""
    plaintext = str(api_key or "").strip()
    if not plaintext:
        raise ValueError("API Key 不能为空")
    return _ENVELOPE_PREFIX + _encryption().encrypt(plaintext)


def decrypt_api_key(ciphertext: str | None) -> str | None:
    """解密模型 Key；无密文返回 None，未知/损坏密文 fail-closed。"""
    if not ciphertext:
        return None
    if not ciphertext.startswith(_ENVELOPE_PREFIX):
        raise CredentialDecryptError("模型 API Key 密文版本未知，拒绝调用外部服务")
    token = ciphertext[len(_ENVELOPE_PREFIX):]
    try:
        return _encryption().decrypt(token)
    except CredentialEncryptionUnavailable:
        raise
    except Exception as exc:
        raise CredentialDecryptError(
            "模型 API Key 无法解密，拒绝调用外部服务"
        ) from exc


def apply_api_key_update(
    model: _SecretModel,
    *,
    api_key: str | None,
    clear_api_key: bool,
) -> bool:
    """应用 write-only Key 更新契约。

    - clear_api_key=True：显式清除；
    - api_key 非空白：替换为新密文；
    - 字段省略/None/空白：保留旧值。
    返回本次是否改变了凭证状态。
    """
    plaintext = str(api_key or "").strip()
    if clear_api_key and plaintext:
        raise ValueError("不能同时替换并清除 API Key")
    if clear_api_key:
        model.api_key_ciphertext = None
    elif plaintext:
        model.api_key_ciphertext = encrypt_api_key(plaintext)
    else:
        return False
    model.api_key_updated_at = datetime.now(timezone.utc)
    return True


def has_api_key(model: _SecretModel) -> bool:
    """仅暴露凭证是否存在，不暴露密文或可回写掩码。"""
    return bool(model.api_key_ciphertext)
