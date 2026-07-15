"""PBT: 四语法殊途同归 → 同一 CanonicalAddress [P2]

**Validates: Requirements Req-6, Req-1**

Property: 对于 wp 域地址，通过 addr_id / URI / formula_ref / index_ref
四种语法输入，均收敛到同一 CanonicalAddress。

即: from_addr_id(id) == from_uri(uri) == from_formula_ref(ref) == from_index_ref(idx)
"""
from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.acnr.canonical import CanonicalAddress, _infer_parent_wp_code


# ─── Strategies ──────────────────────────────────────────────────────────────

# 生成合法的 wp 域三段地址组件（确保 round-trip 可行）
_parent_codes = st.from_regex(r"[A-Z][0-9]{1,2}", fullmatch=True)
_sheet_codes = st.from_regex(r"[A-Z][0-9]{1,2}-[0-9]{1,2}", fullmatch=True)
_cell_addresses = st.from_regex(r"[A-Z][0-9]{1,4}", fullmatch=True)


@st.composite
def wp_address_components(draw: st.DrawFn) -> tuple[str, str, str]:
    """生成 (parent, sheet_code, cell) 三元组，确保推导一致性。

    确保 _infer_parent_wp_code(sheet_code) == parent（四语法能收敛的前提）。
    """
    parent = draw(_parent_codes)
    # sheet_code 必须以 parent 开头（如 D2 → D2-1, D2-2 等）
    suffix = draw(st.from_regex(r"-[0-9]{1,2}", fullmatch=True))
    sheet_code = parent + suffix
    cell = draw(_cell_addresses)

    # 验证推导一致
    assume(_infer_parent_wp_code(sheet_code) == parent)

    return (parent, sheet_code, cell)


# ─── Property Tests ──────────────────────────────────────────────────────────


@settings(max_examples=5, deadline=None)
@given(components=wp_address_components())
def test_four_syntax_convergence(components: tuple[str, str, str]) -> None:
    """P2: 四种语法殊途同归 → 同一 CanonicalAddress。

    验证 addr_id / URI / formula_ref(3参) / index_ref(cell:) 四种语法
    输入都收敛到相同的 CanonicalAddress 实例。
    """
    parent, sheet_code, cell = components

    # 1. addr_id 语法: parent/sheet_code/cell
    addr_id_str = f"{parent}/{sheet_code}/{cell}"
    ca_from_addr_id = CanonicalAddress.from_addr_id(addr_id_str)

    # 2. URI 语法: wp://parent/sheet_code#cell
    uri_str = f"wp://{parent}/{sheet_code}#{cell}"
    ca_from_uri = CanonicalAddress.from_uri(uri_str)

    # 3. formula_ref 语法: WP('parent','sheet_code','cell')
    formula_ref_str = f"WP('{parent}','{sheet_code}','{cell}')"
    ca_from_formula = CanonicalAddress.from_formula_ref(formula_ref_str)

    # 4. index_ref 语法: cell:sheet_code!cell
    index_ref_str = f"cell:{sheet_code}!{cell}"
    ca_from_index = CanonicalAddress.from_index_ref(index_ref_str)

    # 所有四种语法应收敛到同一 CanonicalAddress
    assert ca_from_addr_id == ca_from_uri, (
        f"addr_id vs URI 不一致:\n"
        f"  addr_id → {ca_from_addr_id}\n"
        f"  URI → {ca_from_uri}"
    )
    assert ca_from_addr_id == ca_from_formula, (
        f"addr_id vs formula_ref 不一致:\n"
        f"  addr_id → {ca_from_addr_id}\n"
        f"  formula → {ca_from_formula}"
    )
    assert ca_from_addr_id == ca_from_index, (
        f"addr_id vs index_ref 不一致:\n"
        f"  addr_id → {ca_from_addr_id}\n"
        f"  index → {ca_from_index}"
    )


@settings(max_examples=5, deadline=None)
@given(components=wp_address_components())
def test_custom_flat_converges_to_standard(components: tuple[str, str, str]) -> None:
    """P2 附加: custom_flat 2参 WP(code,cell) 收敛到 3参标准形态。

    WP('D2','E100') → parent=D2, sheet=D2, coordinate=E100
    等价于 addr_id: D2/D2/E100

    custom_flat 是边界兼容 adapter，内部统一为 3参。
    """
    parent, _sheet_code, cell = components

    # custom_flat 2参: WP(parent, cell) → 内部 sheet=parent
    custom_flat_ref = f"WP('{parent}','{cell}')"
    ca_custom = CanonicalAddress.from_formula_ref(custom_flat_ref)

    # 等价的 3参标准形态: WP(parent, parent, cell)
    standard_ref = f"WP('{parent}','{parent}','{cell}')"
    ca_standard = CanonicalAddress.from_formula_ref(standard_ref)

    # 两者应收敛到同一 CanonicalAddress
    assert ca_custom == ca_standard, (
        f"custom_flat 未收敛到标准形态:\n"
        f"  custom_flat WP('{parent}','{cell}') → {ca_custom}\n"
        f"  standard WP('{parent}','{parent}','{cell}') → {ca_standard}"
    )

    # 验证 addr_id 也一致
    assert ca_custom.addr_id == f"{parent}/{parent}/{cell}", (
        f"custom_flat addr_id 不符合预期:\n"
        f"  got: {ca_custom.addr_id}\n"
        f"  expected: {parent}/{parent}/{cell}"
    )


@settings(max_examples=5, deadline=None)
@given(components=wp_address_components())
def test_sheet_level_two_syntax_convergence(components: tuple[str, str, str]) -> None:
    """P2 附加: sheet 级（无 coordinate）的语法也收敛。

    addr_id: D2/D2-2
    URI: wp://D2/D2-2
    formula_ref: WP('D2','D2-2')   (2参但非custom_flat — sheet_code以parent开头)
    index_ref: wp:D2-2
    """
    parent, sheet_code, _cell = components

    # sheet 级
    addr_id_str = f"{parent}/{sheet_code}"
    ca_addr = CanonicalAddress.from_addr_id(addr_id_str)

    uri_str = f"wp://{parent}/{sheet_code}"
    ca_uri = CanonicalAddress.from_uri(uri_str)

    # index_ref: wp:sheet_code (推导 parent)
    index_ref_str = f"wp:{sheet_code}"
    ca_index = CanonicalAddress.from_index_ref(index_ref_str)

    # addr_id 和 URI 必须一致
    assert ca_addr == ca_uri, (
        f"Sheet 级 addr_id vs URI 不一致:\n"
        f"  addr_id → {ca_addr}\n"
        f"  URI → {ca_uri}"
    )

    # index_ref 推导的 parent 也应与实际 parent 一致
    assert ca_index.parent == parent, (
        f"index_ref 推导 parent 不一致:\n"
        f"  expected: {parent}\n"
        f"  got: {ca_index.parent}"
    )
    assert ca_index.sheet == sheet_code
    assert ca_index == ca_addr
