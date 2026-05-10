"""B' 架构下 rollback 语义 + 并发场景隔离集成测试

背景：
- Sprint 2 重构后，`DatasetService.activate/rollback` 不再 UPDATE Tb* 物理行。
- 可见性完全由 `ledger_datasets.status` 控制，物理行 is_deleted 恒为 false。
- 查询层统一通过 `dataset_query.get_active_filter` 获取过滤条件。

本文件验证：
1. **Rollback 语义（Task 3.2）**：V1 → activate → V2 → activate → rollback
   每一步通过 `get_active_filter` 查询 TbBalance，应看到对应 dataset 的数据；
   物理行在整个过程中未被 UPDATE（is_deleted 恒为 false，两个 dataset 的行都在库里）。
2. **并发场景隔离（Task 3.3）**：项目 A staged + 项目 B active 互不污染。
   通过 project_id 过滤即可隔离；staged 数据不会被误读到其他项目。

Fixture 参考 backend/tests/test_dataset_import_platform.py（SQLite in-memory）。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# SQLite 兼容适配：PG JSONB/UUID 降级到 JSON/uuid
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base
import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.dataset_models  # noqa: F401
from app.models.audit_platform_models import TbBalance
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.services.dataset_query import get_active_filter
from app.services.dataset_service import DatasetService


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# 小工具：用 get_active_filter 查 TbBalance 当前对项目可见的行
# ---------------------------------------------------------------------------
async def _select_active_balance(
    db: AsyncSession, project_id: uuid.UUID, year: int
) -> list[TbBalance]:
    condition = await get_active_filter(db, TbBalance.__table__, project_id, year)
    result = await db.execute(
        sa.select(TbBalance).where(condition).order_by(TbBalance.account_code)
    )
    return list(result.scalars().all())


async def _count_physical_rows(
    db: AsyncSession, project_id: uuid.UUID, year: int, dataset_id: uuid.UUID
) -> int:
    """按 dataset_id 直接查物理行数，不过滤 is_deleted —— 用于证明物理行未被删/改。"""
    result = await db.execute(
        sa.select(sa.func.count())
        .select_from(TbBalance)
        .where(
            TbBalance.project_id == project_id,
            TbBalance.year == year,
            TbBalance.dataset_id == dataset_id,
        )
    )
    return result.scalar_one()


# ===========================================================================
# Task 3.2：Rollback 语义（B' 架构下）
# ===========================================================================
@pytest.mark.asyncio
async def test_rollback_flips_visibility_without_updating_physical_rows(
    db_session: AsyncSession,
):
    """验证 rollback 通过 dataset metadata 切换可见性，物理行不受影响。

    流程：
      V1 create_staged → activate → insert V1 rows(is_deleted=False)
      V2 create_staged → activate → insert V2 rows(is_deleted=False)
      get_active_filter → 应只看到 V2 rows
      rollback → V2=rolled_back, V1=active
      get_active_filter → 应只看到 V1 rows
      两个 dataset 的物理行在整个过程中数量不变、is_deleted 不变
    """
    project_id = uuid.uuid4()
    year = 2024

    # ----- 准备 V1：create_staged + activate + 写入 2 条数据 -----
    v1 = await DatasetService.create_staged(db_session, project_id=project_id, year=year)
    await DatasetService.activate(db_session, v1.id)
    await db_session.flush()

    db_session.add_all([
        TbBalance(
            project_id=project_id,
            year=year,
            company_code="001",
            account_code="1001",
            account_name="V1-现金",
            dataset_id=v1.id,
            is_deleted=False,  # B' 架构：物理行写入 false
        ),
        TbBalance(
            project_id=project_id,
            year=year,
            company_code="001",
            account_code="1002",
            account_name="V1-银行",
            dataset_id=v1.id,
            is_deleted=False,
        ),
    ])
    await db_session.flush()

    # V1 激活后可见行应为 V1
    rows = await _select_active_balance(db_session, project_id, year)
    assert len(rows) == 2
    assert {r.account_name for r in rows} == {"V1-现金", "V1-银行"}

    # ----- 准备 V2：create_staged + activate（V1 自动降级为 superseded） -----
    v2 = await DatasetService.create_staged(db_session, project_id=project_id, year=year)
    # staged 时仍先写入 V2 数据（模拟 pipeline 先写后激活的场景）
    db_session.add_all([
        TbBalance(
            project_id=project_id,
            year=year,
            company_code="001",
            account_code="1001",
            account_name="V2-现金",
            dataset_id=v2.id,
            is_deleted=False,
        ),
        TbBalance(
            project_id=project_id,
            year=year,
            company_code="001",
            account_code="1003",
            account_name="V2-应收",
            dataset_id=v2.id,
            is_deleted=False,
        ),
    ])
    await db_session.flush()

    await DatasetService.activate(db_session, v2.id)
    await db_session.flush()

    # ----- 断言：V2 active 后 get_active_filter 只返回 V2 rows -----
    # 从 DB reload 避免 ORM 内存态误判
    await db_session.refresh(v1)
    await db_session.refresh(v2)
    assert v1.status == DatasetStatus.superseded
    assert v2.status == DatasetStatus.active

    rows = await _select_active_balance(db_session, project_id, year)
    assert len(rows) == 2
    assert {r.account_name for r in rows} == {"V2-现金", "V2-应收"}

    # V1 的物理行仍然存在、is_deleted 仍为 false（未被 UPDATE）
    assert await _count_physical_rows(db_session, project_id, year, v1.id) == 2
    v1_physical = (
        await db_session.execute(
            sa.select(TbBalance).where(TbBalance.dataset_id == v1.id)
        )
    ).scalars().all()
    assert all(r.is_deleted is False for r in v1_physical), (
        "B' 架构下 activate 不应 UPDATE 物理行 is_deleted"
    )

    # ----- 执行 rollback：V2 → rolled_back, V1 → active -----
    restored = await DatasetService.rollback(db_session, project_id, year)
    await db_session.flush()

    assert restored is not None
    assert restored.id == v1.id

    await db_session.refresh(v1)
    await db_session.refresh(v2)
    assert v2.status == DatasetStatus.rolled_back
    assert v1.status == DatasetStatus.active

    # ----- 断言：rollback 后 get_active_filter 回到 V1 -----
    rows = await _select_active_balance(db_session, project_id, year)
    assert len(rows) == 2
    assert {r.account_name for r in rows} == {"V1-现金", "V1-银行"}

    # V2 的物理行仍然存在、is_deleted 仍为 false（未被 rollback UPDATE）
    assert await _count_physical_rows(db_session, project_id, year, v2.id) == 2
    v2_physical = (
        await db_session.execute(
            sa.select(TbBalance).where(TbBalance.dataset_id == v2.id)
        )
    ).scalars().all()
    assert all(r.is_deleted is False for r in v2_physical), (
        "B' 架构下 rollback 不应 UPDATE 物理行 is_deleted"
    )

    # ----- 元数据收尾断言：整个流程只改 dataset status，没动物理行 -----
    all_datasets = (
        await db_session.execute(
            sa.select(LedgerDataset).where(
                LedgerDataset.project_id == project_id,
                LedgerDataset.year == year,
            )
        )
    ).scalars().all()
    statuses = {d.id: d.status for d in all_datasets}
    assert statuses[v1.id] == DatasetStatus.active
    assert statuses[v2.id] == DatasetStatus.rolled_back


@pytest.mark.asyncio
async def test_rollback_without_previous_returns_none(db_session: AsyncSession):
    """首版数据集无 previous，rollback 应返回 None（不报错、不改状态）。"""
    project_id = uuid.uuid4()
    year = 2024

    v1 = await DatasetService.create_staged(db_session, project_id=project_id, year=year)
    await DatasetService.activate(db_session, v1.id)
    await db_session.flush()

    restored = await DatasetService.rollback(db_session, project_id, year)
    assert restored is None

    await db_session.refresh(v1)
    assert v1.status == DatasetStatus.active  # 状态保持不变


# ===========================================================================
# Task 3.3：并发场景 — 项目 A staged + 项目 B active 互不污染
# ===========================================================================
@pytest.mark.asyncio
async def test_project_isolation_staged_does_not_leak_across_projects(
    db_session: AsyncSession,
):
    """项目 A 有 staged 数据集 + 物理行；项目 B 有 active 数据集 + 物理行。

    get_active_filter 必须按 project_id 隔离：
    - 查询 A 项目时不能看到 B 的 active 数据（跨项目隔离）
    - 查询 B 项目时不能看到 A 的 staged 数据（跨项目隔离）
    """
    project_a = uuid.uuid4()
    project_b = uuid.uuid4()
    year = 2024

    # ----- 项目 A：create_staged（**不** activate），写入物理行（B' 下 is_deleted=False） -----
    a_staged = await DatasetService.create_staged(
        db_session, project_id=project_a, year=year
    )
    db_session.add_all([
        TbBalance(
            project_id=project_a,
            year=year,
            company_code="A01",
            account_code="1001",
            account_name="A-现金-staged",
            dataset_id=a_staged.id,
            is_deleted=False,
        ),
        TbBalance(
            project_id=project_a,
            year=year,
            company_code="A01",
            account_code="1002",
            account_name="A-银行-staged",
            dataset_id=a_staged.id,
            is_deleted=False,
        ),
    ])
    await db_session.flush()

    # ----- 项目 B：create_staged + activate，写入物理行 -----
    b_active = await DatasetService.create_staged(
        db_session, project_id=project_b, year=year
    )
    await DatasetService.activate(db_session, b_active.id)
    await db_session.flush()

    db_session.add_all([
        TbBalance(
            project_id=project_b,
            year=year,
            company_code="B01",
            account_code="2001",
            account_name="B-应付-active",
            dataset_id=b_active.id,
            is_deleted=False,
        ),
        TbBalance(
            project_id=project_b,
            year=year,
            company_code="B01",
            account_code="2002",
            account_name="B-存货-active",
            dataset_id=b_active.id,
            is_deleted=False,
        ),
    ])
    await db_session.flush()

    # ----- 断言：查询 B 项目（active）→ 只返回 B 的 active 行 -----
    b_rows = await _select_active_balance(db_session, project_b, year)
    assert len(b_rows) == 2
    b_names = {r.account_name for r in b_rows}
    assert b_names == {"B-应付-active", "B-存货-active"}
    # B 的查询结果绝对不能包含 A 的 staged 行
    for r in b_rows:
        assert r.project_id == project_b
        assert not r.account_name.startswith("A-"), (
            "B 项目查询不应泄露 A 项目的 staged 数据"
        )

    # ----- 断言：查询 A 项目（无 active）→ 不应返回 B 的数据 -----
    # 注意：A 无 active dataset，get_active_filter 降级为
    # `project_id=A AND is_deleted=False`；A 的 staged 行 is_deleted=False 会被返回，
    # 这是 B' 架构下的预期行为（允许前端看"当前进度"）。
    # 关键点是：绝对不能返回 B 的行。
    a_rows = await _select_active_balance(db_session, project_a, year)
    for r in a_rows:
        assert r.project_id == project_a
        assert not r.account_name.startswith("B-"), (
            "A 项目查询不应泄露 B 项目的 active 数据"
        )

    # ----- 物理行总数断言：两个项目各 2 行，完全不交叉 -----
    total_a_rows = (
        await db_session.execute(
            sa.select(sa.func.count())
            .select_from(TbBalance)
            .where(TbBalance.project_id == project_a)
        )
    ).scalar_one()
    total_b_rows = (
        await db_session.execute(
            sa.select(sa.func.count())
            .select_from(TbBalance)
            .where(TbBalance.project_id == project_b)
        )
    ).scalar_one()
    assert total_a_rows == 2
    assert total_b_rows == 2


@pytest.mark.asyncio
async def test_project_isolation_two_actives_do_not_pollute_each_other(
    db_session: AsyncSession,
):
    """两个项目分别各有 active 数据集，get_active_filter 必须严格按 project_id 隔离。"""
    project_a = uuid.uuid4()
    project_b = uuid.uuid4()
    year = 2024

    a_active = await DatasetService.create_staged(
        db_session, project_id=project_a, year=year
    )
    await DatasetService.activate(db_session, a_active.id)

    b_active = await DatasetService.create_staged(
        db_session, project_id=project_b, year=year
    )
    await DatasetService.activate(db_session, b_active.id)
    await db_session.flush()

    db_session.add_all([
        TbBalance(
            project_id=project_a,
            year=year,
            company_code="A01",
            account_code="1001",
            account_name="A-only",
            dataset_id=a_active.id,
            is_deleted=False,
        ),
        TbBalance(
            project_id=project_b,
            year=year,
            company_code="B01",
            account_code="1001",
            account_name="B-only",
            dataset_id=b_active.id,
            is_deleted=False,
        ),
    ])
    await db_session.flush()

    a_rows = await _select_active_balance(db_session, project_a, year)
    b_rows = await _select_active_balance(db_session, project_b, year)

    assert len(a_rows) == 1
    assert a_rows[0].account_name == "A-only"
    assert len(b_rows) == 1
    assert b_rows[0].account_name == "B-only"
