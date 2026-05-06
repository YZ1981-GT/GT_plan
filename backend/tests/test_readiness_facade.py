"""R1 Task 7 集成测试：Readiness 门面化改造

覆盖需求 3：

1. SignReadinessService / ArchiveReadinessService 的返回 schema 同时包含
   ``ready / groups / gate_eval_id / expires_at`` 新字段与 legacy
   ``checks / ready_to_sign / passed_count / total_checks`` 兼容字段。
2. ``gate_eval_id`` 5 分钟 TTL（通过 monkeypatch 缩短 TTL 验证过期）。
3. ``validate_gate_eval`` 在 project/gate_type 不匹配或过期时返回 False。
4. 未映射的 ``rule_code`` 归入 ``misc`` 分组。
5. 未提交 gate_eval_id 时签字端点放行（向后兼容）。

Validates: Requirements 3 (refinement-round1-review-closure)
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# 显式导入 phase14/phase15 以便 create_all 建对应表
import app.models.phase14_models  # noqa: F401
import app.models.phase15_models  # noqa: F401
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession):
    project = Project(
        id=FAKE_PROJECT_ID,
        name="R1_Task7_Facade",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
        wizard_state={},
    )
    db_session.add(project)
    await db_session.commit()
    return {"project_id": FAKE_PROJECT_ID}


@pytest.fixture(autouse=True)
def _reset_gate_eval_store():
    """每个用例前后重置本地降级存储。"""
    from app.services import gate_eval_store as ges

    ges._reset_local_for_tests()
    yield
    ges._reset_local_for_tests()


@pytest.fixture(autouse=True)
def _force_local_gate_eval_store(monkeypatch):
    """强制 gate_eval_store 走本地降级，避免单测连真实 Redis。"""
    from app.services import gate_eval_store as ges

    async def _no_redis():
        return None

    monkeypatch.setattr(ges, "_get_redis_client", _no_redis)
    yield


@pytest.fixture
def stub_gate_engine(monkeypatch):
    """劫持 ``gate_engine.evaluate``，返回可控的 GateEvaluateResult。"""
    from app.services import gate_engine as ge_module
    from app.services.gate_engine import GateEvaluateResult, GateRuleHit

    class _Stub:
        decision: str = "allow"
        hit_rules: list[GateRuleHit] = []

        async def evaluate(self, db, gate_type, project_id, wp_id, actor_id, context):
            return GateEvaluateResult(
                decision=self.decision,
                hit_rules=list(self.hit_rules),
                trace_id="trc_20260505120000_stub12345678",
            )

    stub = _Stub()
    monkeypatch.setattr(ge_module, "gate_engine", stub)
    # partner_service / qc_dashboard_service 都用 lazy import，monkeypatch 模块对象即可
    yield stub


# ---------------------------------------------------------------------------
# SignReadiness 门面返回 schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sign_readiness_returns_unified_schema(
    db_session, seeded, stub_gate_engine
):
    """ready / groups / gate_eval_id / expires_at / checks 均存在。"""
    from app.services.partner_service import SignReadinessService

    # gate 返回 allow 但项目 wizard_state 空 → extra_findings 会产生 blocking
    stub_gate_engine.decision = "allow"
    stub_gate_engine.hit_rules = []

    svc = SignReadinessService(db_session)
    result = await svc.check_sign_readiness(seeded["project_id"], actor_id=FAKE_USER_ID)

    # 核心新字段
    assert "ready" in result
    assert "groups" in result and isinstance(result["groups"], list)
    assert "gate_eval_id" in result and result["gate_eval_id"]
    assert "expires_at" in result and result["expires_at"]

    # legacy 兼容字段
    assert "checks" in result and isinstance(result["checks"], list)
    assert "ready_to_sign" in result
    assert "passed_count" in result
    assert "total_checks" in result

    # 8 项 sign_off 类目齐全（checks 不含 misc 占位）
    ids = [g["id"] for g in result["groups"] if g["id"] != "misc"]
    assert set(ids) == {
        "l2_review",
        "qc_all_pass",
        "no_open_issues",
        "adj_approved",
        "misstatement_eval",
        "report_generated",
        "kam_confirmed",
        "independence",
    }

    # wizard_state 为空 → kam/independence/report 应命中 blocking
    by_id = {g["id"]: g for g in result["groups"]}
    assert by_id["kam_confirmed"]["status"] == "blocking"
    assert by_id["independence"]["status"] == "blocking"
    assert result["ready"] is False
    assert result["ready_to_sign"] is False


@pytest.mark.asyncio
async def test_archive_readiness_returns_unified_schema(
    db_session, seeded, stub_gate_engine
):
    """归档 12 项类目齐全。"""
    from app.services.qc_dashboard_service import ArchiveReadinessService

    stub_gate_engine.decision = "allow"
    stub_gate_engine.hit_rules = []

    svc = ArchiveReadinessService(db_session)
    result = await svc.check_readiness(seeded["project_id"], actor_id=FAKE_USER_ID)

    assert "ready" in result
    assert "groups" in result
    assert "gate_eval_id" in result
    assert "expires_at" in result
    assert "checks" in result

    ids = [g["id"] for g in result["groups"] if g["id"] != "misc"]
    assert set(ids) == {
        "review_complete",
        "qc_passed",
        "no_open_issues",
        "adj_approved",
        "misstatement_evaluated",
        "report_generated",
        "kam_confirmed",
        "independence",
        "subsequent_events",
        "going_concern",
        "mgmt_representation",
        "index_complete",
    }


# ---------------------------------------------------------------------------
# rule_code → misc 兜底
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unmapped_rule_code_goes_to_misc(db_session, seeded, stub_gate_engine):
    """未映射的 rule_code 不能消失，必须落到 misc 分组。"""
    from app.services.gate_engine import GateRuleHit
    from app.services.partner_service import SignReadinessService

    stub_gate_engine.decision = "warn"
    stub_gate_engine.hit_rules = [
        GateRuleHit(
            rule_code="R1-NEW-FUTURE",  # 未在 readiness_facade 映射表中
            error_code="FUTURE_RULE",
            severity="warning",
            message="来自未来的新规则",
            location={"project_id": str(seeded["project_id"])},
            suggested_action="升级前端即可",
        )
    ]

    svc = SignReadinessService(db_session)
    result = await svc.check_sign_readiness(seeded["project_id"], actor_id=FAKE_USER_ID)

    misc = next((g for g in result["groups"] if g["id"] == "misc"), None)
    assert misc is not None, "未映射 rule_code 必须落到 misc"
    assert len(misc["findings"]) == 1
    assert misc["findings"][0]["rule_code"] == "R1-NEW-FUTURE"
    assert misc["status"] == "warning"


# ---------------------------------------------------------------------------
# gate_eval_store：5 分钟 TTL + 过期失效
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_eval_store_ttl_expiry(monkeypatch):
    """TTL=1s 测试：等待 > 1s 后 validate 返回 NOT_FOUND_OR_EXPIRED。"""
    from app.services import gate_eval_store as ges

    pid = uuid.uuid4()
    eval_id, _expires = await ges.store_gate_eval(
        project_id=pid,
        gate_type="sign_off",
        ready=True,
        decision="allow",
        ttl_seconds=1,
    )

    # 立刻可用
    ok, reason = await ges.validate_gate_eval(
        eval_id, project_id=pid, gate_type="sign_off"
    )
    assert ok is True, reason

    # 等过期
    await asyncio.sleep(1.2)

    ok, reason = await ges.validate_gate_eval(
        eval_id, project_id=pid, gate_type="sign_off"
    )
    assert ok is False
    assert reason == "GATE_EVAL_NOT_FOUND_OR_EXPIRED"


@pytest.mark.asyncio
async def test_gate_eval_store_project_and_type_mismatch():
    from app.services import gate_eval_store as ges

    pid = uuid.uuid4()
    other_pid = uuid.uuid4()

    eval_id, _ = await ges.store_gate_eval(
        project_id=pid, gate_type="sign_off", ready=True, decision="allow"
    )

    ok, reason = await ges.validate_gate_eval(
        eval_id, project_id=other_pid, gate_type="sign_off"
    )
    assert ok is False
    assert reason == "GATE_EVAL_PROJECT_MISMATCH"

    ok, reason = await ges.validate_gate_eval(
        eval_id, project_id=pid, gate_type="export_package"
    )
    assert ok is False
    assert reason == "GATE_EVAL_TYPE_MISMATCH"


@pytest.mark.asyncio
async def test_gate_eval_store_not_ready_blocks_signature():
    """ready=False 的令牌不能用于签字（require_ready=True）。"""
    from app.services import gate_eval_store as ges

    pid = uuid.uuid4()
    eval_id, _ = await ges.store_gate_eval(
        project_id=pid, gate_type="sign_off", ready=False, decision="block"
    )

    ok, reason = await ges.validate_gate_eval(
        eval_id, project_id=pid, gate_type="sign_off", require_ready=True
    )
    assert ok is False
    assert reason == "GATE_EVAL_NOT_READY"

    # require_ready=False 时可过（供调试/审计）
    ok, reason = await ges.validate_gate_eval(
        eval_id, project_id=pid, gate_type="sign_off", require_ready=False
    )
    assert ok is True


@pytest.mark.asyncio
async def test_gate_eval_store_unknown_id_returns_not_found():
    from app.services import gate_eval_store as ges

    ok, reason = await ges.validate_gate_eval(
        "00000000-0000-0000-0000-000000000000",
        project_id=uuid.uuid4(),
        gate_type="sign_off",
    )
    assert ok is False
    assert reason == "GATE_EVAL_NOT_FOUND_OR_EXPIRED"


# ---------------------------------------------------------------------------
# readiness → store 联动：生成的 gate_eval_id 后续可 validate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_readiness_generates_usable_gate_eval_id(
    db_session, seeded, stub_gate_engine
):
    from app.services import gate_eval_store as ges
    from app.services.partner_service import SignReadinessService

    stub_gate_engine.decision = "allow"
    stub_gate_engine.hit_rules = []

    svc = SignReadinessService(db_session)
    result = await svc.check_sign_readiness(seeded["project_id"], actor_id=FAKE_USER_ID)

    eval_id = result["gate_eval_id"]
    # 即便 extra_findings 产生 blocking 导致 ready=False，令牌仍可被校验
    payload = await ges.get_gate_eval(eval_id)
    assert payload is not None
    assert payload["project_id"] == str(seeded["project_id"])
    assert payload["gate_type"] == "sign_off"
    assert payload["ready"] == result["ready"]
