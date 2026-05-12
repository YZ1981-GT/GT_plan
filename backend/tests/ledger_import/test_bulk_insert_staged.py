"""S7-5: bulk_insert_staged 集成测试（针对 S7-2 通用函数）。

覆盖：
- 字段自省：converter 输出的 row 可能含目标表没有的字段（如 aux_type
  在 TbBalance 上不存在），bulk_insert_staged 必须过滤掉
- 公共字段注入：id/project_id/year/dataset_id/is_deleted 必须正确写入
- NOT NULL 兜底：company_code/currency_code 缺失时用默认值
- 分 chunk：大数据量切片不超 SQLite 参数上限
- 空 rows 安全返回
"""
from __future__ import annotations

import json as _json_mod
import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.models.audit_platform_models import TbAuxBalance, TbBalance, TbLedger
from app.models.base import Base
from app.models import audit_platform_models  # noqa: F401
from app.services.ledger_import.writer import bulk_insert_staged


def _json_dumps(obj):
    def default(o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        return str(o)
    return _json_mod.dumps(obj, default=default, ensure_ascii=False)


_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:", echo=False,
    json_serializer=_json_dumps,
)


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, expire_on_commit=False)
    async with factory() as s:
        yield s


PID = uuid.uuid4()
DID = uuid.uuid4()
YEAR = 2025


@pytest.mark.asyncio
async def test_bulk_insert_balance_basic(db_session):
    """基础：正常 row 插入 TbBalance。"""
    rows = [
        {
            "account_code": "1001",
            "account_name": "库存现金",
            "opening_balance": Decimal("100.00"),
            "closing_balance": Decimal("120.00"),
        },
        {
            "account_code": "1002",
            "account_name": "银行存款",
            "opening_balance": Decimal("5000.00"),
            "closing_balance": Decimal("4800.00"),
        },
    ]
    count = await bulk_insert_staged(
        lambda: _session_ctx(db_session), TbBalance, rows,
        project_id=PID, year=YEAR, dataset_id=DID,
    )
    assert count == 2


class _session_ctx:
    """让 bulk_insert_staged 可接受已有 session 的适配器。"""
    def __init__(self, session):
        self.session = session
    async def __aenter__(self):
        return self.session
    async def __aexit__(self, *args):
        pass


@pytest.mark.asyncio
async def test_bulk_insert_filters_extra_fields(db_session):
    """字段自省：converter 输出的无关字段（如 _aux_dim_str）应被过滤。"""
    rows = [
        {
            "account_code": "1001",
            "account_name": "库存现金",
            # 下面这些 TbBalance 没有，应被过滤
            "aux_type": "客户",
            "aux_code": "C001",
            "_aux_dim_str": "some internal",
            "voucher_no": "应忽略",
        },
    ]
    count = await bulk_insert_staged(
        lambda: _session_ctx(db_session), TbBalance, rows,
        project_id=PID, year=YEAR, dataset_id=DID,
    )
    assert count == 1

    # 查数据库确认无异常（字段过滤成功意味着 INSERT 不报错）
    result = await db_session.execute(
        sa.text("SELECT account_code FROM tb_balance")
    )
    assert result.scalar() == "1001"


@pytest.mark.asyncio
async def test_bulk_insert_injects_common_fields(db_session):
    """公共字段注入：id/project_id/year/dataset_id/is_deleted 自动填充。"""
    rows = [{"account_code": "1001", "account_name": "现金"}]
    await bulk_insert_staged(
        lambda: _session_ctx(db_session), TbBalance, rows,
        project_id=PID, year=YEAR, dataset_id=DID, is_deleted=True,
    )

    row = (await db_session.execute(
        sa.text("SELECT project_id, year, dataset_id, is_deleted FROM tb_balance LIMIT 1")
    )).first()
    # SQLite UUID 存 hex 无连字符
    pid_hex = str(PID).replace("-", "")
    did_hex = str(DID).replace("-", "")
    assert row[0] == pid_hex
    assert row[1] == YEAR
    assert row[2] == did_hex
    assert row[3] in (1, True)  # SQLite boolean 可能是 1


@pytest.mark.asyncio
async def test_bulk_insert_not_null_fallback(db_session):
    """company_code 缺失时用 default_company_code 兜底。"""
    rows = [{"account_code": "1001", "account_name": "现金"}]  # 无 company_code
    await bulk_insert_staged(
        lambda: _session_ctx(db_session), TbBalance, rows,
        project_id=PID, year=YEAR, dataset_id=DID,
        default_company_code="UNIT_TEST_CO",
    )
    row = (await db_session.execute(
        sa.text("SELECT company_code FROM tb_balance LIMIT 1")
    )).first()
    assert row[0] == "UNIT_TEST_CO"


@pytest.mark.asyncio
async def test_bulk_insert_empty_rows(db_session):
    """空 rows 直接返回 0 不报错。"""
    count = await bulk_insert_staged(
        lambda: _session_ctx(db_session), TbBalance, [],
        project_id=PID, year=YEAR, dataset_id=DID,
    )
    assert count == 0


@pytest.mark.asyncio
async def test_bulk_insert_chunk_size(db_session):
    """大批量按 chunk 拆分。"""
    # SQLite 参数上限 999，25 列 × 40 行 = 1000 → 刚好触发分块
    rows = [
        {"account_code": f"{i:04d}", "account_name": f"科目{i}"}
        for i in range(80)
    ]
    count = await bulk_insert_staged(
        lambda: _session_ctx(db_session), TbBalance, rows,
        project_id=PID, year=YEAR, dataset_id=DID,
        chunk_size=30,  # 强制拆 3 批 (30+30+20)
    )
    assert count == 80

    total = (await db_session.execute(
        sa.text("SELECT COUNT(*) FROM tb_balance")
    )).scalar()
    assert total == 80


@pytest.mark.asyncio
async def test_bulk_insert_aux_balance_with_aux_fields(db_session):
    """TbAuxBalance 接受 aux_type/aux_code/aux_name 且不过滤。"""
    rows = [
        {
            "account_code": "1122",
            "account_name": "应收账款",
            "aux_type": "客户",
            "aux_code": "C001",
            "aux_name": "甲公司",
            "closing_balance": Decimal("5000"),
        },
        {
            "account_code": "1122",
            "account_name": "应收账款",
            "aux_type": "客户",
            "aux_code": None,  # None 允许
            "aux_name": None,
            "closing_balance": Decimal("3000"),
        },
    ]
    count = await bulk_insert_staged(
        lambda: _session_ctx(db_session), TbAuxBalance, rows,
        project_id=PID, year=YEAR, dataset_id=DID,
    )
    assert count == 2

    # aux_code 为 None 的行确实存 NULL 不是 ''
    null_count = (await db_session.execute(
        sa.text("SELECT COUNT(*) FROM tb_aux_balance WHERE aux_code IS NULL")
    )).scalar()
    assert null_count == 1


@pytest.mark.asyncio
async def test_bulk_insert_ledger_with_voucher_fields(db_session):
    """TbLedger 接受 voucher_date/voucher_no/summary/preparer。"""
    rows = [
        {
            "account_code": "1001",
            "account_name": "现金",
            "voucher_date": date(2025, 1, 15),
            "voucher_no": "记-001",
            "voucher_type": "记",
            "debit_amount": Decimal("100"),
            "summary": "测试收款",
            "preparer": "张三",
        },
    ]
    count = await bulk_insert_staged(
        lambda: _session_ctx(db_session), TbLedger, rows,
        project_id=PID, year=YEAR, dataset_id=DID,
    )
    assert count == 1
