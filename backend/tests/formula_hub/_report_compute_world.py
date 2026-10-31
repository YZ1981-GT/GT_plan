"""报表三路逐行计算用例的共用夹具（spec formula-hub-integrity-closure 任务 16；需求 5.2、5.3、6.4、4.3 报表部分；ADR-FHIC-05）。

一个【测试】项目（soe 单体 ⇒ 准则 ``soe_standalone``）+ 资产负债表 / 利润表定义 + 试算表 + 库中已有的报表行（形态见
:data:`LINES`）。SQLite 内存库只建报表生成会读写的表（:data:`_MODELS`；全部模型建表在 SQLite 上会撞 PG 专有默认值
``'[]'::jsonb``；ACNR 引用解析、上期来源等读不到的表按各自的 fail-open 处理），每个 :func:`sqlite_world` 一个独立库
⇒ 三路各在一份相同的初始数据上跑。:func:`run_path` 的三路：全量 ``generate_all_reports``（跳过试算表重算、不发事件）、
affected ``regenerate_affected``、stale ``recalculate_stale_rows``（后两者不传准则 ⇒ 按项目真实准则）。
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  全量注册（外键引用的表要在 metadata 里）
from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import Base, ProjectStatus, ProjectType
from app.models.core import Project, User
from app.models.phase16_models import VersionLineStamp
from app.models.report_models import FinancialReport, FinancialReportType, ReportConfig
from app.services.report_engine import ReportEngine
from app.services.report_freshness import CALC_VERSION
from tests.formula_hub._pg_harness import TEST_PROJECT_PREFIX

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

YEAR = 2025
STANDARD = "soe_standalone"
BS, IS = FinancialReportType.balance_sheet, FinancialReportType.income_statement
PATHS = ("full", "affected", "stale")


@dataclass(frozen=True)
class Line:
    """一行：报表类型、公式、库中旧值（None ⇒ 库里还没有这一行）、旧行是否就绪（否 ⇒ 已标过期、计算版本为空的存量行）。"""

    code: str
    report_type: FinancialReportType
    formula: str | None
    old: Decimal | None
    fresh: bool = False


A, B, T, S, NEW = "FHT16-05", "FHT16-06", "FHT16-07", "FHT16-08", "FHT16-09"
DIV0, MISSING, LEGAL_ZERO, LEAF, COMPONENTS = "FHT16-01", "FHT16-02", "FHT16-03", "FHT16-04", "IS-060"
LINES: tuple[Line, ...] = (
    Line(DIV0, BS, "1/0+TB('1001','期末余额')", Decimal("33")),
    Line(MISSING, BS, "TB('9999','期末余额')", Decimal("44")),  # 试算表没有 9999 ⇒ 0
    Line(LEGAL_ZERO, BS, "TB('1001','期末余额')-TB('1001','期末余额')", Decimal("55")),  # 1001 有余额 100
    Line(LEAF, BS, "TB('1231','期末余额')", Decimal("66")),  # 父 100 ≠ 子 40 + 50 ⇒ 90
    Line(A, BS, "TB('1003','期末余额')/TB('1005','期末余额')", Decimal("11")),  # 1005 = 0 ⇒ 除零
    Line(B, BS, "TB('1002','期末余额')", Decimal("22")),
    Line(T, BS, f"ROW('{A}')+ROW('{B}')", Decimal("77")),
    Line(S, BS, f"SUM_ROW('{A}','{B}')", Decimal("88")),
    Line(NEW, BS, "TB('1004','期末余额')/0", None),  # 库里没有：首次生成即失败 ⇒ 金额 NULL
    Line("IS-048", IS, None, Decimal("0"), fresh=True),  # 无公式行
    Line("IS-054", IS, None, Decimal("0"), fresh=True),
    Line(COMPONENTS, IS, "ROW('IS-048')+ROW('IS-054')+TB('6001','期末余额')", Decimal("99")),
)
#: 试算表（科目码 → 期末审定数 = 未审数）；1231 父 100 ≠ 子 40 + 50
TB_ROWS: dict[str, Decimal] = {code: Decimal(v) for code, v in (
    ("1001", 100), ("1002", 200), ("1003", 300), ("1004", 5), ("1005", 0),
    ("1231", 100), ("1231-01", 40), ("1231-02", 50), ("6001", 600))}
#: affected 路径的变更科目：覆盖每个有公式行（1231-02 经前缀命中 TB('1231')；T / S 经 ROW / SUM_ROW 闭包）
ALL_CHANGED = ("1001", "9999", "1231-02", "1002", "1003", "1004", "6001")

State = tuple[Decimal | None, bool, str | None, int | None]  # (金额, is_stale, calc_error, calc_version)


@dataclass(frozen=True)
class World:
    session: AsyncSession
    project_id: uuid.UUID


async def seed(session: AsyncSession, *, tag: str) -> World:
    project = Project(id=uuid.uuid4(), name=f"{TEST_PROJECT_PREFIX}{tag}_{uuid.uuid4().hex[:8]}",
                      client_name=f"{TEST_PROJECT_PREFIX}报表三路", project_type=ProjectType.annual,
                      status=ProjectStatus.planning, template_type="soe", report_scope="standalone")
    session.add(project)
    await session.flush()
    for number, line in enumerate(LINES, 1):
        session.add(ReportConfig(report_type=line.report_type, row_number=number, row_code=line.code,
                                 row_name=f"三路{number}", formula=line.formula, applicable_standard=STANDARD,
                                 is_deleted=False))
        if line.old is not None:
            session.add(FinancialReport(
                project_id=project.id, year=YEAR, report_type=line.report_type, row_code=line.code,
                row_name=f"三路{number}", current_period_amount=line.old, formula_used=line.formula,
                is_stale=not line.fresh, calc_version=CALC_VERSION if line.fresh else None, is_deleted=False))
    for code, amount in TB_ROWS.items():
        session.add(TrialBalance(project_id=project.id, year=YEAR, company_code="001", standard_account_code=code,
                                 account_name=code, account_category=AccountCategory.asset, audited_amount=amount,
                                 unadjusted_amount=amount, opening_balance=Decimal("0"), is_deleted=False))
    await session.commit()
    return World(session, project.id)


#: 报表生成会读写的表（版本链戳记在生成里写库，缺表会让会话的 flush 失败，故建上）
_MODELS = (User, Project, ReportConfig, FinancialReport, TrialBalance, VersionLineStamp)


@asynccontextmanager
async def sqlite_world(*, tag: str = "fh_t16") -> AsyncIterator[World]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[m.__table__ for m in _MODELS]))
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
            yield await seed(session, tag=tag)
    finally:
        await engine.dispose()


async def run_path(world: World, path: str, *, changed: Iterable[str] = ALL_CHANGED, **full_kwargs: Any) -> Any:
    """跑一路并提交；返回该路入口的原返回值。``full_kwargs`` 只给全量路径（如 ``summary_out``）。"""
    engine = ReportEngine(world.session)
    if path == "full":
        kwargs = {"skip_recalc": True, "publish_events": False, **full_kwargs}
        out = await engine.generate_all_reports(world.project_id, YEAR, applicable_standard=STANDARD, **kwargs)
    elif path == "affected":
        out = await engine.regenerate_affected(world.project_id, YEAR, changed_accounts=list(changed))
    elif path == "stale":
        out = await engine.recalculate_stale_rows(world.project_id, YEAR)
    else:
        raise ValueError(path)
    await world.session.commit()
    return out


async def snapshot(world: World) -> dict[str, State]:
    """库中终态（重新读库，不用会话里的对象）：行次 → (金额, is_stale, calc_error, calc_version)。"""
    rows = (await world.session.execute(
        sa.select(FinancialReport)
        .where(FinancialReport.project_id == world.project_id, FinancialReport.year == YEAR)
        .execution_options(populate_existing=True)
    )).scalars().all()
    return {r.row_code: (r.current_period_amount, r.is_stale, r.calc_error, r.calc_version) for r in rows}


async def set_tb(world: World, code: str, amount: int | Decimal) -> None:
    await world.session.execute(
        sa.update(TrialBalance)
        .where(TrialBalance.project_id == world.project_id, TrialBalance.standard_account_code == code)
        .values(audited_amount=Decimal(amount), unadjusted_amount=Decimal(amount))
    )
    await world.session.commit()
