# -*- coding: utf-8 -*-
"""底稿回收站 —— 真实 PostgreSQL（spec procedure-trim-generation-delegation-chain 需求 3 / 任务 8）。

真库约束下验证「移入回收站 = 两层软删、恢复 = 复活原行」这一设计的前提与行为：
- ``uq_wp_index_project_code`` 不含 is_deleted ⇒ 软删后同码不能新建（只能复活）；
- 实质内容判定读真表（``checklist_responses`` 人工填写、``review_records`` 复核意见；公式推送行不算）；
- 移入后生成分流报「在回收站」；按原因恢复（只恢复 ``trim``）两层一起回来，去向记录逐条追加。

全部数据建在一个外层事务里的【测试】项目上，用例结束回滚，不落库。
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.models.base import ProjectStatus, UserRole
from app.models.core import Project, User
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus
from app.services.procedure_scope_retention import TrimmedScope, plan_generation
from app.services.workpaper_recycle_service import (
    RECYCLE_LINEAGE_KEY,
    move_to_recycle_bin,
    plan_recycle,
    plan_restore,
    restore_from_recycle_bin,
)

pytestmark = pytest.mark.pg_only


@pytest.mark.asyncio
async def test_recycle_and_restore_under_real_unique_indexes():
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    conn = await engine.connect()
    trans = await conn.begin()
    db = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
    try:
        user = User(username=f"rcy_{uuid.uuid4().hex[:10]}", email=f"{uuid.uuid4().hex[:10]}@t.example",
                    hashed_password="x", role=UserRole.auditor, is_active=True)
        project = Project(name="【测试】回收站真库", client_name="【测试】回收站真库", status=ProjectStatus.execution)
        db.add_all([user, project])
        await db.flush()
        papers = {}
        for code in ("E1", "E1-1", "E9"):
            idx = WpIndex(project_id=project.id, wp_code=code, wp_name=f"底稿{code}", audit_cycle="E",
                          status=WpStatus.not_started)
            db.add(idx)
            await db.flush()
            wp = WorkingPaper(project_id=project.id, wp_index_id=idx.id, file_path="", file_version=1,
                              source_type=WpSourceType.template)
            db.add(wp)
            await db.flush()
            papers[code] = wp.id
        await db.execute(sa.text(
            "INSERT INTO checklist_responses (project_id, wp_id, item_id, updated_by) VALUES "
            "(:p, :w, 'E1-manual', :u), (:p, :w, 'E1-pushed', NULL)"),
            {"p": project.id, "w": papers["E1"], "u": user.id})
        await db.execute(sa.text(
            "INSERT INTO review_records (id, working_paper_id, comment_text, commenter_id) VALUES (:i, :w, '请补充', :u)"),
            {"i": uuid.uuid4(), "w": papers["E1"], "u": user.id})
        await db.flush()

        targets = {t.wp_code: t for t in await plan_recycle(db, project.id, ["E1", "E1-1", "ZZ"])}
        assert sorted(targets) == ["E1", "E1-1"]
        assert targets["E1"].substantive_reasons == ["人工填写 1 项", "复核意见 1 条"], "公式推送行（updated_by 空）不算"
        assert targets["E1-1"].substantive_reasons == []

        moved = await move_to_recycle_bin(db, project.id, ["E1", "E1-1"], kind="trim", reason="程序裁剪：E1",
                                          actor_user_id=user.id, trim_codes={"E1": ["E1"], "E1-1": ["E1"]})
        assert moved == ["E1", "E1-1"]
        await move_to_recycle_bin(db, project.id, ["E9"], kind="manual", reason="手工删除", actor_user_id=user.id)
        plan = await plan_generation(db, project.id, ["E1", "E1-1", "E9", "E2"], scope=TrimmedScope())
        assert plan.in_recycle_codes == ["E1", "E1-1", "E9"] and plan.to_create == ["E2"]

        # 唯一索引不含 is_deleted ⇒ 同码不能新建，只能从回收站恢复（设计前提，真库实测）
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                db.add(WpIndex(project_id=project.id, wp_code="E1", wp_name="重复", status=WpStatus.not_started))
                await db.flush()

        assert sorted(await plan_restore(db, project.id, ["E1", "E1-1", "E9"])) == ["E1", "E1-1"]
        restored = await restore_from_recycle_bin(db, project.id, ["E1", "E1-1", "E9"], kind="trim",
                                                  reason="程序裁剪恢复执行", actor_user_id=user.id)
        assert restored == ["E1", "E1-1"], "手工删除的 E9 不随粗裁恢复"
        live = (await db.execute(sa.text(
            "SELECT wi.wp_code, wi.is_deleted, wp.is_deleted, wi.cross_ref_codes FROM wp_index wi "
            "JOIN working_paper wp ON wp.wp_index_id = wi.id WHERE wi.project_id = :p ORDER BY wi.wp_code"),
            {"p": project.id})).all()
        assert [(r[0], r[1], r[2]) for r in live] == [("E1", False, False), ("E1-1", False, False), ("E9", True, True)]
        lineage = live[0][3][RECYCLE_LINEAGE_KEY]
        assert [(x["action"], x["kind"]) for x in lineage] == [("recycled", "trim"), ("restored", "trim")]
        epoch = (await db.execute(sa.text("SELECT epoch FROM wp_visibility_policy_epoch WHERE project_id = :p"),
                                  {"p": project.id})).scalar_one()
        assert epoch == 3, "移入 2 次 + 恢复 1 次，各递增一次可见性策略纪元"
    finally:
        await db.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()
