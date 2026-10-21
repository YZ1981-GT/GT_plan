"""报表域全局发布：预览 / CAS / 各分类效果 / 待确认更新 / 幂等 / 原子 / 审计（R2~R4）。"""
from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.models.base import ProjectStatus
from app.models.formula_setting_models import FormulaPublish
from app.models.report_models import ReportConfig
from app.services.formula_settings import publish as publish_mod
from app.services.formula_settings.engine import Decisions
from app.services.formula_settings.errors import VersionConflict, VersionRequired
from app.services.formula_settings.publish import preview_global, publish_global
from app.services.formula_settings.sync import ConflictChoice, ProjectChoice

from ._env import (
    STD,
    add_global_row,
    add_project,
    add_project_row,
    audit_actions,
    make_db,
    pending_items,
    project_rows,
)

OLD, NEW, MINE = "TB('1001','期末余额')", "TB('1001','期末余额')+TB('1012','期末余额')", "ROW('BS-009')"
SLOT = "balance_sheet:BS-001"


async def _world(db):
    """六种项目：无适配 / 跟随副本 / 已一致 / 冲突 / 暂缓固定 / 已归档。"""
    await add_global_row(db, "BS-001", OLD)
    p = {
        "inherit": await add_project(db, "A继承"),
        "follow": await add_project(db, "B跟随"),
        "same": await add_project(db, "C一致"),
        "conflict": await add_project(db, "D冲突"),
        "pinned": await add_project(db, "E暂缓"),
        "frozen": await add_project(db, "F归档", status=ProjectStatus.archived),
        "other_std": await add_project(db, "G上市", template_type="listed"),
    }
    await add_project_row(db, p["follow"], "BS-001", OLD, base_formula=OLD)
    await add_project_row(db, p["same"], "BS-001", NEW, base_formula=OLD)
    await add_project_row(db, p["conflict"], "BS-001", MINE, base_formula=OLD)
    await add_project_row(db, p["pinned"], "BS-001", OLD, base_formula=OLD, pinned=True)
    await db.commit()
    return p


def _change(version=1, formula=NEW):
    return [{"slot_key": SLOT, "definition": {"formula": formula}, "expected_version": version}]


async def test_preview_classifies_without_writing_and_is_repeatable():
    async with make_db() as factory, factory() as db:
        p = await _world(db)
        first = await preview_global(db, domain="report", scope=STD, changes=_change())
        again = await preview_global(db, domain="report", scope=STD, changes=_change())
        assert first == again
        cats = {i["project_id"]: i["category"] for i in first["items"]}
        assert cats == {str(p["follow"]): "follow", str(p["same"]): "same", str(p["conflict"]): "conflict",
                        str(p["pinned"]): "pinned", str(p["frozen"]): "frozen"}
        counts = first["summary"]["counts"]
        assert (counts["inherit"], counts["conflict"]) == (1, 1)
        assert str(p["other_std"]) not in {r["project_id"] for r in first["summary"]["projects"]}
        conflict = next(i for i in first["items"] if i["category"] == "conflict")
        assert (conflict["base_formula"], conflict["new_formula"], conflict["local_formula"]) == (OLD, NEW, MINE)
        g = (await db.execute(sa.select(ReportConfig).where(ReportConfig.applicable_standard == STD))).scalar_one()
        assert (g.formula, g.formula_version) == (OLD, 1)
        assert await db.scalar(sa.select(sa.func.count()).select_from(FormulaPublish)) == 0


@pytest.mark.parametrize(("version", "error"), [(None, VersionRequired), (7, VersionConflict)])
async def test_cas_rejects_whole_batch(version, error):
    async with make_db() as factory, factory() as db:
        await _world(db)
        changes = _change(version) + [{"slot_key": "balance_sheet:BS-NEW", "definition": {"formula": "1"},
                                       "structure": {"row_number": 99, "row_name": "新行"}}]
        with pytest.raises(error):
            await publish_global(db, domain="report", scope=STD, changes=changes, user_id=None)
        await db.rollback()
        rows = (await db.execute(sa.select(ReportConfig.row_code).where(ReportConfig.applicable_standard == STD)))
        assert [r[0] for r in rows] == ["BS-001"]


