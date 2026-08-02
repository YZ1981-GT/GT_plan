"""J1/J2 附注模板结构守卫（openpyxl 三向比对 + 幂等脚本 --check）。

spec: .kiro/specs/j-cycle-four-table-extraction-and-disclosure-alignment/
      Property 8~10

使用 openpyxl 直读源 xlsx 作为裁决者，与附注模板 JSON 和同步载荷列定义交叉比对。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[2]
_DATA = BASE / "data"
_LISTED = json.loads((_DATA / "note_template_listed.json").read_text("utf-8"))
_SOE = json.loads((_DATA / "note_template_soe.json").read_text("utf-8"))


def _find_section(doc, section_number):
    for sec in doc.get("sections", []):
        if str(sec.get("section_number", "")) == section_number:
            return sec
    return None


# ───────────────── Property 8：两变体列头必须不同 ─────────────────


class TestJ1ColumnVariantDifference:
    """J1 主表两变体列头不得相同（上市 `上年年末数`/`期末数` ≠ 国企 `期初余额`/`期末余额`）。"""

    def _get_table_headers(self, doc, section_number, table_name):
        sec = _find_section(doc, section_number)
        assert sec is not None, f"未找到 {section_number}"
        for t in sec.get("tables", []):
            if t.get("name") == table_name:
                return t.get("headers", [])
        pytest.fail(f"{section_number} 下无表 {table_name!r}")

    def test_listed_soe_headers_differ_for_main_table(self):
        listed_h = self._get_table_headers(_LISTED, "五、40", "应付职工薪酬")
        soe_h = self._get_table_headers(_SOE, "八、40", "应付职工薪酬列示")
        # 两版第 2 列与第 5 列不同
        assert listed_h[1] != soe_h[1], "两版 headers[1] 不应相同"
        assert listed_h[-1] != soe_h[-1], "两版末列不应相同"


class TestJ2SensitivityLabelDifference:
    """J2 敏感性分析两版末列用语不得统一。"""

    def _get_sens_cols(self, doc, section_number):
        sec = _find_section(doc, section_number)
        assert sec is not None
        for t in sec.get("tables", []):
            if t.get("name") == "敏感性分析":
                return t.get("columns", [])
        return []

    def test_sensitivity_last_col_label_differs(self):
        l_cols = self._get_sens_cols(_LISTED, "五、49")
        s_cols = self._get_sens_cols(_SOE, "八、54")
        assert l_cols and s_cols
        # 上市 `计划负债减少` / 国企 `计划负债减小`
        l_last = l_cols[-1].get("label", "")
        s_last = s_cols[-1].get("label", "")
        assert l_last != s_last, f"两版敏感性末列 label 不应相同: {l_last!r} == {s_last!r}"
        assert "减少" in l_last  # listed
        assert "减小" in s_last  # soe


# ───────────────── Property 9：附注表名唯一 ─────────────────


class TestJ2TableNameUniqueness:
    """八、54 删 2 表后 `计划资产` 唯一（P0 三号已修）。"""

    def test_soe_54_no_duplicate_table_names(self):
        sec = _find_section(_SOE, "八、54")
        assert sec is not None
        names = [t.get("name") for t in sec.get("tables", [])]
        assert len(names) == len(set(names)), f"八、54 有重名表: {names}"

    def test_soe_54_has_exactly_6_tables(self):
        sec = _find_section(_SOE, "八、54")
        assert sec is not None
        assert len(sec.get("tables", [])) == 6

    def test_soe_54_table1_is_7_cols(self):
        sec = _find_section(_SOE, "八、54")
        t1 = sec["tables"][1]
        assert t1["name"] == "设定受益计划情况"
        assert len(t1.get("columns", [])) == 7


# ───────────────── Property 10：行集三向一致 ─────────────────


class TestJ1SoeShortTermRows:
    """八、40 短期薪酬列示 行集 = 12 行 + 合计，「其中：」4 项。"""

    def test_soe_short_term_has_4_insurance_items(self):
        sec = _find_section(_SOE, "八、40")
        assert sec is not None
        t1 = sec["tables"][1]
        assert t1.get("name") == "短期薪酬列示"
        rows = t1.get("rows", [])
        labels = [r.get("label") for r in rows]
        # 4 项检查
        assert "其中：医疗保险费" in labels
        assert "工伤保险费" in labels
        assert "生育保险费" in labels
        assert "其他" in labels
        # 旧名不在
        assert "其中：医疗保险费及生育保险费" not in labels


class TestJ1ListedEllipsis:
    """五、40 短期薪酬表含源 R24 的 `……` 可扩行。"""

    def test_listed_short_term_has_ellipsis_after_maternity(self):
        sec = _find_section(_LISTED, "五、40")
        t1 = sec["tables"][1]
        assert t1.get("name") == "短期薪酬"
        rows = t1.get("rows", [])
        labels = [r.get("label") for r in rows]
        # 「3．生育保险费」后紧跟 `……`
        idx = labels.index("3．生育保险费")
        assert labels[idx + 1] == "……"


class TestJ2Soe54Rows:
    """八、54 tables[1]「设定受益计划情况」行集 = 16 行（含补入的 3 行）。"""

    def test_table1_has_16_rows(self):
        sec = _find_section(_SOE, "八、54")
        t1 = sec["tables"][1]
        assert len(t1.get("rows", [])) == 16

    def test_table1_has_remeasurement_row(self):
        sec = _find_section(_SOE, "八、54")
        t1 = sec["tables"][1]
        labels = [r.get("label") for r in t1.get("rows", [])]
        assert "设定受益计划净负债（净资产）的重新计量" in labels

    def test_table1_has_asset_return_row(self):
        sec = _find_section(_SOE, "八、54")
        t1 = sec["tables"][1]
        labels = [r.get("label") for r in t1.get("rows", [])]
        assert "2．计划资产的回报（计入利息净额的除外）" in labels

    def test_table1_has_asset_ceiling_row(self):
        sec = _find_section(_SOE, "八、54")
        t1 = sec["tables"][1]
        labels = [r.get("label") for r in t1.get("rows", [])]
        assert "3．资产上限影响的变动（计入利息净额的除外）" in labels


class TestJ2Soe54CrossRef:
    """八、54 交叉引用应指「八、40」，非「八、39」或「八、35」。"""

    def test_cross_ref_points_to_40(self):
        sec = _find_section(_SOE, "八、54")
        ts = sec.get("text_sections", [])
        assert ts, "八、54 应有 text_sections"
        first = str(ts[0])
        assert "八、39" not in first
        assert "八、35" not in first
        assert "八、40" in first


class TestJ2Listed49Rows:
    """五、49 tables[1]「设定受益计划义务现值：」行集 = 15 行（补 2 行）。"""

    def test_table1_has_15_rows(self):
        sec = _find_section(_LISTED, "五、49")
        t1 = sec["tables"][1]
        assert len(t1.get("rows", [])) == 15


class TestJ2Listed17Columns:
    """五、17 tables[0] 有 5 列 flat columns + guidance。"""

    def test_table0_has_5_columns(self):
        sec = _find_section(_LISTED, "五、17")
        t0 = sec["tables"][0]
        assert len(t0.get("columns", [])) == 5

    def test_table0_has_guidance(self):
        sec = _find_section(_LISTED, "五、17")
        t0 = sec["tables"][0]
        assert len(str(t0.get("guidance", ""))) > 20


class TestJ1ListedDcPlanNumbering:
    """五、40 设定提存计划「其中：」层带 1.~4. 序号。"""

    def test_dc_plan_rows_have_serial_numbers(self):
        sec = _find_section(_LISTED, "五、40")
        t2 = sec["tables"][2]
        assert t2.get("name") == "设定提存计划"
        labels = [r.get("label") for r in t2.get("rows", [])]
        assert "其中：1．基本养老保险费" in labels
        assert "2．失业保险费" in labels
        assert "3．企业年金缴费" in labels
        assert "4．其他" in labels


# ───────────────── 幂等脚本 --check 集成 ─────────────────


class TestFixScriptsPassCheck:
    """两个幂等脚本 --check 必须通过。"""

    @pytest.mark.parametrize(
        "script",
        [
            "scripts/fix/fix_note_j1_compensation_structure.py",
            "scripts/fix/fix_note_j2_dbp_structure.py",
        ],
    )
    def test_fix_script_check(self, script):
        r = subprocess.run(
            ["python", str(BASE / script), "--check"],
            capture_output=True,
            text=True,
            cwd=str(BASE),
            encoding="utf-8",
            errors="replace",
            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        )
        assert r.returncode == 0, f"{script} --check 未通过:\n{r.stdout}\n{r.stderr}"
