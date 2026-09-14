"""附注「营业收入」章节（上市 五、62 / 国企 八、64）结构守卫。

三向比对：openpyxl 直读源 xlsx 两级表头 ↔ note_template headers ↔ 同步 columns。
含归一函数 + 反向自检 + guidance 禁 markdown。

Validates: Requirements 9.1, 9.9
spec: d4-four-table-extraction-and-disclosure-alignment
"""
from __future__ import annotations

import functools
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
_FIX_SCRIPT = _BACKEND / "scripts" / "fix" / "fix_note_d4_revenue_structure.py"
_SRC_XLSX = (
    _BACKEND / "wp_templates" / "D"
    / "D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx"
)
_DATA_DIR = _BACKEND / "data"
_LISTED_PATH = _DATA_DIR / "note_template_listed.json"
_SOE_PATH = _DATA_DIR / "note_template_soe.json"

LISTED_SECTION = "五、62"
SOE_SECTION = "八、64"
LISTED_SHEET = "附注披露信息（上市公司）"
SOE_SHEET = "附注披露信息（国企）"


# ─── 加载修订脚本模块 ─────────────────────────────────────────────────────────


def _load_fix():
    spec = importlib.util.spec_from_file_location("_fix_d4_struct", _FIX_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FIX = _load_fix()

VARIANTS = ["listed", "soe"]


# ─── 归一函数 ─────────────────────────────────────────────────────────────────


def _norm(s: str | None) -> str:
    """源 xlsx 表头文本归一：去空格/制表/零宽字符，统一「项 目」→「项目」。

    处理格式差异：
    - 「项 目」（中间有全角/半角空格）→「项目」
    - 「年 度」→「年度」
    - 「合 计」→「合计」
    - 前后空白
    """
    if s is None:
        return ""
    out = str(s).strip()
    # 去掉任何 Unicode 空白/零宽字符（\u200b, \xa0, etc.）中间的
    out = re.sub(r"[\s\u200b\u00a0]+", "", out)
    return out


# ─── 读源 xlsx ────────────────────────────────────────────────────────────────


@functools.lru_cache(maxsize=1)
def _load_xlsx():
    """加载源 xlsx，返回 workbook。"""
    openpyxl = pytest.importorskip("openpyxl")
    return openpyxl.load_workbook(_SRC_XLSX, data_only=True, read_only=True)


def _xlsx_sheet(variant: str):
    wb = _load_xlsx()
    name = LISTED_SHEET if variant == "listed" else SOE_SHEET
    return wb[name]


@functools.lru_cache(maxsize=4)
def _xlsx_headers(variant: str) -> list[list[str]]:
    """读源 xlsx 指定 sheet 的所有非空行，返回列表 [row_values...]。"""
    ws = _xlsx_sheet(variant)
    rows = []
    for row in ws.iter_rows(values_only=True):
        cells = [_norm(str(c)) if c is not None else "" for c in row]
        if any(cells):
            rows.append(cells)
    return rows


def _xlsx_find_row(variant: str, col_a_contains: str) -> list[str] | None:
    """在 A 列搜索含指定文本的行，返回归一后的整行值。"""
    for row in _xlsx_headers(variant):
        if row and col_a_contains in row[0]:
            return row
    return None


# ─── 读 note_template ─────────────────────────────────────────────────────────


def _section(variant: str) -> dict:
    path = _LISTED_PATH if variant == "listed" else _SOE_PATH
    sec_num = LISTED_SECTION if variant == "listed" else SOE_SECTION
    doc = json.loads(path.read_text(encoding="utf-8"))
    for sec in doc.get("sections", []):
        if str(sec.get("section_number", "")) == sec_num:
            return sec
    pytest.fail(f"未找到章节 {sec_num}")


def _tables(variant: str) -> list[dict]:
    return _section(variant).get("tables") or []


# ─── 反向自检：归一函数确实在做事 ─────────────────────────────────────────────


class TestNormalizationSelfCheck:
    """反向自检：归一函数对已知输入产生预期输出，不是空操作。"""

    def test_norm_removes_spaces(self):
        assert _norm("项 目") == "项目"
        assert _norm("年 度") == "年度"
        assert _norm("合 计") == "合计"
        assert _norm("本期发生额") == "本期发生额"

    def test_norm_strips_whitespace(self):
        assert _norm("  收入  ") == "收入"
        assert _norm("\t成本\t") == "成本"

    def test_norm_handles_none(self):
        assert _norm(None) == ""

    def test_norm_changes_known_source_value(self):
        """源 xlsx 的「项 目」确实需要归一才能与模板的「项目」比对。"""
        # 源模板 A 列第一格通常是「项 目」（带空格），模板是「项目」
        assert _norm("项 目") != "项 目"  # 确实改了原始值
        assert _norm("项 目") == _norm("项目")  # 归一后相等


# ─── 反向自检：openpyxl 确实读到非空数据 ─────────────────────────────────────


class TestXlsxReadSelfCheck:
    """反向自检：源 xlsx 读取确实取到含数据的表头行。"""

    def test_listed_sheet_has_data(self):
        rows = _xlsx_headers("listed")
        assert len(rows) > 10, f"上市 sheet 只读到 {len(rows)} 行"

    def test_soe_sheet_has_data(self):
        rows = _xlsx_headers("soe")
        assert len(rows) > 10, f"国企 sheet 只读到 {len(rows)} 行"

    def test_listed_has_revenue_header(self):
        """上市 sheet 必含「本期发生额」文本（（1）~（3）（8）的父表头）。"""
        all_text = " ".join(
            cell for row in _xlsx_headers("listed") for cell in row if cell
        )
        assert "本期发生额" in all_text

    def test_soe_has_revenue_header(self):
        """国企 sheet 必含「本期发生额」文本。"""
        all_text = " ".join(
            cell for row in _xlsx_headers("soe") for cell in row if cell
        )
        assert "本期发生额" in all_text


# ─── 三向比对：源 xlsx 表头 vs note_template headers vs columns ───────────────


@pytest.mark.parametrize("variant", VARIANTS)
def test_table_count(variant: str):
    """上市 6 表，国企 5 表（无试运行销售收入）。"""
    expected = FIX.EXPECTED_LISTED if variant == "listed" else FIX.EXPECTED_SOE
    tables = _tables(variant)
    names = [str(t.get("name", "")) for t in tables]
    assert len(tables) == len(expected), f"{variant} 表数 {len(tables)} ≠ 期望 {len(expected)}"
    assert sorted(names) == sorted(expected), f"{variant} 表名漂移"


@pytest.mark.parametrize("variant", VARIANTS)
def test_table_names_match_source_xlsx(variant: str):
    """模板表名应可在源 xlsx A 列内容中找到对应。"""
    expected_names = FIX.EXPECTED_LISTED if variant == "listed" else FIX.EXPECTED_SOE
    all_text = " ".join(
        cell for row in _xlsx_headers(variant) for cell in row if cell
    )
    # 至少核心表名（（1）主表、（2）行业、（3）地区）应在源 xlsx 出现
    for name in expected_names[:3]:
        # 归一后做包含查找（源 xlsx 可能有小节编号前缀）
        norm_name = _norm(name)
        assert norm_name in _norm(all_text), (
            f"{variant} 表名「{name}」在源 xlsx 找不到"
        )


@pytest.mark.parametrize("variant", VARIANTS)
def test_two_period_leaf_headers_in_source(variant: str):
    """源 xlsx 的两级表头叶子列「收入/成本」在模板 columns 的 label 中也出现。"""
    tables = _tables(variant)
    # （1）主表的两级叶子列应包含「收入」「成本」
    main_table = tables[0]
    cols = main_table.get("columns") or []
    labels = [_norm(str(c.get("label", ""))) for c in cols]
    assert "收入" in labels, f"{variant} 主表 columns 缺「收入」列"
    assert "成本" in labels, f"{variant} 主表 columns 缺「成本」列"


@pytest.mark.parametrize("variant", VARIANTS)
def test_columns_count_matches_headers(variant: str):
    """每张表的 columns 数 == headers 数。"""
    for tbl in _tables(variant):
        name = tbl.get("name", "")
        cols = tbl.get("columns") or []
        headers = tbl.get("headers") or []
        assert len(cols) == len(headers), (
            f"{variant}/{name}: columns={len(cols)} ≠ headers={len(headers)}"
        )


@pytest.mark.parametrize("variant", VARIANTS)
def test_columns_label_matches_headers(variant: str):
    """columns 的 label 与 headers 逐位一致（归一后）。"""
    for tbl in _tables(variant):
        name = tbl.get("name", "")
        cols = tbl.get("columns") or []
        headers = tbl.get("headers") or []
        col_labels = [_norm(str(c.get("label", ""))) for c in cols]
        header_norms = [_norm(str(h)) for h in headers]
        assert col_labels == header_norms, (
            f"{variant}/{name}: columns.label ≠ headers（归一后）"
        )


# ─── Property 12: 两版表名不得统一（（2）（4）表名两版不同）──────────────────


def test_segment_table_names_differ_between_variants():
    """（2）按行业表名：上市「营业收入、营业成本按行业（或产品类型）划分」vs 国企「按行业（或产品类型）划分」。"""
    listed_names = {str(t.get("name", "")) for t in _tables("listed")}
    soe_names = {str(t.get("name", "")) for t in _tables("soe")}
    assert FIX.T_SEGMENT_LISTED in listed_names
    assert FIX.T_SEGMENT_SOE in soe_names
    assert FIX.T_SEGMENT_LISTED != FIX.T_SEGMENT_SOE, "（2）表名两版不应相同"


def test_decompose_table_names_differ_between_variants():
    """（4）分解信息表名：上市「营业收入、营业成本按分解信息」vs 国企「营业收入分解信息」。"""
    listed_names = {str(t.get("name", "")) for t in _tables("listed")}
    soe_names = {str(t.get("name", "")) for t in _tables("soe")}
    assert FIX.T_DECOMPOSE_LISTED in listed_names
    assert FIX.T_DECOMPOSE_SOE in soe_names
    assert FIX.T_DECOMPOSE_LISTED != FIX.T_DECOMPOSE_SOE, "（4）表名两版不应相同"


# ─── 列结构完备性 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("variant", VARIANTS)
def test_all_tables_have_columns(variant: str):
    """所有表都已补 columns（不为 0/空）。"""
    for tbl in _tables(variant):
        name = tbl.get("name", "")
        cols = tbl.get("columns") or []
        assert len(cols) > 0, f"{variant}/{name} 缺 columns"


@pytest.mark.parametrize("variant", VARIANTS)
def test_flat_or_group_declared(variant: str):
    """每张表必须在 flat 与 group 之间恰好表态其一。"""
    for tbl in _tables(variant):
        name = tbl.get("name", "")
        cols = tbl.get("columns") or []
        has_flat = any(c.get("flat") for c in cols)
        has_group = any(c.get("group") for c in cols)
        assert has_flat or has_group, f"{variant}/{name} 未表态 flat/group"


@pytest.mark.parametrize("variant", VARIANTS)
def test_no_header_label_rows(variant: str):
    """所有表不得残留 header_label 假数据行。"""
    for tbl in _tables(variant):
        name = tbl.get("name", "")
        for i, row in enumerate(tbl.get("rows") or []):
            assert str(row.get("row_type", "")) != "header_label", (
                f"{variant}/{name} 第 {i} 行残留 header_label"
            )


# ─── guidance 禁 markdown ─────────────────────────────────────────────────────


@pytest.mark.parametrize("variant", VARIANTS)
def test_guidance_no_markdown_bold(variant: str):
    """所有 guidance 不含 markdown 粗体标记 `**`。

    guidance 是纯文本渲染（TAB 提示 + Word 导出都不解析 markdown）。
    平台级 fix_note_bold_markers.py 会剥离 **，循环脚本写回就互相打架。
    """
    for tbl in _tables(variant):
        name = tbl.get("name", "")
        g = str(tbl.get("guidance") or "")
        assert "**" not in g, f"{variant}/{name} guidance 残留 markdown 粗体 **"


@pytest.mark.parametrize("variant", VARIANTS)
def test_guidance_present(variant: str):
    """所有表应有非空 guidance。"""
    for tbl in _tables(variant):
        name = tbl.get("name", "")
        g = str(tbl.get("guidance") or "").strip()
        assert len(g) > 0, f"{variant}/{name} guidance 为空"


# ─── text_sections 标题可识别 ─────────────────────────────────────────────────


@pytest.mark.parametrize("variant", VARIANTS)
def test_text_sections_titles_identifiable(variant: str):
    """以 #### 开头的 text_sections 段应能被 _is_table_title_paragraph 识别。"""
    sec = _section(variant)
    text_secs = sec.get("text_sections") or []
    title_secs = [s for s in text_secs if str(s).startswith("####")]
    assert len(title_secs) >= 3, f"{variant} 标题化段落过少（{len(title_secs)}）"


# ─── --check 无欠账 ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("variant", VARIANTS)
def test_check_passes(variant: str):
    """修订脚本的 --check 模式应报告 0 项欠账。"""
    _changes, warnings, errs = FIX._runner(variant, dry_run=True, check=True)
    assert not errs, f"{variant} --check 有欠账：{errs}"


def test_fix_script_check_exit_zero():
    """运行 fix_note_d4_revenue_structure.py --check 应以 exit 0 退出。"""
    result = subprocess.run(
        [sys.executable, str(_FIX_SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=str(_BACKEND.parent),
    )
    assert result.returncode == 0, (
        f"--check 退出码 {result.returncode}\nstdout: {result.stdout[:500]}\n"
        f"stderr: {result.stderr[:500]}"
    )


# ─── aligned_by 标记 ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("variant", VARIANTS)
def test_aligned_by_stamp(variant: str):
    sec = _section(variant)
    assert sec.get("_aligned_by") == FIX.ALIGNED_BY


# ─── 源 xlsx 两级表头三向比对（核心 Property 17）─────────────────────────────


def test_source_xlsx_main_table_two_level_headers_listed():
    """上市（1）主表：源 xlsx 两级表头叶子「收入/成本」×2 与模板 columns 一致。"""
    ws = _xlsx_sheet("listed")
    # 源模板（1）主表表头通常在前几行的第二行
    # 扫描找到含「收入」「成本」且在同一行的叶子列
    found_leaf_row = False
    for row_idx in range(1, 30):
        cells = [_norm(str(ws.cell(row_idx, c).value)) for c in range(1, 10)]
        if "收入" in cells and "成本" in cells:
            found_leaf_row = True
            # 应有两对「收入/成本」（本期 + 上期）
            assert cells.count("收入") >= 2, f"行{row_idx} 只有 {cells.count('收入')} 个「收入」"
            assert cells.count("成本") >= 2, f"行{row_idx} 只有 {cells.count('成本')} 个「成本」"
            break
    assert found_leaf_row, "上市 sheet 未找到含「收入」「成本」的两级表头叶子行"

    # 模板的（1）主表 columns 也应有对应
    listed_tables = _tables("listed")
    main_cols = listed_tables[0].get("columns") or []
    col_labels = [_norm(str(c.get("label", ""))) for c in main_cols]
    assert col_labels.count("收入") >= 2
    assert col_labels.count("成本") >= 2


def test_source_xlsx_main_table_two_level_headers_soe():
    """国企（1）主表：源 xlsx 两级表头叶子「收入/成本」×2 与模板 columns 一致。"""
    ws = _xlsx_sheet("soe")
    found_leaf_row = False
    for row_idx in range(1, 30):
        cells = [_norm(str(ws.cell(row_idx, c).value)) for c in range(1, 10)]
        if "收入" in cells and "成本" in cells:
            found_leaf_row = True
            assert cells.count("收入") >= 2
            assert cells.count("成本") >= 2
            break
    assert found_leaf_row, "国企 sheet 未找到含「收入」「成本」的两级表头叶子行"

    soe_tables = _tables("soe")
    main_cols = soe_tables[0].get("columns") or []
    col_labels = [_norm(str(c.get("label", ""))) for c in main_cols]
    assert col_labels.count("收入") >= 2
    assert col_labels.count("成本") >= 2


def test_source_xlsx_parent_headers_present():
    """源 xlsx 应含「本期发生额」「上期发生额」父表头（三向比对的源侧锚点）。"""
    for variant in VARIANTS:
        ws = _xlsx_sheet(variant)
        found_current = False
        found_prior = False
        for row_idx in range(1, 30):
            for col_idx in range(1, 12):
                val = _norm(str(ws.cell(row_idx, col_idx).value or ""))
                if "本期发生额" in val:
                    found_current = True
                if "上期发生额" in val:
                    found_prior = True
        assert found_current, f"{variant} 源 xlsx 未找到「本期发生额」"
        assert found_prior, f"{variant} 源 xlsx 未找到「上期发生额」"


def test_source_xlsx_parent_headers_match_template_groups():
    """模板 columns 的 group 名应与源 xlsx 父表头一致（本期发生额/上期发生额）。"""
    for variant in VARIANTS:
        tables = _tables(variant)
        # （1）主表应有 group 包含「本期发生额」「上期发生额」
        main_cols = tables[0].get("columns") or []
        groups = {_norm(str(c.get("group", ""))) for c in main_cols if c.get("group")}
        assert "本期发生额" in groups, f"{variant} 主表 columns 缺 group「本期发生额」"
        assert "上期发生额" in groups, f"{variant} 主表 columns 缺 group「上期发生额」"


# ─── 试运行销售收入仅上市（Property 验证）────────────────────────────────────


def test_trial_run_table_only_in_listed():
    """（8）试运行销售收入只在上市版，国企不得有。"""
    listed_names = [str(t.get("name", "")) for t in _tables("listed")]
    soe_names = [str(t.get("name", "")) for t in _tables("soe")]
    assert FIX.T_TRIAL_RUN in listed_names, "上市缺试运行销售收入表"
    assert FIX.T_TRIAL_RUN not in soe_names, "国企不应有试运行销售收入表"


# ─── 反向自检：validate_section 能检出结构缺陷 ─────────────────────────────────


def test_reverse_self_check_validate_catches_missing_columns():
    """validate_section 能检出缺 columns 的表（防守卫空转）。"""
    sys.path.insert(0, str(_BACKEND / "scripts" / "fix"))
    from _note_structure_kit import validate_section

    broken = {
        "tables": [{
            "name": "营业收入和营业成本",
            "headers": ["项目", "本期发生额"],
            "rows": [{"label": "项目", "row_type": "header_label"}],
            "guidance": "测试用",
        }],
    }
    errs = validate_section(broken, ["营业收入和营业成本"])
    assert any("缺 columns" in e for e in errs), f"validate 未检出缺 columns: {errs}"
    assert any("header_label" in e for e in errs), f"validate 未检出 header_label: {errs}"
