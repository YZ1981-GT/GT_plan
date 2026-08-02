"""后端守卫：M 循环附注模板结构一致性（幂等脚本 `--check` 退出码校验 + 基本结构断言）。

spec: .kiro/specs/m-cycle-four-table-extraction-and-disclosure-alignment/
      Property 5, 7
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LISTED = ROOT / "data" / "note_template_listed.json"
SOE = ROOT / "data" / "note_template_soe.json"
SCRIPT = ROOT / "scripts" / "fix" / "fix_note_m_equity_structure.py"


class TestIdempotentScript:
    """幂等脚本 `--check` 必须 exit 0（0 项欠账）。"""

    def test_check_exit_zero(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check"],
            capture_output=True,
            text=True,
            cwd=str(ROOT.parent),
        )
        assert result.returncode == 0, (
            f"fix_note_m_equity_structure.py --check 报告欠账:\n{result.stdout}\n{result.stderr}"
        )


class TestListedSections:
    """listed 侧 M 循环章节结构断言。"""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.doc = json.loads(LISTED.read_text(encoding="utf-8"))
        self.secs = self.doc["sections"]

    def _find(self, num: str):
        for s in self.secs:
            if (s.get("section_number") or "").replace(" ", "") == num.replace(" ", ""):
                return s
        pytest.fail(f"未找到章节 {num}")

    def test_stock_53_has_8_columns(self):
        s = self._find("五、53")
        tbl = s["tables"][0]
        assert len(tbl["columns"]) == 8
        groups = {c.get("group") for c in tbl["columns"] if c.get("group")}
        assert "本期增减（+、-）" in groups

    def test_other_equity_54_has_3_tables(self):
        s = self._find("五、54")
        assert len(s["tables"]) == 3
        names = [t["name"] for t in s["tables"]]
        assert "权益工具持有者的相关信息" in names
        # 表2 两级表头
        t1 = s["tables"][1]
        assert len(t1["columns"]) == 9
        groups = {c.get("group") for c in t1["columns"] if c.get("group")}
        assert len(groups) == 4  # 期初/增加/减少/期末

    def test_treasury_stock_56_has_5_flat_columns(self):
        s = self._find("五、56")
        tbl = s["tables"][0]
        assert len(tbl["columns"]) == 5
        assert tbl["columns"][0].get("flat") is True

    def test_oci_57_has_two_tables_8_cols_each(self):
        s = self._find("五、57")
        assert len(s["tables"]) == 2
        for t in s["tables"]:
            assert len(t["columns"]) == 8
            groups = {c.get("group") for c in t["columns"] if c.get("group")}
            assert "本期发生金额" in groups

    def test_general_risk_60_has_table(self):
        s = self._find("五、60")
        assert len(s["tables"]) >= 1
        tbl = s["tables"][0]
        assert tbl["name"] == "一般风险准备"
        assert len(tbl["columns"]) == 5

    def test_retained_earnings_61_has_4_columns(self):
        s = self._find("五、61")
        tbl = s["tables"][0]
        assert len(tbl["columns"]) == 4

    def test_no_header_label_rows(self):
        """所有 M 类章节不得残留 header_label 假行。"""
        nums = ["五、53", "五、54", "五、56", "五、57", "五、60", "五、61"]
        for num in nums:
            s = self._find(num)
            for t in s.get("tables") or []:
                for row in t.get("rows") or []:
                    assert row.get("row_type") != "header_label", (
                        f"{num} {t.get('name')} 残留 header_label 行"
                    )


class TestSoeSections:
    """soe 侧 M 循环章节结构断言。"""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.doc = json.loads(SOE.read_text(encoding="utf-8"))
        self.secs = self.doc["sections"]

    def _find(self, num: str):
        for s in self.secs:
            if (s.get("section_number") or "").replace(" ", "") == num.replace(" ", ""):
                return s
        pytest.fail(f"未找到章节 {num}")

    def test_paid_in_capital_58_has_7_columns(self):
        s = self._find("八、58")
        tbl = s["tables"][0]
        assert len(tbl["columns"]) == 7
        groups = {c.get("group") for c in tbl["columns"] if c.get("group")}
        assert "年初余额" in groups
        assert "期末余额" in groups

    def test_other_equity_59_has_9_columns(self):
        s = self._find("八、59")
        tbl = s["tables"][0]
        assert len(tbl["columns"]) == 9

    def test_retained_earnings_63_has_3_columns(self):
        s = self._find("八、63")
        tbl = s["tables"][0]
        assert len(tbl["columns"]) == 3
        # 无 …… 占位行
        for row in tbl.get("rows") or []:
            assert row.get("label") != "……"

    def test_oci_79_has_7_columns(self):
        s = self._find("八、79")
        tbl = s["tables"][0]
        assert len(tbl["columns"]) == 7
        groups = {c.get("group") for c in tbl["columns"] if c.get("group")}
        assert "本期发生额" in groups
        assert "上期发生额" in groups

    def test_general_risk_94_exists(self):
        """Property 7：八、94 一般风险准备章节已新建。"""
        s = self._find("八、94")
        assert s["section_title"] == "一般风险准备"
        assert len(s["tables"]) >= 1
        assert s["tables"][0]["name"] == "一般风险准备"
        assert len(s["tables"][0]["columns"]) == 5

    def test_no_header_label_rows(self):
        nums = ["八、58", "八、59", "八、63", "八、79", "八、94"]
        for num in nums:
            s = self._find(num)
            for t in s.get("tables") or []:
                for row in t.get("rows") or []:
                    assert row.get("row_type") != "header_label", (
                        f"{num} {t.get('name')} 残留 header_label 行"
                    )

    def test_aligned_by_stamp(self):
        """所有改造章节须有 _aligned_by 标记。"""
        nums = ["八、58", "八、59", "八、63", "八、79", "八、94"]
        for num in nums:
            s = self._find(num)
            assert s.get("_aligned_by") == "fix_note_m_equity_structure", (
                f"{num} 缺 _aligned_by 标记"
            )
