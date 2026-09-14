"""DisclosureEngine × NoteKnowledgeEnricher 集成测试 — disclosure-note-knowledge-ai-enrichment Task 6.

验证 Task 5 把知识库 RAG 注入 DisclosureEngine 后的**三级填充优先级链与零回归/隔离契约**：

- Property 3：year-1 DB 附注存在 → `retrieve_prior_year_note`（知识库上年回退）不被调用，
  且其结果不覆盖 DB（DB 优先）。
- Property 4：DB 缺失 → 知识库上年回退命中 → 用知识库文字且 citations 非空（来源 knowledge_doc），
  且知识库命中后不再走 LLM 生成层。
- LLM 层：DB 缺失 + 知识库上年未命中 → `_generate_text_with_llm` 经 enricher.generate_note_text
  的 grounded 生成结果作为正文。
- 模板层：DB 缺失 + 知识库未命中 + grounded 生成 text 为空 → 退回通用 chat_completion（降级占位串）
  → 最终落模板 substantive。
- Property 6：`DISCLOSURE_NOTE_RAG_ENABLED=False` 时 `NoteKnowledgeEnricher` 完全不被构造，
  行为与 Wave0 characterization 一致（三级链退化 DB→模板）。
- Property 12：批量遍历中某章节 enricher 抛错 → 仅该章降级到模板，其余章节正常，整体不失败。

统一 mock 边界：patch `app.services.disclosure_engine.NoteKnowledgeEnricher`（`_get_enricher`
构造点）+ `app.services.disclosure_engine.chat_completion`（通用 LLM 路径），并按需 monkeypatch
`settings.DISCLOSURE_NOTE_RAG_ENABLED`。不触真实知识库 / 真实 LLM。

Spec:   .kiro/specs/disclosure-note-knowledge-ai-enrichment/
Reqs:   2.1, 2.2, 2.3, 6.2, 6.4   Property: 3, 4, 6, 12
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import settings
from app.models.report_models import DisclosureNote
from app.services.disclosure_engine import DisclosureEngine
from app.services.note_knowledge_enricher import Citation, GroundedDraft

# chat_completion 服务不可用时的降级占位串（通用 LLM 路径 fallback）
_LLM_UNAVAILABLE = "[LLM 服务暂不可用，请检查 vLLM 是否启动]"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine() -> DisclosureEngine:
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    eng = DisclosureEngine(db)
    eng._wp_cache = {}
    eng._tb_cache = {}
    eng._wp_account_cache = {}
    eng._wp_fine_cache = {}
    eng._prior_notes_cache = {}
    return eng


def _tmpl(
    note_section: str = "五、1 存货",
    account_name: str = "存货",
    text_sections: list[str] | None = None,
) -> dict:
    return {
        "note_section": note_section,
        "section_title": account_name,
        "account_name": account_name,
        "content_type": "table",
        "sort_order": 1,
        "text_sections": text_sections or [],
        "text_template": None,
        "tables": [],
        "llm_prompt_key": None,
    }


def _stub_io(eng: DisclosureEngine) -> None:
    """把 generate_notes 的 DB / 模板 IO stub 掉，只保留三级填充决策逻辑。"""
    eng._build_table_data = AsyncMock(return_value=None)  # type: ignore[assignment]
    res_mock = MagicMock()
    res_mock.scalar_one_or_none = MagicMock(return_value=None)
    res_mock.scalar = MagicMock(return_value=None)
    eng.db.execute = AsyncMock(return_value=res_mock)


def _preload_factory(eng: DisclosureEngine, prior: dict):
    async def _fake_preload(_pid, _yr):
        eng._prior_notes_cache = dict(prior)

    return _fake_preload


def _added_notes(eng: DisclosureEngine) -> list[DisclosureNote]:
    return [
        call.args[0]
        for call in eng.db.add.call_args_list
        if isinstance(call.args[0], DisclosureNote)
    ]


def _note_by_section(eng: DisclosureEngine, note_section: str) -> DisclosureNote:
    for n in _added_notes(eng):
        if n.note_section == note_section:
            return n
    raise AssertionError(f"未 db.add 章节 {note_section} 的 DisclosureNote")


def _cit(document_name: str = "参照文档.pdf", folder_path: str = "/知识库") -> Citation:
    return Citation(
        snippet="参照片段内容摘要",
        score=0.88,
        source_id="doc-" + document_name,
        document_name=document_name,
        folder_path=folder_path,
    )


def _patch_enricher():
    """patch NoteKnowledgeEnricher 构造点，返回 (patch_ctx, 预配置的实例 mock)。"""
    ctx = patch("app.services.disclosure_engine.NoteKnowledgeEnricher")
    return ctx


# ===========================================================================
# Property 3：DB 上年优先，知识库回退不被调用
# ===========================================================================


@pytest.mark.asyncio
async def test_p3_db_prior_wins_knowledge_fallback_not_called(monkeypatch):
    monkeypatch.setattr(settings, "DISCLOSURE_NOTE_RAG_ENABLED", True)
    eng = _make_engine()
    eng._load_templates = AsyncMock(return_value=[_tmpl()])  # type: ignore[assignment]
    db_text = "本年度存货主要由原材料和库存商品构成，期末余额较上年略有增长。"
    eng._preload_data_for_notes = _preload_factory(eng, {"五、1 存货": db_text})  # type: ignore[assignment]
    _stub_io(eng)

    with _patch_enricher() as MockEnr:
        inst = MockEnr.return_value
        inst.retrieve_prior_year_note = AsyncMock(
            return_value=GroundedDraft(text="不应被使用的知识库上年片段内容内容", citations=[_cit()])
        )
        inst.generate_note_text = AsyncMock(
            return_value=GroundedDraft(text="不应被使用的 LLM 文本内容内容内容", citations=[])
        )
        await eng.generate_notes(uuid4(), 2025, "soe")

        # DB 命中 → 知识库上年回退 + LLM 生成层均不被调用
        inst.retrieve_prior_year_note.assert_not_awaited()
        inst.generate_note_text.assert_not_awaited()

    note = _note_by_section(eng, "五、1 存货")
    assert note.text_content == db_text


# ===========================================================================
# Property 4：DB 缺失 → 知识库上年回退命中 → 用知识库文字 + citations 非空
# ===========================================================================


@pytest.mark.asyncio
async def test_p4_db_missing_knowledge_fallback_hits(monkeypatch):
    monkeypatch.setattr(settings, "DISCLOSURE_NOTE_RAG_ENABLED", True)
    eng = _make_engine()
    eng._load_templates = AsyncMock(return_value=[_tmpl()])  # type: ignore[assignment]
    eng._preload_data_for_notes = _preload_factory(eng, {})  # type: ignore[assignment]
    _stub_io(eng)

    kb_text = "根据上年审计报告及附注，存货主要包括原材料、库存商品及周转材料，采用成本与可变现净值孰低计量。"
    kb_cits = [_cit(document_name="2024上年审计报告及附注.pdf", folder_path="/知识库/上年")]

    with _patch_enricher() as MockEnr:
        inst = MockEnr.return_value
        inst.retrieve_prior_year_note = AsyncMock(
            return_value=GroundedDraft(text=kb_text, citations=kb_cits, degraded=False)
        )
        inst.generate_note_text = AsyncMock(
            return_value=GroundedDraft(text="不应被使用的 LLM 文本", citations=[])
        )
        await eng.generate_notes(uuid4(), 2025, "soe")

        inst.retrieve_prior_year_note.assert_awaited_once()
        # 知识库上年命中 → 不再走 LLM 生成层
        inst.generate_note_text.assert_not_awaited()

    note = _note_by_section(eng, "五、1 存货")
    assert note.text_content == kb_text
    # citations 非空且来源为知识库文档（Property 4）
    assert eng._last_citations.get("五、1 存货") == kb_cits
    assert eng._last_citations["五、1 存货"][0].document_name == "2024上年审计报告及附注.pdf"


# ===========================================================================
# LLM 层：DB 缺失 + 知识库上年未命中 → grounded 生成结果作为正文
# ===========================================================================


@pytest.mark.asyncio
async def test_db_and_prior_kb_miss_uses_llm_grounded(monkeypatch):
    monkeypatch.setattr(settings, "DISCLOSURE_NOTE_RAG_ENABLED", True)
    eng = _make_engine()
    eng._load_templates = AsyncMock(return_value=[_tmpl()])  # type: ignore[assignment]
    eng._preload_data_for_notes = _preload_factory(eng, {})  # type: ignore[assignment]
    _stub_io(eng)

    llm_text = "由知识库 grounded 生成的存货附注正文，长度超过二十个字符以通过阈值判定。"
    llm_cits = [_cit(document_name="附注模板.docx")]

    with _patch_enricher() as MockEnr:
        inst = MockEnr.return_value
        inst.retrieve_prior_year_note = AsyncMock(return_value=None)  # 上年知识库未命中
        inst.generate_note_text = AsyncMock(
            return_value=GroundedDraft(text=llm_text, citations=llm_cits, degraded=False)
        )
        await eng.generate_notes(uuid4(), 2025, "soe")

        inst.retrieve_prior_year_note.assert_awaited_once()
        inst.generate_note_text.assert_awaited_once()

    note = _note_by_section(eng, "五、1 存货")
    assert note.text_content == llm_text
    assert eng._last_citations.get("五、1 存货") == llm_cits


# ===========================================================================
# 模板层：DB 缺失 + 知识库未命中 + grounded text 空 → 通用 chat_completion 降级 → 模板
# ===========================================================================


@pytest.mark.asyncio
async def test_all_rag_miss_falls_to_template(monkeypatch):
    monkeypatch.setattr(settings, "DISCLOSURE_NOTE_RAG_ENABLED", True)
    eng = _make_engine()
    tpl_text = "本公司存货采用成本与可变现净值孰低法进行后续计量。"
    eng._load_templates = AsyncMock(  # type: ignore[assignment]
        return_value=[_tmpl(text_sections=[tpl_text])]
    )
    eng._preload_data_for_notes = _preload_factory(eng, {})  # type: ignore[assignment]
    _stub_io(eng)

    with _patch_enricher() as MockEnr, patch(
        "app.services.disclosure_engine.chat_completion",
        new=AsyncMock(return_value=_LLM_UNAVAILABLE),
    ) as mock_cc:
        inst = MockEnr.return_value
        inst.retrieve_prior_year_note = AsyncMock(return_value=None)
        # grounded 生成 text 为空 → _generate_text_with_llm 退回通用 chat_completion
        inst.generate_note_text = AsyncMock(
            return_value=GroundedDraft(text=None, citations=[], degraded=True)
        )
        await eng.generate_notes(uuid4(), 2025, "soe")

        inst.generate_note_text.assert_awaited_once()
        mock_cc.assert_awaited()  # 退回通用 LLM 路径

    note = _note_by_section(eng, "五、1 存货")
    assert note.text_content == tpl_text


# ===========================================================================
# Property 6：关闭开关 → NoteKnowledgeEnricher 完全不被构造（零回归）
# ===========================================================================


@pytest.mark.asyncio
async def test_p6_rag_disabled_enricher_never_constructed(monkeypatch):
    monkeypatch.setattr(settings, "DISCLOSURE_NOTE_RAG_ENABLED", False)
    eng = _make_engine()
    tpl_text = "本公司存货采用成本与可变现净值孰低法进行后续计量。"
    eng._load_templates = AsyncMock(  # type: ignore[assignment]
        return_value=[_tmpl(text_sections=[tpl_text])]
    )
    eng._preload_data_for_notes = _preload_factory(eng, {})  # type: ignore[assignment]
    _stub_io(eng)

    with _patch_enricher() as MockEnr, patch(
        "app.services.disclosure_engine.chat_completion",
        new=AsyncMock(return_value=_LLM_UNAVAILABLE),
    ):
        await eng.generate_notes(uuid4(), 2025, "soe")
        # 关闭开关：enricher 类完全不被构造（Property 6）
        MockEnr.assert_not_called()

    note = _note_by_section(eng, "五、1 存货")
    # 行为与 characterization 一致：DB→(LLM 占位串降级)→模板
    assert note.text_content == tpl_text


# ===========================================================================
# Property 12：批量遍历单章 enricher 抛错 → 仅该章降级，其余正常，整体不失败
# ===========================================================================


@pytest.mark.asyncio
async def test_p12_batch_single_section_degradation_isolated(monkeypatch):
    monkeypatch.setattr(settings, "DISCLOSURE_NOTE_RAG_ENABLED", True)
    eng = _make_engine()
    tpl_a = "A章节模板正文：本公司存货采用成本与可变现净值孰低法计量。"
    templates = [
        _tmpl("五、1 存货", "存货", text_sections=[tpl_a]),
        _tmpl("五、2 应收账款", "应收账款", text_sections=["B章节模板正文，不应被使用。"]),
    ]
    eng._load_templates = AsyncMock(return_value=templates)  # type: ignore[assignment]
    eng._preload_data_for_notes = _preload_factory(eng, {})  # type: ignore[assignment]
    _stub_io(eng)

    b_text = "B章节由知识库 grounded 生成的有效正文，长度超过二十个字符以通过阈值判定。"

    async def _gen_side(project_id, year, note_section, section_title, account_name, **kw):
        if note_section == "五、1 存货":
            raise RuntimeError("boom A（单章 RAG 生成异常）")
        return GroundedDraft(text=b_text, citations=[], degraded=False)

    with _patch_enricher() as MockEnr, patch(
        "app.services.disclosure_engine.chat_completion",
        new=AsyncMock(return_value=_LLM_UNAVAILABLE),
    ):
        inst = MockEnr.return_value
        inst.retrieve_prior_year_note = AsyncMock(return_value=None)
        inst.generate_note_text = AsyncMock(side_effect=_gen_side)

        # 整体不因单章 RAG 异常而失败
        await eng.generate_notes(uuid4(), 2025, "soe")

    note_a = _note_by_section(eng, "五、1 存货")
    note_b = _note_by_section(eng, "五、2 应收账款")
    # A 章节 enricher 抛错 → 通用路径降级占位串 → None → 落 A 模板
    assert note_a.text_content == tpl_a
    # B 章节正常生成
    assert note_b.text_content == b_text
