"""Shared test fixtures for AI service tests."""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_db_session():
    """Mock AsyncSession that never hits the real database.
    
    This avoids SQLite FK constraint issues when AI models reference
    tables (like workpapers) that aren't registered in the test Base.
    """
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session
