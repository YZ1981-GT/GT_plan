"""附注单元格 / 合计行的推送写入（从 ``engine.py`` 原样搬出，设计 ADR-9：engine 已超行数门，接线前先抽模块）。

另新增 R12 的兜底行选择 ``pick_fallback_total``：表里有「减：…准备」行时，账面余额合计（该行之前最近的汇总行）
与账面价值合计（最终合计）语义不同，科目余额对应前者 —— 原先一律拒绝兜底，账龄表主表的合计就一直空着。

搬出的四个函数逻辑未改；``record`` 由调用方注入（``engine._record_note``），避免与 engine 互相 import。
``ctx`` 只用到 ``skip``，按鸭子类型接收。

spec: note-table-structure-formula-pull-closure R12 · ADR-8 / ADR-9
"""
from __future__ import annotations

import re
from typing import Any, Callable, Protocol

from app.services.formula_push import note_writer
from app.services.formula_push.policy import Decision, decide_note
from app.services.formula_push.rules import PushRule

__all__ = ["PERIOD_LABELS", "SPLIT_FIELD_LABELS", "find_total_by_label", "note_keep_reason", "pick_fallback_total",
           "push_note_cell", "push_note_total"]

PERIOD_LABELS: dict[str, str] = {"end": "期末", "prior": "期初"}
#: 分「账面余额 / 减值准备 / 账面价值」三列写的字段：旧格式表（按列序存数）只认得出期末 / 期初金额列，这几列不按位置猜
SPLIT_FIELD_LABELS: dict[str, str] = {
    "end_gross": "期末账面余额", "end_impairment": "期末减值准备", "end_net": "期末账面价值",
    "prior_gross": "期初账面余额", "prior_impairment": "期初减值准备", "prior_net": "期初账面价值",
}
#: 「减：坏账准备 / 减：减值准备 / 减：存货跌价准备」这类备抵行：它之前是账面余额，之后的合计是账面价值
_PROVISION_RE = re.compile(r"^减[:：]\s*.{0,8}准备$")


class _SkipCtx(Protocol):
    def skip(self, rule_id: str, domain: str, kind: str, addr: str, reason: str) -> Any: ...


def find_total_by_label(rows: Any, label: str) -> int | None:
    """分段合计表：按行名精确、唯一地对上合计行（不做包含匹配）。"""
    hits = [
        index for index, row in enumerate(rows)
        if isinstance(row, dict) and (row.get("is_total") or row.get("row_type") == "total")
        and note_writer.row_label(row) == label
    ]
    return hits[0] if len(hits) == 1 else None


def pick_fallback_total(rows: Any) -> tuple[int | None, str | None]:
    """明细行一个都没命中时，科目余额该写哪个合计行 → ``(行号, 不兜底的原因)``。

    - 只有一个汇总行：就是它（原行为）。
    - 有「减：…准备」行：它之前最近的汇总行是账面余额合计，科目余额（TB 余额是账面余额）写它；
      最终合计是账面价值，不写（国企账龄表 / 其他应收款账龄表就是这个形态，原先整表拒绝兜底 ⇒ 合计一直空着）。
    - 其余多汇总行（分段合计「一、账面原值合计 / … / 四、账面价值合计」）：哪一段由科目决定，引擎不知道 ⇒ 不兜底。
      2026-10-31 真库教训：按「最终合计」兜底把原值写进了账面价值合计（和平 八、26 应为 66,389,073.02）。
    """
    candidates = note_writer.total_row_candidates(rows)
    if not candidates:
        return None, None
    if len(candidates) == 1:
        return candidates[0], None
    provision = next(
        (i for i, row in enumerate(rows)
         if isinstance(row, dict) and not (row.get("is_total") or row.get("row_type") == "total")
         and _PROVISION_RE.fullmatch(note_writer.row_label(row).replace(" ", ""))),
        None,
    )
    if provision is not None:
        gross = [i for i in candidates if i < provision]
        if len(gross) == 1:
            return gross[0], None
    labels = "、".join(note_writer.row_label(rows[i]) or "（无名）" for i in candidates)
    return None, f"表里有 {len(candidates)} 个合计行（{labels}），不知道科目余额该写哪一行，不兜底"


def note_keep_reason(mode: str | None, decision: Decision) -> str | None:
    if not decision.kept:
        return None
    return "附注中该单元格被标记为锁定（或整节人工覆盖），保留原值" if mode == "locked" else \
        "附注中该单元格被标记为人工填写，保留原值"


def push_note_cell(
    ctx: _SkipCtx, *, rule: PushRule, section: str, addr: str, table: note_writer.NoteTable,
    row: dict, field_name: str, value: float, paper: Any, record: Callable[..., None],
) -> bool:
    ok, current, cell_mode = note_writer.read_cell(row, field_name, table.value_keys)
    if not ok:
        period = note_writer.NOTE_FIELDS[field_name][1]
        detail = f"：{table.column_note}" if table.column_note else ""
        reason = f"附注表缺少「{PERIOD_LABELS[period]}」列{detail}"
        if field_name in SPLIT_FIELD_LABELS and isinstance(row.get("values"), list):
            reason = (f"附注表是旧格式（按列序存数），表头只认得出期末 / 期初金额列，找不到唯一的"
                      f"「{SPLIT_FIELD_LABELS[field_name]}」列，不按位置猜，附注保持原值")
        ctx.skip(rule.rule_id, "note", "note", addr, reason)
        return False
    mode = note_writer.external_mode(table.section_locked, cell_mode)
    decision = decide_note(formula_value=value, current_value=current, cell_mode=mode)
    if decision.writes:
        note_writer.write_cell(row, field_name, value, table.value_keys)
    record(ctx, rule, section, addr, decision, value, current, paper, note_keep_reason(mode, decision))
    return decision.writes


def push_note_total(
    ctx: _SkipCtx, *, rule: PushRule, section: str, table_name: str, table: note_writer.NoteTable, paper: Any,
    record: Callable[..., None], note_addr_id: Callable[[str, str, str, str], str],
) -> bool:
    """合计 = 合计行之前各行之和（人工行一并计入）；上方各行这一列都没有数则不重算（不写 0）。"""
    index = note_writer.find_total_row(table.rows)
    if index is None:
        return False
    total_row = table.rows[index]
    label = note_writer.row_label(total_row) or "合计"
    wrote = False
    for field_name in rule.target.fields:
        _, period = note_writer.NOTE_FIELDS[field_name]
        ok, current, cell_mode = note_writer.read_cell(total_row, field_name, table.value_keys)
        if not ok:
            continue
        value = note_writer.total_formula(table.rows, index, field_name, table.value_keys)
        addr = note_addr_id(section, table_name, label, period)
        if value is None:
            ctx.skip(rule.rule_id, "note", "note", addr,
                     f"合计行「{label}」上方各行这一列都没有数，合计不按 0 重算，附注保持原值")
            continue
        mode = note_writer.external_mode(table.section_locked, cell_mode)
        decision = decide_note(formula_value=value, current_value=current, cell_mode=mode)
        if decision.writes:
            note_writer.write_cell(total_row, field_name, value, table.value_keys)
            wrote = True
        record(ctx, rule, section, addr, decision, value, current, paper, note_keep_reason(mode, decision))
    return wrote
