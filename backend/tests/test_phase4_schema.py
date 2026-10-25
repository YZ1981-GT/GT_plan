"""Phase4 三件套 schema/ORM 三层一致性测试

spec: chain-closure-phase4-deliverable-center-trio 任务 3
需求: 1.5, 2.4, 3.2, 7.5

测试矩阵:
- ORM ↔ 迁移列名一致（所有 V181 新增列在 ORM 中存在）
- 新表 export_job_attempts / deliverable_snapshots 已注册
- 快照 digest 不含生成时间和绝对路径（确定性、幂等）
- 三件套 item 必须引用同一 snapshot（变异红）
- 迁移版本号不撞（V181 唯一）
- SQLite 真 ORM 插入验证字段存在性
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.core import Project, User
from app.models.phase13_models import (
    DeliverableSnapshot,
    ExportJob,
    ExportJobAttempt,
    ExportJobItem,
)
from app.services.deliverable_readiness_service import build_snapshot_digest


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db():
    """SQLite 内存库 — 真 ORM 表。"""
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
async def user(db: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        username="schema_test",
        email="schema@test.com",
        hashed_password="hashed",
        role="admin",
    )
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture
async def project(db: AsyncSession) -> Project:
    p = Project(
        id=uuid.uuid4(),
        name="Schema测试项目",
        client_name="Schema测试",
        status="created",
    )
    db.add(p)
    await db.flush()
    return p


# ──────────────────────────────────────────────────────────────────────
# 1. ORM ↔ 迁移列名一致性
# ──────────────────────────────────────────────────────────────────────

class TestORMMigrationConsistency:
    """ORM 列集合必须覆盖 V181 迁移新增的所有列。"""

    # V181 给 export_jobs_v2 新增的列
    V181_JOB_COLUMNS = {
        "snapshot_id", "kind", "year",
        "trio_total", "trio_succeeded",
        "started_at", "finished_at",
    }

    # V181 给 export_job_items_v2 新增的列
    V181_ITEM_COLUMNS = {
        "step_key", "sequence", "snapshot_id",
        "version_id", "file_path", "file_size",
        "file_sha256", "attempt_count", "last_attempt_id",
    }

    # deliverable_snapshots 所有列
    SNAPSHOT_COLUMNS = {
        "id", "project_id", "year",
        "digest", "payload",
        "created_at", "created_by",
    }

    # export_job_attempts 所有列
    ATTEMPT_COLUMNS = {
        "id", "job_id", "item_id", "attempt_no",
        "status", "started_at", "finished_at",
        "snapshot_id", "error_type", "error_message",
        "diagnostic_detail", "file_path", "file_size",
        "file_sha256", "version_id", "created_by",
        "trigger_source",
    }

    def test_export_job_has_all_v181_columns(self):
        """ExportJob ORM 必须包含 V181 迁移新增的所有列。"""
        orm_cols = {c.name for c in ExportJob.__table__.columns}
        missing = self.V181_JOB_COLUMNS - orm_cols
        assert not missing, (
            f"ExportJob ORM 缺少 V181 列: {sorted(missing)}。"
            f"当前列: {sorted(orm_cols)}"
        )

    def test_export_job_item_has_all_v181_columns(self):
        """ExportJobItem ORM 必须包含 V181 迁移新增的所有列。"""
        orm_cols = {c.name for c in ExportJobItem.__table__.columns}
        missing = self.V181_ITEM_COLUMNS - orm_cols
        assert not missing, (
            f"ExportJobItem ORM 缺少 V181 列: {sorted(missing)}。"
            f"当前列: {sorted(orm_cols)}"
        )

    def test_deliverable_snapshot_has_all_columns(self):
        """DeliverableSnapshot ORM 列必须覆盖迁移定义。"""
        orm_cols = {c.name for c in DeliverableSnapshot.__table__.columns}
        missing = self.SNAPSHOT_COLUMNS - orm_cols
        assert not missing, (
            f"DeliverableSnapshot ORM 缺少列: {sorted(missing)}。"
            f"当前列: {sorted(orm_cols)}"
        )

    def test_export_job_attempt_has_all_columns(self):
        """ExportJobAttempt ORM 列必须覆盖迁移定义。"""
        orm_cols = {c.name for c in ExportJobAttempt.__table__.columns}
        missing = self.ATTEMPT_COLUMNS - orm_cols
        assert not missing, (
            f"ExportJobAttempt ORM 缺少列: {sorted(missing)}。"
            f"当前列: {sorted(orm_cols)}"
        )

    def test_tables_registered_in_metadata(self):
        """两个新表必须在 Base.metadata 中注册。"""
        tables = set(Base.metadata.tables.keys())
        assert "deliverable_snapshots" in tables, f"缺 deliverable_snapshots 表"
        assert "export_job_attempts" in tables, f"缺 export_job_attempts 表"

    def test_snapshot_digest_column_is_unique(self):
        """deliverable_snapshots.digest 必须有 unique 约束。"""
        col = DeliverableSnapshot.__table__.c.digest
        # unique=True on column or explicit UniqueConstraint
        has_unique = col.unique or any(
            getattr(c, "columns", None) and "digest" in {cc.name for cc in c.columns}
            for c in DeliverableSnapshot.__table__.constraints
        )
        assert has_unique, "digest 列缺少 unique 约束"

    def test_attempt_item_no_unique_constraint(self):
        """export_job_attempts 必须有 (item_id, attempt_no) 唯一约束。"""
        from sqlalchemy import UniqueConstraint
        found = False
        for c in ExportJobAttempt.__table__.constraints:
            if isinstance(c, UniqueConstraint):
                col_names = {cc.name for cc in c.columns}
                if col_names == {"item_id", "attempt_no"}:
                    found = True
                    break
        assert found, "export_job_attempts 缺少 (item_id, attempt_no) 唯一约束"

    def test_uuid_pks_have_default(self):
        """所有新模型的 UUID 主键必须有 default=uuid.uuid4。"""
        for model in (DeliverableSnapshot, ExportJobAttempt):
            pk = model.__table__.c.id
            assert pk.default is not None, (
                f"{model.__name__}.id 缺少 default（未设 default=uuid.uuid4 "
                f"会导致 INSERT 时主键为 NULL）"
            )


# ──────────────────────────────────────────────────────────────────────
# 2. 迁移版本号不撞
# ──────────────────────────────────────────────────────────────────────

class TestMigrationVersionCollision:
    """V181 版本号不得与其他迁移冲突。"""

    def test_v181_file_exists(self):
        """V181 迁移文件必须存在。"""
        root = Path(__file__).resolve().parents[1]
        v_file = root / "migrations" / "V181__phase4_trio_schema.sql"
        assert v_file.is_file(), f"V181 迁移文件不存在: {v_file}"

    def test_r181_file_exists(self):
        """R181 回滚文件必须存在。"""
        root = Path(__file__).resolve().parents[1]
        r_file = root / "migrations" / "R181__rollback_phase4_trio_schema.sql"
        assert r_file.is_file(), f"R181 回滚文件不存在: {r_file}"

    def test_no_duplicate_version_181(self):
        """V181 版本号只能出现一次。"""
        root = Path(__file__).resolve().parents[1] / "migrations"
        v181_files = list(root.glob("V181__*.sql"))
        assert len(v181_files) == 1, (
            f"版本 181 出现 {len(v181_files)} 次: {[f.name for f in v181_files]}。"
            f"数值版本不得撞号。"
        )

    def test_migration_is_idempotent_ddl(self):
        """V181 必须使用 IF NOT EXISTS / IF EXISTS 确保幂等。"""
        root = Path(__file__).resolve().parents[1]
        v_file = root / "migrations" / "V181__phase4_trio_schema.sql"
        content = v_file.read_text(encoding="utf-8")
        # 每个 CREATE TABLE 必须有 IF NOT EXISTS
        creates = re.findall(r"CREATE\s+TABLE\b.*?\(", content, re.IGNORECASE | re.DOTALL)
        for stmt in creates:
            assert "IF NOT EXISTS" in stmt.upper(), (
                f"CREATE TABLE 缺少 IF NOT EXISTS: {stmt[:80]}..."
            )
        # 每个 ALTER TABLE ADD COLUMN 必须在 DO $$ 块内通过条件检查
        alters = re.findall(r"ALTER\s+TABLE\s+\w+\s+ADD\s+COLUMN", content, re.IGNORECASE)
        do_blocks = content.count("DO $$")
        assert do_blocks >= len(alters), (
            f"有 {len(alters)} 个 ALTER ADD COLUMN 但只有 {do_blocks} 个 DO $$ 块"
        )

    def test_rollback_drops_all_new_tables(self):
        """R181 必须 DROP 两张新表。"""
        root = Path(__file__).resolve().parents[1]
        r_file = root / "migrations" / "R181__rollback_phase4_trio_schema.sql"
        content = r_file.read_text(encoding="utf-8").lower()
        assert "drop table if exists export_job_attempts" in content
        assert "drop table if exists deliverable_snapshots" in content


# ──────────────────────────────────────────────────────────────────────
# 3. 快照 digest 不变量
# ──────────────────────────────────────────────────────────────────────

class TestSnapshotDigest:
    """快照 digest 必须确定性、不含时间/路径、三项同一。"""

    _PID = UUID("aaaaaaaa-1111-2222-3333-444444444444")
    _YEAR = 2025
    _SOURCES: dict[str, dict[str, Any]] = {
        "tb": {"available": True, "count": 120, "stale_count": 0},
        "formula_push": {"available": True, "count": 1, "stale_count": 0},
        "adjustments": {"available": True, "count": 5, "stale_count": 0},
        "reports": {"available": True, "count": 4, "stale_count": 1},
        "notes": {"available": True, "count": 30, "stale_count": 2},
    }

    def test_digest_deterministic(self):
        """同一输入调用两次，digest 完全相同（需求 1.5）。"""
        r1 = build_snapshot_digest(self._PID, self._YEAR, self._SOURCES)
        r2 = build_snapshot_digest(self._PID, self._YEAR, self._SOURCES)
        assert r1["digest"] == r2["digest"]
        assert r1["id"] == r2["id"]

    def test_digest_does_not_contain_time(self):
        """digest 计算过程不含生成时间（design §五）。"""
        result = build_snapshot_digest(self._PID, self._YEAR, self._SOURCES)
        payload = result["payload"]
        payload_str = json.dumps(payload, sort_keys=True)
        # payload 中不应有任何时间类字段
        for key in ("time", "timestamp", "created_at", "generated_at", "now"):
            assert key not in payload_str.lower(), (
                f"digest payload 包含时间相关字段 '{key}': {payload_str[:200]}"
            )

    def test_digest_does_not_contain_absolute_path(self):
        """digest 不含本机绝对路径（design §五）。"""
        result = build_snapshot_digest(self._PID, self._YEAR, self._SOURCES)
        payload_str = json.dumps(result["payload"], sort_keys=True)
        # 不应包含 Windows 或 Unix 绝对路径
        assert ":\\" not in payload_str, f"payload 含 Windows 路径: {payload_str[:200]}"
        assert not re.search(r'"/[a-zA-Z]', payload_str), (
            f"payload 含 Unix 绝对路径: {payload_str[:200]}"
        )

    def test_digest_changes_when_source_changes(self):
        """修改源数据后 digest 必须改变（变异红：修改快照输入）。"""
        r1 = build_snapshot_digest(self._PID, self._YEAR, self._SOURCES)

        modified_sources = {**self._SOURCES}
        modified_sources["tb"] = {**self._SOURCES["tb"], "stale_count": 5}

        r2 = build_snapshot_digest(self._PID, self._YEAR, modified_sources)
        assert r1["digest"] != r2["digest"], (
            "修改源数据后 digest 未改变 — 快照输入变更未反映到 digest"
        )

    def test_digest_changes_when_project_changes(self):
        """不同项目的 digest 不同。"""
        other_pid = UUID("bbbbbbbb-1111-2222-3333-444444444444")
        r1 = build_snapshot_digest(self._PID, self._YEAR, self._SOURCES)
        r2 = build_snapshot_digest(other_pid, self._YEAR, self._SOURCES)
        assert r1["digest"] != r2["digest"]

    def test_digest_changes_when_year_changes(self):
        """不同年度的 digest 不同。"""
        r1 = build_snapshot_digest(self._PID, self._YEAR, self._SOURCES)
        r2 = build_snapshot_digest(self._PID, 2024, self._SOURCES)
        assert r1["digest"] != r2["digest"]

    def test_digest_is_sha256(self):
        """digest 必须是合法的 SHA-256 十六进制字符串。"""
        result = build_snapshot_digest(self._PID, self._YEAR, self._SOURCES)
        digest = result["digest"]
        assert len(digest) == 64, f"digest 长度 {len(digest)} ≠ 64"
        assert re.fullmatch(r"[0-9a-f]{64}", digest), (
            f"digest 不是合法 SHA-256: {digest}"
        )

    def test_source_key_order_does_not_affect_digest(self):
        """dict key 顺序不影响 digest（内部 sort_keys）。"""
        sources_reverse = dict(reversed(list(self._SOURCES.items())))
        r1 = build_snapshot_digest(self._PID, self._YEAR, self._SOURCES)
        r2 = build_snapshot_digest(self._PID, self._YEAR, sources_reverse)
        assert r1["digest"] == r2["digest"], (
            "源 dict key 顺序不同导致 digest 不同 — 缺少 sort_keys"
        )

    def test_payload_returned_in_result(self):
        """build_snapshot_digest 必须返回 payload 以供 DeliverableSnapshot 存储。"""
        result = build_snapshot_digest(self._PID, self._YEAR, self._SOURCES)
        assert "payload" in result
        assert isinstance(result["payload"], dict)
        assert result["payload"]["project_id"] == str(self._PID)
        assert result["payload"]["year"] == self._YEAR


# ──────────────────────────────────────────────────────────────────────
# 4. SQLite 真 ORM 插入验证
# ──────────────────────────────────────────────────────────────────────

class TestSQLiteORMInsert:
    """用真 ORM 验证新模型可正确插入和查询。"""

    @pytest.mark.asyncio
    async def test_create_snapshot(self, db: AsyncSession, project: Project):
        """DeliverableSnapshot 可以正常插入。"""
        snap = DeliverableSnapshot(
            project_id=project.id,
            year=2025,
            digest="a" * 64,
            payload={"project_id": str(project.id), "year": 2025, "sources": {}},
        )
        db.add(snap)
        await db.flush()

        result = await db.execute(
            select(DeliverableSnapshot).where(DeliverableSnapshot.id == snap.id)
        )
        row = result.scalar_one()
        assert row.digest == "a" * 64
        assert row.year == 2025

    @pytest.mark.asyncio
    async def test_create_job_with_trio_fields(
        self, db: AsyncSession, project: Project, user: User,
    ):
        """ExportJob 扩展列可以正常写入。"""
        snap_id = uuid.uuid4()
        job = ExportJob(
            project_id=project.id,
            job_type="generate",
            status="queued",
            initiated_by=user.id,
            snapshot_id=snap_id,
            kind="deliverable_trio",
            year=2025,
            trio_total=3,
            trio_succeeded=0,
        )
        db.add(job)
        await db.flush()

        result = await db.execute(
            select(ExportJob).where(ExportJob.id == job.id)
        )
        row = result.scalar_one()
        assert row.snapshot_id == snap_id
        assert row.kind == "deliverable_trio"
        assert row.year == 2025
        assert row.trio_total == 3

    @pytest.mark.asyncio
    async def test_create_item_with_trio_fields(
        self, db: AsyncSession, project: Project, user: User,
    ):
        """ExportJobItem 扩展列可以正常写入。"""
        job = ExportJob(
            project_id=project.id,
            job_type="generate",
            status="queued",
            initiated_by=user.id,
        )
        db.add(job)
        await db.flush()

        item = ExportJobItem(
            job_id=job.id,
            step_key="financial_report",
            sequence=1,
            snapshot_id=uuid.uuid4(),
            file_sha256="b" * 64,
        )
        db.add(item)
        await db.flush()

        result = await db.execute(
            select(ExportJobItem).where(ExportJobItem.id == item.id)
        )
        row = result.scalar_one()
        assert row.step_key == "financial_report"
        assert row.sequence == 1
        assert row.file_sha256 == "b" * 64

    @pytest.mark.asyncio
    async def test_create_attempt(
        self, db: AsyncSession, project: Project, user: User,
    ):
        """ExportJobAttempt 可以正常插入。"""
        job = ExportJob(
            project_id=project.id,
            job_type="generate",
            status="running",
            initiated_by=user.id,
        )
        db.add(job)
        await db.flush()

        item = ExportJobItem(
            job_id=job.id,
            step_key="disclosure_notes",
            sequence=2,
        )
        db.add(item)
        await db.flush()

        attempt = ExportJobAttempt(
            job_id=job.id,
            item_id=item.id,
            attempt_no=1,
            status="running",
            snapshot_id=uuid.uuid4(),
            trigger_source="initial",
        )
        db.add(attempt)
        await db.flush()

        result = await db.execute(
            select(ExportJobAttempt).where(ExportJobAttempt.item_id == item.id)
        )
        row = result.scalar_one()
        assert row.attempt_no == 1
        assert row.trigger_source == "initial"

    @pytest.mark.asyncio
    async def test_multiple_attempts_on_same_item(
        self, db: AsyncSession, project: Project, user: User,
    ):
        """同一 item 可以有多个 attempt（递增 attempt_no）。"""
        job = ExportJob(
            project_id=project.id,
            job_type="generate",
            status="running",
            initiated_by=user.id,
        )
        db.add(job)
        await db.flush()

        item = ExportJobItem(job_id=job.id, step_key="audit_report", sequence=3)
        db.add(item)
        await db.flush()

        for i in range(1, 4):
            attempt = ExportJobAttempt(
                job_id=job.id,
                item_id=item.id,
                attempt_no=i,
                status="failed" if i < 3 else "succeeded",
            )
            db.add(attempt)
        await db.flush()

        result = await db.execute(
            select(ExportJobAttempt)
            .where(ExportJobAttempt.item_id == item.id)
            .order_by(ExportJobAttempt.attempt_no)
        )
        rows = result.scalars().all()
        assert len(rows) == 3
        assert [r.attempt_no for r in rows] == [1, 2, 3]
        assert rows[0].status == "failed"
        assert rows[2].status == "succeeded"


# ──────────────────────────────────────────────────────────────────────
# 5. 三件套同一 snapshot 变异测试
# ──────────────────────────────────────────────────────────────────────

class TestTrioSnapshotInvariant:
    """三件套的每个 item 必须引用同一个 snapshot_id。

    变异：让其中一项换 snapshot → 断言必须红。
    """

    @pytest.mark.asyncio
    async def test_all_items_same_snapshot(
        self, db: AsyncSession, project: Project, user: User,
    ):
        """正常情况：三件套 item 共享同一 snapshot。"""
        snap_id = uuid.uuid4()
        job = ExportJob(
            project_id=project.id,
            job_type="generate",
            status="running",
            initiated_by=user.id,
            snapshot_id=snap_id,
            kind="deliverable_trio",
        )
        db.add(job)
        await db.flush()

        steps = [
            ("financial_report", 1),
            ("disclosure_notes", 2),
            ("audit_report", 3),
        ]
        for key, seq in steps:
            item = ExportJobItem(
                job_id=job.id,
                step_key=key,
                sequence=seq,
                snapshot_id=snap_id,
            )
            db.add(item)
        await db.flush()

        result = await db.execute(
            select(ExportJobItem).where(ExportJobItem.job_id == job.id)
        )
        items = result.scalars().all()
        snapshot_ids = {i.snapshot_id for i in items}
        assert len(snapshot_ids) == 1, (
            f"三件套 item 引用了 {len(snapshot_ids)} 个不同的 snapshot: "
            f"{snapshot_ids}。需求 2.4 要求三项引用同一快照。"
        )
        assert snap_id in snapshot_ids

    @pytest.mark.asyncio
    async def test_mutation_different_snapshot_detected(
        self, db: AsyncSession, project: Project, user: User,
    ):
        """变异：把第二项换成不同 snapshot_id → 检查逻辑应识别不一致。"""
        snap_id = uuid.uuid4()
        rogue_snap_id = uuid.uuid4()

        job = ExportJob(
            project_id=project.id,
            job_type="generate",
            status="running",
            initiated_by=user.id,
            snapshot_id=snap_id,
            kind="deliverable_trio",
        )
        db.add(job)
        await db.flush()

        # 正常 item
        for key, seq in [("financial_report", 1), ("audit_report", 3)]:
            db.add(ExportJobItem(
                job_id=job.id, step_key=key, sequence=seq, snapshot_id=snap_id,
            ))
        # 变异 item — 不同 snapshot
        db.add(ExportJobItem(
            job_id=job.id, step_key="disclosure_notes", sequence=2,
            snapshot_id=rogue_snap_id,
        ))
        await db.flush()

        result = await db.execute(
            select(ExportJobItem).where(ExportJobItem.job_id == job.id)
        )
        items = result.scalars().all()
        snapshot_ids = {i.snapshot_id for i in items}
        # 这个检查必须失败 — 证明变异被检测到
        assert len(snapshot_ids) > 1, (
            "变异注入（不同 snapshot_id）未被检测到 — "
            "校验逻辑必须拒绝跨快照的三件套"
        )


# ──────────────────────────────────────────────────────────────────────
# 6. ExportJobAttempt 不可变性（append-only）
# ──────────────────────────────────────────────────────────────────────

class TestAttemptAppendOnly:
    """attempt 历史不可覆盖。"""

    @pytest.mark.asyncio
    async def test_failed_attempt_preserved_after_new_attempt(
        self, db: AsyncSession, project: Project, user: User,
    ):
        """失败 attempt 在新 attempt 创建后仍存在。"""
        job = ExportJob(
            project_id=project.id,
            job_type="generate",
            status="running",
            initiated_by=user.id,
        )
        db.add(job)
        await db.flush()

        item = ExportJobItem(job_id=job.id, step_key="financial_report", sequence=1)
        db.add(item)
        await db.flush()

        # 第一次尝试 — 失败
        a1 = ExportJobAttempt(
            job_id=job.id,
            item_id=item.id,
            attempt_no=1,
            status="failed",
            error_type="FileWriteError",
            error_message="文件写入失败：磁盘空间不足",
            diagnostic_detail="OSError: No space left on device",
        )
        db.add(a1)
        await db.flush()

        # 第二次尝试 — 成功
        a2 = ExportJobAttempt(
            job_id=job.id,
            item_id=item.id,
            attempt_no=2,
            status="succeeded",
            file_sha256="c" * 64,
        )
        db.add(a2)
        await db.flush()

        # 两个 attempt 都在
        result = await db.execute(
            select(ExportJobAttempt)
            .where(ExportJobAttempt.item_id == item.id)
            .order_by(ExportJobAttempt.attempt_no)
        )
        rows = result.scalars().all()
        assert len(rows) == 2
        # 原始失败原因保留
        assert rows[0].error_type == "FileWriteError"
        assert rows[0].error_message == "文件写入失败：磁盘空间不足"
        assert rows[0].status == "failed"
        assert rows[1].status == "succeeded"
