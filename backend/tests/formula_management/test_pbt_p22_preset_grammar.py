"""属性测试 P22：预设引用 grammar_v1 闭合（Task 14.7）。

**Property 22: 预设引用 grammar_v1 闭合**

**Validates: Requirements 22.7, 24.1**

命题：*对任意*预设条目的任意引用，经 ACNR ``grammar_v1``（``normalize_ref`` /
``full_resolve``）归一化后，其状态**要么** ``migrated``（全部函数头 ∈ ACNR 已注册
函数集，可经 ``full_resolve`` 解析），**要么**明确标 ``pending``（且待迁移函数
∈ ``PENDING_FUNCTION_ALLOWLIST`` 白名单 / 空占位 / 裸坐标）——不存在第三种游离态，
也不会把未映射函数误判为 migrated。

被测：``preset_library.build_preset_library`` + ``preset_acnr_migration.normalize_ref``。

conftest 已注册 Hypothesis fast profile（max_examples=5），本文件遵循该 profile。
"""

from __future__ import annotations

from hypothesis import given, strategies as st

from app.services.formula_management import preset_library as pl
from app.services.formula_management.preset_acnr_migration import (
    PENDING_FUNCTION_ALLOWLIST,
    STATUS_MIGRATED,
    STATUS_PENDING,
    _known_acnr_funcs,
    normalize_ref,
)

# ACNR grammar_v1 已注册（canonical）函数头 + 旧别名（归一后可解析）。
_KNOWN_FUNCS = sorted(_known_acnr_funcs())
_ALIAS_FUNCS = ["TB_SUM", "TB_AUX"]  # 归一化到 SUM_TB / AUX → migrated
_PENDING_FUNCS = sorted(PENDING_FUNCTION_ALLOWLIST)  # ADJ/LEDGER/... → pending 白名单

_arg = st.sampled_from(["'1001'", "'assets_total'", "'五、3'", "'1122','审定数'", "'D2','E1'"])


def _call(func: str, arg: str) -> str:
    return f"{func}({arg})"


# ── 具体预设库闭合断言 ────────────────────────────────────────────────────────
# Feature: formula-management-library, Property 22: 预设引用 grammar_v1 闭合
def test_p22_preset_library_refs_grammar_closed():
    """预设库每条引用经 grammar_v1 归一化后 migrated 或明确 pending（白名单）。"""
    entries, _ = pl.build_preset_library()
    assert entries, "预设库为空"
    seen_ref = False
    for e in entries:
        for ref in e.refs:
            seen_ref = True
            # 规范引用：必带 formula_ref / addr_id，禁裸坐标串（Req 24.1 / 11.5）。
            assert isinstance(ref, dict), f"引用非规范 dict: {ref!r} @ {e.page_key}"
            expr = ref.get("formula_ref") or ref.get("addr_id")
            assert expr, f"引用缺 formula_ref/addr_id: {ref!r} @ {e.page_key}"
            nr = normalize_ref(expr)
            # 闭合：状态非 migrated 即 pending，无第三态。
            assert nr.status in (STATUS_MIGRATED, STATUS_PENDING)
            # pending 的未映射函数必须落在白名单内（否则为漂移，drift guard 兜底）。
            if nr.status == STATUS_PENDING:
                for fn in nr.unmapped_functions:
                    assert fn in PENDING_FUNCTION_ALLOWLIST, (
                        f"pending 引用含白名单外函数 {fn!r}: {expr!r} @ {e.page_key}"
                    )
            # 预设库收敛写入的 acnr_status（若有）须与归一化判定一致（不分叉）。
            if "acnr_status" in ref:
                assert ref["acnr_status"] == nr.status
    assert seen_ref, "预设库无任何带引用的条目，无法验证闭合"


# ── 属性：已注册函数 → migrated ──────────────────────────────────────────────
# Feature: formula-management-library, Property 22: 预设引用 grammar_v1 闭合
@given(func=st.sampled_from(_KNOWN_FUNCS + _ALIAS_FUNCS), arg=_arg, lead=st.booleans())
def test_p22_known_functions_are_migrated(func, arg, lead):
    """canonical / 别名函数（归一后 ∈ 已注册集）→ migrated 且可解析。"""
    expr = _call(func, arg)
    if lead:
        expr = "=" + expr
    nr = normalize_ref(expr)
    assert nr.migrated, f"{expr!r} 应 migrated，实为 {nr.status}/{nr.reason}"
    assert nr.status == STATUS_MIGRATED
    assert not nr.unmapped_functions
    # migrated → 产出可用 formula_ref 引用身份。
    assert nr.to_ref_dict() == {"formula_ref": nr.formula_ref, "acnr_status": STATUS_MIGRATED}


# ── 属性：白名单待迁移函数 → pending（不误判 migrated） ────────────────────────
# Feature: formula-management-library, Property 22: 预设引用 grammar_v1 闭合
@given(func=st.sampled_from(_PENDING_FUNCS), arg=_arg)
def test_p22_pending_allowlist_functions_are_pending(func, arg):
    """白名单待迁移函数（无 ACNR 等价）→ pending，未映射函数 ⊆ 白名单。"""
    nr = normalize_ref(_call(func, arg))
    assert nr.status == STATUS_PENDING
    assert nr.unmapped_functions, "白名单函数应被识别为未映射"
    for fn in nr.unmapped_functions:
        assert fn in PENDING_FUNCTION_ALLOWLIST


# ── 属性：任意字符串归一化总闭合（migrated 或 pending，不崩溃） ────────────────
# Feature: formula-management-library, Property 22: 预设引用 grammar_v1 闭合
@given(expr=st.text(max_size=40))
def test_p22_arbitrary_input_is_total_and_closed(expr):
    """归一化是全函数：任意输入都归为 migrated 或 pending，且判定自洽。"""
    nr = normalize_ref(expr)
    assert nr.status in (STATUS_MIGRATED, STATUS_PENDING)
    # migrated ⇒ 无未映射函数；pending ⇒ 有理由（空/裸坐标/未映射函数）。
    if nr.status == STATUS_MIGRATED:
        assert not nr.unmapped_functions
    else:
        assert nr.reason
