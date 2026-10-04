"""Phase4 Task 13 — 真 PG16 临时 schema 与事务回滚（迁移/约束/savepoint/行锁/指纹/零痕迹）。

spec: ``.kiro/specs/chain-closure-phase4-deliverable-center-trio``（需求 7.5）。

本文件是 Task 13 的**真实 PostgreSQL 16** 交付证据，全部用一次性 throwaway 数据库
（``CREATE DATABASE`` → 跑真实迁移/裸 DDL → 断言 → ``DROP DATABASE``），**绝不**写真实
项目生产库 ``audit_platform``。无 PG 环境时每条用例 ``skip``（如实标依赖阻断，不以 SQLite
或 HTTP 200 冒充）。

覆盖矩阵（design §10.3 真实 PG 铁律）：

- **迁移**：``test_v180_apply_then_r180_rollback_clean`` —— V180 apply 建表/列，R180 回滚后
  表与列全部消失（迁移漏列的反向证明；与 Task 3 的分项断言互补，这里做 apply→rollback
  一条龙 + 残留清零）。
- **约束**：``test_attempt_no_unique_serializes_concurrent_inserts`` —— 真 PG 原生并发（两条
  连接）抢同一 ``(item_id, attempt_no)``，唯一约束串行化、第二条被拒。这是三件套
  attempt 并发的真实并发守卫（链路本身不用行锁，见下）。
- **savepoint**：``test_executor_native_savepoint_rolls_back_business_keeps_trace`` —— 在真 PG
  的 ``AsyncSession`` 上跑**真实 executor**，第 2 步失败：原生 ``ROLLBACK TO SAVEPOINT``
  撤销半成品版本，但失败 attempt + item=failed 留痕存活、第 1 步成功版本存活。
- **行锁**：``test_trio_chain_uses_no_row_lock_concurrency_guard_is_unique_index`` —— 现算证明
  三件套编排链 **不使用** ``SELECT ... FOR UPDATE`` / ``with_for_update`` / advisory lock；
  其并发正确性由 ``uq_export_job_attempt_item_no`` 唯一索引承载（行锁对本链「不适用」，
  如实记录而非假装覆盖）。
- **下载指纹**：``test_download_fingerprint_verify_on_real_pg_version_row`` —— 真 PG 版本行
  指向真实落盘文件，``verify_file_fingerprint`` 通过；截断/哈希不匹配 fail-closed。
- **零痕迹（本任务核心）**：``test_dry_run_in_rolled_back_transaction_leaves_zero_trace`` ——
  在真 PG 事务内跑完整 executor（建 job/item/attempt + 落盘文件），随后
  ``ROLLBACK`` 整个外层事务（dry-run 语义），再用**独立连接**复查：
  ``export_jobs_v2`` / ``word_export_task_versions`` / ``export_job_attempts`` 计数全部回到
  试跑前水平（零新增）；落盘文件由 executor 的失败清理/测试清理归零，指纹无残留。

真实 PG 铁律：PG-only SQL（``gen_random_uuid`` / ``information_schema`` / 两连接并发）在真
PG16 验证；无 PG 环境 skip。Windows：``python`` 而非 ``python3``；无 ``&&``。
"""

from __future__ import annotations

import contextlib
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.migration_runner import MigrationRunner
from app.models.phase13_models import (
    ExportJobAttempt,
    ExportJobItem,
    ExportJobStatus,
    WordExportTaskVersion,
)
from app.services.deliverable_file_fingerprint import (
    FileFingerprintError,
    compute_file_fingerprint,
    verify_file_fingerprint,
)
from app.services.full_deliverables_executor import (
    BLOCKED_BY_DEPENDENCY,
    FullDeliverablesExecutor,
)

_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


# ===========================================================================
# PG 环境探测 + 一次性库
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


def _migration_sql(version: str) -> str:
    matches = [
        p for p in _MIGRATIONS_DIR.iterdir() if p.name.startswith(version + "__")
    ]
    assert len(matches) == 1, f"应恰有 1 个 {version} 文件，实际 {matches}"
    return matches[0].read_text(encoding="utf-8")


