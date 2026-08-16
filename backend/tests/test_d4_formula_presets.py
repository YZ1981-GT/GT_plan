"""D4 营业收入公式预设守卫（`prefill_formula_mapping.json` → 公式管理页 `workpaper:D4`）。

钉住 5 条不变式（Req 7.8, 9.2）：

1. **口径 correct**（Req 7.1）: D4 全部 TB/TB_SUM/TB_AUX 公式不得含 `'期初余额'`/`'期末余额'`
   （损益类科目无余额概念，IS-001/IS-002 均为 `'本期发生额'` 口径）。
2. **科目属于 IS-001/IS-002 集合**（Req 7.8）: 所有引用的科目码属于
   `6001~6099`（IS-001 营业收入）或 `6401~6499`（IS-002 营业成本）范围，
   不得出现其他循环科目（平台守卫盲区：既有测试只校验语法合法性，从不校验科目码归属）。
3. **`(sheet_name, cell_ref)` 唯一**（Req 7.3）: 同一 wp_code 内无重复键
   （重复会导致 key collision → 一条公式被静默吞掉）。
4. **防成环**（Req 7.7）: 明细表块（D4-2、D4-3）不得含 WP() 引用审定表（D4-1）。
5. **语法合法**（Req 7.8）: 所有公式通过基本语法校验
   （合法函数 = TB/TB_SUM/TB_AUX/WP/PREV/LEDGER/LEDGER_DETAIL/ADJ）。

spec: .kiro/specs/d4-four-table-extraction-and-disclosure-alignment/ (Task 6.3)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.services.formula_engine import validate_formula

_ROOT = Path(__file__).resolve().parent.parent
_MAPPING = _ROOT / "data" / "prefill_formula_mapping.json"

# ─── D4 sheet 常量（源 xlsx tab 名精确值） ─────────────────────────────
SHEET_ADJ = "营业收入审定表D4-1"
SHEET_DETAIL_MAIN = "主营业务收入明细表D4-2"
SHEET_DETAIL_OTHER = "其他业务收入明细表D4-3"
SHEET_DISC_LISTED = "附注披露信息（上市公司）"
SHEET_DISC_SOE = "附注披露信息（国企）"

# 明细表 sheets（取数根，不应反向引用审定表）
_DETAIL_SHEETS = (SHEET_DETAIL_MAIN, SHEET_DETAIL_OTHER)

# ─── IS-001 / IS-002 科目码范围 ──────────────────────────────────────
# IS-001 = SUM_TB('6001~6099','本期发生额')  → 营业收入
# IS-002 = SUM_TB('6401~6499','本期发生额')  → 营业成本
_IS001_RANGE = (6001, 6099)  # 含两端
_IS002_RANGE = (6401, 6499)

# 损益类余额口径（禁止出现）
_BALANCE_TERMS = ("期初余额", "期末余额")

# prefill 专属词汇（未注册进 formula_engine._REGISTRY，需豁免语法校验）
_PREFILL_ONLY_FUNCS = ("ADJ", "TB_SUM", "LEDGER", "LEDGER_DETAIL")

# 正则：从 TB/TB_SUM/TB_AUX 公式中提取科目码
_CODE_RE = re.compile(
    r"(?:TB|TB_SUM|TB_AUX)\(\s*'([^']+)'"
)


def _d4_blocks() -> list[dict]:
    data = json.loads(_MAPPING.read_text(encoding="utf-8"))
    return [b for b in data["mappings"] if b.get("wp_code") == "D4"]


def _find_block(sheet: str) -> dict | None:
    return next((b for b in _d4_blocks() if b["sheet"] == sheet), None)


def _all_d4_cells() -> list[tuple[str, dict]]:
    """Return (sheet, cell_dict) for all D4 cells."""
    out: list[tuple[str, dict]] = []
    for b in _d4_blocks():
        for c in b.get("cells") or []:
            out.append((b["sheet"], c))
    return out


def _is_in_is001_or_is002(code: str) -> bool:
    """Check if a single code or range falls within IS-001 (6001~6099) or IS-002 (6401~6499)."""
    # Handle range codes like '6001~6099'
    if "~" in code:
        parts = code.split("~")
        try:
            start = int(parts[0][:4])
            end = int(parts[1][:4])
        except (ValueError, IndexError):
            return False
        return (
            (_IS001_RANGE[0] <= start and end <= _IS001_RANGE[1])
            or (_IS002_RANGE[0] <= start and end <= _IS002_RANGE[1])
        )
    # Handle single codes like '6001' or '6001.11'
    try:
        prefix = int(code[:4])
    except (ValueError, IndexError):
        return False
    return (
        _IS001_RANGE[0] <= prefix <= _IS001_RANGE[1]
        or _IS002_RANGE[0] <= prefix <= _IS002_RANGE[1]
    )


def _uses_prefill_only_func(formula: str) -> bool:
    return any(f"{fn}(" in formula for fn in _PREFILL_ONLY_FUNCS)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 口径 correct（Req 7.1）：损益类科目无余额概念
# ═══════════════════════════════════════════════════════════════════════════


class TestBalanceTermsForbidden:
    """D4 所有 TB/TB_SUM/TB_AUX 公式不得含 '期初余额' / '期末余额'。"""

    def test_no_balance_terms_in_d4_formulas(self):
        bad: list[str] = []
        for sheet, cell in _all_d4_cells():
            formula = cell.get("formula") or ""
            ft = cell.get("formula_type") or ""
            if ft not in ("TB", "TB_SUM", "TB_AUX"):
                continue
            for term in _BALANCE_TERMS:
                if term in formula:
                    bad.append(
                        f"{sheet}.{cell['cell_ref']}: 含 '{term}'（应为 '本期发生额'）"
                    )
        assert bad == [], f"损益类科目用余额口径 {len(bad)} 处：\n" + "\n".join(bad)

    def test_reverse_selfcheck_balance_term_detection(self):
        """反向自检：验证检测逻辑能命中余额口径。"""
        assert "期初余额" in "=TB('6001','期初余额')"
        assert "期末余额" in "=TB('6001','期末余额')"
        assert "期初余额" not in "=TB('6001','本期发生额')"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 科目属于 IS-001/IS-002 集合（Req 7.8）
# ═══════════════════════════════════════════════════════════════════════════


class TestAccountCodeBelongsToD4Cycle:
    """所有引用的科目码属于 6001~6099（IS-001）或 6401~6499（IS-002）。"""

    def test_all_d4_account_codes_in_is001_or_is002(self):
        bad: list[str] = []
        for sheet, cell in _all_d4_cells():
            formula = cell.get("formula") or ""
            ft = cell.get("formula_type") or ""
            # Only check TB/TB_SUM/TB_AUX formulas
            if ft not in ("TB", "TB_SUM", "TB_AUX"):
                continue
            codes = _CODE_RE.findall(formula)
            for code in codes:
                if not _is_in_is001_or_is002(code):
                    bad.append(
                        f"{sheet}.{cell['cell_ref']}: 科目码 '{code}' 不属于"
                        f" IS-001(6001~6099) 或 IS-002(6401~6499)"
                    )
        assert bad == [], f"科目码越界 {len(bad)} 处：\n" + "\n".join(bad)

    def test_reverse_selfcheck_code_range_validation(self):
        """反向自检：确认 _is_in_is001_or_is002 对各种码的判定正确。"""
        # IS-001 范围
        assert _is_in_is001_or_is002("6001")
        assert _is_in_is001_or_is002("6051")
        assert _is_in_is001_or_is002("6099")
        assert _is_in_is001_or_is002("6001.11")
        assert _is_in_is001_or_is002("6001~6099")
        # IS-002 范围
        assert _is_in_is001_or_is002("6401")
        assert _is_in_is001_or_is002("6402")
        assert _is_in_is001_or_is002("6499")
        assert _is_in_is001_or_is002("6401~6499")
        # 不属于 D4 的码
        assert not _is_in_is001_or_is002("1001")
        assert not _is_in_is001_or_is002("1121")
        assert not _is_in_is001_or_is002("6601")
        assert not _is_in_is001_or_is002("2211")
        assert not _is_in_is001_or_is002("1401~1499")

    def test_code_regex_extracts_codes(self):
        """反向自检：正则确实能从公式中抽取科目码。"""
        assert _CODE_RE.findall("=TB('6001','本期发生额')") == ["6001"]
        assert _CODE_RE.findall("=TB_SUM('6001~6099','本期发生额')") == ["6001~6099"]
        assert _CODE_RE.findall("=TB_AUX('6401','月份','本期发生额')") == ["6401"]
        # WP/PREV 不匹配（正确：它们不是取数公式）
        assert _CODE_RE.findall("=WP('D4','主营业务收入明细表D4-2','xx')") == []
        assert _CODE_RE.findall("=PREV('D4','附注披露信息（上市公司）','xx')") == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. (sheet_name, cell_ref) 唯一（Req 7.3）
# ═══════════════════════════════════════════════════════════════════════════


class TestSheetCellRefUnique:
    """同一 D4 wp_code 内 (sheet_name, cell_ref) 无重复。"""

    def test_no_duplicate_sheet_cell_ref_pairs(self):
        pairs: list[tuple[str, str]] = []
        for b in _d4_blocks():
            sn = b.get("sheet_name") or b.get("sheet") or ""
            for c in b.get("cells") or []:
                pairs.append((sn, str(c.get("cell_ref") or "")))
        dupes = sorted({p for p in pairs if pairs.count(p) > 1})
        assert dupes == [], (
            f"D4 内 (sheet_name, cell_ref) 重复"
            f"（同 sheet 内公式会互相遮蔽）：{dupes}"
        )

    def test_all_blocks_have_sheet_name(self):
        """每个 D4 块都声明 sheet_name（否则 page_key 忽略 sheet 导致全局撞键）。"""
        missing: list[str] = []
        for b in _d4_blocks():
            if not b.get("sheet_name"):
                missing.append(b.get("sheet") or b.get("wp_name") or "?")
        assert missing == [], f"缺 sheet_name 的块：{missing}"


# ═══════════════════════════════════════════════════════════════════════════
# 4. 防成环（Req 7.7）
# ═══════════════════════════════════════════════════════════════════════════


class TestNoCyclicReferences:
    """明细表块（D4-2、D4-3）不得含 WP() 引用审定表（D4-1）。"""

    @pytest.mark.parametrize("detail_sheet", _DETAIL_SHEETS)
    def test_detail_does_not_reference_adjudication(self, detail_sheet: str):
        block = _find_block(detail_sheet)
        if block is None:
            pytest.skip(f"块 {detail_sheet} 不存在（正常：明细表可能无预设）")
        for cell in block.get("cells") or []:
            formula = cell.get("formula") or ""
            # 🔴 只拦 `WP()` —— 它是**同年**跨底稿取数，才会成环。
            #    `PREV()` 取的是**上年**底稿同 sheet 的值（跨年度），明细表引用上年
            #    审定数是合法且常见的（趋势对比），不构成循环依赖。
            #    本断言原为 `SHEET_ADJ not in formula`（拦一切引用），与本类
            #    docstring 自述的「不得含 WP() 引用审定表」不一致；2026-08-05 Task 18
            #    把 `分析程序D4-3` 正名为源模板真实 tab `其他业务收入明细表D4-3` 后，
            #    该块自带的 `PREV('D4','营业收入审定表D4-1','审定数')` 被误判成成环。
            if "WP(" not in formula:
                continue
            assert SHEET_ADJ not in formula, (
                f"明细表 '{detail_sheet}' 反向引用审定表（成环）："
                f"{cell['cell_ref']} → {formula}"
            )

    def test_adjudication_may_reference_detail(self):
        """反向自检：审定表引用明细表是合法的（单向联动）。"""
        adj = _find_block(SHEET_ADJ)
        assert adj is not None
        formulas = "\n".join(c["formula"] for c in adj["cells"])
        # 审定表应有 WP() 引用明细表
        has_wp_to_detail = any(
            s in formulas for s in (SHEET_DETAIL_MAIN, SHEET_DETAIL_OTHER)
        )
        assert has_wp_to_detail, "审定表应有 WP() 引用明细表（单向合法）"


# ═══════════════════════════════════════════════════════════════════════════
# 5. 语法合法（Req 7.8）
# ═══════════════════════════════════════════════════════════════════════════


class TestFormulaSyntaxValid:
    """所有公式通过基本语法校验。"""

    def test_all_d4_formulas_syntactically_valid(self):
        bad: list[str] = []
        for sheet, cell in _all_d4_cells():
            formula = cell.get("formula") or ""
            if _uses_prefill_only_func(formula):
                continue
            errs = validate_formula(formula)
            if errs:
                bad.append(
                    f"{sheet}/{cell['cell_ref']}: {formula} → {errs}"
                )
        assert bad == [], f"语法不合法 {len(bad)} 处：\n" + "\n".join(bad)

    def test_prefill_only_vocab_still_unregistered(self):
        """反向自检：ADJ/TB_SUM 等若被注册进公式引擎，豁免就该删。"""
        for fn in _PREFILL_ONLY_FUNCS:
            errs = validate_formula(f"=({fn}('6001','x'))")
            assert errs, (
                f"{fn}() 现已被 formula_engine 识别"
                f" → 请从 _PREFILL_ONLY_FUNCS 移除豁免"
            )
