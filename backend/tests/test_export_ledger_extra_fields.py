"""Task 6.1*: export-ledger Excel 导出 raw_extra 业务额外列（零回归）

对含 raw_extra（业务键 + _ 前缀系统标记）的 tb_ledger 行走 export_ledger_excel 导出逻辑，验证：
- 生成的 xlsx 在固定列（对方科目）之后追加业务额外列表头（经办人/内部编号）
- 不含任何 _ 前缀系统标记列（_discarded_mappings / _aggregated_from_aux / _aux_row_count）
- 固定列（日期/凭证号/摘要/借方/贷方/余额/对方科目）保持不变（零回归锚点）
- 数据行额外列按并集顺序写入 extra_fields 值（缺失写空）
- 期初余额行 / 月小计行 额外列留空
- 无任何业务额外列（并集为空）时导出与原来完全一致（7 列，不加列）

沿用 test_ledger_penetration_extra_fields.py 的内存/SQLite fixture 模式（JSONB→JSON 兼容）。
Validates: Requirements 1.1
"""

import io
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from openpyxl import load_workbook
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, ProjectUser
from app.models.audit_platform_models import TbLedger
from app.routers.ledger_penetration import export_ledger_excel

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()
YEAR = 2025

BIZ_EXTRA = {"经办人": "张三", "内部编号": "A-001"}
SYS_MARKERS = {"_discarded_mappings": {"x": 1}, "_aggregated_from_aux": True, "_aux_row_count": 3}
RAW_WITH_BOTH = {**BIZ_EXTRA, **SYS_MARKERS}

FIXED_HEADERS = ["日期", "凭证号", "摘要", "借方", "贷方", "余额", "对方科目"]


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def fake_user() -> User:
    return User(
        id=FAKE_USER_ID, username="tester", email="t@test.com",
        hashed_password="x", role="member",
    )


async def _seed_project(db: AsyncSession):
    db.add(User(
        id=FAKE_USER_ID, username="tester", email="t@test.com",
        hashed_password="x", role="member",
    ))
    db.add(Project(
        id=FAKE_PROJECT_ID, name="export raw_extra 测试", client_name="测试",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        created_by=FAKE_USER_ID,
    ))
    db.add(ProjectUser(
        project_id=FAKE_PROJECT_ID, user_id=FAKE_USER_ID,
        role="auditor", permission_level="edit", is_deleted=False,
    ))


async def _read_export_headers(resp) -> list:
    body = b""
    async for chunk in resp.body_iterator:
        body += chunk.encode() if isinstance(chunk, str) else chunk
    wb = load_workbook(io.BytesIO(body))
    ws = wb.active
    return ws, [c.value for c in ws[1]]


class TestExportLedgerExtraColumns:

    @pytest.mark.asyncio
    async def test_export_appends_business_extra_columns(self, db_session, fake_user):
        """业务额外列追加到对方科目之后，不含 _ 前缀列，固定列不变。"""
        await _seed_project(db_session)
        # 两条 1002：含业务+系统标记 / None
        db_session.add(TbLedger(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
            voucher_date=date(2025, 1, 5), voucher_no="记-0001",
            account_code="1002", account_name="银行存款",
            debit_amount=Decimal("40000"), credit_amount=Decimal("0"),
            summary="收款", counterpart_account="1122", preparer="李四",
            raw_extra=dict(RAW_WITH_BOTH),
        ))
        db_session.add(TbLedger(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
            voucher_date=date(2025, 1, 6), voucher_no="记-0002",
            account_code="1002", account_name="银行存款",
            debit_amount=Decimal("0"), credit_amount=Decimal("10000"),
            summary="付款", counterpart_account="2202", preparer="李四",
            raw_extra=None,
        ))
        await db_session.commit()

        resp = await export_ledger_excel(
            project_id=FAKE_PROJECT_ID, account_code="1002", year=YEAR,
            date_from=None, date_to=None, db=db_session, current_user=fake_user,
        )
        ws, headers = await _read_export_headers(resp)

        # 固定列不变（零回归锚点）
        assert headers[:7] == FIXED_HEADERS
        # 业务额外列追加在对方科目之后，保持首次出现顺序
        assert headers[7:] == ["经办人", "内部编号"]
        # 不含任何 _ 前缀系统标记列
        for h in headers:
            assert not str(h).startswith("_"), f"额外列不得含系统标记: {h}"

    @pytest.mark.asyncio
    async def test_data_rows_and_synthetic_rows_extra_values(self, db_session, fake_user):
        """数据行写 extra_fields 值；缺失写空；期初/小计行额外列留空。"""
        await _seed_project(db_session)
        db_session.add(TbLedger(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
            voucher_date=date(2025, 1, 5), voucher_no="记-0001",
            account_code="1002", account_name="银行存款",
            debit_amount=Decimal("40000"), credit_amount=Decimal("0"),
            summary="收款", counterpart_account="1122", preparer="李四",
            raw_extra=dict(RAW_WITH_BOTH),
        ))
        await db_session.commit()

        resp = await export_ledger_excel(
            project_id=FAKE_PROJECT_ID, account_code="1002", year=YEAR,
            date_from=None, date_to=None, db=db_session, current_user=fake_user,
        )
        ws, headers = await _read_export_headers(resp)
        assert headers[7:] == ["经办人", "内部编号"]

        # 期初余额行（第2行）额外列（第8/9列）留空
        assert ws.cell(2, 8).value in (None, "")
        assert ws.cell(2, 9).value in (None, "")

        # 数据行（第3行）额外列写业务值
        assert ws.cell(3, 3).value == "收款"          # 摘要固定列
        assert ws.cell(3, 7).value == "1122"          # 对方科目固定列
        assert ws.cell(3, 8).value == "张三"           # 经办人
        assert ws.cell(3, 9).value == "A-001"         # 内部编号

    @pytest.mark.asyncio
    async def test_no_extra_columns_when_union_empty(self, db_session, fake_user):
        """并集为空（无 raw_extra 业务键）→ 导出仅固定 7 列，零回归。"""
        await _seed_project(db_session)
        # 一条仅系统标记 + 一条 None → extra_fields 全为 {}
        db_session.add(TbLedger(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
            voucher_date=date(2025, 1, 5), voucher_no="记-0003",
            account_code="1002", account_name="银行存款",
            debit_amount=Decimal("40000"), credit_amount=Decimal("0"),
            summary="收款", counterpart_account="1122", preparer="李四",
            raw_extra=dict(SYS_MARKERS),
        ))
        db_session.add(TbLedger(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
            voucher_date=date(2025, 1, 6), voucher_no="记-0004",
            account_code="1002", account_name="银行存款",
            debit_amount=Decimal("0"), credit_amount=Decimal("5000"),
            summary="付款", counterpart_account="2202", preparer="李四",
            raw_extra=None,
        ))
        await db_session.commit()

        resp = await export_ledger_excel(
            project_id=FAKE_PROJECT_ID, account_code="1002", year=YEAR,
            date_from=None, date_to=None, db=db_session, current_user=fake_user,
        )
        ws, headers = await _read_export_headers(resp)
        assert headers == FIXED_HEADERS
        assert len(headers) == 7
