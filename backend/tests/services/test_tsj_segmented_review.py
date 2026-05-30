"""
TSJ 分段复核服务单测

覆盖：
- split_prompt_by_assertions 拆分正确性
- review_with_auto_segment 阈值判断
- review_segmented 独立调用逻辑
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.tsj_segmented_review_service import (
    SEGMENTATION_THRESHOLD,
    SEGMENT_MAX_TOKENS,
    split_prompt_by_assertions,
    review_segmented,
    review_with_auto_segment,
)


# ============================================================
# split_prompt_by_assertions 单测
# ============================================================


class TestSplitPromptByAssertions:
    """TSJ 提示词拆分逻辑"""

    def test_no_headings_returns_single_segment(self):
        """无 ## 标题时返回整段"""
        text = "这是一段没有标题的提示词内容\n包含多行"
        result = split_prompt_by_assertions(text)
        assert len(result) == 1
        assert result[0]["assertion"] == "全文"
        assert result[0]["content"] == text

    def test_single_heading(self):
        """单个 ## 标题"""
        text = "## 存在性\n检查应收账款是否真实存在"
        result = split_prompt_by_assertions(text)
        assert len(result) == 1
        assert result[0]["assertion"] == "存在性"
        assert "检查应收账款" in result[0]["content"]

    def test_multiple_headings(self):
        """多个认定章节拆分"""
        text = (
            "## 存在性\n检查存在性内容\n\n"
            "## 完整性\n检查完整性内容\n\n"
            "## 准确性\n检查准确性内容"
        )
        result = split_prompt_by_assertions(text)
        assert len(result) == 3
        assert result[0]["assertion"] == "存在性"
        assert result[1]["assertion"] == "完整性"
        assert result[2]["assertion"] == "准确性"

    def test_preamble_before_first_heading(self):
        """第一个标题前有前言内容"""
        text = (
            "# 应收账款审计复核提示词\n\n"
            "本提示词用于复核应收账款底稿。\n\n"
            "## 存在性\n检查存在性\n\n"
            "## 完整性\n检查完整性"
        )
        result = split_prompt_by_assertions(text)
        assert len(result) == 3
        assert result[0]["assertion"] == "前言"
        assert "应收账款审计复核" in result[0]["content"]
        assert result[1]["assertion"] == "存在性"
        assert result[2]["assertion"] == "完整性"

    def test_common_assertion_headings(self):
        """常见认定章节全覆盖"""
        headings = [
            "存在性", "完整性", "准确性",
            "权利义务", "分类", "截止", "计价和分摊",
        ]
        text = "\n\n".join(f"## {h}\n{h}的检查内容" for h in headings)
        result = split_prompt_by_assertions(text)
        assert len(result) == 7
        for i, h in enumerate(headings):
            assert result[i]["assertion"] == h

    def test_empty_string(self):
        """空字符串"""
        result = split_prompt_by_assertions("")
        assert len(result) == 1
        assert result[0]["assertion"] == "全文"
        assert result[0]["content"] == ""

    def test_heading_with_extra_spaces(self):
        """标题含前后空格"""
        text = "##  存在性 \n内容"
        result = split_prompt_by_assertions(text)
        assert len(result) == 1
        assert result[0]["assertion"] == "存在性"

    def test_segment_count_equals_heading_count(self):
        """Property 2: 分段数 == 认定章节数（无前言时）"""
        text = "## A\ncontent A\n## B\ncontent B\n## C\ncontent C"
        result = split_prompt_by_assertions(text)
        assert len(result) == 3


# ============================================================
# review_with_auto_segment 阈值判断
# ============================================================


