"""Task 2.2: 凭证查询端点集成 + 零回归测试（raw_extra → extra_fields）

对含 raw_extra（业务键 + _ 前缀系统标记）的 tb_ledger / tb_aux_ledger 行，验证：
- get_ledger_entries / get_voucher_entries / get_ledger_entries_cursor /
  get_all_ledger_entries / get_aux_ledger_entries / get_aux_ledger_entries_cursor
  每条 item 有 extra_fields 且只含业务键、不含 _ 前缀键、不含原始 raw_extra 键
- 既有固定字段集合与取值不变（零回归锚点）
- 游标方法 next_cursor / has_more 不受影响

沿用 test_ledger_penetration.py 的内存/SQLite fixture 模式（JSONB→JSON 兼容）。
Validates: Requirements 1.1-1.5, 2.1, 5.1, 5.3, 5.4, 6.1
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, ProjectUser
from app.models.audit_platform_models import TbLedger, TbAuxLedger

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()
YEAR = 2025

# 业务额外字段 + 系统标记（_ 前缀）
BIZ_EXTRA = {"经办人": "张三", "内部编号": "A-001"}
SYS_MARKERS = {"_discarded_mappings": {"x": 1}, "_aggregated_from_aux": True, "_aux_row_count": 3}
RAW_WITH_BOTH = {**BIZ_EXTRA, **SYS_MARKERS}

# 序时账固定字段集合（零回归锚点）
LEDGER_FIXED_FIELDS = {
    "id", "voucher_date", "voucher_no", "account_code", "account_name",
    "debit_amount", "credit_amount", "summary",
}


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    user = User(
        id=FAKE_USER_ID, username="tester", email="t@test.com",
        hashed_password="x", role="member",
    )
    db_session.add(user)
    project = Project(
        id=FAKE_PROJECT_ID, name="raw_extra 透出测试", client_name="测试",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    db_session.add(ProjectUser(
        project_id=FAKE_PROJECT_ID, user_id=FAKE_USER_ID,
        role="auditor", permission_level="edit", is_deleted=False,
    ))

    # 3 条 1002 序时账：分别含 (业务+系统) / 仅系统 / None
    ledger_specs = [
        ("记-0001", RAW_WITH_BOTH),           # 业务键 + 系统标记
        ("记-0002", dict(SYS_MARKERS)),       # 仅系统标记 → extra_fields {}
        ("记-0003", None),                    # None → extra_fields {}
    ]
    for i, (vno, raw) in enumerate(ledger_specs):
        db_session.add(TbLedger(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
            voucher_date=date(2025, 1, 1 + i),
            voucher_no=vno,
            account_code="1002", account_name="银行存款",
            debit_amount=Decimal("40000"), credit_amount=Decimal("0"),
            summary=f"测试凭证{i+1}", counterpart_account="1122",
            preparer="李四",
            raw_extra=raw,
        ))

    # 辅助明细（1122 客户 C001）含 raw_extra
    for i in range(2):
        db_session.add(TbAuxLedger(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
            voucher_date=date(2025, 1, 10 + i),
            voucher_no=f"记-{i+200:04d}",
            account_code="1122", aux_type="客户", aux_code="C001", aux_name="客户A",
            debit_amount=Decimal("15000"), credit_amount=Decimal("0"),
            summary=f"辅助明细{i+1}",
            raw_extra=dict(RAW_WITH_BOTH) if i == 0 else None,
        ))

    await db_session.commit()
    return {"project_id": FAKE_PROJECT_ID}


def _assert_extra_fields_contract(items: list[dict], fixed_fields: set):
    """通用断言：每行有 extra_fields、无 _ 前缀键、无原始 raw_extra 键、固定字段保留。"""
    assert items, "expected non-empty items"
    for it in items:
        assert "extra_fields" in it, "每条 item 必须含 extra_fields"
        assert "raw_extra" not in it, "不得透出原始 raw_extra 键"
        for k in it["extra_fields"]:
            assert not k.startswith("_"), f"extra_fields 不得含系统标记键: {k}"
        # 零回归锚点：固定字段仍在
        for f in fixed_fields:
            assert f in it, f"固定字段缺失: {f}"


class TestLedgerEntriesExtraFields:

    @pytest.mark.asyncio
    async def test_get_ledger_entries_exposes_extra_fields(self, db_session, seeded_db):
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session)
        result = await svc.get_ledger_entries(FAKE_PROJECT_ID, YEAR, "1002")
        items = result["items"]
        assert result["total"] == 3
        _assert_extra_fields_contract(items, LEDGER_FIXED_FIELDS)

        by_vno = {it["voucher_no"]: it for it in items}
        # 含业务+系统 → 只留业务键
        assert by_vno["记-0001"]["extra_fields"] == BIZ_EXTRA
        # 仅系统标记 → {}
        assert by_vno["记-0002"]["extra_fields"] == {}
        # None → {}
        assert by_vno["记-0003"]["extra_fields"] == {}

    @pytest.mark.asyncio
    async def test_get_ledger_entries_zero_regression_fixed_values(self, db_session, seeded_db):
        """零回归：既有固定字段取值不变。"""
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session)
        result = await svc.get_ledger_entries(FAKE_PROJECT_ID, YEAR, "1002")
        row = next(it for it in result["items"] if it["voucher_no"] == "记-0001")
        assert row["account_code"] == "1002"
        assert row["account_name"] == "银行存款"
        assert row["debit_amount"] == Decimal("40000")
        assert row["credit_amount"] == Decimal("0")
        assert row["summary"] == "测试凭证1"
        assert row["counterpart_account"] == "1122"

    @pytest.mark.asyncio
    async def test_get_all_ledger_entries_exposes_extra_fields(self, db_session, seeded_db):
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session)
        result = await svc.get_all_ledger_entries(FAKE_PROJECT_ID, YEAR)
        items = result["items"]
        _assert_extra_fields_contract(items, {"id", "voucher_no", "account_code", "preparer"})
        by_vno = {it["voucher_no"]: it for it in items}
        assert by_vno["记-0001"]["extra_fields"] == BIZ_EXTRA
        # preparer 固定字段零回归
        assert by_vno["记-0001"]["preparer"] == "李四"

    @pytest.mark.asyncio
    async def test_get_voucher_entries_exposes_extra_fields(self, db_session, seeded_db):
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session)
        items = await svc.get_voucher_entries(FAKE_PROJECT_ID, YEAR, "记-0001")
        _assert_extra_fields_contract(items, LEDGER_FIXED_FIELDS)
        assert items[0]["extra_fields"] == BIZ_EXTRA
        assert items[0]["voucher_no"] == "记-0001"

    @pytest.mark.asyncio
    async def test_get_ledger_entries_cursor_exposes_extra_fields(self, db_session, seeded_db):
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session)
        page = await svc.get_ledger_entries_cursor(FAKE_PROJECT_ID, YEAR, "1002", limit=10)
        items = page["items"]
        assert page["total"] == 3
        _assert_extra_fields_contract(items, LEDGER_FIXED_FIELDS | {"running_balance"})
        by_vno = {it["voucher_no"]: it for it in items}
        assert by_vno["记-0001"]["extra_fields"] == BIZ_EXTRA
        assert by_vno["记-0002"]["extra_fields"] == {}

    @pytest.mark.asyncio
    async def test_get_ledger_entries_cursor_next_cursor_unaffected(self, db_session, seeded_db):
        """游标：limit=2 时 has_more/next_cursor 逻辑不受 extra_fields 影响。"""
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session)
        page = await svc.get_ledger_entries_cursor(FAKE_PROJECT_ID, YEAR, "1002", limit=2)
        assert page["has_more"] is True
        assert page["next_cursor"] is not None
        # next_cursor 从最后一行 voucher_date|id 计算，不含 raw_extra 影响
        assert "|" in page["next_cursor"]
        assert len(page["items"]) == 2
        for it in page["items"]:
            assert "extra_fields" in it and "raw_extra" not in it


class TestAuxLedgerEntriesExtraFields:

    @pytest.mark.asyncio
    async def test_get_aux_ledger_entries_exposes_extra_fields(self, db_session, seeded_db):
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session)
        result = await svc.get_aux_ledger_entries(
            FAKE_PROJECT_ID, YEAR, "1122", aux_type="客户", aux_code="C001",
        )
        items = result["items"]
        assert result["total"] == 2
        _assert_extra_fields_contract(
            items, {"id", "voucher_no", "account_code", "aux_type", "aux_code", "summary"}
        )
        by_vno = {it["voucher_no"]: it for it in items}
        assert by_vno["记-0200"]["extra_fields"] == BIZ_EXTRA
        assert by_vno["记-0201"]["extra_fields"] == {}

    @pytest.mark.asyncio
    async def test_get_aux_ledger_entries_cursor_exposes_extra_fields(self, db_session, seeded_db):
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session)
        page = await svc.get_aux_ledger_entries_cursor(
            FAKE_PROJECT_ID, YEAR, "1122", limit=10, aux_type="客户", aux_code="C001",
        )
        items = page["items"]
        _assert_extra_fields_contract(
            items, {"id", "voucher_no", "account_code", "aux_type", "summary"}
        )
        by_vno = {it["voucher_no"]: it for it in items}
        assert by_vno["记-0200"]["extra_fields"] == BIZ_EXTRA
        assert by_vno["记-0201"]["extra_fields"] == {}

    @pytest.mark.asyncio
    async def test_aux_cursor_next_cursor_unaffected(self, db_session, seeded_db):
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session)
        page = await svc.get_aux_ledger_entries_cursor(
            FAKE_PROJECT_ID, YEAR, "1122", limit=1, aux_type="客户", aux_code="C001",
        )
        assert page["has_more"] is True
        assert page["next_cursor"] is not None
        assert len(page["items"]) == 1
        assert "extra_fields" in page["items"][0]
        assert "raw_extra" not in page["items"][0]
