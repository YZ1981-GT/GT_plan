"""存储表上的推送拥有格（spec note-table-structure-formula-pull-closure R4.2；formula-writer-ownership-and-stale §13）。

存储表（附注模板生成、不是底稿投影）上公式推送写过、且当前值仍等于推送值（推送状态 ``auto``）的格归推送：预设公式不改写
（用户公式照常覆盖）；模板绑定取数（``refill_sections`` / 报表更新 / 生成合并）同样不改写（写入归属矩阵的推送条目）。

底稿投影表不在这里判：投影表上预设公式本就只补空格（ADR-2），推送拥有格由同步交接（``note_push_ownership``）保证。
找表 / 找行 / 对列与推送、单元格来源诊断同一套（``note_writer.locate_table`` / ``note_push_ownership._locate`` / 规则字段）。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["OwnedPushCell", "PushOwnershipCache", "push_owned_cell_details", "push_owned_cells"]


@dataclass(frozen=True)
class OwnedPushCell:
    """一格推送写定的存储格：``table`` / ``field`` 是推送规则表名与字段（写入归属矩阵的键）。"""

    table: str
    field: str
    label: str
    pushed: Any


async def push_owned_cell_details(
    db: AsyncSession, *, project_id: UUID, year: int, section: str, td: Any, view: Any,
    states: list[Any] | None = None, rules: Any = None,
) -> dict[tuple[int, int, int], OwnedPushCell]:
    """存储表上推送拥有的格 ``{(表序号, 行, 列): OwnedPushCell}``（列 = ``values`` 下标）；视图是底稿投影或没有推送状态 ⇒ 空。

    ``states`` / ``rules`` 可由批量调用方预取（``PushOwnershipCache``），免逐章节查库。
    """
    if not isinstance(td, dict) or view is not td:
        return {}
    from app.services.formula_push import note_writer
    from app.services.formula_push.policy import values_equal
    from app.services.note_formula_tables import iter_note_tables
    from app.services.note_push_ownership import _locate, _owned_states, parse_note_addr

    if states is None:
        states = await _owned_states(db, project_id, year, section)
    if not states:
        return {}
    if rules is None:
        from app.services.formula_settings.push_settings import effective_push_rules

        rules, _issues = await effective_push_rules(db, project_id)
    rule_of = {r.rule_id: r for r in rules}
    tables = dict(iter_note_tables(td))
    owned: dict[tuple[int, int, int], OwnedPushCell] = {}
    for state in states:
        parsed = parse_note_addr(state.addr_id)
        rule = rule_of.get(state.rule_id)
        if parsed is None or rule is None or rule.status != "active":
            continue  # 规则已删除 / 停用：推送不再拥有这一格（与同步交接同口径）
        _sec, table_name, label, period = parsed
        located, _why = note_writer.locate_table(td, table_name, exact=".note.subtable_" in state.rule_id)
        if located is None:
            continue
        t = next((i for i, tb in tables.items() if tb.get("rows") is located.rows), 0 if located.rows is td.get("rows") else None)
        r = _locate(located.rows, label)
        if t is None or r is None or not isinstance(located.rows[r], dict):
            continue
        fields = {f for f in rule.target.fields if note_writer.NOTE_FIELDS.get(f, ("", ""))[1] == period}
        values = located.rows[r].get("values") if isinstance(located.rows[r].get("values"), list) else []
        for c, key in enumerate(located.value_keys):
            if key in fields and c < len(values) and values_equal(values[c], state.last_pushed_value):
                owned[(t, r, c)] = OwnedPushCell(table=table_name, field=key, label=label,
                                                 pushed=state.last_pushed_value)
    return owned


async def push_owned_cells(db: AsyncSession, *, project_id: UUID, year: int, section: str, td: Any,
                           view: Any) -> set[tuple[int, int, int]]:
    """存储表上推送拥有的格 ``{(表序号, 行, 列)}``（列 = ``values`` 下标）；视图是底稿投影或没有推送状态 ⇒ 空集。"""
    return set(await push_owned_cell_details(db, project_id=project_id, year=year, section=section, td=td, view=view))


class PushOwnershipCache:
    """一次批量写入内按章节取推送写定格：推送状态（全项目年度）与有效推送规则各只查一次。"""

    def __init__(self, db: AsyncSession, project_id: UUID, year: int) -> None:
        self.db, self.project_id, self.year = db, project_id, year
        self._states: dict[str, list[Any]] | None = None
        self._rules: Any = None

    async def cells(self, section: str, td: Any) -> dict[tuple[int, int, int], OwnedPushCell]:
        if self._states is None:
            from app.services.note_push_ownership import _owned_states

            grouped: dict[str, list[Any]] = defaultdict(list)
            for state in await _owned_states(self.db, self.project_id, self.year, None):
                grouped[str(state.note_section or "")].append(state)
            self._states = dict(grouped)
        states = self._states.get(section) or []
        if not states:
            return {}
        if self._rules is None:
            from app.services.formula_settings.push_settings import effective_push_rules

            self._rules, _issues = await effective_push_rules(self.db, self.project_id)
        return await push_owned_cell_details(self.db, project_id=self.project_id, year=self.year, section=section,
                                             td=td, view=td, states=states, rules=self._rules)
