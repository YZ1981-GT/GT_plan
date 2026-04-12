"""Backend test environment configuration. Validates: Requirements 2.8"""
import os
from collections.abc import AsyncGenerator
from decimal import Decimal
from typing import Any
from uuid import uuid4

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.base import Base  # noqa: F401
from app.models.consolidation_models import (
    Company,
    ConsolMethod,
    ConsolScope,
    EliminationEntry,
    EliminationEntryType,
    InternalArAp,
    InternalTrade,
    GoodwillCalc,
    MinorityInterest,
    ForexTranslation,
    ComponentAuditor,
    ComponentInstruction,
    ComponentResult,
    InstructionStatus,
    ResultStatus,
    ReviewStatusEnum,
)
from app.models.core import Project, ProjectStatus

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite session for testing."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(test_engine) as session:
        yield session
        await session.rollback()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def sample_project_data() -> dict[str, Any]:
    """Sample project data for testing."""
    return {
        "id": uuid4(),
        "name": "Test Consolidation Project",
        "client_name": "Test Client",
        "audit_period_start": "2024-01-01",
        "audit_period_end": "2024-12-31",
        "project_type": "consolidation",
        "status": ProjectStatus.active,
        "materiality_level": 100000.0,
    }


@pytest.fixture
def sample_company_tree(sample_project_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Sample company tree for testing: A (root) → B → C, A → D."""
    return [
        {
            "id": uuid4(),
            "project_id": sample_project_data["id"],
            "company_code": "A",
            "company_name": "Parent A",
            "parent_code": None,
            "ultimate_code": "A",
            "consol_level": 0,
            "shareholding": Decimal("100.00"),
            "consol_method": ConsolMethod.full,
            "functional_currency": "CNY",
            "is_active": True,
        },
        {
            "id": uuid4(),
            "project_id": sample_project_data["id"],
            "company_code": "B",
            "company_name": "Subsidiary B",
            "parent_code": "A",
            "ultimate_code": "A",
            "consol_level": 1,
            "shareholding": Decimal("80.00"),
            "consol_method": ConsolMethod.full,
            "functional_currency": "CNY",
            "is_active": True,
        },
        {
            "id": uuid4(),
            "project_id": sample_project_data["id"],
            "company_code": "C",
            "company_name": "Subsidiary C",
            "parent_code": "B",
            "ultimate_code": "A",
            "consol_level": 2,
            "shareholding": Decimal("100.00"),
            "consol_method": ConsolMethod.full,
            "functional_currency": "CNY",
            "is_active": True,
        },
        {
            "id": uuid4(),
            "project_id": sample_project_data["id"],
            "company_code": "D",
            "company_name": "Subsidiary D",
            "parent_code": "A",
            "ultimate_code": "A",
            "consol_level": 1,
            "shareholding": Decimal("70.00"),
            "consol_method": ConsolMethod.full,
            "functional_currency": "CNY",
            "is_active": True,
        },
    ]
