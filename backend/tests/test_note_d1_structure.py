"""附注「应收票据」章节（上市 五、4 / 国企 八、4）结构守卫。

锁死 `fix_note_d1_notes_receivable_structure.py` 的修订结果，防止：

- md 重建脚本（`rebuild_note_from_md.py`）把两级表头压扁、把占位说明落成假数据行
- 并发会话回退 `note_template_*.json`（幂等脚本 + 契约测试是唯一可靠恢复手段）
- 新增列时漏 `group`/`flat` 表态 → seed 路径被 `_infer_groups_from_headers` 塞凭空父表头

spec: .kiro/specs/d1-notes-receivable-disclosure-alignment/ Task 2.1
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
DATA_DIR = _BACKEND / "data"
FIX_SCRIPT = _BACKEND / "scripts" / "fix" / "fix_note_d1_notes_receivable_structure.py"


def _load_fix_module():
    spec = importlib.util.spec_from_file_location("_fix_d1_structure", FIX_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FIX = _load_fix_module()

VARIANTS = ["listed", "soe"]
SECTION = {"listed": "五、4", "soe": "八、4"}
TABLE_COUNT = {"listed": 14, "soe": 12}
TEMPLATE = {
    "listed": DATA_DIR / "note_template_listed.json",
    "soe": DATA_DIR / "note_template_soe.json",
}


def _section(variant: str) -> dict:
    doc = json.loads(TEMPLATE[variant].read_text(encoding="utf-8"))
    for sec in doc.get("sections", []):
        if str(sec.get("section_number", "")) == SECTION[variant]:
            return sec
    pytest.fail(f"{TEMPLATE[variant].name} 缺章节 {SECTION[variant]}")


def _tables(variant: str) -> list[dict]:
    return _section(variant).get("tables") or []


# ─── 章节级 ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("variant", VARIANTS)
def test_section_exists_and_titled(variant: str) -> None:
    sec = _section(variant)
    assert sec.get("section_title") == "应收票据"
    assert sec.get("account_name") == "应收票据"


@pytest.mark.parametrize("variant", VARIANTS)
def test_table_count_matches_source_template(variant: str) -> None:
    """表数固定：源模板小节切分 + 双期拆表后 上市 14 张 / 国企 12 张。"""
    assert len(_tables(variant)) == TABLE_COUNT[variant]


@pytest.mark.parametrize("variant", VARIANTS)
def test_aligned_stamp_present(variant: str) -> None:
    assert _section(variant).get("_aligned_by") == FIX.ALIGNED_BY


@pytest.mark.parametrize("variant", VARIANTS)
def test_expected_table_names_complete_and_unique(variant: str) -> None:
    expected = FIX.SECTION_PLANS[variant]["expected"]
    names = [str(t.get("name", "")) for t in _tables(variant)]
    assert len(names) == len(set(names)), f"表名重复：{names}"
    assert sorted(names) == sorted(expected)


@pytest.mark.parametrize("variant", VARIANTS)
def test_validate_section_reports_no_debt(variant: str) -> None:
    """复用修订脚本的校验器（--check 的同一实现）。"""
    errs = FIX.validate_section(_section(variant), FIX.SECTION_PLANS[variant]["expected"])
    assert errs == []


# ─── 表级 ─────────────────────────────────────────────────────────────────────

def _all_tables() -> list[tuple[str, str, dict]]:
    return [(v, str(t.get("name", "")), t) for v in VARIANTS for t in _tables(v)]


ALL_TABLES = _all_tables()
TABLE_IDS = [f"{v}:{n}" for v, n, _ in ALL_TABLES]


@pytest.mark.parametrize(("variant", "name", "tbl"), ALL_TABLES, ids=TABLE_IDS)
def test_columns_declared_and_consistent(variant: str, name: str, tbl: dict) -> None:
    cols = tbl.get("columns") or []
    headers = tbl.get("headers") or []
    assert cols, f"{name} 缺 columns（seed 路径会前缀推断出凭空父表头）"
    assert len(cols) == len(headers), f"{name} columns={len(cols)} ≠ headers={len(headers)}"
    assert [str(c.get("label", "")) for c in cols] == [str(h) for h in headers]
    assert cols[0].get("is_label") is True, f"{name} 首列未标 is_label"
    assert not cols[0].get("group"), f"{name} 标签列不得带 group"

    has_flat = any(c.get("flat") for c in cols)
    has_group = any(c.get("group") for c in cols)
    assert has_flat != has_group, f"{name} 必须在 flat 与 group 之间恰好表态其一"


@pytest.mark.parametrize(("variant", "name", "tbl"), ALL_TABLES, ids=TABLE_IDS)
def test_group_is_single_level(variant: str, name: str, tbl: dict) -> None:
    """🔴 group 含 '/' 会让后端走树形分支，而前端 activeTableColumns 只认扁平格式 → 渲染崩。"""
    for c in tbl.get("columns") or []:
        assert "/" not in str(c.get("group") or ""), f"{name}.{c.get('key')} group 含 '/'"


@pytest.mark.parametrize(("variant", "name", "tbl"), ALL_TABLES, ids=TABLE_IDS)
def test_column_groups_derived_from_columns(variant: str, name: str, tbl: dict) -> None:
    cols = tbl.get("columns") or []
    want = FIX._derive_column_groups(cols)
    got = tbl.get("_column_groups")
    if want:
        assert got == want, f"{name} _column_groups 与 columns.group 不一致"
        for g in got:
            assert g["start"] >= 1
            assert g["start"] + g["span"] <= len(tbl.get("headers") or [])
    else:
        assert got is None, f"{name} 单级表头仍残留 _column_groups"


@pytest.mark.parametrize(("variant", "name", "tbl"), ALL_TABLES, ids=TABLE_IDS)
def test_headers_clean(variant: str, name: str, tbl: dict) -> None:
    for h in tbl.get("headers") or []:
        assert str(h).strip(), f"{name} headers 含空串"
        assert "<" not in str(h), f"{name} headers 含 HTML（md 表格搬来的 <br/>）"


@pytest.mark.parametrize(("variant", "name", "tbl"), ALL_TABLES, ids=TABLE_IDS)
def test_guidance_present(variant: str, name: str, tbl: dict) -> None:
    g = str(tbl.get("guidance") or "")
    assert len(g.strip()) >= 20, f"{name} guidance 过短或缺失（附注 TAB 无编制提示）"


@pytest.mark.parametrize(("variant", "name", "tbl"), ALL_TABLES, ids=TABLE_IDS)
def test_no_placeholder_or_header_label_rows(variant: str, name: str, tbl: dict) -> None:
    """占位说明与压扁的第二行表头都不得留在 rows 里（会渲染成一行空披露数据）。"""
    bad_labels = {"可无限量添加行", "出票人类型或账龄", "……", "..."}
    for i, row in enumerate(tbl.get("rows") or []):
        assert str(row.get("row_type", "")) != "header_label", f"{name} 第 {i} 行是压扁的表头"
        label = str(row.get("label", "")).strip()
        assert label not in bad_labels, f"{name} 第 {i} 行是占位说明「{label}」"


# ─── 关键表的行 / 列结构（防悄悄改回） ────────────────────────────────────────

def _table(variant: str, name: str) -> dict:
    for t in _tables(variant):
        if str(t.get("name", "")) == name:
            return t
    pytest.fail(f"{variant} 缺表「{name}」")


@pytest.mark.parametrize(
    ("variant", "name", "want_groups"),
    [
        ("listed", "应收票据", ["期末余额", "上年年末余额"]),
        ("soe", "应收票据分类", ["期末数", "期初数"]),
        ("listed", "按坏账计提方法分类（期末余额）", ["期末余额"]),
        ("listed", "按坏账计提方法分类（续：上年年末余额）", ["上年年末余额"]),
        ("soe", "按坏账准备计提方法分类披露应收票据（期末数）", ["账面余额", "坏账准备"]),
        ("soe", "按坏账准备计提方法分类披露应收票据（续：期初数）", ["账面余额", "坏账准备"]),
        ("listed", "组合计提项目：银行承兑汇票", ["期末余额", "上年年末余额"]),
        ("listed", "组合计提项目：商业承兑汇票", ["期末余额", "上年年末余额"]),
        ("soe", "本期计提、收回或转回的应收票据坏账准备情况", ["本期变动情况"]),
    ],
)
def test_two_level_header_groups(variant: str, name: str, want_groups: list[str]) -> None:
    """两级表头的表：父表头名逐字取自源模板合并单元格。"""
    tbl = _table(variant, name)
    got = [g["group"] for g in tbl.get("_column_groups") or []]
    assert got == want_groups


@pytest.mark.parametrize(
    ("variant", "name"),
    [
        ("listed", "期末因出票人未履约而将其转应收账款的票据"),
        ("soe", "期末因出票人未履约而其转为应收账款的票据"),
    ],
)
def test_transfer_table_lists_commercial_only(variant: str, name: str) -> None:
    """票据逾期应转入应收账款、账龄连续计算 → 出票人未履约只对商业承兑成立。"""
    rows = _table(variant, name).get("rows") or []
    labels = [str(r.get("label", "")) for r in rows]
    assert labels == ["商业承兑票据", "合计"]


@pytest.mark.parametrize(
    ("variant", "name"),
    [
        ("listed", "期末已质押的应收票据"),
        ("listed", "期末已背书或贴现但尚未到期的应收票据"),
        ("soe", "期末已质押的应收票据"),
        ("soe", "期末已背书或贴现但尚未到期的应收票据"),
    ],
)
def test_bill_kind_wording_per_table(variant: str, name: str) -> None:
    """质押 / 背书贴现表源模板用「票据」（分类总表才用「汇票」）——逐表措辞。"""
    labels = [str(r.get("label", "")) for r in (_table(variant, name).get("rows") or [])]
    assert labels == ["银行承兑票据", "商业承兑票据", "合计"]


@pytest.mark.parametrize("variant", VARIANTS)
def test_main_table_kind_wording(variant: str) -> None:
    name = "应收票据" if variant == "listed" else "应收票据分类"
    labels = [str(r.get("label", "")) for r in (_table(variant, name).get("rows") or [])]
    assert labels == ["银行承兑汇票", "商业承兑汇票", "合计"]


def test_soe_portfolio_subtotal_labels() -> None:
    """国企组合计提表小计行名带「小计：」（源模板 A36/A39）。"""
    labels = [
        str(r.get("label", ""))
        for r in (_table("soe", "按组合计提坏账准备的应收票据").get("rows") or [])
    ]
    assert labels[0] == "商业承兑汇票小计："
    assert "银行承兑汇票小计：" in labels
    assert labels[-1] == "合计"


def test_soe_reversal_cumulative_provision_is_amount() -> None:
    """源模板 C59==SUM(C55:C58) → 该列是金额列，不能当文本。"""
    cols = _table("soe", "本期转回或收回金额重要的应收票据坏账准备")["columns"]
    col = next(c for c in cols if c["key"] == "cumulative_provision")
    assert col["label"] == "转回或收回前累计已计提坏账准备金额"
    assert col["format"] == "amount"


def test_listed_movement_rows_follow_source_formula_order() -> None:
    """源模板 B100 = B94+B95-B96-B97-B98-B99（期末数为合计行）。"""
    rows = _table("listed", "本期计提、收回或转回的坏账准备情况").get("rows") or []
    assert [str(r.get("label", "")) for r in rows] == [
        "上年年末数", "本期计提", "本期收回或转回", "本期核销", "本期转销", "其他", "期末数",
    ]
    assert rows[-1].get("is_total") is True


def test_writeoff_detail_note_type_wording() -> None:
    """上市取预设 F4-29「应收票据性质」，国企取源模板「应收票据的性质」。"""
    listed = _table("listed", "重要的应收票据核销情况（逐项披露）")["columns"]
    soe = _table("soe", "重要的应收票据核销情况")["columns"]
    assert next(c for c in listed if c["key"] == "note_type")["label"] == "应收票据性质"
    assert next(c for c in soe if c["key"] == "note_type")["label"] == "应收票据的性质"


# ─── 幂等 ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("variant", VARIANTS)
def test_apply_plan_is_idempotent(variant: str) -> None:
    """已对齐的章节再跑一次计划应零变更（防脚本与模板漂移）。"""
    section = _section(variant)
    changes, warnings = FIX.apply_plan(section, FIX.SECTION_PLANS[variant]["plan"])
    assert warnings == []
    assert changes == []
