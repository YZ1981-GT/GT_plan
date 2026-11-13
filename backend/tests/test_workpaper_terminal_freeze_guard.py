"""platform-release-blocker-closure Task 9：底稿终态内容冻结。"""

from __future__ import annotations

import ast
import inspect
import textwrap
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.workpaper_models import WpFileStatus
from app.services.workpaper_content_freeze import (
    WorkpaperContentFrozenError,
    assert_workpaper_content_writable,
    load_workpaper_status,
)


def _called_names(fn) -> set[str]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        WpFileStatus.review_passed,
        WpFileStatus.archived,
        WpFileStatus.review_level1_passed,
        WpFileStatus.review_level2_passed,
    ],
)
async def test_domain_guard_rejects_every_frozen_status_with_row_lock(status):
    result = SimpleNamespace(first=lambda: (status.value, "false"))
    db = SimpleNamespace(execute=AsyncMock(return_value=result))

    with pytest.raises(WorkpaperContentFrozenError, match="内容已冻结"):
        await assert_workpaper_content_writable(db, uuid4())

    statement = str(db.execute.await_args.args[0])
    assert "FOR UPDATE" in statement


def test_terminal_set_matches_platform_frozen_status_definition():
    """跨模块一致性：内容冻结门的终态集合必须与平台既有「冻结底稿」定义逐值相同。

    收窄本集合（如只留 review_passed/archived）会让被 formula_push 视为冻结的旧值底稿仍可
    经内容写端点改写；放宽同理失配。任一侧漂移本断言即红。
    """
    from app.services.formula_push.engine import FROZEN_WP_STATUSES
    from app.services.workpaper_content_freeze import TERMINAL_CONTENT_STATUSES

    assert {s.value for s in TERMINAL_CONTENT_STATUSES} == set(FROZEN_WP_STATUSES)


@pytest.mark.asyncio
async def test_domain_guard_allows_draft():
    result = SimpleNamespace(first=lambda: (WpFileStatus.draft.value, "false"))
    db = SimpleNamespace(execute=AsyncMock(return_value=result))

    status = await assert_workpaper_content_writable(db, uuid4())

    assert status is WpFileStatus.draft


@pytest.mark.asyncio
async def test_partial_postgres_workpaper_stub_without_status_is_writable():
    """V151 隔离桩仅有 id/project/revision 时，终态门不得因缺列反而阻断正常写链。"""
    result = SimpleNamespace(first=lambda: (None, None))
    db = SimpleNamespace(execute=AsyncMock(return_value=result))

    assert await assert_workpaper_content_writable(db, uuid4()) is None
    statement = str(db.execute.await_args.args[0])
    assert "to_jsonb(working_paper)->>'status'" in statement
    assert "to_jsonb(working_paper)->>'is_deleted'" in statement


@pytest.mark.asyncio
async def test_sqlite_uses_orm_path_instead_of_postgres_jsonb():
    """PG 专有 to_jsonb 不得进入 SQLite 单测路径。"""
    bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    result = SimpleNamespace(scalar_one_or_none=lambda: WpFileStatus.draft)
    db = SimpleNamespace(get_bind=lambda: bind, execute=AsyncMock(return_value=result))

    assert await load_workpaper_status(db, uuid4()) is WpFileStatus.draft
    assert "to_jsonb" not in str(db.execute.await_args.args[0])


@pytest.mark.asyncio
async def test_deleted_workpaper_remains_outside_terminal_freeze_scope():
    """与旧的 is_deleted=false 过滤同义：删除业务另有专门端点守卫。"""
    result = SimpleNamespace(first=lambda: (WpFileStatus.review_passed.value, "true"))
    db = SimpleNamespace(execute=AsyncMock(return_value=result))

    assert await assert_workpaper_content_writable(db, uuid4()) is None


def test_sync_workflow_lock_has_distinct_423_mapping():
    from app.services.workpaper_sync.endpoint_guard import (
        SyncActionForbiddenError,
        SyncWorkflowLockedError,
        http_status_for_refusal,
    )

    assert http_status_for_refusal(SyncWorkflowLockedError("locked")) == 423
    assert http_status_for_refusal(SyncActionForbiddenError("denied")) == 403


def test_content_revision_lock_checks_terminal_status_in_the_same_locked_row():
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository

    source = inspect.getsource(WorkpaperSyncRepository.lock_workpaper)
    assert "to_jsonb(working_paper)->>'status'" in source
    assert "FOR UPDATE" in source
    # 终态判定复用内容写门禁的单一定义（raise_if_status_text_frozen），而非在此第二处枚举状态。
    assert "raise_if_status_text_frozen" in source


def test_all_primary_content_choke_points_call_the_freeze_guard():
    from app.routers import _wp_gate, excel_html, wp_structure, wp_sync_router
    from app.services.formula_settings.domain_stores import WpStore
    from app.services.wp_visibility import entry_integration

    expected = {
        "dedicated content writes": (_wp_gate.enforce_edit_lock_for_content_write, "raise_if_workpaper_frozen"),
        "computed write-back": (_wp_gate.enforce_edit_lock_at_write_point, "raise_if_workpaper_frozen"),
        "sync editor entry": (wp_sync_router._enforce_entry_edit_lock, "raise_if_workpaper_frozen"),
        "legacy file write": (excel_html._guard_bound_workpaper_write, "raise_if_workpaper_frozen"),
        "bulk import": (entry_integration.make_bulk_preflight, "assert_workpaper_content_writable"),
        "formula project write": (WpStore._assert_wps_writable, "assert_workpaper_content_writable"),
        "batch structure": (wp_structure.batch_generate, "raise_if_workpaper_frozen"),
    }
    missing = [label for label, (fn, name) in expected.items() if name not in _called_names(fn)]
    assert missing == []


