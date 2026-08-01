"""F2 公式预设守卫（`prefill_formula_mapping.json` → 公式管理页 `workpaper:F2`）。

背景：改造前 `审定表F2-1` / `明细汇总表F2-2` 两个块把「原材料=1401」
「在产品=1402」「库存商品=1403」「工程物资=1405」「委托加工物资=1408」
「存货跌价准备=1461」写成公式管理页的固定公式 —— 这些编码在真实科目表里
根本不是这些名字（见 `app.services.f2_extraction.category_rules` 的两个变体
冲突实证表），公式管理页看到的公式与它声称汇总的分类完全对不上。

本守卫钉住 Requirement 4（Wave 4）：

1. `cell_ref` 页内唯一（`page_key` 忽略 sheet，同名会被静默去重丢弃）。
2. 「编码=具体分类」的写死映射已全部删除（Property 6：禁写死编码分类）。
3. 跌价准备保留但显式给出两个变体码并标注「二选一」。
4. 底稿间 `WP()` 联动齐备（F2-1←F2-2、F2-2←F2-3~13、两个披露 sheet、F2-47←F2-1）。
5. 新增/保留公式通过 `validate_formula`（prefill 专属词汇 `ADJ`/`TB_SUM` 豁免）。
6. F2-2 明细汇总表不反引 F2-1（防成环）；F2-3~13 各明细表本身也不含 `WP()`。

spec: .kiro/specs/f2-inventory-account-mapping-and-linkage/ (Task 4.2)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.services.formula_engine import validate_formula
from app.services.formula_management.preset_library import convert_prefill_presets

_ROOT = Path(__file__).resolve().parent.parent
_MAPPING = _ROOT / "data" / "prefill_formula_mapping.json"

PAGE_KEY = "workpaper:F2"

SHEET_ADJ = "审定表F2-1"
SHEET_DETAIL = "明细汇总表F2-2"
SHEET_ANALYSIS = "存货总体分析表F2-18"
SHEET_ANALYSIS_OLD = "分析程序F2-3"
SHEET_F2_47 = "跌价准备测试表F2-47"
SHEET_DISC_LISTED = "附注披露信息（上市公司）"
SHEET_DISC_SOE = "附注披露信息（国企）"

#: F2-3~13 各分类明细表（源 xlsx tab 名），F2-2 应逐一 `WP()` 引用。
_DETAIL_SHEETS = (
    "一、原材料明细表F2-3",
    "二、材料采购、在途物资明细表F2-4",
    "三、周转材料、低值易耗品，包装物明细表F2-5",
    "四、自制半成品明细表F2-6",
    "五、委托加工物资明细表F2-7",
    "六、库存商品明细表F2-8",
    "七、发出商品F2-9",
    "八、开发产品F2-10",
    "九、开发成本F2-11",
    "十、合同履约成本F2-12",
    "十一、消耗性生物资产F2-13",
)

#: 已存在于平台但**未注册进 `formula_engine._REGISTRY`** 的 prefill 专属词汇。
#: `LEDGER`/`LEDGER_DETAIL` 是 F2 盘点/计价测试系列既有条目（改造前已存在，
#: 不属本 spec Wave 4 范围），与 F1 spec 的 `ADJ`/`TB_SUM` 豁免同款处理。
_PREFILL_ONLY_FUNCS = ("ADJ", "TB_SUM", "LEDGER_DETAIL", "LEDGER")

#: 编码语义在两个标准科目表变体间冲突的「具体分类」码（不含区间边界 1499、
#: 不含跌价准备 1416/1461——那两个是显式二选一豁免）。
_VARIANT_CONFLICT_CODES = (
    "1401", "1402", "1403", "1404", "1405", "1406",
    "1407", "1408", "1409", "1410", "1411",
)


def _f2_blocks() -> list[dict]:
    data = json.loads(_MAPPING.read_text(encoding="utf-8"))
    return [b for b in data["mappings"] if b.get("wp_code") == "F2"]


def _f2_presets() -> list:
    return [p for p in convert_prefill_presets() if getattr(p, "page_key", "") == PAGE_KEY]


def _find_block(sheet: str) -> dict | None:
    return next((b for b in _f2_blocks() if b["sheet"] == sheet), None)


def _uses_prefill_only_func(formula: str) -> bool:
    return any(f"{fn}(" in formula for fn in _PREFILL_ONLY_FUNCS)


def _all_formulas() -> list[str]:
    return [
        str(c.get("formula") or "")
        for b in _f2_blocks()
        for c in b.get("cells") or []
    ]


# ─────────────────── cell_ref 页内唯一（page_key 忽略 sheet） ───────────────────


def test_f2_cell_refs_unique_within_page():
    refs = [c["cell_ref"] for b in _f2_blocks() for c in b["cells"]]
    dupes = sorted({r for r in refs if refs.count(r) > 1})
    assert dupes == [], f"workpaper:F2 内 cell_ref 撞键（会被静默丢弃）：{dupes}"


def test_runtime_presets_not_silently_deduped():
    """运行态条目数 == JSON 声明条数（真正验证「没被吞」）。"""
    presets = _f2_presets()
    declared = sum(len(b["cells"]) for b in _f2_blocks())
    assert len(presets) == declared, f"declared={declared} runtime={len(presets)}"
    cells = [p.target_cell for p in presets]
    assert len(cells) == len(set(cells))


# ─────────────────── Property 6：禁写死「编码=分类」映射 ───────────────────


def test_no_hardcoded_category_code_mapping():
    """具体分类编码（除跌价二选一豁免）不得再出现在 F2-1/F2-2 的公式里。"""
    code_pattern = re.compile(
        r"TB\('(" + "|".join(_VARIANT_CONFLICT_CODES) + r")'"
    )
    bad: list[str] = []
    for sheet in (SHEET_ADJ, SHEET_DETAIL):
        block = _find_block(sheet)
        assert block is not None, f"缺 sheet={sheet}"
        for cell in block["cells"]:
            formula = str(cell.get("formula") or "")
            m = code_pattern.search(formula)
            if m:
                bad.append(f"{sheet}/{cell['cell_ref']}: {formula} (编码 {m.group(1)})")
    assert bad == [], bad


def test_reverse_check_variant_conflict_codes_detected():
    """反向自检：本测试文件的编码冲突清单本身能命中改造前的写死写法。"""
    code_pattern = re.compile(
        r"TB\('(" + "|".join(_VARIANT_CONFLICT_CODES) + r")'"
    )
    assert code_pattern.search("=TB('1406','期初余额')")
    assert code_pattern.search("=TB('1401','期末余额')")
    assert not code_pattern.search("=TB_SUM('1401~1499','期末余额')")
    assert not code_pattern.search("=TB('1416','期末余额')")


# ─────────────────── 跌价准备二选一 ───────────────────


def test_impairment_provision_has_both_variant_codes_labeled():
    adj = _find_block(SHEET_ADJ)
    formulas_by_ref = {c["cell_ref"]: c for c in adj["cells"]}
    variant_a = [r for r in formulas_by_ref if "变体A" in r and "存货跌价准备" in r]
    variant_b = [r for r in formulas_by_ref if "变体B" in r and "存货跌价准备" in r]
    assert variant_a and variant_b, formulas_by_ref.keys()
    for ref in variant_a + variant_b:
        assert "二选一" in formulas_by_ref[ref]["description"], ref
    assert any("1416" in formulas_by_ref[r]["formula"] for r in variant_a)
    assert any("1461" in formulas_by_ref[r]["formula"] for r in variant_b)


# ─────────────────── 区间口径保留 ───────────────────


def test_interval_formula_preserved():
    adj = _find_block(SHEET_ADJ)
    formulas = [c["formula"] for c in adj["cells"]]
    assert any("TB_SUM('1401~1499'," in f for f in formulas), formulas


def test_analysis_block_uses_real_source_sheet_name():
    """`分析程序F2-3` 是改造前贴错的 sheet 名（源 xlsx 无此 tab），已改用真实 tab。"""
    assert _find_block(SHEET_ANALYSIS_OLD) is None
    analysis = _find_block(SHEET_ANALYSIS)
    assert analysis is not None
    formulas = [c["formula"] for c in analysis["cells"]]
    assert any("TB_SUM('1401~1499'," in f for f in formulas), formulas


# ─────────────────── 底稿间 WP() 联动齐备 ───────────────────


def test_adj_links_to_f2_14_for_aje_and_f2_2_for_total():
    adj = _find_block(SHEET_ADJ)
    formulas = "\n".join(c["formula"] for c in adj["cells"])
    assert "WP('F2','调整分录汇总F2-14'" in formulas
    assert "WP('F2','明细汇总表F2-2'" in formulas


@pytest.mark.parametrize("detail_sheet", _DETAIL_SHEETS)
def test_f2_2_links_to_each_detail_sheet(detail_sheet: str):
    detail = _find_block(SHEET_DETAIL)
    formulas = "\n".join(c["formula"] for c in detail["cells"])
    assert f"'{detail_sheet}'" in formulas, f"F2-2 缺 {detail_sheet} 联动"


@pytest.mark.parametrize("sheet", (SHEET_DISC_LISTED, SHEET_DISC_SOE))
def test_disclosure_sheets_have_presets(sheet: str):
    block = _find_block(sheet)
    assert block is not None, f"缺披露块 {sheet}"
    assert len(block["cells"]) >= 2
    for cell in block["cells"]:
        assert cell["cell_ref"].strip()
        assert cell["formula"].startswith("=")
        assert len(str(cell.get("description") or "")) >= 10


def test_f2_47_links_to_f2_1():
    block = _find_block(SHEET_F2_47)
    assert block is not None
    formulas = "\n".join(c["formula"] for c in block["cells"])
    assert "WP('F2','存货审定表F2-1'" in formulas


# ─────────────────── 防成环 ───────────────────


def test_f2_2_does_not_reference_f2_1():
    """F2-2 是取数级联的中间层（F2-3~13 → F2-2 → F2-1），反引 F2-1 会成环。"""
    detail = _find_block(SHEET_DETAIL)
    for cell in detail["cells"]:
        assert "存货审定表F2-1" not in cell["formula"], cell


@pytest.mark.parametrize("detail_sheet", _DETAIL_SHEETS)
def test_detail_source_sheets_have_no_wp_reference(detail_sheet: str):
    """F2-3~13 各明细表本身不应有预设块引用其它 F2 sheet（它们是取数根）。"""
    block = _find_block(detail_sheet)
    if block is None:
        return  # 未单独建块属正常（明细表数据来自底稿录入，非公式管理预设）
    for cell in block["cells"]:
        assert "WP(" not in cell["formula"], cell


# ─────────────────── 语法合法 ───────────────────


def test_all_f2_formulas_are_syntactically_valid():
    bad: list[str] = []
    for block in _f2_blocks():
        for cell in block["cells"]:
            formula = cell["formula"]
            if _uses_prefill_only_func(formula):
                continue
            errs = validate_formula(formula)
            if errs:
                bad.append(f"{block['sheet']}/{cell['cell_ref']}: {formula} → {errs}")
    assert bad == [], bad


def test_prefill_only_vocab_still_unregistered():
    """反向自检：ADJ/TB_SUM 若被注册进公式引擎，上面的豁免就该删掉。"""
    for fn in _PREFILL_ONLY_FUNCS:
        errs = validate_formula(f"=({fn}('1401~1499','x'))")
        assert errs, f"{fn}() 现已被 formula_engine 识别 → 请从 _PREFILL_ONLY_FUNCS 移除豁免"
