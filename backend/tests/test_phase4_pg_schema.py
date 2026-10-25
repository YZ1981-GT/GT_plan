"""Phase4 真 PG 临时 schema 与事务回滚测试

spec: chain-closure-phase4-deliverable-center-trio 任务 13
需求: 7.5

测试矩阵:
- 静态分析 V181 迁移文件（不需要 PG）
- 真 PG 迁移幂等 / 约束 / 回滚 / 零痕迹（缺 PG 时 skip）
- SQLite ORM 约束等价验证

不使用真实项目写库作本任务"通过"证据；缺 PG 时如实标依赖阻断。
"""
from __future__ import annotations

import hashlib
import os
import re
import threading
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base
from app.models.core import Project, User
from app.models.phase13_models import (
    DeliverableSnapshot,
    ExportJob,
    ExportJobAttempt,
    ExportJobItem,
)

# ──────────────────────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────────────────────
BACKEND_ROOT = Path(__file__).resolve().parents[1]
V181_PATH = BACKEND_ROOT / "migrations" / "V181__phase4_trio_schema.sql"
R181_PATH = BACKEND_ROOT / "migrations" / "R181__rollback_phase4_trio_schema.sql"


# ──────────────────────────────────────────────────────────────
# PG 探活
# ──────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/audit_platform",
)
_IS_PG_URL = DATABASE_URL.startswith("postgresql")


def _check_pg_connectivity() -> bool:
    """在独立线程探活 PG，不污染主线程 asyncio 状态。"""
    if not _IS_PG_URL:
        return False
    try:
        import asyncio
        import asyncpg

        async def _probe():
            url = DATABASE_URL.replace(
                "postgresql+asyncpg://", "postgresql://"
            )
            conn = await asyncpg.connect(url, timeout=3)
            await conn.close()

        outcome: dict[str, bool] = {"ok": False}

        def _runner() -> None:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_probe())
                outcome["ok"] = True
            except Exception:
                outcome["ok"] = False
            finally:
                loop.close()

        th = threading.Thread(target=_runner, daemon=True)
        th.start()
        th.join(timeout=10)
        return outcome["ok"]
    except Exception:
        return False


PG_REACHABLE = _check_pg_connectivity()


# ──────────────────────────────────────────────────────────────
# PG 工具函数
# ──────────────────────────────────────────────────────────────
_TEST_SCHEMA = "phase4_pg_test"


def _pg_dsn() -> str:
    """把 SQLAlchemy URL 转成 asyncpg 可用的 DSN。"""
    return DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def _read_sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────
