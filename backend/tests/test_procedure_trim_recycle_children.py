"""粗裁应用联动 × 母码跟随下级程序行（spec trim-generation-plan-linkage R4）。

SQLite 真 ORM + 真实 ProcedureTrimService preview / apply：
- 科目程序全部裁掉 ⇒ 已生成的科目审定表（母码 ``D2``）随子表一起移入回收站；
- 之后只恢复其中一条下级程序行 ⇒ 母码也从回收站恢复（「某条程序行管哪些底稿」按 ``deciders`` 判，
  不按当时回报的决定者判 —— 后者在全裁时是第一条下级行，只恢复别的下级行时会漏掉母码）。
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401
from app.models.base import Base, ProjectStatus  # noqa: E402
from app.models.core import Project  # noqa: E402
from app.models.procedure_models import ProcedureInstance  # noqa: E402
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus  # noqa: E402
from app.services import procedure_trim_service as trim_service_module  # noqa: E402
from app.services.procedure_trim_service import ProcedureTrimService  # noqa: E402

pytestmark = pytest.mark.asyncio
D2_ROWS = ("D2-1至D2-4", "D2-5", "D2-6至D2-13")


@pytest.fixture
async def world():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(sa.text(
            "CREATE TABLE checklist_responses (id TEXT PRIMARY KEY, project_id TEXT, wp_id TEXT NOT NULL, "
            "item_id TEXT, updated_by TEXT)"
        ))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    project = Project(id=uuid.uuid4(), name="【测试】母码跟随", client_name="【测试】母码跟随",
                      status=ProjectStatus.execution, template_type="soe", report_scope="standalone", audit_year=2025)
    async with factory() as s:
        s.add(project)
        await s.flush()
        for code in ("D2", "D2-1", "D2-5", "D3"):
            idx = WpIndex(project_id=project.id, wp_code=code, wp_name=f"底稿{code}", audit_cycle="D",
                          status=WpStatus.not_started)
            s.add(idx)
            await s.flush()
            s.add(WorkingPaper(project_id=project.id, wp_index_id=idx.id, file_path="",
                               source_type=WpSourceType.template, file_version=1))
        for i, code in enumerate((*D2_ROWS, "D3")):
            s.add(ProcedureInstance(project_id=project.id, audit_cycle="D", procedure_code=code, procedure_name=code,
                                    status="execute", wp_code=code, sort_order=i * 10))
        await s.commit()
    yield {"factory": factory, "pid": project.id, "user": uuid.uuid4()}
    await engine.dispose()


def _entry(code: str, status: str) -> dict:
    entry = {"kind": "scope", "cycle": "D", "wp_index_code": code, "target_status": status}
    if status != "execute":
        entry["skip_reason"] = "本期无应收账款"
    return entry


async def _preview_apply(w, entries) -> tuple[dict, dict]:
    async with w["factory"]() as s:
        pv = await ProcedureTrimService(s).preview_scheme(w["pid"], actor_user_id=w["user"], entries=entries)
        await s.commit()
    async with w["factory"]() as s:
        res = await ProcedureTrimService(s).apply_scheme(
            w["pid"], actor_user_id=w["user"], preview_id=uuid.UUID(pv["preview_id"]),
            request_id=uuid.uuid4().hex, entries=entries)
        await s.commit()
    return pv, res


async def _deleted(w) -> list[str]:
    async with w["factory"]() as s:
        rows = (await s.execute(sa.select(WpIndex.wp_code).where(
            WpIndex.project_id == w["pid"], WpIndex.is_deleted == sa.true()))).scalars().all()
    return sorted(rows)


async def test_trim_all_subject_rows_recycles_subject_audit_sheet(world):
    pv, res = await _preview_apply(world, [_entry(c, "not_applicable") for c in D2_ROWS])
    assert pv["recycle_preview"]["to_recycle"] == ["D2", "D2-1", "D2-5"], "审定表 D2 随科目程序一起裁掉"
    assert res["recycled_codes"] == ["D2", "D2-1", "D2-5"]
    assert await _deleted(world) == ["D2", "D2-1", "D2-5"], "D3 有自己的程序行，不动"


async def test_partial_trim_keeps_subject_audit_sheet(world):
    pv, res = await _preview_apply(world, [_entry("D2-1至D2-4", "not_applicable"), _entry("D2-5", "not_applicable")])
    assert pv["recycle_preview"]["to_recycle"] == ["D2-1", "D2-5"], "还有一条下级程序行执行 ⇒ 审定表保留"
    assert await _deleted(world) == ["D2-1", "D2-5"]


async def test_restoring_one_child_row_restores_subject_audit_sheet(world):
    await _preview_apply(world, [_entry(c, "not_applicable") for c in D2_ROWS])
    # 只提交一条恢复（参照项目 / 智能裁剪等调用方会只提交部分条目）
    pv, res = await _preview_apply(world, [_entry("D2-5", "execute")])
    assert pv["recycle_preview"]["to_restore"] == ["D2", "D2-5"], "D2 的决定者此时回报 D2-1至D2-4，但它也归 D2-5 管"
    assert res["restored_codes"] == ["D2", "D2-5"]
    assert await _deleted(world) == ["D2-1"]


async def test_old_preview_cannot_overwrite_newer_scope_decision(world):
    """两份 preview 指向同一程序行：后应用的旧 preview 必须 409，不能覆盖较新决定。"""
    entries = [_entry("D2-5", "not_applicable")]
    async with world["factory"]() as s:
        old = await ProcedureTrimService(s).preview_scheme(world["pid"], actor_user_id=world["user"], entries=entries)
        await s.commit()

    await _preview_apply(world, entries)
    async with world["factory"]() as s:
        with pytest.raises(HTTPException) as ei:
            await ProcedureTrimService(s).apply_scheme(
                world["pid"], actor_user_id=world["user"], preview_id=uuid.UUID(old["preview_id"]),
                request_id=uuid.uuid4().hex, entries=entries,
            )
        assert ei.value.status_code == 409
        assert "粗裁目标版本已变化" in str(ei.value.detail)
        row = (await s.execute(sa.select(ProcedureInstance).where(
            ProcedureInstance.project_id == world["pid"], ProcedureInstance.wp_code == "D2-5",
        ))).scalar_one()
        assert row.status == "not_applicable" and row.skip_reason == "本期无应收账款"


async def test_trim_apply_takes_the_same_project_lock_as_generation(world, monkeypatch):
    calls = []

    async def record_lock(_db, project_id):
        calls.append(project_id)

    monkeypatch.setattr(trim_service_module, "lock_project_procedure_scope", record_lock)
    await _preview_apply(world, [_entry("D3", "not_applicable")])
    assert calls == [world["pid"]], "preview 不锁；真正 apply 必须在重读 scope 前取项目共锁"
