"""R1 Task 8 单元/集成测试：UnconvertedRejectedAJERule + EventCascadeHealthRule

覆盖需求 3 验收 7/8：

1. UnconvertedRejectedAJERule
   - 项目无 rejected AJE → None（allow）
   - 项目有 2 个 rejected AJE 组，1 组已转错报 → 返回 warning，计数为 1
   - 项目有 rejected AJE，全部已转 → None
   - severity 恒为 warning（阻断级交质控合伙人评估）

2. EventCascadeHealthRule
   - outbox 无条目 → None
   - 30 分钟前的 pending WORKPAPER_SAVED → warning（enforcement 未到期）
   - 同条件但 now >= enforcement_start_date → blocking
   - 2 小时前的 pending（超出 1h 窗口）→ None

Validates: Requirements 3 (refinement-round1-review-closure)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# 显式导入以便 create_all 建出所有需要的表
import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.dataset_models  # noqa: F401
import app.models.phase14_models  # noqa: F401
from app.models.audit_platform_models import (
    Adjustment,
    AdjustmentType,
    MisstatementType,
    ReviewStatus,
    UnadjustedMisstatement,
)
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.dataset_models import ImportEventOutbox, OutboxStatus
from app.models.phase14_enums import GateSeverity
from app.services.gate_rules_phase14 import (
    EventCascadeHealthRule,
    UnconvertedRejectedAJERule,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

FAKE_USER_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
async def project(db_session: AsyncSession):
    pid = uuid.uuid4()
    proj = Project(
        id=pid,
        name="R1_Task8_NewRules",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
        wizard_state={},
    )
    db_session.add(proj)
    await db_session.commit()
    return proj


def _new_adjustment(
    *,
    project_id: uuid.UUID,
    entry_group_id: uuid.UUID,
    review_status: ReviewStatus,
    adjustment_type: AdjustmentType = AdjustmentType.aje,
    adjustment_no: str = "ADJ-0001",
    account_code: str = "1001",
    debit: Decimal = Decimal("100.00"),
    credit: Decimal = Decimal("0.00"),
    year: int = 2025,
) -> Adjustment:
    return Adjustment(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        company_code="C001",
        adjustment_no=adjustment_no,
        adjustment_type=adjustment_type,
        description="单测用 AJE",
        account_code=account_code,
        account_name="现金",
        debit_amount=debit,
        credit_amount=credit,
        entry_group_id=entry_group_id,
        review_status=review_status,
        reviewer_id=FAKE_USER_ID,
        reviewed_at=datetime.utcnow(),
        rejection_reason="单测驳回",
        is_deleted=False,
        created_by=FAKE_USER_ID,
    )


def _new_misstatement(
    *,
    project_id: uuid.UUID,
    source_adjustment_id: uuid.UUID,
    year: int = 2025,
    amount: Decimal = Decimal("100.00"),
) -> UnadjustedMisstatement:
    return UnadjustedMisstatement(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        source_adjustment_id=source_adjustment_id,
        misstatement_description="源自被拒 AJE",
        affected_account_code="1001",
        affected_account_name="现金",
        misstatement_amount=amount,
        misstatement_type=MisstatementType.factual,
        is_carried_forward=False,
        is_deleted=False,
        created_by=FAKE_USER_ID,
    )


# ---------------------------------------------------------------------------
# UnconvertedRejectedAJERule
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unconverted_aje_rule_no_rejected_returns_none(db_session, project):
    """项目无 rejected AJE → 不命中。"""
    # 只塞一条 approved AJE，不应命中
    adj = _new_adjustment(
        project_id=project.id,
        entry_group_id=uuid.uuid4(),
        review_status=ReviewStatus.approved,
    )
    db_session.add(adj)
    await db_session.commit()

    rule = UnconvertedRejectedAJERule()
    hit = await rule.check(db_session, {"project_id": project.id})
    assert hit is None


@pytest.mark.asyncio
async def test_unconverted_aje_rule_partial_converted_hits(db_session, project):
    """2 组 rejected AJE，其中 1 组已转错报 → warning，计数=1。"""
    group_converted = uuid.uuid4()
    group_unconverted = uuid.uuid4()

    adj_converted = _new_adjustment(
        project_id=project.id,
        entry_group_id=group_converted,
        review_status=ReviewStatus.rejected,
        adjustment_no="ADJ-CONV-001",
    )
    adj_unconverted = _new_adjustment(
        project_id=project.id,
        entry_group_id=group_unconverted,
        review_status=ReviewStatus.rejected,
        adjustment_no="ADJ-UNCONV-001",
    )
    db_session.add_all([adj_converted, adj_unconverted])
    await db_session.flush()

    # 只把 group_converted 那条转为错报
    ms = _new_misstatement(
        project_id=project.id, source_adjustment_id=adj_converted.id
    )
    db_session.add(ms)
    await db_session.commit()

    rule = UnconvertedRejectedAJERule()
    hit = await rule.check(db_session, {"project_id": project.id})

    assert hit is not None
    assert hit.rule_code == "R1-AJE-UNCONVERTED"
    assert hit.error_code == "AJE_REJECTED_NOT_CONVERTED"
    assert hit.severity == GateSeverity.warning
    assert hit.location["unconverted_group_count"] == 1
    assert "1 个被驳回的 AJE 组未转为错报" in hit.message
    assert str(group_unconverted) in hit.location["sample_entry_group_ids"]
    assert str(group_converted) not in hit.location["sample_entry_group_ids"]


@pytest.mark.asyncio
async def test_unconverted_aje_rule_all_converted_returns_none(db_session, project):
    """所有 rejected AJE 都已转错报 → None。"""
    group_a = uuid.uuid4()
    adj_a = _new_adjustment(
        project_id=project.id,
        entry_group_id=group_a,
        review_status=ReviewStatus.rejected,
        adjustment_no="ADJ-A-001",
    )
    db_session.add(adj_a)
    await db_session.flush()
    ms_a = _new_misstatement(project_id=project.id, source_adjustment_id=adj_a.id)
    db_session.add(ms_a)
    await db_session.commit()

    rule = UnconvertedRejectedAJERule()
    hit = await rule.check(db_session, {"project_id": project.id})
    assert hit is None


@pytest.mark.asyncio
async def test_unconverted_aje_rule_ignores_rje(db_session, project):
    """rje 类型的被驳分录不在本规则范围内。"""
    adj = _new_adjustment(
        project_id=project.id,
        entry_group_id=uuid.uuid4(),
        review_status=ReviewStatus.rejected,
        adjustment_type=AdjustmentType.rje,
        adjustment_no="RJE-001",
    )
    db_session.add(adj)
    await db_session.commit()

    rule = UnconvertedRejectedAJERule()
    hit = await rule.check(db_session, {"project_id": project.id})
    assert hit is None


@pytest.mark.asyncio
async def test_unconverted_aje_rule_missing_project_id_returns_none(db_session):
    """context 无 project_id → 早退 None（与其他规则一致）。"""
    rule = UnconvertedRejectedAJERule()
    hit = await rule.check(db_session, {})
    assert hit is None


# ---------------------------------------------------------------------------
# EventCascadeHealthRule
# ---------------------------------------------------------------------------


def _new_outbox(
    *,
    project_id: uuid.UUID,
    event_type: str,
    status: OutboxStatus,
    created_at: datetime,
    year: int = 2025,
) -> ImportEventOutbox:
    item = ImportEventOutbox(
        id=uuid.uuid4(),
        event_type=event_type,
        project_id=project_id,
        year=year,
        payload={},
        status=status,
        attempt_count=0,
    )
    # server_default 在 sqlite 插入时会用 now，这里显式覆盖为目标时间
    item.created_at = created_at
    return item


@pytest.mark.asyncio
async def test_event_cascade_rule_empty_returns_none(db_session, project):
    """outbox 无条目 → 不命中。"""
    rule = EventCascadeHealthRule()
    hit = await rule.check(db_session, {"project_id": project.id})
    assert hit is None


@pytest.mark.asyncio
async def test_event_cascade_rule_pending_within_window_warning_before_enforcement(
    db_session, project, monkeypatch
):
    """30 分钟前的 pending WORKPAPER_SAVED + enforcement 未到期 → warning。"""
    # 强制 enforcement_start_date 在未来
    future = (datetime.now(tz=timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")

    async def fake_load_config(self, db, *, rule_code, threshold_key, tenant_id=None):
        if rule_code == "R1-EVENT-CASCADE" and threshold_key == "enforcement_start_date":
            return future
        return None

    from app.services import gate_engine as ge_module

    monkeypatch.setattr(
        ge_module.GateEngine, "load_rule_config", fake_load_config, raising=True
    )

    db_session.add(
        _new_outbox(
            project_id=project.id,
            event_type="workpaper.saved",
            status=OutboxStatus.pending,
            created_at=datetime.utcnow() - timedelta(minutes=30),
        )
    )
    await db_session.commit()

    rule = EventCascadeHealthRule()
    hit = await rule.check(db_session, {"project_id": project.id})

    assert hit is not None
    assert hit.rule_code == "R1-EVENT-CASCADE"
    assert hit.error_code == "EVENT_CASCADE_UNHEALTHY"
    assert hit.severity == GateSeverity.warning
    assert hit.location["by_status"].get("pending", 0) == 1
    assert hit.location["by_event_type"].get("workpaper.saved", 0) == 1
    assert "下游更新未同步" in hit.message


@pytest.mark.asyncio
async def test_event_cascade_rule_blocking_after_enforcement(
    db_session, project, monkeypatch
):
    """同条件但 now >= enforcement_start_date → blocking。"""
    past = (datetime.now(tz=timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    async def fake_load_config(self, db, *, rule_code, threshold_key, tenant_id=None):
        if rule_code == "R1-EVENT-CASCADE" and threshold_key == "enforcement_start_date":
            return past
        return None

    from app.services import gate_engine as ge_module

    monkeypatch.setattr(
        ge_module.GateEngine, "load_rule_config", fake_load_config, raising=True
    )

    db_session.add(
        _new_outbox(
            project_id=project.id,
            event_type="reports.updated",
            status=OutboxStatus.failed,
            created_at=datetime.utcnow() - timedelta(minutes=15),
        )
    )
    await db_session.commit()

    rule = EventCascadeHealthRule()
    hit = await rule.check(db_session, {"project_id": project.id})

    assert hit is not None
    assert hit.severity == GateSeverity.blocking
    assert hit.location["by_status"].get("failed", 0) == 1


@pytest.mark.asyncio
async def test_event_cascade_rule_outside_window_returns_none(
    db_session, project, monkeypatch
):
    """2 小时前的 pending 超出 1h 窗口 → 不命中。"""
    # 让 enforcement 是"已到期"（若能命中应 blocking），用于反证窗口过滤生效
    past = "2020-01-01"

    async def fake_load_config(self, db, *, rule_code, threshold_key, tenant_id=None):
        if rule_code == "R1-EVENT-CASCADE" and threshold_key == "enforcement_start_date":
            return past
        return None

    from app.services import gate_engine as ge_module

    monkeypatch.setattr(
        ge_module.GateEngine, "load_rule_config", fake_load_config, raising=True
    )

    db_session.add(
        _new_outbox(
            project_id=project.id,
            event_type="workpaper.saved",
            status=OutboxStatus.pending,
            created_at=datetime.utcnow() - timedelta(hours=2),
        )
    )
    await db_session.commit()

    rule = EventCascadeHealthRule()
    hit = await rule.check(db_session, {"project_id": project.id})
    assert hit is None


@pytest.mark.asyncio
async def test_event_cascade_rule_ignores_unwatched_event_types(
    db_session, project, monkeypatch
):
    """非 WORKPAPER_SAVED / REPORTS_UPDATED 的 pending 事件不应触发规则。"""
    past = "2020-01-01"

    async def fake_load_config(self, db, *, rule_code, threshold_key, tenant_id=None):
        return past if threshold_key == "enforcement_start_date" else None

    from app.services import gate_engine as ge_module

    monkeypatch.setattr(
        ge_module.GateEngine, "load_rule_config", fake_load_config, raising=True
    )

    db_session.add(
        _new_outbox(
            project_id=project.id,
            event_type="materiality.changed",  # 不在监控列表
            status=OutboxStatus.pending,
            created_at=datetime.utcnow() - timedelta(minutes=10),
        )
    )
    await db_session.commit()

    rule = EventCascadeHealthRule()
    hit = await rule.check(db_session, {"project_id": project.id})
    assert hit is None


@pytest.mark.asyncio
async def test_event_cascade_rule_published_status_does_not_trigger(
    db_session, project, monkeypatch
):
    """status=published 的事件即使在窗口内也不应触发（已完成消费）。"""
    past = "2020-01-01"

    async def fake_load_config(self, db, *, rule_code, threshold_key, tenant_id=None):
        return past if threshold_key == "enforcement_start_date" else None

    from app.services import gate_engine as ge_module

    monkeypatch.setattr(
        ge_module.GateEngine, "load_rule_config", fake_load_config, raising=True
    )

    db_session.add(
        _new_outbox(
            project_id=project.id,
            event_type="workpaper.saved",
            status=OutboxStatus.published,
            created_at=datetime.utcnow() - timedelta(minutes=5),
        )
    )
    await db_session.commit()

    rule = EventCascadeHealthRule()
    hit = await rule.check(db_session, {"project_id": project.id})
    assert hit is None


@pytest.mark.asyncio
async def test_event_cascade_rule_default_enforcement_when_no_config(
    db_session, project, monkeypatch
):
    """未配置 enforcement_start_date 时走默认常量 '2026-06-05'。"""

    async def fake_load_config(self, db, *, rule_code, threshold_key, tenant_id=None):
        return None  # 刻意不返回任何配置

    from app.services import gate_engine as ge_module

    monkeypatch.setattr(
        ge_module.GateEngine, "load_rule_config", fake_load_config, raising=True
    )

    db_session.add(
        _new_outbox(
            project_id=project.id,
            event_type="workpaper.saved",
            status=OutboxStatus.pending,
            created_at=datetime.utcnow() - timedelta(minutes=20),
        )
    )
    await db_session.commit()

    rule = EventCascadeHealthRule()
    hit = await rule.check(db_session, {"project_id": project.id})

    assert hit is not None
    # 当前测试运行时间的具体 severity 不做硬断言（可能为 warning 或 blocking），
    # 但至少其中之一；通过对比默认常量判断：
    now = datetime.now(tz=timezone.utc)
    default_dt = datetime(2026, 6, 5, tzinfo=timezone.utc)
    expected = (
        GateSeverity.blocking if now >= default_dt else GateSeverity.warning
    )
    assert hit.severity == expected


# ---------------------------------------------------------------------------
# 注册检查：两条规则确实被注册到目标 gate
# ---------------------------------------------------------------------------


def test_rules_are_registered_to_expected_gates():
    """R1-AJE-UNCONVERTED → sign_off；R1-EVENT-CASCADE → sign_off + export_package。"""
    from app.models.phase14_enums import GateType
    from app.services.gate_engine import rule_registry
    from app.services.gate_rules_phase14 import register_phase14_rules

    register_phase14_rules()  # 幂等：重复注册也没关系（规则会被叠加）

    sign_off_codes = [r.rule_code for r in rule_registry.get_rules(GateType.sign_off)]
    export_codes = [r.rule_code for r in rule_registry.get_rules(GateType.export_package)]

    assert "R1-AJE-UNCONVERTED" in sign_off_codes
    assert "R1-EVENT-CASCADE" in sign_off_codes
    assert "R1-EVENT-CASCADE" in export_codes
    # AJE 未转错报不挂 export_package（按 R1 需求仅 sign_off）
    assert "R1-AJE-UNCONVERTED" not in export_codes
