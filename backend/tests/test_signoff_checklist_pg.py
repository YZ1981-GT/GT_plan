"""签发清单真实 PostgreSQL 守卫。

合成 SQLite 测不出两件事：
1. 裸 SQL / ORM 枚举与真实 schema 漂移（历史实现 8 条 SQL 真库失败而 mock 全绿）；
2. PG 一条语句失败会把事务置 aborted，只有 SAVEPOINT 回滚后后续检查才能继续。

只读真实项目；每例结尾 rollback，不改数据。
"""
from __future__ import annotations

from uuid import UUID

import pytest
import sqlalchemy as sa

from app.core.database import async_session
from app.services.signoff_checklist_service import CheckSeverity, SignoffChecklistService

pytestmark = pytest.mark.pg_only

PROJECTS = (
    UUID("0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49"),  # 重药安徽
    UUID("2aa00f57-1df4-4fe8-9840-2d65d0fd8749"),  # 和平药房
    UUID("a7fc75e5-b67f-436d-a126-42423018b6ce"),  # 陕西华氏
    UUID("c8621493-70aa-46a9-8285-e0674e4e1418"),  # 宜宾临港店
)


@pytest.mark.asyncio
async def test_four_real_projects_all_checks_execute_against_live_schema():
    """六类检查都真执行：不允许「执行失败」blocking，也不允许旧「暂不可用」info。"""
    async with async_session() as db:
        try:
            for project_id in PROJECTS:
                result = await SignoffChecklistService(db).generate_checklist(
                    project_id=project_id, year=2025
                )
                categories = {i.category for i in result.items}
                assert categories == {
                    "trial_balance", "adjustment", "conflict", "report", "stale", "ai_content"
                }, (project_id, categories)
                bad = [i.message for i in result.items if "执行失败" in i.message or "暂不可用" in i.message]
                assert not bad, (project_id, bad)
                # 三个没有 audit_report 的真实项目必须被阻断；不再像旧实现一样 5 个 info 后恒可签发。
                if project_id != PROJECTS[0]:
                    assert result.can_signoff is False
                    assert any(i.category == "report" and i.severity == CheckSeverity.blocking for i in result.items)
        finally:
            await db.rollback()


@pytest.mark.asyncio
async def test_failed_check_savepoint_does_not_abort_following_checks(monkeypatch):
    """故障注入在检查下一层：非法 SQL 使 PG 事务 abort；begin_nested 必须回滚到 SAVEPOINT，后续检查仍执行。"""
    project_id = PROJECTS[0]

    async def _broken(self, _project_id, _year, _pid):
        await self.db.execute(sa.text("SELECT definitely_missing_column FROM trial_balance LIMIT 1"))
        return []

    monkeypatch.setattr(SignoffChecklistService, "_check_trial_balance", _broken)
    async with async_session() as db:
        try:
            result = await SignoffChecklistService(db).generate_checklist(project_id=project_id, year=2025)
            failed = [i for i in result.items if i.category == "trial_balance"]
            assert len(failed) == 1 and failed[0].severity == CheckSeverity.blocking
            assert "执行失败" in failed[0].message
            later = [i for i in result.items if i.category == "adjustment"]
            assert later and all("执行失败" not in i.message for i in later), [i.message for i in later]
        finally:
            await db.rollback()