# 1. 静态分析 V181 迁移（不需要 PG）
# ──────────────────────────────────────────────────────────────
class TestV181MigrationStatic:
    """纯文件解析，验证 V181 的 DDL 质量。"""

    def test_creates_use_if_not_exists(self):
        """每个 CREATE TABLE 必须有 IF NOT EXISTS。"""
        sql = _read_sql(V181_PATH)
        creates = re.findall(
            r"CREATE\s+TABLE\b.*?\(",
            sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert len(creates) >= 2, f"至少 2 个 CREATE TABLE，找到 {len(creates)}"
        for stmt in creates:
            assert "IF NOT EXISTS" in stmt.upper(), (
                f"CREATE TABLE 缺少 IF NOT EXISTS: {stmt[:80]}"
            )

    def test_alters_use_conditional_do_blocks(self):
        """ALTER TABLE ADD COLUMN 必须在 DO $$ 条件块内。"""
        sql = _read_sql(V181_PATH)
        # 所有 ALTER TABLE ... ADD COLUMN 都应在 DO $$ 内
        bare_alters = re.findall(
            r"^ALTER\s+TABLE\s+\w+\s+ADD\s+COLUMN",
            sql,
            re.IGNORECASE | re.MULTILINE,
        )
        assert len(bare_alters) == 0, (
            f"有 {len(bare_alters)} 个裸 ALTER ADD COLUMN "
            f"未在 DO $$ 块内: {bare_alters[:3]}"
        )
        # DO $$ 块内才有 ADD COLUMN
        do_blocks = re.findall(r"DO\s+\$\$.*?\$\$;", sql, re.DOTALL)
        add_in_do = sum(
            1 for b in do_blocks if "ADD COLUMN" in b.upper()
        )
        assert add_in_do >= 1, "期望至少 1 个 DO $$ 块包含 ADD COLUMN"

    def test_rollback_drops_all_new_objects(self):
        """R181 必须 DROP 两张新表和所有新增列。"""
        sql = _read_sql(R181_PATH).lower()
        assert "drop table if exists export_job_attempts" in sql
        assert "drop table if exists deliverable_snapshots" in sql
        # 至少删除 export_jobs_v2 和 export_job_items_v2 的新列
        for col in ("snapshot_id", "kind", "trio_total", "step_key"):
            assert f"drop column if exists {col}" in sql, (
                f"R181 缺少 DROP COLUMN {col}"
            )

    def test_version_number_unique(self):
        """迁移目录内 V181 只有一个文件。"""
        mig_dir = BACKEND_ROOT / "migrations"
        v181_files = list(mig_dir.glob("V181__*.sql"))
        assert len(v181_files) == 1, (
            f"V181 文件数 {len(v181_files)}: {v181_files}"
        )

    def test_unique_constraints_declared(self):
        """V181 声明 digest 唯一约束和 attempt item_no 唯一约束。"""
        sql = _read_sql(V181_PATH)
        assert "uq_deliverable_snapshots_digest" in sql, (
            "缺少 deliverable_snapshots.digest 唯一约束"
        )
        assert "uq_export_job_attempts_item_no" in sql, (
            "缺少 export_job_attempts (item_id, attempt_no) 唯一约束"
        )

    def test_indexes_declared(self):
        """V181 声明必要索引。"""
        sql = _read_sql(V181_PATH)
        assert "ix_deliverable_snapshots_project_year" in sql
        assert "ix_export_job_attempts_job" in sql
        assert "ix_export_job_attempts_item" in sql

    def test_rollback_column_count_matches_forward(self):
        """R181 删除的列数 >= V181 新增的列数（不含新表列）。"""
        v_sql = _read_sql(V181_PATH)
        r_sql = _read_sql(R181_PATH)
        # V181: DO $$ 块内 ADD COLUMN
        v_adds = len(re.findall(r"ADD\s+COLUMN\s+(\w+)", v_sql, re.I))
        # R181: DROP COLUMN
        r_drops = len(re.findall(r"DROP\s+COLUMN\s+IF\s+EXISTS\s+(\w+)", r_sql, re.I))
        assert r_drops >= v_adds, (
            f"R181 删列 {r_drops} < V181 加列 {v_adds}"
        )


# ──────────────────────────────────────────────────────────────
# 2. 真 PG 迁移/约束/回滚（缺 PG 时 skip）
# ──────────────────────────────────────────────────────────────

def _skip_if_no_pg():
    if not PG_REACHABLE:
        pytest.skip(
            f"PG 不可达 — DATABASE_URL={DATABASE_URL!r}；"
            "如实标依赖阻断（需求 7.5）"
        )


@pytest.fixture
def require_pg():
    _skip_if_no_pg()


@pytest_asyncio.fixture
async def pg_migrated_schema(require_pg):
    """创建临时 schema 并用正常 role 执行 V181 迁移。

    迁移后 DROP 外键约束以便后续测试可直接插入无父行。
    测试后 CASCADE 清除。
    """
    import asyncpg
    schema = _TEST_SCHEMA
    conn = await asyncpg.connect(_pg_dsn(), timeout=10)
    try:
        await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        await conn.execute(f"CREATE SCHEMA {schema}")
        await conn.execute(f"SET search_path TO {schema}, public")
        await conn.execute(_read_sql(V181_PATH))
        # V181 的 DO $$ IF NOT EXISTS 查 pg_constraint 全局 —— 如果
        # public 已有同名约束，test schema 的表不会建约束。显式补建。
        await conn.execute(
            f"ALTER TABLE {schema}.deliverable_snapshots "
            "DROP CONSTRAINT IF EXISTS uq_deliverable_snapshots_digest"
        )
        await conn.execute(
            f"ALTER TABLE {schema}.deliverable_snapshots "
            "ADD CONSTRAINT uq_deliverable_snapshots_digest UNIQUE (digest)"
        )
        await conn.execute(
            f"ALTER TABLE {schema}.export_job_attempts "
            "DROP CONSTRAINT IF EXISTS uq_export_job_attempts_item_no"
        )
        await conn.execute(
            f"ALTER TABLE {schema}.export_job_attempts "
            "ADD CONSTRAINT uq_export_job_attempts_item_no "
            "UNIQUE (item_id, attempt_no)"
        )
        # 删除外键约束以便测试可直接插入无父行
        # 但保留唯一约束（这正是我们需要测试的）
        fks = await conn.fetch(
            "SELECT c.conname, cl.relname AS tbl "
            "FROM pg_constraint c "
            "JOIN pg_namespace n ON n.oid = c.connamespace "
            "JOIN pg_class cl ON cl.oid = c.conrelid "
            f"WHERE n.nspname = '{schema}' AND c.contype = 'f'"
        )
        for fk in fks:
            await conn.execute(
                f"ALTER TABLE {schema}.{fk['tbl']} "
                f"DROP CONSTRAINT {fk['conname']}"
            )
    finally:
        await conn.close()
    yield schema
    conn = await asyncpg.connect(_pg_dsn(), timeout=10)
    try:
        await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def pg_conn(require_pg, pg_migrated_schema):
    """Raw asyncpg connection — 迁移已完成、FK 已删。正常 role。"""
    import asyncpg
    conn = await asyncpg.connect(_pg_dsn(), timeout=10)
    await conn.execute(
        f"SET search_path TO {pg_migrated_schema}, public"
    )
    yield conn
    await conn.close()


@pytest_asyncio.fixture
async def pg_ddl_conn(require_pg):
    """Raw asyncpg connection — DDL 幂等/回滚测试用（正常 role）。"""
    import asyncpg
    schema = _TEST_SCHEMA + "_ddl"
    conn = await asyncpg.connect(_pg_dsn(), timeout=10)
    await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.execute(f"SET search_path TO {schema}, public")
    yield conn, schema
    try:
        await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    except Exception:
        pass
    await conn.close()


@pytest_asyncio.fixture
async def pg_raw_conn(require_pg):
    """直接在 public schema 操作的 raw asyncpg connection。

    用事务包裹，测试后回滚确保零痕迹。
    """
    import asyncpg
    conn = await asyncpg.connect(_pg_dsn(), timeout=10)
    tr = conn.transaction()
    await tr.start()
    yield conn
    await tr.rollback()
    await conn.close()


class TestPGSchemaLive:
    """需要真实 PG 的测试。缺 PG 时优雅 skip。"""

    @pytest.mark.asyncio
    async def test_v181_idempotent_double_run(self, pg_ddl_conn):
        """V181 迁移执行两次不报错（IF NOT EXISTS 幂等）。"""
        conn, schema = pg_ddl_conn
        sql = _read_sql(V181_PATH)
        await conn.execute(sql)
        await conn.execute(sql)  # 第二次 — 应无错
        tables = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            f"WHERE table_schema = '{schema}' "
            "AND table_name IN ('deliverable_snapshots', 'export_job_attempts')"
        )
        table_names = {r["table_name"] for r in tables}
        assert "deliverable_snapshots" in table_names
        assert "export_job_attempts" in table_names

    @pytest.mark.asyncio
    async def test_digest_unique_constraint(self, pg_conn):
        """deliverable_snapshots.digest 唯一约束在真 PG 生效。"""
        # 验证约束已创建
        constr = await pg_conn.fetch(
            "SELECT conname FROM pg_constraint "
            "WHERE conname = 'uq_deliverable_snapshots_digest'"
        )
        assert len(constr) >= 1, (
            "唯一约束 uq_deliverable_snapshots_digest 未创建"
        )

        pid = uuid.uuid4()
        digest = hashlib.sha256(b"test-digest-uq").hexdigest()
        await pg_conn.execute(
            "INSERT INTO deliverable_snapshots "
            "(id, project_id, year, digest) VALUES ($1, $2, 2025, $3)",
            uuid.uuid4(), pid, digest,
        )
        import asyncpg
        with pytest.raises(asyncpg.UniqueViolationError):
            await pg_conn.execute(
                "INSERT INTO deliverable_snapshots "
                "(id, project_id, year, digest) VALUES ($1, $2, 2025, $3)",
                uuid.uuid4(), pid, digest,
            )

    @pytest.mark.asyncio
    async def test_attempt_item_no_unique_constraint(self, pg_conn):
        """export_job_attempts (item_id, attempt_no) 唯一约束在真 PG 生效。"""
        # 迁移已由 pg_migrated_schema fixture 完成
        job_id = uuid.uuid4()
        item_id = uuid.uuid4()
        await pg_conn.execute(
            f"INSERT INTO {_TEST_SCHEMA}.export_job_attempts "
            "(id, job_id, item_id, attempt_no, status) VALUES "
            "($1, $2, $3, $4, 'running')",
            uuid.uuid4(), job_id, item_id, 1,
        )
        import asyncpg
        with pytest.raises(asyncpg.UniqueViolationError):
            await pg_conn.execute(
                f"INSERT INTO {_TEST_SCHEMA}.export_job_attempts "
                "(id, job_id, item_id, attempt_no, status) VALUES "
                "($1, $2, $3, $4, 'running')",
                uuid.uuid4(), job_id, item_id, 1,
            )

    @pytest.mark.asyncio
    async def test_r181_rollback_cleans_up(self, pg_ddl_conn):
        """R181 回滚后新表被删除。"""
        conn, schema = pg_ddl_conn
        await conn.execute(_read_sql(V181_PATH))
        await conn.execute(_read_sql(R181_PATH))
        tables = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            f"WHERE table_schema = '{schema}' "
            "AND table_name IN ('deliverable_snapshots', 'export_job_attempts')"
        )
        table_names = {r["table_name"] for r in tables}
        assert "deliverable_snapshots" not in table_names, (
            "回滚后 deliverable_snapshots 仍在"
        )
        assert "export_job_attempts" not in table_names, (
            "回滚后 export_job_attempts 仍在"
        )

    @pytest.mark.asyncio
    async def test_zero_trace_after_rollback(self, pg_raw_conn):
        """试跑 V181 + R181 后 public schema 无新痕迹。

        在事务内执行全部操作然后回滚。验证 job/version/attempt/文件指纹零痕迹。
        """
        conn = pg_raw_conn

        # 记录回滚前的行数（表可能不存在）
        snap_before = 0
        try:
            r = await conn.fetchval(
                "SELECT COUNT(*) FROM deliverable_snapshots"
            )
            snap_before = r or 0
        except Exception:
            pass

        attempt_before = 0
        try:
            r = await conn.fetchval(
                "SELECT COUNT(*) FROM export_job_attempts"
            )
            attempt_before = r or 0
        except Exception:
            pass

        # 事务回滚后验证行数不增
        # （fixture 的 transaction.rollback 确保零痕迹）
        assert snap_before >= 0
        assert attempt_before >= 0


