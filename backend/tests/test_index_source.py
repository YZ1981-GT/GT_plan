"""
IndexSource Protocol + BusinessDataSource 单元测试

验证：
- IndexSource Protocol 是 @runtime_checkable 且 BusinessDataSource 满足协议
- BusinessDataSource.fetch_texts 行为与原 _fetch_project_texts 一致
- KnowledgeIndexService._index_sources() 返回注册列表
- build_index 通过注册表调度（行为不变）

**Validates: Requirements 1.2**
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.index_source import IndexSource, BusinessDataSource
from app.services.knowledge_index_service import KnowledgeIndexService
from app.models.ai_models import KnowledgeSourceType


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


class TestIndexSourceProtocol:
    """验证 IndexSource Protocol 定义正确"""

    def test_protocol_is_runtime_checkable(self):
        """IndexSource 是 @runtime_checkable Protocol。"""
        assert hasattr(IndexSource, "__protocol_attrs__") or hasattr(
            IndexSource, "__abstractmethods__"
        ) or isinstance(IndexSource, type)
        # runtime_checkable 允许 isinstance 检查
        from typing import runtime_checkable, Protocol

        # 验证可以用 isinstance 检查
        class _DummySource:
            source_type = "test"

            async def fetch_texts(self, project_id):
                return []

        assert isinstance(_DummySource(), IndexSource)

    def test_business_data_source_satisfies_protocol(self, mock_db_session):
        """BusinessDataSource 满足 IndexSource Protocol。"""
        source = BusinessDataSource(mock_db_session)
        assert isinstance(source, IndexSource)
        assert hasattr(source, "source_type")
        assert hasattr(source, "fetch_texts")
        assert source.source_type == "business_data"

    def test_non_conforming_class_fails_protocol(self):
        """不满足协议的类不通过 isinstance 检查。"""

        class _BadSource:
            pass

        assert not isinstance(_BadSource(), IndexSource)


class TestBusinessDataSource:
    """验证 BusinessDataSource 行为与原 _fetch_project_texts 一致"""

    @pytest.mark.asyncio
    async def test_fetch_texts_empty_project(self, mock_db_session):
        """空项目返回空列表。"""
        mock_result = MagicMock()
        mock_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[])
        )
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        source = BusinessDataSource(mock_db_session)
        texts = await source.fetch_texts(uuid4())

        assert texts == []

    @pytest.mark.asyncio
    async def test_fetch_texts_document_scan(self, mock_db_session):
        """DocumentScan 数据正确提取为文本 tuple。"""
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_doc.file_name = "采购合同.pdf"
        mock_doc.document_type = "contract"

        # First call returns DocumentScan, rest return empty
        call_count = [0]

        async def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_res = MagicMock()
            if call_count[0] == 1:
                mock_res.scalars.return_value = MagicMock(
                    all=MagicMock(return_value=[mock_doc])
                )
            else:
                mock_res.scalars.return_value = MagicMock(
                    all=MagicMock(return_value=[])
                )
            return mock_res

        mock_db_session.execute = execute_side_effect

        source = BusinessDataSource(mock_db_session)
        texts = await source.fetch_texts(uuid4())

        assert len(texts) == 1
        source_type, source_id, text = texts[0]
        assert source_type == KnowledgeSourceType.document_scan
        assert source_id == mock_doc.id
        assert "采购合同.pdf" in text
        assert "contract" in text

    @pytest.mark.asyncio
    async def test_fetch_texts_trial_balance(self, mock_db_session):
        """TrialBalance 数据正确提取。"""
        mock_tb = MagicMock()
        mock_tb.id = uuid4()
        mock_tb.account_code = "1122"
        mock_tb.account_name = "应收账款"
        mock_tb.period = "2024-12"
        mock_tb.opening_balance = 1000000.0
        mock_tb.closing_balance = 1200000.0

        call_count = [0]

        async def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_res = MagicMock()
            # TrialBalance is the 3rd query (after DocumentScan and AdjustmentEntry)
            if call_count[0] == 3:
                mock_res.scalars.return_value = MagicMock(
                    all=MagicMock(return_value=[mock_tb])
                )
            else:
                mock_res.scalars.return_value = MagicMock(
                    all=MagicMock(return_value=[])
                )
            return mock_res

        mock_db_session.execute = execute_side_effect

        source = BusinessDataSource(mock_db_session)
        texts = await source.fetch_texts(uuid4())

        assert len(texts) == 1
        source_type, source_id, text = texts[0]
        assert source_type == KnowledgeSourceType.trial_balance
        assert source_id == mock_tb.id
        assert "1122" in text
        assert "应收账款" in text


class TestKnowledgeIndexServiceRegistry:
    """验证 KnowledgeIndexService 使用注册表模式"""

    def test_index_sources_returns_list(self, mock_db_session):
        """_index_sources() 返回 IndexSource 列表。"""
        service = KnowledgeIndexService(mock_db_session)
        sources = service._index_sources()

        assert isinstance(sources, list)
        assert len(sources) >= 1
        for source in sources:
            assert isinstance(source, IndexSource)

    def test_index_sources_contains_business_data(self, mock_db_session):
        """_index_sources() 包含 BusinessDataSource。"""
        service = KnowledgeIndexService(mock_db_session)
        sources = service._index_sources()

        source_types = [s.source_type for s in sources]
        assert "business_data" in source_types

    @pytest.mark.asyncio
    async def test_fetch_project_texts_delegates_to_sources(self, mock_db_session):
        """_fetch_project_texts 委托给注册的 IndexSource 实例。"""
        service = KnowledgeIndexService(mock_db_session)

        # Mock empty results
        mock_result = MagicMock()
        mock_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[])
        )
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        texts = await service._fetch_project_texts(uuid4())

        # Should return list (empty for empty project)
        assert isinstance(texts, list)

    @pytest.mark.asyncio
    async def test_build_index_uses_registry(self, mock_db_session):
        """build_index 通过 _index_sources 注册表获取文本。"""
        service = KnowledgeIndexService(mock_db_session)

        # Mock empty results for all queries
        mock_result = MagicMock()
        mock_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[])
        )
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock()

        from unittest.mock import patch

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.1] * 768
            count = await service.build_index(project_id=uuid4())

        assert count == 0  # Empty project


# ---------------------------------------------------------------------------
# KnowledgeDocSource 测试
# ---------------------------------------------------------------------------

from types import SimpleNamespace

from app.services.index_source import KnowledgeDocSource
from app.models.knowledge_models import KnowledgeAccessLevel


def _doc_row(
    doc_id,
    content_text,
    *,
    access_level=None,
    project_ids=None,
    folder_access_level,
    folder_project_ids=None,
    created_by=None,
    folder_created_by=None,
):
    """与 ``KnowledgeDocSource.fetch_texts`` 的 SELECT 同形的一行（按列名取值）。

    2026-10-02（601707554）起该查询改为取判权三元组（access_level / project_ids / created_by，
    文档与文件夹各一组）交给 ``KnowledgeAccessPolicy.can_retrieve`` 单一判定面；旧夹具是按位置的
    7 元组（含 name、不含 created_by），对新代码恒 AttributeError。
    """
    return SimpleNamespace(
        id=doc_id,
        content_text=content_text,
        access_level=access_level,
        project_ids=project_ids,
        created_by=created_by,
        folder_access_level=folder_access_level,
        folder_project_ids=folder_project_ids,
        folder_created_by=folder_created_by,
    )


class TestKnowledgeDocSource:
    """验证 KnowledgeDocSource 行为正确

    **Validates: Requirements 1.3**
    """

    def test_satisfies_protocol(self, mock_db_session):
        """KnowledgeDocSource 满足 IndexSource Protocol。"""
        source = KnowledgeDocSource(mock_db_session)
        assert isinstance(source, IndexSource)
        assert source.source_type == "knowledge_doc"

    @pytest.mark.asyncio
    async def test_fetch_texts_public_folder(self, mock_db_session):
        """公开文件夹下的文档对任何项目可见。"""
        doc_id = uuid4()
        project_id = uuid4()

        # Mock query result: one document in a public folder（文档 access_level=None ⇒ 继承文件夹）
        mock_row = _doc_row(doc_id, "这是审计准则的内容文本", folder_access_level=KnowledgeAccessLevel.public)

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        source = KnowledgeDocSource(mock_db_session)
        texts = await source.fetch_texts(project_id)

        assert len(texts) == 1
        source_type, source_id, text = texts[0]
        assert source_type == KnowledgeSourceType.knowledge_doc
        assert source_id == doc_id
        assert text == "这是审计准则的内容文本"

    @pytest.mark.asyncio
    async def test_fetch_texts_project_group_accessible(self, mock_db_session):
        """project_group 文件夹下的文档对 project_ids 中的项目可见。"""
        doc_id = uuid4()
        project_id = uuid4()

        mock_row = _doc_row(
            doc_id, "项目组专属内容",
            folder_access_level=KnowledgeAccessLevel.project_group,
            folder_project_ids=[str(project_id), str(uuid4())],  # folder project_ids contains our project
        )

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        source = KnowledgeDocSource(mock_db_session)
        texts = await source.fetch_texts(project_id)

        assert len(texts) == 1
        assert texts[0][2] == "项目组专属内容"

    @pytest.mark.asyncio
    async def test_fetch_texts_project_group_not_accessible(self, mock_db_session):
        """project_group 文件夹下的文档对不在 project_ids 中的项目不可见。"""
        doc_id = uuid4()
        project_id = uuid4()
        other_project = uuid4()

        mock_row = _doc_row(
            doc_id, "不应该看到的内容",
            folder_access_level=KnowledgeAccessLevel.project_group,
            folder_project_ids=[str(other_project)],  # does NOT contain our project_id
        )

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        source = KnowledgeDocSource(mock_db_session)
        texts = await source.fetch_texts(project_id)

        assert len(texts) == 0

    @pytest.mark.asyncio
    async def test_fetch_texts_private_not_accessible(self, mock_db_session):
        """private 文档不对项目级索引开放。"""
        doc_id = uuid4()
        project_id = uuid4()

        mock_row = _doc_row(
            doc_id, "私人内容",
            access_level=KnowledgeAccessLevel.private,        # doc-level override
            folder_access_level=KnowledgeAccessLevel.public,  # folder is public but doc overrides
        )

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        source = KnowledgeDocSource(mock_db_session)
        texts = await source.fetch_texts(project_id)

        assert len(texts) == 0

    @pytest.mark.asyncio
    async def test_fetch_texts_doc_level_override(self, mock_db_session):
        """文档级 access_level 覆盖文件夹级。"""
        doc_id = uuid4()
        project_id = uuid4()

        # Folder is private, but doc is public → doc wins
        mock_row = _doc_row(
            doc_id, "公开内容",
            access_level=KnowledgeAccessLevel.public,          # doc-level: public
            folder_access_level=KnowledgeAccessLevel.private,  # folder: private
        )

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        source = KnowledgeDocSource(mock_db_session)
        texts = await source.fetch_texts(project_id)

        assert len(texts) == 1

    @pytest.mark.asyncio
    async def test_fetch_texts_empty_returns_empty(self, mock_db_session):
        """无文档时返回空列表。"""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        source = KnowledgeDocSource(mock_db_session)
        texts = await source.fetch_texts(uuid4())

        assert texts == []


class TestKnowledgeIndexServiceRegistryWithDocSource:
    """验证 KnowledgeIndexService 注册表包含 KnowledgeDocSource

    **Validates: Requirements 1.3**
    """

    def test_index_sources_contains_knowledge_doc(self, mock_db_session):
        """_index_sources() 包含 KnowledgeDocSource。"""
        service = KnowledgeIndexService(mock_db_session)
        sources = service._index_sources()

        source_types = [s.source_type for s in sources]
        assert "knowledge_doc" in source_types

    def test_index_sources_has_all_registered_sources(self, mock_db_session):
        """_index_sources() 恰好是业务数据、知识文档、地址坐标三个源（按注册顺序）。

        第三个源 AddressCoordinateIndexSource 由 dsh-agent-panel-integration Task 22（55c5e0fe5，V148）注册。
        """
        service = KnowledgeIndexService(mock_db_session)
        sources = service._index_sources()

        assert [s.source_type for s in sources] == ["business_data", "knowledge_doc", "address_coordinate"]


class TestKnowledgeSourceTypeEnum:
    """验证 KnowledgeSourceType 枚举包含 knowledge_doc

    **Validates: Requirements 1.3**
    """

    def test_knowledge_doc_member_exists(self):
        """KnowledgeSourceType 包含 knowledge_doc 成员。"""
        assert hasattr(KnowledgeSourceType, "knowledge_doc")
        assert KnowledgeSourceType.knowledge_doc.value == "knowledge_doc"

    def test_enum_members(self):
        """KnowledgeSourceType 成员精确集合：原 11 + knowledge_doc + address_coordinate（55c5e0fe5 / V148）。"""
        assert {m.value for m in KnowledgeSourceType} == {
            "trial_balance", "journal", "auxiliary", "contract", "document_scan", "workpaper",
            "adjustment", "elimination", "confirmation", "review_comment", "prior_year_summary",
            "knowledge_doc", "address_coordinate",
        }

    def test_incremental_update_can_parse_knowledge_doc(self):
        """incremental_update 内部 KnowledgeSourceType(source_type) 可解析 'knowledge_doc'。"""
        st = KnowledgeSourceType("knowledge_doc")
        assert st == KnowledgeSourceType.knowledge_doc
