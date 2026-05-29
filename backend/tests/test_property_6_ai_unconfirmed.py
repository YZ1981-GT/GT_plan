"""Property 6: AI 内容确认不变量 — hypothesis 属性测试

V3 收官增强 Req 6.7。

不变量定义：

P6-INV-1：∀ project P，若存在 ≥1 条 ai_content_log.confirm_action='pending'，
  则 AIContentMustBeConfirmedRule.check 必返回 GateRuleHit
  (severity=blocking, error_code=AI_CONTENT_NOT_CONFIRMED, via=ai_content_log)。

P6-INV-2：∀ project P，若 ai_content_log 全部为非 pending 状态（或为空），
  且 parsed_data 不含未确认 AI 内容，则 check 返回 None（通过）。

P6-INV-3：sign_off 全链路集成 — gate_engine.evaluate(GateType.sign_off, ...)
  在存在 pending 时 decision='block'（语义等价 HTTP 422 阻断）。

调速：max_examples=20-30，列表 size 5-50。

Validates: Requirements 6.7
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from hypothesis import HealthCheck, given, settings, strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# SQLite 兼容
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

from app.models.base import Base  # noqa: E402

# 仅注册测试所需的模型
import app.models.core  # noqa: E402, F401
import app.models.audit_log_models  # noqa: E402, F401
import app.models.v3_refinement_models  # noqa: E402, F401
import app.models.phase14_models  # noqa: E402, F401  — gate_decisions / trace_events

from app.models.base import ProjectStatus, ProjectType, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.phase14_enums import GateDecisionResult, GateType  # noqa: E402
from app.services import ai_content_log_service  # noqa: E402

# 触发 AIContentMustBeConfirmedRule 自动注册到 sign_off
from app.services.gate_rules_ai_content import (  # noqa: E402, F401
    AIContentMustBeConfirmedRule,
)
from app.services.gate_engine import gate_engine, rule_registry  # noqa: E402


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


# 4 种合法状态
ACTIONS = ("pending", "confirmed", "revised", "rejected")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_db_with_user_project() -> tuple[
    async_sessionmaker, AsyncSession, uuid.UUID, uuid.UUID
]:
    """新建 DB + 写一条 user/project，返回 (factory, session, user_id, project_id)。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        tables_to_create = [
            Base.metadata.tables["users"],
            Base.metadata.tables["projects"],
            Base.metadata.tables["audit_log_entries"],
            Base.metadata.tables["ai_content_log"],
            Base.metadata.tables["gate_decisions"],
            Base.metadata.tables["trace_events"],
        ]
        await conn.run_sync(Base.metadata.create_all, tables=tables_to_create)

    factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    session = factory()

    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    user = User(
        id=user_id,
        username=f"pbt-{user_id.hex[:8]}",
        email=f"{user_id.hex[:8]}@pbt.local",
        hashed_password="x",
        role=UserRole.auditor,
        is_active=True,
    )
    project = Project(
        id=project_id,
        name="P6 PBT 测试项目",
        client_name="P6 客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
    )
    session.add(user)
    session.add(project)
    await session.commit()
    return factory, session, user_id, project_id


async def _seed_logs_with_actions(
    session: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    actions: list[str],
) -> None:
    """按给定 actions 列表创建 ai_content_log 记录并应用相应状态变迁。"""
    pending_logs = []
    for idx, action in enumerate(actions):
        log = await ai_content_log_service.create(
            db=session,
            project_id=project_id,
            user_id=user_id,
            instance_type="workpaper",
            instance_id=uuid.uuid4(),
            target_cell="narrative",
            model="qwen3.5-27b",
            prompt_hash=None,
            content_hash=f"{idx:0>64}",
            generated_content=f"AI 输出 #{idx}",
            confidence=Decimal("0.80"),
        )
        pending_logs.append((log, action))
    await session.flush()

    # 应用每条记录的目标状态（pending 不需要变迁）
    for log, action in pending_logs:
        if action == "confirmed":
            await ai_content_log_service.confirm(
                db=session, log_id=log.id, user_id=user_id
            )
        elif action == "revised":
            await ai_content_log_service.revise(
                db=session,
                log_id=log.id,
                user_id=user_id,
                revised_content=f"修订: {log.generated_content}",
            )
        elif action == "rejected":
            await ai_content_log_service.reject(
                db=session, log_id=log.id, user_id=user_id
            )
        # pending: 不变迁

    await session.commit()


# ---------------------------------------------------------------------------
# Property 6.7-1：∃ pending → check 命中
# ---------------------------------------------------------------------------


class TestProperty6PendingBlocks:
    """**Validates: Requirements 6.7**

    P6-INV-1：∀ project, ≥1 pending → check returns blocking GateRuleHit。
    """

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    @given(
        # 列表 5-50，但保证至少 1 条 pending（通过 list+min size 1 + pending 注入）
        non_pending_actions=st.lists(
            st.sampled_from(["confirmed", "revised", "rejected"]),
            min_size=0,
            max_size=49,
        ),
        pending_count=st.integers(min_value=1, max_value=10),
    )
    @pytest.mark.asyncio
    async def test_pending_blocks(
        self, non_pending_actions: list[str], pending_count: int
    ):
        """∀ project, 至少 1 条 pending → check 必返回 blocking 命中。

        **Validates: Requirements 6.7**
        """
        factory, session, user_id, project_id = await _setup_db_with_user_project()
        try:
            actions = ["pending"] * pending_count + non_pending_actions
            await _seed_logs_with_actions(session, user_id, project_id, actions)

            rule = AIContentMustBeConfirmedRule()
            hit = await rule.check(session, {"project_id": project_id})

            assert hit is not None, (
                f"应命中（pending={pending_count}, total={len(actions)}）但返回 None"
            )
            assert hit.error_code == "AI_CONTENT_NOT_CONFIRMED"
            assert hit.severity == "blocking"
            assert hit.rule_code == "R3-AI-UNCONFIRMED"
            assert hit.location.get("via") == "ai_content_log"
            # pending_count 与实际 pending 一致
            assert hit.location.get("pending_count") == pending_count
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Property 6.7-2：0 pending → check 通过
# ---------------------------------------------------------------------------


