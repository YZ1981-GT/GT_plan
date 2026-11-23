"""B1：合并附注章节锁（``_lock_note_section``）的真实 PG 并发 barrier。

spec: `platform-capacity-acceptance-and-heavy-defect-closure` B1。
上游 C2/C3 的 `test_note_section_lock_concurrency_pg.py` 覆盖的是**单体附注**
内核（`note_section_write_kernel`，namespace ``b"note"``）；合并附注写入走
`consol_note_formula_service._lock_note_section`（namespace ``0x636E736e``，
key = ``consol_note:{project}:{year}:{section}:{node}``），此前**零 barrier 覆盖**。

五例（与上游判据一一对应，锁实现不同 ⇒ 必须单独验证）：

1. 同 (section, node) 互斥：连接 A 持锁，连接 B 取同章节同节点锁阻塞，A 提交后 B 拿到。
2. 同章节不同节点不互斥：A 锁「五、1」根节点，B 锁「五、1」差额节点 → 立即成功
   （锁粒度是「章节+节点」，不能写成章节级）。
3. 不同章节并行：A 锁「五、1」，B 取「五、2」立即成功。
4. 事务级锁随 commit / rollback 自动释放（参数化两态）。
5. 并发 `fill_by_formula` 不丢更新：两个连接对同一章节各填一个不同公式格，
   串行后两格都在（fill_by_formula 读-改-写整节 rows，没有锁 + 无重叠读取
   一样会丢格 —— 这条是锁存在的业务意义）。

隔离方式与上游一致：提交型临时 schema（不写 public、不碰共享库），结束 DROP。
⚠️ 只在 `GT_BARRIER_PG=1` 且 DATABASE_URL 指向可销毁 PG 时跑，否则 skip。
"""

from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services.consol_note_formula_service import (
    _CONSOL_NOTE_LOCK_NAMESPACE,
    _lock_note_section,
    fill_by_formula,
)


def _barrier_pg_enabled() -> bool:
    return (
        os.environ.get("GT_BARRIER_PG", "").strip() in ("1", "true", "yes")
        and "postgresql" in os.environ.get("DATABASE_URL", "")
    )


pytestmark = [
    pytest.mark.pg_only,
    pytest.mark.skipif(
        not _barrier_pg_enabled(),
        reason="需要一次性 PG：设置 GT_BARRIER_PG=1 且 DATABASE_URL 指向可销毁库",
    ),
    pytest.mark.asyncio,
]

PROJECT = uuid.UUID("11111111-2222-3333-4444-555555555555")
YEAR = 2025
SECTION_A = "五、1"
SECTION_B = "五、2"
NODE_ROOT = "root"
NODE_ELIM = "elim-1"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in url:
        pytest.skip("需要 PostgreSQL（设置 DATABASE_URL）")
    return url


def _make_engine(search_path: str | None = None) -> AsyncEngine:
    from app.core.config import settings

    connect_args: dict = {"ssl": False} if settings.DB_DISABLE_SSL else {}
    if search_path is not None:
        connect_args["server_settings"] = {"search_path": search_path}
    return create_async_engine(_database_url(), poolclass=NullPool, connect_args=connect_args)


def _create_tables(conn) -> None:
    import app.models.audit_platform_models  # noqa: F401
    import app.models.core  # noqa: F401
    import app.models.consol_note_data_models  # noqa: F401
    import app.models.consol_note_mapping_models  # noqa: F401
    import app.models.formula_push_models  # noqa: F401
    import app.models.formula_setting_models  # noqa: F401
    import app.models.report_models  # noqa: F401
    import app.models.workpaper_models  # noqa: F401
    from app.models.base import Base

    Base.metadata.create_all(bind=conn)


@asynccontextmanager
async def consol_note_lock_schema() -> AsyncIterator[tuple[str, async_sessionmaker]]:
    name = os.environ.get("DATABASE_URL", "")
    if "audit_platform" in name:
        raise RuntimeError(
            "拒绝对共享库 audit_platform 运行：本用例需要可销毁环境"
            "（设置 DATABASE_URL 指向独立库）"
        )
    schema = f"consol_note_lock_{uuid.uuid4().hex[:12]}"
    admin = _make_engine()
    world: AsyncEngine | None = None
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", public')
            await conn.run_sync(_create_tables)
        world = _make_engine(search_path=f"{schema},public")
        factory = async_sessionmaker(world, class_=AsyncSession, expire_on_commit=False)
        yield schema, factory
    finally:
        if world is not None:
            await world.dispose()
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        async with admin.connect() as conn:
            exists = (
                await conn.execute(
                    sa.text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"),
                    {"s": schema},
                )
            ).first()
        assert exists is None, f"临时 schema {schema} 未删干净"
        await admin.dispose()


