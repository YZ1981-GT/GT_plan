# -*- coding: utf-8 -*-
"""准则切换与回收站 —— 真实 PostgreSQL（spec procedure-trim-generation-delegation-chain 批 3）。

``uq_wp_index_project_code`` 与 ``uq_working_paper_project_index`` 都不含 is_deleted。原先目标独有底稿遇到
同码软删行就「复活索引 + 新插一份 WorkingPaper」，必撞后者，单条保存点回滚后静默跳过（回执不说）——
切回原准则时，上次归档的底稿既回不来、也不报。现在：源独有底稿两层移入回收站（``standard_conversion``）；
切回时只恢复因准则切换移入的（原行原数据），手工删除的在 ``in_recycle_codes`` 注明，已裁的在
``skipped_trimmed_codes``。

全部数据建在一个外层事务里的【测试】项目上，用例结束回滚，不落库；生成的模板文件写到临时目录。
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.models.base import ProjectStatus, UserRole
from app.models.core import Project, User
from app.models.procedure_models import ProcedureInstance
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus
from app.services import wp_template_init_service
from app.services.workpaper_recycle_service import RECYCLE_LINEAGE_KEY, move_to_recycle_bin
from app.services.wp_standard_conversion_service import WpStandardConversionService

pytestmark = pytest.mark.pg_only

_SOE = {"entity_type": "soe", "scope": "standalone", "year": 2025}
_LISTED = {"entity_type": "listed", "scope": "standalone", "year": 2025}


async def _state(db, pid) -> dict[str, tuple]:
    """``{编码: (索引已删, [底稿已删...], 底稿 id 列表, 去向记录 [(action, kind)])}``。"""
    rows = (await db.execute(sa.text(
        "SELECT wi.wp_code, wi.is_deleted, wp.is_deleted, wp.id, wi.cross_ref_codes FROM wp_index wi "
        "LEFT JOIN working_paper wp ON wp.wp_index_id = wi.id WHERE wi.project_id = :p ORDER BY wi.wp_code"),
        {"p": pid})).all()
    out: dict[str, tuple] = {}
    for code, idx_deleted, wp_deleted, wp_id, cross in rows:
        lineage = [(x["action"], x["kind"]) for x in ((cross or {}).get(RECYCLE_LINEAGE_KEY) or [])]
        prev = out.get(code)
        out[code] = (idx_deleted, (prev[1] if prev else []) + [wp_deleted], (prev[2] if prev else []) + [wp_id],
                     lineage)
    return out


@pytest.mark.asyncio
async def test_round_trip_restores_conversion_archived_and_reports_other_recycled(tmp_path, monkeypatch):
    monkeypatch.setattr(wp_template_init_service, "STORAGE_DIR", tmp_path / "wp_storage")
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    conn = await engine.connect()
    trans = await conn.begin()
    db = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
    try:
        user = User(username=f"cvr_{uuid.uuid4().hex[:10]}", email=f"{uuid.uuid4().hex[:10]}@t.example",
                    hashed_password="x", role=UserRole.auditor, is_active=True)
        project = Project(name="【测试】准则切换回收站", client_name="【测试】准则切换回收站",
                          status=ProjectStatus.execution, template_type="soe", report_scope="standalone",
                          audit_year=2025, scenario="normal")
        db.add_all([user, project])
        await db.flush()
        pid = project.id
        papers: dict[str, uuid.UUID] = {}
        for code in ("Q1", "Q2"):
            idx = WpIndex(project_id=pid, wp_code=code, wp_name=f"底稿{code}", audit_cycle="Q",
                          status=WpStatus.not_started)
            db.add(idx)
            await db.flush()
            wp = WorkingPaper(project_id=pid, wp_index_id=idx.id, file_path="", file_version=1,
                              source_type=WpSourceType.template, parsed_data={"cells": {"A1": f"用户填写{code}"}})
            db.add(wp)
            await db.flush()
            papers[code] = wp.id
        db.add(ProcedureInstance(project_id=pid, audit_cycle="Q", procedure_code="Q5", procedure_name="Q5",
                                 status="skip", wp_code="Q5"))
        await db.flush()
        svc = WpStandardConversionService(db)

        # 第一次切换：Q1 只适用原准则 ⇒ 两层移入回收站；Q3 新建；Q5 已粗裁不建
        out1 = await svc.convert_workpapers(
            pid, {"shared": [], "source_only": ["Q1"], "target_only": ["Q3", "Q5"]}, _LISTED, changed_by=user.id)
        s1 = await _state(db, pid)
        assert s1["Q1"][:2] == (True, [True]), "源独有底稿两层一起移入回收站"
        assert s1["Q1"][3] == [("recycled", "standard_conversion")]
        assert "Q3" in s1 and "Q5" not in s1
        assert (out1["archived"], out1["created"], out1["restored"]) == (1, 1, 0)
        assert out1["skipped_trimmed_codes"] == ["Q5"] and out1["in_recycle_codes"] == []

        # Q2 被手工删除（别的原因进回收站）
        await move_to_recycle_bin(db, pid, ["Q2"], kind="manual", reason="手工删除", actor_user_id=user.id)

        # 切回原准则：Q1 回来（原行原数据），Q2 不动只注明，Q4 新建，Q3 移入回收站
        out2 = await svc.convert_workpapers(
            pid, {"shared": [], "source_only": ["Q3"], "target_only": ["Q1", "Q2", "Q4"]}, _SOE, changed_by=user.id)
        s2 = await _state(db, pid)
        assert s2["Q1"][:3] == (False, [False], [papers["Q1"]]), "因准则切换移入的两层恢复原行，不新插底稿"
        assert s2["Q1"][3] == [("recycled", "standard_conversion"), ("restored", "standard_conversion")]
        assert s2["Q2"][:3] == (True, [True], [papers["Q2"]]), "手工删除的不随准则切回恢复"
        assert s2["Q3"][:2] == (True, [True]) and s2["Q4"][:2] == (False, [False])
        assert out2["restored_codes"] == ["Q1"] and out2["in_recycle_codes"] == ["Q2"]
        assert (out2["archived"], out2["created"], out2["restored"]) == (1, 1, 1)

        q1 = await db.get(WorkingPaper, papers["Q1"])
        await db.refresh(q1)
        assert q1.parsed_data["cells"] == {"A1": "用户填写Q1"}, "填写内容随原行回来"
        assert [x["action"] for x in q1.parsed_data["_conversion_lineage"]] == ["archived_on_standard_change"]
        epoch = (await db.execute(sa.text("SELECT epoch FROM wp_visibility_policy_epoch WHERE project_id = :p"),
                                  {"p": pid})).scalar_one()
        assert epoch == 4, "两次归档 + 手工删除 + 恢复，各递增一次可见性策略纪元"
    finally:
        await db.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()
