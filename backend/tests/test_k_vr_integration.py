"""K 管理循环 VR 集成测试 — 真实 DB → check_k_cycle_triangle_reconciliation → VR-K8-01 结果.

Spec: .kiro/specs/k-admin-cycle-post-review-fix/
Sprint 2 Task 4.1 — P1 应修
Validates: Requirements 2.5

Purpose:
  现有 24 个 VR 测试全部 mock `_get_wp_parsed_data`，缺少真实 DB 记录 →
  run_all_checks → 阻断签字的集成路径。本测试创建真实 WorkingPaper + WpIndex
  记录，不 mock 任何内部方法，验证 VR-K8-01 在真实 DB 路径下的 pass/fail 行为。

Test Cases:
  - pass case: K8 parsed_data 中 k8_total = k8_payroll + k8_depreciation + k8_other
  - fail case: K8 parsed_data 中 k8_total ≠ 明细合计 → blocking failure
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpReviewStatus,
    WpSourceType,
    WpStatus,
)
from app.services.consistency_gate import ConsistencyGate

# SQLite JSONB compatibility
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

FAKE_PROJECT_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    """Create an in-memory SQLite database with all tables."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def project_id():
    return FAKE_PROJECT_ID


def _create_wp_index(project_id: uuid.UUID, wp_code: str) -> WpIndex:
    """Helper to create a WpIndex record."""
    return WpIndex(
        id=uuid.uuid4(),
        project_id=project_id,
        wp_code=wp_code,
        wp_name=f"{wp_code} 底稿",
        audit_cycle="K",
        status=WpStatus.in_progress,
        is_deleted=False,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def _create_working_paper(
    project_id: uuid.UUID,
    wp_index_id: uuid.UUID,
    parsed_data: dict,
) -> WorkingPaper:
    """Helper to create a WorkingPaper record with parsed_data."""
    return WorkingPaper(
        id=uuid.uuid4(),
        project_id=project_id,
        wp_index_id=wp_index_id,
        file_path=f"/fake/path/{wp_index_id}.xlsx",
        source_type=WpSourceType.template,
        status=WpFileStatus.draft,
        review_status=WpReviewStatus.not_submitted,
        file_version=1,
        parsed_data=parsed_data,
        prefill_stale=False,
        is_deleted=False,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


# ---------------------------------------------------------------------------
# Test: VR-K8-01 pass case — 数据勾稽
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vr_k8_01_pass_real_db(db_session: AsyncSession, project_id):
    """VR-K8-01 pass: 真实 DB 记录，k8_total = k8_payroll + k8_depreciation + k8_other.

    创建 WpIndex(wp_code='K8') + WorkingPaper(parsed_data 含勾稽数据)，
    调用 check_k_cycle_triangle_reconciliation 不 mock，断言 VR-K8-01 passed=True.
    """
    # Create WpIndex for K8
    k8_index = _create_wp_index(project_id, "K8")
    db_session.add(k8_index)

    # K8 parsed_data: total = 100万 + 50万 + 200万 = 350万 (勾稽)
    k8_parsed = {
        "k8_total": "3500000.00",
        "k8_payroll": "1000000.00",
        "k8_depreciation": "500000.00",
        "k8_other": "2000000.00",
    }
    k8_wp = _create_working_paper(project_id, k8_index.id, k8_parsed)
    db_session.add(k8_wp)

    await db_session.commit()

    # Call without mock
    gate = ConsistencyGate(db_session)
    checks = await gate.check_k_cycle_triangle_reconciliation(project_id, 2025)

    # Find VR-K8-01 result
    k8_rule = next(c for c in checks if "K8勾稽" in c.check_name)
    assert k8_rule.passed is True, f"VR-K8-01 should pass but got: {k8_rule.details}"
    assert k8_rule.severity == "blocking"
    assert "差额=0" in k8_rule.details or "差额=0.00" in k8_rule.details


# ---------------------------------------------------------------------------
# Test: VR-K8-01 fail case — 数据不勾稽 → blocking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vr_k8_01_fail_real_db(db_session: AsyncSession, project_id):
    """VR-K8-01 fail: 真实 DB 记录，k8_total ≠ 明细合计 → blocking failure.

    创建 WpIndex(wp_code='K8') + WorkingPaper(parsed_data 不勾稽)，
    调用 check_k_cycle_triangle_reconciliation 不 mock，断言 VR-K8-01 passed=False.
    """
    # Create WpIndex for K8
    k8_index = _create_wp_index(project_id, "K8")
    db_session.add(k8_index)

    # K8 parsed_data: total = 400万 ≠ 100万 + 50万 + 200万 = 350万 (差额 50万)
    k8_parsed = {
        "k8_total": "4000000.00",
        "k8_payroll": "1000000.00",
        "k8_depreciation": "500000.00",
        "k8_other": "2000000.00",
    }
    k8_wp = _create_working_paper(project_id, k8_index.id, k8_parsed)
    db_session.add(k8_wp)

    await db_session.commit()

    # Call without mock
    gate = ConsistencyGate(db_session)
    checks = await gate.check_k_cycle_triangle_reconciliation(project_id, 2025)

    # Find VR-K8-01 result
    k8_rule = next(c for c in checks if "K8勾稽" in c.check_name)
    assert k8_rule.passed is False, f"VR-K8-01 should fail but got: {k8_rule.details}"
    assert k8_rule.severity == "blocking"
    # Verify the details mention the discrepancy
    assert "500,000" in k8_rule.details or "500000" in k8_rule.details
