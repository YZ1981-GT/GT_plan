"""公式推送子表规则 × 合计行兜底：科目合计只许写进「就是该科目余额 / 发生额构成」的子表合计行（静态守卫）。

引擎 ``_push_note``：取数行一行都对不上附注行时，把科目合计写进目标表的首个合计行（formula-push-note-skip-reduction
需求 2.3「合计行兜底」）。取数行由 binding 给（试算表 / 底稿主表口径，只有 ending / opening 两个值）；子表规则
（``*.note.subtable_*``，gen_subtable_push_rules.py 生成）与主表规则共用同一 binding 的取数行 ⇒ 子表不是该科目余额构成
时（前五名、账龄超过 1 年的重要款项、逾期借款、继续涉入、坏账 / 减值准备变动……）写进去的是错数。

2026-10-25 普查 38 处（spec consol-note-header-library-and-node-reaggregate R8.4 批 9b-2）：22 条规则写错数已删，
其余 18 处逐条裁决钉在 ``_BREAKDOWN``。新增 / 重跑生成器补回的规则命中兜底，必须先在这里裁决（写对的登记、写错的删规则）。
判据与引擎同口径：字段经 ``NOTE_FIELDS`` 映射到 ending / opening、目标表（``table_by_template`` 优先）有合计行
（``note_writer.find_total_row``）。
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from app.services.formula_push.note_writer import NOTE_FIELDS, find_total_row

_DATA = Path(__file__).resolve().parents[1] / "data"
#: 取数行只有这两个值（tier_a / note_direct / balance_adj / e1 的 note_rows 同口径）
_ACCOUNT_VALUE_KEYS = frozenset({"ending", "opening"})
_PL = "损益类：本期 / 上期发生额按性质（来源）列示，合计 = 科目发生额"

#: (rule_id, 口径) → 科目合计为什么就是这张子表的合计
_BREAKDOWN: dict[tuple[str, str], str] = {
    ("F1.note.subtable_0", "soe"): "预付款项按账龄列示：小计 = 1123 账面余额",
    ("F2.note.subtable_1", "listed"): "binding 不给子表规则出行（note_direct._book_value_rows），兜底无源",
    ("F2.note.subtable_1", "soe"): "binding 不给子表规则出行（note_direct._book_value_rows），兜底无源",
    ("G7.note.subtable_0", "soe"): "长期股权投资分类：小计（减值准备前）= 1511 账面余额",
    ("G7.note.subtable_1", "soe"): "长期股权投资明细：合计期初 = 1511 年初余额",
    ("L1.note.subtable_0", "listed"): "短期借款分类：合计 = 2001",
    ("L1.note.subtable_0", "soe"): "短期借款分类：合计 = 2001",
    ("K3.note.subtable_4", "soe"): "其他应付款按款项性质列示：合计 = 2241",
    ("M9.note.subtable_1", "listed"): "其他综合收益各项目：合计期末 = 4003 期末余额",
    ("G13.note.subtable_0", "listed"): _PL,
    ("G13.note.subtable_0", "soe"): _PL,
    ("G13.note.subtable_1", "listed"): _PL + "（同节重复表，表名是表头「项  目」）",
    ("H10.note.subtable_0", "soe"): _PL,
    ("K8.note.subtable_0", "listed"): _PL,
    ("K9.note.subtable_0", "listed"): _PL,
    ("L8.note.subtable_0", "listed"): _PL,
    ("G11.note.subtable_1", "listed"): _PL + "（同节重复表，表名是表头「项  目」）",
    ("G14.note.subtable_0", "listed"): _PL + "（表名是表头「项  目」）",
}


def _load() -> tuple[list[dict], dict[str, dict[str, dict]]]:
    rules = json.loads((_DATA / "formula_push_rules.json").read_text(encoding="utf-8"))["rules"]
    templates = {}
    for std in ("listed", "soe"):
        doc = json.loads((_DATA / f"note_template_{std}.json").read_text(encoding="utf-8"))
        templates[std] = {s.get("section_number"): s for s in doc["sections"]}
    return rules, templates


def _fallback_targets(rules: list[dict], templates: dict[str, dict[str, dict]]) -> dict[tuple[str, str], str]:
    """会被合计行兜底写入科目合计的 (子表规则, 口径) → 目标「章节 表名」。"""
    hits: dict[tuple[str, str], str] = {}
    for rule in rules:
        target = rule.get("target") or {}
        if target.get("domain") != "note" or ".note.subtable_" not in rule["rule_id"]:
            continue
        if not any(NOTE_FIELDS.get(f, ("",))[0] in _ACCOUNT_VALUE_KEYS for f in target.get("fields") or []):
            continue
        for std, sec in (target.get("section_by_template") or {}).items():
            name = (target.get("table_by_template") or {}).get(std) or target.get("table")
            section = templates[std].get(sec) or {}
            table = next((t for t in section.get("tables") or [] if t.get("name") == name), None)
            if table is not None and find_total_row(table.get("rows") or []) is not None:
                hits[(rule["rule_id"], std)] = f"{sec}「{name}」"
    return hits


def test_every_total_fallback_is_adjudicated() -> None:
    hits = _fallback_targets(*_load())
    pending = {k: v for k, v in hits.items() if k not in _BREAKDOWN}
    assert not pending, (
        "子表规则会把科目合计兜底写进这些表的合计行，先裁决：该表合计就是科目余额 / 发生额 ⇒ 登记 _BREAKDOWN；否则删规则\n"
        + "\n".join(f"  {rid} {std} {where}" for (rid, std), where in sorted(pending.items()))
    )


def test_adjudications_are_live() -> None:
    hits = _fallback_targets(*_load())
    stale = sorted(k for k in _BREAKDOWN if k not in hits)
    assert not stale, f"裁决登记已不触发兜底（规则删了 / 表改了），删掉这些条目：{stale}"


def test_guard_flags_a_planted_rule() -> None:
    """变异：把 2026-10-25 删掉的「逾期借款」子表规则种回去，守卫必须点名（判据不空转）。"""
    rules, templates = _load()
    planted = copy.deepcopy(next(r for r in rules if r["rule_id"] == "L1.note.subtable_0"))
    planted["rule_id"] = "L1.note.subtable_1"
    planted["target"]["table"] = "已逾期未偿还的短期借款情况"
    planted["target"]["section_by_template"] = {"soe": "八、33"}
    hits = _fallback_targets([*rules, planted], templates)
    assert hits.get(("L1.note.subtable_1", "soe")) == "八、33「已逾期未偿还的短期借款情况」"
    assert ("L1.note.subtable_1", "soe") not in _BREAKDOWN
