"""Property-Based Test: A16 模板选择确定性 (Property 10) + A16-7 始终必需 (Property 11)

对于任意随机 business_category 字符串：
1. recommend_a16_version() 返回值始终在合法集合 {A16-1, A16-2, A16-3, A16-5, A16-6} 内
2. 同一输入调用两次，结果完全相同（确定性）
3. A16-7 始终在 always_required 中 + render-config schema 完整

**Validates: Requirements 5.1, 5.2, 5.3, 5.6**
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings as hyp_settings, HealthCheck
from hypothesis import strategies as st

from app.services.template_selector import (
    A16_ALL_VERSIONS,
    A16_ALWAYS_REQUIRED,
    recommend_a16_version,
)


# ─── Constants ────────────────────────────────────────────────────────────────

# 合法输出集合（根据设计文档 A16_CATEGORY_MAP + A16_DEFAULT）
_VALID_OUTPUTS = {"A16-1", "A16-2", "A16-3", "A16-5", "A16-6"}


# ─── Property 10: A16 模板选择确定性 ─────────────────────────────────────────


@hyp_settings(max_examples=5, deadline=None)
@given(business_category=st.text())
def test_property_a16_output_in_valid_set(business_category: str) -> None:
    """Property 10a: 输出在合法集合内

    对于任意 business_category 字符串，recommend_a16_version() 的返回值
    必须属于集合 {A16-1, A16-2, A16-3, A16-5, A16-6}。

    **Validates: Requirements 5.1, 5.2**
    """
    result = recommend_a16_version(business_category)
    assert result in _VALID_OUTPUTS, (
        f"recommend_a16_version({business_category!r}) 返回 {result!r}，"
        f"不在合法集合 {_VALID_OUTPUTS} 内"
    )


@hyp_settings(max_examples=5, deadline=None)
@given(business_category=st.text())
def test_property_a16_deterministic(business_category: str) -> None:
    """Property 10b: 确定性（同一输入始终相同输出）

    对于任意 business_category 字符串，连续调用两次
    recommend_a16_version() 必须返回完全相同的结果。

    **Validates: Requirements 5.1, 5.2**
    """
    result1 = recommend_a16_version(business_category)
    result2 = recommend_a16_version(business_category)
    assert result1 == result2, (
        f"recommend_a16_version({business_category!r}) 非确定性："
        f"第一次={result1!r}, 第二次={result2!r}"
    )



# ─── Property 11: A16-7 始终必需 + render-config schema 完整 ─────────────────


@pytest.mark.asyncio
@hyp_settings(max_examples=5, deadline=None)
@given(business_category=st.one_of(st.text(), st.none()))
async def test_property_a16_7_always_required(business_category: str | None) -> None:
    """Property 11: A16-7 始终必需 + render-config schema 完整

    对于任意 business_category（文本或 None），调用 A16 recommended-version
    端点返回的响应中：
    1. always_required 列表始终包含 "A16-7"
    2. recommended_code 非空
    3. all_versions 数组非空

    **Validates: Requirements 5.3, 5.6**
    """
    from app.routers.wp_editor_router import get_a16_recommended_version

    project_id = uuid.uuid4()
    db = AsyncMock()

    # Mock business_category query result
    biz_row = MagicMock()
    biz_row.__getitem__ = lambda self, i: business_category if i == 0 else None
    biz_result = MagicMock()
    biz_result.first.return_value = biz_row

    # Mock wp_index query - no existing workpapers
    wp_result = MagicMock()
    wp_result.all.return_value = []

    db.execute = AsyncMock(side_effect=[biz_result, wp_result])

    user = MagicMock()
    user.id = uuid.uuid4()

    result = await get_a16_recommended_version(project_id=project_id, db=db, _user=user)

    # 1. A16-7 始终在 always_required 中
    assert "A16-7" in result["always_required"], (
        f"business_category={business_category!r} 时 always_required={result['always_required']!r} "
        f"不包含 A16-7"
    )

    # 2. recommended_code 非空
    assert result["recommended_code"], (
        f"business_category={business_category!r} 时 recommended_code 为空"
    )

    # 3. all_versions 数组非空
    assert len(result["all_versions"]) > 0, (
        f"business_category={business_category!r} 时 all_versions 为空"
    )

    # 4. all_versions 包含所有已知版本
    returned_codes = {v["code"] for v in result["all_versions"]}
    assert returned_codes == set(A16_ALL_VERSIONS), (
        f"all_versions 返回的代码集合 {returned_codes} 不等于预期 {set(A16_ALL_VERSIONS)}"
    )
