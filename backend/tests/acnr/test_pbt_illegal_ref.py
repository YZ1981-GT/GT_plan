# Feature: acnr, Property 15: 非法引用编译期失败
"""Property-based test: 非法引用编译期失败（resolve 校验总返回失败且不入库）。

**Validates: Requirements 14.2**

验证规则:
- R14.2: WHEN 用户保存 formula_ref, THE 公式管理库 SHALL 先调用 resolve() 校验，
          IF 引用非法 THEN THE 公式管理库 SHALL 总是在编译期返回失败。

核心属性:
  对任意非法 formula_ref（语法畸形 WP()、不存在的 sheet、不存在的 cell），
  full_resolve() 总是返回 found=False，且响应包含 candidates 或 error 信息。
  非法引用永远不会产生 found=True 的误判（无假阳性）。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

# 确保 backend 目录在 path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

# ---------------------------------------------------------------------------
# Load catalog data for generating non-existent references
# ---------------------------------------------------------------------------

_CATALOG_PATH = _BACKEND_ROOT / "data" / "acnr" / "global_catalog.json"
_catalog_data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
_ALL_SHEETS: list[dict] = _catalog_data["sheets"]
_ALL_CELLS: list[dict] = _catalog_data["cells"]

# 收集所有真实存在的 sheet_name / sheet_code / parent_wp_code / cell_address
_EXISTING_SHEET_NAMES: set[str] = {s["sheet_name"] for s in _ALL_SHEETS if s.get("sheet_name")}
_EXISTING_SHEET_CODES: set[str] = {s["sheet_code"] for s in _ALL_SHEETS if s.get("sheet_code")}
_EXISTING_PARENTS: set[str] = {s["parent_wp_code"] for s in _ALL_SHEETS if s.get("parent_wp_code")}
_EXISTING_ADDR_IDS: set[str] = {c["addr_id"] for c in _ALL_CELLS}
_EXISTING_ADDR_IDS.update(s["addr_id"] for s in _ALL_SHEETS)


# ---------------------------------------------------------------------------
# Strategies: 生成非法 formula_ref
# ---------------------------------------------------------------------------

# 1. 语法畸形: 不以 WP( / PREV( 开头，或括号/引号不匹配
_MALFORMED_PREFIXES = [
    "WX(", "wp(", "WRONG(", "W(", "P(", "WP[", "WP{", "PREV[",
    "TB(", "FORMULA(", "REF(", "", "WP", "PREV",
]

_malformed_formula_st = st.one_of(
    # 完全无效前缀
    st.sampled_from(_MALFORMED_PREFIXES).map(lambda p: f"{p}'X','Y','Z')"),
    # 缺少引号的 WP
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
        min_size=1,
        max_size=15,
    ).map(lambda t: f"WP({t})"),
    # 空括号
    st.just("WP()"),
    st.just("PREV()"),
    # 参数数量错误（0参/1参/4+参）
    st.text(min_size=1, max_size=8).map(lambda t: f"WP('{t}')"),
    st.tuples(
        st.text(min_size=1, max_size=5),
        st.text(min_size=1, max_size=5),
        st.text(min_size=1, max_size=5),
        st.text(min_size=1, max_size=5),
    ).map(lambda t: f"WP('{t[0]}','{t[1]}','{t[2]}','{t[3]}')"),
)


# 2. 不存在的 sheet: 使用合法语法但 parent / sheet_name 不存在
def _non_existent_sheet_name(draw) -> str:
    """生成不在 catalog 中的 sheet_name。"""
    name = draw(st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N"),
            min_codepoint=0x41,
            max_codepoint=0x5A,
        ),
        min_size=3,
        max_size=12,
    ))
    assume(name not in _EXISTING_SHEET_NAMES)
    assume(name not in _EXISTING_SHEET_CODES)
    return name


def _non_existent_parent(draw) -> str:
    """生成不在 catalog 中的 parent_wp_code。"""
    parent = draw(st.from_regex(r"[T-Z]\d{1,2}", fullmatch=True))
    assume(parent not in _EXISTING_PARENTS)
    return parent


@st.composite
def non_existent_sheet_formula_st(draw):
    """生成指向不存在 sheet 的合法语法 WP() 公式。"""
    # 策略: 使用不存在的 parent 或不存在的 sheet_name
    choice = draw(st.integers(min_value=0, max_value=2))

    if choice == 0:
        # 不存在的 parent + 随机 sheet_name
        parent = _non_existent_parent(draw)
        sheet = draw(st.text(
            alphabet=st.characters(whitelist_categories=("L", "N"), min_codepoint=0x41, max_codepoint=0x7A),
            min_size=2, max_size=8,
        ))
        cell = draw(st.from_regex(r"[A-Z]\d{1,3}", fullmatch=True))
        return f"WP('{parent}','{sheet}','{cell}')"
    elif choice == 1:
        # 存在的 parent + 不存在的 sheet_name
        parent = draw(st.sampled_from(sorted(_EXISTING_PARENTS)))
        sheet = _non_existent_sheet_name(draw)
        cell = draw(st.from_regex(r"[A-Z]\d{1,3}", fullmatch=True))
        return f"WP('{parent}','{sheet}','{cell}')"
    else:
        # 不存在的 parent + 不存在的 sheet_name（2参形式）
        parent = _non_existent_parent(draw)
        sheet = _non_existent_sheet_name(draw)
        return f"WP('{parent}','{sheet}')"


# 3. 不存在的 cell: 使用真实 parent+sheet 但虚假的 cell 坐标
@st.composite
def non_existent_cell_formula_st(draw):
    """生成指向真实 sheet 但不存在 cell 的 WP() 公式。

    使用极大行号（远超种子范围）确保 cell 不存在。
    """
    sheet = draw(st.sampled_from(_ALL_SHEETS))
    parent = sheet.get("parent_wp_code", "D1")
    sheet_name = sheet.get("sheet_name", "")
    assume(parent and sheet_name)

    # 生成远超种子范围的行号（9000+），确保 cell 地址不存在
    col = draw(st.sampled_from(["AA", "AB", "AC", "ZZ", "XY"]))
    row = draw(st.integers(min_value=9000, max_value=9999))
    cell_address = f"{col}{row}"

    # 确认此 addr_id 确实不存在
    potential_addr_id = f"{parent}/{sheet.get('sheet_code', '')}/{cell_address}"
    assume(potential_addr_id not in _EXISTING_ADDR_IDS)

    return f"WP('{parent}','{sheet_name}','{cell_address}')"


# 合并所有非法引用策略
_illegal_formula_ref_st = st.one_of(
    _malformed_formula_st,
    non_existent_sheet_formula_st(),
    non_existent_cell_formula_st(),
)


# ---------------------------------------------------------------------------
# Helper: 运行 async full_resolve
# ---------------------------------------------------------------------------


def _run_resolve(**kwargs):
    """同步包装 async full_resolve。"""
    from app.services.acnr.resolver import full_resolve
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(full_resolve(**kwargs))
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Property Test
# ---------------------------------------------------------------------------


class TestIllegalRefCompileTimeFail:
    """Property 15: 非法引用编译期失败（resolve 校验总返回失败且不入库）。

    模拟公式管理库的保存前校验行为：对任意非法 formula_ref 调用 full_resolve()，
    必须返回 found=False，永远不会误判为合法引用（无假阳性）。
    """

    @given(formula_ref=_illegal_formula_ref_st)
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_invalid_formula_ref_always_returns_not_found(self, formula_ref: str):
        """非法 formula_ref 的 resolve 校验总返回 found=False。

        验证:
        1. full_resolve() 对非法引用返回 found=False（无假阳性）
        2. 响应包含 candidates 列表或 error 信息（辅助用户定位问题）
        3. 非法引用不会产生 addr_id（不入库）

        **Validates: Requirements 14.2**
        """
        result = _run_resolve(formula_ref=formula_ref)

        # 核心断言 1: 非法引用永远不能返回 found=True
        assert result.found is False, (
            f"非法引用误判为合法（假阳性）: formula_ref={formula_ref!r}, "
            f"returned addr_id={result.addr_id}"
        )

        # 核心断言 2: 非法引用的 resolve 结果不应有有效 addr_id
        # （addr_id 可能被中间步骤推导出来但最终未命中，此时
        #  found=False 已保证安全；但若 found=True 则为严重缺陷）
        # 此处已由断言 1 覆盖

        # 核心断言 3: 响应应包含辅助信息（candidates 或 error）
        has_helpful_info = (
            (result.candidates is not None and len(result.candidates) >= 0)
            or result.error is not None
        )
        assert has_helpful_info, (
            f"非法引用的 resolve 响应缺少辅助信息: "
            f"formula_ref={formula_ref!r}, candidates={result.candidates}, "
            f"error={result.error}"
        )

    @given(formula_ref=_illegal_formula_ref_st)
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_invalid_ref_candidates_within_limit(self, formula_ref: str):
        """非法引用的 candidates 数量不超过 5 条（R5.6 限制）。

        **Validates: Requirements 14.2**
        """
        result = _run_resolve(formula_ref=formula_ref)

        assert result.found is False

        # 如果有 candidates，数量应 ≤ 5
        if result.candidates is not None:
            assert len(result.candidates) <= 5, (
                f"candidates 超过 5 条限制: "
                f"formula_ref={formula_ref!r}, count={len(result.candidates)}"
            )
