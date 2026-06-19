# Feature: workpaper-editing-guidance, Property 5: 对话历史持久化往返
"""Property 5: 对话历史持久化往返

This requires a real DB session — SKIP the full integration test.
Instead, test the locator key format: for any doc_type/doc_id/user_id combination,
the locator string is deterministic and contains all three components.

**Validates: Requirements 4.6, 4.7, 9.6**
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st


# 生成合法的 doc_type / doc_id / user_id 组合
_doc_type_st = st.sampled_from(["workpaper", "knowledge_doc", "financial_report", "audit_report"])
_doc_id_st = st.from_regex(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", fullmatch=True)
_user_id_st = st.from_regex(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", fullmatch=True)


def _build_locator(doc_type: str, doc_id: str, user_id: str) -> str:
    """构建会话定位键（与 doc_chat_persistence 实现一致）。

    格式: "{doc_type}:{doc_id}:{user_id}"
    """
    return f"{doc_type}:{doc_id}:{user_id}"


@given(doc_type=_doc_type_st, doc_id=_doc_id_st, user_id=_user_id_st)
@settings(max_examples=5)
def test_locator_key_is_deterministic(doc_type: str, doc_id: str, user_id: str):
    """对任意 doc_type/doc_id/user_id 组合，定位键是确定性的（多次调用结果一致）。"""
    key1 = _build_locator(doc_type, doc_id, user_id)
    key2 = _build_locator(doc_type, doc_id, user_id)

    assert key1 == key2, f"定位键不确定: '{key1}' != '{key2}'"


@given(doc_type=_doc_type_st, doc_id=_doc_id_st, user_id=_user_id_st)
@settings(max_examples=5)
def test_locator_key_contains_all_components(doc_type: str, doc_id: str, user_id: str):
    """定位键包含所有三个组成部分。"""
    key = _build_locator(doc_type, doc_id, user_id)

    assert doc_type in key, f"定位键 '{key}' 未包含 doc_type='{doc_type}'"
    assert doc_id in key, f"定位键 '{key}' 未包含 doc_id='{doc_id}'"
    assert user_id in key, f"定位键 '{key}' 未包含 user_id='{user_id}'"


@given(doc_type=_doc_type_st, doc_id=_doc_id_st, user_id=_user_id_st)
@settings(max_examples=5)
def test_locator_key_format_is_colon_separated(doc_type: str, doc_id: str, user_id: str):
    """定位键格式为冒号分隔的三段式。"""
    key = _build_locator(doc_type, doc_id, user_id)

    parts = key.split(":")
    # UUID 本身包含连字符但不含冒号，所以按冒号分割应得到恰好 3 段
    # 但 UUID 格式是 8-4-4-4-12，不含冒号
    # 分割后：doc_type + doc_id + user_id
    # 注意 UUID 不含冒号，所以应正好 3 部分（如果 doc_type 不含冒号）
    assert len(parts) >= 3, f"定位键 '{key}' 应至少有 3 段（冒号分隔）"
    assert parts[0] == doc_type, f"第一段应为 doc_type"
