"""普通底稿 content version / export / archive evidence 守卫。

spec platform-global-display-settings-closure 任务 10 / AC-22。
"""
from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

ROOT = Path(__file__).resolve().parents[1]


class TestEvidenceBuilder:
    @pytest.mark.asyncio
    async def test_formal_builder_uses_policy_snapshot_digest(self, monkeypatch):
        from app.services.workpaper_sync import export_evidence

        snapshot = json.dumps(
            {
                "_digest": "a" * 64,
                "_project_id": "11111111-2222-3333-4444-555555555555",
                "unit": "yuan",
                "divisor": 1,
                "regions": [],
            }
        )

        async def fake_snapshot(_db, *, project_id):
            assert project_id == UUID("11111111-2222-3333-4444-555555555555")
            return snapshot

        monkeypatch.setattr(
            "app.services.export_policy_snapshot.resolve_policy_snapshot_for_project",
            fake_snapshot,
        )
        evidence = await export_evidence.build_formal_content_export_evidence(
            object(), project_id=UUID("11111111-2222-3333-4444-555555555555")
        )
        assert evidence.export_surface_class == "formal"
        assert evidence.unit_policy_digest == "a" * 64
        assert evidence.unit_policy_snapshot["unit"] == "yuan"
        assert evidence.source_storage_unit is None


class TestExportAndArchiveConsumers:
    def test_workpaper_export_validates_current_content_evidence(self):
        src = (ROOT / "app/routers/wp_xlsx_export.py").read_text(encoding="utf-8")
        assert "resolve_current_content_export_evidence" in src
        assert "current_content_version_id" in src
        assert "WorkpaperExportEvidenceError" in src

    def test_archive_binds_content_evidence(self):
        src = (ROOT / "app/services/archive_inventory.py").read_text(encoding="utf-8")
        for key in (
            "content_version_id",
            "representation_id",
            "artifact_id",
            "artifact_sha256",
            "policy_digest",
        ):
            assert key in src
        assert "resolve_current_content_export_evidence" in src

    def test_formal_content_evidence_is_not_data_exchange(self):
        src = (ROOT / "app/services/workpaper_sync/export_evidence.py").read_text(encoding="utf-8")
        assert 'export_surface_class="formal"' in src
        assert "source_storage_unit=None" in src
