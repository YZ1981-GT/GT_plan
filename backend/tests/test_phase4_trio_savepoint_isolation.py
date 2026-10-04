"""Phase4 Task 6 — savepoint 隔离与事务边界（SQLite 真 ORM + 真 PG 临时 schema + 变异证明）。

spec: ``.kiro/specs/chain-closure-phase4-deliverable-center-trio``（需求 4.1, 4.2, 4.3, 4.5, 7.2）。

事务边界（design §6）：
  · 每个正式步骤的**业务写入**（版本、task 状态、章节状态、item=succeeded 投影）在
    ``db.begin_nested()`` 保存点内执行；
  · **失败留痕**（``export_job_attempts`` 的失败 attempt + item=failed）在保存点**之外**记录；
  · 步骤失败 ⇒ 保存点回滚撤销本步骤半成品业务写入，但失败 attempt 与 item 失败状态存活；
  · 已成功步骤的版本/item 在各自保存点 RELEASE 后属外层事务，不被后续步骤回滚波及。

本文件覆盖：
  P1（SQLite 真 ORM）第 2 步制造失败且**在失败前已 flush 一个半成品版本行** ⇒
      第 1 步版本存活、第 2 步半成品被回滚、第 2 步失败 attempt 存活、第 3 步 blocked。
  P2 失败 attempt 记录含异常类型/中文消息/诊断阶段（需求 4.3）。
  M1（变异）把 ``db.begin_nested`` 换成**不隔离**的空上下文 ⇒ 第 2 步半成品写入泄漏（RED）。
  M2（变异）同上空上下文下，断言失败留痕本应仍在（证明「去掉 savepoint 让业务写入泄漏」是
      唯一变化，attempt 留痕与是否 savepoint 无关 —— 它本就在保存点外）。
  PG1（真 PG16，无 PG 环境 skip）在真实 PG 的 ``AsyncSession`` 上以原生 SAVEPOINT 跑同一
      executor 流程，验证第 1 步版本存活 + 第 2 步半成品回滚 + 失败 attempt 存活。

Windows：``python`` 而非 ``python3``；无 ``&&``。
"""

from __future__ import annotations

import contextlib
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.core import Project, User
from app.models.phase13_models import (
    ExportJobAttempt,
    ExportJobItem,
    ExportJobStatus,
    WordExportTask,
    WordExportTaskVersion,
)
from app.services.full_deliverables_executor import (
    BLOCKED_BY_DEPENDENCY,
    FullDeliverablesExecutor,
)


# ===========================================================================
# 共用：把 executor 的三件套渲染步骤打桩。
#   · financial_report（第 1 步）成功，并落一个**真实版本行**（代表成功步骤的业务写入）。
#   · disclosure_notes（第 2 步）**先 flush 一个半成品版本行，再抛异常**
#     （代表「版本先写、随后校验/落盘失败」—— 需求 4.2 要求本步骤业务写入回滚）。
#   · audit_report（第 3 步）依赖前两项，第 2 步失败 ⇒ 被 blocked_by_dependency。
# ===========================================================================


async def _noop():
    return None


def _patch_executor_with_real_writes(
    executor: FullDeliverablesExecutor,
    task_id_step1: uuid.UUID,
    task_id_step2: uuid.UUID,
    user_id: uuid.UUID,
    *,
    leaked_version_ids: dict,
):
    """桩：第 1 步落真实成功版本；第 2 步落半成品版本后抛异常；第 3 步正常（会被阻断）。"""
    db = executor.db

    async def _step1_financial(project_id, year, user_id_):
        v = WordExportTaskVersion(
            id=uuid.uuid4(),
            word_export_task_id=task_id_step1,
            version_no=1,
            file_path="/storage/financial_v1.xlsx",
            created_by=user_id,
            created_via="generate",
        )
        db.add(v)
        await db.flush()
        leaked_version_ids["step1"] = v.id
        return task_id_step1

    async def _step2_notes_partial_then_fail(project_id, year, user_id_):
        # 半成品：版本行已 flush（代表 create_version 已先写），随后校验失败 → 抛异常。
        # savepoint 必须把这行回滚；无 savepoint 时这行会泄漏到外层事务。
        v = WordExportTaskVersion(
            id=uuid.uuid4(),
            word_export_task_id=task_id_step2,
            version_no=1,
            file_path="/storage/notes_partial.docx",
            created_by=user_id,
            created_via="generate",
        )
        db.add(v)
        await db.flush()
        leaked_version_ids["step2_partial"] = v.id
        raise ValueError("报表附注落盘失败：文件指纹校验未通过（桩）")

    async def _step3_report(project_id, year, user_id_, payload):
        return uuid.uuid4(), None, {"key_audit_matters": True}

    executor._run_financial_reports = _step1_financial  # type: ignore[assignment]
    executor._run_disclosure_notes = _step2_notes_partial_then_fail  # type: ignore[assignment]
    executor._run_report_body = _step3_report  # type: ignore[assignment]
    executor.precheck = lambda project_id, year: _noop()  # type: ignore[assignment]
    executor._build_snapshot_input = (  # type: ignore[assignment]
        lambda project_id, year, payload: _stub_snap(project_id, year)
    )


