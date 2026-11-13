from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.orm.attributes import flag_modified

from app.models.audit_platform_models import TbLedger, TrialBalance
from app.models.dataset_models import LedgerDataset
from app.models.note_account_mapping import NoteAccountMapping
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType
from app.routers import lineage
from app.services import note_readiness_service
from app.services.note_readiness_service import NoteRegistryUnavailable
from app.services.unified_lineage_service import UnifiedLineageService
from tests.authz_world import sqlite_world


@pytest_asyncio.fixture
async def lineage_world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(
        monkeypatch,
        # 附注溯源（trace_section）映射到底稿后按科目取试算表与序时账（当前账套）：这三张表也要有
        extra_tables=(WpIndex.__table__, WorkingPaper.__table__, NoteAccountMapping.__table__,
                      TrialBalance.__table__, TbLedger.__table__, LedgerDataset.__table__),
    ) as world:
        world.target.template_type = "soe"
        await world.db.flush()

        async def no_wp_trace(self, project_id, source, identifier):
            return []

        async def no_attachments(self, project_id, object_type, object_id):
            return []

        monkeypatch.setattr(UnifiedLineageService, "_query_wp_upstream", no_wp_trace)
        monkeypatch.setattr(UnifiedLineageService, "_query_attachments", no_attachments)
        yield world


async def _paper(world, code: str) -> None:
    index = WpIndex(project_id=world.target.id, wp_code=code, wp_name=f"{code} 底稿")
    world.db.add(index)
    await world.db.flush()
    world.db.add(WorkingPaper(
        project_id=world.target.id,
        wp_index_id=index.id,
        file_path=f"test/{code}.xlsx",
        source_type=WpSourceType.manual,
        parsed_data={"html_data": {f"{code}-sheet": {}}},
    ))
    await world.db.flush()


async def _get(world, section: str):
    identity = await world.readonly_member()
    async with world.client(lineage.router, user=identity.user) as client:
        return await client.get(
            f"/api/projects/{world.target.id}/lineage",
            params={
                "object_type": "note_cell",
                "object_id": section,
                "direction": "upstream",
                "year": 2025,
            },
        )


async def test_lineage_endpoint_returns_all_registry_workpapers(lineage_world, monkeypatch):
    world = lineage_world
    await _paper(world, "D1")
    await _paper(world, "D2")
    monkeypatch.setattr(note_readiness_service, "_strict_registry_entries", lambda: (
        {"wp_code": "D1", "soe": "八、4"},
        {"wp_code": "D2", "soe_sections": {"extra": "八、4"}},
    ))

    response = await _get(world, "八、4")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["partial"] is False
    assert payload["errors"] == []
    assert [item["wp_code"] for item in payload["upstream"]] == ["D1", "D2"]


async def test_lineage_endpoint_project_override_has_priority(lineage_world, monkeypatch):
    world = lineage_world
    await _paper(world, "D1")
    await _paper(world, "D2")
    monkeypatch.setattr(note_readiness_service, "_strict_registry_entries", lambda: (
        {"wp_code": "D1", "soe": "八、4"},
        {"wp_code": "D2", "soe": "八、5"},
    ))
    world.target.wizard_state = {"note_wp_mapping": {"八、4": ["D2"]}}
    flag_modified(world.target, "wizard_state")
    await world.db.flush()

    response = await _get(world, "八、4")
    assert response.status_code == 200, response.text
    assert [item["wp_code"] for item in response.json()["upstream"]] == ["D2"]


async def test_lineage_endpoint_not_found_is_complete_empty_result(lineage_world, monkeypatch):
    world = lineage_world
    monkeypatch.setattr(note_readiness_service, "_strict_registry_entries", lambda: (
        {"wp_code": "D1", "soe": "八、4"},
    ))
    response = await _get(world, "八、999")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["partial"] is False
    assert payload["errors"] == []
    assert payload["upstream"] == []


@pytest.mark.parametrize(
    ("setup", "code"),
    [
        ("registry", "REGISTRY_UNAVAILABLE"),
        ("override", "PROJECT_MAPPING_INVALID"),
    ],
)
async def test_lineage_endpoint_distinguishes_mapping_errors(lineage_world, monkeypatch, setup, code):
    world = lineage_world
    if setup == "registry":
        def fail_registry():
            raise NoteRegistryUnavailable("注册表损坏")
        monkeypatch.setattr(note_readiness_service, "_strict_registry_entries", fail_registry)
    else:
        monkeypatch.setattr(note_readiness_service, "_strict_registry_entries", lambda: (
            {"wp_code": "D1", "soe": "八、4"},
        ))
        world.target.wizard_state = {"note_wp_mapping": {"八、4": ["UNKNOWN"]}}
        flag_modified(world.target, "wizard_state")
        await world.db.flush()

    response = await _get(world, "八、4")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["partial"] is True
    assert payload["upstream"] == []
    assert [error["error_code"] for error in payload["errors"]] == [code]
