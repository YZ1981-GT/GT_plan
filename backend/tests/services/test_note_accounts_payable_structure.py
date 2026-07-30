"""附注模板应付账款章节结构契约（对齐源模版）。

- 上市版 §五、37 应付账款（`基础数据/附注模版/上市报表附注.md`）
- 国企版 §八、37 应付账款（`基础数据/附注模版/国企报表附注.md`）
- 上市按性质分类行口径交叉印证：`F4 应付账款.xlsx` → `审定表F4-1` 一、按照性质分类

卡点目的：`scripts/fix/rebuild_note_from_md.py` 从 md 重建模板时会把 md 表格的
**首个表头单元格**当成表名（上市第二张表曾被命名为「项  目」），并把 md 的编制提示
占位行（「可无限量添加行」）留成假数据行。本文件在 CI 阶段拦住这种回退，提示重跑
`backend/scripts/fix/fix_note_accounts_payable_structure.py`。

⚠️ 国企账龄行**不带**底稿 xlsx 的「（含2年）/（含3年）」——附注模版 md 原文如此；
   国企第二张表名「账龄超过1 年的重要应付账款」中「1」后的空格亦为 md 原文，
   两者都不得"顺手修正"，否则破坏前端 `F4_SOE_SUBTABLE` 子表名契约。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
LISTED_PATH = _BACKEND / "data" / "note_template_listed.json"
SOE_PATH = _BACKEND / "data" / "note_template_soe.json"
LISTED_SECTION = "五、37"
SOE_SECTION = "八、37"
ALIGNED_BY = "f4-accounts-payable-disclosure-template-alignment"
_FIX_HINT = "请重跑 python backend/scripts/fix/fix_note_accounts_payable_structure.py"

if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

LISTED_NATURE_TABLE = "应付账款"
LISTED_OVER1Y_TABLE = "其中，账龄超过1年的重要应付账款"
SOE_AGING_TABLE = "应付账款"
SOE_OVER1Y_TABLE = "账龄超过1 年的重要应付账款"

# 与前端 f4NoteSectionMap.ts 的 ColumnDef 常量逐字一致（f4NoteSubtableContract.spec.ts 双向卡）
EXPECTED_COLUMNS: dict[tuple[str, str], list[dict[str, Any]]] = {
    ("listed", LISTED_NATURE_TABLE): [
        {"key": "label", "label": "项目", "is_label": True, "flat": True},
        {"key": "end_amount", "label": "期末余额", "format": "amount"},
        {"key": "prior_amount", "label": "上年年末余额", "format": "amount"},
    ],
    ("listed", LISTED_OVER1Y_TABLE): [
        {"key": "label", "label": "项目", "is_label": True, "flat": True},
        {"key": "end_amount", "label": "期末余额", "format": "amount"},
        {"key": "unsettled_reason", "label": "未偿还或未结转的原因"},
    ],
    ("soe", SOE_AGING_TABLE): [
        {"key": "label", "label": "账龄", "is_label": True, "flat": True},
        {"key": "end_amount", "label": "期末余额", "format": "amount"},
        {"key": "opening_amount", "label": "期初余额", "format": "amount"},
    ],
    ("soe", SOE_OVER1Y_TABLE): [
        {"key": "label", "label": "债权单位名称", "is_label": True, "flat": True},
        {"key": "end_amount", "label": "期末余额", "format": "amount"},
        {"key": "unsettled_reason", "label": "未偿还原因"},
    ],
}


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


def _by_name(section: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(t.get("name")): t for t in section.get("tables") or []}


def _get(section: dict[str, Any], name: str) -> dict[str, Any]:
    tbl = _by_name(section).get(name)
    assert tbl is not None, (
        f"缺表「{name}」；现有 {list(_by_name(section))}；{_FIX_HINT}"
    )
    return tbl


def _labels(tbl: dict[str, Any]) -> list[str]:
    return [str(r.get("label", "")) for r in tbl.get("rows") or []]


# ─────────────── 表名：md 重建误名已修正 ───────────────

def test_listed_tables_are_exactly_two(listed: dict[str, Any]) -> None:
    assert list(_by_name(listed)) == [LISTED_NATURE_TABLE, LISTED_OVER1Y_TABLE], _FIX_HINT


def test_soe_tables_are_exactly_two(soe: dict[str, Any]) -> None:
    assert list(_by_name(soe)) == [SOE_AGING_TABLE, SOE_OVER1Y_TABLE], _FIX_HINT


def test_listed_header_cell_not_used_as_table_name(listed: dict[str, Any]) -> None:
    """「项  目」是 md 表格首个表头单元格，不是表名。"""
    assert "项  目" not in _by_name(listed), _FIX_HINT


def test_soe_over1y_table_name_keeps_md_whitespace(soe: dict[str, Any]) -> None:
    """附注模版 md 原文为「账龄超过1 年」（1 后有空格），前端子表名契约据此逐字对齐。"""
    assert SOE_OVER1Y_TABLE in _by_name(soe), _FIX_HINT


# ─────────────── 行集合 ───────────────

def test_listed_nature_rows_match_adjudication_categories(listed: dict[str, Any]) -> None:
    """上市按性质 5 类取自 F4-1 审定表；md 占位行「可无限量添加行」必须删除。"""
    labels = _labels(_get(listed, LISTED_NATURE_TABLE))
    assert labels == ["货款", "工程款", "设备款", "服务费", "其他", "合计"], _FIX_HINT
    assert "可无限量添加行" not in labels


def test_soe_aging_rows_match_note_template_md(soe: dict[str, Any]) -> None:
    """国企账龄行逐字对齐附注模版 md（不带「（含2年）/（含3年）」）。"""
    assert _labels(_get(soe, SOE_AGING_TABLE)) == [
        "1年以内（含1年）", "1至2年", "2至3年", "3年以上", "合计",
    ], _FIX_HINT


def test_over1y_tables_are_itemized_skeletons(
    listed: dict[str, Any], soe: dict[str, Any]
) -> None:
    """账龄超 1 年逐项披露：空白骨架行 + 合计（同步时整表覆盖）。"""
    for section, name in ((listed, LISTED_OVER1Y_TABLE), (soe, SOE_OVER1Y_TABLE)):
        rows = _get(section, name).get("rows") or []
        assert rows, _FIX_HINT
        assert rows[-1].get("is_total") is True
        assert all(str(r.get("label", "")) == "" for r in rows[:-1]), _FIX_HINT


# ─────────────── 列结构 ───────────────

@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_headers_have_no_blank(variant: str, listed: dict[str, Any], soe: dict[str, Any]) -> None:
    section = listed if variant == "listed" else soe
    for tbl in section.get("tables") or []:
        headers = tbl.get("headers") or []
        assert headers, f"{tbl.get('name')} 缺 headers；{_FIX_HINT}"
        assert all(str(h).strip() for h in headers), f"{tbl.get('name')} headers 含空串"


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_columns_align_with_headers(
    variant: str, listed: dict[str, Any], soe: dict[str, Any]
) -> None:
    """columns 数量 == headers；恰 1 个 is_label 列且其 label == headers[0]。"""
    section = listed if variant == "listed" else soe
    for tbl in section.get("tables") or []:
        name = str(tbl.get("name"))
        headers = tbl.get("headers") or []
        cols = tbl.get("columns") or []
        assert len(cols) == len(headers), f"{name} columns/headers 不等长；{_FIX_HINT}"
        label_cols = [c for c in cols if c.get("is_label")]
        assert len(label_cols) == 1, f"{name} is_label 列数 {len(label_cols)}；{_FIX_HINT}"
        assert str(label_cols[0].get("label")) == str(headers[0]), (
            f"{name} 标签列 label 与 headers[0] 不一致 → 同步出孤儿列；{_FIX_HINT}"
        )
        assert any(c.get("flat") for c in cols), (
            f"{name} 缺 flat 声明（3 列单级表头须抑制后端前缀推断）；{_FIX_HINT}"
        )


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_columns_match_frontend_constants(
    variant: str, listed: dict[str, Any], soe: dict[str, Any]
) -> None:
    section = listed if variant == "listed" else soe
    for (v, name), expected in EXPECTED_COLUMNS.items():
        if v != variant:
            continue
        assert _get(section, name).get("columns") == expected, (
            f"{name} columns 与前端 f4NoteSectionMap.ts 常量漂移；{_FIX_HINT}"
        )


# ─────────────── guidance / text_sections ───────────────

@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_every_table_has_guidance(
    variant: str, listed: dict[str, Any], soe: dict[str, Any]
) -> None:
    section = listed if variant == "listed" else soe
    missing = [
        str(t.get("name")) for t in section.get("tables") or []
        if not str(t.get("guidance", "")).strip()
    ]
    assert not missing, f"缺 TAB 页签编制提示：{missing}；{_FIX_HINT}"


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_text_sections_have_no_table_titles(
    variant: str, listed: dict[str, Any], soe: dict[str, Any]
) -> None:
    """纯表标题行语义由 tables[].name 承载，留在 text_sections 会污染正文/提示分流。"""
    section = listed if variant == "listed" else soe
    names = {str(t.get("name", "")).strip() for t in section.get("tables") or []}
    for text in section.get("text_sections") or []:
        stripped = str(text).lstrip("#").strip()
        assert stripped not in names, f"text_sections 混入表标题：{text!r}；{_FIX_HINT}"


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_text_sections_carry_source_hints(
    variant: str, listed: dict[str, Any], soe: dict[str, Any]
) -> None:
    """两段【提示】分别来自 F4-2 提示区红字与解释第17号供应商融资安排披露。"""
    section = listed if variant == "listed" else soe
    joined = "\n".join(section.get("text_sections") or [])
    assert "账龄超过1年的大额应付账款" in joined, _FIX_HINT
    assert "解释第17号" in joined, _FIX_HINT


# ─────────────── 对齐标记 / 脚本幂等 ───────────────

@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_aligned_marker(variant: str, listed: dict[str, Any], soe: dict[str, Any]) -> None:
    section = listed if variant == "listed" else soe
    assert section.get("_aligned_by") == ALIGNED_BY, _FIX_HINT


def test_fix_script_check_passes() -> None:
    """脚本 --check 口径与本文件断言同源：结构自洽 + 对齐标记齐备。"""
    from scripts.fix.fix_note_accounts_payable_structure import (  # noqa: PLC0415
        LISTED_MAIN_TABLE,
        LISTED_OVER1Y_TABLE as _L_OVER1Y,
        SOE_MAIN_TABLE,
        SOE_OVER1Y_TABLE as _S_OVER1Y,
        validate_section,
    )

    assert validate_section(
        _load_section(LISTED_PATH, LISTED_SECTION), [LISTED_MAIN_TABLE, _L_OVER1Y]
    ) == []
    assert validate_section(
        _load_section(SOE_PATH, SOE_SECTION), [SOE_MAIN_TABLE, _S_OVER1Y]
    ) == []


def test_fix_script_is_idempotent() -> None:
    """二次应用无变更（Property：幂等）。"""
    from scripts.fix.fix_note_accounts_payable_structure import (  # noqa: PLC0415
        _listed_plan,
        _soe_plan,
        LISTED_TEXT_ADDITIONS,
        LISTED_TEXT_REMOVE,
        SOE_TEXT_ADDITIONS,
        SOE_TEXT_REMOVE,
        apply_plan,
        revise_text_sections,
    )

    for path, number, plan, remove, additions in (
        (LISTED_PATH, LISTED_SECTION, _listed_plan(), LISTED_TEXT_REMOVE, LISTED_TEXT_ADDITIONS),
        (SOE_PATH, SOE_SECTION, _soe_plan(), SOE_TEXT_REMOVE, SOE_TEXT_ADDITIONS),
    ):
        section = _load_section(path, number)
        changes, warnings = apply_plan(section, plan)
        changes += revise_text_sections(section, remove, additions)
        assert changes == [], f"{path.name} §{number} 非幂等：{changes}"
        assert warnings == [], f"{path.name} §{number} 计划匹配告警：{warnings}"


# ─────────────── 底稿同步载荷 → 附注投影（端到端结构闭环） ───────────────
#
# 覆盖真实风险：子表名/列头一旦与附注模板漂移，`project_sub_tables` 会产出孤儿子表
# （附注 TAB 永空）或退化成「只有行名、无数据列」的降级表。
# 载荷形态与前端 `f4NoteSectionMap.buildF4{Listed,Soe}SyncPayload` 逐字对应。

_LISTED_PAYLOAD_COLUMNS = EXPECTED_COLUMNS[("listed", LISTED_NATURE_TABLE)]
_LISTED_OVER1Y_PAYLOAD_COLUMNS = EXPECTED_COLUMNS[("listed", LISTED_OVER1Y_TABLE)]
_SOE_PAYLOAD_COLUMNS = EXPECTED_COLUMNS[("soe", SOE_AGING_TABLE)]
_SOE_OVER1Y_PAYLOAD_COLUMNS = EXPECTED_COLUMNS[("soe", SOE_OVER1Y_TABLE)]


def _project(sub_table_data: dict[str, Any], cols: dict[str, Any]) -> list[dict[str, Any]]:
    from app.services.note_sub_table_projector import project_sub_tables  # noqa: PLC0415

    projected = project_sub_tables({
        "_source": "workpaper",
        "sub_table_data": sub_table_data,
        "_sub_table_columns": cols,
    })
    assert projected is not None
    return projected


def test_listed_payload_projects_to_template_tables(listed: dict[str, Any]) -> None:
    tables = _project(
        {
            LISTED_NATURE_TABLE: [
                {"label": "货款", "end_amount": 1000, "prior_amount": 800},
                {"label": "工程款", "end_amount": 500, "prior_amount": 400},
                {"label": "合计", "end_amount": 1500, "prior_amount": 1200, "is_total": True},
            ],
            LISTED_OVER1Y_TABLE: [
                {"label": "A供应商", "end_amount": 300, "unsettled_reason": "对账差异未结"},
                {"label": "合计", "end_amount": 300, "unsettled_reason": "", "is_total": True},
            ],
        },
        {
            LISTED_NATURE_TABLE: _LISTED_PAYLOAD_COLUMNS,
            LISTED_OVER1Y_TABLE: _LISTED_OVER1Y_PAYLOAD_COLUMNS,
        },
    )
    by_name = {t["name"]: t for t in tables}
    # 无孤儿子表：投影表名 == 附注模板表名
    assert set(by_name) == {LISTED_NATURE_TABLE, LISTED_OVER1Y_TABLE}, _FIX_HINT

    nature = by_name[LISTED_NATURE_TABLE]
    assert nature["headers"] == _get(listed, LISTED_NATURE_TABLE)["headers"], _FIX_HINT
    assert [r["label"] for r in nature["rows"]] == ["货款", "工程款", "合计"]
    assert nature["rows"][0]["values"] == [1000, 800]
    assert nature["rows"][-1]["is_total"] is True
    # 3 列单级表头：不得凭空推断出父表头
    assert not nature.get("_column_groups")

    over1y = by_name[LISTED_OVER1Y_TABLE]
    assert over1y["headers"] == _get(listed, LISTED_OVER1Y_TABLE)["headers"], _FIX_HINT
    assert over1y["rows"][0]["values"] == [300, "对账差异未结"]


def test_soe_payload_projects_to_template_tables(soe: dict[str, Any]) -> None:
    aging_rows = [
        {"label": "1年以内（含1年）", "end_amount": 900, "opening_amount": 700},
        {"label": "1至2年", "end_amount": 300, "opening_amount": 200},
        {"label": "2至3年", "end_amount": 100, "opening_amount": 80},
        {"label": "3年以上", "end_amount": 50, "opening_amount": 40},
        {"label": "合计", "end_amount": 1350, "opening_amount": 1020, "is_total": True},
    ]
    tables = _project(
        {
            SOE_AGING_TABLE: aging_rows,
            SOE_OVER1Y_TABLE: [
                {"label": "甲公司", "end_amount": 120, "unsettled_reason": "工程未结算"},
                {"label": "合计", "end_amount": 120, "unsettled_reason": "", "is_total": True},
            ],
        },
        {
            SOE_AGING_TABLE: _SOE_PAYLOAD_COLUMNS,
            SOE_OVER1Y_TABLE: _SOE_OVER1Y_PAYLOAD_COLUMNS,
        },
    )
    by_name = {t["name"]: t for t in tables}
    assert set(by_name) == {SOE_AGING_TABLE, SOE_OVER1Y_TABLE}, _FIX_HINT

    aging = by_name[SOE_AGING_TABLE]
    assert aging["headers"] == _get(soe, SOE_AGING_TABLE)["headers"], _FIX_HINT
    # 附注行名与模板 seed 行名逐字一致（3 年段口径，不带「（含2年）」）
    assert [r["label"] for r in aging["rows"]] == _labels(_get(soe, SOE_AGING_TABLE))
    assert aging["rows"][1]["values"] == [300, 200]
    assert not aging.get("_column_groups")

    over1y = by_name[SOE_OVER1Y_TABLE]
    assert over1y["headers"] == _get(soe, SOE_OVER1Y_TABLE)["headers"], _FIX_HINT
    assert over1y["rows"][0]["values"] == [120, "工程未结算"]


def test_soe_five_year_segments_project_six_aging_rows() -> None:
    """5 年段账龄配置下推送 6 档行名（附注 seed 仍是 3 年段 4 档，同步整表覆盖）。"""
    rows = [
        {"label": lbl, "end_amount": 10, "opening_amount": 5}
        for lbl in ["1年以内（含1年）", "1至2年", "2至3年", "3至4年", "4至5年", "5年以上"]
    ] + [{"label": "合计", "end_amount": 60, "opening_amount": 30, "is_total": True}]
    tables = _project({SOE_AGING_TABLE: rows}, {SOE_AGING_TABLE: _SOE_PAYLOAD_COLUMNS})
    aging = tables[0]
    assert [r["label"] for r in aging["rows"]] == [
        "1年以内（含1年）", "1至2年", "2至3年", "3至4年", "4至5年", "5年以上", "合计",
    ]
    assert aging["headers"] == ["账龄", "期末余额", "期初余额"]


def test_note_texts_and_removed_keys_are_not_projected_as_tables() -> None:
    """`_note_texts` / `_removed_table_keys` 是元数据键，不得投影成表。"""
    tables = _project(
        {
            SOE_AGING_TABLE: [{"label": "1至2年", "end_amount": 1, "opening_amount": 1}],
            "_note_texts": [{"text": "披露正文"}],
            "_removed_table_keys": ["项  目"],
        },
        {SOE_AGING_TABLE: _SOE_PAYLOAD_COLUMNS},
    )
    assert [t["name"] for t in tables] == [SOE_AGING_TABLE]


def test_missing_columns_degrades_to_label_only_table() -> None:
    """反向守卫：列头缺失 → 降级为「只有行名」表（证明 columns 契约不可省）。"""
    tables = _project(
        {SOE_AGING_TABLE: [{"label": "1至2年", "end_amount": 300, "opening_amount": 200}]},
        {},
    )
    assert tables[0]["headers"] == ["项目"]
    assert tables[0]["rows"][0]["values"] == []
