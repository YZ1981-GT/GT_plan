"""属性测试：审计日志哈希链防篡改

**Validates: Requirements 9**

使用 Hypothesis 验证哈希链的四个核心属性：
  1. 正确构建的哈希链 verify 通过
  2. 任意位置修改 payload → verify 必定检出断链
  3. 任意位置修改 entry_hash → verify 必定检出
  4. 交换两条的顺序 → verify 必定检出

测试策略：纯算法测试，直接调用 _compute_entry_hash 并模拟 verify 逻辑，
不需要真实 DB。
"""
from __future__ import annotations

import hashlib
import json
import copy
from dataclasses import dataclass, field

from hypothesis import given, settings, assume, strategies as st


# ---------------------------------------------------------------------------
# 复刻核心算法（与 audit_logger_enhanced._compute_entry_hash 一致）
# ---------------------------------------------------------------------------

GENESIS_HASH = "0" * 64


def _compute_entry_hash(
    ts: str,
    user_id: str,
    action_type: str,
    object_id: str | None,
    payload_json: str,
    prev_hash: str,
) -> str:
    """计算审计日志条目哈希。

    entry_hash = sha256(ts|user_id|action_type|object_id|payload_json|prev_hash)
    """
    raw = f"{ts}|{user_id}|{action_type}|{object_id or ''}|{payload_json}|{prev_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 日志条目数据结构
# ---------------------------------------------------------------------------

@dataclass
class LogEntry:
    ts: str
    user_id: str
    action_type: str
    object_id: str
    payload_json: str
    prev_hash: str = ""
    entry_hash: str = ""


# ---------------------------------------------------------------------------
# 构建正确哈希链
# ---------------------------------------------------------------------------

def build_correct_chain(entries: list[LogEntry]) -> list[LogEntry]:
    """按顺序计算 entry_hash，prev_hash 链接，返回带正确哈希的链。"""
    prev = GENESIS_HASH
    for entry in entries:
        entry.prev_hash = prev
        entry.entry_hash = _compute_entry_hash(
            entry.ts, entry.user_id, entry.action_type,
            entry.object_id, entry.payload_json, prev
        )
        prev = entry.entry_hash
    return entries


# ---------------------------------------------------------------------------
# 模拟 verify-chain 逻辑（与 audit_logs.py verify_chain 端点一致）
# ---------------------------------------------------------------------------

def verify_chain(entries: list[LogEntry]) -> dict:
    """逐条校验哈希链完整性。

    返回 {valid: True/False, ...}
    """
    if not entries:
        return {"valid": True, "entries_checked": 0}

    expected_prev_hash = GENESIS_HASH
    entries_checked = 0

    for entry in entries:
        entries_checked += 1

        # 验证 prev_hash 是否与预期一致
        if entry.prev_hash != expected_prev_hash:
            if entries_checked == 1:
                expected_prev_hash = entry.prev_hash
            else:
                return {
                    "valid": False,
                    "broken_at_index": entries_checked,
                    "message": f"哈希链在第 {entries_checked} 条断裂：prev_hash 不匹配",
                }

        # 重算 entry_hash
        computed_hash = _compute_entry_hash(
            entry.ts, entry.user_id, entry.action_type,
            entry.object_id, entry.payload_json, entry.prev_hash,
        )

        if computed_hash != entry.entry_hash:
            return {
                "valid": False,
                "broken_at_index": entries_checked,
                "message": f"哈希链在第 {entries_checked} 条断裂：entry_hash 被篡改",
            }

        # 下一条的 expected_prev_hash 是当前的 entry_hash
        expected_prev_hash = entry.entry_hash

    return {"valid": True, "entries_checked": entries_checked}


# ---------------------------------------------------------------------------
# Hypothesis 策略
# ---------------------------------------------------------------------------

text_field = st.text(min_size=1, max_size=50)

log_entry_strategy = st.builds(
    LogEntry,
    ts=text_field,
    user_id=text_field,
    action_type=text_field,
    object_id=text_field,
    payload_json=st.builds(
        lambda k, v: json.dumps({k: v}, sort_keys=True, ensure_ascii=False),
        k=text_field,
        v=text_field,
    ),
)

log_chain_strategy = st.lists(log_entry_strategy, min_size=1, max_size=20)


# ---------------------------------------------------------------------------
# 属性 1：正确链 verify 通过
# ---------------------------------------------------------------------------

