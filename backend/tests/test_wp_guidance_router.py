"""GET /workpapers/{id}/guidance 的权限、render membership 与 runtime 接线。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.wp_guidance_chat import get_workpaper_guidance
from app.services.guidance_inventory import (
    GuidanceInventoryEntry,
    RuntimeGuidanceExemption,
)


class _Result:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _Db:
    def __init__(self, wp_code: str, wp_name: str = "测试底稿"):
        self.working_paper = SimpleNamespace(
            id=uuid4(),
            project_id=uuid4(),
            file_path="",
            file_version=1,
            is_deleted=False,
        )
        self.wp_index = SimpleNamespace(wp_code=wp_code, wp_name=wp_name, is_deleted=False)

    async def execute(self, _statement, _params=None):
        return _Result((self.working_paper, self.wp_index))


def _render_sheet(code: str | None, name: str, component_type: str = "d-form-table") -> dict:
    return {
        "sheet_code": code,
        "sheet_name": name,
        "sheet_code_reason": "explicit_code" if code else "no_canonical_code",
        "whole_workbook": False,
        "componentType": component_type,
    }


def _static_entry(code: str) -> GuidanceInventoryEntry:
    return GuidanceInventoryEntry(
        wp_code=code,
        path=f"/guidance/{code}.json",
        parse_status="ok",
        source_digest="a" * 64,
        exact_status="exact",
        missing_sections=(),
        reason="ok",
    )


def _response(code: str) -> dict:
    return {
        "wp_code": code,
        "wp_name": "测试底稿",
        "requested_sheet_code": None,
        "resolved_wp_code": code,
        "inherited_from_parent": False,
        "resolution_status": "missing",
        "resolution_reason": "parent_static_incomplete",
        "source": "static_json",
        "complexity": "low",
        "guidance_version": "guidance-v2-test",
        "source_digest": "a" * 64,
        "generated_at": "2026-09-07T00:00:00+00:00",
        "missing_sections": ["purpose"],
        "guidance": {"sections": [], "raw_text": "测试"},
        "recommended_questions": [],
    }


@pytest.fixture
def route_mocks(monkeypatch):
    from app.routers import wp_render_config
    from app.routers import wp_render_config_helpers
    from app.services import guidance_inventory
    from app.services import guidance_source_refs
    from app.services.wp_visibility import entry_integration
    from app.services.wp_guidance_service import GuidanceService

    gate = AsyncMock(return_value=SimpleNamespace())
    resolve = AsyncMock(return_value=_response("A3"))
    render = AsyncMock(
        return_value={
            "template_version": "2025.1",
            "sheets": [_render_sheet("A3", "商誉主表 A3")],
        }
    )
    monkeypatch.setattr(entry_integration, "gate_wp", gate)
    monkeypatch.setattr(wp_render_config, "_get_render_config_impl", render)
    monkeypatch.setattr(wp_render_config_helpers, "_resolve_template_path", lambda _wp, _code: None)
    snapshot = guidance_source_refs.TemplateAuthoritySnapshot(
        parent_wp_code="A3",
        authorities=(),
        blockers=("canonical_template_not_found",),
        facts_digest="f" * 64,
    )
    authority = Mock(return_value=snapshot)
    monkeypatch.setattr(guidance_source_refs, "build_template_authority_snapshot", authority)
    monkeypatch.setattr(
        guidance_inventory,
        "build_static_guidance_inventory",
        lambda **_kwargs: (),
    )
    monkeypatch.setattr(guidance_inventory, "load_runtime_exemptions", lambda _code: ())
    monkeypatch.setattr(guidance_inventory, "load_template_source_facts", lambda *_args, **_kwargs: ())
    monkeypatch.setattr(GuidanceService, "resolve_guidance", resolve)
    return SimpleNamespace(
        gate=gate,
        resolve=resolve,
        render=render,
        authority=authority,
    )


@pytest.mark.asyncio
async def test_route_uses_visibility_gate_and_runtime_inventory_for_parent_context(route_mocks):
    wp_id = str(uuid4())

    response = await get_workpaper_guidance(
        wp_id=wp_id,
        sheet_code=None,
        sheet_name=None,
        db=_Db("A3"),
        current_user=SimpleNamespace(id=uuid4()),
    )

    assert response["requested_sheet_name"] is None
    assert response["sheet_identity_reason"] == "sheet_without_code"
    assert response["whole_workbook"] is False
    assert response["inventory_run_id"]
    assert len(response["inventory_facts_digest"]) == 64
    assert "ai_enabled" in response
    assert route_mocks.gate.await_args.kwargs["entrypoint"] == "workpaper.dedicated_subroute"
    assert route_mocks.gate.await_args.kwargs["action"] == "dedicated_read"
    assert route_mocks.gate.await_args.kwargs["wp_id"].hex == wp_id.replace("-", "")
    assert route_mocks.render.await_args.args[1] is None
    assert route_mocks.authority.call_args.kwargs["parent_wp_code"] == "A3"
    assert route_mocks.authority.call_args.kwargs["render_sheets"] == route_mocks.render.return_value["sheets"]
    route_mocks.resolve.assert_awaited_once()
    kwargs = route_mocks.resolve.await_args.kwargs
    assert kwargs["parent_wp_code"] == "A3"
    assert kwargs["runtime_entry"] is not None
    assert kwargs["runtime_entry"].sheet_code == "A3"
    assert kwargs["runtime_entry"].exact_status == "missing"
    assert response["template_authority_digest"] == "f" * 64
    assert response["template_authority_blockers"] == ["canonical_template_not_found"]
    assert len(kwargs["inventory_facts_digest"]) == 64


@pytest.mark.asyncio
async def test_virtual_render_sheet_is_canonical_membership_and_enters_service(route_mocks):
    route_mocks.render.return_value = {
        "template_version": "2025.1",
        "sheets": [_render_sheet("A3-8", "商誉减值测试 A3-8", "html-renderer")],
    }
    route_mocks.resolve.return_value = _response("A3-8")

    response = await get_workpaper_guidance(
        wp_id=str(uuid4()),
        sheet_code=None,
        sheet_name="商誉减值测试 A3-8",
        db=_Db("A3"),
        current_user=SimpleNamespace(id=uuid4()),
    )

    assert route_mocks.gate.await_args.kwargs["requested_sheet_key"] == "A3-8"
    kwargs = route_mocks.resolve.await_args.kwargs
    assert kwargs["requested_sheet_code"] == "A3-8"
    assert kwargs["runtime_entry"].sheet_name == "商誉减值测试 A3-8"
    assert kwargs["runtime_entry"].exact_status == "missing"
    assert response["sheet_identity_reason"] == "derived_from_render_sheet"
    assert response["inventory_entry_id"] == kwargs["runtime_entry"].entry_id
    assert response["runtime_guidance_status"] == "missing"
    assert route_mocks.render.await_args.args[1] is None


@pytest.mark.asyncio
async def test_static_guidance_file_does_not_authorize_unreachable_sheet(route_mocks, monkeypatch):
    from app.services import guidance_inventory

    monkeypatch.setattr(
        guidance_inventory,
        "build_static_guidance_inventory",
        lambda **_kwargs: (_static_entry("A3-99"),),
    )
    route_mocks.render.return_value = {
        "template_version": "2025.1",
        "sheets": [_render_sheet("A3-8", "商誉减值测试 A3-8")],
    }

    with pytest.raises(HTTPException) as exc_info:
        await get_workpaper_guidance(
            wp_id=str(uuid4()),
            sheet_code="A3-99",
            sheet_name=None,
            db=_Db("A3"),
            current_user=SimpleNamespace(id=uuid4()),
        )

    assert exc_info.value.status_code == 422
    assert "render-config 可达清册" in str(exc_info.value.detail)
    route_mocks.resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_cross_workpaper_sheet_code_returns_422_from_render_membership(route_mocks):
    with pytest.raises(HTTPException) as exc_info:
        await get_workpaper_guidance(
            wp_id=str(uuid4()),
            sheet_code="D2-1",
            sheet_name=None,
            db=_Db("A3"),
            current_user=SimpleNamespace(id=uuid4()),
        )
    assert exc_info.value.status_code == 422
    assert "render-config 可达清册" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_whole_workbook_is_explicit_and_uses_registered_exemption(route_mocks, monkeypatch):
    from app.services import guidance_inventory

    now = datetime.now(UTC)
    exemption = RuntimeGuidanceExemption(
        kind="whole_workbook",
        target_sheet_code=None,
        target_sheet_name=None,
        inherits_from="A3",
        reason_code="onlyoffice_native_sheet_event_unavailable",
        basis_refs=({"kind": "methodology", "path": "spec/onlyoffice-whole-workbook"},),
        approved_by="methodology-admin",
        approved_at=(now - timedelta(days=1)).isoformat(),
        review_after=(now + timedelta(days=30)).isoformat(),
    )
    monkeypatch.setattr(guidance_inventory, "load_runtime_exemptions", lambda _code: (exemption,))

    response = await get_workpaper_guidance(
        wp_id=str(uuid4()),
        sheet_code=None,
        sheet_name=None,
        whole_workbook=True,
        db=_Db("A3"),
        current_user=SimpleNamespace(id=uuid4()),
    )

    kwargs = route_mocks.resolve.await_args.kwargs
    assert kwargs["whole_workbook"] is True
    assert kwargs["runtime_entry"].context_kind == "whole_workbook"
    assert kwargs["runtime_entry"].exact_status == "inherited"
    assert response["whole_workbook"] is True
    assert response["sheet_identity_reason"] == "whole_workbook"


@pytest.mark.asyncio
async def test_whole_workbook_rejects_sheet_code(route_mocks):
    with pytest.raises(HTTPException) as exc_info:
        await get_workpaper_guidance(
            wp_id=str(uuid4()),
            sheet_code="A3-8",
            whole_workbook=True,
            db=_Db("A3"),
            current_user=SimpleNamespace(id=uuid4()),
        )
    assert exc_info.value.status_code == 422
    assert "完整工作簿" in str(exc_info.value.detail)
    route_mocks.resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_wp_id_returns_404_before_gate(route_mocks):
    with pytest.raises(HTTPException) as exc_info:
        await get_workpaper_guidance(
            wp_id="not-a-uuid",
            db=_Db("A3"),
            current_user=SimpleNamespace(id=uuid4()),
        )
    assert exc_info.value.status_code == 404
    route_mocks.gate.assert_not_awaited()