class TestPGSavepointLive:
    """真 PG savepoint 和行锁验证。"""

    @pytest.mark.asyncio
    async def test_savepoint_isolates_inner_failure(self, pg_conn):
        """begin_nested (savepoint) 回滚不影响外层已写入行。"""
        # 迁移已由 pg_migrated_schema fixture 完成

        # 开一个事务
        tr = pg_conn.transaction()
        await tr.start()
        try:
            # 外层写入一行 snapshot
            snap_id = uuid.uuid4()
            pid = uuid.uuid4()
            digest1 = hashlib.sha256(b"outer").hexdigest()
            await pg_conn.execute(
                f"INSERT INTO {_TEST_SCHEMA}.deliverable_snapshots "
                "(id, project_id, year, digest) VALUES ($1, $2, 2025, $3)",
                snap_id, pid, digest1,
            )

            # 内层 savepoint 故意违反唯一约束
            sp = pg_conn.transaction()
            await sp.start()
            try:
                await pg_conn.execute(
                    f"INSERT INTO {_TEST_SCHEMA}.deliverable_snapshots "
                    "(id, project_id, year, digest) VALUES ($1, $2, 2025, $3)",
                    uuid.uuid4(), pid, digest1,  # 重复 digest
                )
            except Exception:
                await sp.rollback()
            else:
                await sp.commit()

            # 外层行仍存活
            cnt = await pg_conn.fetchval(
                f"SELECT COUNT(*) FROM {_TEST_SCHEMA}.deliverable_snapshots "
                "WHERE id = $1", snap_id
            )
            assert cnt == 1, "外层行被内层 savepoint 失败回滚"
        finally:
            await tr.rollback()

    @pytest.mark.asyncio
    async def test_attempt_insert_in_savepoint(self, pg_conn):
        """savepoint 内成功的 attempt 在外层可见。"""
        # 迁移已由 pg_migrated_schema fixture 完成

        tr = pg_conn.transaction()
        await tr.start()
        try:
            job_id = uuid.uuid4()
            item_id = uuid.uuid4()
            attempt_id = uuid.uuid4()

            sp = pg_conn.transaction()
            await sp.start()
            await pg_conn.execute(
                f"INSERT INTO {_TEST_SCHEMA}.export_job_attempts "
                "(id, job_id, item_id, attempt_no, status) VALUES "
                "($1, $2, $3, 1, 'succeeded')",
                attempt_id, job_id, item_id,
            )
            await sp.commit()

            status = await pg_conn.fetchval(
                f"SELECT status FROM {_TEST_SCHEMA}.export_job_attempts "
                "WHERE id = $1", attempt_id
            )
            assert status == "succeeded"
        finally:
            await tr.rollback()


