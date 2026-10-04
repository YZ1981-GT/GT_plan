# -*- coding: utf-8 -*-
"""D3-1 预收账款审定表 —— `AdjudicationSheetSpec` 声明的独立判据（Task 13，design.md Property 6）。

spec: d3-sync-coverage-via-row-table-engine · Task 13 · Requirements 4.1 / 4.2 / 4.3

═══ Property 6：`sections` / `row_mode` 取自模板实测，非照 D1-1/D2-1 推演（裁决 F3）═══

**Validates: Requirements 4.3**

判据面（对齐 design.md「Property 6」+ requirements 4.1/4.2/4.3）：
1. D3-1 是**两区块**（性质分类 nature + 账龄分类 aging），**不是** D1-1 的 3 区
   （gross/bd/net）、**不是** D2-1 的 1 区写死 4 行。
2. 两 section 的 `section_key` 与前端 `useD3Adjudication.makeItemId` 的 section token 逐字
   对齐（`nature`/`aging`，非展示用的 `by-nature`/`by-aging`），几何行号与模板 openpyxl 实测
   一致（区1 数据 8-12 / 合计 13；区2 数据 17-20 / 合计 21）。
3. `row_mode == fixed_rows`（两区固定行数不可增删）。
4. 逐格 mask 是**格级**（30 行 ×12 列 / 88 公式 / 密度 24%），受管金额字段（区2 手工列）
   不落 mask（`assert_data_cells_not_masked` 不抛，需求 4.2 依赖 `merge._protection` 格级判定）。
5. 🔴 **变异必红**：把 sections 改成 D1-1 的 3 区（gross/bd/net）⇒ 与模板实测几何不符 ⇒
   本文件的几何断言必须失败（证明判据真的钉住实测，不是恒真装饰）。

🔴 本文件是**离线纯声明判据**（不连库、不翻灰度开关、不重生成契约）——Task 13 只落声明 +
   Property 6，接入验收（四态状态机 / 整册 materialize）是 Task 14。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_d3_01_adjudication as D301
from app.services.workpaper_sync.phase5_adjudication_sheet import (
    AdjudicationRowMode,
    AdjudicationSection,
    AdjudicationSheetSpec,
    AdjudicationValueSource,
)


# ─── Property 6 主判据：两区块 + fixed_rows + 实测几何 ────────────────────────

def test_d3_01_has_exactly_two_sections() -> None:
    """🔴 D3-1 是两区块，不是 D1-1 的 3 区、不是 D2-1 的 1 区。"""
    assert len(D301.SPEC_D301.sections) == 2


def test_d3_01_section_keys_match_frontend_tokens() -> None:
    """section_key 与前端 makeItemId 的 section token 逐字对齐（nature/aging，非 by-nature）。"""
    keys = [s.section_key for s in D301.SPEC_D301.sections]
    assert keys == ["nature", "aging"]
    # 反证：绝不是 D1-1 的 gross/bd/net
    assert "gross" not in keys and "bd" not in keys and "net" not in keys


def test_d3_01_nature_section_geometry_matches_template() -> None:
    """区1 性质分类几何 = 模板实测（数据 8-12 含占位第 5 行，合计 13）。"""
    nature = D301.SPEC_D301.section("nature")
    assert nature is not None
    assert nature.first_data_row == 8
    assert nature.last_data_row == 12  # 🔴 模板画 5 行（A12 占位冗余），SUM 区间 8:12
    assert nature.subtotal_row == 13
    assert nature.uuid_col == ""  # 固定行不需 UUID


def test_d3_01_aging_section_geometry_matches_template() -> None:
    """区2 账龄分类几何 = 模板实测（数据 17-20 四行，合计 21）。"""
    aging = D301.SPEC_D301.section("aging")
    assert aging is not None
    assert aging.first_data_row == 17
    assert aging.last_data_row == 20  # 与前端 AGING_ROWS 4 项逐字对应
    assert aging.subtotal_row == 21
    assert aging.uuid_col == ""


def test_d3_01_row_mode_is_fixed_rows() -> None:
    """🔴 两区都是固定行数（不可增删）⇒ fixed_rows（同 D1-1，不是 dynamic_identity）。"""
    assert D301.SPEC_D301.row_mode is AdjudicationRowMode.fixed_rows


def test_d3_01_footer_rows_match_template() -> None:
    """footer 三行：合计 21（账龄区小计）/ 试算平衡表数 22 / 差异 23。"""
    spec = D301.SPEC_D301
    assert spec.total_row == 21
    assert spec.tb_row == 22
    assert spec.diff_row == 23


def test_d3_01_data_and_computed_rows() -> None:
    """data_rows / computed_rows 由两区几何派生，与模板实测一致。"""
    spec = D301.SPEC_D301
    assert spec.data_rows == (8, 9, 10, 11, 12, 17, 18, 19, 20)
    # 两区小计 13/21 + footer TB 22 + 差异 23（合计 21 与账龄小计同一行）
    assert spec.computed_rows == (13, 21, 22, 23)


# ─── 逐格 mask 判据（需求 4.2：格级形态，受管数据格不落 mask）─────────────────

def test_d3_01_cell_mask_is_cell_level_and_matches_measured_formulas() -> None:
    """逐格 mask == 实测 82 个受管公式格（88 公式 - 6 个表头底稿目录引用格）。"""
    spec = D301.SPEC_D301
    # 数量：4 行 ×10（区1 8-11）+ 4（占位 12）+ 10（合计 13）+ 4 行 ×4（区2 17-20）
    #      + 10（合计 21）+ 2（差异 23）= 82
    assert len(spec.masked_cells) == 82
    # 抽样：区1 审定列 E8、跨 sheet SUMIF 列 B8、合计行 B13、区2 审定 E17、差异 E23 均在 mask
    for cell in ("B8", "E8", "K11", "E12", "B13", "K13", "E17", "K20", "J21", "E23", "I23"):
        assert cell in spec.masked_cells, cell
    # 🔴 区2 手工列（B17/C17/D17/F17/G17/H17）不落 mask（账龄区无跨 sheet 公式，是手工空格）
    for cell in ("B17", "C17", "D17", "F17", "G17", "H17"):
        assert cell not in spec.masked_cells, cell


def test_d3_01_editable_data_cells_not_masked() -> None:
    """受管 editable 字段（A 项目名 / L 原因分析）绝不入 mask（D4-1 fail-closed 纪律）。"""
    D301.SPEC_D301.assert_data_cells_not_masked()  # 不抛即通过


def test_d3_01_cell_mask_is_engine_style_not_hardcoded_literal() -> None:
    """mask 由现算函数生成（`_build_cell_mask`），不是手写字面量（Property 5 纪律）。"""
    # 现算函数产出与 spec.cell_mask 一致（去重排序后）
    rebuilt = D301._build_cell_mask()
    assert set(rebuilt) == D301.SPEC_D301.masked_cells


# ─── 值来源判据（需求 4.4/4.5 的前置：cross_sheet 派生格不可 OO 直写）──────────

def test_d3_01_value_sources_and_oo_writable_discipline() -> None:
    """currentUnadjusted 来自 D3-2 跨 sheet 聚合 ⇒ 派生格不可 OO 直写；手工/说明列可写。"""
    spec = D301.SPEC_D301
    assert spec.source_of("current_unadjusted") is AdjudicationValueSource.cross_sheet
    assert spec.is_oo_writable("current_unadjusted") is False  # 派生格不可 OO 直写
    assert spec.is_oo_writable("current_audited") is False     # computed
    assert spec.is_oo_writable("reason_analysis") is True      # 手工文本
    assert spec.is_oo_writable("prior_rje") is True            # 手工录入


def test_d3_01_html_only_note_items_registered() -> None:
    """三个 note item（footer 之下 A25/A26/A30）+ TB 种子登记 HTML-only（同 D4-5 判例）。"""
    html_only = set(D301.SPEC_D301.html_only_item_ids)
    assert "D3-adj-note-aging-reason" in html_only
    assert "D3-adj-note-change-analysis" in html_only
    assert "D3-adj-note-conclusion" in html_only
    assert "D3-adj-trial-balance-amount" in html_only


def test_d3_01_per_cell_key_template_aligns_frontend() -> None:
    """per-cell 锚点模板与前端 `D3-adj-{section}-{rowKey}-{field}` 对齐（框架层用 {slug}）。"""
    tmpl = D301.SPEC_D301.per_cell_key_template
    assert tmpl == "D3-adj-{section}-{slug}-{field}"
    # 实例化后与前端 makeItemId('nature','其他','currentUnadjusted') 同形
    rendered = tmpl.format(section="nature", slug="其他", field="currentUnadjusted")
    assert rendered == "D3-adj-nature-其他-currentUnadjusted"


# ─── 🔴 变异必红：改成 D1-1 的 3 区（gross/bd/net）⇒ 与模板实测几何不符 ──────────

def _mutant_d1_style_three_sections() -> AdjudicationSheetSpec:
    """把 D3-1 声明变异成 D1-1 的 3 区 gross/bd/net（错法）—— 用于证明判据能打红。

    🔴 这不是照抄 D1-1 的合法几何，而是把 D3-1 的 sheet 强行套 D1-1 的区块结构，
       模拟「照 D1-1 推演」这个裁决 F3 明令禁止的错误。
    """
    return AdjudicationSheetSpec(
        managed_sheet=D301.MANAGED_SHEET_D301,
        sheet_key=D301.SHEET_KEY_D301,
        template_id=D301.TEMPLATE_ID_D301,
        header_rows=(5, 6),
        sections=(
            AdjudicationSection(section_key="gross", table_key="g", title_row=7,
                                first_data_row=8, last_data_row=9, subtotal_row=10),
            AdjudicationSection(section_key="bd", table_key="b", title_row=11,
                                first_data_row=12, last_data_row=13, subtotal_row=14),
            AdjudicationSection(section_key="net", table_key="n", title_row=15,
                                first_data_row=16, last_data_row=17, subtotal_row=18),
        ),
        row_mode=AdjudicationRowMode.fixed_rows,
    )


def test_mutation_d1_style_three_sections_is_detected() -> None:
    """🔴 变异检验：若 D3-1 被照 D1-1 推演成 3 区 gross/bd/net，则本判据面必红。

    对变异体运行与真声明相同的几何断言，断言它们**全部失败**（证明 test_d3_01_* 判据
    真的钉住了「两区 nature/aging + 实测行号」，而不是恒真装饰）。
    """
    mutant = _mutant_d1_style_three_sections()

    # 区块数变异检出：3 ≠ 2
    assert len(mutant.sections) != 2

    # section_key 变异检出：gross/bd/net ≠ nature/aging
    mutant_keys = [s.section_key for s in mutant.sections]
    assert mutant_keys != ["nature", "aging"]
    assert "gross" in mutant_keys  # 正是裁决 F3 禁止的 D1-1 推演形态

    # 几何变异检出：D1-1 推演的 net 区数据 16-17，与 D3-1 实测账龄区 17-20 不符
    assert mutant.section("nature") is None  # 变异体根本没有 nature 区
    assert mutant.section("aging") is None
    assert mutant.data_rows != D301.SPEC_D301.data_rows


def test_mutation_run_real_geometry_asserts_would_fail() -> None:
    """把真声明的几何断言直接对变异体跑一遍，逐条确认它们会抛 —— 变异必红的可执行证明。"""
    mutant = _mutant_d1_style_three_sections()

    def _assert_two_sections(spec: AdjudicationSheetSpec) -> None:
        assert len(spec.sections) == 2

    def _assert_keys(spec: AdjudicationSheetSpec) -> None:
        assert [s.section_key for s in spec.sections] == ["nature", "aging"]

    def _assert_aging_geometry(spec: AdjudicationSheetSpec) -> None:
        aging = spec.section("aging")
        assert aging is not None and aging.last_data_row == 20

    # 真声明：三条都通过
    _assert_two_sections(D301.SPEC_D301)
    _assert_keys(D301.SPEC_D301)
    _assert_aging_geometry(D301.SPEC_D301)

    # 变异体：三条都必红
    for fn in (_assert_two_sections, _assert_keys, _assert_aging_geometry):
        with pytest.raises(AssertionError):
            fn(mutant)


# ═══════════════════════════════════════════════════════════════════════════════
# Property 7: D3-1 逐格 mask 下受管金额字段仍判 editable
# ═══════════════════════════════════════════════════════════════════════════════
#
# Validates: Requirements 4.2, 7.2
# 变异：换回 `column_in_ranges` ⇒ 必红（钉住 D4-1 踩过的坑）
# ═══════════════════════════════════════════════════════════════════════════════


def test_d3_01_property7_editable_amount_fields_survive_cell_mask() -> None:
    """Property 7: 区2 账龄分类的手工列（B/C/D/F/G/H）在数据行 17-20 **不在** mask 内，
    因此审计师在 OO 里编辑它们能写回。

    🔴 这是 D4-1 踩过的坑：列向 column_in_ranges 会把整列判只读，但区2 同列在区1 是
    公式格、在区2 是手工格——逐格 mask 才能区分这种 per-row 差异。
    """
    spec = D301.SPEC_D301
    aging = spec.section("aging")
    assert aging is not None

    # 区2 数据行的手工列（B/C/D/F/G/H）——它们在 field_specs 里声明为 formula（因为
    # 区1 同列是公式），但逐格 mask 只覆盖真实公式格，不覆盖区2 的空格
    manual_cols_in_aging = ["B", "C", "D", "F", "G", "H"]
    for row in range(aging.first_data_row, aging.last_data_row + 1):
        for col in manual_cols_in_aging:
            assert not spec.is_cell_masked(col, row), (
                f"{col}{row} 在 mask 内——区2 手工格被误判只读（D4-1 列向 mask 的坑）"
            )

    # 对照：区1 同列同行号处**是**公式格（SUMIF），确实在 mask 内
    nature = spec.section("nature")
    assert nature is not None
    for row in range(nature.first_data_row, nature.first_data_row + 4):  # 8-11（前 4 行全列公式）
        for col in manual_cols_in_aging:
            assert spec.is_cell_masked(col, row), (
                f"{col}{row} 不在 mask 内——区1 SUMIF 公式格应被 mask 保护"
            )


def test_d3_01_property7_mutation_column_range_would_mask_editable() -> None:
    """变异检验 Property 7: 如果用列向区间（column_in_ranges）取代逐格 mask，
    区2 手工列 B17-B20/C17-C20/... 会被误判只读。

    模拟方法：取 mask 覆盖的列集合（从区1 公式列推导），然后对区2 数据行用列向判定——
    证明它会把区2 手工格也覆盖进去（false positive）。
    """
    spec = D301.SPEC_D301
    aging = spec.section("aging")
    assert aging is not None

    # 从 mask 中提取出现在区1 数据行的列集合（这些列在区1 是公式列）
    nature = spec.section("nature")
    assert nature is not None
    formula_cols_in_nature: set[str] = set()
    for cell in spec.masked_cells:
        col = "".join(ch for ch in cell if ch.isalpha())
        row_str = "".join(ch for ch in cell if ch.isdigit())
        if row_str and nature.first_data_row <= int(row_str) <= nature.last_data_row:
            formula_cols_in_nature.add(col)

    # 列向判定（column_in_ranges 错法）：如果用这些列作整列 mask，区2 手工格会被误判
    false_positives: list[str] = []
    for row in range(aging.first_data_row, aging.last_data_row + 1):
        for col in formula_cols_in_nature:
            if not spec.is_cell_masked(col, row):
                false_positives.append(f"{col}{row}")

    # 必须有 false positive（证明列向判定是错的）
    assert len(false_positives) > 0, (
        "列向 mask 没有产生 false positive——这说明区2 手工列与区1 公式列不重叠，"
        "则列向 mask 恰好不伤人（但 D3-1 实测应该重叠：B/C/D/F/G/H 在区1 是 SUMIF 公式）"
    )
    # 具体：B17-B20 等应在 false positive 里
    assert "B17" in false_positives


def test_d3_01_property7_computed_fields_not_oo_writable() -> None:
    """派生格（audited/change）和跨 sheet 格（currentUnadjusted）不可 OO 直写。"""
    spec = D301.SPEC_D301
    non_writable = [
        "current_unadjusted",  # cross_sheet
        "prior_audited",       # computed
        "current_audited",     # computed
        "change_amount",       # computed
        "change_rate",         # computed
    ]
    for col_key in non_writable:
        assert not spec.is_oo_writable(col_key), f"{col_key} 应为不可 OO 直写"

    writable = ["prior_unadjusted", "prior_aje", "prior_rje",
                "current_aje", "current_rje", "reason_analysis"]
    for col_key in writable:
        assert spec.is_oo_writable(col_key), f"{col_key} 应为可 OO 直写"


# ═══════════════════════════════════════════════════════════════════════════════
# Property 8: 只改 derived 不改 stored/snap → 覆盖标记数必须为 0
# ═══════════════════════════════════════════════════════════════════════════════
#
# Validates: Requirements 4.4
# 反证式：只改 `derived` 不改 `stored`/`snap` ⇒ 覆盖标记数为 0
#
# 🔴 Property 8 的同步器判据（"跑同步器"的那条）需要前端 vitest，此处只覆盖后端
# spec 层面的纪律：value_sources 声明 + is_oo_writable 纪律 + cell_mask 覆盖。
# ═══════════════════════════════════════════════════════════════════════════════


def test_d3_01_property8_cross_sheet_fields_have_correct_value_source() -> None:
    """Property 8 前置：cross_sheet 派生格有且仅有 currentUnadjusted。

    🔴 如果有其他字段被误标 cross_sheet，四态状态机会在那些格上也跑 snap 同步，
    导致手工录入被覆盖（stored ← derived 把人工值盖掉）。
    """
    spec = D301.SPEC_D301
    cross_sheet_fields = [
        k for k, v in spec.value_sources.items()
        if v is AdjudicationValueSource.cross_sheet
    ]
    assert cross_sheet_fields == ["current_unadjusted"], (
        f"cross_sheet 派生格应仅有 currentUnadjusted，实得 {cross_sheet_fields}"
    )


def test_d3_01_property8_derived_field_not_oo_writable() -> None:
    """Property 8: cross_sheet 派生格不可 OO 直写——否则 OO 回写会覆盖聚合结果。"""
    spec = D301.SPEC_D301
    assert not spec.is_oo_writable("current_unadjusted")


def test_d3_01_property8_computed_fields_exhaustive() -> None:
    """Property 8: computed 字段（审定数/变动额/变动率）不落库、不可写。"""
    spec = D301.SPEC_D301
    computed_fields = [
        k for k, v in spec.value_sources.items()
        if v is AdjudicationValueSource.computed
    ]
    expected = {"prior_audited", "current_audited", "change_amount", "change_rate"}
    assert set(computed_fields) == expected, f"computed 字段不完整: {computed_fields}"


def test_d3_01_property8_snap_key_pattern_matches_frontend() -> None:
    """Property 8: snap 键 = `{itemId}-snap`，与前端 `snapItemId()` 同规则。

    🔴 上游 13 条纯函数判据全绿但生产坏掉的教训：S4 可达性完全取决于 snap 怎么维护。
    后端不维护 snap（那是前端 watch 的事），但模板声明必须与前端键名规则对齐。
    """
    tmpl = D301.SPEC_D301.per_cell_key_template
    # 前端 snapItemId(section, rowKey, field) = `${makeItemId(section, rowKey, field)}-snap`
    # makeItemId(section, rowKey, field) = `D3-adj-${section}-${rowKey}-${field}`
    rendered = tmpl.format(section="nature", slug="其他", field="currentUnadjusted")
    snap_key = f"{rendered}-snap"
    assert snap_key == "D3-adj-nature-其他-currentUnadjusted-snap"
