from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.disclosure_engine import RefillReport
from app.services.note_wp_mapping_service import _finalize_refill_report


@pytest.mark.asyncio
async def test_value_unchanged_success_is_cleared():
    db = AsyncMock()
    project_id = uuid4()
    report = RefillReport(
        requested_sections=["八、1"],
        sections_recomputed=["八、1"],
        changed_sections=[],
    )

    with (
        patch(
            "app.services.note_wp_mapping_service._apply_final_note_formulas",
            new=AsyncMock(return_value={
                "formula_updated": 0,
                "formula_sections": [],
                "formula_failed_sections": [],
                "formula_errors": [],
                "formula_differs": 0,
            }),
        ),
        patch(
            "app.services.stale_state.clear_note_stale",
            new=AsyncMock(return_value=1),
        ) as clear,
    ):
        await _finalize_refill_report(db, project_id, 2025, report)

    assert report.recomputed_sections == ["八、1"]
    assert report.changed_sections == []
    assert report.failed_sections == []
    assert report.cleared_sections == ["八、1"]
    clear.assert_awaited_once_with(
        db, project_id, sections=["八、1"], year=2025
    )


@pytest.mark.asyncio
async def test_formula_failure_is_removed_from_clear_set():
    db = AsyncMock()
    project_id = uuid4()
    report = RefillReport(
        requested_sections=["八、1", "八、2"],
        sections_recomputed=["八、1", "八、2"],
        changed_sections=["八、1"],
    )

    with (
        patch(
            "app.services.note_wp_mapping_service._apply_final_note_formulas",
            new=AsyncMock(return_value={
                "formula_updated": 0,
                "formula_sections": [],
                "formula_failed_sections": ["八、2"],
                "formula_errors": ["附注公式失败 八、2: ZeroDivisionError"],
                "formula_differs": 0,
            }),
        ),
        patch(
            "app.services.stale_state.clear_note_stale",
            new=AsyncMock(return_value=1),
        ) as clear,
    ):
        await _finalize_refill_report(db, project_id, 2025, report)

    assert report.recomputed_sections == ["八、1"]
    assert report.failed_sections == ["八、2"]
    assert report.cleared_sections == ["八、1"]
    assert report.error_details == [{
        "section": "八、2",
        "stage": "formula",
        "message": "附注公式失败 八、2: ZeroDivisionError",
    }]
    clear.assert_awaited_once_with(
        db, project_id, sections=["八、1"], year=2025
    )


@pytest.mark.asyncio
async def test_formula_written_section_is_changed():
    db = AsyncMock()
    project_id = uuid4()
    report = RefillReport(sections_recomputed=["八、3"])

    with (
        patch(
            "app.services.note_wp_mapping_service._apply_final_note_formulas",
            new=AsyncMock(return_value={
                "formula_updated": 1,
                "formula_sections": ["八、3"],
                "formula_failed_sections": [],
                "formula_errors": [],
                "formula_differs": 0,
            }),
        ),
        patch(
            "app.services.stale_state.clear_note_stale",
            new=AsyncMock(return_value=1),
        ),
    ):
        await _finalize_refill_report(db, project_id, 2025, report)

    assert report.changed_sections == ["八、3"]
    assert report.cleared_sections == ["八、3"]
