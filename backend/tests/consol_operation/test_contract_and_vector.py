"""V244 三层契约、canonical request 与版本向量聚焦测试。"""
from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401 - 注册全模型与 SQLite 方言补丁
from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import Base, ProjectStatus
from app.models.consol_operation_models import OPERATION_STATUSES, ConsolOperation
from app.models.consol_push_models import ConsolPushRun
from app.models.consol_scope_confirmation_models import ConsolScopeConfirmation
from app.models.consol_worksheet_data_models import ConsolWorksheetData
from app.models.core import Project
from app.schemas.consol_operation import ConsolVersionVector
from app.services.consol_operation_service import canonical_request, merge_requests, request_digest
from app.services.consol_version_vector import build_version_vector, digest_payload, vector_digest

YEAR = 2025


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()


def _project() -> Project:
    return Project(
        id=uuid.uuid4(),
        name="【测试】持久合并运行_2025",
        client_name="【测试】持久合并运行",
        company_code="OP",
        audit_year=YEAR,
        report_scope="consolidated",
        status=ProjectStatus.execution,
    )


def test_v235_migration_orm_and_schema_are_aligned():
    backend = Path(__file__).resolve().parents[2]
    forward = (backend / "migrations/V244__consol_operation.sql").read_text(encoding="utf-8")
    rollback = (backend / "migrations/R244__rollback_consol_operation.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS consol_operation" in forward
    assert "DROP TABLE IF EXISTS consol_operation" in rollback
    for status in OPERATION_STATUSES:
        assert f"'{status}'" in forward
    expected = {
        "id", "project_id", "year", "operation_type", "idempotency_key",
        "idempotency_keys", "request_hash", "request_payload", "context_json",
        "version_vector", "status", "revision", "lease_owner", "lease_expires_at",
        "heartbeat_at", "attempt", "steps", "errors", "result_refs", "metrics",
        "trigger_source", "triggered_by", "queued_at", "started_at", "finished_at",
        "superseded_by", "created_at", "updated_at",
    }
    assert set(ConsolOperation.__table__.columns.keys()) == expected
    assert "operation_id" in ConsolPushRun.__table__.columns
    assert {index.name for index in ConsolOperation.__table__.indexes} >= {
        "ux_consol_operation_running", "ux_consol_operation_queued",
        "ux_consol_operation_idempotency", "ix_consol_operation_claim",
    }


def test_canonical_request_and_merge_are_order_independent():
    project_id = uuid.uuid4()
    left = canonical_request(
        project_id=project_id, year=YEAR, operation_type="push",
        trigger_source="formula_changed", requested_actions=("notes", "trial", "notes"),
    )
    right = canonical_request(
        project_id=project_id, year=YEAR, operation_type="push",
        trigger_source="formula_changed", requested_actions=("trial", "notes"),
    )
    assert request_digest(left) == request_digest(right)
    refresh = canonical_request(
        project_id=project_id, year=YEAR, operation_type="refresh_all",
        trigger_source="manual", requested_actions=(),
    )
    merged = merge_requests(left, refresh)
    assert merged["operation_type"] == "refresh_all"
    assert merged["trigger_sources"] == ["formula_changed", "manual"]
    assert merged["requested_actions"] == sorted(set(merged["requested_actions"]))
