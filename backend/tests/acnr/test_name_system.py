"""T06：名称体系 loader —— 平台索引名并入别名与冲突分类（需求 5 / D4 / R2-F2）。

守卫口径（对真实 wp_account_mapping.json + global_catalog.json 现算，变了即红）：
  1. loader 结构：返回 WpNameAliasResult，forbidden/parent_qualified/aliases 类型正确。
  2. 同父一名多码（禁止别名）现算恰 9 组，且组成员与 design §6.3 逐项相等。
  3. 只跨父级重名（父级限定）现算恰 6 组，且每父唯一。
  4. 往返（§6.3）：把可并入别名合并进目录副本后，`sheet_of(父级, 平台名)` 回到本 sheet；
     把禁止别名并入后，`sheet_of(父级, 平台名)` 返回 alias_forbidden（拒绝）。
  5. 与模板名相同的 wp_name 不并入别名（§6.3）。
  6. loader 只读、不触碰目录单例、不读 DB（纯函数：传入 sheets 序列）。

变异（在 verify_wt 做）：某禁止别名组改成单码（删一条 wp_code 行）→ forbidden 组数红 / 往返
禁止别名拒绝用例红；某可并入别名改回与模板名相同 → 往返命中数变化红。
"""
from __future__ import annotations

import json
from pathlib import Path

from app.services.acnr.catalog import CatalogIndex
from app.services.acnr.exact_identity import sheet_of
from app.services.acnr.loaders.from_wp_account_mapping import (
    WpNameAliasResult,
    load_wp_account_mapping_aliases,
)

_BACKEND = Path(__file__).resolve().parents[2]  # backend/
_DATA = _BACKEND / "data"
_ACNR = _DATA / "acnr"

# design §6.3 / §1.2 现算：同父一名多码 9 组（禁止别名）
_EXPECTED_FORBIDDEN: dict[tuple[str, str], list[str]] = {
    ("A18", "向监管部门报送审计小结的函"): ["A18", "A18-1"],
    ("A26", "专业技术委员会业务报告审核提交资料清单"): ["A26", "A26-1"],
    ("A27", "IT审计总结备忘录"): ["A27", "A27-1"],
    ("D1", "应收票据审定表"): ["D1", "D1-1"],
    ("D3", "预收账款审定表"): ["D3", "D3-1"],
    ("F1", "预付账款审定表"): ["F1", "F1-1"],
    ("F3", "应付票据审定表"): ["F3", "F3-1"],
    ("F4", "应付账款审定表"): ["F4", "F4-1"],
    ("F5", "营业成本审定表"): ["F5", "F5-1"],
}

# design §6.3 / §1.2 现算：只跨父级重名 6 组（父级限定别名）
_EXPECTED_PARENT_QUALIFIED_NAMES = {
    "函证结果汇总",
    "差异调节",
    "替代程序",
    "核实被函证单位",
    "财务报告文件包",
    "跟函控制",
}


def _load_sheets() -> list[dict]:
    catalog = json.loads((_ACNR / "global_catalog.json").read_text(encoding="utf-8"))
    return catalog["sheets"]


def _load_catalog() -> dict:
    return json.loads((_ACNR / "global_catalog.json").read_text(encoding="utf-8"))


def _build_merged_index(res: WpNameAliasResult, catalog: dict) -> tuple[CatalogIndex, dict[str, dict]]:
    """把 loader 产出的别名（可并入 + 禁止）并进目录副本，返回 index 与 code→entry。"""
    merged = [dict(s) for s in catalog["sheets"]]
    code_to_entry = {s["sheet_code"]: s for s in merged}

    def _add(code: str, name: str) -> None:
        e = code_to_entry.get(code)
        if e is None:
            return
        cur = list(e.get("sheet_name_aliases", []) or [])
        if name not in cur:
            cur.append(name)
        e["sheet_name_aliases"] = cur

    for code, names in res.aliases.items():
        for n in names:
            _add(code, n)
    # 禁止别名也并入（触发现场推导的 forbidden 判定：同父同名 ≥2 码）
    for (parent, name), codes in res.forbidden.items():
        for code in codes:
            _add(code, name)

    idx = CatalogIndex({
        "version": "1",
        "registry_version": "test",
        "sheets": merged,
        "cells": catalog.get("cells", []),
    })
    return idx, code_to_entry


# ─── 1. 结构 ───────────────────────────────────────────────────────────────


