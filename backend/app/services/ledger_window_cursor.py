"""Versioned, signed Ledger keyset cursor.

Unlike a count token, an invalid Ledger cursor fails visibly: silently restarting
at page one can duplicate rows in an audit export or mix active datasets.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException

_VERSION = 1
_TTL_SECONDS = 1800
_CONTEXT = b"gt-ledger-window-cursor-v1"


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _canonical(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (date, datetime, Decimal)):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return str(value)


def query_fingerprint(payload: dict[str, Any]) -> str:
    raw = json.dumps(_canonical(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _key() -> bytes:
    from app.core.config import settings

    return hmac.new(settings.JWT_SECRET_KEY.encode("utf-8"), _CONTEXT, hashlib.sha256).digest()


def issue(payload: dict[str, Any], *, now: int | None = None) -> str:
    body = {**_canonical(payload), "v": _VERSION,
            "exp": int(time.time() if now is None else now) + _TTL_SECONDS}
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(_key(), raw, hashlib.sha256).digest()
    return f"{_b64encode(raw)}.{_b64encode(signature)}"


def _error(code: str, message: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail={"error_code": code, "message": message})


def decode(
    token: str,
    *,
    subject: str,
    fingerprint: str,
    dataset_id: str,
    now: int | None = None,
) -> dict[str, Any]:
    try:
        payload_part, signature_part = token.split(".", 1)
        raw, signature = _b64decode(payload_part), _b64decode(signature_part)
        if _b64encode(raw) != payload_part or _b64encode(signature) != signature_part:
            raise ValueError("non-canonical base64")
        expected = hmac.new(_key(), raw, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        payload = json.loads(raw.decode("utf-8"))
        current = int(time.time() if now is None else now)
        if payload.get("v") != _VERSION or int(payload.get("exp", 0)) < current:
            raise ValueError("expired or unsupported")
        if payload.get("s") != subject:
            raise ValueError("wrong subject")
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("LEDGER_CURSOR_INVALID", "翻页游标无效或已过期，请刷新后重试") from exc
    if payload.get("q") != fingerprint:
        raise _error("LEDGER_CURSOR_QUERY_MISMATCH", "查询条件已变化，请从第一页重新查询", 409)
    if payload.get("d") != dataset_id:
        raise _error("LEDGER_SNAPSHOT_CHANGED", "生效数据集已切换，请从第一页重新查询", 409)
    return payload
