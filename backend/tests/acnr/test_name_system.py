"""T06：名称体系 loader —— 平台索引名并入别名与冲突分类（需求 5 / D4 / R2-F2）。

守卫口径（对真实 wp_account_mapping.json + global_catalog.json 现算，变了即红）：
  1. loader 结构：返回 WpNameAliasResult，forbidden/parent_qualified/aliases 类型正确。
  2. 同父一名多码（禁止别名）现算恰 9 组，且组成员与 design §6.3 逐项相等。
  3. 只跨父级重名（父级限定）现算恰 6 组，且每父唯一。
  4. 往返（§6.3）：把可并入别名合并进目录副本后，`sheet_of(父级, 平台名)` 回到本 sheet；
     把禁止别名并入后，`sheet_of(父级, 平台名)` 返回 alias_forbidden（拒绝）。
  5. 与模板名相同的 wp_name 不并入别名（§6.3）。
  6. loader 只读、不触碰目录单例、不读 DB（纯函数：传入 sheets 序列）。
  7. 生成器名称规则 `catalog_names`（§6.3）：449 个非孤儿 cell 的 formula_ref / uri 全部往返（模板名归属本
     sheet 用模板名，否则用 sheet_code）；同父一名多码 9 组写进顶层 alias_policy.forbidden 并被拒绝。
  8. §6.4 的 47 格三路判定：openpyxl 现算证据与 cell_verdicts 记录逐条相等（31 行有文字 + 2 行空 = 33 格
     keep_semantic_unverified，14 格超范围 deprecate）；apply_cell_verdicts 按判定改写 cell。

变异（在 verify_wt 做）：某禁止别名组改成单码（删一条 wp_code 行）→ forbidden 组数红 / 往返
禁止别名拒绝用例红；某可并入别名改回与模板名相同 → 往返命中数变化红。
"""
from __future__ import annotations

import collections
import copy
import json
import re
import sys
from pathlib import Path

from app.services.acnr import exact_identity
from app.services.acnr.catalog import CatalogIndex
from app.services.acnr.exact_identity import sheet_of

sys.path.insert(0, str(Path(__file__).resolve().parent))  # _seed_name_mismatch_evidence（与一次性写入脚本同一实现）
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


# ─── 7. 生成器名称规则（catalog_names，design §6.3）────────────────────────────


def _named_copy() -> tuple[dict, object, object]:
    from app.services.acnr import catalog_names

    cat = copy.deepcopy(_load_catalog())
    cat.pop("alias_policy", None)  # 已发布目录自带 alias_policy；去掉它才能证明是名称规则写出来的（段六复审 M5）
    merged = catalog_names.merge_platform_names(cat)
    named = catalog_names.apply_cell_names(cat)
    return cat, merged, named


def _wp_args(ref: str) -> list[str]:
    return re.findall(r"'([^']*)'", ref or "")


def test_generator_name_rules_roundtrip_all_non_orphan_cells():
    """449 个非孤儿 cell 的 formula_ref 与 uri 经 exact_identity 都回到本 cell（含 4 个改用编码的）。"""
    cat, _merged, named = _named_copy()
    idx = CatalogIndex(cat)
    sheet_ids = {s["addr_id"] for s in cat["sheets"]}
    checked, fail = 0, []
    for c in cat["cells"]:
        if c["parent_addr_id"] not in sheet_ids or c.get("cell_address") is None:
            continue
        checked += 1
        a = _wp_args(c["formula_ref"])
        fm = exact_identity.cell_of(a[0], a[1], a[2], index=idx) if len(a) == 3 else None
        p, rest = c["uri"][len("wp://"):].split("/", 1)
        s, a1 = rest.rsplit("#", 1)
        um = exact_identity.cell_of(p, s, a1, index=idx)
        if fm is None or not fm.ok or fm.addr_id != c["addr_id"] or not um.ok or um.addr_id != c["addr_id"]:
            fail.append((c["addr_id"], c["formula_ref"], c["uri"]))
    # 发布前目录：474 − 25 孤儿 = 449；发布后孤儿父 sheet 已补登，25 个停用 cell 也在其中（共 474）；
    # spec wp-deeplink-locate-coverage-closure 起另有 65 个模板核对坐标（共 539，停用格仍在其中）
    assert checked == 539, checked
    assert not fail, f"名称规则往返失败 {len(fail)} 条：{fail[:10]}"
    assert named.by_sheet_code >= 1, "防空转：应有模板名不归属本 sheet、改用 sheet_code 的 cell（如 F2/F2-34）"
    assert named.by_template_name + named.by_sheet_code == checked


