"""附注「应收票据」章节（上市 五、4 / 国企 八、4）结构守卫。

锁死 `fix_note_d1_notes_receivable_structure.py` 的修订结果，防止：

- md 重建脚本（`rebuild_note_from_md.py`）把两级表头压扁、把占位说明落成假数据行
- 并发会话回退 `note_template_*.json`（幂等脚本 + 契约测试是唯一可靠恢复手段）
- 新增列时漏 `group`/`flat` 表态 → seed 路径被 `_infer_groups_from_headers` 塞凭空父表头

spec: .kiro/specs/d1-notes-receivable-disclosure-alignment/ Task 2.1
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
def test_guidance_has_no_markdown_bold(variant: str, name: str, tbl: dict) -> None:
    """guidance 是纯文本渲染（TAB 提示 / Word 导出都不解析 markdown）。

    🔴 平台级 `fix_note_bold_markers.py` 会剥离 `**`；若本循环脚本又写回，
    两个幂等脚本会互相打架（2026-07-31 实测：组合计提表 guidance 一天内被改两次）。
    """
    assert "**" not in str(tbl.get("guidance") or ""), f"{name} guidance 残留 markdown 粗体"


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
        ("listed", "期末因出票人未履约而其转应收账款的票据"),
        ("soe", "期末因出票人未履约而其转为应收账款的票据"),
    ],
)
def test_transfer_table_lists_commercial_only(variant: str, name: str) -> None:
    """票据逾期应转入应收账款、账龄连续计算 → 出票人未履约只对商业承兑成立。"""
    rows = _table(variant, name).get("rows") or []
    labels = [str(r.get("label", "")) for r in rows]
    assert labels == ["商业承兑票据", "合计"]


# ─── 表名 ↔ 源 xlsx 小节标题逐字交叉比对 ──────────────────────────────────────
#
# 🔴 这是 2026-07-31 复核补的守卫：上市「转应收账款」表名此前多一个「将」
#    （源模板 R31 是「而其转应收账款」），既有断言全是**自证**（拿脚本常量比模板），
#    源模板从未参与裁决 → 漂移零成本。此处直读源 xlsx，让源模板成为裁决者。

SRC_XLSX = _BACKEND / "wp_templates" / "D" / "D1 应收票据.xlsx"
SRC_SHEET = {"listed": "附注披露信息（上市公司）", "soe": "附注披露信息（国企）"}


def _norm_source_title(raw: str) -> str:
    """源模板小节标题 → 附注表名口径。

    去掉：小节编号「（N）」、引子「其中：」/「其中，」、行文尾巴「如下」、结尾冒号。
    """
    s = str(raw or "").strip()
    s = re.sub(r"^[（(]\s*\d+\s*[）)]\s*", "", s)
    s = re.sub(r"^其中[：，:,]\s*", "", s)
    s = s.replace("如下", "")
    return s.rstrip("：:").strip()


@functools.lru_cache(maxsize=4)
def _source_titles(variant: str) -> tuple[frozenset[str], frozenset[str]]:
    """返回（归一后标题集, 原始 A 列文本集）。"""
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
    return frozenset(_norm_source_title(r) for r in raw), frozenset(raw)


# {variant: {表名常量键: 该表名必须逐字等于源模板某个小节标题}}
# 只登记「表名应与源模板标题完全对应」的表；双期拆表（名字带「（期末余额）」等
# 期间后缀）与派生名不在此列。
SOURCE_TITLE_TABLES = {
    "listed": ["pledged", "endorsed", "transfer", "movement",
               "reversal", "writeoff_amount", "writeoff_detail"],
    "soe": ["main", "individual_end", "portfolio", "movement", "reversal",
            "pledged", "endorsed", "transfer", "writeoff_amount", "writeoff_detail"],
}


@pytest.mark.parametrize(
    ("variant", "key"),
    [(v, k) for v, keys in SOURCE_TITLE_TABLES.items() for k in keys],
    ids=[f"{v}:{k}" for v, keys in SOURCE_TITLE_TABLES.items() for k in keys],
)
def test_table_name_matches_source_sheet_title(variant: str, key: str) -> None:
    names = FIX.L if variant == "listed" else FIX.S
    expected = names[key]
    normalized, _raw = _source_titles(variant)
    assert expected in normalized, (
        f"{variant}.{key} 表名「{expected}」在源模板 {SRC_SHEET[variant]} 找不到对应小节标题"
    )
    # 模板 JSON 与脚本常量同名（防只改脚本没落盘）
    assert expected in {str(t.get("name", "")) for t in _tables(variant)}


def test_source_title_crosscheck_is_not_vacuous() -> None:
    """反向自检：正则失效 / 读空表时上面的断言会全绿，这里钉死它非空且真能识别漂移。"""
    normalized, raw = _source_titles("listed")
    assert len(raw) > 30 and len(normalized) > 30
    # 归一确实在做事（原始串带小节编号，归一后不带）
    assert "（1）期末已质押的应收票据" in raw
    assert "（1）期末已质押的应收票据" not in normalized
    # 已修掉的旧名（多一个「将」）不在源模板里 → 该守卫能抓住这次的回归
    for legacy in FIX.LEGACY_TABLE_NAMES["listed"]["transfer"]:
        assert legacy not in normalized, f"旧表名「{legacy}」竟在源模板中，映射需重判"


def test_legacy_table_names_are_not_current_names() -> None:
    """历史表名不得同时是当前表名，否则同步会把刚推的表当孤儿删掉。"""
    for variant, mapping in FIX.LEGACY_TABLE_NAMES.items():
        names = FIX.L if variant == "listed" else FIX.S
        current = set(names.values())
        for key, legacy_list in mapping.items():
            assert key in names, f"{variant}.{key} 不是表名常量键"
            for legacy in legacy_list:
                assert legacy not in current, f"{variant} 历史名「{legacy}」仍是当前表名"


# ─── guidance 归属（源模板括注挂在正确的表上）────────────────────────────────

@pytest.mark.parametrize("variant", VARIANTS)
def test_derecognition_note_belongs_to_endorsed_table(variant: str) -> None:
    """源模板「（如根据准则23号终止确认…）」紧跟**已背书或贴现**表（上市 R27 / 国企 R72-73）。

    该括注讲的是本表两列（终止确认 / 未终止确认金额）的口径，与下一张「转应收账款」
    表无关；此前误挂在 transfer 表 guidance 上。
    """
    names = FIX.L if variant == "listed" else FIX.S
    endorsed = str(_table(variant, names["endorsed"]).get("guidance") or "")
    transfer = str(_table(variant, names["transfer"]).get("guidance") or "")

    assert "企业会计准则第23号" in endorsed and "终止确认的金额" in endorsed
    assert "第23号" not in transfer, "准则23号括注不属于「转应收账款」表"
    # 两张表的 guidance 各自仍有本表勾稽（防把内容搬空）
    assert "F4-22" in endorsed
    assert "F4-23" in transfer


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


# ─── text_sections 不得含裸表名 ───────────────────────────────────────────────


@pytest.mark.parametrize("variant", VARIANTS)
def test_text_sections_has_no_bare_table_name(variant: str) -> None:
    """裸表名会被当披露正文渲染（附注正文与 Word 导出多出只有表名的段落）。

    后端 `disclosure_engine._is_table_title_paragraph` 只认 ① `#` 开头
    ② 非 `#` 时 ≤20 字且匹配 `（N）xxx` / `N. xxx` 编号。写成裸表名既不是标题、
    也没有 `提示`/`【` 等 guidance 关键词 → 落进 `text_content`。
    """
    bare = FIX.find_bare_table_name_paragraphs(_section(variant))
    assert bare == [], (
        f"{SECTION[variant]} text_sections 含裸表名 {bare}，须加 #### 前缀"
    )


@pytest.mark.parametrize("variant", VARIANTS)
def test_table_name_paragraphs_use_hash_prefix(variant: str) -> None:
    """引用表名的段落一律 `#### ` 前缀（与 `fix_note_ar_soe_structure` 同范式）。"""
    section = _section(variant)
    names = {str(t.get("name", "")).strip() for t in (section.get("tables") or [])}
    offenders = [
        p for p in (section.get("text_sections") or [])
        if str(p).strip().lstrip("#").strip() in names and not str(p).startswith("#")
    ]
    assert offenders == [], offenders


@pytest.mark.parametrize("variant", VARIANTS)
def test_titleize_is_idempotent(variant: str) -> None:
    """已标题化后再跑一次应零变更。"""
    assert FIX.titleize_text_sections(_section(variant)) == []


def test_is_title_paragraph_matches_backend_semantics() -> None:
    """复刻函数与后端真实实现同口径（防脚本判定漂移导致守卫空转）。"""
    from app.services.disclosure_engine import _is_table_title_paragraph as backend_impl

    samples = [
        "#### 组合计提项目：银行承兑汇票",
        "组合计提项目：银行承兑汇票",
        "（1）期末已质押的应收票据",
        "1. 期末已质押的应收票据",
        "重要的应收票据核销情况（逐项披露）",
        "【提示：此处披露未逾期的应收票据计提的坏账准备。】",
        "",
        "   ",
        "这是一段超过二十个字的普通披露正文用于验证长度约束是否一致生效",
    ]
    for s in samples:
        assert FIX._is_title_paragraph(s) == backend_impl(s), f"判定不一致：{s!r}"
