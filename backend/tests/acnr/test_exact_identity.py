"""T02：唯一精确身份判定 exact_identity（design §6.2）。

6 步规则逐例 + name_owner 对真实目录 78 组现算（70 唯一 / 8 None）+
cell_of 的 A1 与 in_catalog + 父级禁止集合不相交不变量。
"""
from __future__ import annotations

import pytest

from app.services.acnr import exact_identity as ei
from app.services.acnr.catalog import CatalogIndex, get_catalog


# ─── 合成索引工厂 ───────────────────────────────────────────────────────────


def _idx(sheets: list[dict], cells: list[dict] | None = None) -> CatalogIndex:
    return CatalogIndex({"version": "1", "registry_version": "20260101000000",
                         "sheets": sheets, "cells": cells or []})


def _sheet(parent: str, code: str, name: str, aliases: list[str] | None = None) -> dict:
    d = {"addr_id": f"{parent}/{code}", "domain": "wp", "parent_wp_code": parent,
         "sheet_code": code, "sheet_name": name}
    if aliases:
        d["sheet_name_aliases"] = aliases
    return d


# ─── 6 步规则逐例 ───────────────────────────────────────────────────────────


def test_step1_wp_not_in_catalog():
    idx = _idx([_sheet("D2", "D2-1", "明细表")])
    r = ei.sheet_of("ZZZ", "随便", index=idx)
    assert r.state == "wp_not_in_catalog"
    assert "ZZZ" in r.reason


def test_step1_wp_code_is_sheet_code_empty_text_returns_that_sheet():
    idx = _idx([_sheet("D2", "D2-1", "明细表")])
    r = ei.sheet_of("D2-1", "", index=idx)
    assert r.ok and r.entry["addr_id"] == "D2/D2-1"


def test_step2_sheet_code_exact():
    idx = _idx([_sheet("D2", "D2-1", "明细表"), _sheet("D2", "D2-2", "审定表")])
    r = ei.sheet_of("D2", "D2-2", index=idx)
    assert r.ok and r.match_kind == "sheet_code" and r.entry["sheet_code"] == "D2-2"


def test_step3_forbidden_alias():
    # 同一父级下平台名「应收票据审定表」对应 D1 与 D1-1 两张表 → 禁止别名
    sheets = [
        _sheet("D1", "D1", "审定表D1", aliases=["应收票据审定表"]),
        _sheet("D1", "D1-1", "审定表D1-1", aliases=["应收票据审定表"]),
    ]
    idx = _idx(sheets)
    r = ei.sheet_of("D1", "应收票据审定表", index=idx)
    assert r.state == "alias_forbidden"
    assert "D1" in r.reason and "D1-1" in r.reason
    assert r.required_context == ["sheet_code"]


def test_step4_sheet_name_unique():
    idx = _idx([_sheet("D2", "D2-1", "明细表D2-1"), _sheet("D2", "D2-2", "审定表D2-2")])
    r = ei.sheet_of("D2", "审定表D2-2", index=idx)
    assert r.ok and r.match_kind == "sheet_name" and r.entry["sheet_code"] == "D2-2"


def test_step5_alias_unique_when_no_name_hit():
    sheets = [
        _sheet("D2", "D2-1", "明细表D2-1"),
        _sheet("D2", "D2-2", "审定表D2-2", aliases=["应收账款审定表"]),
    ]
    idx = _idx(sheets)
    r = ei.sheet_of("D2", "应收账款审定表", index=idx)
    assert r.ok and r.match_kind == "alias" and r.entry["sheet_code"] == "D2-2"


def test_step6_code_token_picks_longest_unique():
    # 父级 H1 下「审定表H1-1」同时是 H1 与 H1-1 的 sheet_name（借名）
    sheets = [
        _sheet("H1", "H1", "审定表H1-1"),
        _sheet("H1", "H1-1", "审定表H1-1"),
    ]
    idx = _idx(sheets)
    r = ei.sheet_of("H1", "审定表H1-1", index=idx)
    assert r.ok and r.match_kind == "code_token"
    assert r.entry["sheet_code"] == "H1-1"  # 名称所属 sheet，非借名父级


def test_step7_ambiguous_when_multi_name_and_no_token():
    # 两张表同名、名称里不含任一完整编码词元 → ambiguous
    sheets = [
        _sheet("A21", "A21-1", "底稿目录"),
        _sheet("A21", "A21-2", "底稿目录"),
    ]
    idx = _idx(sheets)
    r = ei.sheet_of("A21", "底稿目录", index=idx)
    assert r.state == "ambiguous"
    assert r.required_context == ["sheet_code"]
    assert set(r.candidates) == {"A21/A21-1", "A21/A21-2"}


def test_not_found():
    idx = _idx([_sheet("D2", "D2-1", "明细表D2-1")])
    r = ei.sheet_of("D2", "不存在的表", index=idx)
    assert r.state == "not_found"


# ─── name_owner 对真实目录 78 组现算 ─────────────────────────────────────────

