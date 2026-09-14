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


def _is_disclosure_sheet(sheet: str) -> bool:
    """是否为附注披露 sheet。

    🔴 判据用「以『附注披露信息』开头」而不是穷举括号写法 —— D 类披露 tab 名的
    括号有**六种写法并存**（D1/D5 全角全角、D2/D3/D7 半角半角、D6 前半后全），
    穷举必漏；而「附注披露信息」这个前缀在源模板里是稳定的。
    """
    return sheet.startswith("附注披露信息")


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
    """明细表禁 WP()（防审定表 ↔ 明细表循环引用）；审定表与披露 sheet 允许。

    🔴 判据从「非审定表一律禁」收窄为「**明细表**禁」（2026-08-06 修）：

    原判据把披露 sheet 也算成明细表，而 D1 的两个披露块各有一条
    ``WP('D1','原值明细表（按类别）D1-2','期末合计')`` 是**勾稽核对**用
    （spec Task 20 交付，`description` 明写「勾稽用，不参与披露取数」）。
    它不构成环 —— 环的成因是**双向**引用（审定表取明细合计、明细表又回取审定数），
    而明细表**不反向引用披露 sheet**，披露 sheet 也不被审定表引用。

    同族已登记：「明细表不得引用审定表」写宽会误伤跨循环引用
    （`D0 → WP('D2','审定表D2-1')` 是函证覆盖率的合法分母）。

    ⚠️ 豁免只给「披露 sheet」这一类，且必须配反向自检证明真正的明细表 WP()
    仍会被抓住（否则本条退化成空转）。
    """
    offenders = []
    for m in d1_mappings:
        sheet = str(m.get("sheet") or "")
        if sheet == _ADJUDICATION_SHEET or _is_disclosure_sheet(sheet):
            continue
        for cell in m.get("cells", []):
            if "WP(" in (cell.get("formula") or ""):
                offenders.append(f"{sheet}.{cell['cell_ref']}")
    assert not offenders, f"明细表出现 WP() 循环引用风险: {offenders}"


def test_detail_sheet_wp_guard_reverse_selfcheck(d1_mappings):
    """反向自检：真正的明细表 WP() 必须被上一条抓住（防豁免退化成空转）。

    两条：
      1. 扫描面非空 —— D1 确实存在既非审定表也非披露 sheet 的明细块；
      2. 往明细块注入一条 WP() 时，上一条的判据必须命中。
    """
    detail_sheets = [
        str(m.get("sheet"))
        for m in d1_mappings
        if str(m.get("sheet")) != _ADJUDICATION_SHEET
        and not _is_disclosure_sheet(str(m.get("sheet")))
    ]
    assert detail_sheets, (
        "D1 段没有任何明细块（既非审定表也非披露 sheet）⇒ 上一条守卫是空转"
    )

    # 复现上一条的判据，施加于「注入了 WP() 的明细块」替身
    fake = [{"sheet": detail_sheets[0], "cells": [{"cell_ref": "X1", "formula": "=WP('D1','审定表D1-1','x')"}]}]
    caught = [
        f"{m['sheet']}.{c['cell_ref']}"
        for m in fake
        if m["sheet"] != _ADJUDICATION_SHEET and not _is_disclosure_sheet(m["sheet"])
        for c in m["cells"]
        if "WP(" in c["formula"]
    ]
    assert caught, "判据无法抓住明细块里的 WP() ⇒ 豁免写得太宽"


def test_disclosure_wp_is_reconcile_only(d1_mappings):
    """披露 sheet 的 WP() 只许作勾稽核对，且必须指向明细表而非审定表。

    若哪天披露块用 WP() 去**取审定表的数**，就形成「审定表 ← 明细表」与
    「披露 ← 审定表」两跳链路，一旦明细表回取披露值即成环 ⇒ 提前钉死。
    """
    for m in d1_mappings:
        sheet = str(m.get("sheet") or "")
        if not _is_disclosure_sheet(sheet):
            continue
        for cell in m.get("cells", []):
            formula = cell.get("formula") or ""
            if "WP(" not in formula:
                continue
            assert _ADJUDICATION_SHEET not in formula, (
                f"{sheet}.{cell['cell_ref']} 的 WP() 指向审定表 {_ADJUDICATION_SHEET}，"
                "披露侧只许与明细表勾稽"
            )
            desc = cell.get("description") or ""
            assert "勾稽" in desc, (
                f"{sheet}.{cell['cell_ref']} 有 WP() 但 description 未写明「勾稽」用途 —— "
                "披露侧 WP() 必须显式声明不参与披露取数"
            )


def test_disclosure_wp_targets_are_detail_sheets_not_adjudication(d1_mappings):
    """披露 sheet 的 WP() 只许指向**明细表**做勾稽，不许指向审定表。

    反向锁死：披露 ← 审定表 会与「审定表 ← 明细表」叠成两跳依赖，且披露数字
    应当独立于审定表口径（源模板披露表的数据来自明细表逐行汇总）。
    """
    import re

    pattern = re.compile(r"WP\('D1'\s*,\s*'([^']*)'")
    seen = 0
    for m in d1_mappings:
        sheet = m.get("sheet") or ""
        if not _is_disclosure_sheet(sheet):
            continue
        for cell in m.get("cells", []):
            for target in pattern.findall(cell.get("formula") or ""):
                seen += 1
                assert target != _ADJUDICATION_SHEET, (
                    f"{sheet}.{cell['cell_ref']} 的 WP() 指向审定表 {target!r}，"
                    "披露数字应直接取明细表汇总"
                )
    assert seen > 0, (
        "披露 sheet 没有任何 WP() 勾稽公式 —— 本守卫会空转；"
        "若确实撤销了披露侧勾稽，请同步删除本用例"
    )


def test_detail_sheets_never_reference_disclosure_sheets(d1_mappings):
    """明细表不得反引披露 sheet —— 这是「披露 ← 明细」不成环的结构性前提。"""
    import re

    pattern = re.compile(r"WP\('D1'\s*,\s*'([^']*)'")
    offenders = []
    for m in d1_mappings:
        sheet = m.get("sheet") or ""
        if _is_disclosure_sheet(sheet) or sheet == _ADJUDICATION_SHEET:
            continue
        for cell in m.get("cells", []):
            for target in pattern.findall(cell.get("formula") or ""):
                if _is_disclosure_sheet(target):
                    offenders.append(f"{sheet}.{cell['cell_ref']} -> {target}")
    assert not offenders, f"明细表反引披露 sheet（会成环）: {offenders}"


def test_disclosure_sheet_predicate_self_check(d1_mappings):
    """反向自检：谓词必须真的命中 D1 的两个披露 sheet，且不误判审定/明细表。"""
    sheets = {m.get("sheet") or "" for m in d1_mappings}
    disclosure = {s for s in sheets if _is_disclosure_sheet(s)}
    assert len(disclosure) == 2, (
        f"D1 应有 2 个披露 sheet 条目（上市 + 国企），实测 {sorted(disclosure)}"
    )
    assert not _is_disclosure_sheet(_ADJUDICATION_SHEET)
    assert not _is_disclosure_sheet("原值明细表（按类别）D1-2")


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
