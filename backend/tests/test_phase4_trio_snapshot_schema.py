"""Phase4 Task 3 — 快照与 schema/ORM 三层一致（交付证据 + 变异证明）。

spec: ``.kiro/specs/chain-closure-phase4-deliverable-center-trio``（需求 1.5, 2.4, 3.2, 7.5）。

覆盖三层一致（DB 迁移 + ORM ``Mapped[]`` + service）与两条快照铁律：

- **A 组（SQLite 真 ORM + 纯函数）**：
  - ``ExportJobAttempt`` 模型可建表、append-only ``attempt_no`` 唯一（ORM 层投影）；
  - item 的 ``step_key/sequence/file_sha256/snapshot_id`` 等新列存在；
  - 共享快照 digest **不含生成时间与绝对路径**；同输入同 digest（幂等）；
  - 三件套三项绑定**同一** snapshot_id；``verify_trio_shares_snapshot`` 一致判定。
  - **变异**：改快照业务输入 → digest 变（RED）；让一项换 snapshot → verify False（RED）。

- **B 组（真 PG16，无 PG 环境 skip）**：
  - 一次性库上应用真实 ``V180`` SQL **两次**幂等（第二次不报错、结果一致）；
  - 约束：同 item 的 ``attempt_no`` 唯一冲突被拒；同 job 的 ``step_key`` 唯一冲突被拒；
  - ``R180`` 回滚后新增表与列消失（迁移漏列的反向证明）。
  - **变异**：从 V180 删一列后，依赖该列的插入/约束断言必须红（本组用「漏列即插入失败」证明）。

真实 PG 铁律（design §10.3）：迁移/约束/回滚在真实 PG16 验证；无 PG 环境 skip。
Windows：``python`` 而非 ``python3``；无 ``&&``。
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.migration_runner import MigrationRunner
from app.models.base import Base
from app.models.core import Project, User
from app.models.phase13_models import (
    ExportJob,
    ExportJobAttempt,
    ExportJobItem,
    ExportJobStatus,
)
from app.services.deliverable_trio_snapshot import (
    TRIO_STEP_KEYS,
    DeliverableTrioSnapshot,
    build_digest,
)

_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


# ===========================================================================
# A 组：SQLite 真 ORM + 纯函数快照
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


@pytest_asyncio.fixture
async def seeded(sqlite_db: AsyncSession):
    user = User(
        id=uuid.uuid4(),
        username="phase4_t3",
        email="phase4t3@test.com",
        hashed_password="hashed",
        role="admin",
    )
    project = Project(
        id=uuid.uuid4(), name="三件套快照项目", client_name="测试公司", status="created"
    )
    sqlite_db.add_all([user, project])
    await sqlite_db.flush()
    return {"user": user, "project": project}


async def _make_trio_job(db: AsyncSession, project_id, user_id) -> ExportJob:
    """建一个三件套 job + 三个固定 step_key/sequence 的 item。"""
    job = ExportJob(
        project_id=project_id,
        job_type="deliverable_trio",
        status=ExportJobStatus.queued.value,
        payload={"year": 2025},
        progress_total=3,
        initiated_by=user_id,
    )
    db.add(job)
    await db.flush()
    for seq, key in enumerate(TRIO_STEP_KEYS, start=1):
        db.add(
            ExportJobItem(
                job_id=job.id,
                status=ExportJobStatus.queued.value,
                step_key=key,
                sequence=seq,
            )
        )
    await db.flush()
    return job


class TestOrmLayer:
    """ORM 三层一致：新模型/新列在 ORM 层真实可用。"""

    @pytest.mark.asyncio
    async def test_attempt_model_and_item_columns_exist(self, sqlite_db, seeded):
        job = await _make_trio_job(
            sqlite_db, seeded["project"].id, seeded["user"].id
        )
        items = (
            await sqlite_db.execute(
                sa.select(ExportJobItem).where(ExportJobItem.job_id == job.id)
            )
        ).scalars().all()
        assert {i.step_key for i in items} == set(TRIO_STEP_KEYS)
        assert sorted(i.sequence for i in items) == [1, 2, 3]

        # 新列可写：文件指纹投影 + 共享快照
        target = items[0]
        target.snapshot_id = "deadbeef"
        target.file_sha256 = "a" * 64
        target.file_size = 123
        target.file_path = "x.xlsx"
        target.version_id = uuid.uuid4()
        target.attempt_count = 1
        target.last_attempt_id = uuid.uuid4()
        await sqlite_db.flush()

        # ExportJobAttempt 可建行
        att = ExportJobAttempt(
            job_id=job.id,
            item_id=target.id,
            attempt_no=1,
            status="failed",
            trigger="initial",
            snapshot_id="deadbeef",
            error_type="OSError",
            error_message="磁盘写入失败",
            diagnostic_detail={"stage": "persist"},
        )
        sqlite_db.add(att)
        await sqlite_db.flush()
        got = (
            await sqlite_db.execute(
                sa.select(ExportJobAttempt).where(
                    ExportJobAttempt.item_id == target.id
                )
            )
        ).scalars().all()
        assert len(got) == 1
        assert got[0].error_message == "磁盘写入失败"

    @pytest.mark.asyncio
    async def test_job_trio_columns_exist(self, sqlite_db, seeded):
        job = await _make_trio_job(
            sqlite_db, seeded["project"].id, seeded["user"].id
        )
        # 默认 trio_total=3（server_default），trio_succeeded=0
        await sqlite_db.refresh(job)
        assert job.trio_total == 3
        assert job.trio_succeeded == 0
        job.snapshot_id = "cafe"
        job.readiness = {"status": "ready", "hard_blockers": []}
        await sqlite_db.flush()


class TestSharedSnapshotDigest:
    """共享快照 digest：不含时间/绝对路径，同输入同 digest。"""

    def test_digest_excludes_generation_time(self):
        base = {
            "project_id": "p1",
            "year": 2025,
            "tb_hash": "abc",
        }
        with_time = {**base, "generated_at": "2026-10-01T00:00:00Z"}
        with_time2 = {**base, "generated_at": "2099-12-31T23:59:59Z"}
        assert build_digest(base) == build_digest(with_time)
        assert build_digest(with_time) == build_digest(with_time2)

    def test_digest_excludes_absolute_path(self):
        base = {"project_id": "p1", "year": 2025, "tb_hash": "abc"}
        with_abs = {**base, "file_abs_path": r"D:\GT_plan\storage\x.xlsx"}
        with_abs2 = {**base, "report_abs_path": "/var/data/y.docx"}
        assert build_digest(base) == build_digest(with_abs)
        assert build_digest(base) == build_digest(with_abs2)

    def test_same_input_same_digest(self):
        content = {"project_id": "p1", "year": 2025, "tb_hash": "abc", "notes": {"n": 1}}
        assert build_digest(content) == build_digest(dict(content))

    def test_mutating_business_input_changes_digest(self):
        """变异：改 tb_hash（真实源数据）必须让 digest 变化（否则 digest 是常量）。"""
        content = {"project_id": "p1", "year": 2025, "tb_hash": "abc"}
        mutated = {**content, "tb_hash": "DIFFERENT"}
        assert build_digest(content) != build_digest(mutated), (
            "改快照业务输入后 digest 未变 ⇒ digest 没真正绑定源数据"
        )


class TestTrioSharesSameSnapshot:
    """三件套三项必须引用同一 snapshot_id（需求 2.4）。"""

    @pytest.mark.asyncio
    async def test_bind_all_three_to_same_snapshot(self, sqlite_db, seeded):
        job = await _make_trio_job(
            sqlite_db, seeded["project"].id, seeded["user"].id
        )
        svc = DeliverableTrioSnapshot(sqlite_db)
        digest = svc.digest({"project_id": "p1", "year": 2025, "tb_hash": "abc"})
        bound = await svc.bind_items_to_snapshot(job.id, digest)
        assert bound == 3

        assert await svc.verify_trio_shares_snapshot(job.id) is True

        # job 与三项都绑同一 digest
        await sqlite_db.refresh(job)
        assert job.snapshot_id == digest
        snaps = (
            await sqlite_db.execute(
                sa.select(ExportJobItem.snapshot_id).where(
                    ExportJobItem.job_id == job.id
                )
            )
        ).scalars().all()
        assert set(snaps) == {digest}

    @pytest.mark.asyncio
    async def test_one_item_different_snapshot_fails_verify(self, sqlite_db, seeded):
        """变异：让其中一项换成别的 snapshot ⇒ verify 必须 False（跨快照 fail-closed）。"""
        job = await _make_trio_job(
            sqlite_db, seeded["project"].id, seeded["user"].id
        )
        svc = DeliverableTrioSnapshot(sqlite_db)
        digest = svc.digest({"project_id": "p1", "year": 2025, "tb_hash": "abc"})
        await svc.bind_items_to_snapshot(job.id, digest)
        assert await svc.verify_trio_shares_snapshot(job.id) is True

        # 篡改一项为不同快照
        one = (
            await sqlite_db.execute(
                sa.select(ExportJobItem).where(
                    ExportJobItem.job_id == job.id,
                    ExportJobItem.step_key == "disclosure_notes",
                )
            )
        ).scalar_one()
        one.snapshot_id = "TAMPERED_DIFFERENT_SNAPSHOT"
        await sqlite_db.flush()

        assert await svc.verify_trio_shares_snapshot(job.id) is False, (
            "一项换了快照后仍判一致 ⇒ 跨快照混用未被拦截"
        )


# ===========================================================================
# B 组：真 PG16（迁移幂等 / 约束 / R180 回滚）
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


# V180 依赖的最小前置表（export_jobs_v2 / export_job_items_v2 /
# word_export_task_versions）。只建 V180 会触碰到的列，验证 V180 的 ADD/CREATE 幂等。
_PREREQ_SQL = """
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


