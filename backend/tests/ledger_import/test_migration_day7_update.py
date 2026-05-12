"""F18 / Sprint 11.9: Day 7 一次性 UPDATE 迁移测试

对应迁移文件：
  backend/alembic/versions/view_refactor_cleanup_old_deleted_20260517.py

迁移语义（三阶段部署路径 / ADR-002）：
- Day 0：部署 B' 代码，新写入 is_deleted=false，查询走 get_active_filter
- Day 7：一次性把所有 **active** dataset 对应的 Tb* 物理行 is_deleted=true → false，
  统一新老数据语义
- Day 30：DROP INDEX idx_tb_*_activate_staged

迁移正文是 PG 专用的 PL/pgSQL DO 块（分块 UPDATE + pg_sleep），SQLite 下直接
return 不执行。本测试采用"源代码检查 + 功能模拟"两层策略：

1. **源代码检查**：验证迁移文件结构、revision、表名、分块语义正确
2. **功能模拟**：用等价 SQL 在 SQLite 上构造相同数据 + 跑等价 UPDATE，
   断言行为符合预期（并验证 idempotency）
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base
import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.dataset_models  # noqa: F401
from app.models.audit_platform_models import TbBalance, TbLedger
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.services.dataset_service import DatasetService


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "view_refactor_cleanup_old_deleted_20260517.py"
)


# ===========================================================================
# Part A: 源代码结构检查
# ===========================================================================


@pytest.fixture(scope="module")
def migration_source() -> str:
    assert MIGRATION_PATH.exists(), f"迁移文件不存在：{MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


class TestMigrationSource:
    def test_revision_id(self, migration_source: str):
        assert 'revision = "view_refactor_cleanup_old_deleted_20260517"' in migration_source

    def test_down_revision(self, migration_source: str):
        assert 'down_revision = "view_refactor_activate_index_20260510"' in migration_source

    def test_has_upgrade_and_downgrade(self, migration_source: str):
        assert "def upgrade(" in migration_source
        assert "def downgrade(" in migration_source

    def test_targets_four_tb_tables(self, migration_source: str):
        # 4 张表都在 TABLES 列表
        for tbl in ("tb_balance", "tb_aux_balance", "tb_ledger", "tb_aux_ledger"):
            assert tbl in migration_source, f"迁移未覆盖 {tbl}"

    def test_chunked_update_semantics(self, migration_source: str):
        # 关键 PL/pgSQL 结构
        assert "UPDATE" in migration_source
        assert "SET is_deleted = false" in migration_source
        assert "is_deleted = true" in migration_source
        assert "ledger_datasets" in migration_source
        assert "status = 'active'" in migration_source
        # 分块 + 小睡
        assert "LIMIT" in migration_source
        assert "pg_sleep" in migration_source

    def test_only_runs_on_postgres(self, migration_source: str):
        assert 'dialect != "postgresql"' in migration_source

    def test_downgrade_is_noop_by_design(self, migration_source: str):
        # downgrade 是空实现（docstring 说明不可降级）
        downgrade_section = migration_source.split("def downgrade")[1]
        # 剥离 docstring 后检查真实代码；只允许注释/pass 结构
        # 移除多行 docstring 粗暴法：按 """ 拆分取非 docstring 部分
        code_parts = downgrade_section.split('"""')
        # code_parts[0] = 签名 + 起始 docstring
        # code_parts[1] = docstring 内容
        # code_parts[2] = docstring 结束后的实际代码
        assert len(code_parts) >= 3, "downgrade 应有 docstring 形式的说明"
        actual_code = code_parts[2]
        for forbidden in ("op.execute", "UPDATE", "ALTER TABLE"):
            assert forbidden not in actual_code, (
                f"downgrade 不应包含破坏性操作 {forbidden}（docstring 允许提及）"
            )
        # 必须是 pass（或等价）
        assert "pass" in actual_code


# ===========================================================================
# Part B: SQLite 环境下的 no-op 行为
# ===========================================================================


class TestMigrationOnSqlite:
    def test_upgrade_on_sqlite_is_noop(self, tmp_path):
        """直接 import 迁移模块并在 SQLite 环境下 monkey-patch op.get_bind，
        断言 upgrade() 不抛异常且不执行任何 UPDATE。"""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "view_refactor_cleanup_old_deleted_20260517",
            MIGRATION_PATH,
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        from alembic import op
        from sqlalchemy import create_engine

        sqlite_engine = create_engine(
            f"sqlite:///{tmp_path / 'test.db'}"
        )
        with sqlite_engine.connect() as conn:
            # 伪造 op 上下文
            from alembic.runtime.migration import MigrationContext

            mc = MigrationContext.configure(connection=conn)

            # 用 MigrateOperations + monkey patch 方式 — 更安全直接 patch get_bind
            from unittest.mock import patch

            with patch.object(op, "get_bind", return_value=conn), \
                 patch.object(op, "execute") as mock_execute:
                module.upgrade()
                # SQLite 分支直接 return，不应调 op.execute
                assert mock_execute.call_count == 0, (
                    "SQLite 环境下 Day 7 迁移应 return，不执行 op.execute"
                )


# ===========================================================================
# Part C: 功能模拟 — 等价 SQL 在 SQLite 上验证 UPDATE 语义 + idempotency
# ===========================================================================


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _simulate_day7_flip(db: AsyncSession) -> int:
    """在 SQLite 上模拟迁移等价 UPDATE（分块逻辑简化为一次性）。

    Returns:
        affected row count
    """
    total_affected = 0
    active_ids_subq = (
        sa.select(LedgerDataset.id).where(LedgerDataset.status == DatasetStatus.active)
    ).scalar_subquery()

    for tbl_model in (TbBalance, TbLedger):
        # aux_balance/aux_ledger 省略（同样的模式）
        result = await db.execute(
            sa.update(tbl_model.__table__)
            .where(
                tbl_model.__table__.c.is_deleted == sa.true(),
                tbl_model.__table__.c.dataset_id.in_(active_ids_subq),
            )
            .values(is_deleted=False)
        )
        total_affected += result.rowcount or 0
    await db.commit()
    return total_affected