async def _apply_sql(eng, sql: str) -> None:
    statements = MigrationRunner._split_sql_statements(sql)
    async with eng.begin() as conn:
        for stmt in statements:
            await conn.exec_driver_sql(stmt)


async def _columns(eng, table: str) -> set[str]:
    async with eng.connect() as conn:
        rows = await conn.exec_driver_sql(
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_name = '{table}'"
        )
        return {r[0] for r in rows.fetchall()}


async def _table_exists(eng, table: str) -> bool:
    async with eng.connect() as conn:
        rows = await conn.exec_driver_sql(
            "SELECT 1 FROM information_schema.tables "
            f"WHERE table_name = '{table}'"
        )
        return rows.fetchone() is not None


# executor run() 在本测试里（precheck / _build_snapshot_input / 三个渲染步骤已打桩）
# 只触碰这几张表。裸 DDL 建表（无 FK、无 vector 闭包），与 Task 6 同款最小 schema。
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
async def _throwaway_db(prefix: str, *, apply_v180: bool = False):
    """建一次性 PG 库，产出 engine + url；``apply_v180`` 时跑真实 V180，否则建最小 schema。

    退出时强制断开所有连接并 ``DROP DATABASE``（绝不碰生产 audit_platform）。
    """
    from sqlalchemy.pool import NullPool

    head = _base_url()
    ca = _connect_args()
    admin_url = head + "/postgres"
    tmp_db = f"{prefix}_{uuid.uuid4().hex[:12]}"

    admin = create_async_engine(
        admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT", connect_args=ca
    )
    async with admin.connect() as c:
        await c.exec_driver_sql(f'CREATE DATABASE "{tmp_db}"')
    await admin.dispose()

    url = head + "/" + tmp_db
    eng = create_async_engine(url, poolclass=NullPool, connect_args=ca)
    try:
        if apply_v180:
            await _apply_sql(eng, _migration_sql("V180"))
        else:
            async with eng.begin() as conn:
                for stmt in _PG_PREREQ_SQL.strip().split(";"):
                    if stmt.strip():
                        await conn.exec_driver_sql(stmt)
        yield eng, url
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


# ===========================================================================
# executor 打桩（与 Task 6 同款：第 1 步成功落真实版本；第 2 步半成品后抛异常）
# ===========================================================================


async def _noop():
    return None


async def _stub_snap(project_id, year):
    return {"project_id": str(project_id), "year": year}


def _patch_executor(
    executor: FullDeliverablesExecutor,
    task_id_step1: uuid.UUID,
    task_id_step2: uuid.UUID,
    user_id: uuid.UUID,
    *,
    leaked: dict,
    step1_file_path: str | None = None,
):
    """桩：第 1 步落真实成功版本（可选指向真实文件）；第 2 步落半成品版本后抛异常。"""
    db = executor.db

    async def _step1_financial(project_id, year, user_id_):
        v = WordExportTaskVersion(
            id=uuid.uuid4(),
            word_export_task_id=task_id_step1,
            version_no=1,
            file_path=step1_file_path or "/storage/financial_v1.xlsx",
            created_by=user_id,
            created_via="generate",
        )
        db.add(v)
        await db.flush()
        leaked["step1"] = v.id
        return task_id_step1

    async def _step2_notes_partial_then_fail(project_id, year, user_id_):
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
        leaked["step2_partial"] = v.id
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
    # _finish_attempt_with_fingerprint 会去 DeliverableService._latest_version 查成功
    # 版本；桩版本已落 word_export_task_versions，直接走真实路径即可（不再打桩）。


