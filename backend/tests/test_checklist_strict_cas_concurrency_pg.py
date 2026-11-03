"""真实 PostgreSQL：strict checklist CAS 对尚不存在行的并发首建也必须串行。"""
from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services.checklist_response_cas import lock_and_check_versions

pytestmark = pytest.mark.pg_only


def _engine(*, schema: str | None = None):
    from app.core.config import settings

    if not str(settings.DATABASE_URL).startswith("postgresql"):
        raise RuntimeError("本用例必须使用真实 PostgreSQL")
    connect_args: dict = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    if schema:
        connect_args["server_settings"] = {"search_path": schema}
    return create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=connect_args)


@pytest.mark.asyncio
async def test_two_strict_clients_cannot_both_create_the_same_absent_batch():
    schema = f"tmp_checklist_cas_{uuid.uuid4().hex[:12]}"
    wp_id = uuid.uuid4()
    items_a = [SimpleNamespace(item_id=key, if_match=None) for key in ("new-a", "new-b")]
    items_b = [SimpleNamespace(item_id=key, if_match=None) for key in ("new-a", "new-b")]
    admin = _engine()
    scoped = None
    release_first = asyncio.Event()
    first_inserted = asyncio.Event()
    second_started = asyncio.Event()
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            await conn.exec_driver_sql(
                f'CREATE TABLE "{schema}".checklist_responses ('
                "wp_id UUID NOT NULL, item_id TEXT NOT NULL, remark TEXT, "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(), "
                "UNIQUE (wp_id, item_id))"
            )
        scoped = _engine(schema=schema)
        Session = async_sessionmaker(scoped, expire_on_commit=False)

        async def save_first() -> str:
            async with Session() as db, db.begin():
                assert await lock_and_check_versions(
                    db, wp_id, items_a, require_if_match=True,
                ) == {}
                await db.execute(
                    sa.text(
                        "INSERT INTO checklist_responses (wp_id,item_id,remark) "
                        "VALUES (:wp,'new-a','client-a'),(:wp,'new-b','client-a')"
                    ),
                    {"wp": wp_id},
                )
                first_inserted.set()
                await release_first.wait()
            return "saved"

        async def save_second() -> HTTPException:
            await first_inserted.wait()
            second_started.set()
            try:
                async with Session() as db, db.begin():
                    await lock_and_check_versions(db, wp_id, items_b, require_if_match=True)
                    await db.execute(
                        sa.text(
                            "INSERT INTO checklist_responses (wp_id,item_id,remark) "
                            "VALUES (:wp,'new-a','client-b'),(:wp,'new-b','client-b')"
                        ),
                        {"wp": wp_id},
                    )
            except HTTPException as exc:
                return exc
            raise AssertionError("第二个 strict 客户端未收到版本前置条件错误")

        first_task = asyncio.create_task(save_first())
        await first_inserted.wait()
        second_task = asyncio.create_task(save_second())
        await second_started.wait()
        await asyncio.sleep(0.1)
        assert not second_task.done(), "后到事务未等待不存在行的逻辑键锁"
        release_first.set()
        assert await asyncio.wait_for(first_task, timeout=5) == "saved"
        conflict = await asyncio.wait_for(second_task, timeout=5)
        assert conflict.status_code == 428
        assert conflict.detail["code"] == "version_required"
        assert conflict.detail["item_id"] == "new-a"

        async with Session() as db:
            rows = (await db.execute(sa.text(
                "SELECT item_id, remark FROM checklist_responses ORDER BY item_id"
            ))).all()
        assert rows == [("new-a", "client-a"), ("new-b", "client-a")]
    finally:
        release_first.set()
        if scoped is not None:
            await scoped.dispose()
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin.dispose()


