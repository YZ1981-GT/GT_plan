"""V164 / B3 — 未更正错报 durable 幂等（source_identity）服务级守卫。

背景：底稿"推送错报至 A13"经 useA13MisstatementBridge → createMisstatement 落库，去重此前
仅靠前端 5s 内存 Map（跨窗/刷新失效，真栈实测 48s 两次点击产生 2 条重复）。本测试锁定服务端
durable 幂等：同项目 + 同 source_identity 只落一条，重复推送返回既有记录（deduplicated=True）。

行为级（非字符串）：真跑 UnadjustedMisstatementService.create_misstatement 两次，断言库里只 1 条。
"""
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.audit_platform_models import MisstatementType, UnadjustedMisstatement
from app.models.audit_platform_schemas import MisstatementCreate
from app.models.core import Project, ProjectStatus, ProjectType
from app.services.misstatement_service import UnadjustedMisstatementService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def pid(db: AsyncSession):
    p = Project(
        id=uuid.uuid4(), name="幂等测试_2025", client_name="幂等测试",
        project_type=ProjectType.annual, status=ProjectStatus.planning,
    )
    db.add(p)
    await db.flush()
    return p.id


def _payload(identity: str | None, *, amount="7000", desc="口岸差异测试"):
    return MisstatementCreate(
        year=2025,
        misstatement_description=desc,
        affected_account_code="6001",
        affected_account_name="营业收入",
        misstatement_amount=Decimal(amount),
        misstatement_type=MisstatementType.factual,
        source_wp_code="D4-16",
        source_identity=identity,
    )


async def _count(db: AsyncSession, project_id) -> int:
    r = await db.execute(
        sa.select(sa.func.count()).select_from(UnadjustedMisstatement).where(
            UnadjustedMisstatement.project_id == project_id,
            UnadjustedMisstatement.is_deleted == sa.false(),
        )
    )
    return int(r.scalar() or 0)


@pytest.mark.asyncio
async def test_same_source_identity_dedups_across_calls(db: AsyncSession, pid):
    """**Validates: B3** 同 source_identity 重复推送只落一条，第二次返回既有记录 deduplicated=True。"""
    svc = UnadjustedMisstatementService(db)
    ident = "D4-16|口岸差异测试|7000|6001|factual"

    r1 = await svc.create_misstatement(pid, _payload(ident))
    assert r1.deduplicated is False
    assert await _count(db, pid) == 1

    # 第二次（模拟跨会话/超窗重复点击）—— 不新增，返回既有
    r2 = await svc.create_misstatement(pid, _payload(ident))
    assert r2.deduplicated is True
    assert r2.id == r1.id
    assert await _count(db, pid) == 1  # 真栈曾产生 2 条，现恒为 1


@pytest.mark.asyncio
async def test_different_identity_creates_separate(db: AsyncSession, pid):
    """**Validates: B3** 不同 source_identity（不同金额/描述）是两笔独立错报，不被误吞。"""
    svc = UnadjustedMisstatementService(db)
    await svc.create_misstatement(pid, _payload("D4-16|A|7000|6001|factual", amount="7000", desc="A"))
    await svc.create_misstatement(pid, _payload("D4-16|B|3000|6001|factual", amount="3000", desc="B"))
    assert await _count(db, pid) == 2


@pytest.mark.asyncio
async def test_null_identity_bypasses_dedup(db: AsyncSession, pid):
    """**Validates: B3 兼容** source_identity 为空（手工新建/AJE 路径）不参与幂等，每次都新增。"""
    svc = UnadjustedMisstatementService(db)
    await svc.create_misstatement(pid, _payload(None))
    await svc.create_misstatement(pid, _payload(None))
    assert await _count(db, pid) == 2  # 无 identity → 不去重，两条


@pytest.mark.asyncio
async def test_dedup_type_dimension(db: AsyncSession, pid):
    """**Validates: B3 + CAS1251** 同金额同描述但类型不同（factual vs projected）是两笔（identity 含 type）。"""
    svc = UnadjustedMisstatementService(db)
    p1 = _payload("D4-16|同款|7000|6001|factual")
    p2 = MisstatementCreate(
        year=2025, misstatement_description="口岸差异测试",
        affected_account_code="6001", affected_account_name="营业收入",
        misstatement_amount=Decimal("7000"),
        misstatement_type=MisstatementType.projected,
        source_wp_code="D4-16",
        source_identity="D4-16|同款|7000|6001|projected",
    )
    await svc.create_misstatement(pid, p1)
    await svc.create_misstatement(pid, p2)
    assert await _count(db, pid) == 2