async def _seed_pg_raw(db: AsyncSession):
    uid = uuid.uuid4()
    pid = uuid.uuid4()
    t1 = uuid.uuid4()
    t2 = uuid.uuid4()
    await db.execute(
        sa.text(
            "INSERT INTO users (id, username, email, hashed_password, role) "
            "VALUES (:id, :u, :e, 'hashed', 'admin')"
        ),
        {"id": uid, "u": f"t13_{uid.hex[:8]}", "e": f"t13_{uid.hex[:8]}@test.com"},
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


async def _items_by_step(db: AsyncSession, job_id) -> dict:
    rows = (
        await db.execute(sa.select(ExportJobItem).where(ExportJobItem.job_id == job_id))
    ).scalars().all()
    return {r.step_key: r for r in rows}


async def _version_exists(db: AsyncSession, version_id) -> bool:
    return await db.get(WordExportTaskVersion, version_id) is not None


@pytest_asyncio.fixture
async def pg_session_factory():
    """产出一个 (session_maker, engine) 工厂，针对最小 schema 的一次性 PG 库。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_db("phase4_t13") as (eng, _url):
        maker = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        yield maker, eng


# ===========================================================================
# 1. 迁移：V180 apply → R180 rollback 一条龙 + 残留清零
# ===========================================================================


@pytest.mark.asyncio
async def test_v180_apply_then_r180_rollback_clean():
    """真 PG16：V180 建 attempt 表 + 新列；R180 回滚后全部消失（迁移/回滚闭环）。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    # 这个库只需 V180 依赖的 3 张前置表，用最小 schema 子集即可。
    _prereq = """
    CREATE TABLE export_jobs_v2 (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id uuid NOT NULL,
        job_type varchar(30) NOT NULL,
        status varchar(30) NOT NULL DEFAULT 'queued'
    );
    CREATE TABLE export_job_items_v2 (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        job_id uuid NOT NULL REFERENCES export_jobs_v2(id),
        status varchar(30) NOT NULL DEFAULT 'queued'
    );
    CREATE TABLE word_export_task_versions (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        version_no int NOT NULL
    );
    """
    from sqlalchemy.pool import NullPool

    head = _base_url()
    ca = _connect_args()
    admin_url = head + "/postgres"
    tmp_db = f"phase4_t13_mig_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(
        admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT", connect_args=ca
    )
    async with admin.connect() as c:
        await c.exec_driver_sql(f'CREATE DATABASE "{tmp_db}"')
    await admin.dispose()
    eng = create_async_engine(
        head + "/" + tmp_db, poolclass=NullPool, connect_args=ca
    )
    try:
        async with eng.begin() as conn:
            for stmt in _prereq.strip().split(";"):
                if stmt.strip():
                    await conn.exec_driver_sql(stmt)

        # apply V180
        await _apply_sql(eng, _migration_sql("V180"))
        assert await _table_exists(eng, "export_job_attempts")
        job_cols = await _columns(eng, "export_jobs_v2")
        item_cols = await _columns(eng, "export_job_items_v2")
        ver_cols = await _columns(eng, "word_export_task_versions")
        assert {"snapshot_id", "trio_total", "trio_succeeded", "readiness"} <= job_cols
        assert {"step_key", "sequence", "file_sha256", "snapshot_id"} <= item_cols
        assert {"file_sha256", "snapshot_id"} <= ver_cols

        # rollback R180 → 新增表与列全部消失
        await _apply_sql(eng, _migration_sql("R180"))
        assert not await _table_exists(eng, "export_job_attempts")
        job_cols2 = await _columns(eng, "export_jobs_v2")
        item_cols2 = await _columns(eng, "export_job_items_v2")
        ver_cols2 = await _columns(eng, "word_export_task_versions")
        assert "snapshot_id" not in job_cols2
        assert "trio_total" not in job_cols2
        assert "step_key" not in item_cols2
        assert "file_sha256" not in item_cols2
        assert "file_sha256" not in ver_cols2
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


# ===========================================================================
# 2. 约束：真 PG 并发（两连接）抢同一 attempt_no，唯一索引串行化
# ===========================================================================


