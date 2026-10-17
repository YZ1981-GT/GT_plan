"""整年度附注推倒重建（spec disclosure-note-template-word-realignment Phase 6，design §7）。

用户 2026-10-16：和平药房旧数据要清理，可以清空现有数据、按四表库重新生成。存量对齐（``note_project_realign_apply``）
只改编号 / 树字段、不动内容；本模块把一个项目一个年度的附注删掉重来：

- :func:`plan_rebuild`（只读）：现有行（在用 / 软删 / 有正文 / 有人编辑过 / 编号不在现行模板里）、附注推送状态、章节锁、
  模板节数、生成前置条件（报表有行）。
- :func:`rebuild_project`（调用方管事务，一个事务）：前置不满足即抛 → 锁行 → 备份（``write_backup``，``--restore`` 可原样
  恢复）→ 物理删除该年度全部附注（含软删：唯一索引含软删行，留着同编号重建会撞键；软删章节随旧数据一并清理）与附注域
  推送状态、章节锁 → 生成链（``strict``，不调大模型）→ 校验：编号集合 = 模板编号集合、无软删、无脱树（上级 id 都在）。
- 填数（公式推送）自管保存点与提交，由调用方在提交后另跑（命令行 ``realign_project_notes.py --rebuild``）。
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.formula_push_models import FormulaPushState
from app.models.report_models import DisclosureNote
from app.services.disclosure_engine import DisclosureEngine
from app.services.note_project_realign_apply import LOCKS, RealignError, RealignSkipped, write_backup

__all__ = ["plan_rebuild", "rebuild_project"]


async def _snapshot(db: AsyncSession, project_id: uuid.UUID, year: int, template_codes: set[str]) -> dict[str, Any]:
    t, fps = DisclosureNote.__table__, FormulaPushState.__table__
    rows = (await db.execute(sa.select(t.c.note_section, t.c.is_deleted, t.c.text_content, t.c.updated_by,
                                       t.c.section_id, t.c.parent_section_id)
                             .where(t.c.project_id == project_id, t.c.year == year))).all()
    active = [r for r in rows if not r.is_deleted]
    sids = {r.section_id for r in active if r.section_id}
    count = lambda table, *where: sa.select(sa.func.count()).select_from(table).where(*where)  # noqa: E731
    return {
        "rows": len(rows), "active": len(active), "deleted": len(rows) - len(active),
        "with_text": sum(bool((r.text_content or "").strip()) for r in active),
        "edited": sum(r.updated_by is not None for r in rows),
        "not_in_template": sorted({r.note_section for r in active} - template_codes),
        "orphans": sorted(r.note_section for r in active if r.parent_section_id and r.parent_section_id not in sids),
        "push_states": (await db.execute(count(fps, fps.c.project_id == project_id, fps.c.year == year,
                                                fps.c.domain == "note"))).scalar_one(),
        "locks": (await db.execute(count(LOCKS, LOCKS.c.project_id == project_id, LOCKS.c.year == year))).scalar_one(),
    }


async def plan_rebuild(db: AsyncSession, project_id: uuid.UUID, year: int) -> dict[str, Any]:
    """只读：重建前的现状与前置条件。项目不存在 / 已删除抛 :class:`RealignSkipped`。"""
    deleted = (await db.execute(sa.select(Project.is_deleted).where(Project.id == project_id))).scalar_one_or_none()
    if deleted is None or deleted:
        raise RealignSkipped("项目不存在或已删除（回收站），不处理")
    engine = DisclosureEngine(db)
    template_type = await engine._get_active_template_type(project_id)
    if template_type not in ("soe", "listed"):
        raise RealignError(f"项目模板类型为 {template_type}，只支持国企 / 上市种子")
    templates = await engine._load_templates(project_id, template_type)
    codes = {t["note_section"] for t in templates}
    from app.services.prerequisite_checker import PrerequisiteChecker

    check = await PrerequisiteChecker().check(db, project_id, year, "generate_notes")
    return {"project_id": str(project_id), "year": year, "template_type": template_type,
            "report_scope": (await engine._get_project_basic_info(project_id)).get("report_scope"),
            "templates": len(codes), "prerequisite": check, "before": await _snapshot(db, project_id, year, codes),
            "_codes": codes}


async def rebuild_project(db: AsyncSession, project_id: uuid.UUID, year: int, *,
                          backup_path: Path | None = None) -> dict[str, Any]:
    """删掉该年度全部附注后按现行模板重新生成；任一校验不过即抛 :class:`RealignError`（调用方回滚）。

    ``backup_path`` 为空时不备份（只给 SQLite 用例用；命令行 ``--apply`` 必传）。
    """
    report = await plan_rebuild(db, project_id, year)
    codes: set[str] = report.pop("_codes")
    if not report["prerequisite"].get("ok"):
        raise RealignError(f"生成前置条件不满足：{report['prerequisite']}")
    t, fps = DisclosureNote.__table__, FormulaPushState.__table__
    await db.execute(sa.select(t.c.id).where(t.c.project_id == project_id, t.c.year == year).with_for_update())
    if backup_path is not None:
        report["backup"] = await write_backup(db, project_id, year, backup_path)
    deleted = {
        "disclosure_notes": (await db.execute(sa.delete(t).where(
            t.c.project_id == project_id, t.c.year == year))).rowcount,
        "formula_push_state": (await db.execute(sa.delete(fps).where(
            fps.c.project_id == project_id, fps.c.year == year, fps.c.domain == "note"))).rowcount,
        "note_section_locks": (await db.execute(sa.delete(LOCKS).where(
            LOCKS.c.project_id == project_id, LOCKS.c.year == year))).rowcount,
    }
    if deleted["disclosure_notes"] != report["before"]["rows"]:
        raise RealignError(f"删除行数 {deleted['disclosure_notes']} 与锁定时 {report['before']['rows']} 不一致")
    created = await DisclosureEngine(db).generate_notes(project_id, year, report["template_type"], strict=True)
    await db.flush()
    after = await _snapshot(db, project_id, year, codes)
    got = {r["note_section"] for r in created}
    problems = [f"生成编号与模板不一致：缺 {sorted(codes - got)[:5]} 多 {sorted(got - codes)[:5]}"] if got != codes else []
    if after["active"] != len(codes) or after["deleted"]:
        problems.append(f"重建后在用 {after['active']} / 软删 {after['deleted']}，模板 {len(codes)}")
    if after["not_in_template"] or after["orphans"]:
        problems.append(f"不在模板里 {after['not_in_template'][:5]}，脱树 {after['orphans'][:5]}")
    if problems:
        raise RealignError("；".join(problems))
    report.update(deleted=deleted, after=after)
    return report
