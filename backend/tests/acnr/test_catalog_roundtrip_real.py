"""T10：真实目录往返与 full_resolve 第 1 步身份判定（design §6.2 / §6.5，读真实目录、不 mock）。

- 每个非停用、父 sheet 在目录内的 cell：addr_id / formula_ref / uri / `cell:{sheet_code}!{A1}` 经 `full_resolve`
  回到自身；每个非停用 sheet：addr_id / `sheet:{sheet_code}` 回到自身。
- HEAD 可解析的静态写法（冻结夹具 `head_resolvable_static_writings.json`）：HEAD 解析到真实 sheet 的写法
  发布后仍解析到同一 sheet，或有登记处置——D5-1 / I1-1 / 审定表I1-1 三组经 alias_policy merge_into（带写法
  证据）并入父 sheet，其余 4 组登记 head_resolvable_errmatch 豁免（带 head_resolvable_at 与 writing）。
- 第 1 步多义 / 禁止别名：`found=False` + 错误码 + 中文原因 + `required_context` + 候选，不再按子串猜。
- 删除的旧启发式：父级在目录内而表找不到 → 未命中（不再直接拼接）；父级不在目录（自定义底稿）→ 原样
  拼接交给 L3 运行时条目（不是对目录的猜测）。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.services.acnr import exact_identity
from app.services.acnr.catalog import (
    _formula_ref_to_addr_id,
    _formula_ref_to_sheet_match,
    _uri_to_addr_id,
    get_catalog,
)
from app.services.acnr.resolver import full_resolve

_DATA = Path(__file__).resolve().parents[2] / "data" / "acnr"
_FIX = Path(__file__).resolve().parent / "fixtures"


def _resolve(**kw):
    return asyncio.run(full_resolve(**kw))


async def _resolve_many(calls: list[dict]) -> list:
    return [await full_resolve(**kw) for kw in calls]


def _live_cells():
    cat = get_catalog()
    return [c for c in cat.cells_by_addr_id.values()
            if not c.get("deprecated") and c.get("parent_addr_id") in cat.sheets_by_addr_id]


def test_live_counts_are_nonzero():
    """防空转：目录里非停用 cell / sheet 都有（发布批次现算 435 / 1220）。"""
    cat = get_catalog()
    assert len(_live_cells()) == 435
    assert sum(1 for s in cat.sheets_by_addr_id.values() if not s.get("deprecated")) == 1220


def test_every_live_cell_round_trips_through_full_resolve():
    cat = get_catalog()
    calls, expect = [], []
    for c in _live_cells():
        code = cat.sheets_by_addr_id[c["parent_addr_id"]]["sheet_code"]
        for kw in ({"addr_id": c["addr_id"]}, {"formula_ref": c["formula_ref"]}, {"uri": c["uri"]},
                   {"index_ref": f"cell:{code}!{c['cell_address']}"}):
            calls.append(kw)
            expect.append(c["addr_id"])
    results = asyncio.run(_resolve_many(calls))
    bad = [(kw, r.found, r.addr_id) for kw, r, want in zip(calls, results, expect)
           if not (r.found and r.addr_id == want and r.entry_type == "cell")]
    assert not bad, f"往返失败 {len(bad)} 处，前 5：{bad[:5]}"


def test_every_live_sheet_round_trips_through_full_resolve():
    cat = get_catalog()
    sheets = [s for s in cat.sheets_by_addr_id.values() if not s.get("deprecated")]
    calls = [kw for s in sheets for kw in ({"addr_id": s["addr_id"]}, {"index_ref": f"sheet:{s['sheet_code']}"})]
    results = asyncio.run(_resolve_many(calls))
    want = [s["addr_id"] for s in sheets for _ in (0, 1)]
    bad = [(kw, r.addr_id) for kw, r, w in zip(calls, results, want) if not (r.found and r.addr_id == w)]
    assert not bad, f"sheet 往返失败 {len(bad)} 处，前 5：{bad[:5]}"


def _head_rows() -> list[dict]:
    fx = json.loads((_FIX / "head_resolvable_static_writings.json").read_text(encoding="utf-8"))
    return [w for w in fx["static_writings"] + fx["pg_writings"] if w.get("head_sheet_addr_id")]


def _registered_errmatch() -> dict[tuple[str, str], str]:
    ack = json.loads((_DATA / "sources" / "acknowledgements.json").read_text(encoding="utf-8"))
    return {(e["writing"]["wp_code"], e["writing"]["sheet"]): e["head_resolvable_at"]
            for e in ack["entries"] if e.get("kind") == "head_resolvable_errmatch"}


def _merge_writings() -> dict[tuple[str, str], str]:
    ap = json.loads((_DATA / "sources" / "alias_policy.json").read_text(encoding="utf-8"))
    return {(w["wp_code"], w["sheet"]): e["target"]
            for e in ap["entries"] if e.get("disposition") == "merge_into" for w in e.get("writings") or []}


def test_head_resolvable_writings_still_resolve_or_are_registered():
    """HEAD 解析到真实 sheet 的写法：发布后解析到同一 sheet，或登记了错配豁免（design §6.5）。"""
    errmatch = _registered_errmatch()
    merged = _merge_writings()
    unresolved, wrong_ack, regress = [], [], []
    for w in _head_rows():
        key = (w["args"][0], w["args"][1])
        sheet_addr = "/".join((_formula_ref_to_addr_id(w["writing"]) or "").split("/")[:2]) or None
        if sheet_addr == w["head_sheet_addr_id"]:
            continue
        if key in errmatch:
            if errmatch[key] != w["head_sheet_addr_id"]:
                wrong_ack.append((w["where"], errmatch[key], w["head_sheet_addr_id"]))
            continue
        if sheet_addr is None:
            unresolved.append((w["source"], w["where"], w["writing"]))
        elif sheet_addr != w.get("new_sheet_addr_id") and merged.get(key) != sheet_addr:
            # 改判只允许是 T01 冻结的 exact_identity 判定（同父同名组借名父级 → 名称所属 sheet）
            regress.append((w["where"], w["writing"], w["head_sheet_addr_id"], sheet_addr))
    assert not unresolved, f"HEAD 能解析、现在未命中且无登记处置：{unresolved}"
    assert not wrong_ack, f"错配豁免的 head_resolvable_at 与 HEAD 结果不符：{wrong_ack}"
    assert not regress, f"解析到 HEAD 与冻结判定都不认可的 sheet：{regress[:5]}"


def test_head_resolvable_dispositions_are_exactly_design_groups():
    """3 组并入 + 4 组错配豁免，恰为夹具的 7 组 / 14 处（结构性计数，与设计 §6.5 逐组相等）。"""
    fx = json.loads((_FIX / "head_resolvable_static_writings.json").read_text(encoding="utf-8"))
    groups = {tuple(g) for g in fx["errmatch_groups"]}
    merged = {k for k in _merge_writings()}
    errmatch = set(_registered_errmatch())
    assert merged == {("D5", "D5-1"), ("I1", "I1-1"), ("I1", "审定表I1-1")}
    assert errmatch == groups - merged
    assert len(errmatch) == 4
    for wp, sheet in merged:
        sm = exact_identity.sheet_of(wp, sheet)
        assert sm.ok and sm.match_kind == "alias", (wp, sheet, sm)


def _forbidden_sample() -> tuple[str, str]:
    raw = json.loads((_DATA / "global_catalog.json").read_text(encoding="utf-8"))
    forbidden = (raw.get("alias_policy") or {}).get("forbidden") or {}
    assert forbidden, "目录顶层 alias_policy.forbidden 为空"
    parent = sorted(forbidden)[0]
    return parent, sorted(forbidden[parent])[0]


def _ambiguous_sample() -> tuple[str, str]:
    """现算一个父级内多张 sheet 同名、编码词元也裁不出的名称（design §1.2 的 8 组之一）。"""
    cat = get_catalog()
    by_parent: dict[str, dict[str, int]] = {}
    for s in cat.sheets_by_addr_id.values():
        by_parent.setdefault(s["parent_wp_code"], {}).setdefault(s.get("sheet_name") or "", 0)
        by_parent[s["parent_wp_code"]][s.get("sheet_name") or ""] += 1
    for parent, names in sorted(by_parent.items()):
        for name, n in sorted(names.items()):
            if n >= 2 and name and exact_identity.sheet_of(parent, name).state == "ambiguous":
                return parent, name
    raise AssertionError("目录里没有多义名称（与设计 §1.2 的 8 组不符）")


def test_step1_forbidden_alias_returns_reason_and_candidates():
    parent, alias = _forbidden_sample()
    r = _resolve(formula_ref=f"WP('{parent}','{alias}','A1')")
    assert r.found is False and r.error == "alias_forbidden"
    assert r.reason and "请改用 sheet 编码" in r.reason
    assert r.required_context == ["sheet_code"]
    assert r.candidates and all(c["addr_id"].startswith(parent + "/") for c in r.candidates)


def test_step1_ambiguous_name_returns_reason_and_candidates():
    parent, name = _ambiguous_sample()
    for kw in ({"formula_ref": f"WP('{parent}','{name}','A1')"}, {"uri": f"wp://{parent}/{name}#A1"}):
        r = _resolve(**kw)
        assert r.found is False and r.error == "ambiguous", (kw, r)
        assert r.reason and "对应多张表" in r.reason
        assert r.required_context == ["sheet_code"]
        assert 2 <= len(r.candidates) <= 5
    # 薄壳：多义返回 None
    assert _formula_ref_to_addr_id(f"WP('{parent}','{name}','A1')") is None
    assert _uri_to_addr_id(f"wp://{parent}/{name}#A1") is None


def test_substring_and_concat_heuristics_removed():
    """父级在目录内、表名只靠子串才能命中 → 未命中；不再直接拼成假地址。"""
    ident = _formula_ref_to_sheet_match("WP('A13','A13-3 评价识别出的错报','A10')")
    assert ident.addr_id is None and ident.match.state == "not_found"
    assert _formula_ref_to_addr_id("WP('D2','不存在的表','E100')") is None
    assert _uri_to_addr_id("wp://D2/不存在的表#E100") is None
    r = _resolve(formula_ref="WP('D2','不存在的表','E100')")
    assert r.found is False and r.addr_id is None


def test_custom_workpaper_writing_passes_through_for_runtime_lookup():
    """父级不在目录（自定义底稿）：原样拼接交给 L3，与 HEAD 一致（夹具 23 条 wp_not_in_catalog 不变）。"""
    assert _formula_ref_to_addr_id("WP('CUST-01','CUST-01','B7')") == "CUST-01/CUST-01/B7"
    assert _formula_ref_to_addr_id("WP('PWXD9ZXL','B5')") == "PWXD9ZXL/B5"
    rows = [w for w in json.loads((_FIX / "head_resolvable_static_writings.json").read_text(encoding="utf-8"))
            ["static_writings"] if w.get("new_state") == "wp_not_in_catalog"]
    assert rows and all(_formula_ref_to_addr_id(w["writing"]) == w["head_addr_id"] for w in rows)


@pytest.mark.parametrize("sheet_code", ["K14", "K15", "K16", "K17", "K18"])
def test_deprecated_sheet_resolves_with_replacement(sheet_code):
    r = _resolve(addr_id=f"{sheet_code}/{sheet_code}")
    assert r.found and r.deprecated is True and r.replaced_by
    assert r.reason.startswith("该地址已停用，建议改用")
    target = _resolve(addr_id=r.replaced_by)
    assert target.found and not target.deprecated