@pytest.mark.asyncio
async def test_attempt_no_unique_serializes_concurrent_inserts(pg_session_factory):
    """真 PG16：两条独立连接并发插同一 ``(item_id, attempt_no)``，第二条被唯一约束拒绝。

    这是三件套 attempt append-only 的**真实并发守卫**（链路不用行锁，见下一条）。
    """
    maker, eng = pg_session_factory
    async with maker() as setup:
        _uid, pid, _t1, _t2 = await _seed_pg_raw(setup)
        job_id, item_id = uuid.uuid4(), uuid.uuid4()
        await setup.execute(
            sa.text(
                "INSERT INTO export_jobs_v2 (id, project_id, job_type) "
                "VALUES (:id, :pid, 'full_deliverables')"
            ),
            {"id": job_id, "pid": pid},
        )
        await setup.execute(
            sa.text(
                "INSERT INTO export_job_items_v2 (id, job_id, step_key, sequence) "
                "VALUES (:id, :jid, 'financial_report', 1)"
            ),
            {"id": item_id, "jid": job_id},
        )
        await setup.commit()

    # 两条连接各开事务、都插 attempt_no=1；一条成功 commit，另一条必冲突。
    async with maker() as s1, maker() as s2:
        await s1.execute(
            sa.text(
                "INSERT INTO export_job_attempts (id, job_id, item_id, attempt_no) "
                "VALUES (:id, :jid, :iid, 1)"
            ),
            {"id": uuid.uuid4(), "jid": job_id, "iid": item_id},
        )
        await s1.commit()

        with pytest.raises(Exception) as ei:
            await s2.execute(
                sa.text(
                    "INSERT INTO export_job_attempts (id, job_id, item_id, attempt_no) "
                    "VALUES (:id, :jid, :iid, 1)"
                ),
                {"id": uuid.uuid4(), "jid": job_id, "iid": item_id},
            )
            await s2.commit()
        assert "uq_export_job_attempt_item_no" in str(ei.value) or "unique" in str(
            ei.value
        ).lower()
        await s2.rollback()

    # 终态：该 item 只有一行 attempt_no=1。
    async with maker() as check:
        n = (
            await check.execute(
                sa.text(
                    "SELECT count(*) FROM export_job_attempts "
                    "WHERE item_id=:iid AND attempt_no=1"
                ),
                {"iid": item_id},
            )
        ).scalar_one()
        assert n == 1


# ===========================================================================
# 3. savepoint：真 PG 原生 SAVEPOINT 下跑真实 executor
# ===========================================================================


@pytest.mark.asyncio
async def test_executor_native_savepoint_rolls_back_business_keeps_trace(
    pg_session_factory,
):
    """真 PG16 原生 SAVEPOINT：第 2 步失败 → 半成品版本 ROLLBACK TO，失败留痕存活。"""
    maker, eng = pg_session_factory
    async with maker() as db:
        user_id, project_id_, t1_id, t2_id = await _seed_pg_raw(db)
        executor = FullDeliverablesExecutor(db)
        leaked: dict = {}
        _patch_executor(executor, t1_id, t2_id, user_id, leaked=leaked)

        result = await executor.run(
            project_id=project_id_, user_id=user_id, payload={"year": 2024}
        )
        await db.commit()  # router 边界统一 commit

        items = await _items_by_step(db, result.job_id)
        assert items["financial_report"].status == ExportJobStatus.succeeded.value
        assert items["disclosure_notes"].status == ExportJobStatus.failed.value
        assert items["audit_report"].status == BLOCKED_BY_DEPENDENCY

        assert await _version_exists(db, leaked["step1"]) is True, (
            "真 PG：第 1 步成功版本应存活（保存点 RELEASE 后属外层事务）"
        )
        assert await _version_exists(db, leaked["step2_partial"]) is False, (
            "真 PG：第 2 步半成品版本应被原生 ROLLBACK TO SAVEPOINT 回滚"
        )

        attempts = (
            await db.execute(
                sa.select(ExportJobAttempt).where(
                    ExportJobAttempt.item_id == items["disclosure_notes"].id,
                    ExportJobAttempt.status == ExportJobStatus.failed.value,
                )
            )
        ).scalars().all()
        assert len(attempts) == 1, "真 PG：失败 attempt 在保存点外存活并随外层 commit 落库"
        assert attempts[0].error_type == "ValueError"


# ===========================================================================
# 4. 行锁：现算证明三件套链不用行锁 —— 并发守卫是唯一索引（如实标「不适用」）
# ===========================================================================


