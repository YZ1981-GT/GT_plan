"""附注续写/改写的 draft overlay 与已保存正文对账（spec llm-linkage-audit-practice-closure 任务 13）。

改写：选中原文必须在已保存正文里唯一出现，否则在调用模型之前拒绝（overlay 版本冲突）。
续写：编辑器内容与已保存正文不一致时照常生成，但 overlay 元数据记 ``matches_saved=False``
并提示用户“草稿会追加到已保存正文之后”；真正写入时仍由 DraftArtifact 的 CAS 兜底。
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.routers import note_ai
from app.services.llm_client import LLMInvocationResult, LLMInvocationStatus


def _invocation(text: str, task_code: str):
    return SimpleNamespace(
        result=LLMInvocationResult(
            status=LLMInvocationStatus.success, text=text, model_name="fake", deployment="local"
        ),
        spec=SimpleNamespace(task_code=task_code, prompt_id=task_code),
        prompt_version="1.0.0",
        prompt_hash="a" * 64,
    )


@pytest.mark.parametrize(
    ("saved", "fragment", "code"),
    [
        (None, "任意", "note_not_found"),
        ("已保存正文。", "未保存的新句子", "overlay_baseline_conflict"),
        ("重复句。重复句。", "重复句", "overlay_baseline_conflict"),
        ("已保存正文。", "", "overlay_baseline_conflict"),
        ("已保存正文。", "保存正文", None),
    ],
)
def test_overlay_conflict_rules(saved, fragment, code) -> None:
    conflict = note_ai._overlay_conflict(saved, fragment)
    assert (conflict or {}).get("error_code") == code


def _common_patches(saved: str):
    return (
        patch.object(note_ai, "require_project_audit_year", new=AsyncMock(return_value=2025)),
        patch.object(note_ai, "_saved_note_text", new=AsyncMock(return_value=saved)),
        patch.object(note_ai, "_load_selected_knowledge", new=AsyncMock(return_value=[])),
        patch("app.services.reference_doc_service.ReferenceDocService.load_context", new=AsyncMock(return_value=[])),
    )


@pytest.mark.asyncio
async def test_rewrite_of_unsaved_selection_is_rejected_before_model() -> None:
    p1, p2, p3, p4 = _common_patches("已保存正文。")
    with p1, p2, p3, p4, patch.object(note_ai, "invoke_ai_task", new=AsyncMock()) as invoke:
        result = await note_ai.ai_rewrite(
            uuid4(),
            note_ai.RewriteRequest(text="未保存的新句子", section_number="五、1"),
            MagicMock(),
            SimpleNamespace(id=uuid4(), role="auditor"),
        )
    assert result["error_code"] == "overlay_baseline_conflict"
    assert result["rewritten"] is None
    invoke.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(("editor_text", "matches"), [("已保存正文。", True), ("已保存正文。未保存的一句。", False)])
async def test_continue_records_whether_overlay_matches_saved(editor_text, matches) -> None:
    p1, p2, p3, p4 = _common_patches("已保存正文。")
    persist = AsyncMock(return_value={"message_id": "m", "artifact_id": "a", "generation_id": "g"})
    with p1, p2, p3, p4, patch.object(
        note_ai, "invoke_ai_task", new=AsyncMock(return_value=_invocation("续写段落", "note.continue"))
    ), patch.object(note_ai, "_persist_note_draft", new=persist):
        result = await note_ai.ai_complete(
            uuid4(),
            note_ai.ContinueWriteRequest(text=editor_text, section_number="五、1"),
            MagicMock(),
            SimpleNamespace(id=uuid4(), role="auditor"),
        )
    assert persist.await_args.kwargs["overlay_matches_saved"] is matches
    assert result["artifact_id"] == "a"
    assert ("warning" in result) is (not matches)


@pytest.mark.asyncio
async def test_continue_on_missing_note_never_calls_model() -> None:
    p1, p2, p3, p4 = _common_patches("")
    with p1, patch.object(note_ai, "_saved_note_text", new=AsyncMock(return_value=None)), p3, p4, patch.object(
        note_ai, "invoke_ai_task", new=AsyncMock()
    ) as invoke:
        result = await note_ai.ai_complete(
            uuid4(),
            note_ai.ContinueWriteRequest(text="正文", section_number="五、9"),
            MagicMock(),
            SimpleNamespace(id=uuid4(), role="auditor"),
        )
    assert result["error_code"] == "note_not_found"
    invoke.assert_not_awaited()
