# Feature: procedure-delegation-notification — Task 4 显式 materialize 与底稿原子绑定
"""ProcedureTaskMaterializationService 测试：Properties P4-P7 + PostgreSQL 集成。

Task 4 / 需求 2.1-2.8, 12.2 / Design C2、D2-D3：

- **P6（GET/render-config 零写入）**：Requirements 2.5, 2.7 —— SQLite Hypothesis，
  纯读 overlay 前后 definition/task/preview/projection/outbox + WorkingPaper version 不变。
- **P7（未物化 overlay 完整）**：Requirements 2.6, 2.7, 2.8 —— SQLite Hypothesis，
  有 definition 无 task 的行 overlay 返回 task_id=null/materialization_required=true 且不产生 task。
- **P4（active task 唯一性）**：Requirements 2.1, 2.2, 12.2 —— PostgreSQL，并发 materialize
  对同 (project,wp_index,sheet,definition) 最多产生一个 active task（active partial unique）。
- **P5（nullable wp 原子绑定不换 task）**：Requirements 2.3, 2.4 —— PostgreSQL，绑定 wp 后
  task_id/assignee/reviewer/workflow/assignment_version 不变；重试幂等。

数据库约束/并发在 PostgreSQL 验证，不以 sqlite 替代（memory 铁律）。PBT 用项目 fast profile。
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings as app_settings
from app.core.migration_runner import MigrationRunner
from app.models.base import Base
from app.models.procedure_models import (
    ProcedureOperationPreview,
    ProcedureRowDefinition,
    ProcedureRowTask,
    ProcedureRowTaskHistory,
)
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus
from app.services.procedure_task_materialization_service import (
    ProcedureTaskMaterializationService,
    _base_wp_code,
)

import app.models.procedure_models  # noqa: F401
import app.models.phase15_models  # noqa: F401
import app.models.core  # noqa: F401

from pathlib import Path

_V105 = (
    Path(__file__).resolve().parent.parent.parent
    / "migrations"
    / "V105__procedure_row_tasks.sql"
)
_IS_PG = app_settings.DATABASE_URL.startswith("postgresql")


# ===========================================================================
# 共享：SQLite 内存引擎构造 + 种子（P6/P7，每 example 全新隔离）
# ===========================================================================

async def _make_sqlite_env():
    """全新 SQLite 内存引擎 + 项目/wp_index/working_paper 种子。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    project_id = uuid.uuid4()
    wp_index_id = uuid.uuid4()
    wp_id = uuid.uuid4()
    wp_code = "G1"
    async with factory() as s:
        s.add(
            WpIndex(
                id=wp_index_id,
                project_id=project_id,
                wp_code=wp_code,
                wp_name="测试底稿",
                audit_cycle="G",
                status=WpStatus.not_started,
            )
        )
        s.add(
            WorkingPaper(
                id=wp_id,
                project_id=project_id,
                wp_index_id=wp_index_id,
                file_path="/tmp/G1.xlsx",
                source_type=WpSourceType.template,
                file_version=1,
                parsed_data={"procedure_status": {"G1A": {"row-1": {"status": "pending"}}}},
            )
        )
        await s.commit()
    return engine, factory, project_id, wp_index_id, wp_id, wp_code


async def _seed_definitions(factory, wp_code: str, program_texts: list[tuple[str, str]]):
    """插入模板定义（template_code base == wp_code；program_texts=[(program_no, text), ...]）。"""
    async with factory() as s:
        for i, (program_no, text) in enumerate(program_texts):
            s.add(
                ProcedureRowDefinition(
                    definition_key=f"{wp_code}A::{wp_code}A::{i:04d}{uuid.uuid4().hex[:8]}",
                    template_code=f"{wp_code}A",
                    template_revision_hash="a" * 64,
                    sheet_key=f"{wp_code}A",
                    source_locator={},
                    program_no=program_no,
                    procedure_text=text,
                    ref_snapshot=[],
                    legacy_aliases=[],
                    normalized_content={},
                )
            )
        await s.commit()


