"""Tests for a17_llm_service — A17 LLM 辅助生成服务"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from app.services.a17_llm_service import A17LlmService, _load_prompt, _get_chapter_def


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------


def test_load_prompt_existing_file():
    """已有的 prompt 模板文件应正确加载"""
    content = _load_prompt("chapter_draft_system.txt")
    assert "审计" in content
    assert len(content) > 50


def test_load_prompt_nonexistent_file():
    """不存在的文件应返回空字符串"""
    content = _load_prompt("nonexistent_file.txt")
    assert content == ""


# ---------------------------------------------------------------------------
# Chapter definition lookup
# ---------------------------------------------------------------------------


def test_get_chapter_def_existing():
    """已有的章节 ID 应返回定义"""
    ch = _get_chapter_def("A17-1-ch01")
    assert ch is not None
    assert ch["id"] == "A17-1-ch01"
    assert "审计业务约定" in ch["title"]


def test_get_chapter_def_nonexistent():
    """不存在的章节 ID 应返回 None"""
    ch = _get_chapter_def("A17-1-ch99")
    assert ch is None


# ---------------------------------------------------------------------------
# Service — disabled state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_chapter_draft_disabled():
    """WP_AI_SERVICE_ENABLED=False 时应返回 error"""
    svc = A17LlmService()
    db = AsyncMock()

    with patch("app.services.a17_llm_service.settings") as mock_settings:
        mock_settings.WP_AI_SERVICE_ENABLED = False
        result = await svc.generate_chapter_draft(db, uuid4(), "A17-1-ch01")

    assert "error" in result
    assert "未启用" in result["error"]


@pytest.mark.asyncio
async def test_generate_kam_description_disabled():
    """WP_AI_SERVICE_ENABLED=False 时应返回 error"""
    svc = A17LlmService()
    db = AsyncMock()

    with patch("app.services.a17_llm_service.settings") as mock_settings:
        mock_settings.WP_AI_SERVICE_ENABLED = False
        result = await svc.generate_kam_description(db, uuid4(), "收入确认")

    assert "error" in result
    assert "未启用" in result["error"]


# ---------------------------------------------------------------------------
# Service — enabled, successful generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_chapter_draft_success():
    """LLM 可用时应返回 draft"""
    svc = A17LlmService()
    db = AsyncMock()
    project_id = uuid4()

    # Mock project query
    mock_project = MagicMock()
    mock_project.name = "测试项目_2025"
    mock_project.client_name = "测试公司"
    mock_project.industry = "制造业"
    mock_project.audit_period_end = "2025-12-31"
    mock_project.business_category = "A1"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_project
    db.execute = AsyncMock(return_value=mock_result)

    with patch("app.services.a17_llm_service.settings") as mock_settings, \
         patch("app.services.llm_client.chat_completion", new_callable=AsyncMock) as mock_llm:
        mock_settings.WP_AI_SERVICE_ENABLED = True
        mock_settings.DEFAULT_CHAT_MODEL = "test-model"
        mock_llm.return_value = "这是 AI 生成的章节建议稿内容。"

        result = await svc.generate_chapter_draft(
            db, project_id, "A17-1-ch01", user_hint="关注审计范围变更"
        )

    assert result["draft"] == "这是 AI 生成的章节建议稿内容。"
    assert result["model"] == "test-model"
    assert result["confidence"] == 0.7


@pytest.mark.asyncio
async def test_generate_kam_description_success():
    """LLM 可用时应返回 KAM 描述建议稿"""
    svc = A17LlmService()
    db = AsyncMock()
    project_id = uuid4()

    mock_project = MagicMock()
    mock_project.name = "测试项目_2025"
    mock_project.client_name = "测试公司"
    mock_project.industry = "制造业"
    mock_project.audit_period_end = "2025-12-31"
    mock_project.business_category = "A1"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_project
    db.execute = AsyncMock(return_value=mock_result)

    with patch("app.services.a17_llm_service.settings") as mock_settings, \
         patch("app.services.llm_client.chat_completion", new_callable=AsyncMock) as mock_llm:
        mock_settings.WP_AI_SERVICE_ENABLED = True
        mock_settings.DEFAULT_CHAT_MODEL = "test-model"
        mock_llm.return_value = "### 一、事项情况\n收入确认涉及重大判断..."

        result = await svc.generate_kam_description(
            db, project_id, "收入确认",
            user_hint="关注合同收入时点",
            wp_refs="D4,B50",
        )

    assert "draft" in result
    assert "收入" in result["draft"]
    assert result["model"] == "test-model"


# ---------------------------------------------------------------------------
# Service — LLM error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_chapter_draft_llm_unavailable():
    """LLM 返回错误标记时应返回 error"""
    svc = A17LlmService()
    db = AsyncMock()
    project_id = uuid4()

    mock_project = MagicMock()
    mock_project.name = "测试项目"
    mock_project.client_name = None
    mock_project.industry = None
    mock_project.audit_period_end = None
    mock_project.business_category = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_project
    db.execute = AsyncMock(return_value=mock_result)

    with patch("app.services.a17_llm_service.settings") as mock_settings, \
         patch("app.services.llm_client.chat_completion", new_callable=AsyncMock) as mock_llm:
        mock_settings.WP_AI_SERVICE_ENABLED = True
        mock_settings.DEFAULT_CHAT_MODEL = "test-model"
        mock_llm.return_value = "[LLM 服务暂不可用，请检查 vLLM 是否启动]"

        result = await svc.generate_chapter_draft(db, project_id, "A17-1-ch01")

    assert "error" in result
    assert "LLM" in result["error"]


@pytest.mark.asyncio
async def test_generate_chapter_draft_invalid_chapter():
    """无效的 chapter_id 应返回 error"""
    svc = A17LlmService()
    db = AsyncMock()

    with patch("app.services.a17_llm_service.settings") as mock_settings:
        mock_settings.WP_AI_SERVICE_ENABLED = True
        result = await svc.generate_chapter_draft(db, uuid4(), "A17-1-ch99")

    assert "error" in result
    assert "未找到" in result["error"]


@pytest.mark.asyncio
async def test_generate_chapter_draft_exception_handling():
    """LLM 调用异常时应优雅返回 error 而不崩溃"""
    svc = A17LlmService()
    db = AsyncMock()
    project_id = uuid4()

    mock_project = MagicMock()
    mock_project.name = "测试项目"
    mock_project.client_name = None
    mock_project.industry = None
    mock_project.audit_period_end = None
    mock_project.business_category = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_project
    db.execute = AsyncMock(return_value=mock_result)

    with patch("app.services.a17_llm_service.settings") as mock_settings, \
         patch("app.services.llm_client.chat_completion", new_callable=AsyncMock) as mock_llm:
        mock_settings.WP_AI_SERVICE_ENABLED = True
        mock_settings.DEFAULT_CHAT_MODEL = "test-model"
        mock_llm.side_effect = RuntimeError("连接超时")

        result = await svc.generate_chapter_draft(db, project_id, "A17-1-ch01")

    assert "error" in result
    assert "失败" in result["error"]
