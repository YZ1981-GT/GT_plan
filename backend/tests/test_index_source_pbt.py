"""
Property-Based Test: IndexSource 注册表重构等价性 (R1)

**Validates: Requirements 1.2**

属性 R1：重构后 _fetch_project_texts 通过注册表调度，
对任意 project_id 返回结果与 BusinessDataSource.fetch_texts 完全一致
（因为当前注册表只有 BusinessDataSource 一个源）。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.index_source import IndexSource, BusinessDataSource
from app.services.knowledge_index_service import KnowledgeIndexService


@st.composite
def uuid_strategy(draw):
    """生成有效 UUID。"""
    return UUID(int=draw(st.integers(min_value=0, max_value=2**128 - 1)))


@pytest.fixture
def mock_db_session():
    """Mock AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


class TestIndexSourceRegistryProperty:
    """PBT: 注册表调度等价性"""

    @settings(max_examples=5)
    @given(project_id=uuid_strategy())
    @pytest.mark.asyncio
    async def test_fetch_project_texts_equals_source_fetch(self, project_id: UUID):
        """
        属性：对任意 project_id，KnowledgeIndexService._fetch_project_texts(pid)
        的返回值 == 遍历 _index_sources() 各源 fetch_texts(pid) 的拼接。

        这验证了重构的等价性：注册表模式不改变行为。

        **Validates: Requirements 1.2**
        """
        mock_db = AsyncMock()
        # Mock empty results for all DB queries
        mock_result = MagicMock()
        mock_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[])
        )
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        service = KnowledgeIndexService(mock_db)

        # 通过 _fetch_project_texts 获取
        result_via_service = await service._fetch_project_texts(project_id)

        # 通过直接遍历 _index_sources 获取
        result_via_sources = []
        for source in service._index_sources():
            # Reset mock for fresh calls
            mock_db.execute = AsyncMock(return_value=mock_result)
            source_texts = await source.fetch_texts(project_id)
            result_via_sources.extend(source_texts)

        # 两种路径结果一致
        assert result_via_service == result_via_sources

    @settings(max_examples=5)
    @given(project_id=uuid_strategy())
    @pytest.mark.asyncio
    async def test_index_sources_all_satisfy_protocol(self, project_id: UUID):
        """
        属性：_index_sources() 返回的每个对象都满足 IndexSource Protocol。

        **Validates: Requirements 1.2**
        """
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        service = KnowledgeIndexService(mock_db)
        sources = service._index_sources()

        assert len(sources) >= 1
        for source in sources:
            assert isinstance(source, IndexSource), (
                f"{type(source).__name__} 不满足 IndexSource Protocol"
            )
            assert hasattr(source, "source_type")
            assert isinstance(source.source_type, str)
            assert len(source.source_type) > 0
