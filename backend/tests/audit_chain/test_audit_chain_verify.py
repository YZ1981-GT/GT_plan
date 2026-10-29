"""审计链校验 — verify_entries 单元测试（无 DB）

覆盖九种场景：正确链、missing_prefix、fork、fork_acknowledged、orphan、
content_mismatch_v2、legacy_verified、legacy_unverifiable、空链。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from tests.audit_chain.conftest import build_v2_chain

from app.services.audit_chain.canonical import GENESIS_HASH, hash_v1
from app.services.audit_chain.verify import VerifyResult, verify_entries


def _make_raw_entries(n: int = 5) -> list[dict]:
    """生成 n 条原始条目数据。"""
    ts_base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [
        {
            "id": str(uuid.uuid4()),
            "ts": (ts_base.replace(second=i)).isoformat(timespec="microseconds"),
            "user_id": "user1",
            "action_type": "test.action",
            "object_type": "test_object",
            "resource_id": f"res-{i}",
            "payload": {"index": i, "value": f"v{i}"},
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# (a) 正确 v2 链 → valid
# ---------------------------------------------------------------------------


def test_correct_v2_chain_valid():
    chain = build_v2_chain(_make_raw_entries(5))
    result = verify_entries(chain)
    assert isinstance(result, VerifyResult)
    assert result.valid is True
    assert result.entries_checked == 5
    assert result.legacy_verified == 0
    assert result.problems == []


# ---------------------------------------------------------------------------
# (b) missing_prefix — 没有创世条目
# ---------------------------------------------------------------------------


def test_missing_prefix():
    chain = build_v2_chain(_make_raw_entries(3))
    # 把首条的 prev_hash 改成非创世值
    chain[0]["prev_hash"] = "a" * 64
    result = verify_entries(chain)
    assert result.valid is False
    assert any(p["type"] == "missing_prefix" for p in result.problems)


# ---------------------------------------------------------------------------
# (c) fork — 同一 prev_hash 有两个后继
# ---------------------------------------------------------------------------


def test_fork_detected():
    chain = build_v2_chain(_make_raw_entries(3))
    # 新增一条与 chain[1] 同 prev_hash 的条目（分叉）
    fork_entry = dict(chain[1])
    fork_entry["id"] = str(uuid.uuid4())
    fork_entry["entry_hash"] = "f" * 64  # 不同的哈希
    chain.append(fork_entry)

    result = verify_entries(chain)
    assert result.valid is False
    assert any(p["type"] == "fork" for p in result.problems)


# ---------------------------------------------------------------------------
# (d) fork_acknowledged — 分叉已确认
# ---------------------------------------------------------------------------


def test_fork_acknowledged():
    chain = build_v2_chain(_make_raw_entries(3))
    fork_entry = dict(chain[1])
    fork_entry["id"] = str(uuid.uuid4())
    fork_entry["entry_hash"] = "f" * 64
    chain.append(fork_entry)

    # 提供 fork_ack_dead_ids 排除分叉条目
    result = verify_entries(chain, fork_ack_dead_ids={fork_entry["id"]})
    # 分叉已确认后不应再报 fork
    fork_problems = [p for p in result.problems if p["type"] == "fork"]
    assert len(fork_problems) == 0


# ---------------------------------------------------------------------------
# (e) orphan — prev_hash 不在链内且不是 GENESIS
# ---------------------------------------------------------------------------


def test_orphan_detected():
    chain = build_v2_chain(_make_raw_entries(2))
    # 添加一个 prev_hash 指向不存在的哈希的条目
    orphan = {
        "id": str(uuid.uuid4()),
        "entry_hash": "e" * 64,
        "prev_hash": "d" * 64,  # 链内不存在
        "ts": "2025-01-01T00:00:05.000000+00:00",
        "user_id": "user1",
        "action_type": "test.action",
        "object_type": "test_object",
        "object_id": "",
        "payload": {"_hash_v": 2},
        "payload_json": "",
    }
    chain.append(orphan)

    result = verify_entries(chain)
    assert any(p["type"] == "orphan" for p in result.problems)


# ---------------------------------------------------------------------------
# (f) content_mismatch_v2 — entry_hash 错误
# ---------------------------------------------------------------------------


def test_content_mismatch_v2():
    chain = build_v2_chain(_make_raw_entries(3))
    # 篡改 entry_hash
    chain[1]["entry_hash"] = "b" * 64
    result = verify_entries(chain)
    assert result.valid is False
    assert any(p["type"] == "content_mismatch" for p in result.problems)


# ---------------------------------------------------------------------------
# (g) legacy_verified — v1 条目正确哈希
# ---------------------------------------------------------------------------


def test_legacy_verified_count():
    """v1 条目正确哈希 → legacy_verified 计数。"""
    import json

    entries = []
    prev = GENESIS_HASH
    for i in range(3):
        eid = str(uuid.uuid4())
        ts = f"2025-01-01T00:00:0{i}"
        user_id = "user1"
        action_type = "test.action"
        object_id = str(uuid.uuid4())
        payload = {"idx": i}
        payload_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)

        entry_hash = hash_v1(ts, user_id, action_type, object_id, payload_json, prev)

        entries.append({
            "id": eid,
            "entry_hash": entry_hash,
            "prev_hash": prev,
            "ts": ts,
            "user_id": user_id,
            "action_type": action_type,
            "object_type": "test",
            "object_id": object_id,
            "payload": payload,  # 无 _hash_v → v1
            "payload_json": payload_json,
        })
        prev = entry_hash

    result = verify_entries(entries)
    assert result.valid is True
    assert result.legacy_verified == 3
    assert result.legacy_unverifiable == 0


# ---------------------------------------------------------------------------
# (h) legacy_unverifiable — v1 条目哈希不匹配
# ---------------------------------------------------------------------------


def test_legacy_unverifiable_count():
    """v1 条目哈希不一致 → legacy_unverifiable 计数，但 valid 仍 True。"""
    import json

    entries = []
    prev = GENESIS_HASH
    for i in range(2):
        eid = str(uuid.uuid4())
        ts = f"2025-01-01T00:00:0{i}"
        user_id = "user1"
        action_type = "test.action"
        object_id = str(uuid.uuid4())
        payload = {"idx": i}
        payload_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)

        # 故意用错误哈希
        entry_hash = "bad_hash_" + str(i).ljust(55, "0")

        entries.append({
            "id": eid,
            "entry_hash": entry_hash,
            "prev_hash": prev,
            "ts": ts,
            "user_id": user_id,
            "action_type": action_type,
            "object_type": "test",
            "object_id": object_id,
            "payload": payload,
            "payload_json": payload_json,
        })
        prev = entry_hash

    result = verify_entries(entries)
    assert result.valid is True  # legacy 不影响 valid
    assert result.legacy_unverifiable == 2
    assert result.legacy_verified == 0


# ---------------------------------------------------------------------------
# (i) 空链
# ---------------------------------------------------------------------------


def test_empty_chain():
    result = verify_entries([])
    assert result.valid is True
    assert result.entries_checked == 0
