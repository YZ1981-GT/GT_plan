# Feature: acnr, Property 13: 自定义写入项目归属校验
"""Property-Based Test: 自定义写入项目归属校验（防 IDOR）。

**Validates: Requirements 24.1**

Property 13 验证:
1. register_custom() 总是在写入前校验 project_id + wp_id 归属
2. 无效归属（wp 不属于 project）一律抛出 WpOwnershipError
3. 有效归属的写入成功且条目存入 L3
4. 一个项目登记的条目不可通过另一项目的 L3 store 访问（隔离）

Testing framework: hypothesis
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# 确保 backend 在 sys.path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr.runtime import (
    WpOwnershipError,
    clear_all_runtime_entries,
    get_runtime_entries,
    register_custom,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_l3():
    """每个测试前后清空 L3 store。"""
    clear_all_runtime_entries()
    yield
    clear_all_runtime_entries()


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# project_id / wp_id: UUID4 字符串
_uuid_st = st.uuids(version=4).map(str)

# wp_code: 合法底稿编码（大写字母 + 数字 + 可选后缀）
_wp_code_st = st.from_regex(r"[A-S]\d{1,2}(-\d{1,2})?", fullmatch=True)

# cell_address: A1 样式地址（列 A~Z + 行 1~999）
_cell_address_st = st.from_regex(r"[A-Z]{1,2}\d{1,3}", fullmatch=True)

# semantic_label: 可选语义标签
_semantic_label_st = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N"),
            min_codepoint=0x30,
            max_codepoint=0x9FFF,
        ),
        min_size=1,
        max_size=10,
    ),
)

# 单个 cell 输入
_cell_st = st.fixed_dictionaries(
    {
        "cell_address": _cell_address_st,
        "wp_code": _wp_code_st,
    },
    optional={"semantic_label": _semantic_label_st},
)

# cells 列表（1~4 条）
_cells_st = st.lists(_cell_st, min_size=1, max_size=4)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_db(*, ownership_valid: bool) -> AsyncMock:
    """构造 mock DB session，控制 ownership 校验结果。"""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = 1 if ownership_valid else None
    db.execute.return_value = result
    return db


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(
    project_id=_uuid_st,
    wp_id=_uuid_st,
    cells=_cells_st,
)
@pytest.mark.asyncio
async def test_invalid_ownership_always_raises(
    project_id: str,
    wp_id: str,
    cells: list[dict],
):
    """P13 不变量 1+2: 无效归属时 register_custom 一律抛出 WpOwnershipError。

    对于任意 project_id/wp_id 组合，当 DB 查询返回无匹配行（归属不成立）时，
    register_custom 必须拒绝写入并抛出 WpOwnershipError，不论 cells 内容如何。

    **Validates: Requirements 24.1**
    """
    clear_all_runtime_entries()

    db = _mock_db(ownership_valid=False)

    with pytest.raises(WpOwnershipError) as exc_info:
        await register_custom(db, project_id, wp_id, cells)

    # 异常携带正确的 project/wp 信息
    assert exc_info.value.project_id == project_id
    assert exc_info.value.wp_id == wp_id

    # L3 store 不应有任何写入
    assert get_runtime_entries(project_id) == {}


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(
    project_id=_uuid_st,
    wp_id=_uuid_st,
    cells=_cells_st,
)
@pytest.mark.asyncio
async def test_valid_ownership_stores_in_l3(
    project_id: str,
    wp_id: str,
    cells: list[dict],
):
    """P13 不变量 3: 有效归属时写入成功，条目全部存入 L3。

    对于任意合法的 project_id/wp_id/cells 组合，当归属校验通过时，
    register_custom 必须成功返回条目列表，且所有有效 cell 均可通过
    get_runtime_entries(project_id) 检索到。

    **Validates: Requirements 24.1**
    """
    clear_all_runtime_entries()

    db = _mock_db(ownership_valid=True)

    entries = await register_custom(db, project_id, wp_id, cells)

    # 有效 cells 数量（cell_address 和 wp_code 都非空）
    valid_cells = [
        c for c in cells
        if c.get("cell_address", "").strip() and c.get("wp_code", "").strip()
    ]

    assert len(entries) == len(valid_cells)

    # 所有条目可从 L3 store 检索
    store = get_runtime_entries(project_id)
    for entry in entries:
        assert entry.addr_id in store
        assert store[entry.addr_id].project_id == project_id
        assert store[entry.addr_id].wp_id == wp_id
        assert store[entry.addr_id].runtime_only is True


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(
    project_a=_uuid_st,
    project_b=_uuid_st,
    wp_id=_uuid_st,
    cells=_cells_st,
)
@pytest.mark.asyncio
async def test_cross_project_isolation(
    project_a: str,
    project_b: str,
    wp_id: str,
    cells: list[dict],
):
    """P13 不变量 4: 项目间 L3 数据完全隔离，无法跨项目访问。

    对于任意两个不同的 project_id，project_a 登记的条目不可通过
    get_runtime_entries(project_b) 访问，反之亦然。

    **Validates: Requirements 24.1**
    """
    clear_all_runtime_entries()

    # 确保两个 project 不同
    if project_a == project_b:
        project_b = str(uuid.uuid4())

    db = _mock_db(ownership_valid=True)

    # 仅给 project_a 登记
    entries_a = await register_custom(db, project_a, wp_id, cells)

    # project_b 的 L3 store 为空
    store_b = get_runtime_entries(project_b)
    assert store_b == {}, (
        f"project_b({project_b}) 不应能访问 project_a({project_a}) "
        f"的 L3 数据，但发现 {len(store_b)} 条"
    )

    # project_a 的数据完整
    store_a = get_runtime_entries(project_a)
    for entry in entries_a:
        assert entry.addr_id in store_a
