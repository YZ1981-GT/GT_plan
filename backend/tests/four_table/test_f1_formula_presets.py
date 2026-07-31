"""F1 公式管理预设契约（R5 / Property 11）。

锁定四件事：

1. F1-1 审定表预设覆盖备抵 `1231-04`（期初/期末）与借贷发生额；
2. F1-1 有 `WP()` 跨底稿取数（← F1-2 明细 / ← F1-5 长期挂款），而 **F1-2 明细表禁 `WP()`**
   （F1 的取数级联是 F1-2 → F1-1，明细反引审定表即成环；与 N1-2 / K1-2 同款约束）；
3. F1-4 用存货报表行口径 `TB_SUM('1401~1499')`，**不得**用 `TB('1401')`
   —— 标准科目表 `1401 = 材料采购`，实证两个真实项目该科目均为空（存货余额恒 0，
   「期末与存货有关预付款项余额占存货比重」这项分析从来算不出）；
4. 预设经 `convert_prefill_presets()` 归入 `workpaper:F1` 且 `formula_type == 'auto_calc'`；
   同一 wp_code 内 `cell_ref` 唯一（`page_key` 忽略 sheet，同名互相遮蔽）。

🔴 为什么备抵必须写 `1231-04`：`TB('1231')` 走 `standard_account_code LIKE '1231%'`
前缀聚合，会把应收票据/应收账款/其他应收款的坏账一并算进 F1
（实证项目 `0ec33ac9`：整个 `1231` 期末 28,464,225.16，其中 26,401,719.77 属应收账款）。

spec: .kiro/specs/f1-four-table-extraction-and-disclosure-alignment/
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[2] / "data" / "prefill_formula_mapping.json"

SHEET_ADJ = "审定表F1-1"
SHEET_DETAIL = "明细表F1-2"
SHEET_ANALYSIS = "实质性分析F1-4"


def _blocks() -> list[dict]:
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    return raw["mappings"] if isinstance(raw, dict) and "mappings" in raw else raw


def _f1_block(sheet: str) -> dict:
    hit = [b for b in _blocks() if b.get("wp_code") == "F1" and b.get("sheet") == sheet]
    assert hit, f"prefill_formula_mapping 缺 F1 {sheet} 块"
    return hit[0]


def _formulas(block: dict) -> list[str]:
    return [str(c.get("formula") or "") for c in block.get("cells") or []]


@pytest.fixture(scope="module")
def f1_adjudication() -> dict:
    return _f1_block(SHEET_ADJ)


@pytest.fixture(scope="module")
def f1_detail() -> dict:
    return _f1_block(SHEET_DETAIL)


@pytest.fixture(scope="module")
def f1_analysis() -> dict:
    return _f1_block(SHEET_ANALYSIS)


# ── R5.1：四表取数科目齐备且口径正确 ────────────────────────────────────────


@pytest.mark.parametrize(
    "snippet",
    [
        "TB('1123','期初余额')",
        "TB('1123','期末余额')",
        "TB('1231-04','期初余额')",
        "TB('1231-04','期末余额')",
        "TB('1123','本期借方')",
        "TB('1123','本期贷方')",
    ],
)
def test_adjudication_covers_required_accounts(f1_adjudication: dict, snippet: str) -> None:
    assert any(snippet in f for f in _formulas(f1_adjudication)), f"缺公式 {snippet}"


def test_provision_never_uses_wide_1231_prefix(f1_adjudication: dict) -> None:
    """反向钉子：不得出现 `TB('1231',…)` 宽口径。"""
    for f in _formulas(f1_adjudication):
        assert "TB('1231'," not in f, f"宽口径坏账公式：{f}"
    # 反向自检：确实存在细分码公式（否则本断言空转）
    assert any("1231-04" in f for f in _formulas(f1_adjudication))


def test_account_codes_declared(f1_adjudication: dict) -> None:
    codes = set(f1_adjudication.get("account_codes") or [])
    assert codes >= {"1123", "1231-04"}, codes


# ── R5.2 / R5.3：跨底稿取数方向（禁环） ─────────────────────────────────────


def test_adjudication_has_cross_workpaper_pulls(f1_adjudication: dict) -> None:
    joined = "\n".join(_formulas(f1_adjudication))
    assert "WP('F1','明细表F1-2'" in joined, "缺 F1-1 ← F1-2 明细期末审定合计"
    assert "WP('F1','长期挂款检查表F1-5'" in joined, "缺 F1-1 ← F1-5 1 年以上审定合计"


def test_detail_sheet_has_no_wp_reference(f1_detail: dict) -> None:
    """F1-2 明细表禁引 `WP()` —— 否则 F1-1 ← F1-2 ← F1-1 成环。"""
    assert "WP(" not in json.dumps(f1_detail, ensure_ascii=False)


def test_detail_sheet_still_has_formulas(f1_detail: dict) -> None:
    """反向自检：F1-2 块本身非空（否则上一条断言恒真）。"""
    joined = "\n".join(_formulas(f1_detail))
    assert "TB('1123'" in joined
    assert "AUX('1123','客户'" in joined, "缺按往来单位（辅助维度 `客户`）取数"


# ── R5.4：F1-4 跨循环锚点用报表行口径 ───────────────────────────────────────


def test_analysis_uses_inventory_report_line_caliber(f1_analysis: dict) -> None:
    joined = "\n".join(_formulas(f1_analysis))
    assert "TB_SUM('1401~1499','期末余额')" in joined, "存货未用 BS-010 区间口径"
    assert "TB('2202','期末余额')" in joined, "缺应付账款 BS-045 口径"


def test_analysis_never_uses_1401_as_inventory(f1_analysis: dict) -> None:
    """反向钉子：`1401` 是「材料采购」，拿它当存货合计 → 实证恒为 0。"""
    for f in _formulas(f1_analysis):
        assert "TB('1401'," not in f, f"用 1401 取存货：{f}"


# ── R5.5：收敛进公式管理 ────────────────────────────────────────────────────


def _f1_preset_entries() -> list:
    """`convert_prefill_presets()` 里归属 `workpaper:F1` 的条目。"""
    from app.services.formula_management import preset_library as pl

    return [e for e in pl.convert_prefill_presets() if e.page_key == "workpaper:F1"]


def test_presets_converge_into_workpaper_scope() -> None:
    entries = _f1_preset_entries()
    assert entries, "F1 预设未收敛进 workpaper:F1"
    for e in entries:
        assert e.formula_type == "auto_calc", f"{e.target_cell} 应为 auto_calc"


def test_cell_refs_unique_within_f1() -> None:
    """`page_key` 忽略 sheet → 同一 wp_code 内 `cell_ref` 同名会互相遮蔽。"""
    refs: list[str] = []
    for b in _blocks():
        if b.get("wp_code") != "F1":
            continue
        refs.extend(str(c.get("cell_ref") or "") for c in b.get("cells") or [])
    dupes = sorted({r for r in refs if refs.count(r) > 1})
    assert not dupes, f"重复 cell_ref：{dupes}"


def test_f1_presets_include_new_cells() -> None:
    cells = {e.target_cell for e in _f1_preset_entries()}
    for want in (
        "坏账准备期初余额",
        "坏账准备期末未审数",
        "本期借方发生额",
        "本期贷方发生额",
        "明细表期末审定合计",
        "长期挂款审定合计",
        "明细期初余额",
        "明细期末余额",
        "明细往来单位期末余额",
        "存货期末余额",
        "存货本期采购金额",
        "应付账款期末余额",
    ):
        assert want in cells, f"公式管理缺条目 {want}"

    joined = "\n".join(str(e.expression or "") for e in _f1_preset_entries())
    assert "TB('1231-04','期末余额')" in joined
    assert "TB_SUM('1401~1499','期末余额')" in joined
    assert "WP('F1','明细表F1-2'" in joined
    # 反向钉子：宽口径坏账 / 误把 1401 当存货，都不得进公式管理
    assert "TB('1231'," not in joined
    assert "TB('1401'," not in joined