def test_attachment_content_mutations_preflight_all_linked_workpapers():
    from app.routers import attachments, wp_onlyoffice_router

    functions = (
        attachments.confirm_ocr,
        attachments.update_ocr_status,
        attachments.retry_ocr,
        attachments.delete_attachment,
        attachments.rollback_attachment_version,
    )
    missing = [fn.__name__ for fn in functions if "assert_linked_workpapers_writable" not in _called_names(fn)]
    assert missing == []
    assert "assert_workpaper_content_writable" in _called_names(
        wp_onlyoffice_router.post_sheet_onlyoffice_callback
    )


def test_legacy_excel_html_file_mutations_share_one_bound_workpaper_guard():
    from app.routers import excel_html

    functions = (
        excel_html.save_edits,
        excel_html.confirm_as_template,
        excel_html.sync_from_onlyoffice,
        excel_html.rollback_file_version,
        excel_html.execute_formulas,
    )
    missing = [fn.__name__ for fn in functions if "_guard_bound_workpaper_write" not in _called_names(fn)]
    assert missing == []


def test_structure_get_paths_generate_in_memory_only():
    from app.routers import wp_structure

    for fn in (wp_structure.get_structure, wp_structure.get_structure_html):
        source = inspect.getsource(fn)
        assert "persist_generated=False" in source


def test_review_status_transitions_take_same_workpaper_row_lock():
    from app.services.working_paper_service import WorkingPaperService

    for fn in (WorkingPaperService.update_status, WorkingPaperService.update_review_status):
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
        assert any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "with_for_update"
            for node in ast.walk(tree)
        ), fn.__name__


@pytest.mark.asyncio
async def test_http_freeze_adapter_keeps_423_and_domain_message():
    from app.routers._wp_gate import raise_if_workpaper_frozen

    result = SimpleNamespace(first=lambda: (WpFileStatus.review_passed.value, "false"))
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    with pytest.raises(HTTPException) as caught:
        await raise_if_workpaper_frozen(db, uuid4())
    assert caught.value.status_code == 423
    assert "创建新修订" in str(caught.value.detail)


@pytest.mark.asyncio
async def test_attachment_guard_rejects_when_any_linked_workpaper_is_frozen(monkeypatch):
    from app.services import attachment_access

    first, frozen = uuid4(), uuid4()
    monkeypatch.setattr(
        "app.services.wp_visibility.entry_integration.linked_attachment_wp_ids",
        AsyncMock(return_value=[frozen, first]),
    )

    async def check(_db, wp_id, *, for_update=True):
        assert for_update is True
        if wp_id == frozen:
            raise WorkpaperContentFrozenError("底稿复核通过，内容已冻结")
        return WpFileStatus.draft

    monkeypatch.setattr(
        "app.services.workpaper_content_freeze.assert_workpaper_content_writable",
        check,
    )
    with pytest.raises(HTTPException) as caught:
        await attachment_access.assert_linked_workpapers_writable(
            SimpleNamespace(), uuid4()
        )
    assert caught.value.status_code == 423


@pytest.mark.asyncio
async def test_sync_visibility_probe_reads_terminal_status_separately_from_role_readonly(monkeypatch):
    from app.routers.wp_sync_router import WpGateVisibilityProbe

    project_id, wp_id = uuid4(), uuid4()
    monkeypatch.setattr(
        "app.routers._wp_gate.enforce_wp_gate",
        AsyncMock(return_value=SimpleNamespace(readonly=False, role="manager", access_kinds={"edit"})),
    )
    result = SimpleNamespace(first=lambda: (WpFileStatus.review_passed.value, "false"))
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    facts = await WpGateVisibilityProbe(db, SimpleNamespace(id=uuid4())).observe(
        project_id=project_id,
        wp_id=wp_id,
        entry_id="xlsx/gt-d4-operating-revenue",
    )
    assert facts["project_visible"] is True
    assert facts["readonly"] is False
    assert facts["workflow_locked"] is True


@pytest.mark.asyncio
async def test_real_dedicated_route_dependency_returns_423_before_handler(monkeypatch):
    from starlette.requests import Request

    from app.routers import _wp_gate

    wp_id = uuid4()
    monkeypatch.setattr(
        _wp_gate,
        "enforce_wp_gate",
        AsyncMock(return_value=SimpleNamespace()),
    )
    result = SimpleNamespace(first=lambda: (WpFileStatus.review_passed.value, "false"))
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": f"/api/workpapers/{wp_id}/save",
            "headers": [],
            "path_params": {"wp_id": str(wp_id)},
            "route": SimpleNamespace(path="/api/workpapers/{wp_id}/save"),
        }
    )
    with pytest.raises(HTTPException) as caught:
        await _wp_gate.dedicated_wp_gate(
            request=request,
            db=db,
            current_user=SimpleNamespace(id=uuid4()),
        )
    assert caught.value.status_code == 423
    assert "复核通过" in str(caught.value.detail)
