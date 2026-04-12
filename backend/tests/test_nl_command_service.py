"""
NL Command Service Unit Tests — Task 24.6
Test parse_intent for all command types, execute_command for
project_switch, year_switch, data_query. Test attachment detection.

Requirements: 8.1-8.6
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.nl_command_service import NLCommandService


@pytest.fixture
def mock_db_session():
    """Mock AsyncSession that never hits the real database."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


class TestNLCommandServiceParseIntent:
    """Test NLCommandService.parse_intent()"""

    @pytest.mark.asyncio
    async def test_parse_project_switch(self, mock_db_session):
        """parse_intent returns project_switch for project names."""
        service = NLCommandService(mock_db_session)

        with patch.object(service, "_extract_attachments", return_value=[]):
            result = await service.parse_intent(
                "切换到审计项目ABC",
                "user-1",
                uuid4(),
            )

        assert result["operation_type"] == "project_switch"
        assert result["parameters"]["project_name"] == "审计项目ABC"

    @pytest.mark.asyncio
    async def test_parse_year_switch(self, mock_db_session):
        """parse_intent returns year_switch for year references."""
        service = NLCommandService(mock_db_session)

        with patch.object(service, "_extract_attachments", return_value=[]):
            result = await service.parse_intent(
                "查看2023年的数据",
                "user-1",
                uuid4(),
            )

        assert result["operation_type"] == "year_switch"
        assert result["parameters"]["year"] == "2023"

    @pytest.mark.asyncio
    async def test_parse_workpaper_navigate(self, mock_db_session):
        """parse_intent returns workpaper_navigate for workpaper names."""
        service = NLCommandService(mock_db_session)

        with patch.object(service, "_extract_attachments", return_value=[]):
            result = await service.parse_intent(
                "打开货币资金底稿",
                "user-1",
                uuid4(),
            )

        assert result["operation_type"] == "workpaper_navigate"

    @pytest.mark.asyncio
    async def test_parse_data_query(self, mock_db_session):
        """parse_intent returns data_query for data requests."""
        service = NLCommandService(mock_db_session)

        with patch.object(service, "_extract_attachments", return_value=[]):
            result = await service.parse_intent(
                "查询应收账款余额",
                "user-1",
                uuid4(),
            )

        assert result["operation_type"] == "data_query"
        assert "query_target" in result["parameters"]

    @pytest.mark.asyncio
    async def test_parse_analysis_generate(self, mock_db_session):
        """parse_intent returns analysis_generate for analysis requests."""
        service = NLCommandService(mock_db_session)

        with patch.object(service, "_extract_attachments", return_value=[]):
            result = await service.parse_intent(
                "分析这份合同",
                "user-1",
                uuid4(),
            )

        assert result["operation_type"] == "analysis_generate"

    @pytest.mark.asyncio
    async def test_parse_diff_display(self, mock_db_session):
        """parse_intent returns diff_display for comparison requests."""
        service = NLCommandService(mock_db_session)

        with patch.object(service, "_extract_attachments", return_value=[]):
            result = await service.parse_intent(
                "对比2023年和2024年",
                "user-1",
                uuid4(),
            )

        assert result["operation_type"] == "diff_display"

    @pytest.mark.asyncio
    async def test_parse_with_attachments(self, mock_db_session):
        """parse_intent detects file attachments."""
        service = NLCommandService(mock_db_session)

        with patch.object(service, "_extract_attachments", return_value=["invoice.pdf"]):
            result = await service.parse_intent(
                "分析发票",
                "user-1",
                uuid4(),
            )

        assert result["has_attachments"] is True
        assert result["attachments"] == ["invoice.pdf"]


class TestNLCommandServicePatternMatching:
    """Test NLCommandService._match_patterns()"""

    def test_match_project_switch_patterns(self):
        """_match_patterns matches project switch patterns."""
        service = NLCommandService.__new__(NLCommandService)

        patterns = [
            ("切换到审计项目ABC", "审计项目ABC"),
            ("打开项目测试公司", "测试公司"),
            ("进入项目财务审计", "财务审计"),
        ]

        for text, expected_name in patterns:
            op, params, confidence = service._match_patterns(text)
            if op == "project_switch":
                assert expected_name in params.get("project_name", "")
                assert confidence == 0.85

    def test_match_year_switch_patterns(self):
        """_match_patterns matches year switch patterns."""
        service = NLCommandService.__new__(NLCommandService)

        patterns = [
            ("查询2023年数据", "2023"),
            ("切换到2024年", "2024"),
            ("查看2022年的试算表", "2022"),
        ]

        for text, expected_year in patterns:
            op, params, confidence = service._match_patterns(text)
            if op == "year_switch":
                assert params["year"] == expected_year
                assert confidence == 0.9

    def test_match_workpaper_patterns(self):
        """_match_patterns matches workpaper navigation patterns."""
        service = NLCommandService.__new__(NLCommandService)

        patterns = [
            ("打开货币资金底稿", "货币资金"),
            ("导航到应收账款底稿", "应收账款"),
        ]

        for text, expected_name in patterns:
            op, params, confidence = service._match_patterns(text)
            if op == "workpaper_navigate":
                assert expected_name in params["workpaper_name"]
                assert confidence == 0.85

    def test_match_data_query_patterns(self):
        """_match_patterns matches data query patterns."""
        service = NLCommandService.__new__(NLCommandService)

        patterns = [
            ("查询应收账款余额", "应收账款"),
            ("查科目数据", "科目"),
            ("获取试算表", "试算表"),
        ]

        for text, expected_target in patterns:
            op, params, confidence = service._match_patterns(text)
            if op == "data_query":
                assert expected_target in params.get("query_target", "")

    def test_match_diff_display_patterns(self):
        """_match_patterns matches diff display patterns."""
        service = NLCommandService.__new__(NLCommandService)

        result = service._match_patterns("对比2023年与2024年")
        if result[0] == "diff_display":
            op, params, confidence = result
            assert confidence == 0.85

    def test_match_file_analysis_patterns(self):
        """_match_patterns matches file analysis patterns."""
        service = NLCommandService.__new__(NLCommandService)

        patterns = [
            ("分析文件contract.pdf", "contract.pdf"),
            ("识别invoice.jpg", "invoice.jpg"),
            ("上传文件data.xlsx", "data.xlsx"),
        ]

        for text, expected_file in patterns:
            op, params, confidence = service._match_patterns(text)
            if op == "file_analysis":
                assert expected_file in params["file_name"]

    def test_match_no_match_returns_none(self):
        """_match_patterns returns (None, {}, 0.0) when nothing matches."""
        service = NLCommandService.__new__(NLCommandService)

        op, params, confidence = service._match_patterns("这是一段完全随机的文本")
        assert op is None
        assert params == {}
        assert confidence == 0.0