@pytest.mark.asyncio
async def test_day7_flips_active_dataset_rows_to_false(db_session: AsyncSession):
    """场景模拟：Day 0-6 期间，active dataset 的老数据物理行 is_deleted=true
    （B' 架构上线前写入的老数据），Day 7 一次性 UPDATE 为 false。"""
    project_id = uuid.uuid4()
    year = 2024

    # 建 active dataset
    ds = await DatasetService.create_staged(
        db_session, project_id=project_id, year=year,
    )
    await DatasetService.activate(db_session, ds.id)

    # 写入 3 行老数据（is_deleted=true） + 2 行新数据（is_deleted=false）
    for i in range(3):
        db_session.add(TbBalance(
            id=uuid.uuid4(),
            project_id=project_id, year=year, dataset_id=ds.id,
            company_code="001", account_code=f"OLD{i}",
            currency_code="CNY", is_deleted=True,
        ))
    for i in range(2):
        db_session.add(TbBalance(
            id=uuid.uuid4(),
            project_id=project_id, year=year, dataset_id=ds.id,
            company_code="001", account_code=f"NEW{i}",
            currency_code="CNY", is_deleted=False,
        ))
    await db_session.commit()

    # 迁移前：3 行 is_deleted=true
    before_true = (
        await db_session.execute(
            sa.select(sa.func.count())
            .select_from(TbBalance)
            .where(
                TbBalance.dataset_id == ds.id,
                TbBalance.is_deleted == sa.true(),
            )
        )
    ).scalar_one()
    assert before_true == 3

    # 执行 Day 7 等价 UPDATE
    affected = await _simulate_day7_flip(db_session)
    assert affected == 3

    # 迁移后：所有行 is_deleted=false
    after_true = (
        await db_session.execute(
            sa.select(sa.func.count())
            .select_from(TbBalance)
            .where(
                TbBalance.dataset_id == ds.id,
                TbBalance.is_deleted == sa.true(),
            )
        )
    ).scalar_one()
    assert after_true == 0

    after_total = (
        await db_session.execute(
            sa.select(sa.func.count())
            .select_from(TbBalance)
            .where(TbBalance.dataset_id == ds.id)
        )
    ).scalar_one()
    assert after_total == 5  # 3 翻转 + 2 保持


@pytest.mark.asyncio
async def test_day7_is_idempotent(db_session: AsyncSession):
    """第二次跑 UPDATE 不应再翻转任何行（幂等）。"""
    project_id = uuid.uuid4()
    year = 2024

    ds = await DatasetService.create_staged(
        db_session, project_id=project_id, year=year,
    )
    await DatasetService.activate(db_session, ds.id)

    for i in range(4):
        db_session.add(TbBalance(
            id=uuid.uuid4(),
            project_id=project_id, year=year, dataset_id=ds.id,
            company_code="001", account_code=f"OLD{i}",
            currency_code="CNY", is_deleted=True,
        ))
    await db_session.commit()

    first_affected = await _simulate_day7_flip(db_session)
    assert first_affected == 4

    # 第二次跑：应 0 行受影响
    second_affected = await _simulate_day7_flip(db_session)
    assert second_affected == 0, "Day 7 迁移必须幂等，第二次跑不应再翻转"


@pytest.mark.asyncio
async def test_day7_does_not_flip_superseded_or_rolled_back(
    db_session: AsyncSession,
):
    """非 active dataset（superseded/rolled_back）的 is_deleted=true 行不应被翻转。"""
    project_id = uuid.uuid4()
    year = 2024

    # V1 → superseded，V2 → active（V1 被 V2 取代）
    v1 = await DatasetService.create_staged(
        db_session, project_id=project_id, year=year,
    )
    await DatasetService.activate(db_session, v1.id)
    v2 = await DatasetService.create_staged(
        db_session, project_id=project_id, year=year,
    )
    await DatasetService.activate(db_session, v2.id)  # V1 自动 superseded

    # V1 写 2 行老数据 is_deleted=true（不应被翻转）
    # V2 写 3 行老数据 is_deleted=true（**应**被翻转）
    for i in range(2):
        db_session.add(TbBalance(
            id=uuid.uuid4(),
            project_id=project_id, year=year, dataset_id=v1.id,
            company_code="001", account_code=f"V1-{i}",
            currency_code="CNY", is_deleted=True,
        ))
    for i in range(3):
        db_session.add(TbBalance(
            id=uuid.uuid4(),
            project_id=project_id, year=year, dataset_id=v2.id,
            company_code="001", account_code=f"V2-{i}",
            currency_code="CNY", is_deleted=True,
        ))
    await db_session.commit()

    await _simulate_day7_flip(db_session)

    # V1 行仍 is_deleted=true
    v1_true = (
        await db_session.execute(
            sa.select(sa.func.count())
            .select_from(TbBalance)
            .where(
                TbBalance.dataset_id == v1.id,
                TbBalance.is_deleted == sa.true(),
            )
        )
    ).scalar_one()
    assert v1_true == 2, "superseded dataset 的行不应被翻转"

    # V2 行全 is_deleted=false
    v2_true = (
        await db_session.execute(
            sa.select(sa.func.count())
            .select_from(TbBalance)
            .where(
                TbBalance.dataset_id == v2.id,
                TbBalance.is_deleted == sa.true(),
            )
        )
    ).scalar_one()
    assert v2_true == 0