_EXPECTED_NONE_GROUPS = {
    ("A21", "底稿目录"), ("A22", "底稿目录"), ("A23", "底稿目录"),
    ("A3", "Word附注"), ("A3", "已审比率分析"),
    ("B50", "相关资源"), ("F2", "底稿目录"), ("S32", "S32程序表"),
}


def _same_name_groups(cat: CatalogIndex) -> dict[tuple[str, str], list[dict]]:
    groups: dict[tuple[str, str], list[dict]] = {}
    for s in cat.sheets_by_addr_id.values():
        groups.setdefault((s.get("parent_wp_code", ""), s.get("sheet_name", "")), []).append(s)
    return {k: v for k, v in groups.items() if len(v) > 1}


def test_name_owner_78_groups_real_catalog():
    cat = get_catalog()
    groups = _same_name_groups(cat)
    assert len(groups) == 78, f"同名组数变了：{len(groups)}"
    none_groups = set()
    unique = 0
    for (parent, name), _members in groups.items():
        owner = ei.name_owner(parent, name, index=cat)
        if owner is None:
            none_groups.add((parent, name))
        else:
            unique += 1
    assert none_groups == _EXPECTED_NONE_GROUPS, f"多义组变了：{none_groups}"
    assert unique == 70


def test_name_owner_same_name_group_owner_is_its_own_sheet():
    # 70 个有唯一归属的组，归属 sheet 的 sheet_name 必须 == 该名（编码词元命中本表）
    cat = get_catalog()
    for (parent, name), _members in _same_name_groups(cat).items():
        if (parent, name) in _EXPECTED_NONE_GROUPS:
            continue
        owner = ei.name_owner(parent, name, index=cat)
        assert owner is not None
        # 归属的 sheet 自身名称即为该名（借名父级也叫这个名，但词元规则选到名称所属 sheet）
        assert owner.get("sheet_name") == name
        # 编码词元在名称里
        assert ei._code_token_in(owner["sheet_code"], name)


# ─── cell_of ────────────────────────────────────────────────────────────────


def test_cell_of_bad_a1():
    idx = _idx([_sheet("D2", "D2-1", "明细表D2-1")])
    r = ei.cell_of("D2", "明细表D2-1", "not-a1", index=idx)
    assert r.state == "bad_a1"


def test_cell_of_ok_lowercase_normalized_and_in_catalog_flag():
    sheets = [_sheet("D2", "D2-1", "明细表D2-1")]
    cells = [{"addr_id": "D2/D2-1/C10", "parent_addr_id": "D2/D2-1",
              "domain": "wp", "cell_address": "C10", "formula_ref": "x"}]
    idx = _idx(sheets, cells)
    r = ei.cell_of("D2", "明细表D2-1", "c10", index=idx)
    assert r.ok and r.addr_id == "D2/D2-1/C10" and r.in_catalog is True
    r2 = ei.cell_of("D2", "明细表D2-1", "Z99", index=idx)
    assert r2.ok and r2.addr_id == "D2/D2-1/Z99" and r2.in_catalog is False


def test_cell_of_sheet_unresolved_propagates():
    idx = _idx([_sheet("A21", "A21-1", "底稿目录"), _sheet("A21", "A21-2", "底稿目录")])
    r = ei.cell_of("A21", "底稿目录", "C10", index=idx)
    assert r.state == "ambiguous"


def test_all_real_cells_cell_of_roundtrip():
    """真实目录每个登记 cell 的 sheet 部分都能被 name_owner/sheet_of 用其 sheet_code 命中。"""
    cat = get_catalog()
    for c in list(cat.cells_by_addr_id.values()):
        parent_addr = c.get("parent_addr_id", "")
        if "/" not in parent_addr:
            continue
        parent_wp, sheet_code = parent_addr.split("/", 1)
        a1 = c.get("cell_address")
        if not a1:
            continue  # semantic_only cell 不走 A1 路径
        r = ei.sheet_of(parent_wp, sheet_code, index=cat)
        # 孤儿 cell 的父 sheet 当前不在目录中（T05/T06 补登）→ 允许 wp_not_in_catalog
        if parent_addr in cat.sheets_by_addr_id:
            assert r.ok, f"{parent_addr} sheet_of by code failed: {r.state}"


# ─── 不变量 ──────────────────────────────────────────────────────────────────


def test_forbidden_disjoint_invariant_holds_on_real_catalog():
    cat = get_catalog()
    assert ei.forbidden_disjoint_violations(cat) == []


def test_forbidden_disjoint_detects_violation():
    # 构造：禁止别名「X」同时又是某 sheet 的 sheet_name → 违反不变量
    sheets = [
        _sheet("D1", "D1", "X", aliases=["X"]),
        _sheet("D1", "D1-1", "审定表D1-1", aliases=["X"]),
    ]
    idx = _idx(sheets)
    assert ei.forbidden_disjoint_violations(idx) != []
