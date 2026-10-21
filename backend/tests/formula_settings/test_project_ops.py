"""项目侧：保存适配 / 恢复为全局 / 处理待确认 / 应用到指定项目 / 设为全局与候选（R5~R7）。"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.models.formula_setting_models import FormulaPublish, FormulaSyncItem
from app.models.report_models import ReportConfig
from app.services.formula_settings import apply_ops, project_ops
from app.services.formula_settings.effective import effective_slots
from app.services.formula_settings.engine import Decisions
from app.services.formula_settings.errors import SyncItemStale, VersionConflict, VersionRequired
from app.services.formula_settings.publish import publish_global
from app.services.formula_settings.sync import ConflictChoice

from ._env import STD, add_global_row, add_project, add_project_row, make_db, pending_items, project_rows

OLD, NEW, MINE = "TB('1001','期末余额')", "TB('1001','期末余额')*2", "ROW('BS-009')"
SLOT = "balance_sheet:BS-001"


async def _seed(db):
    await add_global_row(db, "BS-001", OLD)
    await add_global_row(db, "BS-002", "TB('1002','期末余额')", row_number=2)
    return await add_project(db, "本项目"), await add_project(db, "其他项目")


async def test_save_creates_adaptation_with_global_baseline_and_cas():
    async with make_db() as factory, factory() as db:
        pid, _ = await _seed(db)
        out = await project_ops.save_overrides(db, domain="report", project_id=pid, user_id=None,
                                               items=[{"slot_key": SLOT, "definition": {"formula": MINE}}])
        await db.commit()
        row = (await project_rows(db, pid))["BS-001"]
        assert (row.formula, row.base_definition["formula"], row.base_version) == (MINE, OLD, 1)
        assert row.formula_category == "auto_calc"  # 未给出的字段沿用全局（补丁语义）
        version = row.formula_version
        assert out["events"] == [{"project_id": str(pid), "slot_keys": [SLOT]}]
        eff = await effective_slots(db, "report", pid)
        assert (eff[SLOT].layer, eff["balance_sheet:BS-002"].layer) == ("project", "global")
        with pytest.raises(VersionRequired):
            await project_ops.save_overrides(db, domain="report", project_id=pid, user_id=None,
                                             items=[{"slot_key": SLOT, "definition": {"formula": "1"}}])
        with pytest.raises(VersionConflict):
            await project_ops.save_overrides(db, domain="report", project_id=pid, user_id=None, items=[
                {"slot_key": SLOT, "definition": {"formula": "1"}, "expected_version": version + 5}])
        await db.rollback()
        ok = await project_ops.save_overrides(db, domain="report", project_id=pid, user_id=None, items=[
            {"slot_key": SLOT, "definition": {"formula": "2"}, "expected_version": version}])
        assert ok["saved"][0]["version"] == version + 1


async def test_restore_global_deletes_adaptation_and_closes_pending():
    async with make_db() as factory, factory() as db:
        pid, _ = await _seed(db)
        await add_project_row(db, pid, "BS-001", MINE, base_formula=OLD)
        await db.commit()
        await publish_global(db, domain="report", scope=STD, user_id=None,
                             changes=[{"slot_key": SLOT, "definition": {"formula": NEW}, "expected_version": 1}])
        await db.commit()
        assert len(await pending_items(db, pid)) == 1
        out = await project_ops.restore_global(db, domain="report", project_id=pid, slot_keys=[SLOT], user_id=None)
        await db.commit()
        assert await project_rows(db, pid) == {} and await pending_items(db, pid) == []
        item = (await db.execute(sa.select(FormulaSyncItem))).scalar_one()
        assert (item.status, item.resolution) == ("resolved", "adopt")
        assert out["events"][0]["slot_keys"] == [SLOT]


async def _conflict_item(db, pid):
    await add_project_row(db, pid, "BS-001", MINE, base_formula=OLD)
    await db.commit()
    await publish_global(db, domain="report", scope=STD, user_id=None,
                         changes=[{"slot_key": SLOT, "definition": {"formula": NEW}, "expected_version": 1}])
    await db.commit()
    return (await pending_items(db, pid))[0]


@pytest.mark.parametrize(("choice", "formula", "base"), [("adopt", NEW, NEW), ("keep", MINE, NEW),
                                                          ("custom", "ROW('X')", NEW)])
async def test_resolve_three_choices(choice, formula, base):
    async with make_db() as factory, factory() as db:
        pid, _ = await _seed(db)
        item = await _conflict_item(db, pid)
        await project_ops.resolve_items(db, project_id=pid, user_id=None, resolutions=[{
            "item_id": str(item.id), "choice": choice, "upstream_version": item.upstream_version,
            "custom_definition": {"formula": "ROW('X')"} if choice == "custom" else None}])
        await db.commit()
        row = (await project_rows(db, pid))["BS-001"]
        assert (row.formula, row.base_definition["formula"], row.pinned) == (formula, base, False)
        await db.refresh(item)
        assert (item.status, item.resolution) == ("resolved", choice)


async def test_resolve_rejects_stale_item():
    async with make_db() as factory, factory() as db:
        pid, _ = await _seed(db)
        item = await _conflict_item(db, pid)
        item_id, version = str(item.id), item.upstream_version
        with pytest.raises(SyncItemStale):
            await project_ops.resolve_items(db, project_id=pid, user_id=None, resolutions=[
                {"item_id": item_id, "choice": "adopt", "upstream_version": version - 1}])
        await db.rollback()
        await project_ops.resolve_items(db, project_id=pid, user_id=None, resolutions=[
            {"item_id": item_id, "choice": "adopt", "upstream_version": version}])
        await db.commit()
        with pytest.raises(SyncItemStale):
            await project_ops.resolve_items(db, project_id=pid, user_id=None, resolutions=[
                {"item_id": item_id, "choice": "keep", "upstream_version": version}])


async def test_apply_to_projects_inherit_writes_conflict_asks_or_adopts():
    async with make_db() as factory, factory() as db:
        src, inherit = await _seed(db)
        conflicted = await add_project(db, "冲突目标")
        await add_project_row(db, src, "BS-001", MINE, base_formula=OLD)
        await add_project_row(db, conflicted, "BS-001", "ROW('Y')", base_formula=OLD)
        await db.commit()
        preview = await apply_ops.apply_preview(db, domain="report", project_id=src, slot_keys=[SLOT],
                                                target_ids=[inherit, conflicted])
        assert {i["project_id"]: i["category"] for i in preview["items"]} == {
            str(inherit): "inherit", str(conflicted): "conflict"}
        out = await apply_ops.apply_to_projects(db, domain="report", project_id=src, slot_keys=[SLOT],
                                                target_ids=[inherit, conflicted], decisions=Decisions(),
                                                user_id=None)
        await db.commit()
        row = (await project_rows(db, inherit))["BS-001"]
        assert (row.formula, row.base_definition["formula"]) == (MINE, OLD)
        item = (await pending_items(db, conflicted))[0]
        assert (item.upstream_origin, item.upstream_definition["formula"]) == ("project", MINE)
        assert out["events"] == [{"project_id": str(inherit), "slot_keys": [SLOT]}]
        # 目标项目采用推送：定义 = 来源，基线仍是目标自己的上游
        await project_ops.resolve_items(db, project_id=conflicted, user_id=None, resolutions=[
            {"item_id": str(item.id), "choice": "adopt"}])
        await db.commit()
        row = (await project_rows(db, conflicted))["BS-001"]
        assert (row.formula, row.base_definition["formula"]) == (MINE, OLD)
        again = await apply_ops.apply_to_projects(
            db, domain="report", project_id=src, slot_keys=[SLOT], target_ids=[conflicted],
            decisions=Decisions(default_conflict=ConflictChoice.ADOPT), user_id=None)
        assert again["summary"]["counts"]["same"] == 1


async def test_promote_admin_publishes_and_source_becomes_same():
    async with make_db() as factory, factory() as db:
        src, other = await _seed(db)
        await add_project_row(db, src, "BS-001", MINE, base_formula=OLD)
        await db.commit()
        preview = await apply_ops.promote_preview(db, domain="report", project_id=src, slot_keys=[SLOT])
        assert {i["project_id"]: i["category"] for i in preview["items"]} == {str(src): "same"}
        out = await apply_ops.promote(db, domain="report", project_id=src, slot_keys=[SLOT], is_admin=True,
                                      user_id=None)
        await db.commit()
        g = (await db.execute(sa.select(ReportConfig).where(
            ReportConfig.applicable_standard == STD, ReportConfig.row_code == "BS-001"))).scalar_one()
        assert (g.formula, g.formula_version) == (MINE, 2)
        row = (await project_rows(db, src))["BS-001"]
        assert (row.formula, row.base_version) == (MINE, 2)
        assert str(other) in out["summary"]["changed_projects"]


async def test_promote_non_admin_creates_candidate_and_admin_reviews():
    async with make_db() as factory, factory() as db:
        src, other = await _seed(db)
        await add_project_row(db, src, "BS-001", MINE, base_formula=OLD)
        await db.commit()
        out = await apply_ops.promote(db, domain="report", project_id=src, slot_keys=[SLOT], is_admin=False,
                                      user_id=uuid.uuid4())
        await db.commit()
        cand = out["candidate"]
        assert cand["status"] == "pending"
        g = (await db.execute(sa.select(ReportConfig).where(
            ReportConfig.applicable_standard == STD, ReportConfig.row_code == "BS-001"))).scalar_one()
        assert g.formula == OLD  # 候选不改全局
        preview = await apply_ops.candidate_preview(db, uuid.UUID(cand["id"]))
        assert preview["global_changed_since_submit"] == []
        res = await apply_ops.review_candidate(db, publish_id=uuid.UUID(cand["id"]), approve=True, user_id=None)
        await db.commit()
        await db.refresh(g)
        assert g.formula == MINE and res["candidate"]["status"] == "published"
        sources = {r.source for r in (await db.execute(sa.select(FormulaPublish))).scalars()}
        assert sources == {"candidate"}
        assert str(other) in res["summary"]["changed_projects"]


async def test_frozen_project_cannot_adapt():
    from app.models.base import ProjectStatus
    from app.services.formula_settings.errors import Forbidden

    async with make_db() as factory, factory() as db:
        await add_global_row(db, "BS-001", OLD)
        pid = await add_project(db, "已归档", status=ProjectStatus.archived)
        await db.commit()
        with pytest.raises(Forbidden):
            await project_ops.save_overrides(db, domain="report", project_id=pid, user_id=None,
                                             items=[{"slot_key": SLOT, "definition": {"formula": MINE}}])