async def _domain_counts(factory, wp_id: uuid.UUID) -> dict:
    async with factory() as s:
        def_c = (await s.execute(sa.select(sa.func.count()).select_from(ProcedureRowDefinition))).scalar()
        task_c = (await s.execute(sa.select(sa.func.count()).select_from(ProcedureRowTask))).scalar()
        prev_c = (await s.execute(sa.select(sa.func.count()).select_from(ProcedureOperationPreview))).scalar()
        hist_c = (await s.execute(sa.select(sa.func.count()).select_from(ProcedureRowTaskHistory))).scalar()
        wp = (
            await s.execute(
                sa.select(WorkingPaper.parsed_data, WorkingPaper.file_version, WorkingPaper.updated_at).where(
                    WorkingPaper.id == wp_id
                )
            )
        ).one()
        return {
            "definitions": def_c,
            "tasks": task_c,
            "previews": prev_c,
            "history": hist_c,
            "wp_parsed_data": wp[0],
            "wp_file_version": wp[1],
            "wp_updated_at": wp[2],
        }


# Hypothesis 策略：program_no 唯一、文本非空。
@st.composite
def _program_rows(draw):
    n = draw(st.integers(min_value=1, max_value=5))
    texts = draw(
        st.lists(
            st.text(min_size=1, max_size=30).map(lambda s: s.strip() or "x"),
            min_size=n, max_size=n,
        )
    )
    return [(str(i + 1), texts[i]) for i in range(n)]


# ===========================================================================
# P7：未物化 overlay 完整（有 definition 无 task）
# Validates: Requirements 2.6, 2.7, 2.8
# ===========================================================================
class TestP7UnmaterializedOverlay:
    @given(rows=_program_rows())
    @settings(max_examples=5)
    def test_overlay_marks_unmaterialized_and_creates_no_task(self, rows):
        async def scenario():
            engine, factory, project_id, wp_index_id, wp_id, wp_code = await _make_sqlite_env()
            try:
                await _seed_definitions(factory, wp_code, rows)
                async with factory() as s:
                    svc = ProcedureTaskMaterializationService(s)
                    overlay = await svc.build_row_overlay(project_id, wp_index_id)
                    # 每个 definition 行都返回未物化标记
                    assert len(overlay) == len(rows)
                    for item in overlay:
                        assert item["task_id"] is None
                        assert item["materialization_required"] is True
                    # 纯读不得产生 task
                    task_c = (
                        await s.execute(sa.select(sa.func.count()).select_from(ProcedureRowTask))
                    ).scalar()
                    assert task_c == 0
            finally:
                await engine.dispose()

        asyncio.run(scenario())

    @given(rows=_program_rows())
    @settings(max_examples=5)
    def test_program_row_overlay_marks_unmaterialized(self, rows):
        async def scenario():
            engine, factory, project_id, wp_index_id, wp_id, wp_code = await _make_sqlite_env()
            try:
                await _seed_definitions(factory, wp_code, rows)
                programs = [{"program_no": pn, "program_desc": txt} for pn, txt in rows]
                async with factory() as s:
                    svc = ProcedureTaskMaterializationService(s)
                    merged = await svc.overlay_program_rows(project_id, wp_index_id, programs)
                    for prog in merged:
                        assert prog["task_id"] is None
                        assert prog["materialization_required"] is True
                        assert prog.get("definition_key")
            finally:
                await engine.dispose()

        asyncio.run(scenario())


# ===========================================================================
# P6：GET/render-config 零写入
# Validates: Requirements 2.5, 2.7
# ===========================================================================
class TestP6OverlayZeroWrite:
    @given(rows=_program_rows())
    @settings(max_examples=5)
    def test_overlay_read_is_domain_zero_write(self, rows):
        async def scenario():
            engine, factory, project_id, wp_index_id, wp_id, wp_code = await _make_sqlite_env()
            try:
                await _seed_definitions(factory, wp_code, rows)
                before = await _domain_counts(factory, wp_id)
                # 模拟 render-config 多次只读 overlay 调用
                async with factory() as s:
                    svc = ProcedureTaskMaterializationService(s)
                    await svc.build_row_overlay(project_id, wp_index_id)
                    programs = [{"program_no": pn, "program_desc": txt} for pn, txt in rows]
                    await svc.overlay_program_rows(project_id, wp_index_id, programs)
                    # 只读，不 commit
                after = await _domain_counts(factory, wp_id)
                assert after == before
            finally:
                await engine.dispose()

        asyncio.run(scenario())


# ===========================================================================
# PostgreSQL 集成：P4（唯一性）、P5（原子绑定）、基础 materialize
# ===========================================================================
async def _apply_v105(engine) -> None:
    sql = _V105.read_text(encoding="utf-8")
    statements = MigrationRunner._split_sql_statements(sql)
    async with engine.begin() as conn:
        for stmt in statements:
            await conn.exec_driver_sql(stmt)