def test_generator_writes_forbidden_alias_policy_nine_groups():
    """同父一名多码 9 组写进目录顶层 alias_policy.forbidden，且仅凭它（不进 sheet 别名）即被第 3 步拒绝。"""
    cat, merged, _ = _named_copy()
    rows = {(p, a): codes for p, by in cat["alias_policy"]["forbidden"].items() for a, codes in by.items()}
    assert rows == _EXPECTED_FORBIDDEN
    idx = CatalogIndex(cat)
    for (parent, name), codes in _EXPECTED_FORBIDDEN.items():
        for code in codes:
            assert name not in (next(s for s in cat["sheets"] if s["sheet_code"] == code).get("sheet_name_aliases") or [])
        assert sheet_of(parent, name, index=idx).state == "alias_forbidden", (parent, name)
    assert len(merged.parent_qualified) == 6


# ─── 8. §6.4 种子名不一致 47 格三路判定（cell_verdicts，与现算逐项相等）────────────


def test_seed_name_mismatch_verdicts_recomputed():
    from _seed_name_mismatch_evidence import seed_name_mismatch_cells, verdict_record, with_template_evidence

    from app.services.acnr.loaders.from_sheet_verdicts import load_sheet_verdicts

    v = load_sheet_verdicts()
    added = {s.sheet_code for s in v.add_platform_sheets()}
    rows = with_template_evidence(seed_name_mismatch_cells(_load_sheets(), added))
    assert len(rows) == 47 and len({r["sheet_code"] for r in rows}) == 13
    assert collections.Counter(r["class"] for r in rows) == {"in_range_row_text": 31, "in_range_row_empty": 2, "out_of_range": 14}
    recorded = json.loads((_ACNR / "sources" / "sheet_verdicts.json").read_text(encoding="utf-8"))["cell_verdicts"]
    recorded = {c["addr_id"]: c for c in recorded if c.get("kind") == "seed_name_mismatch"}
    expected = {r["addr_id"]: verdict_record(r) for r in rows}
    assert set(recorded) == set(expected), sorted(set(recorded) ^ set(expected))
    diffs = [aid for aid in expected if recorded[aid] != expected[aid]]
    assert not diffs, f"cell_verdicts 记录与现算不符：{diffs[:10]}"
    deprecated = sorted(a for a, r in expected.items() if r["verdict"] == "deprecate")
    assert deprecated == sorted([
        "F3/F3-6/E30", "F4/F4-3/E50", "F4/F4-3/F50", "F4/F4-3/G50", "F4/F4-3/H50", "G14/G14-2/B50",
        "G14/G14-2/E40", "G14/G14-2/F40", "G8/G8-3/B35", "G8/G8-3/E30", "J1/J1-3/F30", "J1/J1-3/G30",
        "J1/J1-3/H30", "J1/J1-3/I30",
    ])


def test_apply_cell_verdicts_three_way():
    from app.services.acnr import catalog_names
    from app.services.acnr.loaders.from_sheet_verdicts import load_sheet_verdicts

    cat = copy.deepcopy(_load_catalog())
    rows = [dict(addr_id=c.addr_id, verdict=c.verdict, replaced_by=c.replaced_by) for c in load_sheet_verdicts().cell_verdicts]
    catalog_names.apply_cell_verdicts(cat, rows)
    by_id = {c["addr_id"]: c for c in cat["cells"]}
    keep = [r for r in rows if r["verdict"] == "keep_semantic_unverified"]
    dep = [r for r in rows if r["verdict"] == "deprecate"]
    # 停用 = T05 孤儿 25 + T06 超范围 14 + spec wp-deeplink-locate-coverage-closure 与模板不符 402
    assert (len(keep), len(dep)) == (33, 39 + 402)
    for r in keep:
        c = by_id[r["addr_id"]]
        assert c["semantic_label"] is None and c["cell_label"] == f"{c['cell_address']}（语义待核对）" and not c.get("deprecated")
    for r in dep:
        c = by_id[r["addr_id"]]
        assert c["deprecated"] is True and c["replaced_by"] == r["replaced_by"]
        # 指父 sheet，或（仅本 spec 改指的）同一张表上模板核对后的新坐标
        assert r["replaced_by"] == c["parent_addr_id"] or r["replaced_by"].rsplit("/", 1)[0] == c["parent_addr_id"], r


# ─── 6. 纯函数：传空 sheets 不抛、不读目录单例 ───────────────────────────────


def test_empty_sheets_yields_empty_result():
    res = load_wp_account_mapping_aliases([])
    assert res.forbidden == {}
    assert res.parent_qualified == {}
    assert res.aliases == {}
