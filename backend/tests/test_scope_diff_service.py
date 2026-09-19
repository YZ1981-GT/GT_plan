"""合并范围校对 scope-diff / sync-scope 验证（group-tree-architecture Task 12.1）。

覆盖：
- compute_scope_diff: 正确的 T\\S（in_tree_not_scope）与 S\\T（in_scope_not_tree）集合差
- sync_scope: 仅新增缺失代码并返回新增数
- sync_scope: 绝不删除已存在的 scope 行（scope 行数只增不减）
- 端点挂载（in-process ASGI httpx），路径 /api/consolidation/{pid}/scope-diff & /sync-scope

property-style: Property 10（精确集合差）。
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
import sqlalchemy as sa
import hypothesis.strategies as st
from hypothesis import given, settings, HealthCheck
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, UserRole
from app.models.consolidation_models import ConsolScope
from app.models.core import Project
from app.services.scope_diff_service import compute_scope_diff, sync_scope

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

USER_ID = uuid.uuid4()

ULTIMATE = "91110000000000000U"
SUB_A = "91110000000000001A"
SUB_B = "91110000000000002B"
YEAR = 2025

# 合并母项目固定 id（供端点路径使用）
CONSOL_PID = uuid.uuid4()


class _FakeUser:
    def __init__(self, uid: uuid.UUID, role: UserRole = UserRole.admin):
        self.id = uid
        self.username = "test_user"
        self.email = "u@test.com"
        self.role = role
        self.is_active = True
        self.is_deleted = False


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


async def _seed_projects(session: AsyncSession) -> None:
    """合并母公司(根) + 子公司A + 子公司B（树形：A 挂根、B 挂 A）。"""
    session.add(Project(
        id=CONSOL_PID,
        name="集团母公司_2025",
        client_name="集团母公司",
        company_code=ULTIMATE,
        parent_company_code=None,
        ultimate_company_code=ULTIMATE,
        report_scope="consolidated",
        audit_period_end=date(YEAR, 12, 31),
    ))
    session.add(Project(
        id=uuid.uuid4(),
        name="子公司A_2025",
        client_name="子公司A",
        company_code=SUB_A,
        parent_company_code=ULTIMATE,
        ultimate_company_code=ULTIMATE,
        report_scope="standalone",
        audit_period_end=date(YEAR, 12, 31),
    ))
    session.add(Project(
        id=uuid.uuid4(),
        name="子公司B_2025",
        client_name="子公司B",
        company_code=SUB_B,
        parent_company_code=SUB_A,
        ultimate_company_code=ULTIMATE,
        report_scope="standalone",
        audit_period_end=date(YEAR, 12, 31),
    ))
    await session.commit()


# ---------------------------------------------------------------------------
# compute_scope_diff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scope_diff_tree_not_scope(db_session: AsyncSession):
    """树形有 A/B，scope 为空 → in_tree_not_scope = {A, B}，in_scope_not_tree 空。"""
    await _seed_projects(db_session)
    diff = await compute_scope_diff(db_session, CONSOL_PID)
    tree_only = {d["company_code"] for d in diff["in_tree_not_scope"]}
    scope_only = {d["company_code"] for d in diff["in_scope_not_tree"]}
    assert tree_only == {SUB_A, SUB_B}
    assert scope_only == set()
    # company_name 已带出
    name_map = {d["company_code"]: d["company_name"] for d in diff["in_tree_not_scope"]}
    assert name_map[SUB_A] == "子公司A"


@pytest.mark.asyncio
async def test_scope_diff_exact_set_difference(db_session: AsyncSession):
    """Property 10: T={A,B}, S={A, X} → T\\S={B}, S\\T={X}。"""
    await _seed_projects(db_session)
    # scope 含 A（在树中）和 X（不在树中）
    db_session.add(ConsolScope(
        project_id=CONSOL_PID, year=YEAR, company_code=SUB_A,
        company_name="子公司A", is_included=True,
    ))
    db_session.add(ConsolScope(
        project_id=CONSOL_PID, year=YEAR, company_code="91110000000000009X",
        company_name="范围外企业X", is_included=True,
    ))
    await db_session.commit()

    diff = await compute_scope_diff(db_session, CONSOL_PID)
    tree_only = {d["company_code"] for d in diff["in_tree_not_scope"]}
    scope_only = {d["company_code"] for d in diff["in_scope_not_tree"]}
    assert tree_only == {SUB_B}          # T \ S
    assert scope_only == {"91110000000000009X"}  # S \ T


@pytest.mark.asyncio
async def test_scope_diff_excluded_scope_not_counted(db_session: AsyncSession):
    """is_included=false 的 scope 行不计入 S。"""
    await _seed_projects(db_session)
    db_session.add(ConsolScope(
        project_id=CONSOL_PID, year=YEAR, company_code=SUB_A,
        company_name="子公司A", is_included=False,
    ))
    await db_session.commit()
    diff = await compute_scope_diff(db_session, CONSOL_PID)
    tree_only = {d["company_code"] for d in diff["in_tree_not_scope"]}
    # A 虽在 scope 表，但 is_included=false → 不算 S → A 仍在 in_tree_not_scope
    assert tree_only == {SUB_A, SUB_B}


# ---------------------------------------------------------------------------
# sync_scope
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_scope_adds_missing_only(db_session: AsyncSession):
    """sync_scope 新增缺失代码并返回新增数；已存在跳过不重复。"""
    await _seed_projects(db_session)
    # A 已在 scope
    db_session.add(ConsolScope(
        project_id=CONSOL_PID, year=YEAR, company_code=SUB_A,
        company_name="子公司A", is_included=True,
    ))
    await db_session.commit()

    added = await sync_scope(db_session, CONSOL_PID, [SUB_A, SUB_B])
    await db_session.commit()
    assert added == 1  # 只新增 B（A 已存在）

    rows = (await db_session.execute(
        sa.select(ConsolScope).where(
            ConsolScope.project_id == CONSOL_PID,
            ConsolScope.is_deleted.is_(False),
        )
    )).scalars().all()
    codes = {r.company_code for r in rows}
    assert codes == {SUB_A, SUB_B}
    # 新增行 company_name 取自同集团项目名
    b_row = next(r for r in rows if r.company_code == SUB_B)
    assert b_row.company_name == "子公司B"
    assert b_row.is_included is True


@pytest.mark.asyncio
async def test_sync_scope_never_deletes(db_session: AsyncSession):
    """sync_scope 绝不删除已存在 scope 行：scope 行数只增不减（Req 9.4）。"""
    await _seed_projects(db_session)
    # 预置一个树形中不存在的范围外企业 X
    db_session.add(ConsolScope(
        project_id=CONSOL_PID, year=YEAR, company_code="91110000000000009X",
        company_name="范围外企业X", is_included=True,
    ))
    await db_session.commit()

    before = (await db_session.execute(
        sa.select(sa.func.count()).select_from(ConsolScope).where(
            ConsolScope.project_id == CONSOL_PID,
            ConsolScope.is_deleted.is_(False),
        )
    )).scalar_one()

    # 同步只含 A/B（不含 X）——X 不应被删除
    await sync_scope(db_session, CONSOL_PID, [SUB_A, SUB_B])
    await db_session.commit()

    after_rows = (await db_session.execute(
        sa.select(ConsolScope).where(
            ConsolScope.project_id == CONSOL_PID,
            ConsolScope.is_deleted.is_(False),
        )
    )).scalars().all()
    after_codes = {r.company_code for r in after_rows}
    # X 仍在（未被删），A/B 已加入 → 行数从 1 增到 3
    assert "91110000000000009X" in after_codes
    assert {SUB_A, SUB_B} <= after_codes
    assert len(after_rows) == before + 2


# ---------------------------------------------------------------------------
# 端点挂载验证
# ---------------------------------------------------------------------------


def _make_app(db_session: AsyncSession) -> FastAPI:
    from app.routers.consol_scope_diff import router as csd_router

    app = FastAPI()
    app.include_router(csd_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return _FakeUser(USER_ID)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


@pytest.mark.asyncio
async def test_endpoints_mounted(db_session: AsyncSession):
    """scope-diff 与 sync-scope 端点挂载且返回预期结构。"""
    await _seed_projects(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        diff_resp = await ac.get(f"/api/consolidation/{CONSOL_PID}/scope-diff")
        assert diff_resp.status_code == 200, diff_resp.text
        diff = diff_resp.json()
        assert {d["company_code"] for d in diff["in_tree_not_scope"]} == {SUB_A, SUB_B}

        sync_resp = await ac.post(
            f"/api/consolidation/{CONSOL_PID}/sync-scope",
            json={"company_codes": [SUB_A, SUB_B]},
        )
        assert sync_resp.status_code == 200, sync_resp.text
        assert sync_resp.json()["added"] == 2

        # 同步后再查 diff，in_tree_not_scope 应清空
        diff_resp2 = await ac.get(f"/api/consolidation/{CONSOL_PID}/scope-diff")
        assert diff_resp2.json()["in_tree_not_scope"] == []


# ===========================================================================
# Feature: group-tree-architecture, Property 10: Scope diff set-difference correctness
# Validates: Requirements 9.2, 9.3
#
# hypothesis (max_examples=5): 对任意树成员集合 T 与合并范围成员集合 S，
# compute_scope_diff 精确产出 in_tree_not_scope = T \ S，in_scope_not_tree = S \ T。
#
# 设计：种子化一棵固定子公司池的集团树（T = 池中被实际挂入树的子公司 code），
# 用 hypothesis 选取 S 的组成（树内子集 + 树外额外 code），在每个 example
# 内用全新的 in-memory engine/session 做 DB 操作，避免跨 example 复用 session。
# ===========================================================================

# 固定子公司代码池（树成员候选）；scope-diff 仅做字符串集合差，不校验 USCC 格式
_TREE_CODE_POOL = [
    "91110000000000010A",
    "91110000000000011B",
    "91110000000000012C",
    "91110000000000013D",
]
# 树外额外代码池（仅可能出现在 scope）
_SCOPE_ONLY_POOL = [
    "91110000000000091X",
    "91110000000000092Y",
    "91110000000000093Z",
]


async def _seed_tree_with_codes(session: AsyncSession, pid: uuid.UUID, sub_codes: list[str]) -> None:
    """种子化合并母项目 + 指定子公司代码（全部直接挂在 ultimate 根下）。"""
    session.add(Project(
        id=pid,
        name="集团母公司_PBT",
        client_name="集团母公司",
        company_code=ULTIMATE,
        parent_company_code=None,
        ultimate_company_code=ULTIMATE,
        report_scope="consolidated",
        audit_period_end=date(YEAR, 12, 31),
    ))
    for i, code in enumerate(sub_codes):
        session.add(Project(
            id=uuid.uuid4(),
            name=f"子公司_{code}",
            client_name=f"子公司_{code}",
            company_code=code,
            parent_company_code=ULTIMATE,
            ultimate_company_code=ULTIMATE,
            report_scope="standalone",
            audit_period_end=date(YEAR, 12, 31),
        ))
    await session.commit()


@given(
    tree_codes=st.lists(st.sampled_from(_TREE_CODE_POOL), min_size=1, max_size=4, unique=True),
    scope_in_tree=st.lists(st.sampled_from(_TREE_CODE_POOL), max_size=4, unique=True),
    scope_extra=st.lists(st.sampled_from(_SCOPE_ONLY_POOL), max_size=3, unique=True),
)
@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_property10_scope_diff_exact_set_difference(
    tree_codes: list[str], scope_in_tree: list[str], scope_extra: list[str]
):
    """Property 10：in_tree_not_scope == sorted(T\\S)，in_scope_not_tree == sorted(S\\T)。"""
    # 每个 example 使用全新的 in-memory engine，避免 hypothesis 跨 example 复用 session
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    pid = uuid.uuid4()
    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)

        # T = 实际挂入树的子公司代码集合
        T = set(tree_codes)
        # S = 树内子集 ∩ T（只有真在树里的才算"树内 scope"，再并上树外额外代码）
        S = (set(scope_in_tree) & T) | set(scope_extra)

        async with factory() as db:
            await _seed_tree_with_codes(db, pid, list(T))
            # 写入 consol_scope（S 全部 is_included=true）
            for code in S:
                db.add(ConsolScope(
                    project_id=pid, year=YEAR, company_code=code,
                    company_name=f"范围_{code}", is_included=True,
                ))
            await db.commit()

            diff = await compute_scope_diff(db, pid)

        in_tree_not_scope = {d["company_code"] for d in diff["in_tree_not_scope"]}
        in_scope_not_tree = {d["company_code"] for d in diff["in_scope_not_tree"]}

        assert in_tree_not_scope == (T - S), f"T={T} S={S} 期望 T\\S={T - S} 实得 {in_tree_not_scope}"
        assert in_scope_not_tree == (S - T), f"T={T} S={S} 期望 S\\T={S - T} 实得 {in_scope_not_tree}"

        # 验证返回列表已按 company_code 排序（服务契约）
        codes_tree = [d["company_code"] for d in diff["in_tree_not_scope"]]
        codes_scope = [d["company_code"] for d in diff["in_scope_not_tree"]]
        assert codes_tree == sorted(codes_tree)
        assert codes_scope == sorted(codes_scope)
    finally:
        await eng.dispose()
