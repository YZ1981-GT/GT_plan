# -*- coding: utf-8 -*-
"""G13-2 列同构判据 —— 骨架载体 + 父子行级 mask + footer 三约定混行。

spec: `g-cycle-single-region-detail-lanes` · Task 12 / C-11
　　　设计依据 `evidence/task8-c6-remaining-eight-template-logic.md` §7 + 本轮逐格实测

═══ 五层闭环 ═══
  ① `header_text` 逐列 == **模板两级表头逐格实测**（横向组 B9:D9 / 🔴 F9:J9 含 J）
  ② `json_key` 集合 == 前端骨架展示行的受管字段（双向相等）
  ③ 🔴 **受管载体是分类骨架不是工具明细** + 固定 10 行三方锁（provider ↔ 前端 ↔ 模板 A 列）
  ④ 🔴 `B`/`C` 判 `editable` 的裁决取证（3 格公式 / 普通公式非 shared 主格 / 逐行不同形台账）
  ⑤ footer 三种约定混行 / 零裸 IF / store 读写

🔴 本文件里凡涉及「这一格自己有没有公式文本」的断言一律**读 XML** ——
openpyxl 会自动展开 shared formula 成员格（G11 那轮踩过）。
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import openpyxl
import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync.phase5_g13_02_detail import (  # noqa: E402
    BOOLEAN_COLUMNS_G1302,
    CHILD_ROWS_G1302,
    FIELD_SPECS_G1302,
    FIRST_DATA_ROW_G1302,
    FOOTER_ROW_G1302,
    FOOTER_SHAPE_FACTS_G1302,
    FORMULA_COLUMNS_G1302,
    FORMULA_TEMPLATES_G1302,
    FRONTEND_ONLY_FIELDS_G1302,
    LAST_DATA_ROW_G1302,
    LEGACY_INSTRUMENT_STORE_ITEM_ID_G1302,
    MANAGED_SHEET_G1302,
    PARENT_ROWS_G1302,
    SPEC_G1302,
    STORE_ITEM_ID_G1302,
    TEMPLATE_BELONG_LABELS_G1302,
    TEMPLATE_PARENT_FORMULAS_G1302,
    TEMPLATE_ROW_LABELS_G1302,
    TOP_LEVEL_LEAF_ROWS_G1302,
)
from app.services.workpaper_sync.phase5_row_table_sheet import (  # noqa: E402
    iter_store_rows,
    merge_projection_into_store_rows,
)

TPL = _BACKEND / "wp_templates" / "G" / "G13 公允价值变动收益.xlsx"
#: 受管 sheet 的包内 XML 路径（workbook 顺序第 7 张）
SHEET_XML_G1302 = "xl/worksheets/sheet7.xml"

_FE = _REPO / "audit-platform/frontend/src/components/workpaper/composables"
FE_SKELETON_STORE = _FE / "g13SkeletonStore.ts"
FE_SKELETON_BUILDER = _FE / "g13CategorySkeleton.ts"
FE_DETAIL = _FE / "useG13Detail.ts"
FE_CONSTANTS = _FE / "g13Constants.ts"

_NON_MANAGED_FE_FIELDS = set(FRONTEND_ONLY_FIELDS_G1302)
_DATA_ROWS = tuple(range(FIRST_DATA_ROW_G1302, LAST_DATA_ROW_G1302 + 1))
_CELL_RE = re.compile(
    r'<c r="([A-Z]+\d+)"(?P<attrs>[^>]*?)(?:/>|>(?P<inner>.*?)</c>)', re.S
)


@pytest.fixture(scope="module")
def wb():
    book = openpyxl.load_workbook(TPL, data_only=False)
    try:
        yield book
    finally:
        book.close()


@pytest.fixture(scope="module")
def ws(wb):
    return wb[MANAGED_SHEET_G1302]


def _cell_map(path: Path) -> dict[str, str]:
    """`ref -> <c> 内容`。自闭合格记空串（不这样做正则会跨格吃到下一个公式）。"""
    with zipfile.ZipFile(path) as zf:
        xml = zf.read(SHEET_XML_G1302).decode("utf-8")
    return {m.group(1): (m.group("inner") or "") for m in _CELL_RE.finditer(xml)}


@pytest.fixture(scope="module")
def cells() -> dict[str, str]:
    return _cell_map(TPL)


@pytest.fixture(scope="module")
def neutralized() -> tuple[dict[str, str], tuple[str, ...]]:
    """真跑中性化：返回 `(after_cells, touched_refs)`。"""
    from app.services.workpaper_sync.g7_oo_crash_if_neutralize import (
        neutralize_oo_crash_if_formulas,
    )

    with tempfile.TemporaryDirectory() as td:
        cp = Path(td) / "g13.xlsx"
        shutil.copy2(TPL, cp)
        touched = neutralize_oo_crash_if_formulas(cp)
        after = _cell_map(cp)
    return after, touched


def _ts_interface_fields(path: Path, name: str) -> list[str]:
    src = path.read_text(encoding="utf-8")
    m = re.search(rf"export interface {name}[^{{]*\{{(?P<body>.*?)\n\}}", src, re.S)
    assert m, f"找不到 {name} 接口 —— 前端结构变了，判据须改写"
    return [
        fm.group(1)
        for line in m.group("body").splitlines()
        if (fm := re.match(r"\s*(\w+)\??:", line))
    ]


def _frontend_managed_fields() -> list[str]:
    """骨架展示行的受管字段（跨两个接口：汇总行 + 展示行扩展）。"""
    base = _ts_interface_fields(FE_SKELETON_BUILDER, "G13CategorySkeletonRow")
    ext = _ts_interface_fields(FE_SKELETON_STORE, "G13SkeletonDisplayRow")
    return [f for f in [*base, *ext] if f not in _NON_MANAGED_FE_FIELDS]


# ════════════════════════════════════════════════════════════════════════════
# ① 两级表头逐格实测
# ════════════════════════════════════════════════════════════════════════════
class TestTwoLevelHeaderMatchesTemplateCellByCell:
    def test_12_columns_in_excel_order_a_to_l(self) -> None:
        from openpyxl.utils import get_column_letter

        cols = [f[1] for f in FIELD_SPECS_G1302]
        assert cols == [get_column_letter(i) for i in range(1, 13)], (
            f"列序必须是 A..L 连续 12 列，实得 {cols}"
        )

    def test_effective_columns_equal_max_column_so_uuid_is_m(self, ws) -> None:
        from openpyxl.utils import get_column_letter

        effective = [
            get_column_letter(c)
            for c in range(1, ws.max_column + 1)
            if any(
                ws.cell(row=r, column=c).value not in (None, "")
                for r in (9, 10, *_DATA_ROWS, FOOTER_ROW_G1302)
            )
        ]
        assert effective == [get_column_letter(i) for i in range(1, 13)]
        assert ws.max_column == 12, "模板 max_column 变了 ⇒ uuid 列取值依据要重算"
        assert SPEC_G1302.uuid_col == "M"

    def test_template_has_zero_defined_names(self, wb) -> None:
        assert len(wb.defined_names) == 0

    def test_spec_declares_group_and_leaf_rows_not_single_header(self) -> None:
        assert SPEC_G1302.header_group_row == 9
        assert SPEC_G1302.header_leaf_row == 10
        assert SPEC_G1302.header_row is None, "两级表头不得同时声明单值 header_row"

    def test_r8_is_a_section_title_not_a_header_row(self, ws) -> None:
        assert str(ws["A8"].value or "") == "二、审计过程："
        assert ws["B8"].value is None, "段标题不该横跨到 B8"

    @pytest.mark.parametrize(
        "field", FIELD_SPECS_G1302, ids=[f[1] for f in FIELD_SPECS_G1302]
    )
    def test_header_text_equals_template_cell(self, field, ws) -> None:
        """有叶子取叶子（R10），纵向合并列取组行（R9）。"""
        from openpyxl.utils import column_index_from_string

        _key, col, _mode, _vt, _json_key, header_text, _group = field
        ci = column_index_from_string(col)
        leaf = ws.cell(row=10, column=ci).value
        group = ws.cell(row=9, column=ci).value
        expect = (
            str(leaf).strip()
            if (leaf and str(leaf).strip())
            else str(group or "").strip()
        )
        assert header_text == expect, (
            f"{col} 列 header_text 实得 {header_text!r}，模板逐格为 {expect!r}"
            f"（R9={group!r} / R10={leaf!r}）"
        )

    def test_exactly_two_horizontal_groups_on_r9(self, ws) -> None:
        """🔴 横向组只有两个：`B9:D9`（本期数）与 **`F9:J9`**（对应科目-公允价值变动）。"""
        groups = sorted(
            r.coord
            for r in ws.merged_cells.ranges
            if r.min_row == 9 and r.max_row == 9 and r.max_col > r.min_col
        )
        assert groups == ["B9:D9", "F9:J9"], f"R9 横向组实得 {groups}"
        starts = {c.split(":")[0] for c in groups}
        assert {f[6] for f in FIELD_SPECS_G1302 if f[6]} == starts

    def test_group_f9_j9_swallows_the_profit_and_loss_column(self, ws) -> None:
        """🔴 `F9:J9` **含 J 列**，而 `J10`=「计入损益」语义上不属该组。

        evidence §7.1 写作 `F9:I10` 不准确 —— 判据按实测钉住，防后人按文档「修正」模板。
        """
        assert ws["F9"].value == "对应科目-公允价值变动"
        assert ws["J10"].value == "计入损益"
        by_col = {f[1]: f for f in FIELD_SPECS_G1302}
        assert by_col["J"][6] == "F9", "J 列的组标题格必须如实指 F9"
        assert by_col["J"][5] == "计入损益"

    def test_four_columns_are_vertically_merged_over_r9_r10(self, ws) -> None:
        """`A`/`E`/`K`/`L` 是 R9:R10 纵向合并 ⇒ 无横向组、header_text 取 R9。"""
        vertical = sorted(
            r.coord
            for r in ws.merged_cells.ranges
            if r.min_row == 9 and r.max_row == 10 and r.min_col == r.max_col
        )
        assert vertical == ["A9:A10", "E9:E10", "K9:K10", "L9:L10"]
        by_col = {f[1]: f for f in FIELD_SPECS_G1302}
        for col in ("A", "E", "K", "L"):
            assert by_col[col][6] == "", f"{col} 是纵向合并，不该声明横向组标题格"


# ════════════════════════════════════════════════════════════════════════════
# ② json_key == 前端骨架展示行的受管字段
# ════════════════════════════════════════════════════════════════════════════
class TestJsonKeysMatchFrontendSkeletonRow:
    def test_declared_json_keys_equal_frontend_managed_fields(self) -> None:
        declared = {f[4] for f in FIELD_SPECS_G1302}
        frontend = set(_frontend_managed_fields())
        assert declared == frontend, (
            "声明的 json_key 与前端骨架展示行的受管字段必须**双向相等**。\n"
            f"  前端有而声明缺：{sorted(frontend - declared)}\n"
            f"  声明有而前端缺：{sorted(declared - frontend)}"
        )
        assert len(declared) == 12

    def test_managed_field_order_matches_excel_column_order_except_belong_label(
        self,
    ) -> None:
        """🔴 与 G11/G14 的差异：G13 的受管字段**跨两个接口**。

        11 个在 `G13CategorySkeletonRow`（原有汇总行），只有 `belongLabel`（E 列）在本轮
        新增的 `G13SkeletonDisplayRow` 里 ⇒ 不能像别家那样直接断言「前端字段序 == 列序」。
        判据改为：**剔掉 E 列后**，汇总行里的 11 个受管字段顺序逐字等于模板列序。
        """
        base = [
            f
            for f in _ts_interface_fields(FE_SKELETON_BUILDER, "G13CategorySkeletonRow")
            if f not in _NON_MANAGED_FE_FIELDS
        ]
        expect = [f[4] for f in FIELD_SPECS_G1302 if f[1] != "E"]
        assert base == expect, f"\n  前端：{base}\n  声明（剔 E）：{expect}"
        assert len(base) == 11
        ext = _ts_interface_fields(FE_SKELETON_STORE, "G13SkeletonDisplayRow")
        assert "belongLabel" in ext

    def test_seven_non_template_fields_are_declared_and_present(self) -> None:
        declared = {f[4] for f in FIELD_SPECS_G1302}
        fe = set(
            _ts_interface_fields(FE_SKELETON_BUILDER, "G13CategorySkeletonRow")
            + _ts_interface_fields(FE_SKELETON_STORE, "G13SkeletonDisplayRow")
        )
        assert len(FRONTEND_ONLY_FIELDS_G1302) == 7
        for f in FRONTEND_ONLY_FIELDS_G1302:
            assert f in fe, f"{f} 不在前端骨架行接口里 ⇒ 登记表过期"
            assert f not in declared, f"{f} 不是模板列，不应受管"

    def test_bs_reconciled_is_frontend_only_because_template_has_one_check_column(
        self, ws
    ) -> None:
        """模板只有 `K` 一个核对列 ⇒ 前端拆的 `bsReconciled` 留在前端不受管。"""
        assert "bsReconciled" in FRONTEND_ONLY_FIELDS_G1302
        by_col = {f[1]: f for f in FIELD_SPECS_G1302}
        assert by_col["K"][4] == "plReconciled", (
            "K 列语义是 `=J=D`（计入损益↔审定数）⇒ json_key 必须是 plReconciled"
        )
        assert ws["K9"].value == "核对"
        assert [f[1] for f in FIELD_SPECS_G1302 if f[5] == "核对"] == ["K"]

    def test_manual_override_flag_is_not_a_template_column(self) -> None:
        """🔴 `manualOverride` 是骨架落库的控制位，不是模板列 ⇒ 不受管。"""
        assert "manualOverride" in FRONTEND_ONLY_FIELDS_G1302
        assert "manualOverride" not in {f[4] for f in FIELD_SPECS_G1302}
        src = FE_SKELETON_STORE.read_text(encoding="utf-8")
        assert "manualOverride" in src
        # 手工覆盖优先的实现必须在场（否则 OO 回流会被汇总立刻冲掉）
        assert "export function mergeSkeletonOverrides(" in src
        assert "if (!hit?.manualOverride)" in src


# ════════════════════════════════════════════════════════════════════════════
# ③ 🔴 受管载体是分类骨架 + 固定 10 行三方锁
# ════════════════════════════════════════════════════════════════════════════
class TestSkeletonIsTheManagedCarrierNotTheInstrumentDetail:
    def test_store_item_is_the_skeleton_not_the_instrument_rows(self) -> None:
        """🔴 本 lane 最易接错的一处：受管 store 是骨架键，不是工具明细键。

        模板 R11-R20 是固定 10 个损益表项目，而 `G13-detail-rows` 存动态增删的金融工具级
        明细 ⇒ 两侧行模型不同构，按序映射会把第 N 条工具写进第 N 个损益项目行（产出错数）。
        """
        assert STORE_ITEM_ID_G1302 == "G13-detail-skeleton"
        assert SPEC_G1302.store_item_id == STORE_ITEM_ID_G1302
        assert LEGACY_INSTRUMENT_STORE_ITEM_ID_G1302 == "G13-detail-rows"
        assert STORE_ITEM_ID_G1302 != LEGACY_INSTRUMENT_STORE_ITEM_ID_G1302

    def test_both_store_keys_are_source_backed_in_the_frontend(self) -> None:
        src = FE_DETAIL.read_text(encoding="utf-8")
        assert f"const ITEM_ID_SKELETON = '{STORE_ITEM_ID_G1302}'" in src
        assert f"const ITEM_ID_ROWS = '{LEGACY_INSTRUMENT_STORE_ITEM_ID_G1302}'" in src
        # 骨架必须真的被持久化（否则受管区永远是空表）
        assert "function persistSkeleton(): void {" in src
        assert "debouncedSave(ITEM_ID_SKELETON" in src

    def test_registry_plan_points_at_the_skeleton_only(self) -> None:
        from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY

        plan = STORE_MERGE_REGISTRY["g13.fair_value_changes_detail"]
        assert [i.item_id for i in plan.items] == [STORE_ITEM_ID_G1302]
        assert plan.oo_crash_neutralization_fn == "neutralize_oo_crash_if_formulas"

    def test_provider_row_labels_equal_template_column_a(self, ws) -> None:
        """三方锁①：provider 行名表逐字等于模板 A11-A20（含缩进空格）。"""
        actual = tuple(
            str(ws.cell(row=r, column=1).value or "") for r in _DATA_ROWS
        )
        assert TEMPLATE_ROW_LABELS_G1302 == actual, (
            f"provider 行名表与模板 A 列不一致。\n  声明：{TEMPLATE_ROW_LABELS_G1302}\n  模板：{actual}"
        )
        assert len(TEMPLATE_ROW_LABELS_G1302) == 10

    def test_frontend_template_row_labels_equal_provider(self) -> None:
        """三方锁②：前端 `TEMPLATE_ROW_LABELS_G13` 与 provider 的同名表双向相等。"""
        src = FE_SKELETON_STORE.read_text(encoding="utf-8")
        m = re.search(
            r"export const TEMPLATE_ROW_LABELS_G13 = \[(?P<body>.*?)\n\] as const", src, re.S
        )
        assert m, "找不到前端 TEMPLATE_ROW_LABELS_G13 —— 行名真源被删了"
        assert re.findall(r"'([^']*)'", m.group("body")) == list(TEMPLATE_ROW_LABELS_G1302)

    def test_frontend_belong_labels_equal_provider_and_template(self, ws) -> None:
        """三方锁③：E 列科目名（🔴 `E20` 模板为空 ⇒ 空串）。"""
        actual = tuple(str(ws.cell(row=r, column=5).value or "") for r in _DATA_ROWS)
        assert TEMPLATE_BELONG_LABELS_G1302 == actual
        assert TEMPLATE_BELONG_LABELS_G1302[-1] == "", "E20 模板为空"
        src = FE_SKELETON_STORE.read_text(encoding="utf-8")
        m = re.search(
            r"export const TEMPLATE_BELONG_LABELS_G13 = \[(?P<body>.*?)\n\] as const",
            src,
            re.S,
        )
        assert m and re.findall(r"'([^']*)'", m.group("body")) == list(
            TEMPLATE_BELONG_LABELS_G1302
        )

    def test_row_set_single_source_is_the_adjudication_items(self) -> None:
        """🔴 行序单一真源 = `g13Constants.G13_ADJUDICATION_ITEMS`（恰 10 项）。

        这推翻 Task 2「发现 I：前端无骨架无父子字段」—— 骨架能力在 `g13CategorySkeleton.ts`
        与 `g13Constants.ts` 里，扫 `isParent`/`parentId`/`children` 字段扫不到。
        """
        const_src = FE_CONSTANTS.read_text(encoding="utf-8")
        m = re.search(
            r"export const G13_ADJUDICATION_ITEMS: G13AdjudicationDef\[\] = \[(?P<body>[\s\S]*?)\n\]",
            const_src,
        )
        assert m, "找不到 G13_ADJUDICATION_ITEMS"
        labels = re.findall(r"^\s*label: '([^']+)',", m.group("body"), re.M)
        assert len(labels) == 10, f"固定行集实得 {len(labels)} 项"
        assert labels == [s.strip() for s in TEMPLATE_ROW_LABELS_G1302], (
            "前端 label（无缩进）应逐项等于模板 A 列去掉前导空格后的值"
        )
        skel_src = FE_SKELETON_STORE.read_text(encoding="utf-8")
        assert "G13_ADJUDICATION_ITEMS.map(" in skel_src, (
            "骨架行序必须从 G13_ADJUDICATION_ITEMS 派生，不得再手写一份"
        )

    def test_parent_child_structure_comes_from_kind_and_indent(self) -> None:
        """🔴 父子关系由 `kind`+`indent` 表达（不需要新加 parentId 字段）。

        `main` indent=0 → 顶层（R11/R14/R17/R19/R20）· `ofWhich`/`derivative` indent=1 → 子行。
        """
        const_src = FE_CONSTANTS.read_text(encoding="utf-8")
        m = re.search(
            r"export const G13_ADJUDICATION_ITEMS: G13AdjudicationDef\[\] = \[(?P<body>[\s\S]*?)\n\]",
            const_src,
        )
        assert m
        kinds = re.findall(r"^\s*kind: '(\w+)',", m.group("body"), re.M)
        indents = [int(x) for x in re.findall(r"^\s*indent: (\d+),", m.group("body"), re.M)]
        assert len(kinds) == len(indents) == 10
        top_rows = tuple(
            FIRST_DATA_ROW_G1302 + i for i, k in enumerate(indents) if k == 0
        )
        assert top_rows == (*PARENT_ROWS_G1302, *TOP_LEVEL_LEAF_ROWS_G1302), (
            f"indent=0 的行实得 {top_rows}"
        )
        child_rows = tuple(
            FIRST_DATA_ROW_G1302 + i for i, k in enumerate(indents) if k == 1
        )
        assert child_rows == CHILD_ROWS_G1302
        assert {kinds[i - FIRST_DATA_ROW_G1302] for i in CHILD_ROWS_G1302} == {
            "ofWhich",
            "derivative",
        }


# ════════════════════════════════════════════════════════════════════════════
# ④ 🔴 B/C 判 editable 的裁决取证 + D/I/J/K formula + K 布尔
# ════════════════════════════════════════════════════════════════════════════
class TestRowLevelMaskForcesEditableOnBAndC:
    def test_b_and_c_carry_formulas_on_exactly_three_parent_rows(self, cells) -> None:
        """🔴 裁决前提：`B`/`C` 在数据区只有 **3 格**有公式（父行），其余 7 格空。"""
        for col in ("B", "C"):
            with_f = tuple(r for r in _DATA_ROWS if "<f" in cells.get(f"{col}{r}", ""))
            assert with_f == PARENT_ROWS_G1302, (
                f"{col} 列带公式的行实得 {with_f}，声明父行为 {PARENT_ROWS_G1302}"
            )
            empty = tuple(r for r in _DATA_ROWS if "<f" not in cells.get(f"{col}{r}", ""))
            assert empty == (*CHILD_ROWS_G1302, *TOP_LEVEL_LEAF_ROWS_G1302)
            assert len(empty) == 7

    def test_b_and_c_are_declared_editable_not_formula(self) -> None:
        """🔴 列级 mode 对「3 行公式 + 7 行空」无解 ⇒ 只能 `editable`。

        判 `formula` 会让 materialize 对 7 个无公式格抛 `ProtectedRegionWriteError`
        （要求 `view.has_formula`）；判 `auto_source` 会对 3 个公式格抛（要求**不是**公式）。
        """
        by_col = {f[1]: f for f in FIELD_SPECS_G1302}
        for col in ("B", "C"):
            assert by_col[col][2] == "editable", f"{col} 列 mode 实得 {by_col[col][2]!r}"
        assert not set(FORMULA_COLUMNS_G1302) & {"B", "C"}
        assert "B" not in "".join(SPEC_G1302.formula_mask)
        assert "C" not in "".join(SPEC_G1302.formula_mask)

    def test_parent_cells_are_plain_formulas_not_shared_masters(self, cells) -> None:
        """🔴 裁决成立的关键：三格是**普通公式**而非 shared 主格。

        `excel_materialize` 对非 formula/auto_source 的格只拦「共享公式**主格**」
        （`SharedFormulaMasterWriteError`）。这三格若哪天被模板改成 shared 主格，
        `editable` 立刻不可行 —— 本判据就是那道警报。
        """
        for (col, row) in TEMPLATE_PARENT_FORMULAS_G1302:
            inner = cells[f"{col}{row}"]
            assert "<f>" in inner, f"{col}{row} 不再是普通 <f> 形态：{inner[:60]!r}"
            assert 't="shared"' not in inner, (
                f"{col}{row} 变成了 shared formula ⇒ 判 editable 会撞 "
                "SharedFormulaMasterWriteError，裁决必须重做"
            )

    @pytest.mark.parametrize(
        "key", sorted(TEMPLATE_PARENT_FORMULAS_G1302), ids=lambda k: f"{k[0]}{k[1]}"
    )
    def test_parent_formula_ledger_matches_template_cell_by_cell(self, key, ws) -> None:
        """父行公式**逐行不同形**（R17 只汇一个子行）⇒ 落台账、判据按行比对。"""
        col, row = key
        got = ws[f"{col}{row}"].value
        assert got == TEMPLATE_PARENT_FORMULAS_G1302[key], (
            f"{col}{row} 模板实得 {got!r}，台账为 {TEMPLATE_PARENT_FORMULAS_G1302[key]!r}"
        )

    def test_parent_formulas_are_not_uniform_so_one_template_cannot_express_them(
        self,
    ) -> None:
        """钉住「为什么不能进 formula_templates」：三行形态互不相同。"""
        b_forms = {
            r: TEMPLATE_PARENT_FORMULAS_G1302[("B", r)] for r in PARENT_ROWS_G1302
        }
        assert b_forms == {11: "=B12+B13", 14: "=B15+B16", 17: "=B18"}
        assert len(set(b_forms.values())) == 3, "三行形态应互不相同"
        assert TEMPLATE_PARENT_FORMULAS_G1302[("B", 17)].count("+") == 0, (
            "R17 只有一个子行 R18 ⇒ 不是加法"
        )
        assert not set(TEMPLATE_PARENT_FORMULAS_G1302) & {
            (c, r) for c in FORMULA_TEMPLATES_G1302 for r in _DATA_ROWS
        }

    def test_top_level_leaf_rows_must_not_be_treated_as_parents(self) -> None:
        """🔴 `R19`/`R20` 是**无子行的顶层行**（B/C 手填）。

        spec 原文把它们与父行混为一类；照那样把 B/C 判 formula 会覆盖用户手填值
        （与 G8 误标同型危害）。
        """
        assert TOP_LEVEL_LEAF_ROWS_G1302 == (19, 20)
        assert not set(TOP_LEVEL_LEAF_ROWS_G1302) & set(PARENT_ROWS_G1302)
        assert not any(r in TOP_LEVEL_LEAF_ROWS_G1302 for _c, r in TEMPLATE_PARENT_FORMULAS_G1302)

    def test_formula_columns_are_exactly_the_every_row_formula_columns(
        self, cells
    ) -> None:
        from openpyxl.utils import get_column_letter

        every_row = tuple(
            get_column_letter(c)
            for c in range(1, 13)
            if all(
                "<f" in cells.get(f"{get_column_letter(c)}{r}", "") for r in _DATA_ROWS
            )
        )
        assert FORMULA_COLUMNS_G1302 == every_row == ("D", "I", "J", "K")

    @pytest.mark.parametrize("col", sorted(FORMULA_TEMPLATES_G1302))
    def test_formula_template_renders_to_every_data_row(self, col: str, ws) -> None:
        """四列逐行同形 ⇒ 逐格可比（openpyxl 会展开 shared 成员格）。"""
        from openpyxl.utils import column_index_from_string

        ci = column_index_from_string(col)
        for r in _DATA_ROWS:
            got = ws.cell(row=r, column=ci).value
            assert got == FORMULA_TEMPLATES_G1302[col].format(r=r), (
                f"{col}{r} 模板实得 {got!r}，声明渲染为 "
                f"{FORMULA_TEMPLATES_G1302[col].format(r=r)!r}"
            )

    def test_shared_masters_sit_on_r12_for_d_i_j(self, cells) -> None:
        """🔴 `D`/`I`/`J` 的 shared 主格在 **R12**（ref `X12:X20`），R11 是独立普通公式。

        首版把 `K` 也归进来 ⇒ 判据打红。实测 K 自成一格，见下一条。
        """
        for col in ("D", "I", "J"):
            assert "<f>" in cells[f"{col}11"], f"{col}11 应是普通公式"
            assert re.search(
                rf'<f t="shared" ref="{col}12:{col}20" si="\d+">', cells[f"{col}12"]
            ), f"{col}12 不再是 shared 主格：{cells[f'{col}12'][:70]!r}"
            for r in range(13, 21):
                assert re.search(r'<f t="shared" si="\d+"/>', cells[f"{col}{r}"]), (
                    f"{col}{r} 不再是 shared 成员格"
                )
            assert 't="shared"' not in cells[f"{col}{FOOTER_ROW_G1302}"] or col == "D", (
                f"{col}21 不应属数据区那个 shared 组"
            )

    def test_k_shared_group_starts_at_r13_and_crosses_the_footer(self, cells) -> None:
        """🔴 `K` 列自成一格：`K11`/`K12` **两格都是普通公式**，**`K13` 才是主格**，
        且 ref = **`K13:K21`** —— 该组**跨越 footer 边界**。

        后果登记：数据区与合计行共用同一份公式文本 ⇒ 改 `K13` 会同时改掉 footer 的布尔格。
        照 D/I/J 的形态推演 K 会得到错误的组区间（首版判据就是这么红的）。
        """
        assert "<f>" in cells["K11"] and 't="shared"' not in cells["K11"]
        assert "<f>" in cells["K12"] and 't="shared"' not in cells["K12"]
        assert re.search(r'<f t="shared" ref="K13:K21" si="(\d+)">J13=D13</f>', cells["K13"]), (
            f"K13 不再是 ref=K13:K21 的 shared 主格：{cells['K13'][:80]!r}"
        )
        si = re.search(r'si="(\d+)"', cells["K13"]).group(1)  # type: ignore[union-attr]
        for r in range(14, FOOTER_ROW_G1302 + 1):
            assert cells[f"K{r}"].startswith(f'<f t="shared" si="{si}"/>'), (
                f"K{r} 不再是 si={si} 的成员格：{cells[f'K{r}'][:60]!r}"
            )
        assert FOOTER_ROW_G1302 == 21, "组区间 K13:K21 的右端就是 footer 行"

    def test_k_is_a_boolean_check_column(self) -> None:
        """🔴 裁决 G1R-H4：`K=J=D` 求值 TRUE/FALSE ⇒ boolean + formula（不入 store）。"""
        by_col = {f[1]: f for f in FIELD_SPECS_G1302}
        assert by_col["K"][2] == "formula", "布尔列标 editable 会让 TRUE/FALSE 进 store"
        assert by_col["K"][3] == "boolean"
        assert BOOLEAN_COLUMNS_G1302 == ("K",)
        assert FORMULA_TEMPLATES_G1302["K"] == "=J{r}=D{r}"
        assert [f[1] for f in FIELD_SPECS_G1302 if f[3] == "boolean"] == ["K"]

    def test_every_formula_mode_field_is_covered_by_formula_mask(self) -> None:
        from app.services.workpaper_sync.contracts import column_in_ranges

        mask = SPEC_G1302.formula_mask
        assert mask == ("D11:D20", "I11:I20", "J11:J20", "K11:K20")
        for key, col, mode, _vt, _json, _hdr, _grp in FIELD_SPECS_G1302:
            if mode != "formula":
                continue
            assert column_in_ranges(col, mask), (
                f"{key}（列 {col}）声明 mode=formula 但不在 formula_mask {mask} 内"
            )


# ════════════════════════════════════════════════════════════════════════════
# ⑤ footer 三约定混行 / 零裸 IF / 几何 / store 读写
# ════════════════════════════════════════════════════════════════════════════
class TestFooterAndNeutralizationAndStore:
    def test_footer_mixes_three_conventions(self, ws) -> None:
        """🔴 同一 footer 行三种约定：枚举相加 3 格 + 纯 SUM 2 格 + 布尔 1 格。"""
        facts = FOOTER_SHAPE_FACTS_G1302
        assert facts["kind"] == "mixed_enumerated_sum_and_boolean"
        top = (*PARENT_ROWS_G1302, *TOP_LEVEL_LEAF_ROWS_G1302)
        for col in facts["enumerated_columns"]:  # type: ignore[union-attr]
            want = "=" + "+".join(f"{col}{r}" for r in top)
            assert ws[f"{col}{FOOTER_ROW_G1302}"].value == want, (
                f"{col}21 实得 {ws[f'{col}{FOOTER_ROW_G1302}'].value!r}，应为 {want!r}"
            )
            assert facts["enumerated_detail"][f"{col}21"] == want  # type: ignore[index]
        for col in facts["pure_sum_columns"]:  # type: ignore[union-attr]
            assert ws[f"{col}{FOOTER_ROW_G1302}"].value == (
                f"=SUM({col}{FIRST_DATA_ROW_G1302}:{col}{LAST_DATA_ROW_G1302})"
            )
        assert ws[f"K{FOOTER_ROW_G1302}"].value == "=J21=D21"
        assert facts["boolean_columns"] == ["K"]

    def test_enumerated_footer_adds_top_level_rows_only(self) -> None:
        """枚举相加加的是**五个顶层行**，不含子行 —— 否则会双重加计。"""
        detail = FOOTER_SHAPE_FACTS_G1302["enumerated_detail"]
        assert isinstance(detail, dict)
        refs = re.findall(r"B(\d+)", detail["B21"])
        assert tuple(int(x) for x in refs) == (
            *PARENT_ROWS_G1302,
            *TOP_LEVEL_LEAF_ROWS_G1302,
        )
        assert not set(int(x) for x in refs) & set(CHILD_ROWS_G1302)

    def test_footer_c21_is_shared_master_and_d21_is_member(self, cells) -> None:
        """🔴 `C21` 是 shared 主格（ref=C21:D21）、`D21` 是成员格 ⇒ 读 XML 才看得出。"""
        assert re.search(r'<f t="shared" ref="C21:D21" si="\d+">', cells["C21"])
        assert re.search(r'<f t="shared" si="\d+"/>', cells["D21"])
        assert re.search(r'<f t="shared" si="\d+"/>', cells["K21"]), "K21 是成员格（主格 K11）"
        assert "<f>" in cells["B21"] and 't="shared"' not in cells["B21"]

    def test_footer_empty_columns_have_no_formula(self, cells) -> None:
        for col in FOOTER_SHAPE_FACTS_G1302["empty_columns"]:  # type: ignore[union-attr]
            assert "<f" not in cells.get(f"{col}{FOOTER_ROW_G1302}", "")

    def test_footer_carries_total_formula_is_declared(self, ws) -> None:
        assert SPEC_G1302.footer_carries_total_formula is True
        assert str(ws[f"A{FOOTER_ROW_G1302}"].value) == SPEC_G1302.footer_marker == "合计"

    def test_managed_sheet_has_zero_bare_if_so_neutralization_is_a_no_op_here(
        self, neutralized, cells
    ) -> None:
        """🔴 受管 sheet **零裸 IF**（整册 11 格全在别的 sheet）⇒ 中性化不动本表。

        与 G11 的 44 格相反 —— 这正是 `D`/`I`/`J`/`K` 能判 `formula` 的前提
        （若中性化摘了它们的 `<f>`，materialize 会抛）。
        """
        after, touched = neutralized
        mine = [t for t in touched if SHEET_XML_G1302.split("/")[-1] in t]
        assert mine == [], f"受管 sheet 被中性化命中 {len(mine)} 格 ⇒ formula 声明要重做"
        assert touched, "整册应仍有裸 IF（别的 sheet）—— 全零说明中性化没跑"
        for col in FORMULA_COLUMNS_G1302:
            for r in _DATA_ROWS:
                assert "<f" in after[f"{col}{r}"], f"{col}{r} 中性化后丢了公式"
        assert not any(re.search(r"\bIF\(", v) for v in FORMULA_TEMPLATES_G1302.values())

    def test_single_region_r11_to_r20_is_10_rows(self) -> None:
        assert (SPEC_G1302.first_data_row, SPEC_G1302.last_data_row) == (11, 20)
        assert len(_DATA_ROWS) == 10
        assert SPEC_G1302.footer_row == FOOTER_ROW_G1302 == 21
        assert SPEC_G1302.footer_row == SPEC_G1302.last_data_row + 1
        assert not SPEC_G1302.row_section_field, "单区不得声明 row_section_field"
        assert SPEC_G1302.table_key == "g13_detail_skeleton"

    def test_audit_note_rows_below_footer_are_out_of_scope(self, ws) -> None:
        assert str(ws["A22"].value or "").startswith("三、审计说明")
        assert str(ws["A26"].value or "").startswith("编制说明")
        assert 22 > SPEC_G1302.footer_row

    def test_row_identity_key_is_rowkey_not_rowid(self) -> None:
        """🔴 固定行集 ⇒ 行身份是业务键 `rowKey`（同 G14），不是工具明细的 `rowId`。"""
        assert SPEC_G1302.row_identity_key == "rowKey"
        detail_rows = _ts_interface_fields(FE_DETAIL, "G13DetailRow")
        assert detail_rows[0] == "rowId", "工具明细行仍用 rowId（两者不得混同）"
        assert "rowKey" in _ts_interface_fields(
            FE_SKELETON_STORE, "G13SkeletonStoredRow"
        )

    def test_iter_reads_every_row_by_rowkey(self) -> None:
        payload = [
            {"rowKey": "trading_assets"},
            {"rowKey": "designated_fv_assets"},
            {"rowKey": "other"},
        ]
        assert [rid for rid, _ in iter_store_rows(SPEC_G1302, payload)] == [
            "trading_assets",
            "designated_fv_assets",
            "other",
        ]

    def test_duplicate_rowkey_fails_closed(self) -> None:
        from app.services.workpaper_sync.phase5_row_table_sheet import (
            RowTableStorePayloadError,
        )

        with pytest.raises(RowTableStorePayloadError, match="重复行身份"):
            list(
                iter_store_rows(
                    SPEC_G1302, [{"rowKey": "other"}, {"rowKey": "other"}]
                )
            )

    def test_merge_keys_rows_by_rowkey_and_does_not_grow_the_fixed_set(self) -> None:
        class _FV:
            def __init__(self, key: str, row_key: str, value):
                self.stable_key = key
                self.row_key = row_key
                self.value = value
                self.is_protected = False

        key = f"{SPEC_G1302.table_key}/trading_assets/current_unadjusted"

        class _Proj:
            def stable_keys(self):
                return [key]

            def get(self, k):
                return _FV(k, "trading_assets", 4321) if k == key else None

        rows, applied, _visited, touched = merge_projection_into_store_rows(
            SPEC_G1302,
            projection=_Proj(),
            base_rows=[{"rowKey": "trading_assets"}, {"rowKey": "other"}],
        )
        assert applied == 1 and touched == {"trading_assets"}
        hit = next(r for r in rows if r["rowKey"] == "trading_assets")
        assert hit["currentUnadjusted"] == 4321
        assert "currentAudited" not in hit, "公式列受保护，不该出现在 store 行里"
        assert [r["rowKey"] for r in rows] == ["trading_assets", "other"]
