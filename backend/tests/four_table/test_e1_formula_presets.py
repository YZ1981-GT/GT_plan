"""E1 货币资金公式预设守卫。

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

Properties: 11（科目合法性）、12（sheet 名存在性）

spec: .kiro/specs/e1-four-table-extraction-and-disclosure-alignment/ (Task 6)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import openpyxl
import pytest

_BACKEND = Path(__file__).resolve().parent.parent.parent
MAPPING_PATH = _BACKEND / "data" / "prefill_formula_mapping.json"
E_TEMPLATE_DIR = _BACKEND / "wp_templates" / "E"
CHART_CANDIDATES = sorted((_BACKEND / "data").glob("*account_chart*.json"))

#: `report_config` 实证：`BS-002 货币资金 = TB('1001') + TB('1002') + TB('1012')`，四准则一致
BS002_CODES = {"1001", "1002", "1012"}

#: E0 的已知错误 sheet 名（本 spec 范围外，显式锁定防静默漂移，见脚本 docstring）
E0_KNOWN_BAD_SHEET = "审定表E0-1"


@pytest.fixture(scope="module")
def mapping() -> dict:
    return json.loads(MAPPING_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def e1_blocks(mapping) -> list[dict]:
    return [b for b in mapping["mappings"] if b.get("wp_code") == "E1"]


@pytest.fixture(scope="module")
def source_tabs() -> set[str]:
    """E 目录四个 workbook 的全部 tab 名（openpyxl 直读源 xlsx）。"""
    tabs: set[str] = set()
    for p in sorted(E_TEMPLATE_DIR.glob("*.xlsx")):
        if p.name.startswith("~$"):
            continue
        wb = openpyxl.load_workbook(p, read_only=True)
        tabs.update(wb.sheetnames)
        wb.close()
    return tabs


def _semantic_blob(block: dict) -> str:
    """只取语义字段 —— description/notes 里如实写着被纠正的反例，整块扫描会误报。"""
    parts = [json.dumps(block.get("account_codes") or [], ensure_ascii=False)]
    for k in ("applies_when",):
        if k in block:
            parts.append(f"{k}={block[k]!r}")
    for c in block.get("cells", []):
        parts.append(str(c.get("formula") or ""))
    return "\n".join(parts)


class TestFixtureSanity:
    """反向自检：夹具真的读到了东西，否则下面所有断言都是空转。"""

    def test_blocks_found(self, e1_blocks):
        assert len(e1_blocks) >= 6, f"E1 块只有 {len(e1_blocks)} 个，定位可能失效"

    def test_source_tabs_found(self, source_tabs):
        assert len(source_tabs) > 30, "源 xlsx tab 名集过小，openpyxl 读取可能失败"
        assert "货币资金审定表E1-1" in source_tabs
        assert "附注披露信息(上市公司)" in source_tabs

    def test_semantic_blob_is_not_empty(self, e1_blocks):
        assert any(_semantic_blob(b).strip() for b in e1_blocks)


class TestProperty12SheetNamesExist:
    """Property 12：预设的 sheet 名必须存在于源 xlsx。"""

    def test_every_e1_block_sheet_exists(self, e1_blocks, source_tabs):
        missing = [
            b.get("sheet") for b in e1_blocks if b.get("sheet") not in source_tabs
        ]
        assert missing == [], (
            f"E1 预设指向源 xlsx 不存在的 sheet: {missing} —— prefill 会静默失效"
        )

    def test_analysis_sheet_e1_3_is_gone(self, e1_blocks, source_tabs):
        """`分析程序E1-3` 是双重错误：E1-3 实为银行明细表，分析表是 E1-14。"""
        assert "分析程序E1-3" not in source_tabs
        sheets = {b.get("sheet") for b in e1_blocks}
        assert "分析程序E1-3" not in sheets
        assert "货币资金分析表E1-14" in sheets

    def test_adjudication_sheet_full_name(self, e1_blocks):
        sheets = {b.get("sheet") for b in e1_blocks}
        assert "货币资金审定表E1-1" in sheets
        assert "审定表E1-1" not in sheets, "短名与源 xlsx 分叉（同 G7 已修过的同款）"

    def test_no_formula_references_a_nonexistent_sheet(self, e1_blocks, source_tabs):
        """公式实参里的 sheet 名（`PREV('E1','xxx',…)` / `WP('E1','xxx',…)`）同样要存在。"""
        pat = re.compile(r"(?:PREV|WP)\(\s*'E1'\s*,\s*'([^']+)'")
        bad: list[tuple[str, str, str]] = []
        for b in e1_blocks:
            for c in b.get("cells", []):
                for sheet in pat.findall(c.get("formula") or ""):
                    if sheet not in source_tabs:
                        bad.append((b.get("sheet") or "", c.get("cell_ref") or "", sheet))
        assert bad == [], f"公式引用了不存在的 sheet: {bad}"

    def test_e0_known_bad_sheet_is_locked(self, mapping, source_tabs):
        """E0 的错误 sheet 名属本 spec 范围外，显式锁定现值防静默漂移。

        改名会让一个长期失效的 prefill 突然开始写入 9 个循环共享的函证 sheet，
        需独立验证 → 留作后续（见 spec Notes）。
        """
        e0 = [b for b in mapping["mappings"] if b.get("wp_code") == "E0"]
        assert e0, "未找到 E0 块（锁定断言会空转）"
        assert E0_KNOWN_BAD_SHEET not in source_tabs
        assert {b.get("sheet") for b in e0} == {E0_KNOWN_BAD_SHEET}, (
            "E0 的 sheet 名变了 —— 若已修请同步更新本断言与 spec Notes"
        )


class TestProperty11AccountCodeLegality:
    """Property 11：科目码必须合法且属本循环。"""

    @pytest.fixture(scope="class")
    def standard_codes(self) -> set[str]:
        codes: set[str] = set()
        for p in CHART_CANDIDATES:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            rows = data if isinstance(data, list) else data.get("accounts") or []
            for r in rows:
                if isinstance(r, dict):
                    c = str(r.get("account_code") or r.get("code") or "").strip()
                    if c:
                        codes.add(c)
        return codes

    def test_1502_is_not_referenced(self, e1_blocks):
        """🔴 `1502` = 持有至到期投资减值准备，不是数字货币。"""
        offenders = [
            b.get("sheet") for b in e1_blocks if "1502" in _semantic_blob(b)
        ]
        assert offenders == [], (
            f"块 {offenders} 仍引用 1502（持有至到期投资减值准备）—— "
            "数字货币按准则解释15号在货币资金项下增设二级科目，无独立一级标准科目"
        )

    def test_account_codes_belong_to_bs002(self, e1_blocks):
        """`account_codes` 只允许 BS-002 引用的三个科目（或为空）。"""
        bad: list[tuple[str, list[str]]] = []
        for b in e1_blocks:
            codes = [str(c) for c in (b.get("account_codes") or [])]
            extra = [c for c in codes if c not in BS002_CODES]
            if extra:
                bad.append((b.get("sheet") or "", extra))
        assert bad == [], f"预设引用了本循环之外的科目: {bad}"

    def test_formula_tb_codes_belong_to_bs002(self, e1_blocks):
        """公式里的 `TB('code',…)` 科目码同样受限于 BS-002 三项。"""
        pat = re.compile(r"TB\('([^']+)'")
        bad: list[tuple[str, str, str]] = []
        for b in e1_blocks:
            for c in b.get("cells", []):
                for code in pat.findall(c.get("formula") or ""):
                    if code not in BS002_CODES:
                        bad.append((b.get("sheet") or "", c.get("cell_ref") or "", code))
        assert bad == [], f"公式 TB() 引用了非货币资金科目: {bad}"

    def test_standard_chart_confirms_1502_is_impairment(self, standard_codes):
        """反向自检：标准科目表里 1502 确实存在且不是数字货币（否则断言无意义）。"""
        if not standard_codes:
            pytest.skip("未找到 account_chart 数据文件")
        assert BS002_CODES <= standard_codes, "BS-002 的三个科目应在标准科目表内"

    def test_no_fragile_range_tb_sum(self, e1_blocks):
        """`TB_SUM('1001~1012')` 在客户存在 1003/1011 时虚增 → 改显式三项相加。"""
        offenders = [
            b.get("sheet")
            for b in e1_blocks
            if "TB_SUM('1001~1012'" in _semantic_blob(b)
        ]
        assert offenders == [], f"块 {offenders} 仍用脆弱区间 TB_SUM('1001~1012')"

    def test_bs002_sum_is_explicit_three_terms(self, e1_blocks):
        """审定表的期初/未审数必须是显式三项相加（与 report_config 同构）。"""
        adj = next(b for b in e1_blocks if b.get("sheet") == "货币资金审定表E1-1")
        by_ref = {c.get("cell_ref"): c.get("formula") for c in adj.get("cells", [])}
        for ref in ("期初余额", "未审数"):
            f = by_ref[ref]
            assert f.count("TB('") == 3, f"{ref} 应为三项相加，实为 {f!r}"
            for code in BS002_CODES:
                assert f"TB('{code}'" in f, f"{ref} 缺 {code}"


class TestDeadFieldRemoved:
    def test_applies_when_dead_field_is_gone(self, e1_blocks):
        """`applies_when="tb_account_exists:1502"` 无任何 Python 消费方 = 死字段。

        `chain_orchestrator` 的同名字段读的是 `project_flags` 里的 **flag 名**
        （B60 平台字段机制），与 `prefill_formula_mapping` 不是一回事；
        `notes` 声称的「无 1502 则隐藏整 sheet」从未实现。
        """
        offenders = [
            b.get("sheet") for b in e1_blocks if "tb_account_exists" in _semantic_blob(b)
        ]
        assert offenders == [], f"块 {offenders} 仍带死字段 tb_account_exists"

    def test_digital_currency_uses_placeholder(self, e1_blocks):
        dig = next(b for b in e1_blocks if b.get("sheet") == "数字货币明细表E1-4")
        assert dig.get("account_codes") == [], (
            "数字货币无独立一级标准科目，account_codes 应留空由语义槽定位"
        )
        types = {c.get("formula_type") for c in dig.get("cells", [])}
        assert types == {"PLACEHOLDER"}


class TestNoCircularWpReference:
    """明细块禁引 `WP()` —— E1 级联是 E1-2/E1-3/E1-4 → E1-1，反引即成环。"""

    DETAIL_SHEETS = {
        "现金明细表E1-2",
        "银行存款及其他货币资金明细表(人民币及外币)E1-3",
        "数字货币明细表E1-4",
    }

    def test_detail_blocks_have_no_wp(self, e1_blocks):
        bad: list[tuple[str, str]] = []
        for b in e1_blocks:
            if b.get("sheet") not in self.DETAIL_SHEETS:
                continue
            for c in b.get("cells", []):
                if "WP(" in (c.get("formula") or ""):
                    bad.append((b.get("sheet") or "", c.get("cell_ref") or ""))
        assert bad == [], f"明细块引用 WP() 会成环: {bad}"

    def test_adjudication_block_does_have_wp(self, e1_blocks):
        """反向自检：审定表确实有 WP() 联动（否则上面的断言是空转）。"""
        adj = next(b for b in e1_blocks if b.get("sheet") == "货币资金审定表E1-1")
        wp_cells = [c for c in adj.get("cells", []) if "WP(" in (c.get("formula") or "")]
        assert len(wp_cells) >= 3, "审定表应有 ← E1-2/E1-3/E1-4 三条 WP() 联动"


class TestDisclosureBlocksPresent:
    """两张披露 sheet 改造前零预设（公式管理页空白）。"""

    @pytest.mark.parametrize(
        "sheet", ["附注披露信息(上市公司)", "附注披露信息(国企)"]
    )
    def test_disclosure_block_exists(self, e1_blocks, sheet):
        blk = next((b for b in e1_blocks if b.get("sheet") == sheet), None)
        assert blk is not None, f"缺披露块 {sheet!r}"
        assert blk.get("cells"), f"披露块 {sheet!r} 无条目"

    def test_disclosure_sheet_names_use_halfwidth_parens(self, source_tabs):
        """E 类披露 sheet tab 名是**半角括号**（openpyxl 实证），不得"修正"成全角。"""
        assert "附注披露信息(上市公司)" in source_tabs
        assert "附注披露信息(国企)" in source_tabs
        assert "附注披露信息（上市公司）" not in source_tabs
        assert "附注披露信息（国企）" not in source_tabs


class TestPageKeyUniqueness:
    """`page_key = f"workpaper:{wp_code}"` 忽略 sheet → cell_ref 须全局唯一。"""

    def test_cell_refs_unique_within_wp_code(self, e1_blocks):
        seen: dict[str, str] = {}
        dupes: list[tuple[str, str, str]] = []
        for b in e1_blocks:
            for c in b.get("cells", []):
                ref = c.get("cell_ref") or ""
                if ref in seen:
                    dupes.append((ref, seen[ref], b.get("sheet") or ""))
                else:
                    seen[ref] = b.get("sheet") or ""
        assert dupes == [], (
            f"cell_ref 撞键（同名互相遮蔽）: {dupes} —— 改造前「上年审定数」"
            "在审定表块与分析表块之间即在撞"
        )

    def test_converted_presets_have_no_duplicates(self):
        """经 `convert_prefill_presets()` 实际加载后也不得有重复 target_cell。"""
        from app.services.formula_management.preset_library import (
            convert_prefill_presets,
        )

        e1 = [p for p in convert_prefill_presets() if p.page_key == "workpaper:E1"]
        assert len(e1) >= 40, f"workpaper:E1 只加载到 {len(e1)} 条，可能被撞键吞掉"
        cells = [p.target_cell for p in e1]
        assert len(cells) == len(set(cells)), "加载后仍有重复 target_cell"
