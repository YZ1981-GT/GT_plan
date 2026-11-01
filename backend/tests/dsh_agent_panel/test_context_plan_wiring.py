"""Chat Run 显式引用、附件和复核提示词必须真实进入 ContextPlan。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.ai_models import AttachmentOcrStatus, ChatEngineName
from app.services.ai_chat.context_plan import build_context_plan
from app.services.ai_chat.engine import AuthorizedChatRunRequest
from app.services.ai_chat.mention_service import MentionContentItem
from app.services.ai_chat.review_mode import ReviewModeContext
from app.services.ai_chat.run_resource_service import ProjectAttachmentContextItem
from app.services.ai_chat.run_contract import CAPABILITIES_BY_ENGINE
from app.services.doc_ai_context_builder import ChatContext, Citation, SearchHit


class _Builder:
    token_budget = 8000

    async def build(self, *, host, query, user, enforce_budget=True):
        assert enforce_budget is False
        return ChatContext(
            doc_excerpt="当前底稿正文",
            project_summary="项目摘要",
            knowledge_hits=[
                SearchHit("knowledge_doc", str(uuid4()), "知识片段", 0.9, 0, "准则文档")
            ],
            citations=[],
            token_estimate=1,
        )

    def build_citations(self, hits):
        return [
            Citation(h.source_type, h.source_id, h.source_name, h.chunk_index, h.content[:20])
            for h in hits
        ]


def _request(attachment_ids=(), project_attachment_ids=()):
    host = SimpleNamespace(
        principal_id=uuid4(),
        project_id=uuid4(),
        year=2025,
        resource_type=SimpleNamespace(value="workpaper"),
        resource_id=str(uuid4()),
        display_label="E1 货币资金",
        project_tools_enabled=True,
    )
    return AuthorizedChatRunRequest(
        run_id=uuid4(),
        session_id=uuid4(),
        request_id=uuid4(),
        host=host,
        query="请复核",
        engine=ChatEngineName.native,
        capabilities=CAPABILITIES_BY_ENGINE[ChatEngineName.native],
        assistant_message_id=uuid4(),
        principal=SimpleNamespace(id=host.principal_id),
        review_mode=True,
        sheet_name="审定表",
        mentions=((SimpleNamespace(value="workpaper"), str(uuid4())),),
        attachment_ids=tuple(attachment_ids),
        project_attachment_ids=tuple(project_attachment_ids),
    )


@pytest.mark.asyncio
async def test_all_selected_context_reaches_one_system_message_and_manifest() -> None:
    attachment_id = uuid4()
    request = _request((attachment_id,))
    review = ReviewModeContext(
        enabled=True,
        wp_code="E1",
        sheet_name="审定表",
        source_level="sheet",
        prompt_content="复核提示词正文",
        tips=[],
        checklist=[],
        risk_areas=[],
        version="v1",
    )
    mention = MentionContentItem(
        type="workpaper",
        id=str(uuid4()),
        label="被引用底稿",
        content="显式引用正文",
        token_estimate=10,
        status="included",
    )
    attachment = SimpleNamespace(
        id=attachment_id,
        original_name="银行回函.pdf",
        ocr_status=AttachmentOcrStatus.succeeded.value,
        ocr_text_protected="附件 OCR 正文",
    )

    with patch(
        "app.services.ai_chat.context_plan.resolve_review_mode",
        new=AsyncMock(return_value=review),
    ), patch(
        "app.services.ai_chat.context_plan.load_mention_context",
        new=AsyncMock(return_value=[mention]),
    ), patch(
        "app.services.ai_chat.context_plan.AttachmentService.validate_for_run",
        new=AsyncMock(return_value=[attachment]),
    ):
        plan = await build_context_plan(
            MagicMock(), request=request, context_builder=_Builder()
        )

    for expected in (
        "当前底稿正文",
        "项目摘要",
        "知识片段",
        "复核提示词正文",
        "显式引用正文",
        "附件 OCR 正文",
    ):
        assert expected in plan.system_message
    assert plan.system_message.count("<<<平台上下文数据 开始>>>") == 1
    rows = [row for key in ("included", "trimmed") for row in plan.manifest.get(key, [])]
    assert {row["source_type"] for row in rows} >= {
        "workpaper", "project_summary", "review_prompt", "mention:workpaper", "attachment", "knowledge_doc"
    }


@pytest.mark.asyncio
async def test_unowned_attachment_is_denied_and_never_enters_prompt() -> None:
    missing_id = uuid4()
    request = _request((missing_id,))
    with patch(
        "app.services.ai_chat.context_plan.resolve_review_mode",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.services.ai_chat.context_plan.load_mention_context",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.services.ai_chat.context_plan.AttachmentService.validate_for_run",
        new=AsyncMock(return_value=[]),
    ):
        plan = await build_context_plan(
            MagicMock(), request=request, context_builder=_Builder()
        )

    assert str(missing_id) not in plan.system_message
    denied = plan.manifest.get("denied", [])
    assert any(row["source_id"] == str(missing_id) for row in denied)


@pytest.mark.asyncio
async def test_pinned_project_attachment_reaches_shared_prompt_and_manifest() -> None:
    attachment_id = uuid4()
    request = _request(project_attachment_ids=(attachment_id,))
    item = ProjectAttachmentContextItem(
        id=attachment_id,
        label="收入合同.txt",
        content="项目附件唯一哨兵：截止性测试结论",
        version="3",
        status="included",
    )
    with patch(
        "app.services.ai_chat.context_plan.resolve_review_mode",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.services.ai_chat.context_plan.load_mention_context",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.services.ai_chat.context_plan.AttachmentService.validate_for_run",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.services.ai_chat.context_plan.AiRunResourceService.load_project_attachment_context",
        new=AsyncMock(return_value=[item]),
    ) as loader:
        plan = await build_context_plan(MagicMock(), request=request, context_builder=_Builder())

    assert "项目附件唯一哨兵：截止性测试结论" in plan.system_message
    assert "项目附件：收入合同.txt" in plan.system_message
    rows = [row for key in ("included", "trimmed") for row in plan.manifest.get(key, [])]
    matched = [row for row in rows if row["source_type"] == "project_attachment"]
    assert matched and matched[0]["source_id"] == str(attachment_id)
    assert matched[0]["version"] == "3"
    loader.assert_awaited_once()


@pytest.mark.asyncio
async def test_authorized_audit_relation_graph_reaches_prompt_and_manifest() -> None:
    from app.services.ai_chat.audit_relation_context import AuditRelationItem

    request = _request()
    relation = AuditRelationItem(
        "trial_balance", str(uuid4()), "试算表 1002 银行存款",
        "未审数 100；审定数 90", version="v2",
        jump_route="/trial-balance?year=2025&account=1002",
    )
    with patch(
        "app.services.ai_chat.context_plan.resolve_review_mode", new=AsyncMock(return_value=None),
    ), patch(
        "app.services.ai_chat.context_plan.load_mention_context", new=AsyncMock(return_value=[]),
    ), patch(
        "app.services.ai_chat.context_plan.AttachmentService.validate_for_run", new=AsyncMock(return_value=[]),
    ), patch(
        "app.services.ai_chat.context_plan.AiRunResourceService.load_project_attachment_context",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.services.ai_chat.context_plan.build_audit_relation_context",
        new=AsyncMock(return_value=[relation]),
    ):
        plan = await build_context_plan(MagicMock(), request=request, context_builder=_Builder())

    assert "未审数 100；审定数 90" in plan.system_message
    rows = [row for key in ("included", "trimmed") for row in plan.manifest.get(key, [])]
    row = next(item for item in rows if item["source_type"] == "trial_balance")
    assert row["version"] == "v2"
    assert row["jump_route"].startswith("/trial-balance")


@pytest.mark.asyncio
async def test_relation_graph_failure_is_visible_not_silent_empty() -> None:
    request = _request()
    with patch(
        "app.services.ai_chat.context_plan.resolve_review_mode", new=AsyncMock(return_value=None),
    ), patch(
        "app.services.ai_chat.context_plan.load_mention_context", new=AsyncMock(return_value=[]),
    ), patch(
        "app.services.ai_chat.context_plan.AttachmentService.validate_for_run", new=AsyncMock(return_value=[]),
    ), patch(
        "app.services.ai_chat.context_plan.AiRunResourceService.load_project_attachment_context",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.services.ai_chat.context_plan.build_audit_relation_context",
        new=AsyncMock(side_effect=RuntimeError("db down")),
    ):
        plan = await build_context_plan(MagicMock(), request=request, context_builder=_Builder())

    unavailable = plan.manifest.get("unavailable", [])
    assert any(
        row["source_type"] == "audit_relation_graph"
        and row["reason"] == "load_failed:RuntimeError"
        for row in unavailable
    )