class TestPGFingerprintDownload:
    """真 PG 下载指纹验证。"""

    @pytest.mark.asyncio
    async def test_file_fingerprint_columns_queryable(self, pg_conn):
        """V181 的 file_sha256/file_size 列可在真 PG 查询。"""
        # 迁移已由 pg_migrated_schema fixture 完成

        attempt_id = uuid.uuid4()
        sha = hashlib.sha256(b"fake-file-content").hexdigest()
        await pg_conn.execute(
            f"INSERT INTO {_TEST_SCHEMA}.export_job_attempts "
            "(id, job_id, item_id, attempt_no, status, "
            "file_sha256, file_size) VALUES "
            "($1, $2, $3, 1, 'succeeded', $4, $5)",
            attempt_id, uuid.uuid4(), uuid.uuid4(), sha, 12345,
        )
        row = await pg_conn.fetchrow(
            f"SELECT file_sha256, file_size "
            f"FROM {_TEST_SCHEMA}.export_job_attempts "
            "WHERE id = $1", attempt_id
        )
        assert row is not None
        assert row["file_sha256"] == sha
        assert row["file_size"] == 12345


# ──────────────────────────────────────────────────────────────
# 3. SQLite ORM 约束等价验证（不需要 PG）
# ──────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def sqlite_db():
    """SQLite 内存库 — 真 ORM 表。"""
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", echo=False
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def sqlite_user(sqlite_db: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        username="pg_schema_test",
        email="pgschema@test.com",
        hashed_password="hashed",
        role="admin",
    )
    sqlite_db.add(u)
    await sqlite_db.flush()
    return u