async def _stub_snap(project_id, year):
    return {"project_id": str(project_id), "year": year}


async def _items_by_step(db: AsyncSession, job_id) -> dict:
    rows = (
        await db.execute(sa.select(ExportJobItem).where(ExportJobItem.job_id == job_id))
    ).scalars().all()
    return {r.step_key: r for r in rows}


async def _version_exists(db: AsyncSession, version_id) -> bool:
    row = await db.get(WordExportTaskVersion, version_id)
    return row is not None


async def _seed_projects_tasks(db: AsyncSession):
    """建 user/project + 两个 WordExportTask（第 1、2 步版本行的 FK 父表）。"""
    user = User(
        id=uuid.uuid4(),
        username=f"t6_{uuid.uuid4().hex[:8]}",
        email=f"t6_{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="hashed",
        role="admin",
    )
    project = Project(
        id=uuid.uuid4(), name="三件套事务项目", client_name="测试公司", status="created"
    )
    db.add_all([user, project])
    await db.flush()
    t1 = WordExportTask(
        id=uuid.uuid4(), project_id=project.id, doc_type="financial_report",
        created_by=user.id,
    )
    t2 = WordExportTask(
        id=uuid.uuid4(), project_id=project.id, doc_type="disclosure_notes",
        created_by=user.id,
    )
    db.add_all([t1, t2])
    await db.flush()
    return user, project, t1, t2


# ===========================================================================
# A 组：SQLite 真 ORM
# ===========================================================================


@pytest_asyncio.fixture
async def sqlite_db():
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


