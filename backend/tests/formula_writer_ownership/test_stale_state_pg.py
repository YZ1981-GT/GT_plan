"""真实 PostgreSQL：值不变重算清 stale、失败保留，并保证事务整体回滚。"""
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
import sqlalchemy as sa

pytestmark = [pytest.mark.pg_only, pytest.mark.asyncio]


async def test_recompute_outcome_updates_stale_in_caller_transaction(monkeypatch):
    from app.core.database import async_session
    from app.models.core import Project
    from app.models.report_models import DisclosureNote
    from app.services.disclosure_engine import RefillReport
    from app.services.note_wp_mapping_service import _finalize_refill_report
    from app.services.stale_state import StaleSource, mark_note_stale

    project_id = uuid4()
    note_id = uuid4()
    section = "八、S3-PG"
    year = 2099

    async def no_formula_failures(*_args, **_kwargs):
        return {
            "formula_updated": 0,
            "formula_sections": [],
            "formula_failed_sections": [],
            "formula_errors": [],
            "formula_differs": 0,
        }

    monkeypatch.setattr(
        "app.services.note_wp_mapping_service._apply_final_note_formulas",
        no_formula_failures,
    )

    async with async_session() as db:
        transaction = await db.begin()
        try:
            db.add(Project(
                id=project_id,
                name="【测试】S3 stale 状态机回滚",
                client_name="【测试】S3 stale 状态机回滚",
                audit_period_start=date(year, 1, 1),
                audit_period_end=date(year, 12, 31),
                audit_year=year,
                template_type="soe",
            ))
            db.add(DisclosureNote(
                id=note_id,
                project_id=project_id,
                year=year,
                note_section=section,
                section_title="【测试】值不变重算",
                table_data={"rows": [{"name": "合计", "values": ["100.00"]}]},
            ))
            await db.flush()

            await mark_note_stale(
                db, project_id, source=StaleSource.ADJUSTMENT,
                sections=[section], year=year,
            )
            note = await db.get(DisclosureNote, note_id)
            await db.refresh(note)
            assert note.is_stale is True
            assert note.stale_source == StaleSource.ADJUSTMENT.value

            unchanged = RefillReport(
                requested_sections=[section],
                sections_recomputed=[section],
                changed_sections=[],
            )
            await _finalize_refill_report(db, project_id, year, unchanged)
            await db.refresh(note)
            assert unchanged.changed_sections == []
            assert unchanged.recomputed_sections == [section]
            assert unchanged.cleared_sections == [section]
            assert note.is_stale is False
            assert note.stale_source is None

            # 新一轮上游变更后本章计算失败：不得清除 stale/source。
            await mark_note_stale(
                db, project_id, source=StaleSource.FORMULA_SETTINGS,
                sections=[section], year=year,
            )
            failed = RefillReport(
                requested_sections=[section],
                sections_recomputed=[],
                failed_sections=[section],
            )
            await _finalize_refill_report(db, project_id, year, failed)
            await db.refresh(note)
            assert failed.cleared_sections == []
            assert note.is_stale is True
            assert note.stale_source == StaleSource.FORMULA_SETTINGS.value
        finally:
            await transaction.rollback()

    # 独立会话反查：临时【测试】项目与附注均未持久化。
    async with async_session() as verify:
        project_count = await verify.scalar(
            sa.select(sa.func.count()).select_from(Project).where(Project.id == project_id)
        )
        note_count = await verify.scalar(
            sa.select(sa.func.count()).select_from(DisclosureNote).where(DisclosureNote.id == note_id)
        )
    assert project_count == 0
    assert note_count == 0
