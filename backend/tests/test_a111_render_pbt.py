"""Property-Based Tests for A11-1 期后事项问询函 render strategy.

Property 2: questions_config always 10 items
Property 3: answer round-trip (10 answers stored → reload returns same)
Property 6: response schema completeness

**Validates: Requirements 5.1, 5.3, 8.1, 8.2, 8.3, 9.1, 9.2**
"""

from __future__ import annotations

from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies._a111_subsequent_events_inquiry import (
    QUESTIONS_CONFIG,
    render,
)

ChecklistRow = namedtuple("ChecklistRow", ["item_id", "conclusion", "remark"])
ProjectRow = namedtuple("ProjectRow", ["client_name", "balance_sheet_date"])


def _make_ctx(checklist_rows=None, project_row=None):
    ctx = MagicMock()
    ctx.wp_id = "wp-test-001"
    ctx.project_id = "proj-test-001"
    db = AsyncMock()
    checklist_result = MagicMock()
    checklist_result.fetchall.return_value = checklist_rows or []
    proj_result = MagicMock()
    proj_result.fetchone.return_value = project_row
    db.execute = AsyncMock(side_effect=[checklist_result, proj_result])
    ctx.db = db
    return ctx


# ─── Property 2: questions_config always 10 items ─────────────────────────────


class TestProperty2QuestionsConfigAlways10:
    """Property 2: questions_config always contains exactly 10 items.

    For any render response, questions_config SHALL have exactly 10 items
    with numbers 1 through 10 in order.

    **Validates: Requirements 5.1, 5.3, 8.1**
    """

    def test_static_config_has_10_items(self):
        """QUESTIONS_CONFIG constant has exactly 10 entries."""
        assert len(QUESTIONS_CONFIG) == 10

    def test_static_config_numbers_sequential(self):
        """QUESTIONS_CONFIG numbers are 1 through 10 in order."""
        for i, q in enumerate(QUESTIONS_CONFIG):
            assert q["number"] == i + 1

    def test_static_config_has_required_keys(self):
        """Each question has all required keys."""
        required_keys = {"number", "title", "text", "has_guidance", "guidance_text"}
        for q in QUESTIONS_CONFIG:
            assert set(q.keys()) == required_keys

    @pytest.mark.asyncio
    @settings(max_examples=5)
    @given(
        client_name=st.text(min_size=0, max_size=50, alphabet=st.characters(blacklist_categories=("Cs",))),
    )
    async def test_render_returns_10_questions_config(self, client_name: str):
        """Render always returns questions_config with 10 items regardless of context."""
        ctx = _make_ctx(
            checklist_rows=[],
            project_row=ProjectRow(client_name, "2026-12-31"),
        )
        result = await render(ctx)
        assert len(result["questions_config"]) == 10
        for i, q in enumerate(result["questions_config"]):
            assert q["number"] == i + 1

    @pytest.mark.asyncio
    async def test_render_questions_config_immutable(self):
        """Two consecutive renders return identical questions_config."""
        ctx1 = _make_ctx(checklist_rows=[], project_row=ProjectRow("A", "2026-12-31"))
        ctx2 = _make_ctx(checklist_rows=[], project_row=ProjectRow("B", "2025-06-30"))
        r1 = await render(ctx1)
        r2 = await render(ctx2)
        assert r1["questions_config"] == r2["questions_config"]


# ─── Property 3: answer round-trip ───────────────────────────────────────────