async def _seed_project(factory: async_sessionmaker) -> None:
    from app.models.base import ProjectStatus, ProjectType
    from app.models.core import Project

    async with factory() as db:
        existing = (
            await db.execute(sa.select(Project).where(Project.id == PROJECT))
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                Project(
                    id=PROJECT,
                    name="【测试】合并附注章节锁并发屏障",
                    client_name="并发屏障",
                    project_type=ProjectType.annual,
                    status=ProjectStatus.created,
                    audit_year=YEAR,
                    template_type="soe",
                    report_scope="consolidated",
                )
            )
            await db.commit()


# ---------------------------------------------------------------------------
# 判据 1：同 (section, node) 互斥
# ---------------------------------------------------------------------------


async def test_same_section_node_lock_blocks_second_connection():
    """A 持 (五、1, root) 锁，B 取同章节同节点锁必须阻塞；A 提交后 B 才拿到。"""
    async with consol_note_lock_schema() as (_schema, factory):
        await _seed_project(factory)

        a = factory()
        b = factory()
        try:
            assert await _lock_note_section(a, PROJECT, YEAR, SECTION_A, NODE_ROOT) is True

            b_task = asyncio.create_task(
                _lock_note_section(b, PROJECT, YEAR, SECTION_A, NODE_ROOT)
            )
            done, _pending = await asyncio.wait({b_task}, timeout=0.6)
            assert not done, "同章节同节点锁未阻塞第二个连接 —— advisory 锁没生效"

            await a.commit()
            await asyncio.wait_for(b_task, timeout=5.0)
            assert b_task.result() is True
        finally:
            await a.close()
            await b.close()


# ---------------------------------------------------------------------------
# 判据 2：同章节不同节点不互斥（锁粒度 = 章节 + 节点）
# ---------------------------------------------------------------------------


async def test_same_section_different_nodes_do_not_block():
    """A 锁 (五、1, root)，B 锁 (五、1, elim-1) 应立即成功。

    合并附注的锁 key 含 node_key：根节点汇总与差额节点计算可以并行
    （两者写的是不同 consol_note_data 行）。若这条红 ⇒ 锁粒度被改成了章节级。
    """
    async with consol_note_lock_schema() as (_schema, factory):
        await _seed_project(factory)

        a = factory()
        b = factory()
        try:
            assert await _lock_note_section(a, PROJECT, YEAR, SECTION_A, NODE_ROOT) is True
            got = await asyncio.wait_for(
                _lock_note_section(b, PROJECT, YEAR, SECTION_A, NODE_ELIM),
                timeout=2.0,
            )
            assert got is True, "同章节不同节点被阻塞 ⇒ 锁粒度写成了章节级"
        finally:
            await a.rollback()
            await b.rollback()
            await a.close()
            await b.close()


# ---------------------------------------------------------------------------
# 判据 3：不同章节并行
# ---------------------------------------------------------------------------


async def test_different_sections_do_not_block():
    """A 锁「五、1」，B 取「五、2」立即成功（跨章节天然并行）。"""
    async with consol_note_lock_schema() as (_schema, factory):
        await _seed_project(factory)

        a = factory()
        b = factory()
        try:
            assert await _lock_note_section(a, PROJECT, YEAR, SECTION_A, NODE_ROOT) is True
            got = await asyncio.wait_for(
                _lock_note_section(b, PROJECT, YEAR, SECTION_B, NODE_ROOT),
                timeout=2.0,
            )
            assert got is True, "不同章节被阻塞 ⇒ 锁粒度写成了项目级"
        finally:
            await a.rollback()
            await b.rollback()
            await a.close()
            await b.close()