class TestSavepointIsolationSqlite:
    """SQLite（aiosqlite 支持 SAVEPOINT）真 ORM 驱动 executor，验证事务边界。"""

    @pytest.mark.asyncio
    async def test_step2_partial_rolled_back_step1_survives_failure_logged(
        self, sqlite_db
    ):
        user, project, t1, t2 = await _seed_projects_tasks(sqlite_db)
        executor = FullDeliverablesExecutor(sqlite_db)
        leaked: dict = {}
        _patch_executor_with_real_writes(
            executor, t1.id, t2.id, user.id, leaked_version_ids=leaked
        )

        result = await executor.run(
            project_id=project.id, user_id=user.id, payload={"year": 2024}
        )

        items = await _items_by_step(sqlite_db, result.job_id)

        # 第 1 步成功版本存活（成功步骤的业务写入在其保存点 RELEASE 后属外层事务）。
        assert await _version_exists(sqlite_db, leaked["step1"]) is True, (
            "第 1 步成功版本不应被第 2 步失败回滚（需求 4.2）"
        )
        assert items["financial_report"].status == ExportJobStatus.succeeded.value

        # 第 2 步半成品版本被 savepoint 回滚 ⇒ 不残留。
        assert await _version_exists(sqlite_db, leaked["step2_partial"]) is False, (
            "第 2 步失败前已 flush 的半成品版本必须随保存点回滚（需求 4.2）"
        )
        # 第 2 步 item 标 failed（失败留痕，在保存点外写）。
        assert items["disclosure_notes"].status == ExportJobStatus.failed.value

        # 第 3 步依赖阻断。
        assert items["audit_report"].status == BLOCKED_BY_DEPENDENCY

        # 失败 attempt 存活（append-only；在保存点外记录）。
        attempts = (
            await sqlite_db.execute(
                sa.select(ExportJobAttempt).where(
                    ExportJobAttempt.item_id == items["disclosure_notes"].id
                )
            )
        ).scalars().all()
        failed = [a for a in attempts if a.status == ExportJobStatus.failed.value]
        assert len(failed) == 1, (
            "第 2 步失败 attempt 必须存活于保存点之外（需求 4.2/4.3）"
        )

        # 聚合：只统计正式三项，仅 financial_report 成功。
        assert result.trio_succeeded == 1
        assert result.trio_total == 3

    @pytest.mark.asyncio
    async def test_failed_attempt_records_error_type_message_and_stage(
        self, sqlite_db
    ):
        """需求 4.3：失败 attempt 保存原始异常类型、中文消息、诊断阶段。"""
        user, project, t1, t2 = await _seed_projects_tasks(sqlite_db)
        executor = FullDeliverablesExecutor(sqlite_db)
        leaked: dict = {}
        _patch_executor_with_real_writes(
            executor, t1.id, t2.id, user.id, leaked_version_ids=leaked
        )

        result = await executor.run(
            project_id=project.id, user_id=user.id, payload={"year": 2024}
        )
        items = await _items_by_step(sqlite_db, result.job_id)
        attempt = (
            await sqlite_db.execute(
                sa.select(ExportJobAttempt).where(
                    ExportJobAttempt.item_id == items["disclosure_notes"].id,
                    ExportJobAttempt.status == ExportJobStatus.failed.value,
                )
            )
        ).scalar_one()

        assert attempt.error_type == "ValueError"
        assert "附注" in (attempt.error_message or "") or "校验" in (
            attempt.error_message or ""
        )
        assert isinstance(attempt.diagnostic_detail, dict)
        assert attempt.diagnostic_detail.get("step") == "disclosure_notes"
        assert attempt.attempt_no == 1
        assert attempt.finished_at is not None

    @pytest.mark.asyncio
    async def test_mutation_remove_savepoint_leaks_partial_write(self, sqlite_db):
        """M1：把 ``begin_nested`` 换成不隔离的空上下文 ⇒ 第 2 步半成品泄漏（证明判据非恒绿）。

        这正是「去掉 savepoint 必须红」：若生产代码不用保存点隔离业务写入，
        第 2 步失败前 flush 的半成品版本行会留在外层事务 ⇒ 下方断言（存活=False）被打破。
        """
        user, project, t1, t2 = await _seed_projects_tasks(sqlite_db)
        executor = FullDeliverablesExecutor(sqlite_db)
        leaked: dict = {}
        _patch_executor_with_real_writes(
            executor, t1.id, t2.id, user.id, leaked_version_ids=leaked
        )

        # 变异：begin_nested → 不开保存点的空上下文（业务写入不再隔离回滚）。
        @contextlib.asynccontextmanager
        async def _no_savepoint():
            yield

        executor.db.begin_nested = _no_savepoint  # type: ignore[assignment]

        result = await executor.run(
            project_id=project.id, user_id=user.id, payload={"year": 2024}
        )
        items = await _items_by_step(sqlite_db, result.job_id)

        # 变异下：第 2 步半成品版本**未被回滚** ⇒ 泄漏存活。
        assert await _version_exists(sqlite_db, leaked["step2_partial"]) is True, (
            "去掉保存点后，第 2 步半成品应泄漏到外层事务（变异有效，证明保存点判据非恒绿）"
        )
        # 失败留痕本就在保存点外，变异不影响其存活（证明两条写入分属不同边界）。
        assert items["disclosure_notes"].status == ExportJobStatus.failed.value
        attempts = (
            await sqlite_db.execute(
                sa.select(ExportJobAttempt).where(
                    ExportJobAttempt.item_id == items["disclosure_notes"].id,
                    ExportJobAttempt.status == ExportJobStatus.failed.value,
                )
            )
        ).scalars().all()
        assert len(attempts) == 1, (
            "失败 attempt 在保存点外记录，不随保存点存废而变（需求 4.2 边界分离）"
        )


# ===========================================================================
# B 组：真 PG16（无 PG 环境 skip）——原生 SAVEPOINT 行为
# ===========================================================================


def _pg_available() -> bool:
    from app.core.config import settings

    return settings.DATABASE_URL.startswith("postgresql")


def _base_url() -> str:
    from app.core.config import settings

    head, _db = settings.DATABASE_URL.rsplit("/", 1)
    return head


def _connect_args() -> dict:
    from app.core.config import settings

    return {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}


