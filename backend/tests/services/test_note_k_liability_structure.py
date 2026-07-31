"""附注 K 系负债/递延类章节结构守卫（K3/K4/K5/K7）。

锁住 ``fix_note_k_liability_structure.py`` 的修订成果，防 md 重建 / 并发会话回退：

- 8 个章节 22 张表全部带 ``columns``（显式 ``flat``）+ ``guidance``，无 ``_column_groups``
- 泄漏 / 假表名 3 处已清除（``项  目`` / ``其他应付款（表6）`` / ``债券名称``）
- 无占位说明行（``可无限量添加行`` / ``……``）与 ``header_label`` 假行
- ``columns`` 与 ``headers`` 逐位同形；列键与前端 map 既有 builder 一致
- K5 变体列数不同（上市 4 / 国企 3）；K7 国企含政府补助明细 10 列表

spec: .kiro/specs/k-cycle-disclosure-alignment/ Task 9
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.fix.fix_note_k_liability_structure import (
    ALIGNED_BY,
    LEAKED_NAMES,
    PLACEHOLDER_ROW_LABELS,
    PLAN,
    validate_section,
)

_DATA = Path(__file__).resolve().parents[2] / "data"
_NORM_PLACEHOLDER = {str(x).replace(" ", "").replace("\u3000", "") for x in PLACEHOLDER_ROW_LABELS}


def _load(variant: str, section_number: str) -> dict[str, Any]:
    doc = json.loads((_DATA / f"note_template_{variant}.json").read_text(encoding="utf-8"))
    for sec in doc.get("sections", []):
        if str(sec.get("section_number", "")) == section_number:
            return sec
    raise AssertionError(f"note_template_{variant}.json 缺章节 {section_number}")


ENTRY_IDS = [f"{e['cycle']}-{e['variant']}" for e in PLAN]


def test_plan_covers_eight_sections() -> None:
    """K3 7+6 / K4 3+1 / K5 1+1 / K7 1+2 = 22 张表。"""
    assert len(PLAN) == 8, f"批 2 应覆盖 K3/K4/K5/K7 两版共 8 章节，实为 {len(PLAN)}"
    assert sum(len(e["tables"]) for e in PLAN) == 22


@pytest.mark.parametrize("entry", PLAN, ids=ENTRY_IDS)
def test_section_passes_script_validator(entry: dict[str, Any]) -> None:
    sec = _load(entry["variant"], entry["section"])
    assert validate_section(sec, entry) == []


@pytest.mark.parametrize("entry", PLAN, ids=ENTRY_IDS)
def test_aligned_by_stamp(entry: dict[str, Any]) -> None:
    sec = _load(entry["variant"], entry["section"])
    assert sec.get("_aligned_by") == ALIGNED_BY


@pytest.mark.parametrize("entry", PLAN, ids=ENTRY_IDS)
def test_no_leaked_names_or_placeholder_rows(entry: dict[str, Any]) -> None:
    sec = _load(entry["variant"], entry["section"])
    names = [str(t.get("name", "")) for t in sec.get("tables") or []]
    for leaked in LEAKED_NAMES:
        assert leaked not in names, f"泄漏/假表名残留：{leaked}"
    for tbl in sec.get("tables") or []:
        for row in tbl.get("rows") or []:
            label = str(row.get("label", "")).replace(" ", "").replace("\u3000", "")
            assert label not in _NORM_PLACEHOLDER, f"{tbl.get('name')} 残留占位行「{row.get('label')}」"
            assert str(row.get("row_type", "")) != "header_label"


@pytest.mark.parametrize("entry", PLAN, ids=ENTRY_IDS)
def test_columns_headers_isomorphic_and_flat(entry: dict[str, Any]) -> None:
    sec = _load(entry["variant"], entry["section"])
    by_name = {str(t.get("name", "")): t for t in sec.get("tables") or []}
    for spec in entry["tables"]:
        tbl = by_name[spec["name"]]
        cols = tbl["columns"]
        assert [c["label"] for c in cols] == [c["label"] for c in spec["columns"]]
        assert [c["key"] for c in cols] == [c["key"] for c in spec["columns"]]
        assert tbl["headers"] == [c["label"] for c in spec["columns"]]
        assert cols[0].get("is_label") is True
        assert any(c.get("flat") for c in cols)
        assert not any(c.get("group") for c in cols)
        assert "_column_groups" not in tbl
        assert str(tbl.get("guidance", "")).strip()


def test_table_counts() -> None:
    expected = {
        ("K3", "listed"): 7, ("K3", "soe"): 6,
        ("K4", "listed"): 3, ("K4", "soe"): 1,
        ("K5", "listed"): 1, ("K5", "soe"): 1,
        ("K7", "listed"): 1, ("K7", "soe"): 2,
    }
    for entry in PLAN:
        sec = _load(entry["variant"], entry["section"])
        got = len(sec.get("tables") or [])
        want = expected[(entry["cycle"], entry["variant"])]
        assert got == want, f"{entry['cycle']} {entry['variant']} 表数 {got} ≠ {want}"


def test_k4_bond_cont_renamed() -> None:
    names = [str(t.get("name")) for t in _load("listed", "五、44")["tables"]]
    assert "短期应付债券（续）" in names
    assert "债券名称" not in names


def test_k3_leaked_names_renamed() -> None:
    listed = [str(t.get("name")) for t in _load("listed", "五、42")["tables"]]
    soe = [str(t.get("name")) for t in _load("soe", "八、42")["tables"]]
    assert "其中，账龄超过1年的重要其他应付款" in listed
    assert "项  目" not in listed
    assert "账龄超过1年的重要其他应付款项" in soe
    assert "其他应付款（表6）" not in soe


def test_k5_variant_column_counts_differ() -> None:
    """上市 4 列（末列「形成原因」）/ 国企 3 列 —— 附注模版口径，不得"统一"。"""
    assert len(_load("listed", "五、50")["tables"][0]["columns"]) == 4
    assert len(_load("soe", "八、55")["tables"][0]["columns"]) == 3
    assert _load("listed", "五、50")["tables"][0]["columns"][3]["key"] == "reason"


def test_k7_soe_grant_table() -> None:
    tables = _load("soe", "八、56")["tables"]
    grant = next(t for t in tables if t["name"] == "其中：递延收益-政府补助情况")
    assert len(grant["columns"]) == 10
    assert grant["columns"][0]["key"] == "grant_item"


def test_validator_catches_regression() -> None:
    """反向自检：摘 flat / 塞占位行 / 改列键，校验器必须报错（防守卫空转）。"""
    entry = next(e for e in PLAN if e["cycle"] == "K3" and e["variant"] == "soe")
    sec = _load(entry["variant"], entry["section"])

    broken = json.loads(json.dumps(sec, ensure_ascii=False))
    for col in broken["tables"][0]["columns"]:
        col.pop("flat", None)
    assert any("未显式 flat" in e for e in validate_section(broken, entry))

    broken2 = json.loads(json.dumps(sec, ensure_ascii=False))
    broken2["tables"][0]["rows"].append({"label": "可无限量添加行", "row_type": "data"})
    assert any("占位说明行" in e for e in validate_section(broken2, entry))

    broken3 = json.loads(json.dumps(sec, ensure_ascii=False))
    broken3["tables"][-1]["name"] = "其他应付款（表6）"
    errs = validate_section(broken3, entry)
    assert any("泄漏" in e for e in errs) or any("缺表" in e for e in errs)
