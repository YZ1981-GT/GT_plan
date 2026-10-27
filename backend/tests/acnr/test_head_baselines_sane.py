"""T01：HEAD 现算基线四夹具的健全性守卫（tasks T01 / design §1.2、§6.5）。

口径（关键）：本 spec T01 明确「实施时以当时 HEAD 现算为准，变化记入本任务」。
设计 §1.2 的 372/26/2599 等数字来自设计阶段的人工策展分析工具，该工具不在仓库，
无法机械复现其人工口径。因此本守卫不绑定设计的固定数字，而是：

  1. 断言四份夹具存在且非空；
  2. 用当前 HEAD 的 catalog / exact_identity **重新机械现算**同名组与 resolvable
     三态，逐条与夹具比对（内部一致性，防夹具与代码漂移）；
  3. 断言 head_resolvable 的 errmatch 条目逐条有 `head_resolvable_at` 且指向真实 sheet；
  4. 断言分类计数自洽（unchanged + reclassified + ambiguous == count）。

同名组 78/70/8 这一项与设计 §1.2 完全一致（T02 已独立验证），这里作为交叉校验保留。

夹具由一次性脚本 tmp_acnr_foundation/probes/export_head_baselines.py 导出。
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest

from app.services.acnr import catalog as cat_mod
from app.services.acnr import exact_identity as ei

FIX = Path(__file__).resolve().parent / "fixtures"


def _load(name: str) -> dict:
    p = FIX / name
    assert p.exists(), f"缺少基线夹具 {name}（先跑 export_head_baselines.py）"
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def catalog():
    return cat_mod.get_catalog()


# ── 1. 四夹具非空 ───────────────────────────────────────────────────────────


def test_four_fixtures_present_and_nonempty():
    platform = _load("platform_name_writings.json")
    sng = _load("same_name_group_writings.json")
    base = _load("resolvable_writings_baseline.json")
    head = _load("head_resolvable_static_writings.json")
    assert platform["count"] > 0 and platform["writings"]
    assert sng["count"] > 0 and sng["writings"]
    assert base["count"] > 0 and base["writings"]
    assert head["count"] > 0 and head["static_writings"]


# ── 2. 同名组现算与夹具一致（并交叉校验 78/70/8）────────────────────────────


def test_same_name_groups_recompute_matches_fixture(catalog):
    sng = _load("same_name_group_writings.json")
    by_parent_name: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for s in catalog.sheets_by_addr_id.values():
        by_parent_name[(s.get("parent_wp_code", ""), s.get("sheet_name", ""))].append(s)
    groups = {k: v for k, v in by_parent_name.items() if len(v) > 1}
    unique = 0
    none = 0
    for (parent, name) in groups:
        if ei.name_owner(parent, name, index=catalog) is None:
            none += 1
        else:
            unique += 1
    assert sng["same_name_group_total"] == len(groups)
    assert sng["owner_unique"] == unique
    assert sng["owner_none"] == none
    # 交叉校验设计 §1.2：78 组 / 70 唯一 / 8 None
    assert (len(groups), unique, none) == (78, 70, 8)


# ── 3. resolvable 三态现算逐条与夹具一致 + 分类自洽 ──────────────────────────


def _recompute_resolvable_state(catalog) -> dict[str, tuple[str | None, str | None, str]]:
    """重跑与导出脚本同口径的三态判定：key = parent||sheet_name||sheet_code。"""
    out: dict[str, tuple[str | None, str | None, str]] = {}
    for s in catalog.sheets_by_addr_id.values():
        parent = s.get("parent_wp_code", "")
        name = s.get("sheet_name", "")
        if not parent or not name:
            continue
        head_ref = f"WP('{parent}','{name}')"
        head_addr = cat_mod._formula_ref_to_addr_id(head_ref)
        sm = ei.sheet_of(parent, name, index=catalog)
        if sm.state == "ambiguous":
            state, new_addr = "ambiguous", None
        elif sm.ok and sm.entry:
            new_addr = sm.entry.get("addr_id")
            state = "unchanged" if new_addr == head_addr else "reclassified"
        else:
            new_addr = None
            state = "unchanged" if head_addr is None else "reclassified"
        key = f"{parent}||{name}||{s.get('sheet_code', '')}"
        out[key] = (head_addr, new_addr, state)
    return out


def test_resolvable_baseline_recompute_matches_fixture(catalog):
    base = _load("resolvable_writings_baseline.json")
    live = _recompute_resolvable_state(catalog)
    # 条数一致
    assert base["count"] == len(base["writings"]) == len(live)
    # 分类计数自洽
    cnt = {"unchanged": 0, "reclassified": 0, "ambiguous": 0}
    for w in base["writings"]:
        cnt[w["state"]] += 1
    assert cnt["unchanged"] == base["unchanged"]
    assert cnt["reclassified"] == base["reclassified"]
    assert cnt["ambiguous"] == base["ambiguous"]
    assert sum(cnt.values()) == base["count"]
    # 逐条与现算一致（防夹具/代码漂移）
    mismatches = []
    for w in base["writings"]:
        key = f"{w['parent']}||{w['sheet_name']}||{w['sheet_code']}"
        assert key in live, f"夹具含现算不存在的 sheet：{key}"
        head_addr, new_addr, state = live[key]
        if (w["head_addr_id"], w["new_addr_id"], w["state"]) != (head_addr, new_addr, state):
            mismatches.append((key, w["state"], state))
    assert not mismatches, f"resolvable 夹具与现算漂移（前5）：{mismatches[:5]}"


# ── 4. head_resolvable errmatch 条目逐条可追溯（design §6.5 核心守卫）────────


def test_head_resolvable_errmatch_each_has_resolvable_at(catalog):
    head = _load("head_resolvable_static_writings.json")
    errmatch = [w for w in head["static_writings"] if w.get("head_resolvable_at")]
    # 夹具声明的 errmatch_count 与实际带 head_resolvable_at 的条数一致
    assert head["errmatch_count"] == len(errmatch) > 0
    for w in errmatch:
        at = w["head_resolvable_at"]
        assert at, f"errmatch 条目缺 head_resolvable_at：{w['raw']}"
        # head_resolvable_at 指向真实 sheet（去掉末段 cell 后命中 sheets_by_addr_id）
        sheet_part = w.get("head_sheet_addr_id")
        assert sheet_part in catalog.sheets_by_addr_id, (
            f"errmatch 的 head_sheet_addr_id 非真实 sheet：{w['raw']} -> {sheet_part}"
        )
        # exact_state 必非 ok（发布后会变 not_found，正是需 T06/T09 处置的对象）
        assert w["exact_state"] != "ok", f"errmatch 条目 exact 已 ok 不应在清单：{w['raw']}"


# ── 5. head_resolvable 全量：static 条数与 count 一致（防截断）────────────────


def test_head_resolvable_counts_self_consistent():
    head = _load("head_resolvable_static_writings.json")
    assert head["count"] == len(head["static_writings"])
    assert head["pg_count"] == len(head["pg_writings"])
