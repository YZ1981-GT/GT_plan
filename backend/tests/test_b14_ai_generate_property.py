"""Property-Based Tests for B1-4 AI Generate prompt construction.

Feature: b1-4-due-diligence-report, Property 8: LLM prompt includes required context sections

Generate random chapter_id / project_context / knowledge_docs (0-3) / cross-chapter summaries,
verify the constructed LLM prompt contains: the chapter title, all provided knowledge base
documents, project basic info (client_name, industry, audit_period), and (if mode=polish)
the current content.

**Validates: Requirements 6.4**
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.routers.b14_ai_generate import (
    _build_user_prompt,
    _CHAPTER_TITLE_MAP,
    _SYSTEM_PROMPT_TEMPLATE,
)


# ─── Hypothesis Strategies ────────────────────────────────────────────────────

_chapter_id_st = st.sampled_from(list(_CHAPTER_TITLE_MAP.keys()))

_mode_st = st.sampled_from(["generate", "polish"])

_text_st = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(categories=("L", "N")),
)

_optional_text_st = st.one_of(st.just(""), _text_st)

_kb_doc_st = st.text(
    min_size=5,
    max_size=100,
    alphabet=st.characters(categories=("L", "N", "P")),
)

_kb_docs_st = st.lists(_kb_doc_st, min_size=0, max_size=3)

_cross_chapter_st = st.one_of(
    st.just(""),
    st.text(min_size=5, max_size=200, alphabet=st.characters(categories=("L", "N", "P"))),
)

_project_context_st = st.fixed_dictionaries({
    "client_name": _text_st,
    "industry": _text_st,
    "audit_period": _text_st,
    "firm_name": _text_st,
})


# ─── Property 8: LLM prompt includes required context sections ───────────────


class TestProperty8LLMPromptContext:
    """Feature: b1-4-due-diligence-report, Property 8: LLM prompt includes required context sections

    For any chapter id, project context (client_name, industry, audit_period),
    knowledge base documents (0-3 docs), and cross-chapter summaries, the
    constructed LLM prompt should contain: the chapter title, all provided
    knowledge base documents, project basic info, and (if mode=polish)
    the current content.

    **Validates: Requirements 6.4**
    """

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        chapter_id=_chapter_id_st,
        mode=_mode_st,
        user_hint=_optional_text_st,
        current_content=_text_st,
        cross_chapter_ctx=_cross_chapter_st,
        kb_docs=_kb_docs_st,
    )
    def test_prompt_contains_chapter_title(
        self, chapter_id, mode, user_hint, current_content, cross_chapter_ctx, kb_docs
    ):
        """User prompt always contains the chapter title."""
        chapter_title = _CHAPTER_TITLE_MAP[chapter_id]

        prompt = _build_user_prompt(
            chapter_title=chapter_title,
            mode=mode,
            user_hint=user_hint,
            current_content=current_content,
            cross_chapter_ctx=cross_chapter_ctx,
            kb_docs=kb_docs,
        )

        assert chapter_title in prompt, (
            f"Chapter title '{chapter_title}' not found in prompt"
        )

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        chapter_id=_chapter_id_st,
        kb_docs=st.lists(_kb_doc_st, min_size=1, max_size=3),
    )
    def test_prompt_contains_all_knowledge_base_docs(self, chapter_id, kb_docs):
        """All provided knowledge base documents appear in the prompt."""
        chapter_title = _CHAPTER_TITLE_MAP[chapter_id]

        prompt = _build_user_prompt(
            chapter_title=chapter_title,
            mode="generate",
            user_hint="",
            current_content="",
            cross_chapter_ctx="",
            kb_docs=kb_docs,
        )

        for doc in kb_docs:
            assert doc in prompt, (
                f"Knowledge base doc not found in prompt: '{doc[:30]}...'"
            )

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        chapter_id=_chapter_id_st,
        project_context=_project_context_st,
    )
    def test_system_prompt_contains_project_info(self, chapter_id, project_context):
        """System prompt contains project basic info (client_name, industry, audit_period)."""
        chapter_title = _CHAPTER_TITLE_MAP[chapter_id]

        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
            chapter_title=chapter_title,
            client_name=project_context["client_name"],
            industry=project_context["industry"],
            audit_period=project_context["audit_period"],
            firm_name=project_context["firm_name"],
        )

        assert project_context["client_name"] in system_prompt, (
            f"client_name not in system prompt"
        )
        assert project_context["industry"] in system_prompt, (
            f"industry not in system prompt"
        )
        assert project_context["audit_period"] in system_prompt, (
            f"audit_period not in system prompt"
        )

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        chapter_id=_chapter_id_st,
        current_content=_text_st,
    )
    def test_polish_mode_includes_current_content(self, chapter_id, current_content):
        """In polish mode, the prompt includes current_content."""
        chapter_title = _CHAPTER_TITLE_MAP[chapter_id]

        prompt = _build_user_prompt(
            chapter_title=chapter_title,
            mode="polish",
            user_hint="",
            current_content=current_content,
            cross_chapter_ctx="",
            kb_docs=[],
        )

        assert current_content in prompt, (
            f"current_content not found in polish-mode prompt"
        )

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        chapter_id=_chapter_id_st,
        current_content=_text_st,
    )
    def test_generate_mode_excludes_current_content_section(self, chapter_id, current_content):
        """In generate mode, the prompt does NOT include the current content section header."""
        chapter_title = _CHAPTER_TITLE_MAP[chapter_id]

        prompt = _build_user_prompt(
            chapter_title=chapter_title,
            mode="generate",
            user_hint="",
            current_content=current_content,
            cross_chapter_ctx="",
            kb_docs=[],
        )

        # Generate mode should not have polish-specific section
        assert "当前章节已有内容" not in prompt, (
            "Generate mode should not include current content section"
        )
