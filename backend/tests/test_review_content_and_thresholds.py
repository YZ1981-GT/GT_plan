"""Tests for review_content_loader and sheet-type pass thresholds."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.llm_response_parser import (
    LlmResponseParser,
    ReviewFinding,
    PassThreshold,
    resolve_pass_threshold,
)
from app.services.review_content_loader import (
    _filter_and_format_responses,
    _guess_item_prefix,
)


def _finding(risk: str, passed: bool = False) -> ReviewFinding:
    return ReviewFinding(
        id="x",
        description="t",
        risk_level=risk,
        pass_status=passed,
        category="general",
    )


class TestPassThresholdBySheet:
    def test_default_threshold(self):
        t = resolve_pass_threshold(None)
        assert t == PassThreshold(max_high=0, max_medium=2)

    def test_adjudication_stricter(self):
        t = resolve_pass_threshold("审定表D2-1")
        assert t.max_medium == 1

    def test_voucher_check_wider(self):
        t = resolve_pass_threshold("凭证检查表D2-7")
        assert t.max_medium == 4

    def test_two_medium_fail_on_adjudication_pass_on_default(self):
        findings = [_finding("medium"), _finding("medium")]
        assert LlmResponseParser.determine_pass_status(findings) == "pass"
        assert LlmResponseParser.determine_pass_status(findings, "审定表D2-1") == "fail"

    def test_four_medium_pass_on_voucher_fail_on_default(self):
        findings = [_finding("medium") for _ in range(4)]
        assert LlmResponseParser.determine_pass_status(findings) == "fail"
        assert LlmResponseParser.determine_pass_status(findings, "D2-7") == "pass"

    def test_any_high_always_fail(self):
        findings = [_finding("high")]
        assert LlmResponseParser.determine_pass_status(findings, "D2-7") == "fail"
        assert LlmResponseParser.determine_pass_status(findings, "D2-1") == "fail"


class TestContentLoaderHelpers:
    def test_guess_prefix_numeric(self):
        assert _guess_item_prefix("审定表D2-1") == "D2-1"
        assert _guess_item_prefix("ECL测算D2-9") == "D2-9"

    def test_guess_prefix_aliases(self):
        assert _guess_item_prefix("截止测试") == "D2-cutoff"
        assert _guess_item_prefix("附注上市") == "D2-note-listed"

    def test_filter_by_prefix(self):
        rows = [
            ("D2-1-adj", "Y", "ok", None),
            ("D2-2-detail", None, "x", None),
            ("D2-cutoff-1", None, "c", None),
        ]
        filtered = _filter_and_format_responses(rows, "审定表D2-1")
        assert len(filtered) == 1
        assert filtered[0]["item_id"] == "D2-1-adj"

    @pytest.mark.asyncio
    async def test_load_empty_returns_placeholder(self):
        from app.services.review_content_loader import load_workpaper_review_content

        mock_db = AsyncMock()
        mock_result_empty = MagicMock()
        mock_result_empty.fetchall.return_value = []
        mock_result_empty.first.return_value = None

        # first execute → checklist rows; second → parsed_data
        mock_db.execute = AsyncMock(side_effect=[mock_result_empty, mock_result_empty])

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.services.review_content_loader.async_session",
            return_value=mock_cm,
        ):
            text = await load_workpaper_review_content("00000000-0000-0000-0000-000000000001")
            assert "无内容" in text or "尚未填写" in text
