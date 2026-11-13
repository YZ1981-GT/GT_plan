"""本地公式保存与旧确认快照：隔离 SQLite，全部调用生产函数。"""
from __future__ import annotations

from copy import deepcopy

import pytest
import sqlalchemy as sa

from app.models.formula_setting_models import FormulaSyncItem
from app.services.formula_settings import project_ops
from app.services.formula_settings.errors import SyncItemStale
from app.services.formula_settings.pending import upsert_pending
from app.services.formula_settings.publish import publish_global

from ._env import STD, add_global_row, add_project, add_project_row, make_db, pending_items, project_rows

SLOT = "balance_sheet:BS-001"
OLD, UPSTREAM, LOCAL, EDIT = "1", "2", "3", "4"


async def seed_conflict(db):
    await add_global_row(db, "BS-001", OLD)
    pid = await add_project(db, "【测试】本地修订号")
    await add_project_row(db, pid, "BS-001", LOCAL, base_formula=OLD)
    await db.commit()
    await publish_global(db, domain="report", scope=STD, user_id=None, changes=[
        {"slot_key": SLOT, "definition": {"formula": UPSTREAM}, "expected_version": 1}])
    await db.commit()
    return pid, (await pending_items(db, pid))[0]


def upstream_snapshot(item):
    return deepcopy({name: getattr(item, name) for name in (
        "id", "base_definition", "upstream_definition", "upstream_version", "reason", "publish_id",
        "upstream_origin", "upstream_template_id", "status", "created_at")})


async def save(db, pid, formula):
    row = (await project_rows(db, pid))["BS-001"]
    return await project_ops.save_overrides(db, domain="report", project_id=pid, user_id=None, items=[
        {"slot_key": SLOT, "definition": {"formula": formula, "_structure": {"transient": True}},
         "expected_version": row.formula_version}])


@pytest.mark.parametrize("choice", ["adopt", "keep", "custom"])
async def test_local_save_invalidates_old_revision_before_resolve(choice):
    async with make_db() as factory, factory() as db:
        pid, item = await seed_conflict(db)
        item_id, revision = item.id, int(item.revision)
        before = upstream_snapshot(item)
        await save(db, pid, EDIT)
        await db.commit()
        # 保持对旧 ORM 对象的引用：RETURNING 必须刷新同一对象，不能只改数据库。
        assert item.revision == revision + 1
        assert item.local_definition["formula"] == EDIT
        assert "_structure" not in item.local_definition
        assert upstream_snapshot(item) == before
        with pytest.raises(SyncItemStale, match="刷新") as exc:
            await project_ops.resolve_items(db, project_id=pid, user_id=None, resolutions=[{
                "item_id": str(item_id), "revision": revision, "choice": choice,
                "custom_definition": {"formula": "5"}}])
        assert exc.value.status_code == 409
        assert (await project_rows(db, pid))["BS-001"].formula == EDIT
        assert (await pending_items(db, pid))[0].revision == revision + 1
        await project_ops.resolve_items(db, project_id=pid, user_id=None, resolutions=[{
            "item_id": str(item_id), "revision": revision + 1, "choice": choice,
            "custom_definition": {"formula": "5"}}])
        await db.commit()
        row = (await project_rows(db, pid))["BS-001"]
        assert row.formula == {"adopt": UPSTREAM, "keep": EDIT, "custom": "5"}[choice]
        assert row.base_definition["formula"] == UPSTREAM
        assert await pending_items(db, pid) == []


async def test_repeated_local_saves_increment_once_each_and_restore_still_resolves():
    async with make_db() as factory, factory() as db:
        pid, item = await seed_conflict(db)
        before, revision = upstream_snapshot(item), int(item.revision)
        for offset, formula in enumerate(("4", "5", "6"), 1):
            await save(db, pid, formula)
            assert item.revision == revision + offset
            assert item.local_definition["formula"] == formula
            assert upstream_snapshot(item) == before
        row = (await project_rows(db, pid))["BS-001"]
        await project_ops.restore_global(db, domain="report", project_id=pid, user_id=None,
                                         slot_keys=[SLOT], expected_versions=[row.formula_version])
        await db.commit()
        assert await pending_items(db, pid) == []
        assert await project_rows(db, pid) == {}
        await db.refresh(item)
        assert (item.status, item.resolution, item.revision) == ("resolved", "adopt", revision + 3)


async def test_save_without_pending_never_creates_or_reopens_an_item():
    async with make_db() as factory, factory() as db:
        await add_global_row(db, "BS-001", OLD)
        pid = await add_project(db, "【测试】没有待确认")
        await project_ops.save_overrides(db, domain="report", project_id=pid, user_id=None,
                                         items=[{"slot_key": SLOT, "definition": {"formula": LOCAL}}])
        assert await db.scalar(sa.select(sa.func.count()).select_from(FormulaSyncItem)) == 0
        item = await upsert_pending(db, project_id=pid, domain="report", slot_key=SLOT, slot_label="报表行",
                                    reason="conflict", base_definition={"formula": OLD},
                                    upstream_definition={"formula": UPSTREAM}, upstream_version=2,
                                    local_definition={"formula": LOCAL}, publish_id=None)
        await project_ops.resolve_items(db, project_id=pid, user_id=None, resolutions=[{
            "item_id": str(item.id), "revision": item.revision, "choice": "keep"}])
        revision, local = int(item.revision), deepcopy(item.local_definition)
        await save(db, pid, EDIT)
        await db.commit()
        await db.refresh(item)
        assert (item.status, item.revision, item.local_definition) == ("resolved", revision, local)
        assert await pending_items(db, pid) == []
        assert await db.scalar(sa.select(sa.func.count()).select_from(FormulaSyncItem)) == 1
        assert (await project_rows(db, pid))["BS-001"].formula == EDIT
