"""附注章节溯源去伪（spec voucher-workflow-linkage-lineage-closure R8.2，design §10.2）

SQLite 真 ORM 行，走生产路径 ``ReportTraceService.trace_section``（附注注册表与底稿科目映射表用仓库里的真数据：
国企「八、1」→ E1 → 1001 / 1002 / 1012）：

- 试算表按年度 + 章节对应科目取、全部主体合计（原先不分年度、不分科目任取 5 行）；
- 序时账按年度 + 科目前缀取 |借 − 贷| 最大的前 10 笔（原先不分科目、只按借方排），结果带取数口径；
- 底稿数据取本项目未删除的那一张；
- 章节没有映射 / 项目没有审计年度：不取，口径写明原因；年度缺省取项目审计年度；
- 查询失败照常抛出（原先每段 ``except: pass``，失败与「没有数据」分不开）。
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import AccountCategory, TbLedger, TrialBalance
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus
from app.services import report_trace_service
from app.services.report_trace_service import TOP_LEDGER_LIMIT, ReportTraceService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
pytestmark = pytest.mark.asyncio

USER, PROJECT, NO_YEAR, WP_E1 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
YEAR, SECTION = 2025, "八、1"


def _tb(code: str, company: str, *, year: int = YEAR, deleted: bool = False, opening="0", unadjusted="0",
        audited="0") -> TrialBalance:
    return TrialBalance(project_id=PROJECT, year=year, company_code=company, standard_account_code=code,
                        account_name=f"科目{code}", account_category=AccountCategory.asset, is_deleted=deleted,
                        opening_balance=Decimal(opening), unadjusted_amount=Decimal(unadjusted),
                        audited_amount=Decimal(audited))


def _line(no: str, account: str, debit: str | None, credit: str | None, *, year: int = YEAR,
          deleted: bool = False, day: int = 5) -> TbLedger:
    return TbLedger(project_id=PROJECT, year=year, company_code="001", voucher_date=date(year, 3, day),
                    voucher_no=no, account_code=account, debit_amount=Decimal(debit) if debit else None,
                    credit_amount=Decimal(credit) if credit else None, summary=f"摘要{no}", is_deleted=deleted)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(User(id=USER, username="u", email="u@t.com", hashed_password="x", role="auditor"))
        for pid, end in ((PROJECT, date(2025, 12, 31)), (NO_YEAR, None)):
            session.add(Project(id=pid, name=f"附注溯源{pid.hex[:4]}", client_name="测试", project_type=ProjectType.annual,
                                status=ProjectStatus.execution, created_by=USER, template_type="soe",
                                audit_period_end=end))
        wi = WpIndex(id=uuid.uuid4(), project_id=PROJECT, wp_code="E1", wp_name="货币资金", audit_cycle="E",
                     status=WpStatus.not_started)
        session.add(wi)
        session.add(WorkingPaper(id=WP_E1, project_id=PROJECT, wp_index_id=wi.id, file_path="x.xlsx",
                                 source_type=WpSourceType.template, file_version=1,
                                 parsed_data={"html_data": {"E1-1 货币资金": {}}}))
        session.add_all([
            _tb("1001", "001", opening="10", unadjusted="11", audited="12"),
            _tb("1001", "002", opening="1", unadjusted="1", audited="1"),
            _tb("1002", "001", opening="100", unadjusted="200", audited="300"),
            _tb("1002", "003", opening="9999", unadjusted="9999", audited="9999", deleted=True),
            _tb("1002", "001", year=2024, opening="7", unadjusted="7", audited="7"),
            _tb("1122", "001", opening="5", unadjusted="5", audited="5"),
        ])
        lines = [_line(f"{i:04d}", "1002.01", str(100 + i), None, day=1 + i) for i in range(12)]
        lines += [
            _line("9001", "1001", None, "5000"),          # 贷方大额：按 |借−贷| 排在最前（原先只按借方排）
            _line("9002", "1122", "99999", None),         # 别的科目：不取
            _line("9003", "1002", "88888", None, year=2024),  # 别的年度：不取
            _line("9004", "1002", "77777", None, deleted=True),
            _line("9005", "6001", "66666", None),
        ]
        session.add_all(lines)
        await session.commit()
        yield session
    await engine.dispose()


async def test_trial_balance_and_ledger_scoped_by_year_and_section_accounts(db):
    out = await ReportTraceService().trace_section(db, PROJECT, SECTION, YEAR)
    assert out["note_data"] == {"wp_code": "E1", "wp_codes": ["E1"], "note_title": SECTION}
    assert out["workpaper_data"] == {"html_data": {"E1-1 货币资金": {}}}
    assert out["year"] == YEAR and out["account_codes"] == ["1001", "1002", "1012"]
    # 试算表：本年度、章节科目、全部主体合计；1122、2024 年度、已删的不出
    assert out["trial_balance_data"] == [
        {"account_code": "1001", "account_name": "科目1001", "opening": 11.0, "unadjusted": 12.0, "audited": 13.0},
        {"account_code": "1002", "account_name": "科目1002", "opening": 100.0, "unadjusted": 200.0, "audited": 300.0},
    ]
    assert out["trial_balance_basis"] == "2025 年度试算表，科目 1001、1002、1012，全部主体合计"
    # 序时账：前 10 笔、按 |借−贷| 降序；贷方 5000 排第一；别的科目 / 年度 / 已删不出
    entries = out["top_ledger_entries"]
    assert len(entries) == TOP_LEDGER_LIMIT
    assert entries[0] == {"voucher_no": "9001", "date": "2025-03-05", "account_code": "1001", "debit": 0.0,
                          "credit": 5000.0, "summary": "摘要9001"}
    assert [e["debit"] for e in entries[1:]] == [111.0, 110.0, 109.0, 108.0, 107.0, 106.0, 105.0, 104.0, 103.0]
    assert {e["account_code"] for e in entries} <= {"1001", "1002.01"}
    assert out["ledger_basis"] == "2025 年度当前账套序时账，科目以 1001、1002、1012 开头，按金额（借贷差的绝对值）降序前 10 笔"


async def test_deleted_workpaper_data_not_shown(db):
    wp = await db.get(WorkingPaper, WP_E1)
    wp.is_deleted = True
    await db.flush()
    out = await ReportTraceService().trace_section(db, PROJECT, SECTION, YEAR)
    assert out["workpaper_data"] is None
    assert out["note_data"]["wp_code"] == "E1"  # 章节映射照旧（映射来自注册表，与底稿是否生成无关）


async def test_year_defaults_to_project_audit_year(db):
    assert await ReportTraceService().trace_section(db, PROJECT, SECTION) == \
        await ReportTraceService().trace_section(db, PROJECT, SECTION, YEAR)


async def test_no_audit_year_does_not_fetch_and_says_why(db):
    out = await ReportTraceService().trace_section(db, NO_YEAR, SECTION)
    assert out["note_data"]["wp_code"] == "E1"
    assert out["trial_balance_data"] is None and out["top_ledger_entries"] == [] and out["year"] is None
    assert out["trial_balance_basis"] == out["ledger_basis"] == "项目未设置审计年度，未取试算表与序时账"


async def test_unmapped_section_does_not_fetch_and_says_why(db):
    out = await ReportTraceService().trace_section(db, PROJECT, "不存在的章节", YEAR)
    assert out["note_data"] is None and out["trial_balance_data"] is None and out["top_ledger_entries"] == []
    assert out["trial_balance_basis"] == "章节没有对应底稿，未取试算表与序时账"


async def test_section_whose_workpapers_have_no_accounts(db, monkeypatch):
    monkeypatch.setattr(report_trace_service, "_section_account_codes", lambda _codes: [])
    out = await ReportTraceService().trace_section(db, PROJECT, SECTION, YEAR)
    assert out["note_data"]["wp_code"] == "E1" and out["trial_balance_data"] is None
    assert out["ledger_basis"] == "章节对应底稿没有映射科目，未取试算表与序时账"


async def test_query_failure_is_raised_not_reported_as_empty(db, monkeypatch):
    async def _boom(*_a, **_kw):
        raise RuntimeError("ledger_datasets 读失败")

    monkeypatch.setattr(report_trace_service, "get_active_filter", _boom)
    with pytest.raises(RuntimeError, match="ledger_datasets 读失败"):
        await ReportTraceService().trace_section(db, PROJECT, SECTION, YEAR)


async def test_ledger_active_filter_is_strict(db, monkeypatch):
    """当前账套查询失败不得退化成「不按账套过滤」并回滚调用方事务（strict=True）。"""
    seen: dict = {}
    real = report_trace_service.get_active_filter

    async def _spy(db_, table, project_id, year, **kw):
        seen.update(kw)
        return await real(db_, table, project_id, year, **kw)

    monkeypatch.setattr(report_trace_service, "get_active_filter", _spy)
    await ReportTraceService().trace_section(db, PROJECT, SECTION, YEAR)
    assert seen == {"strict": True}
