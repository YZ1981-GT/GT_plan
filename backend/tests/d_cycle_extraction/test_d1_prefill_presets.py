"""D1 公式管理预设守卫（prefill_formula_mapping.json 的 D1 段）.

spec: .kiro/specs/d1-extraction-chain-completion/
      (Requirements 5.1~5.5 / Property 12)

守卫三件事：
  1. `sheet` 必须是**源模板真实 sheet 名**（openpyxl 直读 xlsx 交叉比对）。
     改造前登记的 `分析程序D1-3` / `票据明细表D1-4` 在源模板里根本不存在
     → 依赖图 `WP:{wp_code}:{sheet}:{cell_ref}` 指向不存在的坐标。
  2. `TB_AUX` 的维度必须是平台真实存在的 `tb_aux_balance.aux_type`。
     改造前用的 `票据类型` 维度不存在（实测 1121.xx 只有 `客户` / `集团内外`）
     → 该公式永远解析不出值。
  3. 明细表侧不得出现 `WP()`（防审定表 ↔ 明细表循环引用）；审定表可用。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_MAPPING_PATH = _BACKEND / "data" / "prefill_formula_mapping.json"
_TEMPLATE_PATH = _BACKEND / "wp_templates" / "D" / "D1 应收票据.xlsx"

# 审定表 sheet（唯一允许出现 WP() 的 D1 sheet）
_ADJUDICATION_SHEET = "审定表D1-1"

# 平台真实存在的辅助维度（DB 实测 tb_aux_balance.aux_type 的高频值；
# D1 相关科目 1121.xx 实测只有「客户」「集团内外」两种）
_KNOWN_AUX_TYPES = {
    "客户",
    "成本中心",
    "业态",
    "税率",
    "集团内外",
    "三方收款标识",
    "医保类型",
    "职员",
    "保证金类别",
    "经营类往来款",
    "预提费用类别",
    "金融机构",
    "计提方式",
    "减值方式",
}

# 已证实**不存在**的维度（改造前误登记；重现即打红）
_PHANTOM_AUX_TYPES = {"票据类型", "票据种类"}


@pytest.fixture(scope="module")
def d1_mappings() -> list[dict]:
    data = json.loads(_MAPPING_PATH.read_text(encoding="utf-8"))
    out = [m for m in data.get("mappings", []) if str(m.get("wp_code")) == "D1"]
    assert out, "prefill_formula_mapping.json 里没有 D1 条目（守卫会空转）"
    return out


@pytest.fixture(scope="module")
def template_sheets() -> set[str]:
    pytest.importorskip("openpyxl")
    from openpyxl import load_workbook

    assert _TEMPLATE_PATH.exists(), f"源模板缺失: {_TEMPLATE_PATH}"
    wb = load_workbook(_TEMPLATE_PATH, read_only=True)
    try:
        return set(wb.sheetnames)
    finally:
        wb.close()


def test_sheet_names_exist_in_source_template(d1_mappings, template_sheets):
    """Property 12：每条 D1 预设的 sheet 必须是源模板真实 tab 名。"""
    bad = [m["sheet"] for m in d1_mappings if m.get("sheet") not in template_sheets]
    assert not bad, (
        f"以下 sheet 名在源模板里不存在: {bad}\n"
        f"源模板 sheet 名: {sorted(template_sheets)}"
    )


def test_stale_sheet_names_do_not_reappear(d1_mappings):
    """改造前的过时 sheet 名不得重现（它们在源模板里没有对应表）。"""
    stale = {"分析程序D1-3", "票据明细表D1-4"}
    used = {m.get("sheet") for m in d1_mappings}
    assert not (used & stale), f"过时 sheet 名重现: {used & stale}"


def test_tb_aux_dimensions_are_real(d1_mappings):
    """Property 12：TB_AUX 维度必须真实存在，且幽灵维度不得重现。"""
    import re

    pattern = re.compile(r"TB_AUX\('([^']*)'\s*,\s*'([^']*)'")
    seen = 0
    for m in d1_mappings:
        for cell in m.get("cells", []):
            formula = cell.get("formula") or ""
            for _code, dim in pattern.findall(formula):
                seen += 1
                assert dim not in _PHANTOM_AUX_TYPES, (
                    f"{m['sheet']}.{cell['cell_ref']} 使用了平台不存在的辅助维度 {dim!r}"
                )
                assert dim in _KNOWN_AUX_TYPES, (
                    f"{m['sheet']}.{cell['cell_ref']} 的辅助维度 {dim!r} 未在已知维度集中，"
                    "请先用 DB 实证再登记"
                )
    assert seen > 0, "D1 段没有任何 TB_AUX 公式（守卫会空转）"


def test_detail_sheets_have_no_wp_formula(d1_mappings):
    """明细表禁 WP()（防审定表 ↔ 明细表循环引用）；审定表允许。"""
    offenders = []
    for m in d1_mappings:
        if m.get("sheet") == _ADJUDICATION_SHEET:
            continue
        for cell in m.get("cells", []):
            if "WP(" in (cell.get("formula") or ""):
                offenders.append(f"{m['sheet']}.{cell['cell_ref']}")
    assert not offenders, f"明细表出现 WP() 循环引用风险: {offenders}"


def test_adjudication_sheet_links_to_both_detail_sheets(d1_mappings):
    """审定表必须登记「← D1-2 原值」与「← D1-4 坏账」两条底稿间连接取数。"""
    adj = next((m for m in d1_mappings if m.get("sheet") == _ADJUDICATION_SHEET), None)
    assert adj is not None, "缺少审定表 D1-1 条目"
    formulas = " ".join(c.get("formula") or "" for c in adj.get("cells", []))
    assert "原值明细表（按类别）D1-2" in formulas, "审定表未登记 ← D1-2 原值明细的连接取数"
    assert "坏账准备明细表D1-4" in formulas, "审定表未登记 ← D1-4 坏账准备明细的连接取数"


def test_bad_debt_sheet_uses_standard_provision_code(d1_mappings):
    """坏账准备明细表必须取标准码 1231-01（不是 1121，也不是原始码 1231.01）。

    `trial_balance.standard_account_code` 存的是标准码；写成客户原始码 `1231.01`
    会查不到，写成 `1121` 是把原值当坏账（改造前即如此）。
    """
    bd = next(
        (m for m in d1_mappings if m.get("sheet") == "坏账准备明细表D1-4"), None
    )
    assert bd is not None, "缺少 D1-4 坏账准备明细表条目"
    assert bd.get("account_codes") == ["1231-01"], bd.get("account_codes")
    for cell in bd.get("cells", []):
        formula = cell.get("formula") or ""
        assert "1231-01" in formula, f"D1-4 公式未用标准码 1231-01: {formula}"
        assert "1231.01" not in formula, "不得用客户原始码（trial_balance 存标准码）"
