"""规则已不存在、格里还留着推送值的附注单元格（spec note-table-structure-formula-pull-closure R9 / R10 · ADR-7）。

公式推送按规则写格并在 ``formula_push_state`` 记一行（``rule_id`` + ``last_pushed_value``）。规则清单
（``backend/data/formula_push_rules.json``）改名 / 删条目之后，这些状态行就没人维护了：推送不碰它（规则没了），
附注预设公式也不碰它（执行器按 state 判「推送拥有格」就跳过），于是格里永远停在当年推送的那个数。

清点脚本、修复脚本、推送回执共用本模块的判定（只有一份），不各自写一套。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["OrphanState", "known_rule_ids", "count_orphans", "list_orphans"]


@dataclass(frozen=True)
class OrphanState:
    """一条孤儿推送状态行（附注域）。"""

    project_id: str
    year: int
    note_section: str | None
    rule_id: str
    addr_id: str
    state: str
    last_pushed_value: Any
    current_value: Any
    updated_at: str

    @property
    def still_pushed_value(self) -> bool:
        """格里的数仍是这条已删规则当年推的（没人改过、也没人再维护）。"""
        return self.last_pushed_value is not None and self.last_pushed_value == self.current_value

    def to_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "still_pushed_value": self.still_pushed_value}


def known_rule_ids() -> set[str]:
    """现行规则清单里的 ``rule_id``（含未启用的 —— 只要清单里有就不算孤儿）。"""
    from app.services.formula_push.rules import load_rules

    return {r.rule_id for r in load_rules()}


def _scope(project_id: UUID | str | None, year: int | None) -> tuple[str, dict[str, Any]]:
    """附加过滤条件。不用 ``:pid IS NULL OR …``：asyncpg 推不出参数类型（AmbiguousParameterError）。"""
    where, params = "", {}
    if project_id is not None:
        where += " AND project_id = CAST(:pid AS uuid)"
        params["pid"] = str(project_id)
    if year is not None:
        where += " AND year = :yr"
        params["yr"] = year
    return where, params


async def list_orphans(
    db: AsyncSession, *, project_id: UUID | str | None = None, year: int | None = None,
) -> list[OrphanState]:
    """附注域里规则已不存在的推送状态行。"""
    known = known_rule_ids()
    where, params = _scope(project_id, year)
    rows = (await db.execute(sa.text(
        "SELECT project_id, year, note_section, rule_id, addr_id, state, "
        "       last_pushed_value, current_value, updated_at "
        f"FROM formula_push_state WHERE domain = 'note'{where} "
        "ORDER BY project_id, note_section, rule_id, addr_id"
    ), params)).mappings().all()
    return [
        OrphanState(
            project_id=str(r["project_id"]), year=r["year"], note_section=r["note_section"], rule_id=r["rule_id"],
            addr_id=r["addr_id"], state=r["state"], last_pushed_value=r["last_pushed_value"],
            current_value=r["current_value"], updated_at=str(r["updated_at"]),
        )
        for r in rows if r["rule_id"] not in known
    ]


async def count_orphans(db: AsyncSession, *, project_id: UUID | str | None = None, year: int | None = None) -> int:
    """孤儿状态行条数（推送回执用；失败不该拖垮推送 ⇒ 调用方自己兜）。"""
    known = known_rule_ids()
    if not known:
        return 0
    where, params = _scope(project_id, year)
    rows = (await db.execute(sa.text(
        f"SELECT rule_id, count(*) AS n FROM formula_push_state WHERE domain = 'note'{where} GROUP BY rule_id"
    ), params)).all()
    return sum(int(n) for rule_id, n in rows if rule_id not in known)
