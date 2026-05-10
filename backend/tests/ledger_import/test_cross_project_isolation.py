"""F41 / Sprint 7.8: 跨项目隔离集成测试

背景（design D11.2 / requirements F41）：
- 本迁移为 Tb* + ledger_datasets 预留了 `tenant_id` 列（恒 'default'），
  但 **`get_active_filter` 签名尚未加 current_user 参数**（Sprint 7.6/7.7 的事）。
- 即便 tenant 校验未启用，project_id 过滤必须成为跨项目数据隔离的底线。

本测试验证：
1. 项目 A 激活了自己的 dataset；项目 B 也有自己的 active dataset。
2. 通过 `get_active_filter(db, TbLedger.__table__, project_A, year)` 查询，
   **绝对** 只能看到项目 A 的行；反之亦然。
3. tenant_id 在本阶段恒为 'default'（所有物理行同一值），但 project_id 过滤仍
   足以阻止任何跨项目泄露 —— 这是 tenant_id 真正启用前的必要安全保证。

Fixture 模式：参考 `test_dataset_rollback_view_refactor.py`（SQLite 内存库 +
PG JSONB/UUID 降级兼容）。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQLite 兼容适配：PG JSONB/UUID 降级到 JSON/uuid（必须在 Base.metadata 构建前生效）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base  # noqa: E402
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.dataset_models  # noqa: E402, F401
from app.models.audit_platform_models import TbLedger  # noqa: E402
from app.models.dataset_models import LedgerDataset  # noqa: E402
from app.services.dataset_query import get_active_filter  # noqa: E402
from app.services.dataset_service import DatasetService  # noqa: E402


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
async def _seed_active_dataset_with_ledger(
    db: AsyncSession,
    project_id: uuid.UUID,
    year: int,
    rows: list[dict],
    tenant_id: str = "default",
) -> LedgerDataset:
    """创建 active dataset 并写入 tb_ledger 物理行。

    rows 每条 dict 至少包含 voucher_no / account_code / summary；
    其他公共字段由本函数自动填充。
    """
    dataset = await DatasetService.create_staged(
        db, project_id=project_id, year=year
    )
    await DatasetService.activate(db, dataset.id)
    await db.flush()

    for row in rows:
        db.add(
            TbLedger(
                tenant_id=tenant_id,
                project_id=project_id,
                year=year,
                company_code=row.get("company_code", "001"),
                voucher_date=row.get("voucher_date") or _make_date(year),
                voucher_no=row["voucher_no"],
                account_code=row["account_code"],
                account_name=row.get("account_name"),
                summary=row.get("summary"),
                dataset_id=dataset.id,
                is_deleted=False,
            )
        )
    await db.flush()
    return dataset


def _make_date(year: int):
    from datetime import date

    return date(year, 1, 1)


async def _active_ledger_rows(
    db: AsyncSession, project_id: uuid.UUID, year: int
) -> list[TbLedger]:
    condition = await get_active_filter(db, TbLedger.__table__, project_id, year)
    result = await db.execute(
        sa.select(TbLedger).where(condition).order_by(TbLedger.voucher_no)
    )
    return list(result.scalars().all())


# ===========================================================================
# 1) 两个项目各自有 active dataset：查询只能看到自己的行
# ===========================================================================
@pytest.mark.asyncio
async def test_active_filter_isolates_two_projects_with_active_datasets(
    db_session: AsyncSession,
):
    project_a = uuid.uuid4()
    project_b = uuid.uuid4()
    year = 2024

    await _seed_active_dataset_with_ledger(
        db_session,
        project_a,
        year,
        rows=[
            {"voucher_no": "A-001", "account_code": "1001", "summary": "A 现金收入"},
            {"voucher_no": "A-002", "account_code": "1002", "summary": "A 银行存款"},
        ],
    )
    await _seed_active_dataset_with_ledger(
        db_session,
        project_b,
        year,
        rows=[
            {"voucher_no": "B-001", "account_code": "2001", "summary": "B 应付账款"},
            {"voucher_no": "B-002", "account_code": "2002", "summary": "B 存货"},
            {"voucher_no": "B-003", "account_code": "2003", "summary": "B 主营业务"},
        ],
    )

    a_rows = await _active_ledger_rows(db_session, project_a, year)
    b_rows = await _active_ledger_rows(db_session, project_b, year)

    # 项目 A 只能看到自己的 2 行
    assert len(a_rows) == 2
    assert {r.voucher_no for r in a_rows} == {"A-001", "A-002"}
    for r in a_rows:
        assert r.project_id == project_a
        assert r.voucher_no.startswith("A-"), (
            f"项目 A 的查询泄露了项目 B 的凭证 {r.voucher_no}"
        )

    # 项目 B 只能看到自己的 3 行
    assert len(b_rows) == 3
    assert {r.voucher_no for r in b_rows} == {"B-001", "B-002", "B-003"}
    for r in b_rows:
        assert r.project_id == project_b
        assert r.voucher_no.startswith("B-"), (
            f"项目 B 的查询泄露了项目 A 的凭证 {r.voucher_no}"
        )


# ===========================================================================
# 2) 同一 year、同一 tenant_id 下，project_id 仍然是底线
# ===========================================================================
@pytest.mark.asyncio
async def test_same_tenant_same_year_but_different_projects_are_isolated(
    db_session: AsyncSession,
):
    project_a = uuid.uuid4()
    project_b = uuid.uuid4()
    year = 2024

    await _seed_active_dataset_with_ledger(
        db_session,
        project_a,
        year,
        rows=[{"voucher_no": "A-X", "account_code": "1001", "summary": "A only"}],
        tenant_id="default",
    )
    await _seed_active_dataset_with_ledger(
        db_session,
        project_b,
        year,
        rows=[{"voucher_no": "B-X", "account_code": "1001", "summary": "B only"}],
        tenant_id="default",
    )

    # 断言：两个项目的所有行 tenant_id 都是 'default'，但 project_id 过滤仍然完全隔离
    all_rows = (
        await db_session.execute(sa.select(TbLedger).order_by(TbLedger.voucher_no))
    ).scalars().all()
    assert len(all_rows) == 2
    assert all(r.tenant_id == "default" for r in all_rows), (
        "Sprint 7.5 阶段所有行 tenant_id 应恒为 'default'"
    )

    a_rows = await _active_ledger_rows(db_session, project_a, year)
    b_rows = await _active_ledger_rows(db_session, project_b, year)
    assert [r.voucher_no for r in a_rows] == ["A-X"]
    assert [r.voucher_no for r in b_rows] == ["B-X"]


# ===========================================================================
# 3) 项目 B 的 dataset 有相同 year 但不同 project：不能误读到 A
# ===========================================================================
@pytest.mark.asyncio
async def test_active_filter_does_not_leak_across_projects_with_overlapping_year(
    db_session: AsyncSession,
):
    """
    模拟现实场景：不同客户（project）可以共享同一会计年度。
    查询 A 项目 2024 年度时不应误取到 B 项目 2024 年度的数据集行。
    """
    project_a = uuid.uuid4()
    project_b = uuid.uuid4()
    year = 2024

    # 两个项目都在 2024 年度有 active dataset
    dataset_a = await _seed_active_dataset_with_ledger(
        db_session,
        project_a,
        year,
        rows=[{"voucher_no": "A-001", "account_code": "1001", "summary": "A"}],
    )
    dataset_b = await _seed_active_dataset_with_ledger(
        db_session,
        project_b,
        year,
        rows=[{"voucher_no": "B-001", "account_code": "1001", "summary": "B"}],
    )
    assert dataset_a.id != dataset_b.id

    # 即使两个 dataset 都是 active 且同 year、同 account_code，查询仍按 project 隔离
    a_rows = await _active_ledger_rows(db_session, project_a, year)
    b_rows = await _active_ledger_rows(db_session, project_b, year)

    assert len(a_rows) == 1 and a_rows[0].voucher_no == "A-001"
    assert len(b_rows) == 1 and b_rows[0].voucher_no == "B-001"

    # 直接物理行断言：两条数据 tenant_id / account_code / year 全部相同，
    # 只有 project_id 和 dataset_id 不同 —— 正是本测试要验证的隔离维度
    physical = (
        await db_session.execute(sa.select(TbLedger).order_by(TbLedger.voucher_no))
    ).scalars().all()
    assert len(physical) == 2
    assert {p.project_id for p in physical} == {project_a, project_b}
    assert {p.year for p in physical} == {year}
    assert {p.tenant_id for p in physical} == {"default"}


# ===========================================================================
# 4) 数据集 metadata 本身也按 project_id 隔离
# ===========================================================================
@pytest.mark.asyncio
async def test_active_dataset_lookup_is_project_scoped(db_session: AsyncSession):
    """项目 A 的 active dataset id 不应被查到项目 B。"""
    project_a = uuid.uuid4()
    project_b = uuid.uuid4()
    year = 2024

    a_dataset = await _seed_active_dataset_with_ledger(
        db_session, project_a, year, rows=[]
    )
    b_dataset = await _seed_active_dataset_with_ledger(
        db_session, project_b, year, rows=[]
    )

    a_active = await DatasetService.get_active_dataset_id(db_session, project_a, year)
    b_active = await DatasetService.get_active_dataset_id(db_session, project_b, year)

    assert a_active == a_dataset.id
    assert b_active == b_dataset.id
    assert a_active != b_active

    # ledger_datasets 本身也有 tenant_id 列，且恒为 'default'
    datasets = (
        await db_session.execute(sa.select(LedgerDataset))
    ).scalars().all()
    assert len(datasets) == 2
    assert all(d.tenant_id == "default" for d in datasets)
