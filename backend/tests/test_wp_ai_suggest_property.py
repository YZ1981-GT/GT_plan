"""PBT P-5：LLM 建议安全性

Property P-5 from requirements:
- 当 WP_AI_SERVICE_ENABLED=false 时，端点返回 403
- 返回的建议文本长度 ≤ 2000 字符
- ai_assisted 标记正确写入 audit_trail

**Validates: Requirements US-5 P-5**

Testing framework: hypothesis (Python PBT)
"""

from __future__ import annotations

import uuid
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st


# ─── Strategies ──────────────────────────────────────────────────────────────

wp_id_strategy = st.uuids()

sheet_name_strategy = st.from_regex(r"[A-Z][0-9a-z_\-]{1,30}", fullmatch=True)

field_name_strategy = st.from_regex(r"[a-z][a-z0-9_]{2,30}", fullmatch=True)

# Generate existing content of varying lengths (including very long)
existing_content_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=0,
    max_size=5000,
)

# Generate suggestion text that may exceed 2000 chars
suggestion_text_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=0,
    max_size=4000,
)

confidence_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)


# ─── Fake service / DB helpers ───────────────────────────────────────────────


class FakeWorkingPaper:
    """Simulates a WorkingPaper ORM record."""

    def __init__(self, wp_id: uuid.UUID, project_id: uuid.UUID):
        self.id = wp_id
        self.project_id = project_id


class FakeUser:
    """Simulates a user object."""

    def __init__(self, user_id: uuid.UUID | None = None):
        self.id = user_id or uuid.uuid4()


class FakeDB:
    """Simulates async DB session."""

    def __init__(self, wp: FakeWorkingPaper | None = None):
        self._wp = wp

    async def execute(self, stmt):
        class FakeResult:
            def __init__(self, wp):
                self._wp = wp

            def scalar_one_or_none(self):
                return self._wp

        return FakeResult(self._wp)

    async def commit(self):
        pass

    async def rollback(self):
        pass


# ─── Property Tests ──────────────────────────────────────────────────────────


class TestP5LlmSuggestSafety:
    """PBT P-5: LLM 建议安全性"""

    @given(
        wp_id=wp_id_strategy,
        sheet_name=sheet_name_strategy,
        field_name=field_name_strategy,
        existing_content=st.text(min_size=0, max_size=100),
    )
    @settings(max_examples=20)
    def test_flag_disabled_returns_403(
        self, wp_id, sheet_name, field_name, existing_content
    ):
        """Property: WP_AI_SERVICE_ENABLED=false → endpoint returns 403"""
        import asyncio
        from app.core.config import settings as app_settings

        async def _run():
            from app.routers.wp_ai import suggest_fill, SuggestRequest

            # Patch settings to disable AI
            with patch.object(app_settings, "WP_AI_SERVICE_ENABLED", False):
                from fastapi import HTTPException

                body = SuggestRequest(
                    sheet_name=sheet_name,
                    field_name=field_name,
                    existing_content=existing_content,
                )
                with pytest.raises(HTTPException) as exc_info:
                    await suggest_fill(
                        wp_id=wp_id,
                        body=body,
                        db=FakeDB(),
                        user=FakeUser(),
                    )
                assert exc_info.value.status_code == 403
                assert "AI service disabled" in str(exc_info.value.detail)

        asyncio.run(_run())

    @given(
        wp_id=wp_id_strategy,
        project_id=st.uuids(),
        sheet_name=sheet_name_strategy,
        field_name=field_name_strategy,
        suggestion_text=suggestion_text_strategy,
        confidence=confidence_strategy,
    )
    @settings(max_examples=30)
    def test_suggestion_text_length_capped_at_2000(
        self, wp_id, project_id, sheet_name, field_name, suggestion_text, confidence
    ):
        """Property: Suggestion text length ≤ 2000 characters regardless of LLM output"""
        import asyncio
        from app.core.config import settings as app_settings

        async def _run():
            from app.routers.wp_ai import suggest_fill, SuggestRequest

            fake_wp = FakeWorkingPaper(wp_id, project_id)
            fake_db = FakeDB(fake_wp)

            # Mock the AI service to return arbitrary-length text
            mock_suggest = AsyncMock(return_value={
                "text": suggestion_text,
                "confidence": confidence,
            })

            with patch.object(app_settings, "WP_AI_SERVICE_ENABLED", True), \
                 patch("app.routers.wp_ai.WpAIService") as MockSvc, \
                 patch("app.services.audit_logger_enhanced.audit_logger.log_action", new_callable=AsyncMock):

                mock_instance = MagicMock()
                mock_instance.suggest_field_content = mock_suggest
                MockSvc.return_value = mock_instance

                body = SuggestRequest(
                    sheet_name=sheet_name,
                    field_name=field_name,
                    existing_content="",
                )
                result = await suggest_fill(
                    wp_id=wp_id,
                    body=body,
                    db=fake_db,
                    user=FakeUser(),
                )

                # Property: response text ≤ 2000 chars
                assert len(result.suggestion) <= 2000

        asyncio.run(_run())

    @given(
        wp_id=wp_id_strategy,
        project_id=st.uuids(),
        sheet_name=sheet_name_strategy,
        field_name=field_name_strategy,
    )
    @settings(max_examples=15)
    def test_audit_trail_written_on_suggest(
        self, wp_id, project_id, sheet_name, field_name
    ):
        """Property: ai_suggest_requested action written to audit_trail on successful suggest"""
        import asyncio
        from app.core.config import settings as app_settings

        async def _run():
            from app.routers.wp_ai import suggest_fill, SuggestRequest

            fake_wp = FakeWorkingPaper(wp_id, project_id)
            fake_db = FakeDB(fake_wp)
            fake_user = FakeUser()

            mock_suggest = AsyncMock(return_value={
                "text": "建议文本",
                "confidence": 0.8,
            })

            mock_log = AsyncMock()

            with patch.object(app_settings, "WP_AI_SERVICE_ENABLED", True), \
                 patch("app.routers.wp_ai.WpAIService") as MockSvc, \
                 patch("app.services.audit_logger_enhanced.audit_logger.log_action", mock_log):

                mock_instance = MagicMock()
                mock_instance.suggest_field_content = mock_suggest
                MockSvc.return_value = mock_instance

                body = SuggestRequest(
                    sheet_name=sheet_name,
                    field_name=field_name,
                    existing_content="已有内容",
                )
                await suggest_fill(
                    wp_id=wp_id,
                    body=body,
                    db=fake_db,
                    user=fake_user,
                )

                # Property: audit_logger.log_action was called
                mock_log.assert_called_once()
                call_kwargs = mock_log.call_args[1]

                # Property: correct action type
                assert call_kwargs["action"] == "workpaper.ai_suggest_requested"
                # Property: correct object references
                assert call_kwargs["object_id"] == wp_id
                assert call_kwargs["object_type"] == "workpaper"
                assert call_kwargs["user_id"] == fake_user.id
                assert call_kwargs["project_id"] == project_id
                # Property: details contain field info
                assert call_kwargs["details"]["sheet_name"] == sheet_name
                assert call_kwargs["details"]["field_name"] == field_name

        asyncio.run(_run())