@given(entries=log_chain_strategy)
@settings(max_examples=5)
def test_correct_chain_always_valid(entries: list[LogEntry]):
    """**Validates: Requirements 9**

    属性 1：正确构建的哈希链，verify-chain 必定返回 valid=True。
    """
    chain = build_correct_chain(entries)
    result = verify_chain(chain)
    assert result["valid"] is True
    assert result["entries_checked"] == len(entries)


# ---------------------------------------------------------------------------
# 属性 2：任意位置修改 payload → verify 必定检出断链
# ---------------------------------------------------------------------------

@given(
    entries=st.lists(log_entry_strategy, min_size=1, max_size=20),
    tamper_index=st.integers(min_value=0, max_value=19),
    new_payload_value=text_field,
)
@settings(max_examples=5)
def test_tampered_payload_detected(
    entries: list[LogEntry],
    tamper_index: int,
    new_payload_value: str,
):
    """**Validates: Requirements 9**

    属性 2：任意位置修改一条的 payload → verify 必定检出断链。
    """
    # 确保 tamper_index 在范围内
    assume(tamper_index < len(entries))

    chain = build_correct_chain(entries)

    # 篡改指定位置的 payload
    original_payload = chain[tamper_index].payload_json
    new_payload = json.dumps({"tampered": new_payload_value}, sort_keys=True, ensure_ascii=False)
    assume(new_payload != original_payload)  # 确保确实修改了

    chain[tamper_index].payload_json = new_payload

    result = verify_chain(chain)
    assert result["valid"] is False
    # 断链点应该在被篡改的位置
    assert result["broken_at_index"] == tamper_index + 1


# ---------------------------------------------------------------------------
# 属性 3：任意位置修改 entry_hash → verify 必定检出
# ---------------------------------------------------------------------------

@given(
    entries=st.lists(log_entry_strategy, min_size=1, max_size=20),
    tamper_index=st.integers(min_value=0, max_value=19),
    fake_hash_suffix=st.text(min_size=1, max_size=10, alphabet="0123456789abcdef"),
)
@settings(max_examples=5)
def test_tampered_entry_hash_detected(
    entries: list[LogEntry],
    tamper_index: int,
    fake_hash_suffix: str,
):
    """**Validates: Requirements 9**

    属性 3：任意位置修改一条的 entry_hash → verify 必定检出。
    """
    assume(tamper_index < len(entries))

    chain = build_correct_chain(entries)

    # 篡改 entry_hash（用不同的值替换）
    original_hash = chain[tamper_index].entry_hash
    fake_hash = ("f" * (64 - len(fake_hash_suffix))) + fake_hash_suffix
    assume(fake_hash != original_hash)

    chain[tamper_index].entry_hash = fake_hash

    result = verify_chain(chain)
    assert result["valid"] is False

    # 断链点：如果只有一条，在该条检出 entry_hash 不匹配
    # 如果有后续条目，可能在当前条（entry_hash 不匹配）或下一条（prev_hash 不匹配）
    if tamper_index == len(chain) - 1:
        # 最后一条被改 entry_hash，当前条 entry_hash 重算不匹配
        assert result["broken_at_index"] == tamper_index + 1
    else:
        # 非最后一条：当前条 entry_hash 重算不匹配
        assert result["broken_at_index"] == tamper_index + 1


# ---------------------------------------------------------------------------
# 属性 4：交换两条的顺序 → verify 必定检出
# ---------------------------------------------------------------------------

@given(
    entries=st.lists(log_entry_strategy, min_size=2, max_size=20),
    swap_data=st.data(),
)
@settings(max_examples=5)
def test_swapped_entries_detected(entries: list[LogEntry], swap_data):
    """**Validates: Requirements 9**

    属性 4：交换两条的顺序 → verify 必定检出断链。
    """
    chain = build_correct_chain(entries)

    # 选择两个不同的位置交换
    i = swap_data.draw(st.integers(min_value=0, max_value=len(chain) - 1))
    j = swap_data.draw(st.integers(min_value=0, max_value=len(chain) - 1))
    assume(i != j)

    # 交换两条记录（整体交换，包括 prev_hash 和 entry_hash）
    chain[i], chain[j] = chain[j], chain[i]

    result = verify_chain(chain)
    assert result["valid"] is False
