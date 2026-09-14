"""三层一致伪绿检测 — note-guidance-text-separation Task 1.4."""

from __future__ import annotations

import inspect
from pathlib import Path

from sqlalchemy import Text

from app.models.report_models import DisclosureNote
from app.models.report_schemas import DisclosureNoteDetail, DisclosureNoteUpdate
from app.services.disclosure_engine import DisclosureEngine


def test_v074_migration_file_exists():
    root = Path(__file__).resolve().parents[2]
    v074 = root / "migrations" / "V074__disclosure_notes_guidance_text.sql"
    content = v074.read_text(encoding="utf-8")
    assert "guidance_text TEXT" in content
    assert "IF NOT EXISTS" in content


def test_orm_guidance_text_column():
    col = DisclosureNote.__mapper__.columns["guidance_text"]
    assert isinstance(col.type, Text)
    assert col.nullable is True


def test_update_note_accepts_guidance_text():
    sig = inspect.signature(DisclosureEngine.update_note)
    assert "guidance_text" in sig.parameters


def test_schemas_expose_guidance_text():
    assert "guidance_text" in DisclosureNoteDetail.model_fields
    assert "guidance_text" in DisclosureNoteUpdate.model_fields
