"""D 循环 aux 归集测试用真 SQLite 库：只建 ``tb_aux_balance`` / ``ledger_datasets`` 两表。

共享件 ``aggregate_d_cycle_aux`` → ``aggregate_aux_by_name_ex`` 的 ORM 查询、active dataset 过滤与
维度锁定都原样执行；报表映射 / 科目表 / account_mapping 等表不建 ⇒ 科目解析按设计 fail-open
回落到兜底码（D6 = 1141）。spec formula-fetch-and-wp-generation-defect-closure R7.2。
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from decimal import Decimal

from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.sql import sqltypes

from app.models.audit_platform_models import TbAuxBalance
from app.models.dataset_models import LedgerDataset

# SQLite 建表：JSONB / UUID 按通用类型编译（与 tests/test_wp_formula_three_type.py 等同款）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid


def aux_row(name, *, project_id, opening, closing, year=2025, code="1141", aux_type="客户",
            debit=0, credit=0, deleted=False) -> TbAuxBalance:
    return TbAuxBalance(
        project_id=project_id, year=year, company_code="001", account_code=code,
        aux_type=aux_type, aux_name=name, opening_balance=Decimal(str(opening)),
        debit_amount=Decimal(str(debit)), credit_amount=Decimal(str(credit)),
        closing_balance=Decimal(str(closing)), is_deleted=deleted,
    )


@contextmanager
def _pg_like_uuid_binds():
    """UUID 列绑定参数按 PG 语义接受字符串。

    生产代码给 UUID 列传 ``str(project_id)``（PG 原生 UUID 直接收字符串）；SQLite 方言的 UUID 绑定
    只收 ``uuid.UUID``（取 ``value.hex``），字符串会在共享件里抛错并被 fail-open 吞成空结果。
    测试期间把字符串先转 ``uuid.UUID`` —— 只放宽类型，不改值；退出即还原。
    """
    original = sqltypes.Uuid.bind_processor

    def bind_processor(self, dialect):
        process = original(self, dialect)
        if process is None:
            return None

        def _process(value):
            return process(uuid.UUID(value) if isinstance(value, str) else value)

        return _process

    sqltypes.Uuid.bind_processor = bind_processor
    try:
        yield
    finally:
        sqltypes.Uuid.bind_processor = original


async def run_on_aux_rows(rows, fn):
    """建库 → 落库并提交（共享件降级路径会 rollback）→ ``await fn(db)`` → 释放引擎。"""
    with _pg_like_uuid_binds():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        try:
            async with engine.begin() as conn:
                for table in (TbAuxBalance.__table__, LedgerDataset.__table__):
                    await conn.run_sync(lambda sc, t=table: t.create(sc, checkfirst=True))
            factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with factory() as db:
                db.add_all(list(rows))
                await db.commit()
                return await fn(db)
        finally:
            await engine.dispose()
