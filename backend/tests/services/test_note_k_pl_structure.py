"""附注 K 系损益类章节结构守卫（K8~K13）。

锁住 ``fix_note_k_pl_structure.py`` 的修订成果，防 md 重建 / 并发会话回退：

- 12 个章节各恰 1 张表，表名为科目名（泄漏名 ``项  目`` 已清除）
- 每张表带 ``columns``（显式 ``flat``）+ ``guidance``，无 ``_column_groups``
- 无占位说明行（``可无限量添加行`` / ``......`` / ``……``）与 ``header_label`` 假行
- K10 国企 4 列（末列「是否为政府补助」）、K12/K13 两版 4 列（末列非经常性损益）
- 上市侧章节号是模板实测截断值（``三、`` 章 md 重建既有形态）

spec: .kiro/specs/k-cycle-disclosure-alignment/ Task 4.3
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.fix.fix_note_k_pl_structure import (
    ALIGNED_BY,
    LEAKED_TABLE_NAME,
    PLACEHOLDER_ROW_LABELS,
    PLAN,
    validate_section,
)

_DATA = Path(__file__).resolve().parents[2] / "data"


def _load(variant: str, section_number: str) -> dict[str, Any]:
    doc = json.loads((_DATA / f"note_template_{variant}.json").read_text(encoding="utf-8"))
    for sec in doc.get("sections", []):
        if str(sec.get("section_number", "")) == section_number:
            return sec
    raise AssertionError(f"note_template_{variant}.json 缺章节 {section_number}")


ENTRY_IDS = [f"{e['cycle']}-{e['variant']}" for e in PLAN]


def test_plan_covers_twelve_sections() -> None:
    assert len(PLAN) == 12, f"批 1 应覆盖 K8~K13 两版共 12 章节，实为 {len(PLAN)}"
    assert len({(e["cycle"], e["variant"]) for e in PLAN}) == 12


@pytest.mark.parametrize("entry", PLAN, ids=ENTRY_IDS)
def test_section_passes_script_validator(entry: dict[str, Any]) -> None:
    sec = _load(entry["variant"], entry["section"])
    assert validate_section(sec, entry) == []


@pytest.mark.parametrize("entry", PLAN, ids=ENTRY_IDS)
def test_aligned_by_stamp(entry: dict[str, Any]) -> None:
    sec = _load(entry["variant"], entry["section"])
    assert sec.get("_aligned_by") == ALIGNED_BY


@pytest.mark.parametrize("entry", PLAN, ids=ENTRY_IDS)
def test_no_leaked_or_placeholder(entry: dict[str, Any]) -> None:
    sec = _load(entry["variant"], entry["section"])
    names = [str(t.get("name", "")) for t in sec.get("tables") or []]
    assert LEAKED_TABLE_NAME not in names

    norm = {str(x).replace(" ", "").replace("\u3000", "") for x in PLACEHOLDER_ROW_LABELS}
    for tbl in sec.get("tables") or []:
        for row in tbl.get("rows") or []:
            label = str(row.get("label", "")).replace(" ", "").replace("\u3000", "")
            assert label not in norm, f"{tbl.get('name')} 残留占位行「{row.get('label')}」"
            assert str(row.get("row_type", "")) != "header_label"


@pytest.mark.parametrize("entry", PLAN, ids=ENTRY_IDS)
def test_columns_and_guidance(entry: dict[str, Any]) -> None:
    sec = _load(entry["variant"], entry["section"])
    by_name = {str(t.get("name", "")): t for t in sec.get("tables") or []}
    for spec in entry["tables"]:
        tbl = by_name[spec["name"]]
        cols = tbl["columns"]
        assert [c["label"] for c in cols] == [c["label"] for c in spec["columns"]]
        assert tbl["headers"] == [c["label"] for c in spec["columns"]]
        assert cols[0].get("is_label") is True
        assert any(c.get("flat") for c in cols)
        assert not any(c.get("group") for c in cols)
        assert "_column_groups" not in tbl
        assert str(tbl.get("guidance", "")).strip()


def test_column_counts_per_cycle() -> None:
    """列数是本批的实质修复点（旧常量丢了 K10 国企与 K12/K13 两版的第 4 列）。"""
    expected = {
        ("K8", "listed"): 3, ("K8", "soe"): 3,
        ("K9", "listed"): 3, ("K9", "soe"): 3,
        ("K10", "listed"): 3, ("K10", "soe"): 4,
        ("K11", "listed"): 3, ("K11", "soe"): 3,
        ("K12", "listed"): 4, ("K12", "soe"): 4,
        ("K13", "listed"): 4, ("K13", "soe"): 4,
    }
    for entry in PLAN:
        sec = _load(entry["variant"], entry["section"])
        tbl = (sec.get("tables") or [])[0]
        got = len(tbl["columns"])
        want = expected[(entry["cycle"], entry["variant"])]
        assert got == want, f"{entry['cycle']} {entry['variant']} 列数 {got} ≠ {want}"


def test_extra_column_labels() -> None:
    k10_soe = _load("soe", "八、69")["tables"][0]
    assert k10_soe["columns"][3]["label"] == "是否为政府补助"
    assert k10_soe["columns"][3]["key"] == "is_gov_grant"
    for variant, section in (("listed", "三、营业外收入（注："), ("soe", "八、76")):
        tbl = _load(variant, section)["tables"][0]
        assert tbl["columns"][3]["label"] == "计入当期非经常性损益的金额"
        assert tbl["columns"][3]["key"] == "non_recurring_amount"


def test_listed_section_numbers_are_truncated_form() -> None:
    """listed `三、` 章 section_number 被 md 重建截断为 10 字符，是既有真源形态。"""
    listed_sections = {e["section"] for e in PLAN if e["variant"] == "listed"}
    assert "三、资产减值损失（损" in listed_sections
    assert "三、营业外收入（注：" in listed_sections
    assert "三、营业外支出（注：" in listed_sections


def test_validator_catches_regression() -> None:
    """反向自检：摘掉 flat / 塞回占位行，校验器必须报错（防守卫空转）。"""
    entry = next(e for e in PLAN if e["cycle"] == "K12" and e["variant"] == "soe")
    sec = _load(entry["variant"], entry["section"])

    broken = json.loads(json.dumps(sec, ensure_ascii=False))
    for col in broken["tables"][0]["columns"]:
        col.pop("flat", None)
    assert any("未显式 flat" in e for e in validate_section(broken, entry))

    broken2 = json.loads(json.dumps(sec, ensure_ascii=False))
    broken2["tables"][0]["rows"].append({"label": "......", "row_type": "data"})
    assert any("占位说明行" in e for e in validate_section(broken2, entry))

    broken3 = json.loads(json.dumps(sec, ensure_ascii=False))
    broken3["tables"][0]["columns"] = broken3["tables"][0]["columns"][:3]
    assert validate_section(broken3, entry) != []
