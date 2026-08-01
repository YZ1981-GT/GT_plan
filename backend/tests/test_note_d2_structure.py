"""附注「应收账款」章节（上市 五、5 / 国企 八、5）结构守卫。

锁死 `fix_note_d2_ar_structure.py` 的修订结果，防止：

- md 重建脚本把两级表头压扁、把占位说明落成假数据行
- 并发会话回退 `note_template_*.json`（幂等脚本 + 契约测试是唯一可靠恢复手段）
- 新增列时漏 `group`/`flat` 表态 → seed 路径被 `_infer_groups_from_headers` 塞凭空父表头

背景：D2 的表名/行骨架已由并发会话的两个归档 spec（`d2-ar-disclosure-template-alignment` /
`d2-ar-disclosure-soe-alignment`）处理过，但两者都只做了同步载荷、没把 `columns`/`guidance`
写回模板 JSON。本守卫锁死本 spec 补齐的那部分（列/guidance/占位行清理）。

spec: .kiro/specs/d-cycle-extraction-chain-completion/ Task 2.3
"""
from __future__ import annotations

import functools
import importlib.util
import json
import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
DATA_DIR = _BACKEND / "data"
FIX_SCRIPT = _BACKEND / "scripts" / "fix" / "fix_note_d2_ar_structure.py"