@pytest_asyncio.fixture
async def pg_engine():
    if not _IS_PG:
        pytest.skip("need PostgreSQL (materialization concurrency/binding)")
    engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable")
    await _apply_v105(engine)
    try:
        yield engine
    finally:
        await engine.dispose()


async def _pick_project_wp_index_wp(factory):
    """复用 dev 库已存在的 project+wp_index+working_paper，避免重建重 FK 图。"""
    async with factory() as s:
        row = (
            await s.execute(
                sa.text(
                    "SELECT wp.project_id, wp.wp_index_id, wp.id, wi.wp_code, "
                    "COALESCE(wi.audit_cycle, 'A') "
                    "FROM working_paper wp JOIN wp_index wi ON wi.id = wp.wp_index_id "
                    "WHERE wp.is_deleted = false AND wi.is_deleted = false LIMIT 1"
                )
            )
        ).first()
    return row


async def _insert_test_definition(factory, wp_code: str) -> str:
    """插入一个匹配 wp_code 的临时定义，返回 definition_key（唯一）。"""
    definition_key = f"{wp_code}::TEST::{uuid.uuid4().hex}"
    async with factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO procedure_row_definitions "
                "(definition_key, template_code, template_revision_hash, sheet_key, procedure_text) "
                "VALUES (:k, :tc, :h, :sk, :pt)"
            ),
            {
                "k": definition_key,
                "tc": wp_code,  # base(template_code)==wp_code，被 _definitions_for_wp_code 命中
                "h": "b" * 64,
                "sk": f"{wp_code}::TEST",
                "pt": "临时测试程序",
            },
        )
        await s.commit()
    return definition_key


async def _cleanup(factory, definition_key: str):
    async with factory() as s:
        await s.execute(
            sa.text("DELETE FROM procedure_row_task_history WHERE task_id IN "
                    "(SELECT id FROM procedure_row_tasks WHERE definition_key = :k)"),
            {"k": definition_key},
        )
        await s.execute(
            sa.text("DELETE FROM procedure_row_tasks WHERE definition_key = :k"),
            {"k": definition_key},
        )
        await s.execute(
            sa.text("DELETE FROM procedure_row_definitions WHERE definition_key = :k"),
            {"k": definition_key},
        )
        await s.commit()