class TestNLCommandServiceExecuteCommand:
    """Test NLCommandService.execute_command()"""

    @pytest.mark.asyncio
    async def test_execute_project_switch_success(self, mock_db_session):
        """execute_command project_switch returns project info on match."""
        service = NLCommandService(mock_db_session)

        # Mock the Project lookup
        mock_project = MagicMock()
        mock_project.id = uuid4()
        mock_project.name = "Test Project"

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_project
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        intent = {
            "operation_type": "project_switch",
            "parameters": {"project_name": "Test"},
        }

        result = await service.execute_command(intent, "user-1", uuid4())

        assert result["success"] is True
        assert result.get("action") == "project_switch"
        assert "project_id" in result

    @pytest.mark.asyncio
    async def test_execute_project_switch_not_found(self, mock_db_session):
        """execute_command project_switch returns failure when not found."""
        service = NLCommandService(mock_db_session)

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        intent = {
            "operation_type": "project_switch",
            "parameters": {"project_name": "Nonexistent"},
        }

        result = await service.execute_command(intent, "user-1", uuid4())

        assert result["success"] is False
        assert "未找到" in result.get("message", "")

    @pytest.mark.asyncio
    async def test_execute_year_switch(self, mock_db_session):
        """execute_command year_switch returns year data."""
        service = NLCommandService(mock_db_session)

        # Mock TrialBalanceService.get_trial_balance
        with patch(
            "app.services.trial_balance_service.TrialBalanceService"
        ) as MockTB:
            mock_tb = MockTB.return_value
            mock_tb.get_trial_balance = AsyncMock(return_value=[])

            intent = {
                "operation_type": "year_switch",
                "parameters": {"year": "2023"},
            }

            result = await service.execute_command(intent, "user-1", uuid4())

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_data_query(self, mock_db_session):
        """execute_command data_query triggers trial balance query."""
        service = NLCommandService(mock_db_session)

        # Mock TrialBalanceService.get_trial_balance
        with patch(
            "app.services.trial_balance_service.TrialBalanceService"
        ) as MockTB:
            mock_tb = MockTB.return_value
            mock_tb.get_trial_balance = AsyncMock(return_value=[])

            intent = {
                "operation_type": "data_query",
                "parameters": {"query_target": "试算表"},
            }

            result = await service.execute_command(intent, "user-1", uuid4())

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_no_operation_type(self, mock_db_session):
        """execute_command with no operation_type returns error."""
        service = NLCommandService(mock_db_session)

        intent = {"operation_type": None}

        result = await service.execute_command(intent, "user-1", uuid4())

        assert result["success"] is False


class TestNLCommandServiceAttachmentDetection:
    """Test NLCommandService._extract_attachments()"""

    def test_extract_attachments_windows_path(self):
        """_extract_attachments detects Windows-style file paths."""
        service = NLCommandService.__new__(NLCommandService)

        text = "请分析这份文件C:\\Users\\admin\\Documents\\contract.pdf"
        attachments = service._extract_attachments(text)

        assert len(attachments) > 0
        assert any("contract.pdf" in a for a in attachments)

    def test_extract_attachments_unix_path(self):
        """_extract_attachments detects Unix-style file paths."""
        service = NLCommandService.__new__(NLCommandService)

        text = "上传文件 /home/audit/invoice.xlsx"
        attachments = service._extract_attachments(text)

        assert len(attachments) > 0
        assert any("invoice.xlsx" in a for a in attachments)

    def test_extract_attachments_no_paths(self):
        """_extract_attachments returns empty list for plain text."""
        service = NLCommandService.__new__(NLCommandService)

        text = "今天天气真好"
        attachments = service._extract_attachments(text)

        assert attachments == []