# executor run() 在本测试里（precheck / _build_snapshot_input / 三个渲染步骤已打桩）
# 实际只触碰这几张表。用裸 DDL 建它们（只保留 ORM 插入会写的列），**去掉 FK 约束**
# 以避免 ``Project``→``accounting_standards``、``knowledge_index``→``vector`` 等无关闭包
# （本机 PG 未装 pgvector，全量 create_all 会因 ``type "vector"`` 失败）。
_PG_PREREQ_SQL = """
CREATE TABLE users (
    id uuid PRIMARY KEY,
    username varchar(255) NOT NULL,
    email varchar(255) NOT NULL,
    hashed_password varchar(255) NOT NULL,
    role varchar(50) NOT NULL DEFAULT 'admin',
    is_active boolean NOT NULL DEFAULT true,
    is_deleted boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE projects (
    id uuid PRIMARY KEY,
    name varchar(255) NOT NULL,
    client_name varchar(255) NOT NULL,
    status varchar(30) NOT NULL DEFAULT 'created',
    version integer NOT NULL DEFAULT 1,
    consol_level integer NOT NULL DEFAULT 0,
    consol_lock boolean NOT NULL DEFAULT false,
    is_large_soe boolean NOT NULL DEFAULT false,
    scenario varchar(20) NOT NULL DEFAULT 'normal',
    has_foreign_currency boolean NOT NULL DEFAULT false,
    is_deleted boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE word_export_task (
    id uuid PRIMARY KEY,
    project_id uuid NOT NULL,
    doc_type varchar(50) NOT NULL,
    status varchar(30) NOT NULL DEFAULT 'draft',
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE word_export_task_versions (
    id uuid PRIMARY KEY,
    word_export_task_id uuid NOT NULL,
    version_no int NOT NULL,
    file_path text,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    html_path text,
    file_size bigint,
    file_hash varchar(64),
    hash_chain_entry_id uuid,
    source_snapshot_refs jsonb,
    selected_sections jsonb,
    created_via varchar(20) DEFAULT 'generate',
    edited_by uuid,
    edited_at timestamptz,
    drift_report jsonb,
    file_sha256 varchar(64),
    snapshot_id varchar(64)
);
CREATE TABLE export_jobs_v2 (
    id uuid PRIMARY KEY,
    project_id uuid NOT NULL,
    job_type varchar(30) NOT NULL,
    status varchar(30) NOT NULL DEFAULT 'queued',
    payload jsonb,
    progress_total int NOT NULL DEFAULT 0,
    progress_done int NOT NULL DEFAULT 0,
    failed_count int NOT NULL DEFAULT 0,
    initiated_by uuid,
    snapshot_id varchar(64),
    trio_total int DEFAULT 3,
    trio_succeeded int DEFAULT 0,
    readiness jsonb,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE export_job_items_v2 (
    id uuid PRIMARY KEY,
    job_id uuid NOT NULL,
    word_export_task_id uuid,
    status varchar(30) NOT NULL DEFAULT 'queued',
    error_message text,
    finished_at timestamptz,
    step_key varchar(50),
    sequence int,
    snapshot_id varchar(64),
    version_id uuid,
    file_path text,
    file_size bigint,
    file_sha256 varchar(64),
    attempt_count int NOT NULL DEFAULT 0,
    last_attempt_id uuid
);
CREATE TABLE export_job_attempts (
    id uuid PRIMARY KEY,
    job_id uuid NOT NULL,
    item_id uuid NOT NULL,
    attempt_no int NOT NULL,
    status varchar(30) NOT NULL DEFAULT 'running',
    trigger varchar(30),
    snapshot_id varchar(64),
    error_type varchar(120),
    error_message text,
    diagnostic_detail jsonb,
    file_path text,
    file_size bigint,
    file_sha256 varchar(64),
    version_id uuid,
    created_by uuid,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    CONSTRAINT uq_export_job_attempt_item_no UNIQUE (item_id, attempt_no)
);
"""