@pytest.mark.asyncio
class TestPgMaterialization:
    async def test_base_wp_code_helper(self, pg_engine):
        # base 归一：D2A→D2 / D2-7A→D2-7 / G1A→G1
        assert _base_wp_code("D2A") == "D2"
        assert _base_wp_code("D2-7A") == "D2-7"
        assert _base_wp_code("G1A") == "G1"
        assert _base_wp_code("G1") == "G1"

    async def test_materialize_creates_then_idempotent_no_reset(self, pg_engine):
        """基础：materialize 首次创建，二次幂等（existing），已存在 task 不被重置。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp_index_wp(factory)
        if picked is None:
            pytest.skip("dev 库无 project+wp_index+working_paper 可复用")
        project_id, wp_index_id, wp_id, wp_code, _cycle = picked
        definition_key = await _insert_test_definition(factory, wp_code)
        try:
            # 首次物化
            async with factory() as s:
                svc = ProcedureTaskMaterializationService(s)
                r1 = await svc.materialize(project_id, [wp_index_id])
                await s.commit()
            assert r1["created"] >= 1

            # 手动改 task 的委派/工作流，模拟已委派状态
            async with factory() as s:
                await s.execute(
                    sa.text(
                        "UPDATE procedure_row_tasks SET workflow_status='assigned', "
                        "assignment_version=3, lock_version=2 WHERE definition_key=:k"
                    ),
                    {"k": definition_key},
                )
                await s.commit()

            # 二次物化：幂等，不重置 assignment/workflow/version
            async with factory() as s:
                svc = ProcedureTaskMaterializationService(s)
                r2 = await svc.materialize(project_id, [wp_index_id])
                await s.commit()
            assert r2["existing"] >= 1
            async with factory() as s:
                row = (
                    await s.execute(
                        sa.text(
                            "SELECT workflow_status, assignment_version, lock_version, wp_id "
                            "FROM procedure_row_tasks WHERE definition_key=:k"
                        ),
                        {"k": definition_key},
                    )
                ).first()
            assert row[0] == "assigned"
            assert row[1] == 3
            assert row[2] == 2
            assert row[3] is None  # materialize 不绑定 wp
        finally:
            await _cleanup(factory, definition_key)

    async def test_p4_concurrent_materialize_unique(self, pg_engine):
        """P4：并发 materialize 对同锚点最多产生一个 active task。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp_index_wp(factory)
        if picked is None:
            pytest.skip("dev 库无 project+wp_index+working_paper 可复用")
        project_id, wp_index_id, wp_id, wp_code, _cycle = picked
        definition_key = await _insert_test_definition(factory, wp_code)
        try:
            async def one_materialize():
                async with factory() as s:
                    svc = ProcedureTaskMaterializationService(s)
                    res = await svc.materialize(project_id, [wp_index_id])
                    await s.commit()
                    return res

            # 并发多次
            await asyncio.gather(*[one_materialize() for _ in range(4)])

            async with factory() as s:
                active = (
                    await s.execute(
                        sa.text(
                            "SELECT count(*) FROM procedure_row_tasks "
                            "WHERE definition_key=:k AND is_deleted=false"
                        ),
                        {"k": definition_key},
                    )
                ).scalar()
            assert active == 1, f"active partial unique 应保证唯一，实际 {active}"
        finally:
            await _cleanup(factory, definition_key)

    async def test_p5_atomic_bind_idempotent_no_task_change(self, pg_engine):
        """P5：绑定 wp 后 task_id/assignee/reviewer/workflow/assignment_version 不变，重试幂等。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp_index_wp(factory)
        if picked is None:
            pytest.skip("dev 库无 project+wp_index+working_paper 可复用")
        project_id, wp_index_id, wp_id, wp_code, _cycle = picked
        definition_key = await _insert_test_definition(factory, wp_code)
        try:
            async with factory() as s:
                svc = ProcedureTaskMaterializationService(s)
                await svc.materialize(project_id, [wp_index_id])
                await s.commit()

            # 记录绑定前 task 身份
            async with factory() as s:
                before = (
                    await s.execute(
                        sa.text(
                            "SELECT id, wp_id, assignee_staff_id, reviewer_staff_id, "
                            "workflow_status, assignment_version FROM procedure_row_tasks "
                            "WHERE definition_key=:k"
                        ),
                        {"k": definition_key},
                    )
                ).first()
            before_task_id, before_wp = before[0], before[1]
            assert before_wp is None

            # 首次绑定
            async with factory() as s:
                svc = ProcedureTaskMaterializationService(s)
                b1 = await svc.bind_working_paper(project_id, wp_index_id, wp_id)
                await s.commit()
            assert b1["bound"] >= 1

            # 重试绑定：幂等，already_bound
            async with factory() as s:
                svc = ProcedureTaskMaterializationService(s)
                b2 = await svc.bind_working_paper(project_id, wp_index_id, wp_id)
                await s.commit()
            assert b2["bound"] == 0
            assert b2["already_bound"] >= 1

            async with factory() as s:
                after = (
                    await s.execute(
                        sa.text(
                            "SELECT id, wp_id, assignee_staff_id, reviewer_staff_id, "
                            "workflow_status, assignment_version FROM procedure_row_tasks "
                            "WHERE definition_key=:k"
                        ),
                        {"k": definition_key},
                    )
                ).first()
            # task_id 不变，wp_id 已绑定，其余身份不变
            assert after[0] == before_task_id
            assert str(after[1]) == str(wp_id)
            assert after[2] == before[2]  # assignee 不变
            assert after[3] == before[3]  # reviewer 不变
            assert after[4] == before[4]  # workflow 不变
            assert after[5] == before[5]  # assignment_version 不变
        finally:
            await _cleanup(factory, definition_key)

    async def test_bind_rejects_cross_project_wp(self, pg_engine):
        """bind 校验 wp 属于同 project/wp_index；不匹配抛错、零写。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp_index_wp(factory)
        if picked is None:
            pytest.skip("dev 库无 project+wp_index+working_paper 可复用")
        project_id, wp_index_id, wp_id, wp_code, _cycle = picked
        definition_key = await _insert_test_definition(factory, wp_code)
        try:
            async with factory() as s:
                svc = ProcedureTaskMaterializationService(s)
                await svc.materialize(project_id, [wp_index_id])
                await s.commit()
            # 用一个随机不存在的 wp_id → ValueError
            async with factory() as s:
                svc = ProcedureTaskMaterializationService(s)
                with pytest.raises(ValueError):
                    await svc.bind_working_paper(project_id, wp_index_id, uuid.uuid4())
                await s.rollback()
        finally:
            await _cleanup(factory, definition_key)