class TestAutoSegmentThreshold:
    """自动分段阈值逻辑"""

    @pytest.mark.asyncio
    async def test_short_content_uses_single_call(self):
        """≤8000 字符走单次调用"""
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        ai_service = AsyncMock()
        ai_service.chat_completion = AsyncMock(return_value="复核结果")

        content = "短内容" * 100  # 远小于 8000
        prompt = "## 存在性\n检查\n## 完整性\n检查"

        result = await review_with_auto_segment(
            db=db,
            project_id=uuid4(),
            workpaper_id=uuid4(),
            workpaper_content=content,
            prompt_text=prompt,
            ai_service=ai_service,
            audit_cycle="receivable",
        )

        assert len(result) == 1
        # 单次调用只调一次 chat_completion
        assert ai_service.chat_completion.call_count == 1

    @pytest.mark.asyncio
    async def test_long_content_uses_segmented(self):
        """>8000 字符走分段调用"""
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        ai_service = AsyncMock()
        ai_service.chat_completion = AsyncMock(return_value="分段结果")

        content = "长" * (SEGMENTATION_THRESHOLD + 1)
        prompt = "## 存在性\n检查存在性\n## 完整性\n检查完整性"

        result = await review_with_auto_segment(
            db=db,
            project_id=uuid4(),
            workpaper_id=uuid4(),
            workpaper_content=content,
            prompt_text=prompt,
            ai_service=ai_service,
            audit_cycle="receivable",
        )

        # 2 个认定章节 → 2 次调用
        assert len(result) == 2
        assert ai_service.chat_completion.call_count == 2

    @pytest.mark.asyncio
    async def test_exactly_threshold_uses_single(self):
        """恰好 8000 字符走单次"""
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        ai_service = AsyncMock()
        ai_service.chat_completion = AsyncMock(return_value="结果")

        content = "x" * SEGMENTATION_THRESHOLD  # 恰好 8000
        prompt = "## 存在性\n检查\n## 完整性\n检查"

        result = await review_with_auto_segment(
            db=db,
            project_id=uuid4(),
            workpaper_id=uuid4(),
            workpaper_content=content,
            prompt_text=prompt,
            ai_service=ai_service,
        )

        assert len(result) == 1
        assert ai_service.chat_completion.call_count == 1


# ============================================================
# review_segmented 独立调用逻辑
# ============================================================


class TestReviewSegmented:
    """分段复核独立 LLM 调用"""

    @pytest.mark.asyncio
    async def test_each_segment_gets_independent_call(self):
        """每段独立调用 + 独立 token 预算"""
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        ai_service = AsyncMock()
        ai_service.chat_completion = AsyncMock(return_value="发现")

        segments = [
            {"assertion": "存在性", "content": "检查存在性"},
            {"assertion": "完整性", "content": "检查完整性"},
            {"assertion": "准确性", "content": "检查准确性"},
        ]

        result = await review_segmented(
            db=db,
            project_id=uuid4(),
            workpaper_id=uuid4(),
            workpaper_content="底稿内容",
            prompt_segments=segments,
            ai_service=ai_service,
            audit_cycle="cash",
        )

        assert len(result) == 3
        assert ai_service.chat_completion.call_count == 3

        # 验证每次调用都传了 max_tokens
        for call in ai_service.chat_completion.call_args_list:
            assert call.kwargs["max_tokens"] == SEGMENT_MAX_TOKENS
            assert call.kwargs["temperature"] == 0.3

    @pytest.mark.asyncio
    async def test_segment_failure_does_not_block_others(self):
        """单段失败不阻塞其他段"""
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        call_count = 0

        async def mock_chat(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("LLM 超时")
            return "正常结果"

        ai_service = AsyncMock()
        ai_service.chat_completion = mock_chat

        segments = [
            {"assertion": "存在性", "content": "检查"},
            {"assertion": "完整性", "content": "检查"},
            {"assertion": "准确性", "content": "检查"},
        ]

        result = await review_segmented(
            db=db,
            project_id=uuid4(),
            workpaper_id=uuid4(),
            workpaper_content="底稿",
            prompt_segments=segments,
            ai_service=ai_service,
        )

        # 3 段都有结果（失败段有 fallback 文本）
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_data_sources_include_assertion(self):
        """结果 data_sources 包含 assertion 名称"""
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        ai_service = AsyncMock()
        ai_service.chat_completion = AsyncMock(return_value="结果")

        segments = [{"assertion": "权利义务", "content": "检查"}]

        result = await review_segmented(
            db=db,
            project_id=uuid4(),
            workpaper_id=uuid4(),
            workpaper_content="底稿",
            prompt_segments=segments,
            ai_service=ai_service,
            audit_cycle="receivable",
        )

        assert result[0].data_sources["assertion"] == "权利义务"
        assert result[0].data_sources["review_type"] == "segmented"
        assert result[0].data_sources["audit_cycle"] == "receivable"
