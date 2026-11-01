"""附注公式执行时的推送拥有格保护（spec note-table-structure-formula-pull-closure R20.3 / ADR-15）。

存储表（附注模板生成、不是底稿投影）上公式推送写过、且当前值仍等于推送值（推送状态 ``auto``）
的格归推送：预设公式不改写（用户公式照常覆盖）。推送后自动运算（``note_followup``）与刷新链路
都经执行器，没有这道判断，合计行会被「明细之和」改掉推送按试算表审定数写入的值
（明细只填了一部分时）。

底稿投影表不在这里判：投影表上预设公式本就只补空格（ADR-2），推送拥有格由同步交接
（``note_push_ownership``）保证。
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["push_owned_cells"]


async def push_owned_cells(
    db: AsyncSession, *, project_id: UUID, year: int, section: str, td: Any, view: Any,
) -> set[tuple[int, int, int]]:
    """存储表上推送拥有的格 ``{(表序号, 行, 列)}``（列 = ``values`` 下标）。

    视图是底稿投影或没有推送状态 → 空集。
    """
    if not isinstance(td, dict) or view is not td:
        return set()
    from app.services.formula_push import note_writer
    from app.services.formula_push.policy import values_equal
    from app.services.note_formula_tables import iter_note_tables
    from app.services.note_push_ownership import _locate, _owned_states, parse_note_addr

    states = await _owned_states(db, project_id, year, section)
    if not states:
        return set()

    tables = dict(iter_note_tables(td))
    owned: set[tuple[int, int, int]] = set()
    for state in states:
        parsed = parse_note_addr(state.addr_id)
        if parsed is None:
            continue
        _sec, table_name, label, period = parsed
        located, _why = note_writer.locate_table(td, table_name, exact=".note.subtable_" in state.rule_id)
        if located is None:
            continue
        t = next(
            (i for i, tb in tables.items() if tb.get("rows") is located.rows),
            0 if located.rows is td.get("rows") else None,
        )
        r = _locate(located.rows, label)
        if t is None or r is None or not isinstance(located.rows[r], dict):
            continue
        fields = {
            f for f in (note_writer.NOTE_FIELDS or {})
            if note_writer.NOTE_FIELDS.get(f, ("", ""))[1] == period
        }
        values = located.rows[r].get("values") if isinstance(located.rows[r].get("values"), list) else []
        for c, key in enumerate(located.value_keys):
            if key in fields and c < len(values) and values_equal(values[c], state.last_pushed_value):
                owned.add((t, r, c))
    return owned
