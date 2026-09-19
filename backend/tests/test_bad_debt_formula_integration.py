# Feature: workpaper-bad-debt-nested-structure — Task 8.2 公式引擎集成单元测试
"""D2-3 坏账准备明细表 WP 函数寻址集成测试。

覆盖（Validates Requirements 9.2, 9.3, 9.4）：
- 合计级引用：WP('D2','坏账准备明细表D2-3','本期计提合计') → Summary_Row.amount_f 等
- 父行级引用：WP('D2','坏账准备明细表D2-3','单项评估计提.期末审定数') → INDIVIDUAL 父行 amount_n
- 地址变更触发依赖重算：extract_wp_refs 能识别三参 D2-3 引用，find_dependent_wp_ids
  标记下游底稿 stale（依赖联动链路）

DB：in-process 内存 SQLite，建 wp_index + bad_debt_detail_rows 表（与 service 测试同口径）。
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# WpIndex.cross_ref_codes 为 JSONB，SQLite 无原生 JSONB → 复用 JSON 编译
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]

from app.models.base import Base
from app.models.bad_debt_models import BadDebtDetailRow, ProvisionMethod
from app.models.workpaper_models import WpIndex
from app.schemas.bad_debt_schemas import (
    CreateChildRowDTO,
    CreateParentRowDTO,
    UpdateRowDTO,
    RowAmounts,
)
from app.services.bad_debt_nested_table_service import NestedTableService
from app.services.formula_engine import WPExecutor
from app.services.wp_formula_linkage_service import (
    expression_references_cell,
    extract_wp_refs,
)

_D23_SHEET = "坏账准备明细表D2-3"


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[WpIndex.__table__, BadDebtDetailRow.__table__],
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _seed_d23(
    db: AsyncSession, project_id: uuid.UUID, wp_code: str = "D2"
) -> uuid.UUID:
    """建一个 D2-3 底稿 wp_index + 两个父行（INDIVIDUAL/CREDIT_RISK_AGING）含子行。"""
    wp_index_id = uuid.uuid4()
    db.add(
        WpIndex(
            id=wp_index_id,
            project_id=project_id,
            wp_code=wp_code,
            wp_name="坏账准备明细表D2-3",
            audit_cycle="D",
            status="not_started",
        )
    )
    await db.flush()

    svc = NestedTableService(db)
    # 父行1：单项评估计提 — 两个子行，本期计提合计=300，期末审定数合计=500
    p1 = await svc.create_parent_row(
        wp_index_id,
        CreateParentRowDTO(
            provision_method=ProvisionMethod.INDIVIDUAL, row_label="按单项评估计提"
        ),
    )
    c1 = await svc.create_child_row(
        p1.id, CreateChildRowDTO(row_label="其中：甲公司", amount_n=Decimal("200.00"))
    )
    # 用 update_row 给子行补 F 列（本期计提），CreateChildRowDTO 只接受 E/K/N
    await svc.update_row(
        c1.id,
        UpdateRowDTO(
            version=1,
            amounts=RowAmounts(amount_f=Decimal("100.00"), amount_n=Decimal("200.00")),
        ),
    )
    c2 = await svc.create_child_row(
        p1.id, CreateChildRowDTO(row_label="其中：乙公司", amount_n=Decimal("300.00"))
    )
    await svc.update_row(
        c2.id,
        UpdateRowDTO(
            version=1,
            amounts=RowAmounts(amount_f=Decimal("200.00"), amount_n=Decimal("300.00")),
        ),
    )

    # 父行2：信用风险组合-账龄分析法 — 一个子行，本期计提=50，期末审定数=80
    p2 = await svc.create_parent_row(
        wp_index_id,
        CreateParentRowDTO(
            provision_method=ProvisionMethod.CREDIT_RISK_AGING,
            row_label="信用风险组合-账龄分析法",
        ),
    )
    c3 = await svc.create_child_row(
        p2.id, CreateChildRowDTO(row_label="其中：账龄组合", amount_n=Decimal("80.00"))
    )
    await svc.update_row(
        c3.id,
        UpdateRowDTO(
            version=1,
            amounts=RowAmounts(amount_f=Decimal("50.00"), amount_n=Decimal("80.00")),
        ),
    )
    await db.flush()
    return wp_index_id


# ─── 9.2 合计级引用 ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_summary_level_本期计提合计(session: AsyncSession):
    """WP('D2','坏账准备明细表D2-3','本期计提合计') → Summary amount_f = 100+200+50=350。"""
    project_id = uuid.uuid4()
    await _seed_d23(session, project_id)
    val = await WPExecutor.execute(
        session, project_id, "D2", _D23_SHEET, field="本期计提合计"
    )
    assert val == Decimal("350.00")


@pytest.mark.asyncio
async def test_summary_level_期末余额(session: AsyncSession):
    """WP(...,'期末余额') → Summary amount_n = 200+300+80=580。"""
    project_id = uuid.uuid4()
    await _seed_d23(session, project_id)
    val = await WPExecutor.execute(
        session, project_id, "D2", _D23_SHEET, field="期末余额"
    )
    assert val == Decimal("580.00")


@pytest.mark.asyncio
async def test_summary_level_本期转回核销为零(session: AsyncSession):
    """未填的 H/I 列 → 合计为 0。"""
    project_id = uuid.uuid4()
    await _seed_d23(session, project_id)
    huizhuan = await WPExecutor.execute(
        session, project_id, "D2", _D23_SHEET, field="本期转回合计"
    )
    hexiao = await WPExecutor.execute(
        session, project_id, "D2", _D23_SHEET, field="核销合计"
    )
    assert huizhuan == Decimal("0")
    assert hexiao == Decimal("0")


# ─── 9.4 父行级引用 ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_parent_level_单项评估计提_期末审定数(session: AsyncSession):
    """WP(...,'单项评估计提.期末审定数') → INDIVIDUAL 父行 amount_n = 200+300=500。"""
    project_id = uuid.uuid4()
    await _seed_d23(session, project_id)
    val = await WPExecutor.execute(
        session, project_id, "D2", _D23_SHEET, field="单项评估计提.期末审定数"
    )
    assert val == Decimal("500.00")


@pytest.mark.asyncio
async def test_parent_level_单项评估计提_本期计提(session: AsyncSession):
    """父行级本期计提 = 100+200=300。"""
    project_id = uuid.uuid4()
    await _seed_d23(session, project_id)
    val = await WPExecutor.execute(
        session, project_id, "D2", _D23_SHEET, field="单项评估计提.本期计提"
    )
    assert val == Decimal("300.00")


@pytest.mark.asyncio
async def test_parent_level_账龄分析法(session: AsyncSession):
    """父行级按 provision_method_label 匹配 CREDIT_RISK_AGING：期末审定数=80。"""
    project_id = uuid.uuid4()
    await _seed_d23(session, project_id)
    val = await WPExecutor.execute(
        session,
        project_id,
        "D2",
        _D23_SHEET,
        field="信用风险组合-账龄分析法.期末审定数",
    )
    assert val == Decimal("80.00")


@pytest.mark.asyncio
async def test_parent_level_未匹配父行返回零(session: AsyncSession):
    """不存在的父行名 → 容错返回 0。"""
    project_id = uuid.uuid4()
    await _seed_d23(session, project_id)
    val = await WPExecutor.execute(
        session, project_id, "D2", _D23_SHEET, field="其他.期末审定数"
    )
    assert val == Decimal("0")


@pytest.mark.asyncio
async def test_unknown_field_returns_zero(session: AsyncSession):
    """未知字段名 → 容错返回 0。"""
    project_id = uuid.uuid4()
    await _seed_d23(session, project_id)
    val = await WPExecutor.execute(
        session, project_id, "D2", _D23_SHEET, field="不存在的字段"
    )
    assert val == Decimal("0")


@pytest.mark.asyncio
async def test_no_data_returns_zero(session: AsyncSession):
    """项目无坏账数据 → 返回 0（不报错）。"""
    project_id = uuid.uuid4()
    val = await WPExecutor.execute(
        session, project_id, "D2", _D23_SHEET, field="本期计提合计"
    )
    assert val == Decimal("0")


# ─── 9.3 地址变更触发依赖重算（依赖识别链路）─────────────────────────────────


def test_extract_wp_refs_三参_d23():
    """extract_wp_refs 识别三参 D2-3 引用为 (wp_code, sheet.field)。"""
    expr = "=WP('D2','坏账准备明细表D2-3','本期计提合计') + 100"
    refs = extract_wp_refs(expr)
    assert ("D2", "坏账准备明细表D2-3.本期计提合计") in refs


def test_extract_wp_refs_两参向后兼容():
    """两参 WP 引用仍按 (wp_code, cell) 解析。"""
    refs = extract_wp_refs("WP('D1-1','B5')")
    assert refs == [("D1-1", "B5")]


def test_expression_references_cell_三参():
    """下游公式引用 D2-3 字段时被识别为依赖（触发 stale 标记的基础）。"""
    expr = "WP('D2','坏账准备明细表D2-3','期末余额')"
    assert (
        expression_references_cell(expr, "D2", "坏账准备明细表D2-3.期末余额") is True
    )
    assert expression_references_cell(expr, "D2", "B5") is False


@pytest.mark.asyncio
async def test_summary_recompute_after_child_update(session: AsyncSession):
    """子行金额变更后，合计级引用返回重算后的新值（数据变更触发汇总变化）。"""
    project_id = uuid.uuid4()
    wp_index_id = await _seed_d23(session, project_id)

    before = await WPExecutor.execute(
        session, project_id, "D2", _D23_SHEET, field="本期计提合计"
    )
    assert before == Decimal("350.00")

    # 找到 INDIVIDUAL 父行第一个子行，把本期计提从 100 改为 1000
    tree = await NestedTableService(session).get_tree(wp_index_id)
    individual = next(
        p for p in tree.parents if p.provision_method == ProvisionMethod.INDIVIDUAL
    )
    first_child = individual.children[0]
    await NestedTableService(session).update_row(
        first_child.id,
        UpdateRowDTO(
            version=first_child.version,
            amounts=RowAmounts(
                amount_f=Decimal("1000.00"), amount_n=first_child.amounts.amount_n
            ),
        ),
    )
    await session.flush()

    after = await WPExecutor.execute(
        session, project_id, "D2", _D23_SHEET, field="本期计提合计"
    )
    # 100→1000，合计 350→1250
    assert after == Decimal("1250.00")
