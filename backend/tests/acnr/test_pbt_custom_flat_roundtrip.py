# Feature: acnr-consumer-wiring, Property 17: Custom Cell addr_id custom_flat Round-Trip
"""Property-based test: 自定义格 custom_flat addr_id 往返一致性（P17）.

**Validates: Requirements 12.1, 12.2**

验证规则:
- R12.1: 自定义 WP 格登记进 ACNR L3 runtime，addr_id == ``{wp_code}/{wp_code}/{cell}``
  （custom_flat profile），且在既有 legacy AddressEntry 产出之外追加（additive）。
- R12.2: runtime 登记派生的 ``formula_ref`` 与 grammar_v1 custom_flat profile 一致，
  可被 catalog ``_formula_ref_to_addr_id``（grammar_v1 custom_flat 解析）往返回同一 addr_id。

测试覆盖:
- Property 17: 随机 ``(wp_code, cell)`` → ``_build_custom_flat_addr_id`` == ``{wp_code}/{wp_code}/{cell}``；
  ``_formula_ref_to_addr_id(_build_custom_flat_formula_ref(...))`` 往返回同一 addr_id。
- 追加登记：``_build_custom_wp_cell_entries`` 在产出 legacy AddressEntry 的同时，
  把自定义格追加登记进 L3 runtime（不替换 legacy）。
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

# 确保 backend 目录在 path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr.catalog import _formula_ref_to_addr_id, get_catalog
from app.services.acnr.runtime import (
    _build_custom_flat_addr_id,
    _build_custom_flat_formula_ref,
    clear_all_runtime_entries,
    get_runtime_entries,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies: 生成合法 grammar 形状的 (wp_code, cell)
#   - 避免引号 ' 、逗号 , 、斜杠 / （否则会破坏 WP(...) / addr_id 分段解析）
#   - 自定义 wp_code：多字母前缀 + 可选数字 + 可选 -N 后缀，语义上代表非种子自定义底稿
#   - cell：A1 形式（1~3 字母列 + 1~4 数字行）
# ---------------------------------------------------------------------------

_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@st.composite
def custom_wp_codes(draw) -> str:
    """生成自定义底稿编码，形如 ``CUST01`` / ``MYWP-3`` / ``ZQX12``。

    不含引号/逗号/斜杠。以 2+ 字母开头（区别于 A~S 单字母循环码），
    显著降低与种子 catalog parent_wp_code 撞码的概率。
    """
    letters = draw(st.text(alphabet=_UPPER, min_size=2, max_size=5))
    digits = draw(st.text(alphabet="0123456789", min_size=0, max_size=3))
    suffix = draw(st.sampled_from(["", "-1", "-2", "-10", "-A"]))
    return f"{letters}{digits}{suffix}"


@st.composite
def cell_addresses(draw) -> str:
    """生成 A1 形式单元格坐标，形如 ``B7`` / ``AA100`` / ``ABC1234``。"""
    col = draw(st.text(alphabet=_UPPER, min_size=1, max_size=3))
    row = draw(st.integers(min_value=1, max_value=9999))
    return f"{col}{row}"


def _catalog_parent_codes() -> set[str]:
    """收集 catalog 中真实的 parent_wp_code / sheet_code 集合。

    3 参 ``_formula_ref_to_addr_id`` 仅当 ``parent == 真实 parent_wp_code`` 时
    才会命中种子解析而非 custom_flat fallback；用于 ``assume`` 排除撞码样本。
    """
    cat = get_catalog()
    parents: set[str] = set()
    try:
        for s in cat.sheets_by_addr_id.values():
            p = s.get("parent_wp_code")
            if p:
                parents.add(str(p))
        parents.update(str(k) for k in cat.sheets_by_code.keys())
    except Exception:
        pass
    return parents


_REAL_PARENTS = _catalog_parent_codes()


# ---------------------------------------------------------------------------
# Property 17: custom_flat addr_id / formula_ref 往返一致性
# ---------------------------------------------------------------------------


class TestCustomFlatRoundTrip:
    """Property 17: Custom Cell addr_id custom_flat Round-Trip."""

    @given(wp_code=custom_wp_codes(), cell=cell_addresses())
    @settings(max_examples=200, deadline=None)
    def test_custom_flat_addr_id_and_formula_ref_round_trip(
        self, wp_code: str, cell: str
    ):
        """随机 (wp_code, cell)：

        1. ``_build_custom_flat_addr_id`` == ``{wp_code}/{wp_code}/{cell}``
        2. ``_build_custom_flat_formula_ref`` 经 grammar_v1 custom_flat 解析
           (``_formula_ref_to_addr_id``) 往返回同一 addr_id。
        """
        # 排除与种子 catalog 撞码的样本（撞码会走种子解析而非 custom_flat fallback）
        assume(wp_code not in _REAL_PARENTS)

        expected_addr_id = f"{wp_code}/{wp_code}/{cell}"

        # (1) addr_id 构造正确
        addr_id = _build_custom_flat_addr_id(wp_code, cell)
        assert addr_id == expected_addr_id, (
            f"custom_flat addr_id 不匹配: {addr_id!r} != {expected_addr_id!r}"
        )

        # (2) formula_ref 经 grammar_v1 custom_flat 解析往返回同一 addr_id
        formula_ref = _build_custom_flat_formula_ref(wp_code, cell)
        assert formula_ref == f"WP('{wp_code}','{wp_code}','{cell}')"

        round_tripped = _formula_ref_to_addr_id(formula_ref)
        assert round_tripped == expected_addr_id, (
            f"formula_ref 往返失败: {formula_ref!r} → {round_tripped!r}, "
            f"期望 {expected_addr_id!r}"
        )


# ---------------------------------------------------------------------------
# Additive registration: legacy AddressEntry 仍产出 + L3 runtime 追加登记
# ---------------------------------------------------------------------------


def _mock_db_for_build(rows: list[tuple]) -> AsyncMock:
    """构造 mock db：

    - 第 1 次 execute（SELECT WorkingPaper JOIN WpIndex）→ ``.all()`` 返回 rows
    - 后续 execute（register_custom 的归属校验）→ ``.scalar_one_or_none()`` = 1
    """
    db = AsyncMock()

    select_result = MagicMock()
    select_result.all.return_value = rows

    ownership_result = MagicMock()
    ownership_result.scalar_one_or_none.return_value = 1

    db.execute.side_effect = [select_result, ownership_result]
    return db


class TestAdditiveRegistration:
    """R12.1: legacy AddressEntry 仍产出，L3 runtime 为追加而非替换。"""

    @pytest.fixture(autouse=True)
    def _clean_l3(self):
        clear_all_runtime_entries()
        yield
        clear_all_runtime_entries()

    @pytest.mark.asyncio
    async def test_legacy_entry_and_l3_runtime_both_produced(self):
        """_build_custom_wp_cell_entries 同时产出 legacy AddressEntry 与 L3 runtime 条目。"""
        from app.services.address_registry import (
            AddressEntry,
            _build_custom_wp_cell_entries,
        )

        project_id = str(uuid.uuid4())
        wp_id = str(uuid.uuid4())
        wp_code = "CUST-01"
        cell = "B7"

        # parsed_data 扁平形式：{sheet: {cell: value}}
        parsed_data = {"Sheet1": {cell: 123}}
        rows = [(wp_id, parsed_data, wp_code, "自定义底稿")]

        db = _mock_db_for_build(rows)

        entries = await _build_custom_wp_cell_entries(db, project_id, 2025)

        # (1) legacy AddressEntry 仍产出（2 参 formula_ref，未被替换）
        legacy = [
            e for e in entries
            if isinstance(e, AddressEntry) and e.domain == "wp" and e.cell == cell
        ]
        assert len(legacy) == 1, f"应产出 1 条 legacy AddressEntry，实际 {len(legacy)}"
        assert legacy[0].formula_ref == f"WP('{wp_code}','{cell}')", (
            f"legacy formula_ref 应为 2 参形式，实际 {legacy[0].formula_ref!r}"
        )

        # (2) L3 runtime 追加登记（custom_flat addr_id + 3 参 formula_ref）
        l3 = get_runtime_entries(project_id)
        expected_addr_id = f"{wp_code}/{wp_code}/{cell}"
        assert expected_addr_id in l3, (
            f"L3 runtime 应含追加登记 addr_id {expected_addr_id!r}，实际 {list(l3.keys())}"
        )
        l3_entry = l3[expected_addr_id]
        assert l3_entry.formula_ref == f"WP('{wp_code}','{wp_code}','{cell}')"
        assert l3_entry.uri_profile == "custom_flat"
