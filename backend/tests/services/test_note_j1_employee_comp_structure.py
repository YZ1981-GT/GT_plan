"""附注 J1 应付职工薪酬披露章节结构守卫（对齐源模板后不得漂移）。

配套幂等脚本：``backend/scripts/fix/fix_note_j1_employee_comp_structure.py``
（``--check`` 供 CI；本文件从**模板落盘结果**正向断言，两者互为兜底）。

覆盖的回归点（全部在 2026-07-30 实测发生过）：

- 🔴 soe 八、40 第 3 张表曾与第 2 张**重名**（都叫 `短期薪酬列示`），而前端推
  `设定提存计划列示` → 孤儿子表（模板第 3 张表永空）
- 6 张表 `columns` 曾全部缺失 → seed 路径被 `_infer_groups_from_headers` 按
  「本期增加 / 本期减少」共同前缀反猜出源模板**不存在**的「本期」父表头
- 6 张表 `guidance` 曾全部缺失（附注 TAB 页签无编制提示）
- listed 表2 曾残留 `……` 占位行（渲染成一行空披露数据）
- 两侧说明文本区几乎全缺（soe 只有 3 个 `###` 表标题 → 文本区 seed 恒空）
- 前端子表名常量与模板 `tables[].name` 必须逐字一致（读 `.ts` 源码，防双真源漂移）

spec: .kiro/specs/j1-disclosure-template-alignment/ Task 2.1
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent
DATA_DIR = _BACKEND / "data"
COMPOSABLES = (
    _REPO / "audit-platform" / "frontend" / "src" / "components" / "workpaper" / "composables"
)

TEMPLATE = {
    "listed": DATA_DIR / "note_template_listed.json",
    "soe": DATA_DIR / "note_template_soe.json",
}

SECTION = {"listed": "五、40", "soe": "八、40"}

# 顺序即模板 tables 顺序（汇总 → 短期薪酬 → 设定提存计划）
EXPECTED_TABLES = {
    "listed": ["应付职工薪酬", "短期薪酬", "设定提存计划"],
    "soe": ["应付职工薪酬列示", "短期薪酬列示", "设定提存计划列示"],
}

MOVEMENT_HEADERS = ["项目", "期初余额", "本期增加", "本期减少", "期末余额"]

VARIANTS = ("listed", "soe")

_PLACEHOLDER_LABELS = {"……", "…", "..."}


# ─────────────────────────── 载入 ───────────────────────────

def _load_section(variant: str) -> dict:
    doc = json.loads(TEMPLATE[variant].read_text(encoding="utf-8"))
    for sec in doc.get("sections", []):
        if str(sec.get("section_number", "")) == SECTION[variant]:
            return sec
    raise AssertionError(f"{TEMPLATE[variant].name} 缺章节 {SECTION[variant]}")


def _tables(variant: str) -> list[dict]:
    return _load_section(variant).get("tables") or []


# ─────────────────────────── 表名 / 表数 ───────────────────────────

@pytest.mark.parametrize("variant", VARIANTS)
def test_table_names_and_order(variant: str) -> None:
    """三张表齐备且顺序固定（顺序决定附注 TAB 页签排列）。"""
    assert [t.get("name") for t in _tables(variant)] == EXPECTED_TABLES[variant]


@pytest.mark.parametrize("variant", VARIANTS)
def test_table_names_unique(variant: str) -> None:
    """🔴 重名表会按 name 建键互相覆盖丢表（soe 第 3 张曾与第 2 张同名）。"""
    names = [t.get("name") for t in _tables(variant)]
    assert len(set(names)) == len(names), f"表名重复：{names}"


def test_soe_third_table_is_defined_contribution() -> None:
    """soe 第 3 张表必须叫「设定提存计划列示」，与前端推送键一致。

    回归：原为「短期薪酬列示」（与第 2 张重名）→ 前端推的键在模板里不存在 →
    孤儿子表。`consol_note_sections_soe.json` 五-41-3 的 title 印证此措辞。
    """
    tables = _tables("soe")
    assert tables[2]["name"] == "设定提存计划列示"
    assert tables[2]["rows"][0]["label"] == "离职后福利"


# ─────────────────────────── columns 表态 ───────────────────────────

@pytest.mark.parametrize("variant", VARIANTS)
def test_columns_present_and_flat(variant: str) -> None:
    """每张表 5 列齐备、标签列标 flat、无 group、无残留 `_column_groups`。"""
    for tbl in _tables(variant):
        name = tbl.get("name")
        cols = tbl.get("columns") or []
        assert len(cols) == 5, f"{name} columns={len(cols)}（应 5 列）"
        assert cols[0].get("is_label") is True, f"{name} 首列未标 is_label"
        assert cols[0].get("flat") is True, (
            f"{name} 未标 flat → seed 路径会被反猜出凭空「本期」父表头"
        )
        assert not any(c.get("group") for c in cols), f"{name} 不应有 group（单级表头）"
        assert not tbl.get("_column_groups"), f"{name} 单级表头却残留 _column_groups"


@pytest.mark.parametrize("variant", VARIANTS)
def test_headers_match_columns(variant: str) -> None:
    """headers 与 columns 标签逐字一致，且都等于附注交付口径的 5 列。"""
    for tbl in _tables(variant):
        name = tbl.get("name")
        assert tbl.get("headers") == MOVEMENT_HEADERS, f"{name} headers={tbl.get('headers')}"
        assert [c.get("label") for c in tbl["columns"]] == MOVEMENT_HEADERS, name


@pytest.mark.parametrize("variant", VARIANTS)
def test_amount_columns_formatted(variant: str) -> None:
    """4 个金额列标 format=amount，标签列不标。"""
    for tbl in _tables(variant):
        cols = tbl["columns"]
        assert cols[0].get("format") is None, f"{tbl.get('name')} 标签列不应标 format"
        assert [c.get("format") for c in cols[1:]] == ["amount"] * 4, tbl.get("name")


# ─────────────────────────── rows ───────────────────────────

@pytest.mark.parametrize("variant", VARIANTS)
def test_no_placeholder_or_blank_rows(variant: str) -> None:
    """无 `……` 占位行、无空 label 行、无压扁的 header_label 假数据行。"""
    for tbl in _tables(variant):
        name = tbl.get("name")
        for i, row in enumerate(tbl.get("rows") or []):
            label = str(row.get("label", "")).strip()
            assert row.get("row_type") != "header_label", f"{name}[{i}] 仍为 header_label"
            assert label, f"{name}[{i}] label 为空（交付物不应出现无名空行）"
            assert label not in _PLACEHOLDER_LABELS, (
                f"{name}[{i}] 是占位行「{label}」，语义应移入 guidance"
            )


@pytest.mark.parametrize("variant", VARIANTS)
def test_every_table_ends_with_total(variant: str) -> None:
    """三张表末行都是合计行（源模板均有 SUM 合计）。"""
    for tbl in _tables(variant):
        last = (tbl.get("rows") or [])[-1]
        assert last.get("is_total") is True, f"{tbl.get('name')} 末行不是合计行"
        assert last.get("label") == "合计", f"{tbl.get('name')} 合计行 label={last.get('label')}"


def test_listed_short_term_has_non_monetary_row() -> None:
    """上市表2 有独立「非货币性福利」行（源 xlsx R32）。"""
    labels = [r["label"] for r in _tables("listed")[1]["rows"]]
    assert "非货币性福利" in labels


def test_soe_short_term_merges_non_monetary() -> None:
    """国企表2 **无**独立「非货币性福利」行。

    源公式 `B28='明细表J1-2 '!J30+J31` 把它并入「其他短期薪酬」→ 不得照抄上市版。
    """
    labels = [r["label"] for r in _tables("soe")[1]["rows"]]
    assert "非货币性福利" not in labels
    assert "其他短期薪酬" in labels


def test_soe_summary_has_other_row() -> None:
    """国企表1 多一行「其他」（源 xlsx R13）。"""
    labels = [r["label"] for r in _tables("soe")[0]["rows"]]
    assert labels == [
        "短期薪酬", "离职后福利-设定提存计划", "辞退福利", "一年内到期的其他福利", "其他", "合计",
    ]


# ─────────────────────────── guidance ───────────────────────────

@pytest.mark.parametrize("variant", VARIANTS)
def test_guidance_present(variant: str) -> None:
    """每张表都有 guidance（附注 TAB 页签编制提示），且含勾稽口径。"""
    for tbl in _tables(variant):
        guidance = str(tbl.get("guidance") or "")
        assert guidance.strip(), f"{tbl.get('name')} 缺 guidance"
        assert "勾稽：" in guidance, f"{tbl.get('name')} guidance 未写明勾稽口径"


@pytest.mark.parametrize("variant", VARIANTS)
def test_guidance_states_period_end_formula(variant: str) -> None:
    """三张表都是变动表 → guidance 必须写明 期末 = 期初 + 增加 − 减少。"""
    for tbl in _tables(variant):
        guidance = str(tbl.get("guidance") or "")
        assert "期末余额 = 期初余额 + 本期增加 − 本期减少" in guidance, tbl.get("name")


def test_soe_short_term_guidance_explains_row_granularity() -> None:
    """国企表2 的 3 项 vs 底稿 4 项差异必须写进 guidance（防下次复盘重复提议聚合）。"""
    guidance = _tables("soe")[1]["guidance"]
    assert "医疗保险费及生育保险费" in guidance
    assert "不做聚合" in guidance


# ─────────────────────────── text_sections ───────────────────────────

@pytest.mark.parametrize("variant", VARIANTS)
def test_text_sections_have_no_dropped_headings(variant: str) -> None:
    """🔴 `####` 前缀段会被 `_is_table_title_paragraph` 判为标题并静默丢弃。"""
    for para in _load_section(variant).get("text_sections") or []:
        assert not str(para).startswith("####"), f"{variant} 文本段以 #### 开头：{para[:40]}"


def test_listed_text_sections_cover_four_disclosures() -> None:
    """上市侧 4 段说明齐备（源 xlsx R37 / R38 / R50 / R53）+ 现金流量勾稽注。"""
    blob = "\n".join(_load_section("listed").get("text_sections") or [])
    assert "非货币性福利形式" in blob
    assert "短期利润分享计划" in blob
    assert "设定提存计划的性质" in blob
    assert "辞退福利的性质、内容及计算依据" in blob
    assert "支付职工" in blob, "缺现金流量勾稽注（源 xlsx R54 红字）"


def test_soe_text_sections_cover_three_disclosures() -> None:
    """国企侧 3 条说明齐备（源 xlsx R42~R44），且保留 3 个表标题。"""
    paras = _load_section("soe").get("text_sections") or []
    blob = "\n".join(paras)
    assert paras[:3] == ["### 应付职工薪酬列示", "### 短期薪酬列示", "### 设定提存计划列示"]
    assert "非货币性福利的形式、金额及其计算依据" in blob
    assert "设定提存计划的性质、计算缴费金额的公式或依据" in blob
    assert "重大精算假设及有关敏感性分析" in blob, "第 3 条曾被截断改写"


def test_soe_defined_benefit_cross_reference_points_to_real_section() -> None:
    """设定受益计划交叉引用必须指向真实章节。

    源 xlsx 写"详见附注八、47"，但平台现行 八、47 = 「（3）一年内到期的长期应付款」，
    八、54 = 「长期应付职工薪酬」（8 张设定受益计划表在此）→ 按实证指向 八、54。
    """
    blob = "\n".join(_load_section("soe").get("text_sections") or [])
    assert "八、54" in blob
    assert "八、47" not in blob

    doc = json.loads(TEMPLATE["soe"].read_text(encoding="utf-8"))
    titles = {s.get("section_number"): s.get("section_title") for s in doc["sections"]}
    assert titles.get("八、54") == "长期应付职工薪酬"


# ─────────────────── 前端常量 ↔ 模板（防双真源漂移） ───────────────────

def test_frontend_subtable_keys_match_template() -> None:
    """`j1NoteSectionMap.J1_SUB_TABLE_KEYS` 的表名逐字存在于模板。"""
    src = (COMPOSABLES / "j1NoteSectionMap.ts").read_text(encoding="utf-8")
    block = re.search(
        r"J1_SUB_TABLE_KEYS\s*=\s*\{(.*?)\n\}\s*as const", src, re.S
    )
    assert block, "未找到 J1_SUB_TABLE_KEYS 声明"

    for variant in VARIANTS:
        line = re.search(rf"{variant}:\s*\{{([^}}]*)\}}", block.group(1))
        assert line, f"{variant} 分支缺失"
        names = re.findall(r"'([^']+)'", line.group(1))
        assert len(names) == 3, f"{variant} 子表键数={len(names)}"
        template_names = set(EXPECTED_TABLES[variant])
        assert set(names) == template_names, (
            f"{variant} 前端子表名 {names} ≠ 模板 {sorted(template_names)} → 会产出孤儿子表"
        )


def test_frontend_movement_columns_match_template_headers() -> None:
    """`j1MovementColumns()` 的 5 个 label 与模板 headers 逐字一致。"""
    src = (COMPOSABLES / "j1NoteSectionMap.ts").read_text(encoding="utf-8")
    body = re.search(r"export function j1MovementColumns\(\)[^{]*\{(.*?)\n\}", src, re.S)
    assert body, "未找到 j1MovementColumns"
    labels = re.findall(r"label:\s*'([^']+)'", body.group(1))
    assert labels == MOVEMENT_HEADERS, f"前端列头 {labels} ≠ 模板 {MOVEMENT_HEADERS}"