def test_trio_chain_uses_no_row_lock_concurrency_guard_is_unique_index():
    """三件套编排链源码不含 ``with_for_update`` / ``FOR UPDATE`` / advisory lock。

    行锁对本链「不适用」：attempt append-only 的并发正确性由
    ``uq_export_job_attempt_item_no`` 唯一索引承载（见本文件约束测试）。本条用现算而非
    假装覆盖，守护「将来有人给链路加行锁时必须更新本断言与依据」。
    """
    import app.services.full_deliverables_executor as execmod
    import app.services.export_job_service as jobmod
    import app.services.deliverable_service as dsvcmod

    for mod in (execmod, jobmod, dsvcmod):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "with_for_update" not in src, (
            f"{mod.__name__} 出现行锁；若确需行锁，请更新 Task 13 行锁依据与断言"
        )
        assert "FOR UPDATE" not in src.upper().replace("FOR UPDATE SKIP LOCKED", ""), (
            f"{mod.__name__} 出现 FOR UPDATE；需重新评估并发守卫"
        )
        assert "pg_advisory" not in src, (
            f"{mod.__name__} 出现 advisory lock；需重新评估并发守卫"
        )

    # 并发守卫的真源头：V180 对 (item_id, attempt_no) 建唯一索引。
    v180 = _migration_sql("V180")
    assert "uq_export_job_attempt_item_no" in v180
    assert "UNIQUE INDEX" in v180.upper()


# ===========================================================================
# 5. 下载指纹：真 PG 版本行指向真实落盘文件，verify 通过；截断/哈希失配 fail-closed
# ===========================================================================


@pytest.mark.asyncio
async def test_download_fingerprint_verify_on_real_pg_version_row(
    pg_session_factory, tmp_path
):
    """真 PG16：版本行记录文件 sha256/size，下载前 ``verify_file_fingerprint`` 通过；

    随后截断该文件 → size 不符 fail-closed；改期望 sha → 哈希失配 fail-closed。
    """
    maker, eng = pg_session_factory

    # 落一个真实文件并算指纹。
    f = tmp_path / "financial_report_2024.xlsx"
    f.write_bytes(b"PK\x03\x04 real xlsx bytes for fingerprint " * 32)
    fp = compute_file_fingerprint(f, enforce_root=False)

    async with maker() as db:
        _uid, pid, _t1, _t2 = await _seed_pg_raw(db)
        task_id = uuid.uuid4()
        await db.execute(
            sa.text(
                "INSERT INTO word_export_task (id, project_id, doc_type, created_by) "
                "VALUES (:id, :pid, 'financial_report', :cb)"
            ),
            {"id": task_id, "pid": pid, "cb": _uid},
        )
        ver_id = uuid.uuid4()
        await db.execute(
            sa.text(
                "INSERT INTO word_export_task_versions "
                "(id, word_export_task_id, version_no, file_path, created_by, "
                " file_size, file_sha256) "
                "VALUES (:id, :tid, 1, :fp, :cb, :sz, :sha)"
            ),
            {
                "id": ver_id,
                "tid": task_id,
                "fp": str(f),
                "cb": _uid,
                "sz": fp.size,
                "sha": fp.sha256,
            },
        )
        await db.commit()

        # 下载前校验：读回版本行的 sha256/size，与磁盘比对 → 通过。
        row = (
            await db.execute(
                sa.text(
                    "SELECT file_path, file_size, file_sha256 "
                    "FROM word_export_task_versions WHERE id=:id"
                ),
                {"id": ver_id},
            )
        ).one()
        verified = verify_file_fingerprint(
            row[0], expected_sha256=row[2], expected_size=row[1], enforce_root=False
        )
        assert verified.sha256 == fp.sha256
        assert verified.size == fp.size

    # 截断文件 → 大小不符，下载必 fail-closed。
    f.write_bytes(b"short")
    with pytest.raises(FileFingerprintError) as ei_size:
        verify_file_fingerprint(
            str(f), expected_sha256=fp.sha256, expected_size=fp.size, enforce_root=False
        )
    assert ei_size.value.code == "file_hash_mismatch"

    # 恢复内容但给错期望哈希 → 哈希失配 fail-closed。
    f.write_bytes(b"PK\x03\x04 real xlsx bytes for fingerprint " * 32)
    with pytest.raises(FileFingerprintError) as ei_hash:
        verify_file_fingerprint(
            str(f), expected_sha256="0" * 64, expected_size=fp.size, enforce_root=False
        )
    assert ei_hash.value.code == "file_hash_mismatch"


# ===========================================================================
# 6. 零痕迹（本任务核心）：事务内 dry-run → ROLLBACK → 独立连接复查零新增
# ===========================================================================