def test_result_shape_is_pure_function():
    sheets = _load_sheets()
    res = load_wp_account_mapping_aliases(sheets)
    assert isinstance(res, WpNameAliasResult)
    assert isinstance(res.forbidden, dict)
    assert isinstance(res.parent_qualified, dict)
    assert isinstance(res.aliases, dict)
    # aliases 值为去重排序 list
    for code, names in res.aliases.items():
        assert isinstance(names, list)
        assert names == sorted(set(names))


# ─── 2. 同父一名多码（禁止别名）恰 9 组 ───────────────────────────────────────


def test_forbidden_alias_groups_are_exactly_nine():
    sheets = _load_sheets()
    res = load_wp_account_mapping_aliases(sheets)
    assert len(res.forbidden) == 9, (
        f"同父一名多码应恰 9 组，现算 {len(res.forbidden)}：{sorted(res.forbidden)}"
    )
    assert res.forbidden == _EXPECTED_FORBIDDEN, (
        "禁止别名组成员与 design §6.3 现算不一致：\n"
        f"现算 {dict(sorted(res.forbidden.items()))}\n"
        f"期望 {dict(sorted(_EXPECTED_FORBIDDEN.items()))}"
    )


# ─── 3. 只跨父级重名（父级限定）恰 6 组 ───────────────────────────────────────


def test_parent_qualified_groups_are_exactly_six():
    sheets = _load_sheets()
    res = load_wp_account_mapping_aliases(sheets)
    assert len(res.parent_qualified) == 6, (
        f"只跨父级重名应恰 6 组，现算 {len(res.parent_qualified)}：{sorted(res.parent_qualified)}"
    )
    assert set(res.parent_qualified) == _EXPECTED_PARENT_QUALIFIED_NAMES
    # 每父唯一
    for name, per_parent in res.parent_qualified.items():
        assert len(per_parent) >= 2
        for parent, code in per_parent.items():
            assert isinstance(code, str) and code


# ─── 4. 往返与禁止别名拒绝 ────────────────────────────────────────────────────


def test_mergeable_aliases_roundtrip_to_self():
    catalog = _load_catalog()
    res = load_wp_account_mapping_aliases(catalog["sheets"])
    idx, code_to_entry = _build_merged_index(res, catalog)

    fail = []
    for code, names in res.aliases.items():
        e = code_to_entry[code]
        parent = e.get("parent_wp_code", "")
        for name in names:
            sm = sheet_of(parent, name, index=idx)
            if not (sm.ok and sm.entry and sm.entry.get("sheet_code") == code):
                fail.append((parent, name, code, sm.state))
    assert not fail, f"可并入别名往返失败（应回到本 sheet）：{fail[:10]}"


def test_forbidden_aliases_rejected():
    catalog = _load_catalog()
    res = load_wp_account_mapping_aliases(catalog["sheets"])
    idx, _ = _build_merged_index(res, catalog)

    fail = []
    for (parent, name), codes in res.forbidden.items():
        sm = sheet_of(parent, name, index=idx)
        if sm.state != "alias_forbidden":
            fail.append((parent, name, sm.state))
    assert not fail, f"禁止别名应被 sheet_of 第 3 步拒绝（alias_forbidden）：{fail}"


# ─── 5. 与模板名相同的 wp_name 不并入 ────────────────────────────────────────


def test_same_name_as_template_not_aliased():
    """wp_name == sheet_name 的 wp_code 不产生别名（§6.3）。"""
    sheets = _load_sheets()
    by_code = {s["sheet_code"]: s for s in sheets}
    res = load_wp_account_mapping_aliases(sheets)
    # E1 的 wp_name「货币资金」与 sheet_name「货币资金」相同 → 不应作别名
    # 现算核对：若某 sheet 的所有别名里出现了与它 sheet_name 相同的字符串即失败
    for code, names in res.aliases.items():
        sheet_name = by_code.get(code, {}).get("sheet_name", "")
        assert sheet_name not in names, (
            f"{code} 的别名里不应含与模板名相同的「{sheet_name}」"
        )


# ─── 6. 纯函数：传空 sheets 不抛、不读目录单例 ───────────────────────────────


def test_empty_sheets_yields_empty_result():
    res = load_wp_account_mapping_aliases([])
    assert res.forbidden == {}
    assert res.parent_qualified == {}
    assert res.aliases == {}
