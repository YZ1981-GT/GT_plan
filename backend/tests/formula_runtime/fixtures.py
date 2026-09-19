"""Shared fixtures for formula_runtime baseline & convergence tests.

Provides:
- Async session mock fixture (pytest fixture for isolation)
- Sample project/year/wp_id constants used across gap baseline tests
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


# ─── Sample Constants ──────────────────────────────────────────────────────────

SAMPLE_PROJECT_ID = uuid.UUID("5e193c68-0000-0000-0000-000000000001")
SAMPLE_YEAR = 2025
SAMPLE_WP_ID = uuid.UUID("687a23a5-0000-0000-0000-000000000002")
SAMPLE_OPERATOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")


# ─── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_async_session() -> AsyncMock:
    """Provide a fully mocked AsyncSession for unit isolation (no real DB)."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    session.delete = AsyncMock()
    return session


@pytest.fixture()
def mock_operator() -> MagicMock:
    """Provide a mock operator (User) with partner role for DraftRefreshService."""
    op = MagicMock()
    op.id = SAMPLE_OPERATOR_ID
    op.role = "partner"
    return op