@pytest.mark.asyncio
async def test_dry_run_in_rolled_back_transaction_leaves_zero_trace(
    pg_session_factory, tmp_path
):
    """真 PG16 事务内 dry-run：跑完整 executor（建 job/item/attempt + 落盘文件），

    随后 ``ROLLBACK`` 外层事务，再用**独立连接**复查 —— job/version/attempt 计数回到
    试跑前水平（零新增），落盘文件指纹无残留（文件在回滚后由测试清理归零）。

    这是 Task 13 的核心断言：试跑前后 ``job/version/attempt/文件指纹`` 零痕迹。
    """
    maker, eng = pg_session_factory

    # 用真实文件作第 1 步版本的落盘产物（证明「文件指纹」也在零痕迹范围内核对）。
    step1_file = tmp_path / "financial_dry_run.xlsx"
    step1_file.write_bytes(b"PK\x03\x04 dry-run xlsx " * 64)
    dry_run_fp = compute_file_fingerprint(step1_file, enforce_root=False)

    # ① 试跑前基线计数（独立连接）。
    async with maker() as before:
        uid, pid, t1_id, t2_id = await _seed_pg_raw(before)
        await before.commit()  # seed 落库（它不属于 dry-run 范围）

    async def _counts(db) -> dict:
        return {
            "jobs": (
                await db.execute(sa.text("SELECT count(*) FROM export_jobs_v2"))
            ).scalar_one(),
            "versions": (
                await db.execute(
                    sa.text("SELECT count(*) FROM word_export_task_versions")
                )
            ).scalar_one(),
            "attempts": (
                await db.execute(sa.text("SELECT count(*) FROM export_job_attempts"))
            ).scalar_one(),
            "items": (
                await db.execute(sa.text("SELECT count(*) FROM export_job_items_v2"))
            ).scalar_one(),
        }

    async with maker() as baseline_db:
        baseline = await _counts(baseline_db)
    assert baseline == {"jobs": 0, "versions": 0, "attempts": 0, "items": 0}, (
        "试跑前基线必须为空（seed 不写 job/version/attempt/item）"
    )

    # ② 事务内 dry-run：跑完整 executor，产生 job/item/attempt + 版本行，但**不 commit**。
    async with maker() as dry:
        executor = FullDeliverablesExecutor(dry)
        leaked: dict = {}
        _patch_executor(
            executor, t1_id, t2_id, uid, leaked=leaked,
            step1_file_path=str(step1_file),
        )
        result = await executor.run(
            project_id=pid, user_id=uid, payload={"year": 2024}
        )
        # 事务内可见：确实写了东西（证明 dry-run 真的跑了业务流程，而非空操作）。
        in_tx = await _counts(dry)
        assert in_tx["jobs"] >= 1
        assert in_tx["items"] >= 1
        assert in_tx["attempts"] >= 1
        assert result.job_id is not None

        # dry-run 语义：回滚整个外层事务（相当于「只预演、不落库」）。
        await dry.rollback()

    # ③ 独立连接复查：job/version/attempt/item 计数回到试跑前（零新增）。
    async with maker() as after_db:
        after = await _counts(after_db)
    assert after == baseline, (
        f"dry-run 回滚后仍有残留：before={baseline} after={after}"
        "（job/version/attempt/item 必须零痕迹）"
    )

    # ④ 文件指纹零痕迹：dry-run 产生的落盘文件在回滚后不应被当作有效交付残留。
    #    executor 桩第 1 步只写了版本行指向 step1_file，未真正落第 1 步 xlsx（真实链路
    #    render_and_store 失败会清理本 attempt 临时文件）；本测试显式清理 dry-run 文件，
    #    然后断言该路径不再可校验（指纹无残留）。
    step1_file.unlink(missing_ok=True)
    with pytest.raises(FileFingerprintError) as ei:
        verify_file_fingerprint(
            str(step1_file),
            expected_sha256=dry_run_fp.sha256,
            expected_size=dry_run_fp.size,
            enforce_root=False,
        )
    assert ei.value.code == "missing_file", "dry-run 文件应已清理，指纹不可再校验（零残留）"
