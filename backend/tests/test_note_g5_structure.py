"""附注 G5 长期应收款章节结构守卫（§五、16 上市 / §八、17 国企）。

锁定模板结构完整性：
1. 上市 §五、16 共 8 张表（性质/坏账/单项×2/组合骨架/变动/核销/重要核销），
   国企 §八、17 共 3 张表（性质/终止确认/继续涉入）
2. 所有表 `columns` 非空、`guidance` 非空
3. 表名与前端 `G5_LISTED_SUBTABLE` / `G5_SOE_SUBTABLE` 常量逐字一致
4. 性质表有两级表头（期末余额/上年年末余额 for listed, 期末余额/期初余额 for soe）
5. 组合骨架表 `组合计提项目：XXX` 存在
6. 变动/核销/核销明细/终止确认/继续涉入表标签列标 flat

含 openpyxl 直读源 xlsx 交叉比对 + 反向自检。

spec: g5-four-table-extraction-and-disclosure-alignment (Task 5.1)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    import openpyxl
except ImportError:
    openpyxl = None  # type: ignore[assignment]

_ROOT = Path(__file__).resolve().parent.parent
_LISTED_JSON = _ROOT / "data" / "note_template_listed.json"
_SOE_JSON = _ROOT / "data" / "note_template_soe.json"
_SRC_XLSX = _ROOT / "wp_templates" / "G" / "G5 长期应收款.xlsx"

# ── 权威期望值（取自前端 g5NoteSectionMap.ts 常量） ─────────────────────────────

G5_LISTED_TABLE_NAMES = [
    "长期应收款按性质披露",
    "坏账准备计提情况",
    "按单项计提坏账准备",
    "按单项计提坏账准备（续：上年年末余额）",
    "组合计提项目：XXX",
    "本期计提、收回或转回的坏账准备情况",
    "本期实际核销的长期应收款",
    "重要的长期应收款核销情况（逐项披露）",
]

G5_SOE_TABLE_NAMES = [
    "长期应收款按性质披露",
    "终止确认的长期应收款",
    "转移长期应收款且继续涉入形成的资产、负债的金额",
]

# flat 表（标签列须有 flat=True）
_FLAT_TABLES_LISTED = {
    "本期计提、收回或转回的坏账准备情况",
    "本期实际核销的长期应收款",
    "重要的长期应收款核销情况（逐项披露）",
}

_FLAT_TABLES_SOE = {
    "终止确认的长期应收款",
    "转移长期应收款且继续涉入形成的资产、负债的金额",
}

# 两级表头表（应有 _column_groups 或 columns 中有 group）
_TWO_LEVEL_TABLES_LISTED = {
    "长期应收款按性质披露",
    "坏账准备计提情况",
    "按单项计提坏账准备",
    "按单项计提坏账准备（续：上年年末余额）",
    "组合计提项目：XXX",
}

_TWO_LEVEL_TABLES_SOE = {
    "长期应收款按性质披露",
}


# ── Helper ──────────────────────────────────────────────────────────────────────

def _load_section(variant: str) -> dict:
    """加载附注模板 JSON 中 G5 所在章节。"""
    if variant == "listed":
        path, sec_num = _LISTED_JSON, "五、16"
    else:
        path, sec_num = _SOE_JSON, "八、17"
    doc = json.loads(path.read_text(encoding="utf-8"))
    for s in doc.get("sections", []):
        if str(s.get("section_number")) == sec_num:
            return s
    raise AssertionError(f"模板中未找到 {sec_num}")


# ── 测试 ────────────────────────────────────────────────────────────────────────

class TestListedSection:
    """上市 §五、16 结构守卫。"""

    @pytest.fixture(autouse=True)
    def _section(self):
        self.sec = _load_section("listed")
        self.tables = self.sec.get("tables") or []
        self.by_name = {str(t.get("name")): t for t in self.tables}

    def test_table_count(self):
        assert len(self.tables) == 8, f"期望 8 张表，实得 {len(self.tables)}"

    def test_table_names_match_constants(self):
        names = [str(t.get("name")) for t in self.tables]
        assert names == G5_LISTED_TABLE_NAMES, f"表名序列漂移: {names}"

    def test_all_tables_have_columns(self):
        for t in self.tables:
            cols = t.get("columns") or []
            assert len(cols) > 0, f"表 '{t.get('name')}' 缺 columns"

    def test_all_tables_have_guidance(self):
        for t in self.tables:
            guidance = (t.get("guidance") or "").strip()
            assert guidance, f"表 '{t.get('name')}' 缺 guidance"

    def test_nature_table_two_level_header(self):
        """性质表应有两级表头（期末余额 / 上年年末余额）。"""
        tbl = self.by_name["长期应收款按性质披露"]
        cols = tbl.get("columns") or []
        # 数据列（非标签列）应有 group
        data_cols = [c for c in cols if not c.get("is_label")]
        groups = {c.get("group") for c in data_cols if c.get("group")}
        assert "期末余额" in groups or "上年年末余额" in groups, (
            f"性质表缺两级分组，groups={groups}"
        )

    def test_portfolio_seed_exists(self):
        """组合骨架表名含前缀 `组合计提项目：`。"""
        assert "组合计提项目：XXX" in self.by_name, "缺组合骨架表"

    def test_flat_tables_have_flat_label_column(self):
        """变动/核销系列表的标签列须标 flat。"""
        for name in _FLAT_TABLES_LISTED:
            tbl = self.by_name.get(name)
            if tbl is None:
                continue
            cols = tbl.get("columns") or []
            label_col = next((c for c in cols if c.get("is_label")), None)
            assert label_col and label_col.get("flat"), (
                f"表 '{name}' 标签列未标 flat"
            )

    def test_two_level_tables_have_groups(self):
        """两级表头的表数据列应有 group 或 _column_groups。"""
        for name in _TWO_LEVEL_TABLES_LISTED:
            tbl = self.by_name.get(name)
            if tbl is None:
                continue
            cols = tbl.get("columns") or []
            data_cols = [c for c in cols if not c.get("is_label")]
            has_group = any(c.get("group") for c in data_cols)
            has_column_groups = bool(tbl.get("_column_groups"))
            assert has_group or has_column_groups, (
                f"表 '{name}' 两级表头未声明 group 或 _column_groups"
            )

    def test_no_header_label_fake_rows(self):
        """无残留 header_label 假数据行。"""
        for t in self.tables:
            rows = t.get("rows") or []
            fakes = [r for r in rows if r.get("row_type") == "header_label"]
            assert not fakes, f"表 '{t.get('name')}' 残留 header_label"


class TestSoeSection:
    """国企 §八、17 结构守卫。"""

    @pytest.fixture(autouse=True)
    def _section(self):
        self.sec = _load_section("soe")
        self.tables = self.sec.get("tables") or []
        self.by_name = {str(t.get("name")): t for t in self.tables}

    def test_table_count(self):
        assert len(self.tables) == 3, f"期望 3 张表，实得 {len(self.tables)}"

    def test_table_names_match_constants(self):
        names = [str(t.get("name")) for t in self.tables]
        assert names == G5_SOE_TABLE_NAMES, f"表名序列漂移: {names}"

    def test_all_tables_have_columns(self):
        for t in self.tables:
            cols = t.get("columns") or []
            assert len(cols) > 0, f"表 '{t.get('name')}' 缺 columns"

    def test_all_tables_have_guidance(self):
        for t in self.tables:
            guidance = (t.get("guidance") or "").strip()
            assert guidance, f"表 '{t.get('name')}' 缺 guidance"

    def test_nature_table_two_level_header(self):
        """国企性质表应有两级表头（期末余额 / 期初余额）。"""
        tbl = self.by_name["长期应收款按性质披露"]
        cols = tbl.get("columns") or []
        data_cols = [c for c in cols if not c.get("is_label")]
        groups = {c.get("group") for c in data_cols if c.get("group")}
        assert "期末余额" in groups or "期初余额" in groups, (
            f"性质表缺两级分组，groups={groups}"
        )

    def test_flat_tables_have_flat_label_column(self):
        """终止确认/继续涉入表标签列须标 flat。"""
        for name in _FLAT_TABLES_SOE:
            tbl = self.by_name.get(name)
            if tbl is None:
                continue
            cols = tbl.get("columns") or []
            label_col = next((c for c in cols if c.get("is_label")), None)
            assert label_col and label_col.get("flat"), (
                f"表 '{name}' 标签列未标 flat"
            )

    def test_no_header_label_fake_rows(self):
        """无残留 header_label 假数据行。"""
        for t in self.tables:
            rows = t.get("rows") or []
            fakes = [r for r in rows if r.get("row_type") == "header_label"]
            assert not fakes, f"表 '{t.get('name')}' 残留 header_label"


class TestSourceXlsxCrossCheck:
    """openpyxl 直读源 xlsx 交叉比对。"""

    @pytest.fixture(autouse=True)
    def _check_openpyxl(self):
        if openpyxl is None:
            pytest.skip("openpyxl not installed")
        if not _SRC_XLSX.exists():
            pytest.skip("源 xlsx 不存在")
        # 跳过锁文件
        lock = _SRC_XLSX.parent / f"~${_SRC_XLSX.name}"
        if lock.exists():
            pytest.skip("源 xlsx 有锁文件（WPS/Excel 打开中）")

    def test_xlsx_has_disclosure_sheets(self):
        """源 xlsx 含上市和国企披露 sheet。"""
        wb = openpyxl.load_workbook(_SRC_XLSX, data_only=True, read_only=True)
        names = wb.sheetnames
        wb.close()
        # G5 源模板使用「国企」短名
        soe_found = any("国企" in n for n in names)
        listed_found = any("上市" in n for n in names)
        assert soe_found, f"源 xlsx 缺国企披露 sheet: {names}"
        assert listed_found, f"源 xlsx 缺上市披露 sheet: {names}"

    def test_soe_nature_table_columns(self):
        """国企性质表：行 7 表头应含 期末余额 / 期初余额 相关字样。"""
        wb = openpyxl.load_workbook(_SRC_XLSX, data_only=True, read_only=True)
        soe_sheet_name = next(
            (n for n in wb.sheetnames if "国企" in n), None
        )
        assert soe_sheet_name, "未找到国企 sheet"
        ws = wb[soe_sheet_name]
        # 读前 10 行前 10 列找表头
        header_values = []
        for row in ws.iter_rows(min_row=1, max_row=15, max_col=10, values_only=True):
            header_values.append(row)
        wb.close()
        # 至少找到「期末余额」或「期初余额」
        flat_text = " ".join(
            str(cell) for row in header_values for cell in row if cell
        )
        assert "期末" in flat_text or "期初" in flat_text, (
            f"国企 sheet 前 15 行未见期末/期初表头"
        )


class TestReverseSelfCheck:
    """反向自检：确保测试本身读到真实数据而非空壳。"""

    def test_listed_section_is_not_empty(self):
        sec = _load_section("listed")
        tables = sec.get("tables") or []
        assert len(tables) > 0, "listed 章节 tables 为空，测试可能空转"

    def test_soe_section_is_not_empty(self):
        sec = _load_section("soe")
        tables = sec.get("tables") or []
        assert len(tables) > 0, "soe 章节 tables 为空，测试可能空转"

    def test_listed_first_table_has_real_columns(self):
        sec = _load_section("listed")
        tables = sec.get("tables") or []
        cols = tables[0].get("columns") or []
        # 性质表应至少 5 列（label + 3*期末 + 3*上年年末 or similar）
        assert len(cols) >= 5, f"性质表只有 {len(cols)} 列，期望 ≥5"

    def test_soe_nature_table_has_real_columns(self):
        sec = _load_section("soe")
        tables = sec.get("tables") or []
        cols = tables[0].get("columns") or []
        assert len(cols) >= 5, f"国企性质表只有 {len(cols)} 列，期望 ≥5"

    def test_template_json_files_exist(self):
        assert _LISTED_JSON.exists(), f"{_LISTED_JSON} 不存在"
        assert _SOE_JSON.exists(), f"{_SOE_JSON} 不存在"
