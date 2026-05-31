"""
TSJ 结构化输出服务单测

覆盖：
- Task 3.1: build_structured_prompt 构建
- Task 3.2: parse_findings_json 解析 + write_findings_to_ai_content 写入
- Task 3.3: process_review_response fallback 逻辑
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.tsj_structured_output_service import (
    STRUCTURED_OUTPUT_INSTRUCTION,
    build_structured_prompt,
    parse_findings_json,
    process_review_response,
    write_findings_to_ai_content,
)


# --------------------------------------------------------------------------
# Task 3.1: build_structured_prompt
# --------------------------------------------------------------------------


class TestBuildStructuredPrompt:
    def test_appends_instruction(self):
        result = build_structured_prompt("检查存在性", "底稿内容ABC")
        assert "检查存在性" in result
        assert "底稿内容ABC" in result
        assert STRUCTURED_OUTPUT_INSTRUCTION in result

    def test_contains_json_format_requirement(self):
        result = build_structured_prompt("base", "content")
        assert '"findings"' in result
        assert "issue_type" in result
        assert "severity" in result


# --------------------------------------------------------------------------
# Task 3.2: parse_findings_json
# --------------------------------------------------------------------------


class TestParseFindingsJson:
    def test_direct_json(self):
        """直接 JSON 文本解析"""
        text = json.dumps({
            "findings": [
                {
                    "issue_type": "数值错误",
                    "severity": "high",
                    "sheet": "应收账款明细",
                    "cell_range": "B5:D5",
                    "description": "金额不匹配",
                    "evidence_ref": "D2-3!B5",
                    "remediation": "核实原始凭证",
                }
            ]
        })
        result = parse_findings_json(text)
        assert result is not None
        assert len(result) == 1
        assert result[0]["issue_type"] == "数值错误"

    def test_code_block_json(self):
        """从 markdown 代码块提取"""
        text = "以下是复核结果：\n```json\n" + json.dumps({
            "findings": [{"issue_type": "逻辑错误", "severity": "medium",
                          "sheet": "S1", "cell_range": "A1",
                          "description": "desc", "evidence_ref": "",
                          "remediation": "fix"}]
        }) + "\n```\n其他文字"
        result = parse_findings_json(text)
        assert result is not None
        assert len(result) == 1
        assert result[0]["issue_type"] == "逻辑错误"

    def test_embedded_json_object(self):
        """从文本中提取 {...} 模式"""
        text = '复核完成，结果如下：{"findings": [{"issue_type": "披露缺失", "severity": "low", "sheet": "X", "cell_range": "C1", "description": "d", "evidence_ref": "", "remediation": "r"}]} 以上。'
        result = parse_findings_json(text)
        assert result is not None
        assert len(result) == 1

    def test_empty_findings(self):
        """空 findings 数组"""
        text = '{"findings": []}'
        result = parse_findings_json(text)
        assert result is not None
        assert len(result) == 0

    def test_invalid_json_returns_none(self):
        """无法解析时返回 None"""
        result = parse_findings_json("这是一段纯文本复核结果，没有JSON格式。")
        assert result is None

    def test_empty_string_returns_none(self):
        result = parse_findings_json("")
        assert result is None

    def test_none_like_returns_none(self):
        result = parse_findings_json("   ")
        assert result is None

    def test_top_level_array(self):
        """顶层直接是数组"""
        text = json.dumps([
            {"issue_type": "证据不足", "severity": "high",
             "sheet": "S", "cell_range": "A1:A2",
             "description": "d", "evidence_ref": "ref",
             "remediation": "r"}
        ])
        result = parse_findings_json(text)
        assert result is not None
        assert len(result) == 1


# --------------------------------------------------------------------------
# Task 3.2: write_findings_to_ai_content
# --------------------------------------------------------------------------


class TestWriteFindingsToAiContent:
    @pytest.mark.asyncio
    async def test_writes_one_record_per_finding(self):
        """每条 finding 写入一条 AIContent"""
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        findings = [
            {
                "issue_type": "数值错误",
                "severity": "high",
                "sheet": "应收账款明细",
                "cell_range": "B5:D5",
                "description": "金额不匹配",
                "evidence_ref": "D2-3!B5",
                "remediation": "核实原始凭证",
            },
            {
                "issue_type": "披露缺失",
                "severity": "low",
                "sheet": "附注",
                "cell_range": "A10",
                "description": "缺少披露",
                "evidence_ref": "",
                "remediation": "补充披露",
            },
        ]

        results = await write_findings_to_ai_content(
            db=db,
            project_id=uuid.uuid4(),
            workpaper_id=uuid.uuid4(),
            wp_code="D2-3",
            findings=findings,
            audit_cycle="D",
        )

        assert len(results) == 2
        assert db.add.call_count == 2
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_target_cell_format(self):
        """target_cell 格式为 {wp_code}:{sheet}:{cell_range}"""
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        findings = [
            {
                "issue_type": "数值错误",
                "severity": "medium",
                "sheet": "应收账款明细",
                "cell_range": "B5:D5",
                "description": "desc",
                "evidence_ref": "",
                "remediation": "",
            }
        ]

        results = await write_findings_to_ai_content(
            db=db,
            project_id=uuid.uuid4(),
            workpaper_id=uuid.uuid4(),
            wp_code="D2-3",
            findings=findings,
        )

        ai_content = results[0]
        assert ai_content.data_sources["target_cell"] == "D2-3:应收账款明细:B5:D5"

    @pytest.mark.asyncio
    async def test_confirmation_status_pending(self):
        """所有写入的记录 confirmation_status = pending"""
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        findings = [
            {"issue_type": "逻辑错误", "severity": "high",
             "sheet": "S", "cell_range": "A1",
             "description": "d", "evidence_ref": "", "remediation": "r"}
        ]

        results = await write_findings_to_ai_content(
            db=db,
            project_id=uuid.uuid4(),
            workpaper_id=uuid.uuid4(),
            wp_code="D2",
            findings=findings,
        )

        from app.models.ai_models import AIConfirmationStatus
        assert results[0].confirmation_status == AIConfirmationStatus.pending

    @pytest.mark.asyncio
    async def test_empty_findings_no_commit(self):
        """空 findings 不触发 commit"""
        db = AsyncMock()
        db.commit = AsyncMock()

        results = await write_findings_to_ai_content(
            db=db,
            project_id=uuid.uuid4(),
            workpaper_id=uuid.uuid4(),
            wp_code="D2",
            findings=[],
        )

        assert len(results) == 0
        db.commit.assert_not_awaited()


# --------------------------------------------------------------------------
# Task 3.3: process_review_response (fallback)
# --------------------------------------------------------------------------


class TestProcessReviewResponse:
    @pytest.mark.asyncio
    async def test_structured_parse_success(self):
        """结构化解析成功时逐条写入"""
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        response = json.dumps({
            "findings": [
                {"issue_type": "数值错误", "severity": "high",
                 "sheet": "S1", "cell_range": "B1",
                 "description": "问题1", "evidence_ref": "ref1",
                 "remediation": "修复1"},
                {"issue_type": "披露缺失", "severity": "low",
                 "sheet": "S2", "cell_range": "C2",
                 "description": "问题2", "evidence_ref": "ref2",
                 "remediation": "修复2"},
            ]
        })

        results = await process_review_response(
            db=db,
            project_id=uuid.uuid4(),
            workpaper_id=uuid.uuid4(),
            wp_code="D2-3",
            response_text=response,
            audit_cycle="D",
        )

        assert len(results) == 2
        assert results[0].data_sources["review_type"] == "structured"

    @pytest.mark.asyncio
    async def test_fallback_plain_text(self):
        """解析失败时 fallback 为纯文本单条存储"""
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        plain_text = "这是一段无法解析为JSON的复核结果，包含多项发现但格式不规范。"

        results = await process_review_response(
            db=db,
            project_id=uuid.uuid4(),
            workpaper_id=uuid.uuid4(),
            wp_code="D2-3",
            response_text=plain_text,
            audit_cycle="D",
        )

        assert len(results) == 1
        assert results[0].content_text == plain_text
        assert results[0].data_sources["review_type"] == "unstructured_fallback"
        assert results[0].data_sources["parse_failed"] is True

    @pytest.mark.asyncio
    async def test_fallback_preserves_full_response(self):
        """fallback 不丢数据：完整保留原始响应"""
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        long_text = "复核发现：\n1. 应收账款余额异常\n2. 存货计价方法不一致\n" * 10

        results = await process_review_response(
            db=db,
            project_id=uuid.uuid4(),
            workpaper_id=uuid.uuid4(),
            wp_code="F2",
            response_text=long_text,
        )

        assert results[0].content_text == long_text
