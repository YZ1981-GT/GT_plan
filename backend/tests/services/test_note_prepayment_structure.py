"""附注模板预付款项章节结构契约（对齐源模版两级表头）。

- 上市版 §五、7 预付款项（``基础数据/附注模版/上市报表附注.md``）
- 国企版 §八、7 预付款项（``基础数据/附注模版/国企报表附注.md``）
- 底稿源模板：``F1 预付账款.xlsx`` 的 ``附注披露信息(上市公司)`` / ``附注披露信息(国企)``
- 列存在性口径交叉印证：``note_check_preset_formulas.json`` F7-1~F7-14（listed / soe 双份）

卡点目的：

1. ``scripts/fix/rebuild_note_from_md.py`` 从 md 重建模板时会把两级表头压扁
   （第二行表头降级成 ``row_type: header_label`` 假数据行）；
2. 修订前国企第 3 张表与第 2 张**同名**，与同步载荷键错位形成孤儿子表；
3. 上市第 3 张表名误用标签列列头「单位名称」。

以上任一回退都会被本文件在 CI 阶段拦住，提示重跑
``backend/scripts/fix/fix_note_prepayment_structure.py``。

spec: .kiro/specs/f1-prepayment-disclosure-template-alignment/ R1 / R6.1
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
LISTED_PATH = _BACKEND / "data" / "note_template_listed.json"
SOE_PATH = _BACKEND / "data" / "note_template_soe.json"
CHECK_PRESET_PATH = _BACKEND / "data" / "note_check_preset_formulas.json"

LISTED_SECTION = "五、7"
SOE_SECTION = "八、7"
#: `--check` 与本文件均按**集合**判定 `_aligned_by`（历史批次写的是归档 spec 名）
ALIGNED_BY_ACCEPTED = frozenset({
    "f1-four-table-extraction-and-disclosure-alignment",
    "f1-prepayment-disclosure-template-alignment",
})
_FIX_HINT = "请重跑 python backend/scripts/fix/fix_note_prepayment_structure.py"

#: 底稿源模板（运行时权威）—— 三向比对的第一源
SOURCE_XLSX = _BACKEND / "wp_templates" / "F" / "F1 预付账款.xlsx"
SOURCE_SHEETS = {
    "listed": "附注披露信息(上市公司)",
    "soe": "附注披露信息(国企)",
}
#: 同步载荷列头常量所在文件（三向比对的第三源）
SYNC_PAYLOAD_TS = (
    _BACKEND.parent
    / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
    / "composables" / "f1DisclosureSyncPayload.ts"
)

T_LISTED = ("预付款项按账龄披露", "账龄超过1年的重要预付款项",
            "按预付对象归集的预付款项期末余额前五名单位情况")
T_SOE = ("预付款项按账龄列示", "账龄超过1年的大额预付款项",
         "按欠款方归集的期末余额前五名的预付款项")

AGING_COLUMN_KEYS = ["label", "end_amount", "end_pct", "prior_amount", "prior_pct"]
AGING_TAIL_ROWS = ["小计", "减：减值准备", "合计"]


def _load_section(path: Path, section_number: str) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    sec = next(
        (s for s in doc.get("sections") or [] if str(s.get("section_number")) == section_number),
        None,
    )
    assert sec is not None, f"{path.name} 缺少 {section_number} 章节"
    return sec


@pytest.fixture(scope="module")
def listed() -> dict[str, Any]:
    return _load_section(LISTED_PATH, LISTED_SECTION)


@pytest.fixture(scope="module")
def soe() -> dict[str, Any]:
    return _load_section(SOE_PATH, SOE_SECTION)


def _names(section: dict[str, Any]) -> list[str]:
    return [str(t.get("name")) for t in section.get("tables") or []]


def _get(section: dict[str, Any], name: str) -> dict[str, Any]:
    tbl = next((t for t in section.get("tables") or [] if str(t.get("name")) == name), None)
    assert tbl is not None, f"缺表「{name}」（现有：{_names(section)}）；{_FIX_HINT}"
    return tbl


# ─── 对齐标记与表清单 ─────────────────────────────────────────────────────────

def test_aligned_by_stamped(listed: dict[str, Any], soe: dict[str, Any]) -> None:
    for sec in (listed, soe):
        assert sec.get("_aligned_by") in ALIGNED_BY_ACCEPTED, _FIX_HINT


@pytest.mark.parametrize(
    ("fixture_name", "expected"),
    [("listed", T_LISTED), ("soe", T_SOE)],
)
def test_table_names_exact(
    fixture_name: str, expected: tuple[str, ...], request: pytest.FixtureRequest
) -> None:
    """表名逐字对齐（与 f1DisclosureSyncPayload.ts 子表键一致），且顺序不变。"""
    section = request.getfixturevalue(fixture_name)
    assert _names(section) == list(expected), _FIX_HINT


@pytest.mark.parametrize("fixture_name", ["listed", "soe"])
def test_table_names_unique(fixture_name: str, request: pytest.FixtureRequest) -> None:
    """表名唯一：国企第 3 张表曾与第 2 张同名 → 同步孤儿子表。"""
    names = _names(request.getfixturevalue(fixture_name))
    assert len(set(names)) == len(names), f"表名重复：{names}；{_FIX_HINT}"


def test_obsolete_listed_table_name_gone(listed: dict[str, Any]) -> None:
    """旧表名「单位名称」（实为标签列列头）已改名迁移。"""
    assert "单位名称" not in _names(listed), _FIX_HINT


# ─── 两级表头（按账龄表） ─────────────────────────────────────────────────────

#: 按账龄表列头字面（逐字取源 xlsx，**含空格**；上市金额列双空格、国企单空格）
AGING_LABEL_COL = "账  龄"
AGING_HEADER_CASES = [
    # fixture, table, 标签列, 金额列, 比例列, 期末组名, 期初组名
    ("listed", T_LISTED[0], AGING_LABEL_COL, "金  额", "比例%", "期末数", "上年年末数"),
    ("soe", T_SOE[0], AGING_LABEL_COL, "金 额", "比例（%）", "期末数", "期初数"),
]


@pytest.mark.parametrize(
    ("fixture_name", "table_name", "label_col", "amount_label", "pct_label", "end_group", "prior_group"),
    AGING_HEADER_CASES,
)
def test_aging_two_level_header(
    fixture_name: str,
    table_name: str,
    label_col: str,
    amount_label: str,
    pct_label: str,
    end_group: str,
    prior_group: str,
    request: pytest.FixtureRequest,
) -> None:
    """按账龄表 = 5 列（账龄 + 期末{金额,比例} + 期初{金额,比例}）+ `_column_groups`。"""
    tbl = _get(request.getfixturevalue(fixture_name), table_name)
    assert tbl["headers"] == [label_col, amount_label, pct_label, amount_label, pct_label], _FIX_HINT
    assert tbl["_column_groups"] == [
        {"group": end_group, "start": 1, "span": 2},
        {"group": prior_group, "start": 3, "span": 2},
    ], _FIX_HINT
    assert [c["key"] for c in tbl["columns"]] == AGING_COLUMN_KEYS, _FIX_HINT
    assert [c.get("group") for c in tbl["columns"]] == [
        None, end_group, end_group, prior_group, prior_group,
    ], _FIX_HINT


@pytest.mark.parametrize(
    ("fixture_name", "table_name", "first_bucket"),
    [
        ("listed", T_LISTED[0], "1年以内"),
        ("soe", T_SOE[0], "1年以内（含1年）"),
    ],
)
def test_aging_rows_skeleton(
    fixture_name: str,
    table_name: str,
    first_bucket: str,
    request: pytest.FixtureRequest,
) -> None:
    """行骨架 = 源模版默认 3 年段四档 + 小计 + 减：减值准备 + 合计（F7-6 / F7-7）。

    5 年段 / 自定义段由底稿同步整表覆盖行，seed 只是初始骨架。
    """
    rows = _get(request.getfixturevalue(fixture_name), table_name)["rows"]
    labels = [str(r.get("label")) for r in rows]
    assert len(labels) == 7, f"{labels}；{_FIX_HINT}"
    assert labels[0] == first_bucket
    assert labels[1:4] == ["1至2年", "2至3年", "3年以上"]
    assert labels[4:] == AGING_TAIL_ROWS, _FIX_HINT


# ─── 单级表头表列结构（三源裁决结果） ────────────────────────────────────────

def test_listed_over1_columns(listed: dict[str, Any]) -> None:
    """上市 ② 表无「账龄」「未结算的原因」列（F7-9 / F7-10 listed 明确）。"""
    tbl = _get(listed, T_LISTED[1])
    assert tbl["headers"] == [
        "债务人名称", "账面余额", "占预付款项合计的比例（%）", "减值准备",
    ], _FIX_HINT
    assert [c["key"] for c in tbl["columns"]] == [
        "label", "balance", "proportion_pct", "impairment",
    ], _FIX_HINT


def test_listed_top5_columns(listed: dict[str, Any]) -> None:
    """上市 ③ 表 3 列，无「减值准备」列（F7-13 listed 明确跳过）。"""
    tbl = _get(listed, T_LISTED[2])
    assert len(tbl["headers"]) == 3, _FIX_HINT
    assert tbl["headers"][0] == "单位名称"
    assert not any("减值准备" in h for h in tbl["headers"]), _FIX_HINT


def test_soe_over1_columns(soe: dict[str, Any]) -> None:
    tbl = _get(soe, T_SOE[1])
    assert tbl["headers"] == [
        "债权单位", "债务单位", "期末余额", "账龄", "未结算的原因",
    ], _FIX_HINT
    assert tbl["columns"][0]["key"] == "creditor_unit"
    assert tbl["columns"][0].get("is_label") is True


def test_soe_top5_columns(soe: dict[str, Any]) -> None:
    """国企 ③ 表第 4 列为「减值准备」（附注模版 + F7-13 soe），非「坏账准备」。"""
    tbl = _get(soe, T_SOE[2])
    assert tbl["headers"] == [
        "债务人名称", "账面余额", "占预付款项合计的比例（%）", "减值准备",
    ], _FIX_HINT
    assert [c["key"] for c in tbl["columns"]] == [
        "label", "end_amount", "proportion_pct", "impairment",
    ], _FIX_HINT


# ─── 通用结构自洽 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("fixture_name", ["listed", "soe"])
def test_no_header_label_rows(fixture_name: str, request: pytest.FixtureRequest) -> None:
    """压扁的第二行表头会残留为 `header_label` 假数据行 → 必须删净。"""
    for tbl in request.getfixturevalue(fixture_name).get("tables") or []:
        for row in tbl.get("rows") or []:
            assert row.get("row_type") != "header_label", (
                f"{tbl.get('name')} 残留 header_label；{_FIX_HINT}"
            )


@pytest.mark.parametrize("fixture_name", ["listed", "soe"])
def test_headers_columns_consistent(fixture_name: str, request: pytest.FixtureRequest) -> None:
    for tbl in request.getfixturevalue(fixture_name).get("tables") or []:
        name = tbl.get("name")
        headers = tbl.get("headers") or []
        cols = tbl.get("columns") or []
        assert headers, f"{name} 缺 headers；{_FIX_HINT}"
        assert all(str(h).strip() for h in headers), f"{name} headers 含空串；{_FIX_HINT}"
        assert len(cols) == len(headers), (
            f"{name} columns={len(cols)} ≠ headers={len(headers)}；{_FIX_HINT}"
        )
        assert str(cols[0].get("label")) == str(headers[0]), (
            f"{name} columns[0].label ≠ headers[0]；{_FIX_HINT}"
        )
        assert sum(1 for c in cols if c.get("is_label")) == 1, (
            f"{name} 标签列须恰好 1 个；{_FIX_HINT}"
        )


@pytest.mark.parametrize("fixture_name", ["listed", "soe"])
def test_every_table_has_guidance(fixture_name: str, request: pytest.FixtureRequest) -> None:
    missing = [
        tbl.get("name")
        for tbl in request.getfixturevalue(fixture_name).get("tables") or []
        if not str(tbl.get("guidance") or "").strip()
    ]
    assert not missing, f"缺 guidance：{missing}；{_FIX_HINT}"


@pytest.mark.parametrize("fixture_name", ["listed", "soe"])
def test_column_groups_within_bounds(fixture_name: str, request: pytest.FixtureRequest) -> None:
    for tbl in request.getfixturevalue(fixture_name).get("tables") or []:
        headers = tbl.get("headers") or []
        occupied: set[int] = set()
        for g in tbl.get("_column_groups") or []:
            start, span = int(g["start"]), int(g["span"])
            assert start >= 1, f"{tbl.get('name')} 分组 start<1"
            assert start + span <= len(headers), f"{tbl.get('name')} 分组越界"
            rng = set(range(start, start + span))
            assert not (rng & occupied), f"{tbl.get('name')} 分组区间重叠"
            occupied |= rng


def test_listed_text_sections_keep_two_formats(listed: dict[str, Any]) -> None:
    """源模版两种披露格式说明与括注不得丢失。"""
    blob = "\n".join(listed.get("text_sections") or [])
    assert "汇总披露格式" in blob
    assert "分别披露格式" in blob
    assert "账龄超过1年的金额重要预付账款，应说明未及时结算的原因" in blob


def test_soe_text_sections_have_unsettled_reason_note(soe: dict[str, Any]) -> None:
    blob = "\n".join(soe.get("text_sections") or [])
    assert "未结算的原因" in blob


# ─── 与校验预设交叉印证 ──────────────────────────────────────────────────────

def test_check_presets_reference_impairment_row_not_column() -> None:
    """F7-7 依赖「减值准备**行**」（非逐段列），据此裁决附注按账龄表为 5 列。"""
    doc = json.loads(CHECK_PRESET_PATH.read_text(encoding="utf-8"))

    def _f7_7(variant: str) -> str:
        stack: list[Any] = [doc[variant]]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if node.get("id") == "F7-7":
                    return str(node.get("formula", ""))
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
        return ""

    for variant in ("listed", "soe"):
        formula = _f7_7(variant)
        assert "合计行" in formula and "小计行" in formula and "减值准备行" in formula, variant


def test_fix_script_check_mode_passes() -> None:
    """`--check` 通过 = 结构与脚本预期一致（供 CI 直接复用同一校验器）。"""
    import sys

    sys.path.insert(0, str(_BACKEND))
    from scripts.fix.fix_note_prepayment_structure import (  # noqa: PLC0415
        LISTED_SECTION as S_LISTED,
        SOE_SECTION as S_SOE,
        validate_section,
    )

    for path, section_number in ((LISTED_PATH, S_LISTED), (SOE_PATH, S_SOE)):
        sec = _load_section(path, section_number)
        errs = validate_section(sec, section_number)
        assert not errs, f"{path.name} §{section_number}: {errs}；{_FIX_HINT}"


# ─── 生成期 seed 元数据透传（新建项目 / 重新生成附注走这条路） ──────────────────

def _build_from_seed(section: dict[str, Any]) -> list[dict[str, Any]]:
    """模拟 `generate_notes` 的多表分支：只带 name/headers/rows，再由透传补元数据。"""
    import sys

    sys.path.insert(0, str(_BACKEND))
    from app.services.disclosure_engine import (  # noqa: PLC0415
        _carry_seed_column_meta,
        _carry_seed_table_guidance,
    )

    seed_tables = section.get("tables") or []
    built: list[dict[str, Any]] = []
    for tbl in seed_tables:
        item = {"name": tbl.get("name"), "headers": list(tbl.get("headers") or []), "rows": []}
        _carry_seed_column_meta(tbl, item)
        built.append(item)
    _carry_seed_table_guidance(seed_tables, built)
    return built


@pytest.mark.parametrize(
    ("fixture_name", "expected_names", "aging_groups"),
    [
        ("listed", T_LISTED, ["期末数", "上年年末数"]),
        ("soe", T_SOE, ["期末数", "期初数"]),
    ],
)
def test_generation_path_carries_groups_and_guidance(
    fixture_name: str,
    expected_names: tuple[str, ...],
    aging_groups: list[str],
    request: pytest.FixtureRequest,
) -> None:
    """新建项目生成的 `table_data._tables` 必须有 3 张唯一表 + 两级表头 + guidance。

    存量项目的 `_tables` 是**生成时快照**，不受模板修订影响（见 spec Notes）。
    """
    built = _build_from_seed(request.getfixturevalue(fixture_name))

    names = [t["name"] for t in built]
    assert names == list(expected_names)
    assert len(set(names)) == 3, f"生成的 TAB 重名：{names}"

    aging = built[0]
    assert [g["group"] for g in aging["_column_groups"]] == aging_groups
    assert len(aging["columns"]) == 5

    for t in built:
        assert str(t.get("guidance") or "").strip(), f"{t['name']} 生成后缺 guidance"

    # 单级表头表：`flat` 标在标签列 → 后端不做前缀反猜
    for t in built[1:]:
        assert not t.get("_column_groups"), f"{t['name']} 不应有父表头"
        assert t["columns"][0].get("flat") is True, f"{t['name']} 标签列缺 flat"


# ─── 三向比对：源 xlsx ↔ note_template ↔ 同步载荷常量 ────────────────────────
#
# 前面的断言只锁「模板 ↔ 常量」两侧，源 xlsx 是盲区 —— 而列头字面（尤其**空格**）
# 的唯一裁决者是源 xlsx（`基础数据/附注模版/*.md` 在本仓库不存在）。
# 本节用 openpyxl **直读**源 xlsx 单元格，把三侧钉在一起。
#
# spec: .kiro/specs/f1-four-table-extraction-and-disclosure-alignment/ R6 / R11.3


def _source_cells(variant: str) -> dict[str, str]:
    """直读源 xlsx 披露 sheet 的关键单元格（原样返回，**不 strip**）。"""
    openpyxl = pytest.importorskip("openpyxl")
    assert SOURCE_XLSX.exists(), f"源模板缺失：{SOURCE_XLSX}"
    wb = openpyxl.load_workbook(SOURCE_XLSX, data_only=True, read_only=True)
    try:
        sheet = SOURCE_SHEETS[variant]
        assert sheet in wb.sheetnames, f"源模板缺 sheet「{sheet}」（现有 {wb.sheetnames}）"
        ws = wb[sheet]
        # 只读模式不支持随机访问 → 逐行取前 12 行前 8 列
        grid: dict[str, str] = {}
        for row in ws.iter_rows(min_row=1, max_row=12, max_col=8):
            for cell in row:
                if cell.value is not None:
                    grid[cell.coordinate] = str(cell.value)
        return grid
    finally:
        wb.close()


def test_source_xlsx_sheet_names_are_half_width() -> None:
    """F1 两个披露 sheet 名是**半角**括号（与 `F1_DISCLOSURE_SHEET_NAME` 常量同源）。

    平台存在 8 种括号写法，写死字面量必再分叉 → 此处直读 xlsx 钉住。
    """
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.load_workbook(SOURCE_XLSX, read_only=True)
    try:
        for sheet in SOURCE_SHEETS.values():
            assert sheet in wb.sheetnames, f"源模板缺 sheet「{sheet}」"
    finally:
        wb.close()


@pytest.mark.parametrize(
    ("variant", "cell", "expected"),
    [
        # 标签列（两版同为双空格）
        ("listed", "A8", "账  龄"),
        ("soe", "A8", "账  龄"),
        # 两级表头父组名
        ("listed", "B8", "期末数"),
        ("listed", "D8", "上年年末数"),
        ("soe", "B8", "期末数"),
        ("soe", "E8", "期初数"),
        # 金额列（上市双空格 / 国企单空格）
        ("listed", "B9", "金  额"),
        ("soe", "B10", "金 额"),
        # 比例列
        ("listed", "C9", "比例%"),
        ("soe", "C10", "比例（%）"),
    ],
)
def test_source_xlsx_literals(variant: str, cell: str, expected: str) -> None:
    """源 xlsx 单元格字面（含空格）—— 本 spec 全部列头字面的第一源。"""
    grid = _source_cells(variant)
    assert grid.get(cell) == expected, (
        f"{SOURCE_SHEETS[variant]}!{cell} 实为 {grid.get(cell)!r}，期望 {expected!r}"
    )


def test_source_xlsx_amount_labels_differ_between_variants() -> None:
    """反向自检：两版金额列空格数**确实不同** —— 若被 trim 成同值，本 spec 的
    「逐字保留」就失去意义（也说明比对没生效）。"""
    assert _source_cells("listed").get("B9") != _source_cells("soe").get("B10")


@pytest.mark.parametrize(
    ("fixture_name", "table_name", "label_col", "amount_label", "pct_label", "end_group", "prior_group"),
    AGING_HEADER_CASES,
)
def test_three_way_aging_header_alignment(
    fixture_name: str,
    table_name: str,
    label_col: str,
    amount_label: str,
    pct_label: str,
    end_group: str,
    prior_group: str,
    request: pytest.FixtureRequest,
) -> None:
    """三向一致：源 xlsx 字面 == 模板 headers/columns == 同步载荷常量。"""
    variant = fixture_name
    grid = _source_cells(variant)

    # ① 源 xlsx
    assert grid.get("A8") == label_col
    assert grid.get("B8") == end_group
    assert grid.get("D8" if variant == "listed" else "E8") == prior_group
    assert grid.get("B9" if variant == "listed" else "B10") == amount_label
    assert grid.get("C9" if variant == "listed" else "C10") == pct_label

    # ② note_template
    tbl = _get(request.getfixturevalue(fixture_name), table_name)
    assert tbl["headers"] == [label_col, amount_label, pct_label, amount_label, pct_label]
    assert [c.get("group") for c in tbl["columns"]] == [
        None, end_group, end_group, prior_group, prior_group,
    ]

    # ③ 同步载荷常量（读 .ts 源码，避免前后端各写一份字面）
    assert SYNC_PAYLOAD_TS.exists(), f"缺同步载荷文件：{SYNC_PAYLOAD_TS}"
    ts = SYNC_PAYLOAD_TS.read_text(encoding="utf-8")
    assert f"F1_AGING_LABEL_COL = '{label_col}'" in ts, "标签列常量与源 xlsx 不一致"
    const_name = "F1_LISTED_AMOUNT_LABEL" if variant == "listed" else "F1_SOE_AMOUNT_LABEL"
    assert f"{const_name} = '{amount_label}'" in ts, f"{const_name} 与源 xlsx 不一致"
    groups_const = "F1_LISTED_AGING_GROUPS" if variant == "listed" else "F1_SOE_AGING_GROUPS"
    assert (
        f"{groups_const} = {{ end: '{end_group}', prior: '{prior_group}' }}" in ts
    ), f"{groups_const} 与源 xlsx 不一致"


def test_three_way_reverse_self_check() -> None:
    """反向自检：把期望值改成错的，比对必须失败（证明断言不是空转）。"""
    grid = _source_cells("listed")
    assert grid.get("A8") != "账龄", "源 xlsx 标签列若真是无空格『账龄』，本 spec 的前提就错了"
    ts = SYNC_PAYLOAD_TS.read_text(encoding="utf-8")
    assert "F1_LISTED_AGING_GROUPS = { end: '期末余额'" not in ts, "旧组名残留"


def test_prefill_preset_check_script_passes() -> None:
    """F1 公式预设校验脚本零欠账（与结构脚本同为 CI 卡点）。"""
    import subprocess  # noqa: PLC0415
    import sys  # noqa: PLC0415

    script = _BACKEND / "scripts" / "fix" / "fix_f1_prefill_presets.py"
    assert script.exists(), f"缺脚本 {script}"
    proc = subprocess.run(
        [sys.executable, str(script), "--check"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, f"F1 公式预设校验失败：\n{proc.stdout}\n{proc.stderr}"
