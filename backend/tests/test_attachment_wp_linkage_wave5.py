"""附件↔底稿关联收敛 — Wave 5：stale 失效前置

spec: attachment-workpaper-linkage-convergence Task 6.1
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.workpaper_attachment_stale import build_stale_info


class TestBuildStaleInfoLevels:
    @pytest.mark.asyncio
    async def test_definite_from_inactive_refs(self):
        wp_id = uuid.uuid4()
        project_id = uuid.uuid4()
        ref_id = uuid.uuid4()

        wp_row = (project_id, False, 2025)
        calls = {"n": 0}

        async def fake_execute(stmt, params=None):
            calls["n"] += 1
            result = MagicMock()
            if calls["n"] == 1:
                # working_paper × project 行
                result.first.return_value = wp_row
                return result
            # evidence_refs inactive
            result.mappings.return_value.all.return_value = [
                {
                    "id": ref_id,
                    "evidence_type": "attachment",
                    "evidence_id": str(uuid.uuid4()),
                    "label": "失效引用",
                    "status": "inactive",
                }
            ]
            return result

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=fake_execute)

        info = await build_stale_info(db, wp_id=wp_id, attachment_ids=[])
        assert info is not None
        assert info["has_stale"] is True
        assert info["level"] == "definite"
        assert info["items"][0]["reason"] == "ref_inactive"

    @pytest.mark.asyncio
    async def test_conservative_prefill_stale(self):
        wp_id = uuid.uuid4()
        project_id = uuid.uuid4()
        wp_row = (project_id, True, 2025)

        async def fake_execute(stmt, params=None):
            sql = str(stmt)
            result = MagicMock()
            if "working_paper" in sql.lower() or "WorkingPaper" in sql:
                result.first.return_value = wp_row
                return result
            result.mappings.return_value.all.return_value = []
            return result

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=fake_execute)

        info = await build_stale_info(db, wp_id=wp_id, attachment_ids=[])
        assert info is not None
        assert info["has_stale"] is True
        assert info["level"] == "conservative"
        assert info["items"][0]["reason"] == "prefill_stale"

    @pytest.mark.asyncio
    async def test_no_stale(self):
        wp_id = uuid.uuid4()
        project_id = uuid.uuid4()
        wp_row = (project_id, False, 2025)

        async def fake_execute(stmt, params=None):
            sql = str(stmt)
            result = MagicMock()
            if "working_paper" in sql.lower() or "WorkingPaper" in sql:
                result.first.return_value = wp_row
                return result
            result.mappings.return_value.all.return_value = []
            return result

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=fake_execute)

        info = await build_stale_info(db, wp_id=wp_id, attachment_ids=[])
        assert info is not None
        assert info["has_stale"] is False
        assert info["level"] is None

    @pytest.mark.asyncio
    async def test_fail_open_returns_none(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("db down"))
        info = await build_stale_info(db, wp_id=uuid.uuid4(), attachment_ids=[])
        assert info is None


class TestGetWpAttachmentsStaleAttach:
    @pytest.mark.asyncio
    async def test_attaches_stale_info(self):
        from app.services.attachment_service import AttachmentService

        svc = AttachmentService(AsyncMock())
        with (
            patch.object(
                svc,
                "_resolve_wp_code",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.services.workpaper_attachment_stale.build_stale_info",
                new_callable=AsyncMock,
                return_value={
                    "has_stale": True,
                    "level": "conservative",
                    "items": [{"reason": "prefill_stale"}],
                    "project_id": "p1",
                },
            ),
            patch.object(svc.db, "execute", new_callable=AsyncMock) as ex,
        ):
            empty = MagicMock()
            empty.all.return_value = []
            empty.scalars.return_value.all.return_value = []
            empty.scalars.return_value.unique.return_value.all.return_value = []
            ex.return_value = empty

            result = await svc.get_wp_attachments(uuid.uuid4())
            assert result["stale_info"]["has_stale"] is True
            assert result["stale_info"]["level"] == "conservative"
