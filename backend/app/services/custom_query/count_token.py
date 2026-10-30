"""翻页查询的精确 COUNT 凭证（platform-performance-user-experience-closure 任务 9）。

第 1 页照常在库里 COUNT，并签发凭证；同一查询的后续页带回凭证即可跳过重复 COUNT。改造前每翻一页都重数一次
（和平药房 2025 辅助明细科目 1002：补索引前冷 COUNT 约 73 秒）。

凭证不是客户端说了算的 total：

- 摘要覆盖 **计数 SQL 原文 + 展开后的全部绑定参数 + 调用者身份**，换了筛选 / 排序以外的任何条件、换了项目 / 年度 /
  生效数据集、换了用户，摘要都变，凭证即失效；
- HMAC 签名，密钥由 ``JWT_SECRET_KEY`` 派生（与 JWT 不同上下文，凭证不能当令牌用，反之亦然）；
- 有效期 600 秒；版本号不符、非规范 base64、签名不符、过期一律视为没带，照常计数，绝不报错。

凭证只省一次 COUNT，不绕过任何权限判定：鉴权、作用域与取数照常在每一页执行。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from sqlalchemy.sql import Select

_TOKEN_VERSION = 1
_TOKEN_TTL_SECONDS = 600
_MAX_TOKEN_CHARS = 2048
_CONTEXT = b"gt-custom-query-count-v1"


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _canonical(value: Any) -> Any:
    """绑定参数的稳定 JSON 形态（字典按键排序；日期、Decimal、UUID 等按字符串）。"""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_canonical(v) for v in value]
    return str(value)


def subject_of(user: Any) -> str:
    """凭证绑定的调用者身份（用户 id；内部调用没有用户时为空串）。"""
    return str(getattr(user, "id", "") or "")


def statement_digest(stmt: Select, bind: Any, *, subject: str) -> str:
    """计数语句的摘要：按当前方言编译（展开 IN 列表）后的 SQL、全部绑定参数与调用者身份。"""
    compiled = stmt.compile(
        dialect=bind.dialect,
        compile_kwargs={"render_postcompile": True},
    )
    body = {
        "sql": str(compiled),
        "params": _canonical(compiled.params),
        "subject": subject,
    }
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _key() -> bytes:
    from app.core.config import settings

    return hmac.new(settings.JWT_SECRET_KEY.encode("utf-8"), _CONTEXT, hashlib.sha256).digest()


def issue(*, digest: str, total: int, subject: str, now: int | None = None) -> str:
    """签发凭证：``base64url(载荷).base64url(HMAC)``。"""
    issued_at = int(time.time() if now is None else now)
    payload = {
        "v": _TOKEN_VERSION,
        "d": digest,
        "n": int(total),
        "s": subject,
        "exp": issued_at + _TOKEN_TTL_SECONDS,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{_b64encode(raw)}.{_b64encode(hmac.new(_key(), raw, hashlib.sha256).digest())}"


def reuse(token: str | None, *, digest: str, subject: str, now: int | None = None) -> int | None:
    """凭证有效且与本次查询、调用者一致时返回签发时的精确 total，否则返回 None（调用方照常计数）。"""
    if not token or len(token) > _MAX_TOKEN_CHARS:
        return None
    try:
        payload_part, signature_part = token.split(".", 1)
        raw = _b64decode(payload_part)
        signature = _b64decode(signature_part)
        # 只认规范编码：base64 尾部填充位可变，不规范化就会出现「改了一个字符签名照样对」
        if _b64encode(raw) != payload_part or _b64encode(signature) != signature_part:
            return None
        if not hmac.compare_digest(signature, hmac.new(_key(), raw, hashlib.sha256).digest()):
            return None
        payload = json.loads(raw.decode("utf-8"))
        current = int(time.time() if now is None else now)
        if payload.get("v") != _TOKEN_VERSION or int(payload.get("exp", 0)) < current:
            return None
        if payload.get("d") != digest or payload.get("s") != subject:
            return None
        total = int(payload["n"])
        return total if total >= 0 else None
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError):
        return None
