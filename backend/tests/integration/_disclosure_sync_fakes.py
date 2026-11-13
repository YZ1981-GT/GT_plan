"""附注双源单向同步 PBT（``test_disclosure_sync.py``）用的内存版 AsyncSession 替身。

2026-11-04 从测试文件挪出（该文件 HEAD 已 814 行、超过行数门）：同步链路自 spec formula-writer-ownership-and-stale R2
起在更新已有章节后经统一入口 ``stale_state.clear_note_stale`` 清过期（一条按章节 IN 过滤的 UPDATE + flush），
替身须认这两步，原替身把 UPDATE 当查询解析、章节 IN 的列表当键 ⇒ TypeError。
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from sqlalchemy.sql.dml import Update
from sqlalchemy.sql.elements import BinaryExpression, BindParameter, BooleanClauseList

from app.models.report_models import DisclosureNote


def _extract_filters(stmt: Any) -> dict[str, Any]:
    """从 SQLAlchemy select stmt 的 WHERE 子句提取 BindParameter 值。

    handles AND'd BinaryExpression chain 的常见情况
    （DisclosureNote.project_id == X、year == Y、note_section == Z、is_deleted == false()）
    """
    filters: dict[str, Any] = {}
    where = stmt.whereclause
    if where is None:
        return filters

    if isinstance(where, BooleanClauseList):
        children = list(where.clauses)
    else:
        children = [where]

    for clause in children:
        if not isinstance(clause, BinaryExpression):
            continue
        col_name = getattr(clause.left, "key", None) or getattr(clause.left, "name", None)
        right = clause.right
        if isinstance(right, BindParameter):
            filters[col_name] = right.value
    return filters


class FakeDB:
    """模拟 AsyncSession：以 (project_id, year, note_section) 为主键存储 DisclosureNote。"""

    def __init__(self) -> None:
        self.notes: dict[tuple, DisclosureNote] = {}
        self.commit_count: int = 0
        self.add_count: int = 0
        self.rollback_count: int = 0

    async def execute(self, stmt: Any) -> Any:
        if isinstance(stmt, Update):
            # 清过期 UPDATE（stale_state.clear_note_stale）：本替身不建模过期列
            result = MagicMock()
            result.rowcount = 0
            return result
        filters = _extract_filters(stmt)
        key = (
            filters.get("project_id"),
            filters.get("year"),
            filters.get("note_section"),
        )
        note = self.notes.get(key)
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=note)
        return result

    async def flush(self) -> None:
        return None

    def add(self, obj: Any) -> None:
        self.add_count += 1
        if isinstance(obj, DisclosureNote):
            key = (obj.project_id, obj.year, obj.note_section)
            self.notes[key] = obj

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1