async def test_publish_effects_per_category():
    async with make_db() as factory, factory() as db:
        p = await _world(db)
        decisions = Decisions(project_choices={})
        result = await publish_global(db, domain="report", scope=STD, changes=_change(), user_id=None,
                                      decisions=decisions, request_id="req-1")
        await db.commit()
        g = (await db.execute(sa.select(ReportConfig).where(ReportConfig.applicable_standard == STD))).scalar_one()
        assert (g.formula, g.formula_version) == (NEW, 2)
        follow = (await project_rows(db, p["follow"]))["BS-001"]
        assert (follow.formula, follow.base_version, follow.base_definition["formula"]) == (NEW, 2, NEW)
        same = (await project_rows(db, p["same"]))["BS-001"]
        assert (same.formula, same.base_version) == (NEW, 2)
        conflict = (await project_rows(db, p["conflict"]))["BS-001"]
        assert (conflict.formula, conflict.base_version) == (MINE, 1)
        pinned = (await project_rows(db, p["pinned"]))["BS-001"]
        assert (pinned.formula, pinned.pinned) == (OLD, True)
        frozen = (await project_rows(db, p["frozen"]))["BS-001"]
        assert (frozen.formula, frozen.pinned) == (OLD, True)
        assert await project_rows(db, p["inherit"]) == {}
        pend = {(i.project_id, i.reason) for i in await pending_items(db)}
        assert pend == {(p["conflict"], "conflict"), (p["pinned"], "deferred")}
        changed = set(result["summary"]["changed_projects"])
        assert changed == {str(p["inherit"]), str(p["follow"])}
        assert {e["project_id"] for e in result["events"]} == changed
        assert result["versions"] == {SLOT: 2}


async def test_admin_choices_defer_adopt_keep():
    async with make_db() as factory, factory() as db:
        p = await _world(db)
        extra = await add_project(db, "H冲突2")
        await add_project_row(db, extra, "BS-001", "ROW('X')", base_formula=OLD)
        await db.commit()
        decisions = Decisions(
            project_choices={str(p["inherit"]): ProjectChoice.DEFER, str(p["follow"]): ProjectChoice.DEFER},
            conflict_choices={f"{p['conflict']}|{SLOT}": ConflictChoice.ADOPT, f"{extra}|{SLOT}": ConflictChoice.KEEP},
        )
        await publish_global(db, domain="report", scope=STD, changes=_change(), user_id=None, decisions=decisions)
        await db.commit()
        inherit = (await project_rows(db, p["inherit"]))["BS-001"]
        assert (inherit.formula, inherit.pinned, inherit.base_version) == (OLD, True, 1)
        follow = (await project_rows(db, p["follow"]))["BS-001"]
        assert (follow.formula, follow.pinned) == (OLD, True)
        adopted = (await project_rows(db, p["conflict"]))["BS-001"]
        assert (adopted.formula, adopted.base_version) == (NEW, 2)
        kept = (await project_rows(db, extra))["BS-001"]
        assert (kept.formula, kept.base_version, kept.base_definition["formula"]) == ("ROW('X')", 2, NEW)
        reasons = {i.project_id: i.reason for i in await pending_items(db)}
        assert reasons == {p["inherit"]: "deferred", p["follow"]: "deferred", p["pinned"]: "deferred"}


async def test_second_publish_updates_pending_instead_of_duplicating():
    async with make_db() as factory, factory() as db:
        p = await _world(db)
        await publish_global(db, domain="report", scope=STD, changes=_change(), user_id=None)
        await db.commit()
        await publish_global(db, domain="report", scope=STD, changes=_change(2, "TB('1001','期末余额')*2"),
                             user_id=None)
        await db.commit()
        items = await pending_items(db, p["conflict"])
        assert len(items) == 1
        item = items[0]
        assert (item.upstream_version, item.upstream_definition["formula"]) == (3, "TB('1001','期末余额')*2")
        assert item.base_definition["formula"] == OLD and item.reason == "conflict"


