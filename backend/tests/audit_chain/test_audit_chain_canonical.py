"""审计链规范化与哈希 — 纯函数测试（无 DB）

覆盖 canonical_payload、hash_v2、hash_v1 的核心行为。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.services.audit_chain.canonical import (
    GENESIS_HASH,
    AuditPayloadError,
    canonical_payload,
    hash_v1,
    hash_v2,
)


# ---------------------------------------------------------------------------
# canonical_payload 测试
# ---------------------------------------------------------------------------


def test_canonical_float_1e20():
    """1e20 → 无科学记数法的定点字符串。"""
    result = canonical_payload(1e20)
    assert result == "100000000000000000000"


def test_canonical_float_0_1():
    """0.1 → 精确字符串。"""
    result = canonical_payload(0.1)
    assert result == "0.1"


def test_canonical_decimal():
    """Decimal 直接 format。"""
    result = canonical_payload(Decimal("3.14"))
    assert result == "3.14"


def test_canonical_nested():
    """嵌套 dict / list，混合类型全部规范化。"""
    uid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    dt = datetime(2025, 1, 15, 8, 30, 0, 123456, tzinfo=timezone.utc)
    obj = {
        "amount": 1e20,
        "rate": Decimal("0.05"),
        "id": uid,
        "ts": dt,
        "items": [1.5, Decimal("2.0")],
    }
    result = canonical_payload(obj)
    assert result["amount"] == "100000000000000000000"
    assert result["rate"] == "0.05"
    assert result["id"] == str(uid)
    assert result["ts"] == "2025-01-15T08:30:00.123456+00:00"
    assert result["items"] == ["1.5", "2.0"]


def test_canonical_nan_rejected():
    """NaN 必须被拒绝。"""
    with pytest.raises(AuditPayloadError, match="不可规范化"):
        canonical_payload(float("nan"))


def test_canonical_inf_rejected():
    """Inf 必须被拒绝。"""
    with pytest.raises(AuditPayloadError, match="不可规范化"):
        canonical_payload(float("inf"))


def test_canonical_uuid():
    """UUID 对象 → 字符串。"""
    uid = uuid.uuid4()
    assert canonical_payload(uid) == str(uid)


def test_canonical_datetime():
    """aware datetime → UTC ISO 微秒字符串。"""
    dt = datetime(2025, 6, 1, 12, 0, 0, 0, tzinfo=timezone.utc)
    result = canonical_payload(dt)
    assert result == "2025-06-01T12:00:00.000000+00:00"


# ---------------------------------------------------------------------------
# hash_v2 测试
# ---------------------------------------------------------------------------


def test_hash_v2_json_roundtrip():
    """v2 哈希：float 与其规范化字符串形式产生相同哈希。

    关键：1e20 (float) 和 "100000000000000000000" (字符串) 经 canonical_payload
    后都变成字符串 "100000000000000000000"，因此 hash_v2 结果一致。
    这保证了 JSONB 往返（将 1e20 存为 100000000000000000000 整数再读回）不影响哈希。
    """
    payload_float = {"amount": 1e20, "note": "test"}
    # 模拟规范化后的形态（字符串，与 canonical_payload(1e20) 一致）
    payload_canonical = {"amount": "100000000000000000000", "note": "test"}
    ts = "2025-01-15T08:30:00.000000+00:00"

    h1 = hash_v2(
        ts=ts, user_id="user1", action_type="formula.changed",
        object_type="report_config", resource_id="r1",
        project_id="proj1", year=2025, payload=payload_float,
        prev_hash=GENESIS_HASH,
    )

    h2 = hash_v2(
        ts=ts, user_id="user1", action_type="formula.changed",
        object_type="report_config", resource_id="r1",
        project_id="proj1", year=2025, payload=payload_canonical,
        prev_hash=GENESIS_HASH,
    )

    assert h1 == h2


# ---------------------------------------------------------------------------
# hash_v1 测试
# ---------------------------------------------------------------------------


def test_hash_v1_matches_legacy():
    """hash_v1 与 audit_log_helper._compute_entry_hash 公式一致。"""
    import hashlib

    ts = "2025-01-15T08:30:00"
    user_id = "user-abc"
    action_type = "formula_changed"
    object_id = "obj-123"
    payload_json = '{"key":"val"}'
    prev_hash = GENESIS_HASH

    # 手算预期值（与 helper 一致）
    raw = f"{ts}|{user_id or ''}|{action_type}|{object_id or ''}|{payload_json}|{prev_hash}"
    expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    result = hash_v1(ts, user_id, action_type, object_id, payload_json, prev_hash)
    assert result == expected


def test_hash_v1_empty_user_id():
    """hash_v1 user_id 为空/None 时用空字符串（含 or ''）。"""
    import hashlib

    ts = "2025-01-01T00:00:00"
    action_type = "test"
    payload_json = "{}"
    prev_hash = GENESIS_HASH

    raw = f"{ts}||{action_type}||{payload_json}|{prev_hash}"
    expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    assert hash_v1(ts, None, action_type, None, payload_json, prev_hash) == expected
    assert hash_v1(ts, "", action_type, "", payload_json, prev_hash) == expected
