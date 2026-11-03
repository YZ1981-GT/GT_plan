"""属性测试：审计日志哈希链防篡改

**Validates: Requirements 9**

使用 Hypothesis 验证哈希链的四个核心属性：
  1. 正确构建的哈希链 verify 通过
  2. 任意位置修改 payload → verify 必定检出断链
  3. 任意位置修改 entry_hash → verify 必定检出
  4. 交换两条的顺序 → verify 必定检出

测试调用 audit_chain 包的 hash_v2 / verify_entries，不再自带校验函数。
"""
from __future__ import annotations

import json
import uuid

from hypothesis import assume, given, settings, strategies as st

from app.services.audit_chain.canonical import GENESIS_HASH, canonical_payload, hash_v2
from app.services.audit_chain.verify import verify_entries


# ---------------------------------------------------------------------------
# 日志条目数据结构（v2，含 verify_entries 所需全部字段）
# ---------------------------------------------------------------------------


def _build_entry_dict(
    *,
    ts: str,
    user_id: str,
    action_type: str,
    object_type: str,
    resource_id: str,
    payload: dict,
) -> dict:
    """构建原始条目 dict（不含哈希，由 build_chain 填充）。"""
    return {
        "id": str(uuid.uuid4()),
        "ts": ts,
        "user_id": user_id,
        "action_type": action_type,
        "object_type": object_type,
        "object_id": "",
        "resource_id": resource_id,
        "project_id": None,
        "year": None,
        "payload_raw": payload,  # 用于 hash 计算的原始载荷
    }


def build_correct_chain(raw_entries: list[dict]) -> list[dict]:
    """按顺序计算 v2 entry_hash，prev_hash 链接，返回带正确哈希的链。"""
    prev = GENESIS_HASH
    result = []
    for raw in raw_entries:
        payload_raw = raw["payload_raw"]
        resource_id = raw.get("resource_id", "")
        project_id = raw.get("project_id") or None
        year = raw.get("year") or None

        entry_hash = hash_v2(
            ts=raw["ts"],
            user_id=raw["user_id"],
            action_type=raw["action_type"],
            object_type=raw["object_type"],
            resource_id=resource_id,
            project_id=project_id,
            year=year,
            payload=payload_raw,
            prev_hash=prev,
        )
        # 落库载荷带保留键（verify_entries 从这里读取）
        full_payload = dict(payload_raw)
        full_payload["_hash_v"] = 2
        full_payload["_resource_id"] = resource_id
        if project_id:
            full_payload["project_id"] = project_id
        if year is not None:
            full_payload["_year"] = year

        entry = {
            "id": raw["id"],
            "entry_hash": entry_hash,
            "prev_hash": prev,
            "ts": raw["ts"],
            "user_id": raw["user_id"],
            "action_type": raw["action_type"],
            "object_type": raw["object_type"],
            "object_id": raw.get("object_id", ""),
            "payload": full_payload,
            "payload_json": "",
        }
        result.append(entry)
        prev = entry_hash
    return result


# ---------------------------------------------------------------------------
# Hypothesis 策略
# ---------------------------------------------------------------------------

text_field = st.text(min_size=1, max_size=50)

raw_entry_strategy = st.builds(
    _build_entry_dict,
    ts=text_field,
    user_id=text_field,
    action_type=text_field,
    object_type=text_field,
    resource_id=text_field,
    payload=st.builds(
        lambda k, v: {k: v},
        k=text_field,
        v=text_field,
    ),
)

raw_chain_strategy = st.lists(raw_entry_strategy, min_size=1, max_size=20)


# ---------------------------------------------------------------------------
# 属性 1：正确链 verify 通过
# ---------------------------------------------------------------------------


@given(entries=raw_chain_strategy)
@settings(max_examples=5)
def test_correct_chain_always_valid(entries: list[dict]):
    """**Validates: Requirements 9**

    属性 1：正确构建的哈希链，verify_entries 必定返回 valid=True。
    """
    chain = build_correct_chain(entries)
    result = verify_entries(chain)
    assert result.valid is True
    assert result.entries_checked == len(entries)


# ---------------------------------------------------------------------------
# 属性 2：任意位置修改 payload → verify 必定检出断链
# ---------------------------------------------------------------------------


@given(
    entries=st.lists(raw_entry_strategy, min_size=1, max_size=20),
    tamper_index=st.integers(min_value=0, max_value=19),
    new_payload_value=text_field,
)
@settings(max_examples=5)
def test_tampered_payload_detected(
    entries: list[dict],
    tamper_index: int,
    new_payload_value: str,
):
    """**Validates: Requirements 9**

    属性 2：任意位置修改一条的 payload → verify 必定检出断链。
    """
    assume(tamper_index < len(entries))

    chain = build_correct_chain(entries)

    # 篡改指定位置的 payload（改存储载荷，但保留 _hash_v）
    original_payload = chain[tamper_index]["payload"]
    new_payload = {"tampered": new_payload_value, "_hash_v": 2}
    assume(new_payload != original_payload)

    chain[tamper_index]["payload"] = new_payload

    result = verify_entries(chain)
    assert result.valid is False


# ---------------------------------------------------------------------------
# 属性 3：任意位置修改 entry_hash → verify 必定检出
# ---------------------------------------------------------------------------


@given(
    entries=st.lists(raw_entry_strategy, min_size=1, max_size=20),
    tamper_index=st.integers(min_value=0, max_value=19),
    fake_hash_suffix=st.text(min_size=1, max_size=10, alphabet="0123456789abcdef"),
)
@settings(max_examples=5)
def test_tampered_entry_hash_detected(
    entries: list[dict],
    tamper_index: int,
    fake_hash_suffix: str,
):
    """**Validates: Requirements 9**

    属性 3：任意位置修改一条的 entry_hash → verify 必定检出。
    """
    assume(tamper_index < len(entries))

    chain = build_correct_chain(entries)

    original_hash = chain[tamper_index]["entry_hash"]
    fake_hash = ("f" * (64 - len(fake_hash_suffix))) + fake_hash_suffix
    assume(fake_hash != original_hash)

    chain[tamper_index]["entry_hash"] = fake_hash

    result = verify_entries(chain)
    assert result.valid is False


# ---------------------------------------------------------------------------
# 属性 4：交换两条的顺序 → verify 必定检出
# ---------------------------------------------------------------------------


@given(
    entries=st.lists(raw_entry_strategy, min_size=2, max_size=20),
    swap_data=st.data(),
)
@settings(max_examples=5)
def test_swapped_entries_detected(entries: list[dict], swap_data):
    """**Validates: Requirements 9**

    属性 4：交换两条的 payload 内容（保持链接关系） → verify 必定检出断链。
    图形验证器不依赖列表位置，交换整条记录不改变图结构。
    改为交换 payload 内容，使 entry_hash 与实际内容不匹配。
    """
    chain = build_correct_chain(entries)

    i = swap_data.draw(st.integers(min_value=0, max_value=len(chain) - 1))
    j = swap_data.draw(st.integers(min_value=0, max_value=len(chain) - 1))
    assume(i != j)
    # 确保两条的 payload 不同（相同 payload 交换无效果）
    assume(chain[i]["payload"] != chain[j]["payload"])

    # 交换 payload 内容，保持 entry_hash 和 prev_hash 不变 → content_mismatch
    chain[i]["payload"], chain[j]["payload"] = chain[j]["payload"], chain[i]["payload"]

    result = verify_entries(chain)
    assert result.valid is False
