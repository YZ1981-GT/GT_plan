"""EncryptionService 缺 cryptography 时必须 fail-closed（spec environment-hygiene-deps-and-scratch-schemas Req 5.1）。

旧实现：``from cryptography.fernet import Fernet`` 失败 ⇒ 静默改用 base64 编码，
``encrypt()`` 返回的「密文」任何人都能直接 ``urlsafe_b64decode`` 还原。
缺包用 ``sys.modules`` 置 None 模拟（import 即抛 ImportError），不卸载真包。
"""
from __future__ import annotations

import base64
import sys

import pytest

from app.services.encryption_service import EncryptionService


@pytest.fixture
def no_cryptography(monkeypatch):
    for name in ("cryptography", "cryptography.fernet"):
        monkeypatch.setitem(sys.modules, name, None)


def test_configured_key_without_cryptography_refuses_to_construct(no_cryptography):
    with pytest.raises(RuntimeError, match="未安装 cryptography"):
        EncryptionService(key="k")


def test_no_key_still_constructs_and_refuses_to_encrypt(no_cryptography):
    svc = EncryptionService(key="")
    assert not svc.is_available
    for call in (lambda: svc.encrypt("x"), lambda: svc.decrypt("x"),
                 lambda: svc.encrypt_bytes(b"x"), lambda: svc.decrypt_bytes("x")):
        with pytest.raises(ValueError, match="not configured"):
            call()


def test_ciphertext_is_not_a_reversible_encoding():
    """正向对照：真加密的输出不能被 base64 直接还原成明文（旧降级正是这种形态）。"""
    svc = EncryptionService(key="k")
    token = svc.encrypt("敏感数据")
    assert "敏感数据".encode("utf-8") not in base64.urlsafe_b64decode(token.encode("utf-8"))
    assert svc.decrypt(token) == "敏感数据"


def test_generate_key_fallback_is_a_valid_32_byte_key(no_cryptography):
    raw = base64.urlsafe_b64decode(EncryptionService.generate_key())
    assert len(raw) == 32
