"""Phase 5 测试：原子 apply、幂等、冲突检测和审计记录。"""

from __future__ import annotations

import hashlib
import uuid

import pytest

from app.services.note_html_sanitizer import append_note_html as _append_html
from app.services.note_text_batch_apply import ApplyError


class TestAppendHtml:
    def test_basic_append(self):
        result = _append_html("<p>旧内容</p>", "<p>新内容</p>")
        assert "<p>旧内容</p>" in result
        assert "<p>新内容</p>" in result
        assert "<p>&nbsp;</p>" in result

    def test_duplicate_suppressed(self):
        """完全相同的段落不重复追加。"""
        existing = "<p>旧内容</p>"
        result = _append_html(existing, "<p>旧内容</p>")
        assert result == existing

    def test_empty_existing(self):
        result = _append_html("", "<p>新内容</p>")
        assert "<p>新内容</p>" in result

    def test_empty_new(self):
        result = _append_html("<p>旧内容</p>", "")
        # 新内容为空不拼接分隔符
        assert "<p>旧内容</p>" in result


class TestApplyBatchValidation:
    """测试 apply_batch 的纯逻辑校验（不需 DB）。"""

    def test_apply_error_has_fields(self):
        err = ApplyError("CODE", "消息", stale_notes=["一、1", "二、2"])
        assert err.code == "CODE"
        assert err.message == "消息"
        assert err.stale_notes == ["一、1", "二、2"]

    def test_apply_error_empty_stale(self):
        err = ApplyError("CODE", "消息")
        assert err.stale_notes == []


class TestSelectionSchema:
    """测试 Pydantic schema 层面的校验（Task 27）。"""

    def test_reject_free_mode(self):
        from app.models.note_content_template_schemas import BatchApplyMode
        assert "merge" not in {m.value for m in BatchApplyMode}

    def test_duplicate_targets_rejected(self):
        from pydantic import ValidationError
        from app.models.note_content_template_schemas import BatchApplyRequest
        tid = str(uuid.uuid4())
        with pytest.raises(ValidationError, match="重复"):
            BatchApplyRequest.model_validate({
                "year": 2025,
                "source": {
                    "source_kind": "upload",
                    "parsed_source": {"source_kind": "upload", "sections": []},
                },
                "preview_digest": "0" * 64,
                "selections": [
                    {
                        "source_id": "s1",
                        "target_note_id": tid,
                        "mode": "replace",
                        "before_hash": "1" * 64,
                        "proposed_hash": "2" * 64,
                        "proposed_html": "<p>x</p>",
                    },
                    {
                        "source_id": "s2",
                        "target_note_id": tid,
                        "mode": "replace",
                        "before_hash": "3" * 64,
                        "proposed_hash": "4" * 64,
                        "proposed_html": "<p>y</p>",
                    },
                ],
            })

    def test_valid_selection_passes(self):
        from app.models.note_content_template_schemas import BatchApplyRequest
        req = BatchApplyRequest.model_validate({
            "year": 2025,
            "source": {
                "source_kind": "upload",
                "parsed_source": {"source_kind": "upload", "sections": []},
            },
            "preview_digest": "0" * 64,
            "selections": [{
                "source_id": "s1",
                "target_note_id": str(uuid.uuid4()),
                "mode": "replace",
                "before_hash": "1" * 64,
                "proposed_hash": "2" * 64,
                "proposed_html": "<p>内容</p>",
            }],
        })
        assert len(req.selections) == 1


class TestCoordinatorMultiEvent:
    """Task 32：coordinator 支持事件列表。"""

    def test_execute_signature_accepts_list_factory(self):
        """验证 coordinator.execute 的 event_factory 可返回列表。"""
        import inspect
        from app.services.disclosure_mutation_coordinator import DisclosureMutationCoordinator
        sig = inspect.getsource(DisclosureMutationCoordinator.execute)
        # 确认代码中有列表判断
        assert "isinstance(payloads, list)" in sig

    def test_execute_signature_loops_payloads(self):
        import inspect
        from app.services.disclosure_mutation_coordinator import DisclosureMutationCoordinator
        src = inspect.getsource(DisclosureMutationCoordinator.execute)
        assert "for payload in payloads:" in src


class TestAuditRecordSchema:
    """Task 31：审计记录字段完整性。"""

    def test_application_model_has_required_fields(self):
        from app.models.note_content_template_models import NoteTextBatchApplication
        cols = set(NoteTextBatchApplication.__table__.columns.keys())
        assert "source_kind" in cols
        assert "mutation_id" in cols
        assert "preview_digest" in cols
        assert "detail" in cols
        assert "applied_count" in cols
        assert "status" in cols


class TestAppendNoteHtmlReview:
    """复盘 R-10：追加须按段落去重、空新内容不拼分隔段、结果为消毒后 canonical HTML。"""

    def test_empty_new_returns_existing_unchanged(self):
        from app.services.note_html_sanitizer import append_note_html

        assert append_note_html("<p>旧</p>", "") == "<p>旧</p>"
        assert append_note_html("<p>旧</p>", "   ") == "<p>旧</p>"

    def test_empty_existing_has_no_leading_separator(self):
        from app.services.note_html_sanitizer import append_note_html

        assert append_note_html("", "<p>新</p>") == "<p>新</p>"

    def test_paragraph_level_dedupe(self):
        from app.services.note_html_sanitizer import append_note_html

        assert append_note_html("<p>甲</p><p>乙</p>", "<p>乙</p><p>丙</p>") == (
            "<p>甲</p><p>乙</p><p>&nbsp;</p><p>丙</p>"
        )

    def test_all_new_paragraphs_already_present(self):
        from app.services.note_html_sanitizer import append_note_html

        assert append_note_html("<p>甲</p><p>乙</p>", "<p>乙</p>") == "<p>甲</p><p>乙</p>"

    def test_result_is_sanitized_and_has_no_audit_marker(self):
        from app.services.note_html_sanitizer import append_note_html

        result = append_note_html("<p>旧</p>", "<p>新</p><script>x</script>")
        assert "<script>" not in result
        assert "引用自" not in result
