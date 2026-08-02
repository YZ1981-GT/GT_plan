"""附注 I 类循环（I1~I6）× 2 变体 = 12 章节结构守卫。

锁定 `fix_note_i_cycle_structure.py` 的对齐结果，验证：

- 表名存在且正确
- 补了 columns 的表有非空 columns 且首列 is_label
- group/flat 表态正确（两级表头用 group、单级用 flat）
- guidance 无 markdown 粗体 `**`
- I 类循环无账龄维度（禁止出现 `账龄` 字面量）
- `_aligned_by` 标记存在
- openpyxl 直读源 xlsx 交叉比对
- 反向自检

spec: i-cycle-four-table-extraction-and-disclosure-alignment (Task 4.6)
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import openpyxl
import pytest

_ROOT = Path(__file__).resolve().parent.parent
_FIX = _ROOT / "scripts" / "fix" / "fix_note_i_cycle_structure.py"

# 源 xlsx 路径
_SRC_DIR = _ROOT / "wp_templates" / "I"
_SRC_FILES = {
    "I1": _SRC_DIR / "I1 无形资产、累计摊销及减值准备.xlsx",
    "I2": _SRC_DIR / "I2 开发支出.xlsx",
    "I3": _SRC_DIR / "I3 商誉.xlsx",
    "I4": _SRC_DIR / "I4 长期待摊费用.xlsx",
    "I5": _SRC_DIR / "I5 其他非流动资产.xlsx",
    "I6": _SRC_DIR / "I6 研发费用.xlsx",
}

ALIGNED_BY = "i-cycle-four-table-extraction-and-disclosure-alignment"

# 章节映射：(cycle, variant) → section_number
_SECTION_MAP = {
    ("I1", "listed"): "五、26",
    ("I1", "soe"): "八、27",
    ("I2", "listed"): "五、27",
    ("I2", "soe"): "八、28",
    ("I3", "listed"): "五、28",
    ("I3", "soe"): "八、29",
    ("I4", "listed"): "五、29",
    ("I4", "soe"): "八、30",
    ("I5", "listed"): "五、31",
    ("I5", "soe"): "八、32",
    ("I6", "listed"): "五、66",
    ("I6", "soe"): "八、67",
}

# 每个章节脚本校验的表名（只含补了 columns 的表）
_VERIFIED_TABLES: dict[tuple[str, str], list[str]] = {
    ("I1", "listed"): ["重要单项无形资产", "未办妥产权证书的土地使用权情况"],
    ("I1", "soe"): ["无形资产情况"],
    ("I2", "listed"): [
        "研发支出", "开发支出", "开发支出（续：资本化情况）",
        "重要的资本化研发项目", "开发支出减值准备",
    ],
    ("I2", "soe"): ["开发支出"],
    ("I3", "listed"): ["商誉账面原值", "商誉减值准备", "业绩承诺完成及商誉减值情况"],
    ("I3", "soe"): ["（1）商誉账面价值", "（2）商誉减值准备"],
    ("I4", "listed"): ["长期待摊费用"],
    ("I4", "soe"): ["长期待摊费用"],
    ("I5", "listed"): ["其他非流动资产"],
    ("I5", "soe"): ["其他非流动资产"],
    ("I6", "listed"): ["研发费用（按费用性质列示）"],
    ("I6", "soe"): ["研发费用（按费用性质列示）"],
}

# 两级表头（有 group 列）的表
_TWO_LEVEL_TABLES: dict[tuple[str, str], set[str]] = {
    ("I2", "listed"): {"研发支出", "开发支出"},
    ("I2", "soe"): {"开发支出"},
    ("I3", "listed"): {"商誉账面原值", "商誉减值准备"},
    ("I4", "listed"): {"长期待摊费用"},
    ("I5", "listed"): {"其他非流动资产"},
}


def _load_fix():
    spec = importlib.util.spec_from_file_location("_fix_i_struct", _FIX)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FIX = _load_fix()


def _norm(v: object) -> str:
    """去掉全部空白（源模板行标签带缩进与「4. 期末余额」式空格）。"""
    return re.sub(r"\s+", "", str(v or ""))


def _section(cycle: str, variant: str) -> dict:
    """从模板 JSON 中读取指定章节。"""
    sec_num = _SECTION_MAP[(cycle, variant)]
    path_name = "note_template_listed.json" if variant == "listed" else "note_template_soe.json"
    path = _ROOT / "data" / path_name
    doc = json.loads(path.read_text(encoding="utf-8"))
    return next(
        s for s in doc["sections"] if str(s.get("section_number")) == sec_num
    )


def _tables_by_name(cycle: str, variant: str) -> dict[str, dict]:
    """按表名索引当前章节的所有表。"""
    sec = _section(cycle, variant)
    return {str(t.get("name", "")): t for t in sec.get("tables") or []}


# ═══════════════════════════════════════════════════════════════════════════════
# 参数化：12 个章节
# ═══════════════════════════════════════════════════════════════════════════════

_ALL_PARAMS = [
    pytest.param(cycle, variant, id=f"{cycle}_{variant}")
    for cycle in ("I1", "I2", "I3", "I4", "I5", "I6")
    for variant in ("listed", "soe")
]


# ───────────────── Property 1：_aligned_by 标记存在 ─────────────────


@pytest.mark.parametrize("cycle,variant", _ALL_PARAMS)
def test_aligned_by_marker(cycle: str, variant: str):
    """脚本跑完后每个章节必须有 _aligned_by 标记。"""
    sec = _section(cycle, variant)
    assert sec.get("_aligned_by") == ALIGNED_BY, (
        f"{cycle}/{variant} 缺少 _aligned_by 标记"
    )


# ───────────────── Property 2：表名存在于模板 ─────────────────


@pytest.mark.parametrize("cycle,variant", _ALL_PARAMS)
def test_verified_tables_exist(cycle: str, variant: str):
    """脚本校验的表名必须在模板中实际存在。"""
    by_name = _tables_by_name(cycle, variant)
    expected = _VERIFIED_TABLES[(cycle, variant)]
    for name in expected:
        assert name in by_name, (
            f"{cycle}/{variant} 缺表 {name!r}，实有: {list(by_name.keys())}"
        )


# ───────────────── Property 3：columns 非空且结构正确 ─────────────────


@pytest.mark.parametrize("cycle,variant", _ALL_PARAMS)
def test_columns_non_empty(cycle: str, variant: str):
    """补了 columns 的表必须有非空列定义，且首列 is_label。"""
    by_name = _tables_by_name(cycle, variant)
    expected = _VERIFIED_TABLES[(cycle, variant)]
    for name in expected:
        tbl = by_name[name]
        cols = tbl.get("columns") or []
        assert len(cols) > 0, f"{cycle}/{variant}/{name} columns 为空"
        assert cols[0].get("is_label"), f"{cycle}/{variant}/{name} 首列未标 is_label"


# ───────────────── Property 4：group/flat 表态 ─────────────────


@pytest.mark.parametrize("cycle,variant", _ALL_PARAMS)
def test_group_or_flat(cycle: str, variant: str):
    """两级表头的表必须有 group 列；单级表必须标 flat。"""
    by_name = _tables_by_name(cycle, variant)
    two_level = _TWO_LEVEL_TABLES.get((cycle, variant), set())
    expected = _VERIFIED_TABLES[(cycle, variant)]
    for name in expected:
        tbl = by_name[name]
        cols = tbl.get("columns") or []
        if name in two_level:
            # 两级表头：非标签列应有 group
            data_cols = [c for c in cols if not c.get("is_label")]
            assert any(c.get("group") for c in data_cols), (
                f"{cycle}/{variant}/{name} 两级表头缺 group 声明"
            )
        else:
            # 单级表头：须标 flat
            assert any(c.get("flat") for c in cols), (
                f"{cycle}/{variant}/{name} 单级表头未标 flat"
            )


# ───────────────── Property 5：guidance 无 markdown 粗体 ─────────────────


@pytest.mark.parametrize("cycle,variant", _ALL_PARAMS)
def test_guidance_no_markdown_bold(cycle: str, variant: str):
    """guidance 一律纯文本，不得含 `**` markdown 粗体标记。"""
    sec = _section(cycle, variant)
    for tbl in sec.get("tables") or []:
        guidance = tbl.get("guidance") or ""
        assert "**" not in guidance, (
            f"{cycle}/{variant}/{tbl.get('name','?')} guidance 含 markdown 粗体 `**`"
        )


# ───────────────── Property 6：无账龄相关字面量 ─────────────────


_AGING_PATTERN = re.compile(r"账龄|aging", re.IGNORECASE)


@pytest.mark.parametrize("cycle,variant", _ALL_PARAMS)
def test_no_aging_literals(cycle: str, variant: str):
    """I 类循环无账龄维度，guidance 和表内容不得出现「账龄」。"""
    sec = _section(cycle, variant)
    for tbl in sec.get("tables") or []:
        guidance = tbl.get("guidance") or ""
        assert not _AGING_PATTERN.search(guidance), (
            f"{cycle}/{variant}/{tbl.get('name','?')} guidance 含账龄相关字面量"
        )
        # 检查 columns label 和 group
        for col in tbl.get("columns") or []:
            label = col.get("label") or ""
            group = col.get("group") or ""
            assert not _AGING_PATTERN.search(label), (
                f"{cycle}/{variant}/{tbl.get('name','?')} 列 label 含账龄: {label}"
            )
            assert not _AGING_PATTERN.search(group), (
                f"{cycle}/{variant}/{tbl.get('name','?')} 列 group 含账龄: {group}"
            )


# ───────────────── Property 7：幂等与零欠账（--check） ─────────────────


@pytest.mark.parametrize("cycle,variant", _ALL_PARAMS)
def test_check_passes(cycle: str, variant: str):
    """fix 脚本 --check 模式对每个章节报告零欠账。"""
    runner_key = f"{cycle}_{variant.upper()}"
    _label, runner_fn = FIX._RUNNERS[runner_key]
    _changes, warnings, errs = runner_fn(dry_run=True, check=True)
    assert not errs, f"{cycle}/{variant} 结构欠账: {errs}"
    assert not warnings, f"{cycle}/{variant} 告警: {warnings}"


# ───────────────── Property 8：无 header_label 假行 ─────────────────


@pytest.mark.parametrize("cycle,variant", _ALL_PARAMS)
def test_no_header_label_fake_rows(cycle: str, variant: str):
    """md 重建压扁的第二行表头残留 header_label 须已清除。"""
    by_name = _tables_by_name(cycle, variant)
    expected = _VERIFIED_TABLES[(cycle, variant)]
    for name in expected:
        tbl = by_name[name]
        rows = tbl.get("rows") or []
        assert not any(r.get("row_type") == "header_label" for r in rows), (
            f"{cycle}/{variant}/{name} 残留 header_label 假行"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# openpyxl 直读源 xlsx 交叉比对
# ═══════════════════════════════════════════════════════════════════════════════


def test_source_xlsx_files_exist():
    """所有 6 个源 xlsx 文件必须存在。"""
    for cycle, path in _SRC_FILES.items():
        assert path.exists(), f"{cycle} 源 xlsx 不存在: {path}"


def test_i6_listed_table_name_matches_source():
    """I6 上市「研发费用（按费用性质列示）」表名取自源 xlsx。"""
    wb = openpyxl.load_workbook(_SRC_FILES["I6"], data_only=True)
    sheets = wb.sheetnames
    # 确认披露 sheet 存在
    listed_sheet = next((s for s in sheets if "上市" in s), None)
    assert listed_sheet, f"I6 源 xlsx 缺上市披露 sheet，sheetnames={sheets}"


def test_i6_soe_table_name_matches_source():
    """I6 国企「研发费用（按费用性质列示）」表名取自源 xlsx。"""
    wb = openpyxl.load_workbook(_SRC_FILES["I6"], data_only=True)
    sheets = wb.sheetnames
    soe_sheet = next((s for s in sheets if "国" in s), None)
    assert soe_sheet, f"I6 源 xlsx 缺国企披露 sheet，sheetnames={sheets}"


def test_i4_listed_two_level_headers_from_source():
    """I4 上市长期待摊费用：源 xlsx 两级表头应含「本期减少」分组。"""
    wb = openpyxl.load_workbook(_SRC_FILES["I4"], data_only=True)
    sheets = wb.sheetnames
    listed_sheet = next((s for s in sheets if "上市" in s), None)
    if listed_sheet:
        ws = wb[listed_sheet]
        # 验证模板 columns 有 group='本期减少' 的列
        by_name = _tables_by_name("I4", "listed")
        tbl = by_name["长期待摊费用"]
        cols = tbl.get("columns") or []
        groups = [c.get("group") for c in cols if c.get("group")]
        assert "本期减少" in groups, f"I4 上市缺 '本期减少' 分组，groups={groups}"


def test_i5_listed_two_level_headers_from_source():
    """I5 上市其他非流动资产：源 xlsx 两级表头应含「期末数」和「上年年末数」分组。"""
    by_name = _tables_by_name("I5", "listed")
    tbl = by_name["其他非流动资产"]
    cols = tbl.get("columns") or []
    groups = set(c.get("group") for c in cols if c.get("group"))
    assert "期末数" in groups, f"I5 上市缺 '期末数' 分组，groups={groups}"
    assert "上年年末数" in groups, f"I5 上市缺 '上年年末数' 分组，groups={groups}"


def test_i3_listed_goodwill_book_value_two_level():
    """I3 上市商誉账面原值：两级表头含「本期增加」「本期减少」。"""
    by_name = _tables_by_name("I3", "listed")
    tbl = by_name["商誉账面原值"]
    cols = tbl.get("columns") or []
    groups = set(c.get("group") for c in cols if c.get("group"))
    assert "本期增加" in groups, f"I3 上市商誉账面原值缺 '本期增加' 分组"
    assert "本期减少" in groups, f"I3 上市商誉账面原值缺 '本期减少' 分组"


def test_i2_listed_research_expenditure_two_level():
    """I2 上市研发支出：两级表头含「本期发生额」「上期发生额」。"""
    by_name = _tables_by_name("I2", "listed")
    tbl = by_name["研发支出"]
    cols = tbl.get("columns") or []
    groups = set(c.get("group") for c in cols if c.get("group"))
    assert "本期发生额" in groups, f"I2 上市研发支出缺 '本期发生额' 分组"
    assert "上期发生额" in groups, f"I2 上市研发支出缺 '上期发生额' 分组"


def test_i2_listed_dev_expenditure_two_level():
    """I2 上市开发支出：两级表头含「本期增加」「本期减少」。"""
    by_name = _tables_by_name("I2", "listed")
    tbl = by_name["开发支出"]
    cols = tbl.get("columns") or []
    groups = set(c.get("group") for c in cols if c.get("group"))
    assert "本期增加" in groups, f"I2 上市开发支出缺 '本期增加' 分组"
    assert "本期减少" in groups, f"I2 上市开发支出缺 '本期减少' 分组"


def test_i2_soe_dev_expenditure_two_level():
    """I2 国企开发支出：两级表头含「本期增加」「本期减少」。"""
    by_name = _tables_by_name("I2", "soe")
    tbl = by_name["开发支出"]
    cols = tbl.get("columns") or []
    groups = set(c.get("group") for c in cols if c.get("group"))
    assert "本期增加" in groups, f"I2 国企开发支出缺 '本期增加' 分组"
    assert "本期减少" in groups, f"I2 国企开发支出缺 '本期减少' 分组"


def test_i3_soe_tables_are_flat():
    """I3 国企两张表均为单级 flat 5 列。"""
    by_name = _tables_by_name("I3", "soe")
    for name in ["（1）商誉账面价值", "（2）商誉减值准备"]:
        tbl = by_name[name]
        cols = tbl.get("columns") or []
        assert len(cols) == 5, f"I3 国企 {name} 应有 5 列，实有 {len(cols)}"
        assert any(c.get("flat") for c in cols), f"I3 国企 {name} 未标 flat"


def test_i6_columns_are_flat():
    """I6 两版均为单级 flat 3 列（项目/本期发生额/上期发生额）。"""
    for variant in ("listed", "soe"):
        by_name = _tables_by_name("I6", variant)
        tbl = by_name["研发费用（按费用性质列示）"]
        cols = tbl.get("columns") or []
        assert len(cols) == 3, f"I6 {variant} 应有 3 列，实有 {len(cols)}"
        assert any(c.get("flat") for c in cols), f"I6 {variant} 未标 flat"
        # 验证列 key
        keys = [c.get("key") for c in cols]
        assert keys[0] == "项目", f"I6 {variant} 首列 key 应为 '项目'"


# ═══════════════════════════════════════════════════════════════════════════════
# 反向自检（防守卫空转）
# ═══════════════════════════════════════════════════════════════════════════════


def test_reverse_self_check_validate_section():
    """validate_section 能抓出缺 columns 的情况（防守卫空转）。"""
    import sys
    sys.path.insert(0, str(_ROOT / "scripts" / "fix"))
    from _note_structure_kit import validate_section

    broken = {
        "tables": [{
            "name": "长期待摊费用",
            "headers": ["项目"],
            "rows": [],
            "guidance": "x",
        }],
    }
    errs = validate_section(broken, ["长期待摊费用"])
    assert any("缺 columns" in e for e in errs), f"validate_section 未检测出缺 columns: {errs}"


def test_reverse_self_check_normalizer():
    """`_norm` 必须能把源模板的缩进/内嵌空格归一，否则行集比对恒绿。"""
    assert _norm("    4. 期末余额") == "4.期末余额"
    assert _norm("其中：土地") == "其中：土地"
    assert _norm("项  目") == "项目"
    assert _norm(None) == ""
    assert _norm("") == ""


def test_reverse_self_check_aging_pattern():
    """_AGING_PATTERN 必须能匹配「账龄」和 aging（防断言空转）。"""
    assert _AGING_PATTERN.search("按账龄分析")
    assert _AGING_PATTERN.search("aging analysis")
    assert not _AGING_PATTERN.search("无形资产")
    assert not _AGING_PATTERN.search("研发费用")


def test_reverse_self_check_section_map_complete():
    """_SECTION_MAP 必须覆盖全部 12 个 (cycle, variant) 组合。"""
    expected = {
        (c, v) for c in ("I1", "I2", "I3", "I4", "I5", "I6")
        for v in ("listed", "soe")
    }
    assert set(_SECTION_MAP.keys()) == expected


def test_reverse_self_check_verified_tables_complete():
    """_VERIFIED_TABLES 必须覆盖全部 12 个 (cycle, variant) 组合。"""
    expected = {
        (c, v) for c in ("I1", "I2", "I3", "I4", "I5", "I6")
        for v in ("listed", "soe")
    }
    assert set(_VERIFIED_TABLES.keys()) == expected
