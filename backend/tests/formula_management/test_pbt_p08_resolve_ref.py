"""属性测试 P8：公式引用一律经 ACNR full_resolve 解析（Task 2.4）。

**Property 8: 公式引用一律经 ACNR full_resolve 解析**

**Validates: Requirements 5.3, 6.5, 7.4, 11.1, 11.2, 16.3, 17.2**

策略：Hypothesis 随机生成三类型公式（auto_calc / logic_check / reasonability）
+ 有效 / 悬空引用；对 ``app.services.acnr.resolver.full_resolve`` 桩注入（含抛
基础设施异常的分支）以验证：

1. 每条引用都经 ``full_resolve`` 解析（调用次数 == 引用条数），且一律以
   ``formula_ref`` / ``addr_id`` 形式传参（禁止裸 ``wp_code+sheet+cell`` 拼接）。
2. ``found=true`` 时 ``resolve_ref`` 返回 ACNR 的 canonical ``addr_id`` 作引用身份；
   ``miss`` 时回显入参 ``addr_id``。
3. 基础设施异常 → fail-open：``resolve_ref`` 返回 ``found=False`` +
   ``fail_open=True``，且 ``execute_formula`` 不因解析器故障抛异常/中断。

conftest 已注册 Hypothesis fast profile（max_examples=5），本文件遵循该 profile。
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import patch

from hypothesis import given, strategies as st

from app.services.acnr.resolver import ResolveResult
from app.services.formula_engine import FormulaContext
from app.services.formula_management.engine import (
    FormulaRecord,
    execute_formula,
    resolve_ref,
)

_FORMULA_TYPES = ["auto_calc", "logic_check", "reasonability"]

# 每条引用：(kind, valid)。kind 决定以 formula_ref 还是 addr_id 形态传入；
# valid 决定桩内 full_resolve 命中（found=True）或悬空（found=False）。
_ref_specs = st.lists(
    st.tuples(st.sampled_from(["formula_ref", "addr_id"]), st.booleans()),
    min_size=0,
    max_size=6,
)


def _build_refs(specs: list[tuple[str, bool]]):
    """把随机 specs 展开为 refs 列表 + 有效性映射（按唯一 ident 索引）。"""
    refs: list[dict] = []
    validity: dict[str, bool] = {}
    for i, (kind, valid) in enumerate(specs):
        if kind == "formula_ref":
            ident = f"WP('D2','明细表D2-{i}','E{i}')"
            refs.append({"formula_ref": ident})
        else:
            ident = f"D2/D2-{i}/E{i}"
            refs.append({"addr_id": ident})
        validity[ident] = valid
    return refs, validity


def _make_stub(validity: dict[str, bool], calls: list[dict]):
    """构造 full_resolve 桩：记录每次调用；命中返回 canonical addr_id。"""

    async def _stub(**kwargs):
        calls.append(kwargs)
        ident = (
            kwargs.get("formula_ref")
            if kwargs.get("formula_ref") is not None
            else kwargs.get("addr_id")
        )
        if validity.get(ident, False):
            return ResolveResult(
                found=True,
                addr_id=f"acnr-canon::{ident}",
                formula_ref=kwargs.get("formula_ref"),
                semantic_label="语义标签",
            )
        return ResolveResult(found=False, addr_id=None, candidates=[])

    return _stub


# Feature: formula-management-library, Property 8: 公式引用一律经 ACNR full_resolve 解析
@given(specs=_ref_specs, ftype=st.sampled_from(_FORMULA_TYPES))
def test_p8_every_ref_resolved_via_full_resolve(specs, ftype):
    """每条引用都经 full_resolve 解析，且一律以 formula_ref/addr_id 传参。"""
    refs, validity = _build_refs(specs)
    calls: list[dict] = []
    stub = _make_stub(validity, calls)
    f = FormulaRecord(
        id="f-p8",
        formula_type=ftype,
        target_cell="C1",
        expression="ROW('r1')",
        refs=refs,
    )
    ctx = FormulaContext(row_cache={"r1": Decimal("100")})
    with patch("app.services.acnr.resolver.full_resolve", stub):
        asyncio.run(
            execute_formula(
                None, formula=f, ctx=ctx, project_id="p1", resolve_refs=True
            )
        )
    # 三类型公式引用解析路径一致：每条引用恰好一次 full_resolve。
    assert len(calls) == len(refs)
    for c in calls:
        # 一律经 full_resolve 参数化（addr_id/formula_ref），无裸串拼接。
        assert "formula_ref" in c and "addr_id" in c
        assert c.get("project_id") == "p1"


# Feature: formula-management-library, Property 8: 公式引用一律经 ACNR full_resolve 解析
@given(kind=st.sampled_from(["formula_ref", "addr_id"]), valid=st.booleans())
def test_p8_found_uses_canonical_addr_id(kind, valid):
    """found=true 时用 ACNR canonical addr_id；miss 时回显入参 addr_id。"""
    if kind == "formula_ref":
        ident = "WP('D2','明细表D2-2','E100')"
        kwargs = {"formula_ref": ident}
    else:
        ident = "D2/D2-2/E100"
        kwargs = {"addr_id": ident}
    calls: list[dict] = []
    stub = _make_stub({ident: valid}, calls)
    with patch("app.services.acnr.resolver.full_resolve", stub):
        rr = asyncio.run(resolve_ref(project_id="p1", **kwargs))
    assert len(calls) == 1
    if valid:
        assert rr.found is True
        assert rr.addr_id == f"acnr-canon::{ident}"  # canonical addr_id 作引用身份
    else:
        assert rr.found is False
        # miss：回显入参 addr_id（formula_ref 形态入参 addr_id 为 None）。
        assert rr.addr_id == kwargs.get("addr_id")


# Feature: formula-management-library, Property 8: 公式引用一律经 ACNR full_resolve 解析
@given(specs=_ref_specs, ftype=st.sampled_from(_FORMULA_TYPES))
def test_p8_fail_open_on_infra_exception(specs, ftype):
    """基础设施异常 → fail-open：不抛、不阻断；返回 found=False + fail_open=True。"""
    refs, _ = _build_refs(specs)

    async def _boom(**kwargs):
        raise RuntimeError("ACNR infra down")

    f = FormulaRecord(
        id="f-p8-boom",
        formula_type=ftype,
        target_cell="C1",
        expression="ROW('r1')",
        refs=refs,
    )
    ctx = FormulaContext(row_cache={"r1": Decimal("100")})
    with patch("app.services.acnr.resolver.full_resolve", _boom):
        # resolver 故障不得阻断公式执行（fail-open）。
        res = asyncio.run(
            execute_formula(
                None, formula=f, ctx=ctx, project_id="p1", resolve_refs=True
            )
        )
        assert res is not None
        # 直接验证 resolve_ref 的 fail-open 降级契约。
        rr = asyncio.run(
            resolve_ref(formula_ref="WP('D2','明细表D2-2','E1')", project_id="p1")
        )
    assert rr.found is False
    assert rr.fail_open is True
    assert rr.error == "acnr_unavailable_fallback"
