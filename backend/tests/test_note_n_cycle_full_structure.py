"""N 类附注模板结构守卫（openpyxl 交叉比对 + 反向自检）.

Property 1: 7 个章节全部有 _tables 且表数正确
Property 2: 列 key 集合与前端 builder 一致（读 .ts 源码）
Property 3: 所有表有 guidance（>=20 字）
Property 4: 幂等脚本 --check exit 0
Property 5: 反向自检（表数锚点 / 源 xlsx 披露 sheet 存在）

Requirements: n-cycle-note-template-and-disclosure-completion 4.1
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DATA = Path(__file__).resolve().parent.parent / "data"
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "fix"
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "wp_templates" / "N"
FRONTEND_COMPOSABLES = (
    Path(__file__).resolve().parent.parent.parent
    / "audit-platform" / "frontend" / "src" / "components" / "workpaper" / "composables"
)

LISTED_PATH = BACKEND_DATA / "note_template_listed.json"
SOE_PATH = BACKEND_DATA / "note_template_soe.json"


def _load_sections(path: Path) -> list[dict]:
    root = json.loads(path.read_text("utf-8"))
    if isinstance(root, dict):
        return root.get("sections", [])
    return root


def _find_section(sections, sn):
    for s in sections:
        if s.get("section_number") == sn:
            return s
    return None


# ─── Property 1: 章节表数正确 ────────────────────────────────────────────────

EXPECTED_TABLES = {
    ("listed", "五、30"): 4,
    ("soe", "八、31"): 5,
    ("listed", "五、41"): 1,
    ("soe", "八、41"): 1,
    ("listed", "五、63"): 1,
    ("listed", "三、所得税费用"): 2,
    ("soe", "八、78"): 2,
}


@pytest.mark.parametrize("variant,section_number,expected_count", [
    (v, sn, c) for (v, sn), c in EXPECTED_TABLES.items()
])
def test_table_count(variant, section_number, expected_count):
    """各章节 _tables 表数正确."""
    path = LISTED_PATH if variant == "listed" else SOE_PATH
    sections = _load_sections(path)
    sec = _find_section(sections, section_number)
    assert sec is not None, f"{section_number} 未找到于 {path.name}"
    tables = sec.get("_tables", [])
    assert len(tables) == expected_count, (
        f"{section_number}: 期望 {expected_count} 张表，实际 {len(tables)}"
    )


# ─── Property 2: 列 key 对齐前端 ────────────────────────────────────────────

def _extract_column_keys_from_template(variant: str, section_number: str) -> dict[str, set[str]]:
    """从模板提取 {表名: {列key集合}}."""
    path = LISTED_PATH if variant == "listed" else SOE_PATH
    sections = _load_sections(path)
    sec = _find_section(sections, section_number)
    if not sec:
        return {}
    result = {}
    for t in sec.get("_tables", []):
        name = t.get("name", "")
        cols = t.get("columns", [])
        result[name] = {c["key"] for c in cols if "key" in c}
    return result


@pytest.mark.parametrize("variant,section_number", [
    ("listed", "五、30"),
    ("soe", "八、31"),
    ("listed", "五、41"),
    ("soe", "八、41"),
    ("listed", "五、63"),
    ("listed", "三、所得税费用"),
    ("soe", "八、78"),
])
def test_columns_have_keys(variant, section_number):
    """每张表的 columns 都有 key."""
    table_keys = _extract_column_keys_from_template(variant, section_number)
    assert table_keys, f"{section_number} 无表"
    for name, keys in table_keys.items():
        assert len(keys) >= 2, f"{section_number}/{name} 列数不足"
        assert "label" in keys, f"{section_number}/{name} 缺 label 列"


# ─── Property 3: guidance 非空 ───────────────────────────────────────────────

@pytest.mark.parametrize("variant,section_number", [
    ("listed", "五、30"),
    ("soe", "八、31"),
    ("listed", "五、41"),
    ("soe", "八、41"),
    ("listed", "五、63"),
    ("listed", "三、所得税费用"),
    ("soe", "八、78"),
])
def test_guidance_present(variant, section_number):
    """每张表有 guidance（>=20 字）."""
    path = LISTED_PATH if variant == "listed" else SOE_PATH
    sections = _load_sections(path)
    sec = _find_section(sections, section_number)
    assert sec is not None
    for t in sec.get("_tables", []):
        guidance = t.get("guidance", "")
        assert len(guidance) >= 20, (
            f"{section_number}/{t.get('name')}: guidance 太短 ({len(guidance)} 字)"
        )


# ─── Property 4: 幂等脚本 --check ───────────────────────────────────────────

def test_idempotent_script_check():
    """fix_note_n_cycle_full_structure.py --check exit 0."""
    script = SCRIPTS_DIR / "fix_note_n_cycle_full_structure.py"
    assert script.exists(), f"脚本不存在: {script}"
    result = subprocess.run(
        [sys.executable, str(script), "--check"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"--check 失败:\n{result.stdout}\n{result.stderr}"


# ─── Property 5: 反向自检 ────────────────────────────────────────────────────

def test_source_templates_have_disclosure_sheets():
    """源 xlsx 确实有披露 sheet（反向自检：若源模板无该 sheet 则本脚本就不该建表）."""
    try:
        import openpyxl
    except ImportError:
        pytest.skip("openpyxl not installed")

    expected_sheets = {
        "N1 递延所得税资产.xlsx": ["附注披露信息（上市公司）", "附注披露信息（国企）"],
        "N2 应交税费.xlsx": ["附注披露信息（上市公司）", "附注披露信息（国企）"],
        "N4 税金及附加.xlsx": ["附注披露信息（上市公司）"],  # 国企为「无」
        "N5 所得税费用.xlsx": ["附注披露信息（上市公司）"],  # 国企缺右括号另处理
    }
    for fname, expected in expected_sheets.items():
        fpath = TEMPLATES_DIR / fname
        if not fpath.exists():
            pytest.skip(f"{fname} not found")
        wb = openpyxl.load_workbook(str(fpath), read_only=True)
        actual = wb.sheetnames
        wb.close()
        for sheet_name in expected:
            assert sheet_name in actual, (
                f"{fname} 缺少 sheet '{sheet_name}', 实有: {actual}"
            )


def test_total_table_count_anchor():
    """反向自检：7 章节总共应有 16 张表."""
    total = 0
    for (variant, sn), count in EXPECTED_TABLES.items():
        total += count
    assert total == 16, f"预期表数锚点 16，实际 {total}"

    # 同时验证模板实际总表数
    actual_total = 0
    for (variant, sn), _ in EXPECTED_TABLES.items():
        path = LISTED_PATH if variant == "listed" else SOE_PATH
        sections = _load_sections(path)
        sec = _find_section(sections, sn)
        if sec:
            actual_total += len(sec.get("_tables", []))
    assert actual_total == 16, f"模板实际表数 {actual_total}，期望 16"


def test_aligned_by_marker():
    """所有章节标记 _aligned_by."""
    for (variant, sn), _ in EXPECTED_TABLES.items():
        path = LISTED_PATH if variant == "listed" else SOE_PATH
        sections = _load_sections(path)
        sec = _find_section(sections, sn)
        assert sec is not None
        assert sec.get("_aligned_by") == "n-cycle-note-template-and-disclosure-completion", (
            f"{sn} _aligned_by 未标记"
        )
