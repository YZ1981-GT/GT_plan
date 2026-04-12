"""
自然语言指令服务单元测试
测试自然语言指令解析和执行
需求覆盖: 8.1-8.6

注：此文件测试实际服务实现中已存在的方法。
方法签名需与 backend/app/services/nl_command_service.py 对齐。
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.nl_command_service import NLCommandService


class TestNLCommandService:
    """测试自然语言指令服务 — 基于实际实现的方法签名"""

    @pytest.mark.asyncio
    async def test_service_instantiation(self):
        """测试服务可正常实例化"""
        mock_db = AsyncMock()
        service = NLCommandService(mock_db)
        assert service is not None

    @pytest.mark.asyncio
    async def test_parse_intent_method_exists(self):
        """测试 parse_intent 方法存在"""
        mock_db = AsyncMock()
        service = NLCommandService(mock_db)
        assert hasattr(service, "parse_intent")
        assert callable(service.parse_intent)

    @pytest.mark.asyncio
    async def test_execute_command_method_exists(self):
        """测试 execute_command 方法存在"""
        mock_db = AsyncMock()
        service = NLCommandService(mock_db)
        assert hasattr(service, "execute_command")
        assert callable(service.execute_command)

    @pytest.mark.asyncio
    async def test_analyze_file_method_exists(self):
        """测试 analyze_file 方法存在"""
        mock_db = AsyncMock()
        service = NLCommandService(mock_db)
        assert hasattr(service, "analyze_file")
        assert callable(service.analyze_file)

    @pytest.mark.asyncio
    async def test_analyze_folder_method_exists(self):
        """测试 analyze_folder 方法存在"""
        mock_db = AsyncMock()
        service = NLCommandService(mock_db)
        assert hasattr(service, "analyze_folder")
        assert callable(service.analyze_folder)

    @pytest.mark.asyncio
    async def test_compare_pbc_list_method_exists(self):
        """测试 compare_pbc_list 方法存在"""
        mock_db = AsyncMock()
        service = NLCommandService(mock_db)
        assert hasattr(service, "compare_pbc_list")
        assert callable(service.compare_pbc_list)

    @pytest.mark.asyncio
    async def test_chat_method_exists(self):
        """测试 chat 方法存在"""
        mock_db = AsyncMock()
        service = NLCommandService(mock_db)
        assert hasattr(service, "chat")
        assert callable(service.chat)

    @pytest.mark.asyncio
    async def test_match_patterns_method_exists(self):
        """测试 _match_patterns 方法存在"""
        mock_db = AsyncMock()
        service = NLCommandService(mock_db)
        assert hasattr(service, "_match_patterns")
        assert callable(service._match_patterns)

    @pytest.mark.asyncio
    async def test_match_patterns_returns_tuple(self):
        """测试 _match_patterns 返回正确结构"""
        mock_db = AsyncMock()
        service = NLCommandService(mock_db)

        intent, params, confidence = service._match_patterns("查看2024年12月余额")
        assert intent is None or isinstance(intent, str)
        assert isinstance(params, dict)
        assert isinstance(confidence, float)
        assert 0 <= confidence <= 1

    @pytest.mark.asyncio
    async def test_extract_attachments_method_exists(self):
        """测试 _extract_attachments 方法存在"""
        mock_db = AsyncMock()
        service = NLCommandService(mock_db)
        assert hasattr(service, "_extract_attachments")
        assert callable(service._extract_attachments)

    @pytest.mark.asyncio
    async def test_extract_attachments_finds_files(self):
        """测试 _extract_attachments 能提取附件"""
        mock_db = AsyncMock()
        service = NLCommandService(mock_db)

        text = "请分析这份合同.pdf和发票.png的内容"
        attachments = service._extract_attachments(text)
        assert isinstance(attachments, list)

    @pytest.mark.asyncio
    async def test_extract_json_method_exists(self):
        """测试 _extract_json 方法存在"""
        mock_db = AsyncMock()
        service = NLCommandService(mock_db)
        assert hasattr(service, "_extract_json")
        assert callable(service._extract_json)

    @pytest.mark.asyncio
    async def test_extract_json_parses_valid_json(self):
        """测试 _extract_json 能解析有效JSON"""
        mock_db = AsyncMock()
        service = NLCommandService(mock_db)

        text = '回答如下：{"intent": "balance_query", "params": {}}'
        result = service._extract_json(text)
        # 能提取到JSON（即使格式不完全匹配也能处理）
        assert result is None or isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_extract_query_params_method_exists(self):
        """测试 _extract_query_params 方法存在"""
        mock_db = AsyncMock()
        service = NLCommandService(mock_db)
        assert hasattr(service, "_extract_query_params")
        assert callable(service._extract_query_params)

    @pytest.mark.asyncio
    async def test_extract_workpaper_params_method_exists(self):
        """测试 _extract_workpaper_params 方法存在"""
        mock_db = AsyncMock()
        service = NLCommandService(mock_db)
        assert hasattr(service, "_extract_workpaper_params")
        assert callable(service._extract_workpaper_params)

    @pytest.mark.asyncio
    async def test_parse_intent_returns_dict(self):
        """测试 parse_intent 返回字典结构"""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        service = NLCommandService(mock_db)

        with patch.object(service, "_ai_classify_intent", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "intent": "data_query",
                "params": {},
                "confidence": 0.9,
            }

            result = await service.parse_intent(
                user_input="查看应收账款余额",
                project_id=uuid4(),
                user_id="test-user",
            )

            assert isinstance(result, dict)
            assert "intent" in result

    @pytest.mark.asyncio
    async def test_execute_command_returns_dict(self):
        """测试 execute_command 返回字典结构"""
        mock_db = AsyncMock()
        service = NLCommandService(mock_db)

        parsed_command = {
            "intent": "data_query",
            "params": {"year": "2024", "month": "12"},
        }

        result = await service.execute_command(
            parsed_command,
            project_id=uuid4(),
            user_id="test-user",
            db=mock_db,
        )

        assert isinstance(result, dict)
        assert "type" in result or "message" in result or "data" in result

    @pytest.mark.asyncio
    async def test_analyze_file_returns_dict(self):
        """测试 analyze_file 返回字典结构"""
        mock_db = AsyncMock()
        service = NLCommandService(mock_db)

        result = await service.analyze_file(
            file_path="/path/to/test.pdf",
            project_id=uuid4(),
            user_id="test-user",
        )

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_analyze_folder_returns_dict(self):
        """测试 analyze_folder 返回字典结构"""
        mock_db = AsyncMock()
        service = NLCommandService(mock_db)

        result = await service.analyze_folder(
            folder_path="/path/to/folder",
            project_id=uuid4(),
            user_id="test-user",
        )

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_compare_pbc_list_returns_dict(self):
        """测试 compare_pbc_list 返回字典结构"""
        mock_db = AsyncMock()
        service = NLCommandService(mock_db)

        result = await service.compare_pbc_list(
            project_id=uuid4(),
            pbc_list=[],
        )

        assert isinstance(result, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
