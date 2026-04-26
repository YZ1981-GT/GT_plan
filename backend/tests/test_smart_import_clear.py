"""smart_import_streaming 清理旧数据逻辑测试。"""

import uuid

import pytest
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.audit_platform_models import (
    ImportBatch,
    ImportStatus,
    TbAuxBalance,
    TbAuxLedger,
    TbBalance,
    TbLedger,
)
from app.models.core import Project, ProjectStatus, ProjectType
from app.services.smart_import_engine import _clear_project_year_tables

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest.mark.asyncio
async def test_clear_project_year_tables_soft_deletes_rows_and_rolls_batches():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as db_session:
        from datetime import date

        project_id = uuid.uuid4()
        batch_old = uuid.uuid4()
        batch_other_year = uuid.uuid4()

        db_session.add(Project(
            id=project_id,
            name="smart-import-clear-test",
            client_name="client",
            project_type=ProjectType.annual,
            status=ProjectStatus.planning,
            created_by=uuid.uuid4(),
        ))

        db_session.add_all([
            ImportBatch(
                id=batch_old,
                project_id=project_id,
                year=2025,
                source_type="smart_import",
                file_name="old",
                data_type="tb_balance",
                status=ImportStatus.completed,
            ),
            ImportBatch(
                id=batch_other_year,
                project_id=project_id,
                year=2024,
                source_type="smart_import",
                file_name="other-year",
                data_type="tb_balance",
                status=ImportStatus.completed,
            ),
        ])

        db_session.add_all([
            TbBalance(project_id=project_id, year=2025, company_code="001", account_code="1001", import_batch_id=batch_old),
            TbLedger(project_id=project_id, year=2025, company_code="001", voucher_date=date(2025, 1, 1), voucher_no="1", account_code="1001", import_batch_id=batch_old),
            TbAuxBalance(project_id=project_id, year=2025, company_code="001", account_code="1001", aux_type="部门", import_batch_id=batch_old),
            TbAuxLedger(project_id=project_id, year=2025, company_code="001", account_code="1001", import_batch_id=batch_old),
            TbBalance(project_id=project_id, year=2024, company_code="001", account_code="1001", import_batch_id=batch_other_year),
        ])
        await db_session.commit()

        await _clear_project_year_tables(project_id, 2025, db_session)
        await db_session.commit()

        tb_2025 = (await db_session.execute(
            TbBalance.__table__.select().where(TbBalance.project_id == project_id, TbBalance.year == 2025)
        )).mappings().all()
        assert tb_2025 and all(r["is_deleted"] for r in tb_2025)

        tb_2024 = (await db_session.execute(
            TbBalance.__table__.select().where(TbBalance.project_id == project_id, TbBalance.year == 2024)
        )).mappings().all()
        assert tb_2024 and all(not r["is_deleted"] for r in tb_2024)

        batch_old_row = (await db_session.execute(
            ImportBatch.__table__.select().where(ImportBatch.id == batch_old)
        )).mappings().one()
        batch_other_year_row = (await db_session.execute(
            ImportBatch.__table__.select().where(ImportBatch.id == batch_other_year)
        )).mappings().one()
        assert batch_old_row["status"] == ImportStatus.rolled_back
        assert batch_other_year_row["status"] == ImportStatus.completed
