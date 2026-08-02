"""J 类公式预设合法性守卫。

spec: .kiro/specs/j-cycle-four-table-extraction-and-disclosure-alignment/
      Property 6, 7（预设科目码双重合法 / sheet 名存在于源 xlsx）

注：本测试**不连库**（CI 可跑），用静态文件做断言。
"""
from __future__ import annotations

import json
from pathlib import Path

import openpyxl
import pytest

BASE = Path(__file__).resolve().parents[2]
MAPPING_FILE = BASE / "data" / "prefill_formula_mapping.json"
WP_TEMPLATES = BASE / "wp_templates" / "J"

# 源 xlsx tab 名（逐字精确，含尾空格差异）
_XLS_SHEETS: dict[str, list[str]] = {}


def _get_xlsx_sheets(wp_code: str) -> list[str]:
    if wp_code not in _XLS_SHEETS:
        pattern = list(WP_TEMPLATES.glob(f"{wp_code} *.xlsx"))
        if not pattern:
            pattern = list(WP_TEMPLATES.glob(f"{wp_code}*.xlsx"))
        if pattern:
            wb = openpyxl.load_workbook(str(pattern[0]), read_only=True)
            _XLS_SHEETS[wp_code] = list(wb.sheetnames)
        else:
            _XLS_SHEETS[wp_code] = []
    return _XLS_SHEETS[wp_code]


def _j_blocks():
    doc = json.loads(MAPPING_FILE.read_text("utf-8"))
    return [b for b in doc["mappings"] if b["wp_code"] in ("J1", "J2", "J3")]


class TestPresetAccountCodes:
    """Property 6：预设科目码双重合法。"""

    @pytest.mark.parametrize("block", _j_blocks(), ids=lambda b: f"{b['wp_code']}/{b['sheet']}")
    def test_no_2611_in_any_formula(self, block):
        """🔴 `2611` 在活体 account_chart 不存在 → 恒空。"""
        for c in block["cells"]:
            assert "2611" not in c.get("formula", ""), (
                f"{block['wp_code']}/{block['sheet']}/{c['cell_ref']}: "
                f"公式含不存在的科目码 2611"
            )

    @pytest.mark.parametrize("block", _j_blocks(), ids=lambda b: f"{b['wp_code']}/{b['sheet']}")
    def test_no_2221_in_j2_formula(self, block):
        """🔴 J2 不能用 `2221`（那是应交税费）。"""
        if block["wp_code"] != "J2":
            return
        assert "2221" not in block.get("account_codes", [])
        for c in block["cells"]:
            assert "2221" not in c.get("formula", "")

    def test_j2_account_codes_are_2705(self):
        for b in _j_blocks():
            if b["wp_code"] == "J2":
                assert b["account_codes"] == ["2705"], f"{b['sheet']}: should be ['2705']"


class TestPresetSheetNames:
    """Property 7：预设 sheet 名存在于源 xlsx。"""

    @pytest.mark.parametrize("block", _j_blocks(), ids=lambda b: f"{b['wp_code']}/{b['sheet']}")
    def test_sheet_exists_in_source_xlsx(self, block):
        wp = block["wp_code"]
        sheet = block["sheet"]
        xlsx_sheets = _get_xlsx_sheets(wp)
        if not xlsx_sheets:
            pytest.skip(f"源 xlsx 未找到 ({wp})")
        # 源 xlsx 部分 tab 名有尾空格（如 `审定表J1-1 `），这是 xlsx quirk
        # → 按 strip 比对，不强制预设带空格
        stripped = [s.strip() for s in xlsx_sheets]
        assert sheet.strip() in stripped, (
            f"{wp} 预设的 sheet {sheet!r} 不在源 xlsx tab 名清单内。\n"
            f"  可选: {xlsx_sheets}"
        )


class TestPresetCircularDependency:
    """明细表块禁 WP()（防成环）。"""

    @pytest.mark.parametrize("block", _j_blocks(), ids=lambda b: f"{b['wp_code']}/{b['sheet']}")
    def test_detail_blocks_have_no_wp_formula(self, block):
        if "明细" not in block.get("sheet", ""):
            return
        for c in block["cells"]:
            assert "WP(" not in c.get("formula", ""), (
                f"{block['wp_code']}/{block['sheet']}/{c['cell_ref']}: "
                f"明细表块禁 WP()（防成环）"
            )


class TestPresetNoHardcodedAux:
    """J1-2/J1-7 不得残留硬编码成本中心 AUX。"""

    @pytest.mark.parametrize("block", _j_blocks(), ids=lambda b: f"{b['wp_code']}/{b['sheet']}")
    def test_no_aux_with_cost_center_literal(self, block):
        if block["wp_code"] != "J1":
            return
        if block["sheet"] not in ("明细表J1-2 ", "分配情况检查表J1-7"):
            return
        for c in block["cells"]:
            if c.get("formula_type") == "AUX" and "成本中心" in c.get("formula", ""):
                pytest.fail(
                    f"{block['sheet']}/{c['cell_ref']}: 残留硬编码成本中心 AUX\n"
                    f"  formula={c['formula']}"
                )


class TestPresetCheck:
    """幂等脚本 `--check` 必须通过（CI 挂这一条即可保全部修订不回退）。"""

    def test_fix_script_check_passes(self):
        import subprocess

        script = BASE / "scripts" / "fix" / "fix_j_cycle_prefill_presets.py"
        r = subprocess.run(
            ["python", str(script), "--check"],
            capture_output=True,
            text=True,
            cwd=str(BASE),
            encoding="utf-8",
            errors="replace",
            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        )
        assert r.returncode == 0, f"--check 未通过:\n{r.stdout}\n{r.stderr}"