@contextlib.asynccontextmanager
async def _pg_session():
    """在真 PG16 上建一次性库 + executor 实际触碰的表（裸 DDL），产出真实 AsyncSession。

    用裸 DDL 而非 ``Base.metadata.create_all``：完整 metadata 的 FK 闭包牵连
    ``accounting_standards`` 等表，且 ``knowledge_index`` 依赖未安装的 ``vector`` 扩展，
    全量建表在本机 PG 必失败。executor 在本测试里只写这 7 张表。
    """
    from sqlalchemy.pool import NullPool

    head = _base_url()
    ca = _connect_args()
    admin_url = head + "/postgres"
    tmp_db = f"phase4_t6_{uuid.uuid4().hex[:12]}"

    admin = create_async_engine(
        admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT", connect_args=ca
    )
    async with admin.connect() as c:
        await c.exec_driver_sql(f'CREATE DATABASE "{tmp_db}"')
    await admin.dispose()

    url = head + "/" + tmp_db
    eng = create_async_engine(url, poolclass=NullPool, connect_args=ca)
    try:
        async with eng.begin() as conn:
            for stmt in _PG_PREREQ_SQL.strip().split(";"):
                if stmt.strip():
                    await conn.exec_driver_sql(stmt)
        async_session = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            yield session
    finally:
        await eng.dispose()
        admin = create_async_engine(
            admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT", connect_args=ca
        )
        async with admin.connect() as c:
            await c.exec_driver_sql(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname='{tmp_db}' AND pid<>pg_backend_pid()"
            )
            await c.exec_driver_sql(f'DROP DATABASE IF EXISTS "{tmp_db}"')
        await admin.dispose()


async def _seed_pg_raw(db: AsyncSession):
    """真 PG 临时库用裸 SQL 播种 user/project/两个 task（避开 ORM 全列闭包）。

    executor 在本测试里只对 job/item/attempt/version 走 ORM；user/project/task 仅作为
    FK 载体，裸 SQL 写入即可（这些表在本测试里不被 ORM 查询/写入）。
    """
    uid = uuid.uuid4()
    pid = uuid.uuid4()
    t1 = uuid.uuid4()
    t2 = uuid.uuid4()
    await db.execute(
        sa.text(
            "INSERT INTO users (id, username, email, hashed_password, role) "
            "VALUES (:id, :u, :e, 'hashed', 'admin')"
        ),
        {"id": uid, "u": f"t6_{uid.hex[:8]}", "e": f"t6_{uid.hex[:8]}@test.com"},
    )
    await db.execute(
        sa.text(
            "INSERT INTO projects (id, name, client_name, status) "
            "VALUES (:id, '三件套事务项目', '测试公司', 'created')"
        ),
        {"id": pid},
    )
    for tid, dt in ((t1, "financial_report"), (t2, "disclosure_notes")):
        await db.execute(
            sa.text(
                "INSERT INTO word_export_task (id, project_id, doc_type, created_by) "
                "VALUES (:id, :pid, :dt, :cb)"
            ),
            {"id": tid, "pid": pid, "dt": dt, "cb": uid},
        )
    await db.flush()
    return uid, pid, t1, t2


@pytest.mark.asyncio
async def test_pg_native_savepoint_isolates_step2_and_keeps_failure_trace():
    """PG1：真 PG16 原生 SAVEPOINT 下跑 executor —— 第 1 步版本存活、第 2 步半成品回滚、失败 attempt 存活。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")

    async with _pg_session() as db:
        user_id, project_id_, t1_id, t2_id = await _seed_pg_raw(db)
        executor = FullDeliverablesExecutor(db)
        leaked: dict = {}
        _patch_executor_with_real_writes(
            executor, t1_id, t2_id, user_id, leaked_version_ids=leaked
        )

        result = await executor.run(
            project_id=project_id_, user_id=user_id, payload={"year": 2024}
        )
        # 在真 PG 上统一 commit（router 边界），再重新查证痕迹落库。
        await db.commit()

        items = await _items_by_step(db, result.job_id)
        assert items["financial_report"].status == ExportJobStatus.succeeded.value
        assert items["disclosure_notes"].status == ExportJobStatus.failed.value
        assert items["audit_report"].status == BLOCKED_BY_DEPENDENCY

        assert await _version_exists(db, leaked["step1"]) is True, (
            "真 PG：第 1 步成功版本应存活"
        )
        assert await _version_exists(db, leaked["step2_partial"]) is False, (
            "真 PG：第 2 步半成品版本应被 SAVEPOINT ROLLBACK TO 回滚"
        )

        attempts = (
            await db.execute(
                sa.select(ExportJobAttempt).where(
                    ExportJobAttempt.item_id == items["disclosure_notes"].id,
                    ExportJobAttempt.status == ExportJobStatus.failed.value,
                )
            )
        ).scalars().all()
        assert len(attempts) == 1, "真 PG：失败 attempt 必须在保存点外存活并随外层 commit 落库"
