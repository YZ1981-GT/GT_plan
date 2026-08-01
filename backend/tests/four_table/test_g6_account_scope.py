"""G6 其他债权投资 — 科目映射单一真源守卫.

验证 report_config BS-022 = TB('1505','期末余额') 在代码中的落地：
- render 策略科目常量 = 1505
- 源码不含旧科目码 1503/1510/1531 作为科目使用
- ReportLineAccountSpec.row_code = 'BS-022'
- 公式预设中所有 G6 条目只含 1505 族

spec: .kiro/specs/g6-four-table-extraction-and-disclosure-alignment/
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

# ─── 后端 render 常量 ──────────────────────────────────────────────────

def test_account_prefix_is_1505():
    """render 策略的 _G6_ACCOUNT_PREFIX 必须是 '1505'."""
    from app.routers.wp_render_strategies._g6_other_bond_investment_main import (
        _G6_ACCOUNT_PREFIX,
    )
    assert _G6_ACCOUNT_PREFIX == "1505"


def test_account_spec_row_code():
    """ReportLineAccountSpec.row_code 必须是 'BS-022'."""
    from app.routers.wp_render_strategies._g6_other_bond_investment_main import (
        _G6_ACCOUNT_SPEC,
    )
    assert _G6_ACCOUNT_SPEC.row_code == "BS-022"


def test_account_spec_fallback_gross():
    """fallback_gross 必须含 '1505'."""
    from app.routers.wp_render_strategies._g6_other_bond_investment_main import (
        _G6_ACCOUNT_SPEC,
    )
    assert "1505" in _G6_ACCOUNT_SPEC.fallback_gross


def test_account_spec_no_provision():
    """G6 无备抵科目 → provision_row_code 为 None / fallback_provision 为空."""
    from app.routers.wp_render_strategies._g6_other_bond_investment_main import (
        _G6_ACCOUNT_SPEC,
    )
    assert _G6_ACCOUNT_SPEC.provision_row_code is None
    assert len(_G6_ACCOUNT_SPEC.fallback_provision) == 0


# ─── 源码中禁止旧科目码 ───────────────────────────────────────────────

def _strip_comments(src: str) -> str:
    """去掉 Python 注释（# 开头到行尾）和多行字符串中的注释行."""
    lines = []
    for line in src.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # 移除行内注释（简化：从最后一个 # 开始，且不在字符串内的粗略近似）
        lines.append(line)
    return "\n".join(lines)


def test_render_source_no_forbidden_account_codes():
    """render 策略源码不得含 '1503'/'1510'/'1531' 作为科目码/请求参数.

    允许出现在注释和字符串说明中（如 '原值为 1503' 的纠错注释），但不许作为
    函数参数/变量赋值/字面量。
    """
    src_path = Path(__file__).resolve().parents[2] / (
        "app/routers/wp_render_strategies/_g6_other_bond_investment_main.py"
    )
    src = src_path.read_text(encoding="utf-8")
    clean = _strip_comments(src)

    # 匹配模式：引号包裹的科目码 '1503' / "1503" / 赋值 = "1503" 等
    forbidden_patterns = [
        r"""['"]1503['"]""",  # 字符串字面量 '1503' 或 "1503"
        r"""['"]1510['"]""",
        r"""['"]1531""",
    ]
    for pat in forbidden_patterns:
        matches = re.findall(pat, clean)
        # 允许在 _G6_ACCOUNT_PREFIX 旧值纠错注释中提及，但注释已被 strip
        assert not matches, (
            f"G6 render 源码（去注释后）仍含禁止的科目码模式 {pat}: {matches}"
        )


# ─── 公式预设守卫 ─────────────────────────────────────────────────────

def test_formula_presets_g6_only_1505():
    """prefill_formula_mapping.json 中 wp_code=G6 的所有条目只许含 1505 族科目."""
    presets_path = Path(__file__).resolve().parents[2] / "data/prefill_formula_mapping.json"
    data = json.loads(presets_path.read_text(encoding="utf-8"))
    entries = data.get("mappings", [])
    g6_entries = [e for e in entries if e.get("wp_code") == "G6"]
    assert len(g6_entries) >= 2, "G6 should have at least 2 preset entries"

    all_codes: set[str] = set()
    for entry in g6_entries:
        all_codes.update(entry.get("account_codes", []))
        for cell in entry.get("cells", []):
            formula = cell.get("formula", "")
            found = re.findall(r"'(\d{4}[\d.]*)'", formula)
            all_codes.update(found)

    forbidden = {c for c in all_codes if c.startswith(("1503", "1510", "1531"))}
    assert not forbidden, f"G6 presets still contain forbidden codes: {forbidden}"

    # 正向断言：必须含 1505
    assert any(c.startswith("1505") for c in all_codes), "G6 presets must contain 1505"


def test_formula_presets_g6_no_hardcoded_aux():
    """G6 公式预设不得含硬编码客户/项目名称 AUX 公式."""
    presets_path = Path(__file__).resolve().parents[2] / "data/prefill_formula_mapping.json"
    data = json.loads(presets_path.read_text(encoding="utf-8"))
    entries = data.get("mappings", [])
    g6_entries = [e for e in entries if e.get("wp_code") == "G6"]

    for entry in g6_entries:
        for cell in entry.get("cells", []):
            formula = cell.get("formula", "")
            assert "AUX(" not in formula, (
                f"G6 preset contains hardcoded AUX formula: {cell.get('cell_ref')}: {formula}"
            )