class TestProperty3AnswerRoundTrip:
    """Property 3: answer data round-trip.

    For any set of 10 answer strings saved to checklist_responses,
    reloading render SHALL return the same 10 answer strings.

    **Validates: Requirements 9.1, 9.2**
    """

    @pytest.mark.asyncio
    @settings(max_examples=5)
    @given(
        answers=st.lists(
            st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_categories=("Cs",))),
            min_size=10,
            max_size=10,
        )
    )
    async def test_10_answers_round_trip(self, answers: list[str]):
        """10 answers stored → render returns same 10 answers."""
        rows = [
            ChecklistRow(f"a111-qa-{i+1}", None, ans)
            for i, ans in enumerate(answers)
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("测试", "2026-12-31"))
        result = await render(ctx)

        assert len(result["qa_list"]) == 10
        for i, qa in enumerate(result["qa_list"]):
            assert qa["answer"] == answers[i]
            assert qa["number"] == i + 1

    @pytest.mark.asyncio
    @settings(max_examples=5)
    @given(
        answer_idx=st.integers(min_value=1, max_value=10),
        answer_text=st.text(min_size=1, max_size=200, alphabet=st.characters(blacklist_categories=("Cs",))),
    )
    async def test_single_answer_round_trip(self, answer_idx: int, answer_text: str):
        """A single answer stored → appears at correct index."""
        rows = [ChecklistRow(f"a111-qa-{answer_idx}", None, answer_text)]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("公司", "2026-12-31"))
        result = await render(ctx)

        assert result["qa_list"][answer_idx - 1]["answer"] == answer_text
        # Other answers remain None
        for i, qa in enumerate(result["qa_list"]):
            if i != answer_idx - 1:
                assert qa["answer"] is None


# ─── Property 6: response schema completeness ────────────────────────────────


class TestProperty6ResponseSchemaCompleteness:
    """Property 6: 渲染策略返回结构完整性.

    For any valid A11-1 render request, the response SHALL contain:
    - meta_data with 4 fields
    - qa_list with 10 items (each has number and answer)
    - evidence (string or null)
    - project_context (client_name, balance_sheet_date)
    - questions_config (10 items)

    **Validates: Requirements 8.1, 8.2, 8.3**
    """

    @pytest.mark.asyncio
    @settings(max_examples=5)
    @given(
        client_name=st.text(min_size=0, max_size=50, alphabet=st.characters(blacklist_categories=("Cs",))),
        date_str=st.one_of(st.none(), st.from_regex(r"\d{4}-\d{2}-\d{2}", fullmatch=True)),
    )
    async def test_top_level_keys(self, client_name: str, date_str: str | None):
        """Response has all 5 top-level keys."""
        ctx = _make_ctx(
            checklist_rows=[],
            project_row=ProjectRow(client_name, date_str),
        )
        result = await render(ctx)
        assert set(result.keys()) == {"meta_data", "qa_list", "evidence", "project_context", "questions_config"}

    @pytest.mark.asyncio
    async def test_meta_data_has_4_fields(self):
        """meta_data has inquiry_date, interviewee, location, team_signature."""
        ctx = _make_ctx(checklist_rows=[], project_row=ProjectRow("X", "2026-12-31"))
        result = await render(ctx)
        assert set(result["meta_data"].keys()) == {"inquiry_date", "interviewee", "location", "team_signature"}

    @pytest.mark.asyncio
    async def test_qa_list_has_10_items_with_number_and_answer(self):
        """qa_list has 10 items, each with number and answer."""
        ctx = _make_ctx(checklist_rows=[], project_row=ProjectRow("X", "2026-12-31"))
        result = await render(ctx)
        assert len(result["qa_list"]) == 10
        for i, qa in enumerate(result["qa_list"]):
            assert qa["number"] == i + 1
            assert "answer" in qa

    @pytest.mark.asyncio
    async def test_project_context_has_2_fields(self):
        """project_context has client_name and balance_sheet_date."""
        ctx = _make_ctx(checklist_rows=[], project_row=ProjectRow("X", "2026-12-31"))
        result = await render(ctx)
        assert set(result["project_context"].keys()) == {"client_name", "balance_sheet_date"}

    @pytest.mark.asyncio
    async def test_questions_config_has_10_with_required_keys(self):
        """questions_config has 10 items with all required keys."""
        ctx = _make_ctx(checklist_rows=[], project_row=ProjectRow("X", "2026-12-31"))
        result = await render(ctx)
        assert len(result["questions_config"]) == 10
        required = {"number", "title", "text", "has_guidance", "guidance_text"}
        for q in result["questions_config"]:
            assert set(q.keys()) == required
