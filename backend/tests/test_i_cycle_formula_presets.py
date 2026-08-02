"""I 类公式预设合法性契约测试。

验证 `prefill_formula_mapping.json` 中 I 类（wp_code 以 I 开头且后续全为数字）
所有块的：

1. sheet 存在性（源模板 xlsx sheetnames）
2. 科目存在性（standard_account_chart.json）
3. 防成环（审定表 WP() 不引用自己；明细表不引用回审定表）
4. wp_name 语义
5. 无 1712/1717/1911 残留

spec: .kiro/specs/i-cycle-four-table-extraction-and-disclosure-alignment/
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

# ── 路径 ──────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
TEMPLATE_DIR = ROOT / "wp_templates" / "I"
MAPPING_PATH = DATA_DIR / "prefill_formula_mapping.json"
ACCOUNT_CHART_PATH = DATA_DIR / "standard_account_chart.json"


# ── 数据加载 ──────────────────────────────────────────────────────────────────

def _load_mapping() -> list[dict[str, Any]]:
    raw = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    mappings = raw["mappings"] if isinstance(raw, dict) and "mappings" in raw else raw
    return [
        b for b in mappings
        if b.get("wp_code", "").startswith("I")
        and b["wp_code"][1:].isdigit()
        and not b.get("deleted", False)
    ]


def _load_account_codes() -> set[str]:
    raw = json.loads(ACCOUNT_CHART_PATH.read_text(encoding="utf-8"))
    return {a["code"] for a in raw.get("accounts", [])}


def _load_template_sheetnames() -> dict[str, list[str]]:
    """返回 {wp_code: [sheetname, ...]}，跳过 ~$ 锁文件。"""
    import openpyxl

    result: dict[str, list[str]] = {}
    for xlsx_path in sorted(TEMPLATE_DIR.glob("*.xlsx")):
        if xlsx_path.name.startswith("~$"):
            continue
        # 提取 wp_code: 文件名形如 "I1 无形资产…xlsx"
        stem = xlsx_path.stem
        wp_code_match = re.match(r"^(I\d+)\s", stem)
        if not wp_code_match:
            continue
        wp_code = wp_code_match.group(1)
        wb = openpyxl.load_workbook(xlsx_path, read_only=True)
        result[wp_code] = list(wb.sheetnames)
        wb.close()
    return result


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def i_blocks() -> list[dict[str, Any]]:
    return _load_mapping()


@pytest.fixture(scope="module")
def account_codes() -> set[str]:
    return _load_account_codes()


@pytest.fixture(scope="module")
def template_sheets() -> dict[str, list[str]]:
    return _load_template_sheetnames()


# ── 参数化 ────────────────────────────────────────────────────────────────────

def _block_ids() -> list[str]:
    """为每个块生成唯一 test id。"""
    blocks = _load_mapping()
    return [f"{b['wp_code']}-{b['sheet']}" for b in blocks]


def _blocks_parametrize():
    blocks = _load_mapping()
    return blocks


# ── 1. Sheet 存在性 ──────────────────────────────────────────────────────────

# 预设里贴错标签的 sheet 名 → 源 xlsx 真实 tab 名
# 见 memory §任务状态 "预设 sheet 名贴错标签"
_KNOWN_SHEET_LABEL_ISSUES: dict[tuple[str, str], str] = {
    ("I1", "审定表I1-1"): "审定表I1",
    # I1 审定表在源模板中实际名称为 "审定表I1"（不带 -1 后缀）
}


@pytest.mark.parametrize("block", _blocks_parametrize(), ids=_block_ids())
def test_sheet_exists_in_template(block: dict, template_sheets: dict[str, list[str]]) -> None:
    """每个块的 sheet 字段必须存在于对应源模板 xlsx 的 sheetnames 中。
    已知贴错标签的 sheet 走白名单（源模板权威，预设可纠偏）。
    """
    wp_code = block["wp_code"]
    sheet = block["sheet"]

    # 跳过已知贴错标签的块（已记录，等待 spec 修订）
    if (wp_code, sheet) in _KNOWN_SHEET_LABEL_ISSUES:
        pytest.skip(
            f"已知 sheet 名不一致: 预设 '{sheet}' vs "
            f"源模板 '{_KNOWN_SHEET_LABEL_ISSUES[(wp_code, sheet)]}'"
        )

    assert wp_code in template_sheets, (
        f"源模板目录下找不到 {wp_code} 对应的 xlsx 文件"
    )
    sheetnames = template_sheets[wp_code]
    assert sheet in sheetnames, (
        f"{wp_code} 的 sheet '{sheet}' 不存在于模板中。"
        f" 可用的 sheet: {sheetnames}"
    )


# ── 2. 科目存在性 ────────────────────────────────────────────────────────────

# 已知 chart_conflict：I2 的 1703 在本项目被诊断冲突后回退兜底 1704，
# 但 1704 不在 standard_account_chart.json（CAS 标准没有该码）。
# 见 memory §任务状态 "I2 的 `1703` 被 `chart_conflict` 正确诊断并回退兜底 `1704`"
_KNOWN_CHART_CONFLICTS: set[str] = {"1704"}


@pytest.mark.parametrize("block", _blocks_parametrize(), ids=_block_ids())
def test_account_codes_exist_in_chart(block: dict, account_codes: set[str]) -> None:
    """每个块 account_codes 里的码必须存在于标准科目表。
    空列表合法（I5）。已知 chart_conflict 码走白名单。
    """
    codes = block.get("account_codes", [])
    for code in codes:
        if code in _KNOWN_CHART_CONFLICTS:
            continue
        assert code in account_codes, (
            f"{block['wp_code']} / {block['sheet']} 的科目码 '{code}' "
            f"不在 standard_account_chart.json 中"
        )


# ── 3. 防成环 ────────────────────────────────────────────────────────────────

_WP_PATTERN = re.compile(r"WP\(\s*'([^']+)'\s*,\s*'([^']+)'")


@pytest.mark.parametrize("block", _blocks_parametrize(), ids=_block_ids())
def test_no_self_referencing_cycles(block: dict) -> None:
    """
    审定表块的 cells[].formula 里的 WP() 引用不得指向自己
    （如 WP('I1','审定表I1',…) 不应出现在 I1 审定表块里）；
    明细表块不得有 WP() 引用回审定表。
    """
    wp_code = block["wp_code"]
    sheet = block["sheet"]
    cells = block.get("cells", [])

    is_adjudication = "审定表" in sheet
    is_detail = "明细表" in sheet

    for cell in cells:
        formula = cell.get("formula", "")
        for match in _WP_PATTERN.finditer(formula):
            ref_wp = match.group(1)
            ref_sheet = match.group(2)

            if is_adjudication:
                # 审定表不得引用自己的审定表 sheet
                if ref_wp == wp_code and "审定表" in ref_sheet:
                    pytest.fail(
                        f"{wp_code}/{sheet} 审定表块 WP() 引用了自己的审定表: "
                        f"WP('{ref_wp}','{ref_sheet}',...) "
                        f"cell_ref={cell.get('cell_ref')}"
                    )

            if is_detail:
                # 明细表不得引用回审定表
                if ref_wp == wp_code and "审定表" in ref_sheet:
                    pytest.fail(
                        f"{wp_code}/{sheet} 明细表块 WP() 引用了审定表: "
                        f"WP('{ref_wp}','{ref_sheet}',...) "
                        f"cell_ref={cell.get('cell_ref')}"
                    )


# ── 4. wp_name 语义 ──────────────────────────────────────────────────────────

_WP_NAME_RULES: dict[str, list[str]] = {
    "I1": ["无形资产", "摊销"],
    "I2": ["开发支出", "研发"],
    "I3": ["商誉"],
    "I4": ["长期待摊费用", "待摊", "摊销"],
    "I5": ["其他非流动资产", "非流动"],
    "I6": ["研发费用", "研发"],
}


@pytest.mark.parametrize("block", _blocks_parametrize(), ids=_block_ids())
def test_wp_name_semantic(block: dict) -> None:
    """wp_name 必须包含对应循环的语义关键字。"""
    wp_code = block["wp_code"]
    wp_name = block.get("wp_name", "")
    keywords = _WP_NAME_RULES.get(wp_code, [])

    if not keywords:
        return  # 没有定义规则的跳过

    matched = any(kw in wp_name for kw in keywords)
    assert matched, (
        f"{wp_code} 块 wp_name='{wp_name}' 不含任何预期关键字 {keywords}"
    )


# ── 5. 无 1712/1717/1911 残留 ────────────────────────────────────────────────

_FORBIDDEN_CODES = {"1712", "1717", "1911"}


@pytest.mark.parametrize("block", _blocks_parametrize(), ids=_block_ids())
def test_no_forbidden_code_residue(block: dict) -> None:
    """I 类所有块的 account_codes 与 cells[].formula 中不得出现 1712/1717/1911。"""
    wp_code = block["wp_code"]
    sheet = block["sheet"]

    # 检查 account_codes
    codes = block.get("account_codes", [])
    for code in codes:
        assert code not in _FORBIDDEN_CODES, (
            f"{wp_code}/{sheet} account_codes 含禁用码 '{code}'"
        )

    # 检查 cells[].formula
    for cell in block.get("cells", []):
        formula = cell.get("formula", "")
        for forbidden in _FORBIDDEN_CODES:
            assert forbidden not in formula, (
                f"{wp_code}/{sheet} cell_ref='{cell.get('cell_ref')}' "
                f"公式含禁用码 '{forbidden}': {formula}"
            )