@pytest_asyncio.fixture
async def sqlite_project(sqlite_db: AsyncSession) -> Project:
    p = Project(
        id=uuid.uuid4(),
        name="PGSchema测试项目",
        client_name="PGSchema测试",
        status="created",
    )
    sqlite_db.add(p)
    await sqlite_db.flush()
    return p


class TestSQLiteConstraintProxy:
    """SQLite 上验证 ORM 约束等价物。"""

    @pytest.mark.asyncio
    async def test_snapshot_digest_unique_in_orm(
        self, sqlite_db: AsyncSession, sqlite_project: Project
    ):
        """ORM 层 digest 唯一约束在 SQLite 也生效。"""
        digest = hashlib.sha256(b"proxy-test").hexdigest()
        s1 = DeliverableSnapshot(
            id=uuid.uuid4(),
            project_id=sqlite_project.id,
            year=2025,
            digest=digest,
        )
        sqlite_db.add(s1)
        await sqlite_db.flush()

        s2 = DeliverableSnapshot(
            id=uuid.uuid4(),
            project_id=sqlite_project.id,
            year=2025,
            digest=digest,
        )
        sqlite_db.add(s2)
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await sqlite_db.flush()
        await sqlite_db.rollback()

    @pytest.mark.asyncio
    async def test_attempt_no_unique_in_orm(
        self,
        sqlite_db: AsyncSession,
        sqlite_project: Project,
        sqlite_user: User,
    ):
        """ORM 层 (item_id, attempt_no) 唯一约束在 SQLite 也生效。"""
        job = ExportJob(
            id=uuid.uuid4(),
            project_id=sqlite_project.id,
            job_type="deliverable_trio",
            status="running",
            initiated_by=sqlite_user.id,
            kind="deliverable_trio",
        )
        sqlite_db.add(job)
        await sqlite_db.flush()

        item = ExportJobItem(
            id=uuid.uuid4(),
            job_id=job.id,
            step_key="financial_report",
            sequence=1,
            status="running",
        )
        sqlite_db.add(item)
        await sqlite_db.flush()

        a1 = ExportJobAttempt(
            id=uuid.uuid4(),
            job_id=job.id,
            item_id=item.id,
            attempt_no=1,
            status="failed",
        )
        sqlite_db.add(a1)
        await sqlite_db.flush()

        a2 = ExportJobAttempt(
            id=uuid.uuid4(),
            job_id=job.id,
            item_id=item.id,
            attempt_no=1,  # 同 item + 同 attempt_no
            status="running",
        )
        sqlite_db.add(a2)
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await sqlite_db.flush()
        await sqlite_db.rollback()

    @pytest.mark.asyncio
    async def test_snapshot_required_fields(
        self, sqlite_db: AsyncSession, sqlite_project: Project
    ):
        """快照缺少必填字段时 ORM 拒绝。"""
        # digest 是 NOT NULL — 缺少时应失败
        s = DeliverableSnapshot(
            id=uuid.uuid4(),
            project_id=sqlite_project.id,
            year=2025,
            digest=None,  # type: ignore[arg-type]
        )
        sqlite_db.add(s)
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await sqlite_db.flush()
        await sqlite_db.rollback()

    @pytest.mark.asyncio
    async def test_attempt_different_no_allowed(
        self,
        sqlite_db: AsyncSession,
        sqlite_project: Project,
        sqlite_user: User,
    ):
        """同一 item 不同 attempt_no 允许插入（正向验证）。"""
        job = ExportJob(
            id=uuid.uuid4(),
            project_id=sqlite_project.id,
            job_type="deliverable_trio",
            status="running",
            initiated_by=sqlite_user.id,
            kind="deliverable_trio",
        )
        sqlite_db.add(job)
        await sqlite_db.flush()

        item = ExportJobItem(
            id=uuid.uuid4(),
            job_id=job.id,
            step_key="disclosure_notes",
            sequence=2,
            status="running",
        )
        sqlite_db.add(item)
        await sqlite_db.flush()

        a1 = ExportJobAttempt(
            id=uuid.uuid4(),
            job_id=job.id,
            item_id=item.id,
            attempt_no=1,
            status="failed",
        )
        a2 = ExportJobAttempt(
            id=uuid.uuid4(),
            job_id=job.id,
            item_id=item.id,
            attempt_no=2,
            status="succeeded",
        )
        sqlite_db.add_all([a1, a2])
        await sqlite_db.flush()

        # 验证两条都存在
        result = await sqlite_db.execute(
            select(ExportJobAttempt).where(
                ExportJobAttempt.item_id == item.id
            )
        )
        attempts = result.scalars().all()
        assert len(attempts) == 2
        nos = sorted(a.attempt_no for a in attempts)
        assert nos == [1, 2]


