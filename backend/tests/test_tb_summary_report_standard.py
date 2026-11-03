"""试算平衡表按报表行次汇总：行次模板的报表标准与报表页同一个解析（spec consol-autotree-residual-closure R6）。

原实现读 ``wizard_state["basic_info"]["data"]`` 定标准，而向导把基本信息存在 ``steps.basic_info.data``，
平铺位置要到向导确认后才由 ``set_standard`` 写出 ⇒ 未确认的上市 / 合并项目一直按国企单户的行次汇总。
现在与报表页同走 ``ReportConfigService.resolve_applicable_standard``（项目两列）。

真 SQLite + 真 ORM 行 + 真 service。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

_PID = uuid.UUID("bbbbbbbb-0000-4000-8000-00000000e301")
_UID = uuid.UUID("cccccccc-0000-4000-8000-00000000e302")
_YEAR = 2099
_CO = "001"
_REPORT_TYPE = "income_statement"
_ACCT = "6001"
# 两套标准各一行，行次编码不同 ⇒ 汇总结果里出现哪一个，就是按哪套标准取的模板
_ROWS = {"soe_standalone": "IS-SOE-001", "listed_consolidated": "IS-LC-001"}


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _seed(db: AsyncSession, *, template_type: str | None, report_scope: str | None) -> None:
    from app.models.audit_platform_models import (
        AccountCategory, ReportLineMapping, ReportLineMappingType, TrialBalance,
    )
    from app.models.core import Project, User
    from app.models.report_models import ReportConfig

    db.add(User(id=_UID, username="tbstd", email="tbstd@test.local", hashed_password="x", role="admin"))
    # 向导形状照真实写法：基本信息只在 steps 下，没有平铺副本（向导确认前的状态）
    wizard = {
        "project_id": str(_PID), "current_step": "basic_info", "completed": False,
        "steps": {"basic_info": {"step": "basic_info", "completed": True,
                                 "data": {"template_type": template_type, "report_scope": report_scope}}},
    }
    db.add(Project(id=_PID, name="tbstd", client_name="测试客户", status="created", created_by=_UID,
                   template_type=template_type, report_scope=report_scope, wizard_state=wizard))
    for i, (standard, row_code) in enumerate(_ROWS.items(), start=1):
        db.add(ReportConfig(
            id=uuid.uuid4(), report_type=_REPORT_TYPE, row_number=i, row_code=row_code,
            row_name="营业收入", indent_level=1, formula=f"TB('{_ACCT}','未审数')",
            applicable_standard=standard, is_total_row=False, is_deleted=False,
        ))
        db.add(ReportLineMapping(
            id=uuid.uuid4(), project_id=_PID, report_type=_REPORT_TYPE, standard_account_code=_ACCT,
            report_line_code=row_code, report_line_name="营业收入", report_line_level=2, mapping_sign="add",
            mapping_type=ReportLineMappingType.manual, is_confirmed=True, is_deleted=False,
        ))
    db.add(TrialBalance(
        id=uuid.uuid4(), project_id=_PID, year=_YEAR, company_code=_CO, standard_account_code=_ACCT,
        account_name="主营业务收入", account_category=AccountCategory.revenue,
        unadjusted_amount=Decimal("100"), aje_adjustment=Decimal("0"), rje_adjustment=Decimal("0"),
        audited_amount=Decimal("100"), opening_balance=Decimal("0"), is_deleted=False,
    ))
    await db.flush()


async def _row_codes(db: AsyncSession) -> set[str]:
    from app.services.trial_balance_service import TrialBalanceService

    rows = await TrialBalanceService(db).get_summary_with_adjustments(_PID, _YEAR, _REPORT_TYPE, _CO)
    return {r["row_code"] for r in rows}


@pytest.mark.asyncio
async def test_listed_consolidated_project_uses_its_own_rows(db_session: AsyncSession):
    await _seed(db_session, template_type="listed", report_scope="consolidated")
    assert await _row_codes(db_session) == {_ROWS["listed_consolidated"]}


@pytest.mark.asyncio
async def test_unset_standard_falls_back_to_soe_standalone(db_session: AsyncSession):
    await _seed(db_session, template_type=None, report_scope=None)
    assert await _row_codes(db_session) == {_ROWS["soe_standalone"]}


@pytest.mark.asyncio
async def test_same_resolver_as_report_page(db_session: AsyncSession):
    """汇总取模板的标准 == 报表页的 ``resolve_applicable_standard``（同一函数，不是各写一遍）。"""
    from app.services.report_config_service import ReportConfigService

    await _seed(db_session, template_type="listed", report_scope="consolidated")
    standard = await ReportConfigService.resolve_applicable_standard(db_session, _PID)
    assert await _row_codes(db_session) == {_ROWS[standard]}
