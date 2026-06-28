"""Tests for b14_ai_generate — B1-4 尽职调查报告 AI 生成端点

测试覆盖:
- 正常调用返回正确 schema (Req 6.2)
- 知识库无匹配文档时继续生成不报错 (Req 6.3)
- LLM 服务不可用时返回 503 + error (Req 6.7)
- 无效 chapter_id 返回 400 (Req 6.4)
- AI 服务未启用时返回 503 (Req 6.7)
- prompt 包含必需上下文 (Req 6.4, 6.8)
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from app.routers.b14_ai_generate import (
    _build_user_prompt,
    _CHAPTER_TITLE_MAP,
    _SYSTEM_PROMPT_TEMPLATE,
    B14AiGenerateRequest,
)


# ---------------------------------------------------------------------------
# 辅助函数测试
# ---------------------------------------------------------------------------


class TestChapterTitleMap:
    """章节标题映射完整性"""

    def test_all_13_chapters_mapped(self):
        assert len(_CHAPTER_TITLE_MAP) == 13

    def test_ch1_is_序言(self):
        assert _CHAPTER_TITLE_MAP["ch1"] == "序言"

    def test_ch13_is_主要问题(self):
        assert _CHAPTER_TITLE_MAP["ch13"] == "公司存在的主要问题及建议"


class TestBuildUserPrompt:
    """用户 prompt 构造逻辑"""

    def test_generate_mode_includes_chapter_title(self):
        prompt = _build_user_prompt(
            chapter_title="序言",
            mode="generate",
            user_hint="",
            current_content="",
            cross_chapter_ctx="",
            kb_docs=[],
        )
        assert "序言" in prompt
        assert "生成" in prompt

    def test_polish_mode_includes_current_content(self):
        prompt = _build_user_prompt(
            chapter_title="报告概要",
            mode="polish",
            user_hint="",
            current_content="这是已有内容",
            cross_chapter_ctx="",
            kb_docs=[],
        )
        assert "这是已有内容" in prompt
        assert "润色" in prompt

    def test_user_hint_injected(self):
        prompt = _build_user_prompt(
            chapter_title="序言",
            mode="generate",
            user_hint="关注IPO相关内容",
            current_content="",
            cross_chapter_ctx="",
            kb_docs=[],
        )
        assert "关注IPO相关内容" in prompt

    def test_knowledge_base_docs_injected(self):
        prompt = _build_user_prompt(
            chapter_title="序言",
            mode="generate",
            user_hint="",
            current_content="",
            cross_chapter_ctx="",
            kb_docs=["【知识库 - 尽调模板】\n参考内容1", "【知识库 - 行业报告】\n参考内容2"],
        )
        assert "参考内容1" in prompt
        assert "参考内容2" in prompt
        assert "知识库参考文档" in prompt

    def test_cross_chapter_context_injected(self):
        prompt = _build_user_prompt(
            chapter_title="序言",
            mode="generate",
            user_hint="",
            current_content="",
            cross_chapter_ctx="[b14-ch2-content] 调查目的概述...",
            kb_docs=[],
        )
        assert "其他章节上下文" in prompt
        assert "调查目的概述" in prompt

    def test_empty_kb_docs_no_section_header(self):
        prompt = _build_user_prompt(
            chapter_title="序言",
            mode="generate",
            user_hint="",
            current_content="",
            cross_chapter_ctx="",
            kb_docs=[],
        )
        assert "知识库参考文档" not in prompt


class TestSystemPromptTemplate:
    """System prompt 模板格式"""

    def test_template_contains_cpa_rules(self):
        prompt = _SYSTEM_PROMPT_TEMPLATE.format(
            chapter_title="序言",
            client_name="测试公司",
            industry="制造业",
            audit_period="2025年度",
            firm_name="致同会计师事务所（特殊普通合伙）",
        )
        assert "注册会计师" in prompt
        assert "CPA" in prompt
        assert "人民币" in prompt
        assert "两位小数" in prompt
        assert "测试公司" in prompt
        assert "制造业" in prompt
        assert "2025年度" in prompt


# ---------------------------------------------------------------------------
# 端点逻辑测试（通过直接调用函数，mock 依赖）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_b14_ai_generate_invalid_chapter_id():
    """无效的 chapter_id 应返回 400"""
    from fastapi import HTTPException
    from app.routers.b14_ai_generate import b14_ai_generate

    db = AsyncMock()
    user = MagicMock()
    body = B14AiGenerateRequest(mode="generate")

    with pytest.raises(HTTPException) as exc_info:
        await b14_ai_generate(uuid4(), "ch99", body, db, user)

    assert exc_info.value.status_code == 400
    assert "无效" in exc_info.value.detail


@pytest.mark.asyncio
async def test_b14_ai_generate_service_disabled():
    """AI 服务未启用时应返回 503"""
    from fastapi import HTTPException
    from app.routers.b14_ai_generate import b14_ai_generate

    db = AsyncMock()
    user = MagicMock()
    body = B14AiGenerateRequest(mode="generate")

    with patch("app.routers.b14_ai_generate.settings") as mock_settings:
        mock_settings.WP_AI_SERVICE_ENABLED = False

        with pytest.raises(HTTPException) as exc_info:
            await b14_ai_generate(uuid4(), "ch1", body, db, user)

    assert exc_info.value.status_code == 503
    assert "未启用" in exc_info.value.detail


@pytest.mark.asyncio
async def test_b14_ai_generate_success():
    """LLM 正常返回时应返回完整 schema"""
    from app.routers.b14_ai_generate import b14_ai_generate

    db = AsyncMock()
    user = MagicMock()
    project_id = uuid4()
    body = B14AiGenerateRequest(mode="generate", user_hint="关注IPO")

    # Mock _load_project_context
    # Mock _load_cross_chapter_summaries
    # Mock _load_knowledge_base_docs
    # Mock chat_completion
    with patch("app.routers.b14_ai_generate.settings") as mock_settings, \
         patch("app.routers.b14_ai_generate._load_project_context", new_callable=AsyncMock) as mock_ctx, \
         patch("app.routers.b14_ai_generate._load_cross_chapter_summaries", new_callable=AsyncMock) as mock_cross, \
         patch("app.routers.b14_ai_generate._load_knowledge_base_docs", new_callable=AsyncMock) as mock_kb, \
         patch("app.services.llm_client.chat_completion", new_callable=AsyncMock) as mock_llm:

        mock_settings.WP_AI_SERVICE_ENABLED = True
        mock_settings.DEFAULT_CHAT_MODEL = "Qwen3.5-27B"
        mock_ctx.return_value = {
            "client_name": "测试公司",
            "industry": "制造业",
            "audit_period": "2025年度",
            "firm_name": "致同会计师事务所（特殊普通合伙）",
        }
        mock_cross.return_value = ""
        mock_kb.return_value = []
        mock_llm.return_value = "这是尽调报告序言章节的建议稿内容。"

        result = await b14_ai_generate(project_id, "ch1", body, db, user)

    assert result.draft == "这是尽调报告序言章节的建议稿内容。"
    assert result.model == "Qwen3.5-27B"
    assert result.confidence == 0.85
    assert result.error is None


@pytest.mark.asyncio
async def test_b14_ai_generate_llm_unavailable():
    """LLM 服务不可用（返回错误标记）时应返回 503"""
    from fastapi import HTTPException
    from app.routers.b14_ai_generate import b14_ai_generate

    db = AsyncMock()
    user = MagicMock()
    body = B14AiGenerateRequest(mode="generate")

    with patch("app.routers.b14_ai_generate.settings") as mock_settings, \
         patch("app.routers.b14_ai_generate._load_project_context", new_callable=AsyncMock) as mock_ctx, \
         patch("app.routers.b14_ai_generate._load_cross_chapter_summaries", new_callable=AsyncMock) as mock_cross, \
         patch("app.routers.b14_ai_generate._load_knowledge_base_docs", new_callable=AsyncMock) as mock_kb, \
         patch("app.services.llm_client.chat_completion", new_callable=AsyncMock) as mock_llm:

        mock_settings.WP_AI_SERVICE_ENABLED = True
        mock_settings.DEFAULT_CHAT_MODEL = "test-model"
        mock_ctx.return_value = {"client_name": "", "industry": "", "audit_period": "", "firm_name": ""}
        mock_cross.return_value = ""
        mock_kb.return_value = []
        mock_llm.return_value = "[LLM 服务暂不可用，请检查 vLLM 是否启动]"

        with pytest.raises(HTTPException) as exc_info:
            await b14_ai_generate(uuid4(), "ch1", body, db, user)

    assert exc_info.value.status_code == 503
    assert "LLM" in exc_info.value.detail


@pytest.mark.asyncio
async def test_b14_ai_generate_llm_exception():
    """LLM 调用抛异常时应返回 503"""
    from fastapi import HTTPException
    from app.routers.b14_ai_generate import b14_ai_generate

    db = AsyncMock()
    user = MagicMock()
    body = B14AiGenerateRequest(mode="generate")

    with patch("app.routers.b14_ai_generate.settings") as mock_settings, \
         patch("app.routers.b14_ai_generate._load_project_context", new_callable=AsyncMock) as mock_ctx, \
         patch("app.routers.b14_ai_generate._load_cross_chapter_summaries", new_callable=AsyncMock) as mock_cross, \
         patch("app.routers.b14_ai_generate._load_knowledge_base_docs", new_callable=AsyncMock) as mock_kb, \
         patch("app.services.llm_client.chat_completion", new_callable=AsyncMock) as mock_llm:

        mock_settings.WP_AI_SERVICE_ENABLED = True
        mock_settings.DEFAULT_CHAT_MODEL = "test-model"
        mock_ctx.return_value = {"client_name": "", "industry": "", "audit_period": "", "firm_name": ""}
        mock_cross.return_value = ""
        mock_kb.return_value = []
        mock_llm.side_effect = Exception("httpx.ConnectError: connection refused")

        with pytest.raises(HTTPException) as exc_info:
            await b14_ai_generate(uuid4(), "ch1", body, db, user)

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_b14_ai_generate_kb_empty_continues():
    """知识库无匹配文档时继续生成不报错"""
    from app.routers.b14_ai_generate import b14_ai_generate

    db = AsyncMock()
    user = MagicMock()
    body = B14AiGenerateRequest(mode="generate")

    with patch("app.routers.b14_ai_generate.settings") as mock_settings, \
         patch("app.routers.b14_ai_generate._load_project_context", new_callable=AsyncMock) as mock_ctx, \
         patch("app.routers.b14_ai_generate._load_cross_chapter_summaries", new_callable=AsyncMock) as mock_cross, \
         patch("app.routers.b14_ai_generate._load_knowledge_base_docs", new_callable=AsyncMock) as mock_kb, \
         patch("app.services.llm_client.chat_completion", new_callable=AsyncMock) as mock_llm:

        mock_settings.WP_AI_SERVICE_ENABLED = True
        mock_settings.DEFAULT_CHAT_MODEL = "test-model"
        mock_ctx.return_value = {"client_name": "测试", "industry": "", "audit_period": "", "firm_name": ""}
        mock_cross.return_value = ""
        mock_kb.return_value = []  # 空知识库
        mock_llm.return_value = "生成成功，无知识库参考。"

        result = await b14_ai_generate(uuid4(), "ch1", body, db, user)

    assert result.draft == "生成成功，无知识库参考。"
    assert result.error is None


@pytest.mark.asyncio
async def test_b14_ai_generate_polish_mode():
    """polish 模式应将 current_content 传入 prompt"""
    from app.routers.b14_ai_generate import b14_ai_generate

    db = AsyncMock()
    user = MagicMock()
    body = B14AiGenerateRequest(
        mode="polish",
        current_content="原始内容需要润色",
    )

    captured_messages = []

    async def capture_llm(messages, **kwargs):
        captured_messages.extend(messages)
        return "润色后的内容"

    with patch("app.routers.b14_ai_generate.settings") as mock_settings, \
         patch("app.routers.b14_ai_generate._load_project_context", new_callable=AsyncMock) as mock_ctx, \
         patch("app.routers.b14_ai_generate._load_cross_chapter_summaries", new_callable=AsyncMock) as mock_cross, \
         patch("app.routers.b14_ai_generate._load_knowledge_base_docs", new_callable=AsyncMock) as mock_kb, \
         patch("app.services.llm_client.chat_completion", side_effect=capture_llm):

        mock_settings.WP_AI_SERVICE_ENABLED = True
        mock_settings.DEFAULT_CHAT_MODEL = "test-model"
        mock_ctx.return_value = {"client_name": "", "industry": "", "audit_period": "", "firm_name": ""}
        mock_cross.return_value = ""
        mock_kb.return_value = []

        result = await b14_ai_generate(uuid4(), "ch1", body, db, user)

    assert result.draft == "润色后的内容"
    # 验证 user prompt 中包含了原始内容
    user_msg = captured_messages[1]["content"]
    assert "原始内容需要润色" in user_msg
    assert "润色" in user_msg
