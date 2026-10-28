"""公式推送附注规则的目标静态守卫（spec note-pull-followup-closure R2.4 / R2.5）。

2026-10-27 清点：子表规则 118 条里 99 条字段一个都映射不到取数行的值（取数行只有期末 / 期初），74 个口径对的表名在该版
模板里不存在（原引擎回退写首表）；主表规则 H10 / L6 / N3 / F5 挂错章节（H10 上市写进 L4 应付债券、L6 写进应付职工薪酬、
N3 写进固定资产、F5 用合并附注编号）。判据：
① 每条附注规则的底稿在注册表里有章节，且规则各口径章节 == 注册表章节；
② 子表规则：表在该口径模板章节里（``table_by_template`` 优先）、至少一个字段映射到期末 / 期初；
③ 生成器重跑不补回（``gen_subtable_push_rules.generate_rules()`` 为空）。
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

from app.services.formula_push.note_writer import NOTE_FIELDS

_BACKEND = Path(__file__).resolve().parents[1]
_DATA = _BACKEND / "data"
_ACCOUNT_KEYS = frozenset({"ending", "opening"})


def _norm(text) -> str:
    return "".join(str(text or "").split())


@pytest.fixture(scope="module")
def world():
    rules = json.loads((_DATA / "formula_push_rules.json").read_text(encoding="utf-8"))["rules"]
    templates = {}
    for std in ("listed", "soe"):
        doc = json.loads((_DATA / f"note_template_{std}.json").read_text(encoding="utf-8"))
        templates[std] = {s.get("section_number"): s for s in doc["sections"]}
    reg = json.loads((_DATA / "note_workpaper_sync_registry.json").read_text(encoding="utf-8"))
    registry = {str(e.get("wp_code")): {k: e[k] for k in ("listed", "soe") if e.get(k)} for e in reg["entries"]}
    return rules, templates, registry


def _problems(rules, templates, registry) -> list[str]:
    out: list[str] = []
    for rule in rules:
        target = rule.get("target") or {}
        if target.get("domain") != "note":
            continue
        rid = rule["rule_id"]
        wp = str(rule.get("page_key") or "").split(":", 1)[-1]
        sub = ".note.subtable_" in rid
        if wp not in registry:
            out.append(f"{rid}：底稿 {wp} 在附注同步注册表里没有章节（附注由谁披露未登记），不得推附注")
            continue
        for std, section in (target.get("section_by_template") or {}).items():
            if registry[wp].get(std) != section:
                out.append(f"{rid} {std}：章节 {section} ≠ 注册表 {registry[wp].get(std)}")
                continue
            if section not in templates[std]:
                out.append(f"{rid} {std}：模板没有章节 {section}")
                continue
            if sub:
                name = (target.get("table_by_template") or {}).get(std) or target.get("table")
                names = {_norm(t.get("name")) for t in templates[std][section].get("tables") or []}
                if _norm(name) not in names:
                    out.append(f"{rid} {std}：{section} 里没有「{name}」表")
        if sub and not any(NOTE_FIELDS.get(f, ("",))[0] in _ACCOUNT_KEYS for f in target.get("fields") or []):
            out.append(f"{rid}：字段 {target.get('fields')} 一个都取不到值（取数行只有期末 / 期初）")
    return out


def test_note_rule_targets_are_consistent(world) -> None:
    problems = _problems(*world)
    assert not problems, "\n".join(problems)


def test_subtable_rule_count_after_cleanup(world) -> None:
    """2026-10-27 清点后子表规则 14 条（118 删 104：取不到值 99 + 语义错 5）；增加须先过本守卫与合计兜底裁决。"""
    rules, _templates, _registry = world
    subs = sorted(r["rule_id"] for r in rules if ".note.subtable_" in r["rule_id"])
    assert len(subs) == 14, subs


def test_generator_does_not_add_back(world) -> None:
    gen_dir = str(_BACKEND / "scripts" / "gen")
    if gen_dir not in sys.path:
        sys.path.insert(0, gen_dir)
    import gen_subtable_push_rules as gen

    assert gen.generate_rules() == [], "重跑生成器又产出了规则（删过的写错数 / 取不到值的规则被补回）"


@pytest.mark.parametrize("planted", [
    pytest.param(lambda r: r["target"].update(section_by_template={"listed": "五、46"}), id="H10-listed-wrong-section"),
    pytest.param(lambda r: r.update(page_key="workpaper:L6", rule_id="L6.note.main"), id="unregistered-workpaper"),
])
def test_guard_flags_planted_main_rule(world, planted) -> None:
    rules, templates, registry = world
    rule = copy.deepcopy(next(r for r in rules if r["rule_id"] == "H10.note.main"))
    planted(rule)
    assert _problems([rule], templates, registry), "判据空转：错挂的主表规则没被点名"


@pytest.mark.parametrize("planted", [
    pytest.param(lambda r: r["target"].update(fields=["provision", "ratio"]), id="fields-unmapped"),
    pytest.param(lambda r: r["target"].update(section_by_template={"listed": "五、33", "soe": "八、33"},
                                              table="短期借款分类", table_by_template={"listed": "不存在的表"}),
                 id="table-missing-in-template"),
])
def test_guard_flags_planted_subtable_rule(world, planted) -> None:
    rules, templates, registry = world
    rule = copy.deepcopy(next(r for r in rules if r["rule_id"] == "L1.note.subtable_0"))
    planted(rule)
    assert _problems([rule], templates, registry), "判据空转：取不到值 / 表名错版的子表规则没被点名"
