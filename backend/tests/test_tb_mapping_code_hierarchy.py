"""客户科目 → 标准科目汇总口径（tb_mapping_sql）：科目层级与编码形态。

真库两种形态（重庆医药集团四川医药 / 新健康大药房临港店 2025，同一份余额表）：

1. **连写编码**：``1122`` / ``112201``（不是 ``1122.01``）。原叶子判定只认点号下级，
   父级与明细都被当成叶子 ⇒ 父子重复汇总，临港 1122 未审数 3,988,174.34 = 文件 1,994,087.17 × 2。
2. **``.0`` 尾巴**：Excel 数字格式的编码早期导入成 ``"1001.0"``；导入端改为写 ``"1001"`` 后，
   重新导入的余额表是 ``1001``、沿用的客户科目表与映射仍是 ``1001.0`` ⇒ 287 行一行都映射不上，
   四川试算表与「审定科目余额表 / 底稿取数余额表」整张为 0。
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import AccountMapping, MappingType, TbBalance, TrialBalance
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.services.standard_balance_view_service import build_standard_balance_view
from app.services.trial_balance_service import TrialBalanceService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_UID = uuid.uuid4()


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)() as s:
        yield s


async def _project(db, mappings: dict[str, str], balances: list[tuple[str, str, str, str]]) -> uuid.UUID:
    """mappings: 客户码 → 标准码；balances: (客户码, 期末, 本期借, 本期贷)，期初为 0。"""
    p = Project(
        id=uuid.uuid4(), name="科目层级_2025", client_name="层级测试",
        project_type=ProjectType.annual, status=ProjectStatus.planning, created_by=_UID,
    )
    db.add(p)
    await db.flush()
    for orig, std in mappings.items():
        db.add(AccountMapping(
            project_id=p.id, original_account_code=orig, original_account_name=orig,
            standard_account_code=std, mapping_type=MappingType.manual, created_by=_UID,
        ))
    for code, closing, dr, cr in balances:
        db.add(TbBalance(
            project_id=p.id, year=2025, company_code="001", account_code=code, account_name=code,
            opening_balance=Decimal("0"), closing_balance=Decimal(closing),
            debit_amount=Decimal(dr), credit_amount=Decimal(cr),
        ))
    await db.flush()
    await TrialBalanceService(db).recalc_unadjusted(p.id, 2025)
    await db.commit()
    return p.id


async def _unadjusted(db, pid, code) -> Decimal:
    row = (await db.execute(sa.select(TrialBalance).where(
        TrialBalance.project_id == pid, TrialBalance.standard_account_code == code,
    ))).scalar_one()
    return row.unadjusted_amount


def _view(rows, code):
    return next(r for r in rows if r["standard_account_code"] == code)


@pytest.mark.asyncio
async def test_undotted_children_are_not_double_counted(db):
    """连写编码：父级 1122 = 112201 + 112202，只汇总明细，不重复加父级。"""
    pid = await _project(
        db,
        {"1122": "1122", "112201": "1122", "112202": "1122"},
        [("1122", "300", "500", "200"), ("112201", "100", "200", "100"), ("112202", "200", "300", "100")],
    )
    assert await _unadjusted(db, pid, "1122") == Decimal("300")
    v = _view(await build_standard_balance_view(db, pid, 2025), "1122")
    assert (Decimal(v["closing_balance"]), Decimal(v["period_debit"]), Decimal(v["period_credit"])) == (
        Decimal("300"), Decimal("500"), Decimal("200"),
    )


@pytest.mark.asyncio
async def test_dotted_children_still_work(db):
    """点号分级：1002 = 1002.01 + 1002.02（原有口径不变）。"""
    pid = await _project(
        db,
        {"1002": "1002", "1002.01": "1002", "1002.02": "1002"},
        [("1002", "90", "0", "0"), ("1002.01", "40", "0", "0"), ("1002.02", "50", "0", "0")],
    )
    assert await _unadjusted(db, pid, "1002") == Decimal("90")


@pytest.mark.asyncio
async def test_unmapped_undotted_child_inherits_parent_mapping(db):
    """明细没有映射行：按最近的已映射上级取标准码（连写编码同样适用）。"""
    pid = await _project(db, {"1651": "1641"}, [("1651", "70", "0", "0"), ("165102", "70", "0", "0")])
    assert await _unadjusted(db, pid, "1641") == Decimal("70")


@pytest.mark.asyncio
async def test_float_suffix_codes_match_clean_codes(db):
    """映射是旧的 ``1001.0`` 形态、余额表是重新导入的 ``1001`` 形态：仍能对上，且层级照常判定。"""
    pid = await _project(
        db,
        {"1001.0": "1001", "100101.0": "1001", "100102.0": "1001", "1122.0": "1122"},
        [("1001", "0", "1047830", "1054201"), ("100101", "0", "0", "0"),
         ("100102", "0", "1047830", "1054201"), ("1122", "1994087.17", "0", "0")],
    )
    assert await _unadjusted(db, pid, "1122") == Decimal("1994087.17")
    v = _view(await build_standard_balance_view(db, pid, 2025), "1001")
    assert Decimal(v["period_debit"]) == Decimal("1047830")
    assert Decimal(v["period_credit"]) == Decimal("1054201")


@pytest.mark.asyncio
async def test_float_suffix_on_both_sides_still_detects_hierarchy(db):
    """余额表与映射都还是 ``.0`` 形态（临港）：``100101.0`` 仍是 ``1001.0`` 的下级。"""
    pid = await _project(
        db,
        {"1122.0": "1122", "112201.0": "1122"},
        [("1122.0", "1994087.17", "0", "0"), ("112201.0", "1994087.17", "0", "0")],
    )
    assert await _unadjusted(db, pid, "1122") == Decimal("1994087.17")


@pytest.mark.asyncio
async def test_real_dotted_code_ending_in_zero_digit_is_kept(db):
    """``1002.01`` / ``1002.10`` 这类真分级码不被当成 ``.0`` 尾巴剥掉。"""
    pid = await _project(
        db,
        {"1002.10": "1002", "1002.01": "1002"},
        [("1002.10", "5", "0", "0"), ("1002.01", "7", "0", "0")],
    )
    assert await _unadjusted(db, pid, "1002") == Decimal("12")
