"""附注应付票据（F3）章节结构守卫。

修订入口（结构漂移时先跑）::

    python backend/scripts/fix/fix_note_notes_payable_structure.py --check
    python backend/scripts/fix/fix_note_notes_payable_structure.py

权威源：``backend/wp_templates/F/F3 应付票据.xlsx``（逐格实证）
  - 上市「附注披露信息(上市公司)」A6=种类 / B6=期末余额 / C6=上年年末余额
  - 国企「附注披露信息(国企)」    A6=类别 / B6=期末余额 / C6=期初余额
  - 两版行序均为 r7 银行承兑汇票 → r8 商业承兑汇票 → r9 合计

spec: .kiro/specs/f-cycle-disclosure-parity/ R1 / R2 / R3
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent
DATA_DIR = _BACKEND / "data"

ALIGNED_BY = "f-cycle-disclosure-parity"
TABLE_NAME = "应付票据"
_FIX_HINT = "→ 跑 backend/scripts/fix/fix_note_notes_payable_structure.py"

LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"
LISTED_SECTION = "五、36"
SOE_SECTION = "八、36"

EXPECTED_ROWS = ["银行承兑汇票", "商业承兑汇票", "合计"]
EXPECTED_HEADERS = {
    "listed": ["种类", "期末余额", "上年年末余额"],
    "soe": ["类别", "期末余额", "期初余额"],
}


def _load_section(path: Path, section_number: str) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    for s in doc.get("sections", []):
        if str(s.get("section_number", "")) == section_number:
            return s
    raise AssertionError(f"{path.name} 缺章节 {section_number}")


@pytest.fixture(scope="module")
def sections() -> dict[str, dict[str, Any]]:
    return {
        "listed": _load_section(LISTED_PATH, LISTED_SECTION),
        "soe": _load_section(SOE_PATH, SOE_SECTION),
    }


def _table(section: dict[str, Any]) -> dict[str, Any]:
    tbl = next(
        (t for t in section.get("tables") or [] if str(t.get("name")) == TABLE_NAME),
        None,
    )
    assert tbl is not None, f"缺表「{TABLE_NAME}」；{_FIX_HINT}"
    return tbl


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_headers_match_source_xlsx(sections: dict[str, Any], variant: str) -> None:
    """R1：国企第 1/3 列用语与上市不同（类别 / 期初余额），不得共用上市口径。"""
    tbl = _table(sections[variant])
    assert tbl["headers"] == EXPECTED_HEADERS[variant], _FIX_HINT


def test_listed_and_soe_headers_differ(sections: dict[str, Any]) -> None:
    """反向断言：两版表头必须不同，防再次退回共用一份列头。"""
    assert _table(sections["listed"])["headers"] != _table(sections["soe"])["headers"]


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_rows_follow_source_order(sections: dict[str, Any], variant: str) -> None:
    """R2：源 xlsx r7 银行承兑在前，r8 商业承兑在后。"""
    labels = [str(r.get("label")) for r in _table(sections[variant]).get("rows") or []]
    assert labels == EXPECTED_ROWS, _FIX_HINT


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_columns_declared_and_flat(sections: dict[str, Any], variant: str) -> None:
    """R3：单级表头必须显式标 flat，否则 seed 路径会被前缀推断塞凭空父表头。"""
    tbl = _table(sections[variant])
    cols = tbl.get("columns") or []
    assert len(cols) == len(tbl["headers"]), _FIX_HINT
    assert any(c.get("flat") for c in cols), f"未标 flat；{_FIX_HINT}"
    assert not any(c.get("group") for c in cols), "单级表头不应有 group"
    for k, (h, c) in enumerate(zip(tbl["headers"], cols)):
        assert str(c.get("label")) == str(h), f"第 {k} 列 label 与 headers 不一致；{_FIX_HINT}"


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_guidance_present_and_plain_headers(sections: dict[str, Any], variant: str) -> None:
    tbl = _table(sections[variant])
    assert str(tbl.get("guidance") or "").strip(), f"缺 guidance；{_FIX_HINT}"
    for h in tbl["headers"]:
        assert not re.search(r"<[^>]+>", str(h)), f"headers 含 HTML：{h!r}"


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_section_carries_alignment_stamp(sections: dict[str, Any], variant: str) -> None:
    section = sections[variant]
    assert section.get("_aligned_by") == ALIGNED_BY, _FIX_HINT
    assert section.get("_aligned_at")


def test_frontend_columns_mirror_template() -> None:
    """前端同步列头 label 必须与模板 headers 逐字一致（防两侧漂移）。"""
    ts = (
        _REPO / "audit-platform/frontend/src/components/workpaper/composables"
        / "f3NoteSectionMap.ts"
    ).read_text(encoding="utf-8")

    for variant, const in (("listed", "F3_LISTED_YFPJ_COLUMNS"), ("soe", "F3_SOE_YFPJ_COLUMNS")):
        m = re.search(rf"{const}[^=]*=\s*\[(.*?)\n\]", ts, re.S)
        assert m, f"{const} 未找到"
        labels = re.findall(r"label:\s*'([^']+)'", m.group(1))
        assert labels == EXPECTED_HEADERS[variant], f"{const} label 与模板不一致"

    # 行序常量同样锚定源 xlsx
    m = re.search(r"F3_CLASS_ROW_ORDER\s*=\s*\[(.*?)\]", ts, re.S)
    assert m, "F3_CLASS_ROW_ORDER 未找到"
    assert re.findall(r"'([^']+)'", m.group(1)) == EXPECTED_ROWS[:-1]