class TestProperty6NoPendingPasses:
    """**Validates: Requirements 6.7**

    P6-INV-2：∀ project, 0 pending（log 表全为 confirmed/revised/rejected
    或为空，且无 parsed_data 残留）→ check 返回 None。
    """

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    @given(
        non_pending_actions=st.lists(
            st.sampled_from(["confirmed", "revised", "rejected"]),
            min_size=0,
            max_size=50,
        ),
    )
    @pytest.mark.asyncio
    async def test_no_pending_passes(self, non_pending_actions: list[str]):
        """∀ project, 0 pending → check 必返回 None。

        **Validates: Requirements 6.7**
        """
        factory, session, user_id, project_id = await _setup_db_with_user_project()
        try:
            await _seed_logs_with_actions(
                session, user_id, project_id, non_pending_actions
            )

            rule = AIContentMustBeConfirmedRule()
            hit = await rule.check(session, {"project_id": project_id})

            assert hit is None, (
                f"应通过（0 pending, total={len(non_pending_actions)}）但命中: "
                f"{hit and hit.error_code}"
            )
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Property 6.7-3：gate_engine.evaluate(sign_off) 全链路集成 — pending 时 block
# ---------------------------------------------------------------------------


class TestProperty6SignOffIntegration:
    """**Validates: Requirements 6.7**

    P6-INV-3：sign_off 全链路：gate_engine.evaluate(GateType.sign_off, ...)
    在含 pending 时 decision='block'，等价 HTTP 422 阻断。
    """

    @settings(
        max_examples=15,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    @given(
        actions=st.lists(
            st.sampled_from(ACTIONS), min_size=1, max_size=30
        ),
    )
    @pytest.mark.asyncio
    async def test_sign_off_blocks_when_any_pending(self, actions: list[str]):
        """∀ project，actions 含 pending → sign_off block；全无 pending → not block。

        **Validates: Requirements 6.7**
        """
        factory, session, user_id, project_id = await _setup_db_with_user_project()
        try:
            await _seed_logs_with_actions(session, user_id, project_id, actions)

            result = await gate_engine.evaluate(
                db=session,
                gate_type=GateType.sign_off,
                project_id=project_id,
                wp_id=None,
                actor_id=user_id,
                context={"action": "sign_off"},
            )

            has_pending = any(a == "pending" for a in actions)
            if has_pending:
                # 必须 block 且命中 R3-AI-UNCONFIRMED
                assert result.decision == GateDecisionResult.block, (
                    f"含 pending 应 block，实际 {result.decision}"
                )
                rule_codes = [h.rule_code for h in result.hit_rules]
                assert "R3-AI-UNCONFIRMED" in rule_codes, (
                    f"应命中 R3-AI-UNCONFIRMED，实际命中 {rule_codes}"
                )
                error_codes = [h.error_code for h in result.hit_rules]
                assert "AI_CONTENT_NOT_CONFIRMED" in error_codes
            else:
                # 全无 pending → 至少 R3-AI-UNCONFIRMED 不再命中
                rule_codes = [h.rule_code for h in result.hit_rules]
                assert "R3-AI-UNCONFIRMED" not in rule_codes, (
                    f"无 pending 不应命中 R3-AI-UNCONFIRMED，实际命中 {rule_codes}"
                )
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# 传统断言：固定场景 sanity check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sanity_rule_registered_to_sign_off():
    """**Validates: Requirements 6.7** — 模块导入即注册到 sign_off。"""
    rules = rule_registry.get_rules(GateType.sign_off)
    rule_codes = [getattr(r, "rule_code", None) for r in rules]
    assert "R3-AI-UNCONFIRMED" in rule_codes


@pytest.mark.asyncio
async def test_sanity_empty_log_passes():
    """**Validates: Requirements 6.7** — 空 ai_content_log + 干净 parsed_data → check 通过。"""
    factory, session, user_id, project_id = await _setup_db_with_user_project()
    try:
        rule = AIContentMustBeConfirmedRule()
        hit = await rule.check(session, {"project_id": project_id})
        assert hit is None
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_sanity_single_pending_blocks_sign_off():
    """**Validates: Requirements 6.7** — 单条 pending → sign_off block + R3-AI-UNCONFIRMED。"""
    factory, session, user_id, project_id = await _setup_db_with_user_project()
    try:
        await _seed_logs_with_actions(session, user_id, project_id, ["pending"])

        result = await gate_engine.evaluate(
            db=session,
            gate_type=GateType.sign_off,
            project_id=project_id,
            wp_id=None,
            actor_id=user_id,
            context={"action": "sign_off"},
        )
        assert result.decision == GateDecisionResult.block
        assert any(
            h.error_code == "AI_CONTENT_NOT_CONFIRMED" for h in result.hit_rules
        )
    finally:
        await session.close()
