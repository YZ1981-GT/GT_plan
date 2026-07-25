"""Task 7 — 附注 ai-fill / batch-ai-fill 端点测试.

Spec: .kiro/specs/disclosure-note-knowledge-ai-enrichment/ Task 7
覆盖：
- P11 ai-fill 不写库（调用后 DisclosureNote.text_content 未变，无 update/commit 到 text_content）
- degraded 提示（enricher 返回 degraded=True → resp.degraded True）
- 权限跳过（doc_filter 含无效文档 → skipped_docs 含之，不 500）
- P13 reference_only（body reference_only=True → enricher 收到 reference_only=True）
- batch（batch-ai-fill 返回逐章 results 结构正确）

风格参照 test_disclosure_notes_hardening.py：直调 router 函数 + AsyncMock db + patch enricher。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.models.core import User, UserRole
from app.models.report_models import NoteStatus
from app.routers import disclosure_notes as notes_router
from app.services.note_knowledge_enricher import Citation, GroundedDraft

PROJECT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _run(coro):
    return asyncio.run(coro)


def _user() -> User:
    return User(
        id=USER_ID,
        username="ai-fill-user",
        email="aifill@test.local",
        hashed_password="x",
        role=UserRole.admin,
        is_active=True,
        is_deleted=False,
    )


class _Row(tuple):
    """模拟 db.execute(...).one_or_none() 返回的 (section_title, account_name) 行。"""


class _OneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def one_or_none(self):
        return self._value


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


def _citation(**kw) -> Citation:
    base = dict(
        snippet="上年应收账款按账龄计提坏账准备……",
        score=0.87,
        source_id="doc-1",
        document_name="上年审计报告及附注.pdf",
        folder_path="/知识库/2024",
        is_stale=False,
    )
    base.update(kw)
    return Citation(**base)


# ===========================================================================
# ai-fill 端点
# ===========================================================================


class TestAiFillEndpoint:
    """POST /{project_id}/{year}/{note_section}/ai-fill 现状与属性。"""

    def _db_with_section(self, *, doc_active=None):
        """db.execute 依次返回：section 行 → (可选) doc_filter 活跃文档。"""
        db = MagicMock()
        results = [_OneOrNoneResult(("应收账款", "应收账款"))]
        if doc_active is not None:
            results.append(_ScalarsResult(doc_active))
        db.execute = AsyncMock(side_effect=results)
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        return db

    def test_p11_ai_fill_does_not_write_db(self):
        """P11：ai-fill 只返回预览，绝不写库（无 commit/flush，enricher 不落库）。"""
        db = self._db_with_section()
        draft = GroundedDraft(text="生成的附注正文", citations=[_citation()], degraded=False)

        with patch(
            "app.services.note_knowledge_enricher.NoteKnowledgeEnricher.generate_note_text",
            new=AsyncMock(return_value=draft),
        ):
            result = _run(
                notes_router.ai_fill_note_section(
                    PROJECT_ID, 2025, "五、3",
                    notes_router.NoteAiFillRequest(),
                    db, _user(),
                )
            )

        assert result["text"] == "生成的附注正文"
        assert result["degraded"] is False
        assert result["skipped_docs"] == []
        assert len(result["citations"]) == 1
        assert result["citations"][0]["document_name"] == "上年审计报告及附注.pdf"
        assert result["citations"][0]["is_stale"] is False
        # 不落库：无写操作
        db.commit.assert_not_awaited()
        db.flush.assert_not_awaited()

    def test_degraded_flag_passthrough(self):
        """enricher 返回 degraded=True（无 RAG 依据/降级）→ resp.degraded True。"""
        db = self._db_with_section()
        draft = GroundedDraft(text=None, citations=[], degraded=True)

        with patch(
            "app.services.note_knowledge_enricher.NoteKnowledgeEnricher.generate_note_text",
            new=AsyncMock(return_value=draft),
        ):
            result = _run(
                notes_router.ai_fill_note_section(
                    PROJECT_ID, 2025, "五、3",
                    notes_router.NoteAiFillRequest(),
                    db, _user(),
                )
            )

        assert result["degraded"] is True
        assert result["text"] is None
        assert result["citations"] == []

    def test_skipped_docs_for_invalid_doc_filter(self):
        """权限跳过：doc_filter 含不存在/已删文档 → skipped_docs 含之，不 500。"""
        valid = uuid4()
        invalid = uuid4()
        # 活跃文档只返回 valid（invalid 已删/不存在）
        db = self._db_with_section(doc_active=[valid])
        draft = GroundedDraft(text="正文", citations=[], degraded=False)

        with patch(
            "app.services.note_knowledge_enricher.NoteKnowledgeEnricher.generate_note_text",
            new=AsyncMock(return_value=draft),
        ):
            result = _run(
                notes_router.ai_fill_note_section(
                    PROJECT_ID, 2025, "五、3",
                    notes_router.NoteAiFillRequest(doc_filter=[valid, invalid]),
                    db, _user(),
                )
            )

        assert str(invalid) in result["skipped_docs"]
        assert str(valid) not in result["skipped_docs"]

    def test_p13_reference_only_passed_to_enricher(self):
        """P13：body reference_only=True → enricher 收到 reference_only=True。"""
        db = self._db_with_section()
        draft = GroundedDraft(text=None, citations=[_citation()], degraded=True)
        gen = AsyncMock(return_value=draft)

        with patch(
            "app.services.note_knowledge_enricher.NoteKnowledgeEnricher.generate_note_text",
            new=gen,
        ):
            result = _run(
                notes_router.ai_fill_note_section(
                    PROJECT_ID, 2025, "五、3",
                    notes_router.NoteAiFillRequest(reference_only=True),
                    db, _user(),
                )
            )

        gen.assert_awaited_once()
        assert gen.await_args.kwargs["reference_only"] is True
        # reference_only 只回片段：text=None + citations 非空
        assert result["text"] is None
        assert len(result["citations"]) == 1

    def test_section_title_fallback_to_note_section(self):
        """章节记录缺失时 section_title 用 note_section 兜底，仍能生成。"""
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[_OneOrNoneResult(None)])
        db.commit = AsyncMock()
        draft = GroundedDraft(text="兜底生成", citations=[], degraded=False)
        gen = AsyncMock(return_value=draft)

        with patch(
            "app.services.note_knowledge_enricher.NoteKnowledgeEnricher.generate_note_text",
            new=gen,
        ):
            result = _run(
                notes_router.ai_fill_note_section(
                    PROJECT_ID, 2025, "五、99",
                    notes_router.NoteAiFillRequest(),
                    db, _user(),
                )
            )

        # section_title 兜底为 note_section
        assert gen.await_args.args[3] == "五、99"
        assert result["text"] == "兜底生成"


# ===========================================================================
# batch-ai-fill 端点
# ===========================================================================


class _FakeNote:
    def __init__(self, note_section, section_title, account_name, text_content, status, is_local_override=False):
        self.note_section = note_section
        self.section_title = section_title
        self.account_name = account_name
        self.text_content = text_content
        self.status = status
        self.is_local_override = is_local_override


class TestBatchAiFillEndpoint:
    """POST /{project_id}/{year}/batch-ai-fill 逐章结果结构。"""

    def test_batch_returns_per_section_results(self):
        """batch-ai-fill 返回逐章 results + generated/degraded/skipped 计数；不落库。"""
        notes = [
            _FakeNote("五、1", "货币资金", "货币资金", None, NoteStatus.draft),
            _FakeNote("五、2", "应收账款", "应收账款", "", NoteStatus.draft),
            _FakeNote("五、3", "存货", "存货", None, NoteStatus.draft),
        ]
        db = MagicMock()
        db.execute = AsyncMock(return_value=_ScalarsResult(notes))
        db.commit = AsyncMock()
        db.flush = AsyncMock()

        batch_result = [
            {"note_section": "五、1", "status": "generated", "text": "正文1", "citations": [_citation()]},
            {"note_section": "五、2", "status": "degraded", "text": None, "citations": []},
            {"note_section": "五、3", "status": "skipped", "text": None, "citations": []},
        ]

        with patch(
            "app.services.note_knowledge_enricher.NoteKnowledgeEnricher.batch_prefill",
            new=AsyncMock(return_value=batch_result),
        ):
            result = _run(
                notes_router.batch_ai_fill_notes(
                    PROJECT_ID, 2025,
                    notes_router.NoteBatchAiFillRequest(),
                    db, _user(),
                )
            )

        assert len(result["results"]) == 3
        assert result["generated"] == 1
        assert result["degraded"] == 1
        assert result["skipped"] == 1
        # 逐章结构正确 + citations 序列化为 dict
        gen_row = next(r for r in result["results"] if r["note_section"] == "五、1")
        assert gen_row["status"] == "generated"
        assert gen_row["text"] == "正文1"
        assert gen_row["citations"][0]["document_name"] == "上年审计报告及附注.pdf"
        # 不落库
        db.commit.assert_not_awaited()

    def test_batch_sections_built_from_empty_or_draft_notes(self):
        """构造 sections 时携带 note_section/section_title/account_name，供 enricher 使用。"""
        notes = [_FakeNote("五、1", "货币资金", "货币资金", None, NoteStatus.draft)]
        db = MagicMock()
        db.execute = AsyncMock(return_value=_ScalarsResult(notes))
        db.commit = AsyncMock()
        bp = AsyncMock(return_value=[])

        with patch(
            "app.services.note_knowledge_enricher.NoteKnowledgeEnricher.batch_prefill",
            new=bp,
        ):
            _run(
                notes_router.batch_ai_fill_notes(
                    PROJECT_ID, 2025,
                    notes_router.NoteBatchAiFillRequest(),
                    db, _user(),
                )
            )

        bp.assert_awaited_once()
        sections = bp.await_args.args[2]
        assert sections[0]["note_section"] == "五、1"
        assert sections[0]["section_title"] == "货币资金"
        assert sections[0]["account_name"] == "货币资金"
        assert sections[0]["is_draft"] is True

    def test_batch_empty_when_no_matching_sections(self):
        """无匹配章节 → results 空、计数全 0，不 500。"""
        db = MagicMock()
        db.execute = AsyncMock(return_value=_ScalarsResult([]))
        db.commit = AsyncMock()

        with patch(
            "app.services.note_knowledge_enricher.NoteKnowledgeEnricher.batch_prefill",
            new=AsyncMock(return_value=[]),
        ):
            result = _run(
                notes_router.batch_ai_fill_notes(
                    PROJECT_ID, 2025,
                    notes_router.NoteBatchAiFillRequest(),
                    db, _user(),
                )
            )

        assert result["results"] == []
        assert result["generated"] == 0
        assert result["degraded"] == 0
        assert result["skipped"] == 0


# ===========================================================================
# 采纳落库约束（Req5.2）：采纳 AI 附注正文仅写 text_content，不碰 guidance_text
# ===========================================================================


class _FakeAdoptNote:
    """模拟 update_note 反查到的既有附注章节（带原有 guidance_text）。"""

    def __init__(self):
        self.id = uuid4()
        self.text_content = "旧正文"
        self.guidance_text = "既有编制提示（不应被采纳流触碰）"
        self.table_data = {"headers": ["项目"], "rows": []}
        self.status = NoteStatus.draft
        self.is_deleted = False


class _NoteScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class TestAdoptionWritesOnlyTextContent:
    """采纳 AI 正文经既有 update_note 落库，仅写 text_content，不碰 guidance_text（Req5.2/Property 11 落库侧）。

    采纳流：ai-fill 预览（不落库）→ /api/ai-chat/adopt（写 ai_content_log pending）→ 审计师确认后
    经 DisclosureEngine.update_note 仅传 text_content 落库。此测试守卫「仅传 text_content 时
    guidance_text 保持不变」——现有 update_note 以 `if X is not None` 分支满足该约束，不新增端点。
    """

    def test_update_note_text_only_leaves_guidance_untouched(self):
        from app.services.disclosure_engine import DisclosureEngine

        note = _FakeAdoptNote()
        db = MagicMock()
        db.execute = AsyncMock(return_value=_NoteScalarResult(note))
        db.flush = AsyncMock()

        engine = DisclosureEngine(db)
        updated = _run(
            engine.update_note(
                note.id,
                text_content="采纳的 AI 附注正文",
                # guidance_text 不传（采纳流只回写正文）
            )
        )

        assert updated is note
        # 仅写 text_content
        assert note.text_content == "采纳的 AI 附注正文"
        # guidance_text 不被采纳流触碰（Req5.2）
        assert note.guidance_text == "既有编制提示（不应被采纳流触碰）"
        db.flush.assert_awaited()
