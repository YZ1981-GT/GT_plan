"""V215：客户科目按 dataset 版本化；DDL 在回滚事务内演练。"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

pytestmark = pytest.mark.pg_only
ROOT = Path(__file__).resolve().parents[1]
V215 = ROOT / "migrations/V215__account_chart_dataset_versioning.sql"
R215 = ROOT / "migrations/R215__rollback_account_chart_dataset_versioning.sql"


async def _run_sql(conn, path: Path) -> None:
    body = "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )
    for statement in body.split(";"):
        sql = statement.strip()
        if sql:
            await conn.execute(sa.text(sql))


@pytest.mark.asyncio
async def test_v215_allows_dataset_versions_and_r215_fails_closed_on_duplicates():
    if not str(settings.DATABASE_URL).startswith("postgresql"):
        pytest.skip("需要真实 PostgreSQL")
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as conn:
        tx = await conn.begin()
        try:
            project_id = await conn.scalar(sa.text(
                "SELECT id FROM projects WHERE client_name LIKE '【测试】%' LIMIT 1"
            ))
            if project_id is None:
                pytest.skip("没有【测试】项目")
            await _run_sql(conn, V215)
            names = set((await conn.execute(sa.text(
                "SELECT indexname FROM pg_indexes WHERE tablename='account_chart'"
            ))).scalars())
            assert "uq_account_chart_project_code_source" not in names
            assert {
                "uq_account_chart_project_dataset_code_source",
                "uq_account_chart_project_code_source_legacy",
            } <= names

            code = f"T{uuid.uuid4().hex[:10]}"
            common = {
                "pid": project_id,
                "code": code,
                "name": "【测试】版本化客户科目",
                "d1": uuid.uuid4(),
                "d2": uuid.uuid4(),
            }
            await conn.execute(sa.text(
                "INSERT INTO account_chart "
                "(id,project_id,account_code,account_name,direction,level,category,source,dataset_id,is_deleted) "
                "VALUES (gen_random_uuid(),:pid,:code,:name,'debit',1,'asset','client',:d1,false),"
                "(gen_random_uuid(),:pid,:code,:name,'debit',1,'asset','client',:d2,false)"
            ), common)
            assert await conn.scalar(sa.text(
                "SELECT count(*) FROM account_chart WHERE project_id=:pid AND account_code=:code AND is_deleted=false"
            ), common) == 2

            savepoint = await conn.begin_nested()
            with pytest.raises(sa.exc.IntegrityError, match="uq_account_chart_project_code_source"):
                await _run_sql(conn, R215)
            await savepoint.rollback()
            names = set((await conn.execute(sa.text(
                "SELECT indexname FROM pg_indexes WHERE tablename='account_chart'"
            ))).scalars())
            assert "uq_account_chart_project_code_source" not in names
            assert "uq_account_chart_project_dataset_code_source" in names
        finally:
            await tx.rollback()
    await engine.dispose()