def _load_fix_module():
    spec = importlib.util.spec_from_file_location("_fix_d2_structure", FIX_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FIX = _load_fix_module()

VARIANTS = ["listed", "soe"]
SECTION = {"listed": "五、5", "soe": "八、5"}
TABLE_COUNT = {"listed": 17, "soe": 13}
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
    assert sec.get("section_title") == "应收账款"


@pytest.mark.parametrize("variant", VARIANTS)
def test_table_count_matches_source_template(variant: str) -> None:
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
    for c in tbl.get("columns") or []:
        assert "/" not in str(c.get("group") or ""), f"{name}.{c.get('key')} group 含 '/'"


@pytest.mark.parametrize(("variant", "name", "tbl"), ALL_TABLES, ids=TABLE_IDS)
def test_column_groups_derived_from_columns(variant: str, name: str, tbl: dict) -> None:
    cols = tbl.get("columns") or []
    want = FIX.derive_column_groups(cols)
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
        assert "<" not in str(h), f"{name} headers 含 HTML"


@pytest.mark.parametrize(("variant", "name", "tbl"), ALL_TABLES, ids=TABLE_IDS)
def test_guidance_present(variant: str, name: str, tbl: dict) -> None:
    g = str(tbl.get("guidance") or "")
    assert len(g.strip()) >= 20, f"{name} guidance 过短或缺失（附注 TAB 无编制提示）"


@pytest.mark.parametrize(("variant", "name", "tbl"), ALL_TABLES, ids=TABLE_IDS)
def test_guidance_has_no_markdown_bold(variant: str, name: str, tbl: dict) -> None:
    """guidance 是纯文本渲染，`**` 会与平台级 `fix_note_bold_markers.py` 互相打架（D1 实测）。"""
    assert "**" not in str(tbl.get("guidance") or ""), f"{name} guidance 残留 markdown 粗体"


@pytest.mark.parametrize(("variant", "name", "tbl"), ALL_TABLES, ids=TABLE_IDS)
def test_no_placeholder_or_header_label_rows(variant: str, name: str, tbl: dict) -> None:
    bad_labels = {"可无限量添加行", "……", "..."}
    for i, row in enumerate(tbl.get("rows") or []):
        assert str(row.get("row_type", "")) != "header_label", f"{name} 第 {i} 行是压扁的表头"
        label = str(row.get("label", "")).strip()
        assert label not in bad_labels, f"{name} 第 {i} 行是占位说明「{label}」"


# ─── 关键表的两级表头分组（防悄悄改回） ────────────────────────────────────────

def _table(variant: str, name: str) -> dict:
    for t in _tables(variant):
        if str(t.get("name", "")) == name:
            return t
    pytest.fail(f"{variant} 缺表「{name}」")


@pytest.mark.parametrize(
    ("variant", "name", "want_groups"),
    [
        ("listed", "按坏账计提方法分类披露", ["账面余额", "坏账准备"]),
        ("listed", "按坏账计提方法分类披露（续：上年年末余额）", ["账面余额", "坏账准备"]),
        ("soe", "（2）按坏账准备计提方法分类披露应收账款", ["账面金额", "坏账准备"]),
        ("soe", "（2）按坏账准备计提方法分类披露应收账款（续：期初数）", ["账面金额", "坏账准备"]),
        ("listed", "组合计提项目：应收中央企业客户", ["期末余额", "上年年末余额"]),
        ("soe", "组合计提项目：应收中央企业客户", ["期末数", "期初数"]),
        ("soe", "采用余额百分比或其他组合方法计提坏账准备的应收账款", ["期末数", "期初数"]),
        ("soe", "（3）本期计提、收回或转回的坏账准备情况", ["本期变动金额"]),
    ],
)
def test_two_level_header_groups(variant: str, name: str, want_groups: list[str]) -> None:
    tbl = _table(variant, name)
    got = [g["group"] for g in tbl.get("_column_groups") or []]
    assert got == want_groups


def test_soe_movement_prior_and_end_have_no_group() -> None:
    """国企变动表「期初数/期末数」不带 group（只有中间 3 列在「本期变动金额」组内）。"""
    cols = _table("soe", "（3）本期计提、收回或转回的坏账准备情况")["columns"]
    prior = next(c for c in cols if c["key"] == "prior_amount")
    end = next(c for c in cols if c["key"] == "end_amount")
    assert not prior.get("group")
    assert not end.get("group")


def test_listed_and_soe_movement_columns_differ() -> None:
    """上市变动表只 2 列（项目+坏账准备金额），国企是 6 列完整变动明细——不可混用。"""
    listed_cols = _table("listed", "本期计提、收回或转回的坏账准备情况")["columns"]
    soe_cols = _table("soe", "（3）本期计提、收回或转回的坏账准备情况")["columns"]
    assert len(listed_cols) == 2
    assert len(soe_cols) == 6


# ─── 5 张动态组合分表列结构同构（上市），2 张同构（国企） ───────────────────────

def test_listed_portfolio_tables_share_identical_columns() -> None:
    names = [
        "组合计提项目：应收中央企业客户", "组合计提项目：应收地方国有企业客户",
        "组合计提项目：应收海外企业客户", "组合计提项目：组合4", "组合计提项目：组合5",
    ]
    cols_sets = [tuple((c["key"], c.get("group")) for c in _table("listed", n)["columns"]) for n in names]
    assert len(set(cols_sets)) == 1, "上市 5 张组合分表列结构必须同构"


def test_soe_portfolio_tables_share_identical_columns() -> None:
    names = ["组合计提项目：应收中央企业客户", "组合计提项目：应收海外企业客户"]
    cols_sets = [tuple((c["key"], c.get("group")) for c in _table("soe", n)["columns"]) for n in names]
    assert len(set(cols_sets)) == 1, "国企 2 张组合分表列结构必须同构"


# ─── 幂等 ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("variant", VARIANTS)
def test_apply_plan_is_idempotent(variant: str) -> None:
    section = _section(variant)
    changes, warnings = FIX.apply_plan(section, FIX.SECTION_PLANS[variant]["plan"])
    assert warnings == []
    assert changes == []


@pytest.mark.parametrize("variant", VARIANTS)
def test_clean_placeholder_rows_is_idempotent(variant: str) -> None:
    assert FIX._clean_placeholder_rows(_section(variant)) == []


@pytest.mark.parametrize("variant", VARIANTS)
def test_titleize_is_idempotent(variant: str) -> None:
    assert FIX.titleize_text_sections(_section(variant)) == []


# ─── text_sections 不得含裸表名 ───────────────────────────────────────────────

@pytest.mark.parametrize("variant", VARIANTS)
def test_text_sections_has_no_bare_table_name(variant: str) -> None:
    bare = FIX.find_bare_table_name_paragraphs(_section(variant))
    assert bare == [], f"{SECTION[variant]} text_sections 含裸表名 {bare}，须加 #### 前缀"


# ─── 表名 ↔ 源 xlsx 小节标题逐字交叉比对（D1 同款升级守卫） ──────────────────

SRC_XLSX = _BACKEND / "wp_templates" / "D" / "D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx"
# 🔴 该 xlsx 有 4 个含「附注」字样的 sheet：**不带 `D2-1` 后缀**的两个（`附注披露信息(上市公司)`
# `/ (国企)`）编号（1）~（7）与附注模板逐字对应；**带 `D2-1` 后缀**的两个是底稿内示例/占位 sheet
# （内容顺序不同、甚至写「其他应收款」字样），不是本章节裁决源。核对方法：openpyxl 直读两组
# 编号小节标题逐字比对（本文件 2026-08-01 手工核实，见 spec Notes）。
SRC_SHEET = {
    "listed": "附注披露信息(上市公司)",
    "soe": "附注披露信息(国企)",
}


def _norm_source_title(raw: str) -> str:
    s = str(raw or "").strip()
    s = re.sub(r"^[（(]\s*\d+\s*[）)]\s*", "", s)
    s = re.sub(r"^其中[：，:,]\s*", "", s)
    s = s.replace("如下", "")
    # 源模板部分小节标题带方括号括注（如「【如证券化、保理等】」），附注表名不含该括注
    s = re.sub(r"[【\[][^】\]]*[】\]]\s*$", "", s)
    return s.rstrip("：:").strip()


@functools.lru_cache(maxsize=4)
def _source_titles(variant: str) -> frozenset[str]:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.load_workbook(SRC_XLSX, data_only=False, read_only=True)
    try:
        ws = wb[SRC_SHEET[variant]]
        raw = {
            str(row[0]).strip()
            for row in ws.iter_rows(min_col=1, max_col=1, values_only=True)
            if row and isinstance(row[0], str) and str(row[0]).strip()
        }
    finally:
        wb.close()
    return frozenset(_norm_source_title(r) for r in raw)


# 只登记「表名应与源模板标题完全对应」的固定表（组合分表是动态生成，名字不在源模板小节里）
SOURCE_TITLE_TABLES = {
    "listed": [
        "按账龄披露", "按坏账计提方法分类披露", "本期计提、收回或转回的坏账准备情况",
        "转回或收回金额重要的坏账准备", "本期实际核销的应收账款情况",
        "重要的应收账款核销情况（逐项披露）",
        "因金融资产转移而终止确认的应收账款情况",
        "转移应收账款且继续涉入形成的资产、负债的金额",
    ],
    # 🔴 国企 aging 表不在此列：源模板国企侧账龄段**不带编号**（隐含在「应收账款附注」
    # 总标题下的第一部分），（1）从「按坏账准备计提方法分类披露」才开始 —— 与上市侧
    # 「（1）按账龄披露」不对称。前端常量把国企账龄表也命名成「（1）按账龄披露应收账款」
    # 是有意的规范化（与上市对称，非抄错），故此表不参与源模板编号交叉裁决。
    "soe": [
        "（2）按坏账准备计提方法分类披露应收账款",
        "（3）本期计提、收回或转回的坏账准备情况", "（4）本期实际核销的应收账款",
        "（5）按欠款方归集的期末余额前五名的应收账款",
        "（6）由金融资产转移而终止确认的应收账款",
        # 源模板 R129「（6）应收账款转移继续涉入形成的资产、负债的金额【如证券化、保理等】」，
        # 附注表编号顺延为（7）（账龄表在国企侧无编号，见上方说明）。
        "（7）应收账款转移继续涉入形成的资产、负债的金额",
    ],
}


@pytest.mark.parametrize(
    ("variant", "name"),
    [(v, n) for v, names in SOURCE_TITLE_TABLES.items() for n in names],
    ids=[f"{v}:{n}" for v, names in SOURCE_TITLE_TABLES.items() for n in names],
)
def test_table_name_matches_source_sheet_title(variant: str, name: str) -> None:
    normalized = _source_titles(variant)
    assert _norm_source_title(name) in normalized, (
        f"{variant} 表名「{name}」在源模板 {SRC_SHEET[variant]} 找不到对应小节标题"
    )
    assert name in {str(t.get("name", "")) for t in _tables(variant)}


def test_source_title_crosscheck_is_not_vacuous() -> None:
    """反向自检：正则失效 / 读空表时上面的断言会全绿。"""
    normalized = _source_titles("listed")
    assert len(normalized) > 15
    assert "（1）期末已质押的应收票据" not in normalized  # D1 的标题不应窜进 D2