@asynccontextmanager
async def _throwaway_db():
    from sqlalchemy.pool import NullPool

    head = _base_url()
    ca = _connect_args()
    admin_url = head + "/postgres"
    tmp_db = f"phase4_t3_{uuid.uuid4().hex[:12]}"

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
            for stmt in _PREREQ_SQL.strip().split(";"):
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


def _migration_sql(version: str) -> str:
    """读真实迁移文件内容（V180 / R180）。"""
    prefix = version  # 如 "V180" / "R180"
    matches = [p for p in _MIGRATIONS_DIR.iterdir() if p.name.startswith(prefix + "__")]
    assert len(matches) == 1, f"应恰有 1 个 {prefix} 文件，实际 {matches}"
    return matches[0].read_text(encoding="utf-8")


async def _apply_sql(eng, sql: str) -> None:
    """用迁移运行器同款分句器执行一段迁移 SQL。"""
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


@pytest.mark.asyncio
async def test_v180_applies_twice_idempotent():
    """V180 真实 SQL 在真 PG 上应用两次：第二次不报错，列/表与第一次一致。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    v180 = _migration_sql("V180")
    async with _throwaway_db() as (eng, _url):
        await _apply_sql(eng, v180)
        cols1_job = await _columns(eng, "export_jobs_v2")
        cols1_item = await _columns(eng, "export_job_items_v2")
        cols1_ver = await _columns(eng, "word_export_task_versions")
        assert await _table_exists(eng, "export_job_attempts")

        # 第二次应用必须幂等（IF NOT EXISTS），不抛错
        await _apply_sql(eng, v180)
        cols2_job = await _columns(eng, "export_jobs_v2")
        cols2_item = await _columns(eng, "export_job_items_v2")
        cols2_ver = await _columns(eng, "word_export_task_versions")

        assert cols1_job == cols2_job
        assert cols1_item == cols2_item
        assert cols1_ver == cols2_ver

        # 关键新列确实落到真 PG schema
        assert {"snapshot_id", "trio_total", "trio_succeeded", "readiness"} <= cols2_job
        assert {"step_key", "sequence", "snapshot_id", "file_sha256"} <= cols2_item
        assert {"file_sha256", "snapshot_id"} <= cols2_ver


@pytest.mark.asyncio
async def test_v180_attempt_no_unique_constraint():
    """约束：同一 item 的 attempt_no 唯一（append-only，禁覆盖）。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_db() as (eng, _url):
        await _apply_sql(eng, _migration_sql("V180"))
        job_id, item_id = uuid.uuid4(), uuid.uuid4()
        async with eng.begin() as conn:
            await conn.exec_driver_sql(
                "INSERT INTO export_jobs_v2 (id, project_id, job_type) "
                f"VALUES ('{job_id}', '{uuid.uuid4()}', 'deliverable_trio')"
            )
            await conn.exec_driver_sql(
                "INSERT INTO export_job_items_v2 (id, job_id, step_key, sequence) "
                f"VALUES ('{item_id}', '{job_id}', 'financial_report', 1)"
            )
            await conn.exec_driver_sql(
                "INSERT INTO export_job_attempts (id, job_id, item_id, attempt_no) "
                f"VALUES ('{uuid.uuid4()}', '{job_id}', '{item_id}', 1)"
            )
        # 同 item 再插 attempt_no=1 必须被唯一约束拒绝
        with pytest.raises(Exception) as ei:
            async with eng.begin() as conn:
                await conn.exec_driver_sql(
                    "INSERT INTO export_job_attempts (id, job_id, item_id, attempt_no) "
                    f"VALUES ('{uuid.uuid4()}', '{job_id}', '{item_id}', 1)"
                )
        assert "uq_export_job_attempt_item_no" in str(ei.value) or "unique" in str(
            ei.value
        ).lower()


