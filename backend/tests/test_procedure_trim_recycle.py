"""粗裁与已生成底稿联动（spec procedure-trim-generation-delegation-chain 需求 3 / 任务 8~9）。

SQLite 真 ORM + 真实 ProcedureTrimService preview / apply：
- 裁剪 ⇒ 范围内已生成底稿（主码、子表、程序表）两层移入回收站，去向记录写明原因；范围外与自带程序行的不动；
- 级联取消按底稿归属匹配（循环快照兜底成 ``A`` 的任务也取消）；
- 有编制内容的底稿未确认 ⇒ 409 且零副作用，确认后用同一预览凭证重试成功；
- 恢复执行 ⇒ 只恢复因裁剪移入的底稿，只重开因级联取消的任务（细裁取消的不动）；
- 区间程序行只管区间成员，成员自带程序行的不管。
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
from app.models.procedure_models import (  # noqa: E402
    ProcedureInstance,
    ProcedureRowDefinition,
    ProcedureRowTask,
    ProcedureRowTaskHistory,
)
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus  # noqa: E402
from app.models.wp_visibility_models import WpVisibilityPolicyEpoch  # noqa: E402
from app.services.procedure_trim_service import ProcedureTrimService  # noqa: E402
from app.services.workpaper_recycle_service import RECYCLE_LINEAGE_KEY  # noqa: E402

pytestmark = pytest.mark.asyncio
_HASH = "a" * 64


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
    project = Project(id=uuid.uuid4(), name="【测试】裁剪回收站", client_name="【测试】裁剪回收站",
                      status=ProjectStatus.execution, template_type="soe", report_scope="standalone", audit_year=2025)
    ids: dict[str, uuid.UUID] = {}
    async with factory() as s:
        s.add(project)
        await s.flush()
        for code in ("H3", "H3-1", "H3A", "H3-9", "G1", "A1", "A1-1", "A1-11", "D2-7", "D2-7-1", "D2-8"):
            idx = WpIndex(project_id=project.id, wp_code=code, wp_name=f"底稿{code}", audit_cycle=code[0],
                          status=WpStatus.not_started)
            s.add(idx)
            await s.flush()
            wp = WorkingPaper(project_id=project.id, wp_index_id=idx.id, file_path="", source_type=WpSourceType.template,
                              file_version=1)
            s.add(wp)
            await s.flush()
            ids[code], ids[f"wp:{code}"] = idx.id, wp.id
        # H3-9 早已因别的原因进回收站（不应被「恢复执行」带回来）
        idx_h39 = await s.get(WpIndex, ids["H3-9"])
        idx_h39.is_deleted = True
        idx_h39.cross_ref_codes = {RECYCLE_LINEAGE_KEY: [{"action": "recycled", "kind": "manual", "reason": "手工删除"}]}
        (await s.get(WorkingPaper, ids["wp:H3-9"])).is_deleted = True
        for code, cycle in (("H3", "H"), ("G1", "G"), ("A1", "A"), ("A1-11", "A"), ("D2-6至D2-13", "D"), ("D2-8", "D")):
            inst = ProcedureInstance(project_id=project.id, audit_cycle=cycle, procedure_code=code,
                                     procedure_name=code, status="execute", wp_code=code)
            s.add(inst)
            await s.flush()
            ids[f"inst:{code}"] = inst.id
        await s.commit()
    w = {"factory": factory, "pid": project.id, "ids": ids, "user": uuid.uuid4()}
    w["t_h31"] = await _task(w, "H3-1", "assigned", cycle="A")          # 物化时循环兜底成 A
    w["t_h3_fine"] = await _task(w, "H3", "cancelled", applicability="not_applicable",
                                 history="trim_not_applicable")           # 细裁取消，恢复执行不应重开
    w["t_a111"] = await _task(w, "A1-11", "assigned", cycle="A")
    yield w
    await engine.dispose()


async def _task(w, code, workflow, *, applicability="execute", cycle=None, history=None) -> uuid.UUID:
    dk = f"{code}A::{code}A::{uuid.uuid4().hex[:12]}"
    async with w["factory"]() as s:
        s.add(ProcedureRowDefinition(definition_key=dk, template_code=f"{code}A", template_revision_hash=_HASH,
                                     sheet_key=f"{code}A", source_locator={}, program_no="1", procedure_text="程序",
                                     ref_snapshot=[], legacy_aliases=[], normalized_content={}))
        task = ProcedureRowTask(project_id=w["pid"], wp_index_id=w["ids"][code], definition_key=dk,
                                sheet_key=f"{code}A", wp_code=code, definition_revision_hash=_HASH,
                                audit_cycle_snapshot=cycle or code[0], applicability_status=applicability,
                                workflow_status=workflow, lock_version=1, assignment_version=1)
        s.add(task)
        await s.flush()
        if history:
            s.add(ProcedureRowTaskHistory(task_id=task.id, project_id=w["pid"], event_type=history,
                                          from_status="assigned", to_status=workflow))
        await s.commit()
        return task.id


def _scope(code: str, cycle: str, status: str, reason: str | None = None) -> dict:
    entry = {"kind": "scope", "cycle": cycle, "wp_index_code": code, "target_status": status}
    if reason:
        entry["skip_reason"] = reason
    return entry


async def _preview(w, entries) -> dict:
    async with w["factory"]() as s:
        pv = await ProcedureTrimService(s).preview_scheme(w["pid"], actor_user_id=w["user"], entries=entries)
        await s.commit()
    return pv


async def _apply(w, entries, pv, *, confirm=False, request_id=None) -> dict:
    async with w["factory"]() as s:
        try:
            res = await ProcedureTrimService(s).apply_scheme(
                w["pid"], actor_user_id=w["user"], preview_id=uuid.UUID(pv["preview_id"]),
                request_id=request_id or uuid.uuid4().hex, entries=entries, confirm_substantive_recycle=confirm)
        except Exception:
            await s.rollback()
            raise
        await s.commit()
    return res


async def _state(w) -> dict:
    async with w["factory"]() as s:
        idx = {r.wp_code: r for r in (await s.execute(sa.select(WpIndex).where(WpIndex.project_id == w["pid"]))).scalars()}
        wps = {r.wp_index_id: r.is_deleted for r in (await s.execute(sa.select(WorkingPaper))).scalars()}
        tasks = {r.id: (r.workflow_status, r.applicability_status)
                 for r in (await s.execute(sa.select(ProcedureRowTask))).scalars()}
        inst = {r.procedure_code: r.status for r in (await s.execute(sa.select(ProcedureInstance))).scalars()}
        epoch = await s.get(WpVisibilityPolicyEpoch, w["pid"])
    deleted = sorted(c for c, r in idx.items() if r.is_deleted)
    assert all(wps[r.id] == r.is_deleted for r in idx.values()), "两层删除状态不一致"
    return {"deleted": deleted, "index": idx, "tasks": tasks, "inst": inst, "epoch": epoch.epoch if epoch else 0}


async def test_trim_recycles_covered_workpapers_and_cascades_by_ownership(world):
    entries = [_scope("H3", "H", "not_applicable", "本期无投资性房地产")]
    pv = await _preview(world, entries)
    assert pv["recycle_preview"] == {"to_recycle": ["H3", "H3-1", "H3A"], "substantive": [], "to_restore": [],
                                     "to_reopen_tasks": 0}
    assert pv["summary"]["would_change"] == 2, "程序行 1 + 级联取消 H3-1 的任务 1（细裁已取消的不重复计）"
    res = await _apply(world, entries, pv)
    assert res["applied"] == 2 and res["recycled_codes"] == ["H3", "H3-1", "H3A"] and res["restored_codes"] == []
    st = await _state(world)
    assert st["deleted"] == ["H3", "H3-1", "H3-9", "H3A"], "G1 / A1 等范围外不动"
    assert st["tasks"][world["t_h31"]] == ("cancelled", "not_applicable"), "循环快照为 A 的任务也按底稿归属取消"
    assert st["tasks"][world["t_a111"]] == ("assigned", "execute")
    lineage = st["index"]["H3-1"].cross_ref_codes[RECYCLE_LINEAGE_KEY][-1]
    assert (lineage["action"], lineage["kind"], lineage["reason"], lineage["trim_codes"]) == (
        "recycled", "trim", "本期无投资性房地产", ["H3"])
    assert st["epoch"] >= 1, "移入回收站递增可见性策略纪元"


async def test_restore_brings_back_only_trim_recycled_and_reopens_only_cascade(world):
    trim = [_scope("H3", "H", "not_applicable")]
    await _apply(world, trim, await _preview(world, trim))
    restore = [_scope("H3", "H", "execute")]
    pv = await _preview(world, restore)
    assert pv["recycle_preview"]["to_restore"] == ["H3", "H3-1", "H3A"], "H3-9 因别的原因进回收站，不恢复"
    assert pv["recycle_preview"]["to_reopen_tasks"] == 1 and pv["summary"]["would_change"] == 2
    res = await _apply(world, restore, pv)
    assert res["restored_codes"] == ["H3", "H3-1", "H3A"] and res["applied"] == 2
    st = await _state(world)
    assert st["deleted"] == ["H3-9"]
    assert st["tasks"][world["t_h31"]] == ("unassigned", "execute"), "级联取消的重开为待委派"
    assert st["tasks"][world["t_h3_fine"]] == ("cancelled", "not_applicable"), "细裁取消的不随粗裁恢复"
    assert st["index"]["H3"].cross_ref_codes[RECYCLE_LINEAGE_KEY][-1]["action"] == "restored"


async def test_substantive_workpaper_requires_confirmation(world):
    async with world["factory"]() as s:
        (await s.get(WorkingPaper, world["ids"]["wp:H3-1"])).content_revision = 3
        await s.execute(sa.text("INSERT INTO checklist_responses (id, wp_id, item_id, updated_by) VALUES (:i, :w, 'x', :u)"),
                        {"i": uuid.uuid4().hex, "w": world["ids"]["wp:H3-1"].hex, "u": uuid.uuid4().hex})
        await s.commit()
    entries = [_scope("H3", "H", "not_applicable")]
    pv = await _preview(world, entries)
    [item] = pv["recycle_preview"]["substantive"]
    assert item["wp_code"] == "H3-1" and item["substantive_reasons"] == ["已保存过 3 次", "人工填写 1 项"]
    with pytest.raises(HTTPException) as err:
        await _apply(world, entries, pv, request_id="r-1")
    assert err.value.status_code == 409 and err.value.detail["error"] == "substantive_recycle_unconfirmed"
    assert err.value.detail["codes"] == ["H3-1"]
    st = await _state(world)
    assert st["deleted"] == ["H3-9"] and st["inst"]["H3"] == "execute", "未确认 ⇒ 零副作用"
    res = await _apply(world, entries, pv, confirm=True, request_id="r-2")
    assert res["recycled_codes"] == ["H3", "H3-1", "H3A"], "预览凭证未被失败的一次消费，确认后可重试"


async def test_nearest_program_row_and_range_rows(world):
    entries = [_scope("A1", "A", "not_applicable"), _scope("D2-6至D2-13", "D", "skip")]
    pv = await _preview(world, entries)
    assert pv["recycle_preview"]["to_recycle"] == ["A1", "A1-1", "D2-7", "D2-7-1"], (
        "A1-11、D2-8 自带程序行，不随母码 / 区间裁剪")
    await _apply(world, entries, pv)
    st = await _state(world)
    assert st["deleted"] == ["A1", "A1-1", "D2-7", "D2-7-1", "H3-9"]
    assert st["tasks"][world["t_a111"]] == ("assigned", "execute")