async def test_global_delete_follow_removes_local_conflict_asks():
    async with make_db() as factory, factory() as db:
        p = await _world(db)
        await publish_global(db, domain="report", scope=STD,
                             changes=[{"slot_key": SLOT, "definition": None, "expected_version": 1}], user_id=None)
        await db.commit()
        assert await project_rows(db, p["follow"]) == {}
        item = (await pending_items(db, p["conflict"]))[0]
        assert item.upstream_definition is None
        g = (await db.execute(sa.select(ReportConfig).where(ReportConfig.applicable_standard == STD))).scalar_one()
        assert g.is_deleted and g.formula_version == 2


async def test_request_id_is_idempotent():
    async with make_db() as factory, factory() as db:
        await _world(db)
        first = await publish_global(db, domain="report", scope=STD, changes=_change(), user_id=None,
                                     request_id="same")
        await db.commit()
        again = await publish_global(db, domain="report", scope=STD, changes=_change(), user_id=None,
                                     request_id="same")
        assert again["idempotent"] and again["publish_id"] == first["publish_id"]
        assert await db.scalar(sa.select(sa.func.count()).select_from(FormulaPublish)) == 1


async def test_template_origin_rows_are_skipped():
    async with make_db() as factory, factory() as db:
        await add_global_row(db, "BS-001", OLD)
        pid = await add_project(db, "订阅模板")
        await add_project_row(db, pid, "BS-001", "TPL()", base_formula="TPL()", base_origin="template")
        await db.commit()
        preview = await preview_global(db, domain="report", scope=STD, changes=_change())
        assert preview["summary"]["counts"]["template"] == 1
        await publish_global(db, domain="report", scope=STD, changes=_change(), user_id=None)
        await db.commit()
        row = (await project_rows(db, pid))["BS-001"]
        assert (row.formula, row.base_definition["formula"]) == ("TPL()", "TPL()")
        assert await pending_items(db, pid) == []


async def test_publish_is_atomic(monkeypatch):
    async with make_db() as factory, factory() as db:
        p = await _world(db)

        async def boom(*a, **k):
            raise RuntimeError("注入：审计写失败")

        monkeypatch.setattr(publish_mod, "audit_project", boom)
        with pytest.raises(RuntimeError):
            await publish_global(db, domain="report", scope=STD, changes=_change(), user_id=None)
        await db.rollback()
        g = (await db.execute(sa.select(ReportConfig).where(ReportConfig.applicable_standard == STD))).scalar_one()
        assert (g.formula, g.formula_version) == (OLD, 1)
        assert (await project_rows(db, p["follow"]))["BS-001"].formula == OLD
        assert await pending_items(db) == []
        assert await db.scalar(sa.select(sa.func.count()).select_from(FormulaPublish)) == 0


async def test_audit_global_entry_and_per_project_entries():
    async with make_db() as factory, factory() as db:
        p = await _world(db)
        await publish_global(db, domain="report", scope=STD, changes=_change(), user_id=None)
        await db.commit()
        actions = await audit_actions(db)
        assert [a for a, _ in actions].count("formula.global_published") == 1
        per = {pl.get("project_id"): pl for a, pl in actions if a == "formula.changed"}
        assert str(p["inherit"]) in per and str(p["conflict"]) in per and str(p["same"]) not in per
        e = per[str(p["follow"])]
        assert (e["module"], e["row_code"], e["old_formula"], e["new_formula"]) == ("report", "BS-001", OLD, NEW)


async def test_description_only_change_follows_unmodified_descriptions():
    async with make_db() as factory, factory() as db:
        await add_global_row(db, "BS-001", OLD)
        pid = await add_project(db, "说明跟随")
        row = await add_project_row(db, pid, "BS-001", OLD, base_formula=OLD)
        row.formula_description = None
        await db.commit()
        await publish_global(db, domain="report", scope=STD, changes=[
            {"slot_key": SLOT, "definition": {"formula_description": "新说明"}, "expected_version": 1}], user_id=None)
        await db.commit()
        r = (await project_rows(db, pid))["BS-001"]
        assert (r.formula, r.formula_description, r.base_version) == (OLD, "新说明", 2)
        assert await pending_items(db, pid) == []