@pytest.mark.asyncio
async def test_v180_step_key_unique_per_job():
    """约束：同 job 内一个 step_key 只能一行（三件套固定 3 行）。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_db() as (eng, _url):
        await _apply_sql(eng, _migration_sql("V180"))
        job_id = uuid.uuid4()
        async with eng.begin() as conn:
            await conn.exec_driver_sql(
                "INSERT INTO export_jobs_v2 (id, project_id, job_type) "
                f"VALUES ('{job_id}', '{uuid.uuid4()}', 'deliverable_trio')"
            )
            await conn.exec_driver_sql(
                "INSERT INTO export_job_items_v2 (id, job_id, step_key, sequence) "
                f"VALUES ('{uuid.uuid4()}', '{job_id}', 'financial_report', 1)"
            )
        with pytest.raises(Exception) as ei:
            async with eng.begin() as conn:
                await conn.exec_driver_sql(
                    "INSERT INTO export_job_items_v2 (id, job_id, step_key, sequence) "
                    f"VALUES ('{uuid.uuid4()}', '{job_id}', 'financial_report', 1)"
                )
        assert "uq_export_job_item_step" in str(ei.value) or "unique" in str(
            ei.value
        ).lower()


@pytest.mark.asyncio
async def test_r180_rollback_removes_table_and_columns():
    """R180 回滚后：attempt 表与 V180 新增列全部消失（迁移漏列的反向证明）。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_db() as (eng, _url):
        await _apply_sql(eng, _migration_sql("V180"))
        assert await _table_exists(eng, "export_job_attempts")

        await _apply_sql(eng, _migration_sql("R180"))
        assert not await _table_exists(eng, "export_job_attempts")

        cols_job = await _columns(eng, "export_jobs_v2")
        cols_item = await _columns(eng, "export_job_items_v2")
        cols_ver = await _columns(eng, "word_export_task_versions")
        assert "snapshot_id" not in cols_job
        assert "trio_total" not in cols_job
        assert "step_key" not in cols_item
        assert "file_sha256" not in cols_item
        assert "file_sha256" not in cols_ver
        assert "snapshot_id" not in cols_ver

        # R180 幂等：再次回滚不报错
        await _apply_sql(eng, _migration_sql("R180"))