# ---------------------------------------------------------------------------
# 判据 4：事务级锁随 commit / rollback 自动释放
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("release", ["commit", "rollback"])
async def test_lock_released_on_transaction_end(release: str):
    """commit 与 rollback 都必须释放 advisory xact 锁。"""
    async with consol_note_lock_schema() as (_schema, factory):
        await _seed_project(factory)

        a = factory()
        b = factory()
        try:
            assert await _lock_note_section(a, PROJECT, YEAR, SECTION_A, NODE_ROOT) is True

            b_task = asyncio.create_task(
                _lock_note_section(b, PROJECT, YEAR, SECTION_A, NODE_ROOT)
            )
            done, _pending = await asyncio.wait({b_task}, timeout=0.5)
            assert not done, "释放前 B 竟然拿到了锁"

            if release == "commit":
                await a.commit()
            else:
                await a.rollback()
            await asyncio.wait_for(b_task, timeout=5.0)
            assert b_task.result() is True
        finally:
            await a.close()
            await b.close()


# ---------------------------------------------------------------------------
# 判据 5：并发 fill_by_formula 不丢更新
# ---------------------------------------------------------------------------


async def test_concurrent_fill_by_formula_does_not_lose_cells():
    """两个连接对同一 (project, year, section, node) 各填一个不同列的公式格。

    ``fill_by_formula`` 是「读整节 rows → 改 → 写回」的读-改-写；没有章节锁时，
    两个并发 writer 各自从同一初态读入、各自写回，后提交者会抹掉先提交者的格
    （丢更新）。串行后两格必须都在 —— 这是章节锁存在的业务意义。

    直接写公式格不走真实公式种子（避免依赖模板内容）：构造两个
    ``_precomputed_cells``（row_index=模板行、col_index 各占一列）。
    """
    async with consol_note_lock_schema() as (_schema, factory):
        await _seed_project(factory)
        from app.models.consol_note_data_models import ConsolNoteData

        node_key = "fill-node"
        # 初始记录：1 行 3 列，第 1 列有值
        async with factory() as db:
            db.add(ConsolNoteData(
                project_id=PROJECT, year=YEAR, section_id=SECTION_A, node_key=node_key,
                data={"headers": ["项目", "列1", "列2"], "rows": [["合计", "100", ""]]},
            ))
            await db.commit()

        async def _fill(col: int, value: str) -> None:
            async with factory() as db:
                await fill_by_formula(
                    db, PROJECT, YEAR, SECTION_A,
                    node_key=node_key,
                    template_type="soe",
                    _precomputed_cells=[
                        {"row_index": 0, "col_index": col, "consolidated": value},
                    ],
                )
                await db.commit()

        await asyncio.gather(_fill(1, "200"), _fill(2, "300"))

        async with factory() as db:
            record = (
                await db.execute(
                    sa.select(ConsolNoteData).where(
                        ConsolNoteData.project_id == PROJECT,
                        ConsolNoteData.year == YEAR,
                        ConsolNoteData.section_id == SECTION_A,
                        ConsolNoteData.node_key == node_key,
                    )
                )
            ).scalar_one()
            rows = record.data["rows"]
            assert rows[0][1] == "200", f"列1 被并发写丢：{rows[0]}"
            assert rows[0][2] == "300", f"列2 被并发写丢：{rows[0]}"


# ---------------------------------------------------------------------------
# 锁命名空间与 key 形态自检（防与单体附注内核 / 其它域串锁）
# ---------------------------------------------------------------------------


def test_lock_namespace_is_distinct_from_standalone_note_kernel():
    """合并附注锁 namespace 必须与单体附注内核（note_section_write_kernel）不同。

    两把锁若共用 namespace 且 key 形态重叠会跨域误伤（合并附注的刷新阻塞
    单体附注的编辑，或反之）。合并附注 namespace = 0x636E736E（b"cnsn"）、
    内核 = 0x6E6F7465（b"note"），即便 key 形态也不同（前者带 node_key）。
    """
    from app.services.disclosure import note_section_write_kernel as kernel

    kernel_ns = kernel._ADVISORY_NAMESPACE
    assert kernel_ns == 0x6E6F7465, f"单体附注内核 namespace 漂移：{kernel_ns:#x}"
    assert _CONSOL_NOTE_LOCK_NAMESPACE != kernel_ns, (
        "合并附注与单体附注锁共用 namespace ⇒ 跨域误伤"
    )
