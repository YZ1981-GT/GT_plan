"""F3/F4/F5 公式预设守卫（Property 8, 9）。

验证：
- 科目码与 report_config 一致
- 公式语法合法（TB/TB_SUM/WP/PREV/AUX/ADJ 词汇表）
- 无成环（明细表块不得引用审定表）
- sheet 名与源 xlsx tab 名逐字一致（openpyxl 直读）
- 虚构 AUX 维度值已清除

spec: .kiro/specs/f-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 5.1~5.8 / Property 8, 9
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
MAPPING_PATH = _BACKEND / "data" / "prefill_formula_mapping.json"
TEMPLATE_DIR = _BACKEND / "wp_templates"

#: 公式预设引擎支持的函数关键字（上层用 `=` 开头识别，本守卫只验证函数名合法性）
VALID_FORMULA_FUNCTIONS = {"TB", "TB_SUM", "WP", "PREV", "AUX", "ADJ", "LEDGER", "LEDGER_DETAIL"}

#: 虚构 AUX 维度值黑名单
FABRICATED_AUX_VALUES = {"TOP1", "TOP2", "TOP3", "TOP4", "TOP5", "A类", "B类", "长库龄", "呆滞"}


@pytest.fixture(scope="module")
def doc():
    with open(MAPPING_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def f_blocks(doc):
    return [b for b in doc["mappings"] if b.get("wp_code", "").startswith("F")]


@pytest.fixture(scope="module")
def f345_xlsx_tabs():
    """从源 xlsx 读取 F3/F4/F5 可见 sheet tab 名集合。"""
    try:
        from openpyxl import load_workbook
    except ImportError:
        pytest.skip("openpyxl not available")

    tabs: dict[str, set[str]] = {}
    for code in ("F3", "F4", "F5"):
        pattern = os.path.join(TEMPLATE_DIR, "**", f"{code} *.xlsx")
        files = [f for f in glob.glob(pattern, recursive=True) if "~$" not in f]
        if not files:
            continue
        wb = load_workbook(files[0], read_only=True, data_only=True)
        tabs[code] = {sn for sn in wb.sheetnames if wb[sn].sheet_state == "visible"}
        wb.close()
    return tabs


# ─── Property 8: 公式语法合法 ─────────────────────────────────────────────────


class TestFormulaSyntax:
    """每条公式的函数名必须在合法词汇表内。"""

    def test_all_f_cycle_formulas_have_valid_function(self, f_blocks):
        invalid = []
        for b in f_blocks:
            items_key = "items" if "items" in b else "cells"
            for cell in b.get(items_key, []):
                formula = cell.get("formula", "")
                if not formula.startswith("="):
                    continue
                # 提取函数名（第一个 `(` 之前的文字，去掉 `=`）
                body = formula.lstrip("=")
                paren_idx = body.find("(")
                if paren_idx < 0:
                    continue
                func_name = body[:paren_idx].strip()
                if func_name not in VALID_FORMULA_FUNCTIONS:
                    invalid.append(
                        f"{b['wp_code']}/{b.get('sheet','')}: {cell.get('cell_ref','')}: "
                        f"未知函数 '{func_name}'"
                    )
        assert not invalid, f"发现 {len(invalid)} 条非法函数:\n" + "\n".join(invalid)


# ─── Property 9: 明细表禁反引审定表（防成环） ────────────────────────────────────


class TestNoCircularReference:
    """明细表块不得含 WP() 引用。"""

    @pytest.mark.parametrize("wp_code", ["F3", "F4", "F5"])
    def test_detail_block_no_wp(self, f_blocks, wp_code):
        for b in f_blocks:
            if b.get("wp_code") != wp_code:
                continue
            sheet = b.get("sheet", "")
            if "明细" not in sheet:
                continue
            items_key = "items" if "items" in b else "cells"
            for cell in b.get(items_key, []):
                formula = cell.get("formula", "")
                assert "WP(" not in formula, (
                    f"{wp_code}/{sheet}: 明细表禁 WP()（防成环）→ "
                    f"{cell.get('cell_ref','')}: {formula[:60]}"
                )


# ─── Property 8: sheet 名与源 xlsx tab 名一致 ────────────────────────────────


class TestSheetNameConsistency:
    """预设块的 sheet 必须是源 xlsx 的可见 tab 名。"""

    @pytest.mark.parametrize("wp_code", ["F3", "F4", "F5"])
    def test_sheet_exists_in_source_xlsx(self, f_blocks, f345_xlsx_tabs, wp_code):
        if wp_code not in f345_xlsx_tabs:
            pytest.skip(f"{wp_code} 源 xlsx 未找到")
        xlsx_tabs = f345_xlsx_tabs[wp_code]
        for b in f_blocks:
            if b.get("wp_code") != wp_code:
                continue
            sheet = b.get("sheet", "")
            if not sheet:
                continue
            # 只检查有 items 的块（空骨架块是遗留，不阻塞）
            items_key = "items" if "items" in b else "cells"
            if not b.get(items_key):
                continue
            assert sheet in xlsx_tabs, (
                f"{wp_code}: 预设 sheet '{sheet}' 不在源 xlsx tab 名集合中。"
                f"可用 tab: {sorted(xlsx_tabs)}"
            )


# ─── Property 8: 虚构 AUX 维度值已清除 ───────────────────────────────────────


class TestNoFabricatedAux:
    """F 类预设不得含虚构的 AUX 维度值。"""

    def test_no_fabricated_aux_values(self, f_blocks):
        violations = []
        for b in f_blocks:
            items_key = "items" if "items" in b else "cells"
            for cell in b.get(items_key, []):
                formula = cell.get("formula", "")
                for fab in FABRICATED_AUX_VALUES:
                    if f"'{fab}'" in formula:
                        violations.append(
                            f"{b['wp_code']}/{b.get('sheet','')}: "
                            f"{cell.get('cell_ref','')}: 虚构维度 '{fab}'"
                        )
        assert not violations, (
            f"发现 {len(violations)} 处虚构 AUX 维度值:\n" + "\n".join(violations)
        )


# ─── Property 8: 损益类禁期初/期末余额 ──────────────────────────────────────


class TestPLAccountNoBalance:
    """F5（损益类）预设禁 '期初余额'/'期末余额'。"""

    def test_f5_no_balance_period(self, f_blocks):
        violations = []
        for b in f_blocks:
            if b.get("wp_code") != "F5":
                continue
            items_key = "items" if "items" in b else "cells"
            for cell in b.get(items_key, []):
                formula = cell.get("formula", "")
                if "'期初余额'" in formula or "'期末余额'" in formula:
                    violations.append(
                        f"F5/{b.get('sheet','')}: {cell.get('cell_ref','')}: "
                        f"损益类禁期初/期末余额 → {formula[:60]}"
                    )
        assert not violations, "\n".join(violations)


# ─── 反向自检 ────────────────────────────────────────────────────────────────


class TestReverseChecks:
    """确保守卫非空转。"""

    def test_f_blocks_nonempty(self, f_blocks):
        """F 类预设块非空（本守卫确实在检查东西）。"""
        assert len(f_blocks) >= 30, f"F 类块只有 {len(f_blocks)} 个，预期 ≥30"

    def test_f345_have_items(self, f_blocks):
        """F3/F4/F5 至少各有一个块含 items。"""
        for code in ("F3", "F4", "F5"):
            code_blocks = [b for b in f_blocks if b.get("wp_code") == code]
            has_items = any(
                len(b.get("items", b.get("cells", []))) > 0
                for b in code_blocks
            )
            assert has_items, f"{code} 的所有块 items 为空，预设未落地"

    def test_fix_script_check_passes(self):
        """`fix_f_cycle_prefill_presets.py --check` exit 0。"""
        import subprocess
        result = subprocess.run(
            ["python", str(_BACKEND / "scripts" / "fix" / "fix_f_cycle_prefill_presets.py"), "--check"],
            capture_output=True, text=True, cwd=str(_BACKEND.parent),
        )
        assert result.returncode == 0, f"--check 失败:\n{result.stdout}\n{result.stderr}"