@pytest.mark.asyncio
async def test_strict_cas_and_store_mirror_share_the_same_item_lock(monkeypatch):
    """Mirror 必须等 CAS 提交后再读 base，不能用旧 JSON 覆盖已成功的 HTML 保存。"""
    import importlib
    import json

    from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY
    from app.services.workpaper_sync.store_mirror import mirror_projection_into_store

    adapter_id = "d3.prepaid_receipts_detail"
    plan = STORE_MERGE_REGISTRY[adapter_id]
    provider = importlib.import_module(
        f"app.services.workpaper_sync.{plan.provider_module}"
    )
    item_id = provider.STORE_ITEM_ID
    merge_called = asyncio.Event()
    observed_bases: list[list[dict[str, object]]] = []

    def merge_rows(*, projection, base_rows):
        del projection
        observed_bases.append(base_rows)
        merge_called.set()
        row = dict(base_rows[0])
        row["oo_value"] = "from-oo"
        return [row], 1, 1, {"oo_value"}

    monkeypatch.setattr(provider, plan.merge_rows_fn, merge_rows)
    schema = f"tmp_checklist_mirror_{uuid.uuid4().hex[:12]}"
    project_id = uuid.uuid4()
    wp_id = uuid.uuid4()
    initial = json.dumps([{"rowId": "r1", "html_value": "old"}])
    html_value = json.dumps(
        [{"rowId": "r1", "html_value": "new", "html_only": "kept"}]
    )
    admin = _engine()
    scoped = None
    release_html = asyncio.Event()
    html_updated = asyncio.Event()
    mirror_started = asyncio.Event()
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            await conn.exec_driver_sql(
                f'CREATE TABLE "{schema}".checklist_responses ('
                "wp_id UUID NOT NULL, item_id TEXT NOT NULL, remark TEXT, "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(), "
                "UNIQUE (wp_id, item_id))"
            )
            await conn.execute(
                sa.text(
                    f'INSERT INTO "{schema}".checklist_responses '
                    "(wp_id,item_id,remark) VALUES (:wp,:item,:remark)"
                ),
                {"wp": wp_id, "item": item_id, "remark": initial},
            )
        scoped = _engine(schema=schema)
        Session = async_sessionmaker(scoped, expire_on_commit=False)
        async with Session() as db:
            stamp = (
                await db.execute(
                    sa.text(
                        "SELECT updated_at FROM checklist_responses "
                        "WHERE wp_id=:wp AND item_id=:item"
                    ),
                    {"wp": wp_id, "item": item_id},
                )
            ).scalar_one()

        async def html_save() -> None:
            async with Session() as db, db.begin():
                item = SimpleNamespace(item_id=item_id, if_match=stamp.isoformat())
                await lock_and_check_versions(
                    db, wp_id, [item], require_if_match=True
                )
                await db.execute(
                    sa.text(
                        "UPDATE checklist_responses "
                        "SET remark=:remark, updated_at=clock_timestamp() "
                        "WHERE wp_id=:wp AND item_id=:item"
                    ),
                    {"remark": html_value, "wp": wp_id, "item": item_id},
                )
                html_updated.set()
                await release_html.wait()

        async def oo_mirror() -> None:
            await html_updated.wait()
            mirror_started.set()
            async with Session() as db, db.begin():
                await mirror_projection_into_store(
                    db,
                    adapter_id=adapter_id,
                    project_id=project_id,
                    wp_id=wp_id,
                    merged_projection={},
                    commit=False,
                )

        html_task = asyncio.create_task(html_save())
        await html_updated.wait()
        mirror_task = asyncio.create_task(oo_mirror())
        await mirror_started.wait()
        await asyncio.sleep(0.1)
        assert not mirror_task.done()
        assert not merge_called.is_set(), "mirror 在取得共享锁前读取了陈旧 base"

        release_html.set()
        await asyncio.wait_for(html_task, timeout=5)
        await asyncio.wait_for(mirror_task, timeout=5)
        assert observed_bases == [json.loads(html_value)]
        async with Session() as db:
            final_raw = (
                await db.execute(
                    sa.text(
                        "SELECT remark FROM checklist_responses "
                        "WHERE wp_id=:wp AND item_id=:item"
                    ),
                    {"wp": wp_id, "item": item_id},
                )
            ).scalar_one()
        final = json.loads(final_raw)
        assert final == [{
            "rowId": "r1",
            "html_value": "new",
            "html_only": "kept",
            "oo_value": "from-oo",
        }]
    finally:
        release_html.set()
        if scoped is not None:
            await scoped.dispose()
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin.dispose()
