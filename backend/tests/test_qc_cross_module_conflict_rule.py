"""V3 Req 7.6：未调解跨模块冲突守门规则单元测试

V3-CROSS-MODULE-CONFLICT-UNRESOLVED 在 sign_off 入口检查 pending 冲突计数。

覆盖：
- test_no_pending_passes — 无 pending → check 返回 None
- test_pending_blocks_sign_off — 1+ pending → 阻断且 GateRuleHit 字段齐全
- test_resolved_does_not_block — 已 resolve / auto_resolve 不计入
- test_rule_registered_to_sign_off — 模块导入即注册（自动注册铁律）

Validates: Requirements 7.6
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQLite 兼容 JSONB + ARRAY（必须先于模型导入）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

from app.models.base import Base  # noqa: E402

# 注册测试所需模型
import app.models.core  # noqa: E402, F401
import app.models.audit_log_models  # noqa: E402, F401
import app.models.v3_refinement_models  # noqa: E402, F401

# 触发 CrossModuleConflictUnresolvedRule 自动注册到 sign_off
from app.services.gate_rules_cross_module_conflict import (  # noqa: E402, F401
    CrossModuleConflictUnresolvedRule,
)
from app.services import conflict_resolution_service as svc  # noqa: E402
from app.services.gate_engine import rule_registry  # noqa: E402
from app.models.phase14_enums import GateType, GateSeverity  # noqa: E402


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        tables_to_create = [
            Base.metadata.tables["users"],
            Base.metadata.tables["projects"],
            Base.metadata.tables["audit_log_entries"],
            Base.metadata.tables["cross_module_conflicts"],
        ]
        await conn.run_sync(Base.metadata.create_all, tables=tables_to_create)

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def user_and_project(db_session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    from app.models.base import ProjectStatus, UserRole
    from app.models.core import Project, User

    user_id = uuid.uuid4()
    project_id = uuid.uuid4()

    user = User(
        id=user_id,
        username=f"tester-{user_id.hex[:8]}",
        email=f"{user_id.hex[:8]}@test.local",
        hashed_password="hashed",
        role=UserRole.auditor,
        is_active=True,
    )
    project = Project(
        id=project_id,
        name="测试项目",
        client_name="测试客户",
        status=ProjectStatus.execution,
    )
    db_session.add(user)
    db_session.add(project)
    await db_session.commit()
    return user_id, project_id


async def _enqueue_pending(
    db_session: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    target_module: str = "disclosure",
    target_id: uuid.UUID | None = None,
):
    # _emit_enqueued_event 内部 try/except 已兜底无 event_bus 场景
    return await svc.enqueue(
        db=db_session,
        project_id=project_id,
        source_module="workpaper",
        source_id=uuid.uuid4(),
        target_module=target_module,
        target_id=target_id or uuid.uuid4(),
        target_field="amount",
        upstream_value="100",
        manual_value="200",
        user_id=user_id,
    )


@pytest.mark.asyncio
async def test_no_pending_passes(
    db_session: AsyncSession,
    user_and_project: tuple[uuid.UUID, uuid.UUID],
):
    """无 pending 冲突 → check 返回 None。"""
    _user_id, project_id = user_and_project
    rule = CrossModuleConflictUnresolvedRule()
    hit = await rule.check(db_session, {"project_id": project_id})
    assert hit is None


@pytest.mark.asyncio
async def test_pending_blocks_sign_off(
    db_session: AsyncSession,
    user_and_project: tuple[uuid.UUID, uuid.UUID],
):
    """存在 1+ pending 冲突 → block + 字段齐全。"""
    user_id, project_id = user_and_project
    conflict = await _enqueue_pending(db_session, project_id, user_id)

    rule = CrossModuleConflictUnresolvedRule()
    hit = await rule.check(db_session, {"project_id": project_id})

    assert hit is not None
    assert hit.rule_code == "V3-CROSS-MODULE-CONFLICT-UNRESOLVED"
    assert hit.error_code == "CROSS_MODULE_CONFLICT_UNRESOLVED"
    assert hit.severity == GateSeverity.blocking
    assert hit.location["pending_count"] == 1
    assert str(conflict.id) in hit.location["sample_conflict_ids"]
    assert hit.suggested_action  # 非空


@pytest.mark.asyncio
async def test_resolved_does_not_block(
    db_session: AsyncSession,
    user_and_project: tuple[uuid.UUID, uuid.UUID],
):
    """resolve 后 status 不再是 pending → check 返回 None。"""
    user_id, project_id = user_and_project
    conflict = await _enqueue_pending(db_session, project_id, user_id)

    # 调解为 keep_manual
    await svc.resolve(
        db=db_session,
        conflict_id=conflict.id,
        resolution="keep_manual",
        user_id=user_id,
    )

    rule = CrossModuleConflictUnresolvedRule()
    hit = await rule.check(db_session, {"project_id": project_id})
    assert hit is None


def test_rule_registered_to_sign_off():
    """模块导入即注册到 sign_off gate（自动注册铁律）。"""
    rules = rule_registry.get_rules(GateType.sign_off)
    rule_codes = [getattr(r, "rule_code", None) for r in rules]
    assert "V3-CROSS-MODULE-CONFLICT-UNRESOLVED" in rule_codes, (
        f"V3-CROSS-MODULE-CONFLICT-UNRESOLVED 应注册到 sign_off，实际只有 {rule_codes}"
    )

    target = next(
        (
            r
            for r in rules
            if getattr(r, "rule_code", None) == "V3-CROSS-MODULE-CONFLICT-UNRESOLVED"
        ),
        None,
    )
    assert target is not None
    assert isinstance(target, CrossModuleConflictUnresolvedRule)