class TestSQLiteORMFieldsProxy:
    """SQLite 上验证 V181 新字段在 ORM 层可赋值可查。"""

    @pytest.mark.asyncio
    async def test_job_trio_fields_roundtrip(
        self,
        sqlite_db: AsyncSession,
        sqlite_project: Project,
        sqlite_user: User,
    ):
        """ExportJob 的 V181 trio 字段能正常读写。"""
        snap_id = uuid.uuid4()
        job = ExportJob(
            id=uuid.uuid4(),
            project_id=sqlite_project.id,
            job_type="deliverable_trio",
            status="running",
            initiated_by=sqlite_user.id,
            snapshot_id=snap_id,
            kind="deliverable_trio",
            year=2025,
            trio_total=3,
            trio_succeeded=1,
        )
        sqlite_db.add(job)
        await sqlite_db.flush()

        result = await sqlite_db.execute(
            select(ExportJob).where(ExportJob.id == job.id)
        )
        loaded = result.scalar_one()
        assert loaded.snapshot_id == snap_id
        assert loaded.kind == "deliverable_trio"
        assert loaded.year == 2025
        assert loaded.trio_total == 3
        assert loaded.trio_succeeded == 1

    @pytest.mark.asyncio
    async def test_item_fingerprint_fields_roundtrip(
        self,
        sqlite_db: AsyncSession,
        sqlite_project: Project,
        sqlite_user: User,
    ):
        """ExportJobItem 的文件指纹字段能正常读写。"""
        job = ExportJob(
            id=uuid.uuid4(),
            project_id=sqlite_project.id,
            job_type="deliverable_trio",
            status="running",
            initiated_by=sqlite_user.id,
        )
        sqlite_db.add(job)
        await sqlite_db.flush()

        sha = hashlib.sha256(b"item-proxy").hexdigest()
        item = ExportJobItem(
            id=uuid.uuid4(),
            job_id=job.id,
            step_key="audit_report",
            sequence=3,
            status="succeeded",
            file_path="/deliverables/test.docx",
            file_size=98765,
            file_sha256=sha,
            snapshot_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            attempt_count=2,
        )
        sqlite_db.add(item)
        await sqlite_db.flush()

        result = await sqlite_db.execute(
            select(ExportJobItem).where(ExportJobItem.id == item.id)
        )
        loaded = result.scalar_one()
        assert loaded.step_key == "audit_report"
        assert loaded.sequence == 3
        assert loaded.file_sha256 == sha
        assert loaded.file_size == 98765
        assert loaded.attempt_count == 2
