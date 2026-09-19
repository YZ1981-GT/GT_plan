"""属性测试 P23：导入导出往返 + 编报说明存在（Task 14.7）。

**Property 23: 导入导出往返 + 编报说明存在**

**Validates: Requirements 23.2, 23.4**

三条不变量：

1. **编报说明区存在**（Req 23.2）：``build_template_workbook`` /
   ``build_data_workbook`` 生成的工作簿首个 sheet 恒为「编报说明」，且含单一源
   文档标题（``reporting_instructions.DOC_TITLE``）。
2. **导入→导出往返一致**（Req 23.4）：*对任意*引用有效的公式条目集，导出为数据
   工作簿再解析导入，还原条目的 page_key / target_cell / expression / formula_type
   与原条目逐一相等（引用经 full_resolve 桩全部命中）。
3. **悬空报告不入库**（Req 23.4）：含悬空引用（full_resolve found=False 且非
   fail-open）的公式被报告到 skipped，且不出现在 imported。

被测：``formula_import_export`` 的 ``build_template_workbook`` /
``build_data_workbook`` / ``parse_import_rows``。引用解析经
``app.services.acnr.resolver.full_resolve`` 桩注入。

conftest 已注册 Hypothesis fast profile（max_examples=5），本文件遵循该 profile。
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from hypothesis import given, strategies as st

from app.services.acnr.resolver import ResolveResult
from app.services.formula_management import formula_import_export as fie
from app.services.formula_management.preset_library import PresetEntry
from app.services.formula_management.reporting_instructions import DOC_TITLE

_FORMULA_TYPES = ["auto_calc", "logic_check", "reasonability"]

# page_key / target_cell / expression：简单可回显文本（避免换行/前后空白影响 strip 比较）。
_token = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"),
    min_size=1,
    max_size=10,
).filter(lambda s: s.strip() == s and s.strip() != "")

_scope = st.sampled_from(["workpaper", "report", "note"])


@st.composite
def _entries(draw, *, valid_refs: bool):
    """生成一组预设条目；valid_refs 控制引用在桩内命中/悬空。"""
    n = draw(st.integers(min_value=1, max_value=4))
    out: list[PresetEntry] = []
    used: set[tuple[str, str]] = set()
    for i in range(n):
        scope = draw(_scope)
        key = draw(_token)
        page_key = f"{scope}:{key}"
        target_cell = f"{draw(_token)}-{i}"
        if (page_key, target_cell) in used:
            continue
        used.add((page_key, target_cell))
        ftype = draw(st.sampled_from(_FORMULA_TYPES))
        # 引用身份决定桩命中；valid_refs=True → 命中，False → 悬空。
        marker = "OK" if valid_refs else "MISS"
        ref_id = f"TB('{marker}-{i}')"
        out.append(
            PresetEntry(
                page_key=page_key,
                target_cell=target_cell,
                expression=f"{ref_id} + 1",
                formula_type=ftype,
                refs=[{"formula_ref": ref_id}],
                source="test",
                description=draw(st.sampled_from(["", "说明A", "note"])),
            )
        )
    return out


def _make_full_resolve_stub():
    """full_resolve 桩：formula_ref 含 'OK' → 命中；含 'MISS' → 悬空。"""

    async def _stub(**kwargs):
        ident = kwargs.get("formula_ref") or kwargs.get("addr_id") or ""
        if "MISS" in ident:
            return ResolveResult(found=False, addr_id=None, candidates=[])
        return ResolveResult(
            found=True,
            addr_id=f"canon::{ident}",
            formula_ref=kwargs.get("formula_ref"),
            semantic_label="label",
        )

    return _stub


# ── 1. 编报说明区存在（Req 23.2） ─────────────────────────────────────────────
# Feature: formula-management-library, Property 23: 导入导出往返 + 编报说明存在
def test_p23_template_first_sheet_is_instructions():
    """导出模板首 sheet = 编报说明，含单一源文档标题。"""
    wb = fie.build_template_workbook()
    assert wb.sheetnames[0] == fie.INSTRUCTIONS_SHEET_NAME
    ws = wb[fie.INSTRUCTIONS_SHEET_NAME]
    texts = [str(row[0]) for row in ws.iter_rows(values_only=True) if row and row[0]]
    assert DOC_TITLE in texts, "编报说明区未含单一源文档标题"
    # 公式 sheet 也应存在（含表头）。
    assert fie.FORMULA_SHEET_NAME in wb.sheetnames


# Feature: formula-management-library, Property 23: 导入导出往返 + 编报说明存在
@given(entries=_entries(valid_refs=True))
def test_p23_data_workbook_first_sheet_is_instructions(entries):
    """导出数据工作簿首 sheet 也恒为编报说明（同一单一源）。"""
    wb = fie.build_data_workbook(entries)
    assert wb.sheetnames[0] == fie.INSTRUCTIONS_SHEET_NAME
    ws = wb[fie.INSTRUCTIONS_SHEET_NAME]
    texts = [str(row[0]) for row in ws.iter_rows(values_only=True) if row and row[0]]
    assert DOC_TITLE in texts


# ── 2. 导入→导出往返一致（Req 23.4） ─────────────────────────────────────────
# Feature: formula-management-library, Property 23: 导入导出往返 + 编报说明存在
@given(entries=_entries(valid_refs=True))
def test_p23_export_import_roundtrip_fields_preserved(entries):
    """导出→导入往返：核心字段（page_key/target_cell/expression/type）逐一保真。"""
    wb = fie.build_data_workbook(entries)
    content = fie.workbook_to_bytes(wb)
    with patch("app.services.acnr.resolver.full_resolve", _make_full_resolve_stub()):
        result = asyncio.run(fie.parse_import_rows(content, project_id="p1"))

    # 有效引用全部入库，无跳过。
    assert result.skipped_count == 0, [s.to_dict() for s in result.skipped]
    assert result.imported_count == len(entries)

    orig = {(e.page_key, e.target_cell): e for e in entries}
    for imp in result.imported:
        key = (imp.page_key, imp.target_cell)
        assert key in orig, f"往返出现未知条目: {key}"
        src = orig[key]
        assert imp.expression == src.expression
        assert imp.formula_type == src.formula_type


# ── 3. 悬空报告不入库（Req 23.4） ─────────────────────────────────────────────
# Feature: formula-management-library, Property 23: 导入导出往返 + 编报说明存在
@given(entries=_entries(valid_refs=False))
def test_p23_dangling_refs_reported_and_not_imported(entries):
    """悬空引用条目被报告到 skipped，且绝不入库 imported。"""
    wb = fie.build_data_workbook(entries)
    content = fie.workbook_to_bytes(wb)
    with patch("app.services.acnr.resolver.full_resolve", _make_full_resolve_stub()):
        result = asyncio.run(fie.parse_import_rows(content, project_id="p1"))

    # 悬空全部跳过，无一入库。
    assert result.imported_count == 0, "悬空引用不应入库"
    assert result.skipped_count == len(entries)
    for skip in result.skipped:
        assert skip.dangling_refs, "跳过项应记录悬空引用清单"
        assert "悬空" in skip.reason


# ── 4. fail-open（基础设施故障）不误判为悬空（Req 11.3 交叉守护） ──────────────
# Feature: formula-management-library, Property 23: 导入导出往返 + 编报说明存在
@given(entries=_entries(valid_refs=True))
def test_p23_fail_open_not_treated_as_dangling(entries):
    """full_resolve 抛基础设施异常时 fail-open：不跳过、照常入库。"""

    async def _boom(**kwargs):
        raise RuntimeError("ACNR infra down")

    wb = fie.build_data_workbook(entries)
    content = fie.workbook_to_bytes(wb)
    with patch("app.services.acnr.resolver.full_resolve", _boom):
        result = asyncio.run(fie.parse_import_rows(content, project_id="p1"))

    assert result.skipped_count == 0, "fail-open 不应被当作悬空跳过"
    assert result.imported_count == len(entries)
