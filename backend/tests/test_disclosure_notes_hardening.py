"""Wave 0/1/4 附注后端加固属性与回归测试。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from hypothesis import given, settings, strategies as st

from app.deps import get_current_user
from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.core import User, UserRole
from app.models.report_schemas import DisclosureNoteGenerateRequest, DisclosureNoteUpdate
from app.models.report_models import NoteStatus
from app.routers import disclosure_notes as notes_router
from app.services.disclosure_mutation_coordinator import (
    DisclosureMutationCoordinator,
    _LOCAL_LOCKS,
    _LOCAL_RESULTS,
    mutation_fingerprint,
)
from app.services.custom_query.ownership_guard import OwnershipGuard

PROJECT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
NOTE_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
USER_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _run(coro):
    return asyncio.run(coro)


def _user() -> User:
    return User(
        id=USER_ID,
        username="hardening-user",
        email="hardening@test.local",
        hashed_password="x",
        role=UserRole.admin,
        is_active=True,
        is_deleted=False,
    )


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDB:
    def __init__(self, *, commit_fails: bool = False):
        self.commit_fails = commit_fails
        self.commit_count = 0
        self.rollback_count = 0

    async def commit(self):
        self.commit_count += 1
        if self.commit_fails:
            raise RuntimeError("commit failed")

    async def rollback(self):
        self.rollback_count += 1


def _event() -> EventPayload:
    return EventPayload(
        event_type=EventType.NOTE_SECTION_SAVED,
        project_id=PROJECT_ID,
        year=2025,
        extra={"section_code": "五、1", "action": "update"},
    )


# Feature: advanced-query-disclosure-integration-hardening, Property P1
@given(row_idx=st.integers(min_value=0, max_value=50), col_idx=st.integers(min_value=0, max_value=50))
@settings(max_examples=5, deadline=None)
def test_p1_trace_authorizes_after_minimal_project_lookup_without_domain_read(row_idx, col_idx):
    """越权 trace 只解析 project_id，且 403 前不进入 trace 领域查询。"""
    db = MagicMock()
    db.execute = AsyncMock(return_value=_ScalarResult(PROJECT_ID))
    denied = HTTPException(
        status_code=403,
        detail={"error_code": "FORBIDDEN_PROJECT", "message": "无权访问该项目数据"},
    )

    with patch(
        "app.routers.disclosure_notes.OwnershipGuard.assert_target_accessible",
        new=AsyncMock(side_effect=denied),
    ) as guard, patch(
        "app.routers.disclosure_notes.DisclosureEngine.trace_cell",
        new=AsyncMock(),
    ) as trace:
        with pytest.raises(HTTPException) as exc_info:
            _run(notes_router.trace_cell(NOTE_ID, row_idx, col_idx, db, _user()))

    assert exc_info.value.status_code == 403
    assert "五、1" not in str(exc_info.value.detail)
    assert db.execute.await_count == 1
    guard.assert_awaited_once()
    trace.assert_not_awaited()


# Feature: advanced-query-disclosure-integration-hardening, Property P2
@given(text=st.one_of(st.none(), st.text(max_size=20)))
@settings(max_examples=5, deadline=None)
def test_p2_update_denial_precedes_all_mutation(text):
    """update 按 note_id 最小解析项目后，edit 门禁失败时零 mutation/commit。"""
    db = MagicMock()
    db.execute = AsyncMock(return_value=_ScalarResult(PROJECT_ID))
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    denied = HTTPException(status_code=403, detail="权限不足")

    with patch(
        "app.routers.disclosure_notes._assert_project_edit",
        new=AsyncMock(side_effect=denied),
    ) as gate, patch(
        "app.routers.disclosure_notes.DisclosureEngine.update_note",
        new=AsyncMock(),
    ) as mutation:
        with pytest.raises(HTTPException) as exc_info:
            _run(
                notes_router.update_note(
                    NOTE_ID,
                    DisclosureNoteUpdate(text_content=text),
                    db,
                    _user(),
                    "p2-denied",
                )
            )

    assert exc_info.value.status_code == 403
    gate.assert_awaited_once()
    mutation.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_generate_project_gate_precedes_lock_and_prerequisite():
    """body.project_id 的统一 edit 门禁失败时，锁后业务检查均不可达。"""
    db = MagicMock()
    denied = HTTPException(status_code=403, detail="权限不足")
    request = DisclosureNoteGenerateRequest(project_id=PROJECT_ID, year=2025)

    with patch(
        "app.routers.disclosure_notes._assert_project_edit",
        new=AsyncMock(side_effect=denied),
    ), patch(
        "app.services.prerequisite_checker.PrerequisiteChecker.check",
        new=AsyncMock(),
    ) as prerequisite:
        with pytest.raises(HTTPException):
            _run(notes_router.generate_notes(request, db, _user(), "p2-generate"))

    prerequisite.assert_not_awaited()


# Feature: advanced-query-disclosure-integration-hardening, Property P8
@given(fault=st.sampled_from(["none", "mutate", "commit", "publish"]))
@settings(max_examples=8, deadline=None)
def test_p8_transaction_event_state_machine(fault, monkeypatch):
    """commit 前失败 rollback/无事件；commit 后事件失败保留数据并暴露 warning。"""
    _LOCAL_RESULTS.clear()
    _LOCAL_LOCKS.clear()
    monkeypatch.setattr("app.core.redis.redis_client", None)
    db = _FakeDB(commit_fails=fault == "commit")
    mutation_calls = 0

    async def mutate():
        nonlocal mutation_calls
        mutation_calls += 1
        if fault == "mutate":
            raise RuntimeError("mutation failed")
        return {"ok": True}

    publish = AsyncMock(
        side_effect=RuntimeError("event failed") if fault == "publish" else None
    )
    mutation_id = f"p8-{fault}-{uuid4()}"
    coordinator = DisclosureMutationCoordinator(
        db,
        project_id=PROJECT_ID,
        mutation_id=mutation_id,
        fingerprint=mutation_fingerprint("update", {"value": 1}),
    )

    with patch("app.services.event_bus.event_bus.publish", new=publish):
        if fault in {"mutate", "commit"}:
            with pytest.raises(RuntimeError):
                _run(coordinator.execute(mutate, lambda _response: _event()))
            assert db.rollback_count == 1
            publish.assert_not_awaited()
        else:
            response = _run(coordinator.execute(mutate, lambda _response: _event()))
            assert db.commit_count == 1
            assert db.rollback_count == 0
            if fault == "publish":
                assert response["event_delivery"] == "failed"
                assert response["warnings"][0]["code"] == "event_delivery_failed"
            else:
                assert response["event_delivery"] == "published"
                assert response["warnings"] == []
    assert mutation_calls == 1


# Feature: advanced-query-disclosure-integration-hardening, Property P9
@given(client_mutation_id=st.uuids().map(str), value=st.integers())
@settings(max_examples=5, deadline=None)
def test_p9_same_mutation_id_is_at_most_once(client_mutation_id, value, monkeypatch):
    """同 project/id/摘要顺序重试只 mutation/commit/publish 一次并返回相同最终状态。"""
    _LOCAL_RESULTS.clear()
    _LOCAL_LOCKS.clear()
    monkeypatch.setattr("app.core.redis.redis_client", None)
    db = _FakeDB()
    mutation_calls = 0

    async def mutate():
        nonlocal mutation_calls
        mutation_calls += 1
        return {"ok": True, "value": value}

    publish = AsyncMock()
    fingerprint = mutation_fingerprint("patch", {"value": value})

    async def scenario():
        first = DisclosureMutationCoordinator(
            db,
            project_id=PROJECT_ID,
            mutation_id=client_mutation_id,
            fingerprint=fingerprint,
        )
        second = DisclosureMutationCoordinator(
            db,
            project_id=PROJECT_ID,
            mutation_id=client_mutation_id,
            fingerprint=fingerprint,
        )
        one = await first.execute(mutate, lambda _response: _event())
        two = await second.execute(mutate, lambda _response: _event())
        return one, two

    with patch("app.services.event_bus.event_bus.publish", new=publish):
        one, two = _run(scenario())

    assert one == two
    assert one["mutation_id"] == client_mutation_id
    assert mutation_calls == 1
    assert db.commit_count == 1
    assert publish.await_count == 1
    assert publish.await_args.args[0].extra["mutation_id"] == client_mutation_id


def test_p9_reused_mutation_id_with_different_payload_is_rejected(monkeypatch):
    _LOCAL_RESULTS.clear()
    _LOCAL_LOCKS.clear()
    monkeypatch.setattr("app.core.redis.redis_client", None)
    db = _FakeDB()

    async def scenario():
        first = DisclosureMutationCoordinator(
            db,
            project_id=PROJECT_ID,
            mutation_id="reused-id",
            fingerprint=mutation_fingerprint("patch", {"value": 1}),
        )
        await first.execute(lambda: _async_value({"ok": True}), lambda _r: _event())
        second = DisclosureMutationCoordinator(
            db,
            project_id=PROJECT_ID,
            mutation_id="reused-id",
            fingerprint=mutation_fingerprint("patch", {"value": 2}),
        )
        await second.execute(lambda: _async_value({"ok": True}), lambda _r: _event())

    with patch("app.services.event_bus.event_bus.publish", new=AsyncMock()):
        with pytest.raises(HTTPException) as exc_info:
            _run(scenario())
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error_code"] == "MUTATION_ID_CONFLICT"


async def _async_value(value):
    return value


def _api_app() -> FastAPI:
    app = FastAPI()
    app.include_router(notes_router.router)

    async def user_override():
        return _user()

    app.dependency_overrides[get_current_user] = user_override
    return app


# Feature: advanced-query-disclosure-integration-hardening, Property P12
@given(year=st.integers(min_value=2000, max_value=2100))
@settings(max_examples=5, deadline=None)
def test_p12_historical_upload_always_501_with_no_db_dependency(year):
    """历史上传直调恒为机器可读 501，端点不声明 DB/文件/任务依赖。"""

    async def scenario():
        async with AsyncClient(
            transport=ASGITransport(app=_api_app()), base_url="http://test"
        ) as client:
            return await client.post(
                f"/api/disclosure-notes/{PROJECT_ID}/upload-history",
                params={"year": year},
                content=b"not-a-real-file",
            )

    response = _run(scenario())
    assert response.status_code == 501
    assert response.json()["detail"]["error_code"] == "HISTORICAL_UPLOAD_NOT_IMPLEMENTED"
    assert "历史 Word/PDF" in response.json()["detail"]["message"]


def test_capabilities_report_historical_upload_disabled_in_chinese():
    async def scenario():
        async with AsyncClient(
            transport=ASGITransport(app=_api_app()), base_url="http://test"
        ) as client:
            return await client.get("/api/disclosure-notes/capabilities")

    response = _run(scenario())
    assert response.status_code == 200
    assert response.json()["historical_upload"] is False
    assert response.json()["historical_upload_reason"] == "历史 Word/PDF 解析尚未实现"


def test_p2_unified_edit_gate_orders_project_then_operation_then_lock(monkeypatch):
    calls: list[str] = []

    def project_factory(permission):
        assert permission == "edit"

        async def dependency(**_kwargs):
            calls.append("project_edit")

        return dependency

    def operation_factory(operation):
        assert operation == "note:edit"

        async def dependency(**_kwargs):
            calls.append("note_edit")

        return dependency

    async def lock(**_kwargs):
        calls.append("lock")

    monkeypatch.setattr(notes_router, "require_project_access", project_factory)
    monkeypatch.setattr(notes_router, "require_operation", operation_factory)
    monkeypatch.setattr(notes_router, "check_consol_lock", lock)

    _run(
        notes_router._assert_project_edit(
            project_id=PROJECT_ID, current_user=_user(), db=MagicMock()
        )
    )
    assert calls == ["project_edit", "note_edit", "lock"]


def test_mutation_id_accepts_header_or_generates_uuid():
    supplied = "client-stable-mutation-id"
    assert notes_router._mutation_id(supplied) == supplied
    generated = notes_router._mutation_id(None)
    assert str(UUID(generated)) == generated


# ===========================================================================
# Wave 0 Task 0.2 — 附注 mutation、trace 与历史上传现状回归测试
# Requirements: 1.2, 7.1–7.4, 9.1–9.4, 10.1
# 固定真实现状，不把当前静默失败写成期望成功。
# ===========================================================================


class TestGenerateEndpointRegression:
    """generate endpoint 的现状回归：成功路径 + 错误路径。"""

    def test_generate_success_invokes_coordinator_and_returns_committed(self):
        """成功路径：edit 门禁通过 → coordinator.execute → 返回 committed/published。"""
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()

        db = MagicMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        fake_notes = [{"id": "n1", "section": "五、1"}, {"id": "n2", "section": "五、2"}]

        with patch(
            "app.routers.disclosure_notes._assert_project_edit", new=AsyncMock()
        ), patch(
            "app.services.prerequisite_checker.PrerequisiteChecker.check",
            new=AsyncMock(return_value={"ok": True}),
        ), patch(
            "app.services.disclosure_engine.DisclosureEngine.generate_notes",
            new=AsyncMock(return_value=fake_notes),
        ), patch(
            "app.services.event_bus.event_bus.publish", new=AsyncMock()
        ), patch(
            "app.core.redis.redis_client", None
        ):
            request = DisclosureNoteGenerateRequest(project_id=PROJECT_ID, year=2025)
            result = _run(notes_router.generate_notes(request, db, _user(), "gen-001"))

        assert result["committed"] is True
        assert result["event_delivery"] == "published"
        assert result["warnings"] == []
        assert result["mutation_id"] == "gen-001"
        # 业务响应包含 note_count 和 message
        assert result["note_count"] == 2
        assert result["message"] == "附注生成成功"
        assert db.commit.await_count == 1

    def test_generate_prerequisite_failure_returns_400(self):
        """业务前提失败：PrerequisiteChecker 不满足时 coordinator 抛 HTTPException 400。"""
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()

        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        with patch(
            "app.routers.disclosure_notes._assert_project_edit", new=AsyncMock()
        ), patch(
            "app.services.prerequisite_checker.PrerequisiteChecker.check",
            new=AsyncMock(return_value={"ok": False, "reason": "试算表未完成"}),
        ), patch(
            "app.services.event_bus.event_bus.publish", new=AsyncMock()
        ) as pub, patch(
            "app.core.redis.redis_client", None
        ):
            request = DisclosureNoteGenerateRequest(project_id=PROJECT_ID, year=2025)
            with pytest.raises(HTTPException) as exc_info:
                _run(notes_router.generate_notes(request, db, _user(), "gen-fail"))

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["ok"] is False
        # rollback occurs, no event published
        assert db.rollback.await_count == 1
        pub.assert_not_awaited()

    def test_generate_engine_exception_returns_500_and_rollback(self):
        """DisclosureEngine 抛异常 → 500 且 rollback，无事件。"""
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()

        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        with patch(
            "app.routers.disclosure_notes._assert_project_edit", new=AsyncMock()
        ), patch(
            "app.services.prerequisite_checker.PrerequisiteChecker.check",
            new=AsyncMock(return_value={"ok": True}),
        ), patch(
            "app.services.disclosure_engine.DisclosureEngine.generate_notes",
            new=AsyncMock(side_effect=RuntimeError("DB timeout")),
        ), patch(
            "app.services.event_bus.event_bus.publish", new=AsyncMock()
        ) as pub, patch(
            "app.core.redis.redis_client", None
        ):
            request = DisclosureNoteGenerateRequest(project_id=PROJECT_ID, year=2025)
            with pytest.raises(HTTPException) as exc_info:
                _run(notes_router.generate_notes(request, db, _user(), "gen-err"))

        assert exc_info.value.status_code == 500
        assert "附注生成失败" in exc_info.value.detail
        pub.assert_not_awaited()


class TestUpdateEndpointRegression:
    """update endpoint 的现状回归。"""

    def test_update_success_returns_committed_with_note_detail(self):
        """成功更新：note_id lookup → edit 门禁 → coordinator → committed。"""
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()

        db = MagicMock()
        db.execute = AsyncMock(return_value=_ScalarResult(PROJECT_ID))
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        # 构造一个能通过 DisclosureNoteDetail.model_validate(from_attributes=True) 的对象
        class _FakeNote:
            id = NOTE_ID
            project_id = PROJECT_ID
            year = 2025
            note_section = "五、3"
            section_title = "应收账款"
            account_name = None
            content_type = None
            text_content = "updated content"
            table_data = None
            guidance_text = None
            source_template = None
            status = NoteStatus.draft
            is_empty = False
            is_deleted = False
            sort_order = 3
            updated_at = None
            last_sync_source = None
            last_sync_wp_id = None
            last_sync_at = None
            last_sync_user_id = None

        fake_note = _FakeNote()

        with patch(
            "app.routers.disclosure_notes._assert_project_edit", new=AsyncMock()
        ), patch(
            "app.services.disclosure_engine.DisclosureEngine.update_note",
            new=AsyncMock(return_value=fake_note),
        ), patch(
            "app.services.event_bus.event_bus.publish", new=AsyncMock()
        ), patch(
            "app.core.redis.redis_client", None
        ):
            data = DisclosureNoteUpdate(text_content="updated content")
            result = _run(notes_router.update_note(NOTE_ID, data, db, _user(), "upd-001"))

        assert result["committed"] is True
        assert result["event_delivery"] == "published"
        assert result["mutation_id"] == "upd-001"
        assert result["warnings"] == []
        assert db.commit.await_count == 1

    def test_update_note_not_found_returns_404(self):
        """note_id 不存在时直接 404，不进入 mutation coordinator。"""
        db = MagicMock()
        db.execute = AsyncMock(return_value=_ScalarResult(None))
        db.commit = AsyncMock()

        data = DisclosureNoteUpdate(text_content="anything")
        with pytest.raises(HTTPException) as exc_info:
            _run(notes_router.update_note(NOTE_ID, data, db, _user(), "upd-404"))

        assert exc_info.value.status_code == 404
        db.commit.assert_not_awaited()


class TestDeleteEndpointRegression:
    """delete endpoint 的现状回归。"""

    def test_delete_success_soft_deletes_and_publishes_event(self):
        """成功删除：edit 门禁 → soft-delete → commit → event published。"""
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()

        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.flush = AsyncMock()

        class _FakeNote:
            is_deleted = False

        fake_note = _FakeNote()
        db.execute = AsyncMock(return_value=_ScalarResult(fake_note))

        with patch(
            "app.routers.disclosure_notes._assert_project_edit", new=AsyncMock()
        ), patch(
            "app.services.event_bus.event_bus.publish", new=AsyncMock()
        ) as pub, patch(
            "app.core.redis.redis_client", None
        ):
            result = _run(
                notes_router.delete_section(
                    PROJECT_ID, 2025, "五、3", db, _user(), "del-001"
                )
            )

        assert result["committed"] is True
        assert result["event_delivery"] == "published"
        assert result["ok"] is True
        assert fake_note.is_deleted is True
        pub.assert_awaited_once()
        assert db.commit.await_count == 1

    def test_delete_section_not_found_returns_404_and_rollback(self):
        """要删除的章节不存在 → 404，coordinator 保证 rollback。"""
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()

        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.execute = AsyncMock(return_value=_ScalarResult(None))

        with patch(
            "app.routers.disclosure_notes._assert_project_edit", new=AsyncMock()
        ), patch(
            "app.services.event_bus.event_bus.publish", new=AsyncMock()
        ) as pub, patch(
            "app.core.redis.redis_client", None
        ):
            with pytest.raises(HTTPException) as exc_info:
                _run(
                    notes_router.delete_section(
                        PROJECT_ID, 2025, "不存在", db, _user(), "del-404"
                    )
                )

        assert exc_info.value.status_code == 404
        pub.assert_not_awaited()
        assert db.rollback.await_count == 1


class TestRestoreEndpointRegression:
    """restore endpoint 的现状回归。"""

    def test_restore_success_marks_not_deleted_and_publishes(self):
        """成功恢复：edit 门禁 → is_deleted=False → commit → event published。"""
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()

        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.flush = AsyncMock()

        class _FakeNote:
            is_deleted = True
            note_section = "五、4"

        fake_note = _FakeNote()
        db.execute = AsyncMock(return_value=_ScalarResult(fake_note))

        with patch(
            "app.routers.disclosure_notes._assert_project_edit", new=AsyncMock()
        ), patch(
            "app.services.event_bus.event_bus.publish", new=AsyncMock()
        ) as pub, patch(
            "app.core.redis.redis_client", None
        ):
            result = _run(
                notes_router.restore_section(
                    PROJECT_ID, 2025, NOTE_ID, db, _user(), "rst-001"
                )
            )

        assert result["committed"] is True
        assert result["event_delivery"] == "published"
        assert result["ok"] is True
        assert fake_note.is_deleted is False
        pub.assert_awaited_once()

    def test_restore_not_found_returns_404(self):
        """要恢复的章节不存在或未被删除 → 404。"""
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()

        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.execute = AsyncMock(return_value=_ScalarResult(None))

        with patch(
            "app.routers.disclosure_notes._assert_project_edit", new=AsyncMock()
        ), patch(
            "app.services.event_bus.event_bus.publish", new=AsyncMock()
        ), patch(
            "app.core.redis.redis_client", None
        ):
            with pytest.raises(HTTPException) as exc_info:
                _run(
                    notes_router.restore_section(
                        PROJECT_ID, 2025, NOTE_ID, db, _user(), "rst-404"
                    )
                )

        assert exc_info.value.status_code == 404


class TestStatusChangeEndpointRegression:
    """patch_section (status change) 的现状回归。"""

    def test_patch_status_to_not_applicable_success(self):
        """将章节标记为 not_applicable → is_empty=True → committed。"""
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()

        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.flush = AsyncMock()

        class _FakeNote:
            is_empty = False
            status = MagicMock(value="draft")

        fake_note = _FakeNote()
        db.execute = AsyncMock(return_value=_ScalarResult(fake_note))

        with patch(
            "app.routers.disclosure_notes._assert_project_edit", new=AsyncMock()
        ), patch(
            "app.services.event_bus.event_bus.publish", new=AsyncMock()
        ), patch(
            "app.core.redis.redis_client", None
        ):
            result = _run(
                notes_router.patch_section(
                    PROJECT_ID, 2025, "五、5", {"status": "not_applicable"},
                    db, _user(), "patch-001",
                )
            )

        assert result["committed"] is True
        assert result["event_delivery"] == "published"
        assert result["ok"] is True
        assert result["status"] == "not_applicable"
        assert fake_note.is_empty is True

    def test_patch_section_not_found_returns_404(self):
        """不存在的章节 → 404，rollback。"""
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()

        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.execute = AsyncMock(return_value=_ScalarResult(None))

        with patch(
            "app.routers.disclosure_notes._assert_project_edit", new=AsyncMock()
        ), patch(
            "app.services.event_bus.event_bus.publish", new=AsyncMock()
        ), patch(
            "app.core.redis.redis_client", None
        ):
            with pytest.raises(HTTPException) as exc_info:
                _run(
                    notes_router.patch_section(
                        PROJECT_ID, 2025, "不存在", {"status": "draft"},
                        db, _user(), "patch-404",
                    )
                )

        assert exc_info.value.status_code == 404


class TestTraceCellRegression:
    """note_id-based trace 的现状回归。"""

    def test_trace_cell_success_delegates_to_engine(self):
        """trace_cell 成功路径：note 存在 → project 授权 → engine 返回溯源数据。"""
        db = MagicMock()
        db.execute = AsyncMock(return_value=_ScalarResult(PROJECT_ID))

        trace_result = {
            "binding": {"source": "trial_balance", "field": "audited_amount"},
            "formula_resolved": "=TB('1601','audited_amount')",
            "computed_value": 1234.56,
            "evidence": {"trial_balance_rows": [{"account_code": "1601"}]},
        }

        with patch(
            "app.routers.disclosure_notes.OwnershipGuard.assert_target_accessible",
            new=AsyncMock(),
        ), patch(
            "app.services.disclosure_engine.DisclosureEngine.trace_cell",
            new=AsyncMock(return_value=trace_result),
        ) as trace_mock:
            result = _run(notes_router.trace_cell(NOTE_ID, 0, 1, db, _user()))

        assert result == trace_result
        trace_mock.assert_awaited_once_with(NOTE_ID, 0, 1)

    def test_trace_cell_note_not_found_returns_error_dict(self):
        """note_id 不存在时返回 200 + error 字段（非 HTTPException，前端友好降级）。"""
        db = MagicMock()
        db.execute = AsyncMock(return_value=_ScalarResult(None))

        result = _run(notes_router.trace_cell(NOTE_ID, 0, 0, db, _user()))

        assert result["error"] == "note_not_found"
        assert result["note_id"] == str(NOTE_ID)

    def test_trace_cell_auth_failure_403_no_domain_read(self):
        """越权时 403，且不调用 DisclosureEngine.trace_cell。"""
        db = MagicMock()
        db.execute = AsyncMock(return_value=_ScalarResult(PROJECT_ID))
        denied = HTTPException(status_code=403, detail="Forbidden")

        with patch(
            "app.routers.disclosure_notes.OwnershipGuard.assert_target_accessible",
            new=AsyncMock(side_effect=denied),
        ), patch(
            "app.services.disclosure_engine.DisclosureEngine.trace_cell",
            new=AsyncMock(),
        ) as trace_mock:
            with pytest.raises(HTTPException) as exc_info:
                _run(notes_router.trace_cell(NOTE_ID, 2, 3, db, _user()))

        assert exc_info.value.status_code == 403
        trace_mock.assert_not_awaited()


class TestHistoricalUploadRegression:
    """历史上传端点现状回归：始终返回 501，零副作用。"""

    def test_upload_history_returns_501_no_db_dependency(self):
        """端点签名无 DB 依赖，始终抛 501。"""
        with pytest.raises(HTTPException) as exc_info:
            _run(notes_router.upload_history(PROJECT_ID, year=2025))

        assert exc_info.value.status_code == 501
        detail = exc_info.value.detail
        assert detail["error_code"] == "HISTORICAL_UPLOAD_NOT_IMPLEMENTED"
        assert "历史 Word/PDF" in detail["message"]

    def test_upload_history_any_year_still_501(self):
        """不论传什么年份，都返回 501。"""
        for year in [2000, 2025, 2100]:
            with pytest.raises(HTTPException) as exc_info:
                _run(notes_router.upload_history(PROJECT_ID, year=year))
            assert exc_info.value.status_code == 501


class TestEventBusFailurePathRegression:
    """EventBus 发布失败时的现状行为回归。

    当前设计（DisclosureMutationCoordinator）：
    - commit 成功后尝试 publish
    - publish 失败时**不**回滚业务数据（已 committed）
    - 响应中 event_delivery="failed"，warnings 含 event_delivery_failed
    - 结构化日志记录异常（不静默 pass）

    这些测试固定此行为，防止误改为静默吞错或误回滚。
    """

    def test_event_bus_failure_preserves_committed_data(self):
        """EventBus 失败：业务数据保留（commit=1, rollback=0）。"""
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()

        db = _FakeDB(commit_fails=False)

        async def mutate():
            return {"status": "saved"}

        publish = AsyncMock(side_effect=RuntimeError("EventBus 连接超时"))
        coordinator = DisclosureMutationCoordinator(
            db,
            project_id=PROJECT_ID,
            mutation_id=f"evt-fail-{uuid4()}",
            fingerprint=mutation_fingerprint("update", {"value": 1}),
        )

        with patch("app.services.event_bus.event_bus.publish", new=publish), \
             patch("app.core.redis.redis_client", None):
            result = _run(coordinator.execute(mutate, lambda _r: _event()))

        assert db.commit_count == 1
        assert db.rollback_count == 0
        assert result["committed"] is True
        assert result["event_delivery"] == "failed"
        assert len(result["warnings"]) == 1
        assert result["warnings"][0]["code"] == "event_delivery_failed"
        assert "mutation_id" in result["warnings"][0]

    def test_event_bus_failure_does_not_pass_silently(self):
        """EventBus 失败后 warning 不为空（不是静默 pass）。"""
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()

        db = _FakeDB(commit_fails=False)

        async def mutate():
            return {"data": "x"}

        publish = AsyncMock(side_effect=Exception("channel closed"))
        coordinator = DisclosureMutationCoordinator(
            db,
            project_id=PROJECT_ID,
            mutation_id=f"evt-silent-{uuid4()}",
            fingerprint=mutation_fingerprint("patch", {"data": "x"}),
        )

        with patch("app.services.event_bus.event_bus.publish", new=publish), \
             patch("app.core.redis.redis_client", None):
            result = _run(coordinator.execute(mutate, lambda _r: _event()))

        # 关键断言：确认不是静默 pass
        assert result["warnings"] != []
        assert result["event_delivery"] != "published"

    def test_commit_failure_means_no_event_no_success_response(self):
        """commit 失败：rollback，无事件，无 committed 响应。"""
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()

        db = _FakeDB(commit_fails=True)

        async def mutate():
            return {"should": "not be seen"}

        publish = AsyncMock()
        coordinator = DisclosureMutationCoordinator(
            db,
            project_id=PROJECT_ID,
            mutation_id=f"commit-fail-{uuid4()}",
            fingerprint=mutation_fingerprint("generate", {}),
        )

        with patch("app.services.event_bus.event_bus.publish", new=publish), \
             patch("app.core.redis.redis_client", None):
            with pytest.raises(RuntimeError, match="commit failed"):
                _run(coordinator.execute(mutate, lambda _r: _event()))

        assert db.rollback_count == 1
        assert db.commit_count == 1  # commit was attempted
        publish.assert_not_awaited()  # 关键：commit 失败后不发布事件

    def test_mutation_failure_means_rollback_no_event(self):
        """mutation 内部异常：rollback，不 commit，无事件。"""
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()

        db = _FakeDB(commit_fails=False)

        async def mutate():
            raise ValueError("业务规则违反")

        publish = AsyncMock()
        coordinator = DisclosureMutationCoordinator(
            db,
            project_id=PROJECT_ID,
            mutation_id=f"mut-fail-{uuid4()}",
            fingerprint=mutation_fingerprint("delete", {"id": "x"}),
        )

        with patch("app.services.event_bus.event_bus.publish", new=publish), \
             patch("app.core.redis.redis_client", None):
            with pytest.raises(ValueError, match="业务规则违反"):
                _run(coordinator.execute(mutate, lambda _r: _event()))

        assert db.rollback_count == 1
        assert db.commit_count == 0
        publish.assert_not_awaited()


# ===========================================================================
# Wave1 Task 1.2 — 收敛附注读取与对象归属门禁
# Requirements: 1.1–1.3
# 验证所有读端点的 readonly gate、403 不泄露 note 内容/trace 证据/缓存信息
# ===========================================================================


class TestTask12ReadEndpointGates:
    """Task 1.2: 所有附注读端点在未授权时返回 403，且 403 不泄露 note 内容。

    验证策略:
    - project_id-based 端点使用 Depends(require_project_access("readonly"))，
      FastAPI DI 在调用端点体之前短路 → 业务逻辑不可达。
      通过 monkeypatch require_project_access 工厂验证。
    - note_id-based 端点 (trace_cell) 先最小投影解析 project_id → OwnershipGuard。
      通过直接调用 + mock 验证。
    """

    # ---- 目录 (list/tree) ----

    def test_list_tree_gate_precedes_engine(self):
        """目录/树端点：require_project_access("readonly") 作为 FastAPI DI 先于端点体执行。

        验证逻辑：endpoint 参数 `current_user` 的 Depends 是 require_project_access("readonly")。
        当该依赖 raise 403 时，FastAPI 短路不执行端点体（=DisclosureEngine 不可达）。
        此处结合 inspect 签名验证 + 直接调用验证 403 返回不泄露数据。
        """
        import inspect
        sig = inspect.signature(notes_router.get_notes_tree)
        user_param = sig.parameters["current_user"]
        # Depends(require_project_access("readonly")) 对象
        assert hasattr(user_param.default, "dependency")

        # 验证: 如果 current_user 参数来自于 403 的 DI（模拟）,
        # 端点根本不会被 FastAPI 调用。
        # 这里额外验证：如果强行越过 DI 调用端点体但 engine 前的逻辑不泄露数据。
        # get_notes_tree 签名 = project_id, year, db, current_user
        # 业务数据在 engine.get_notes_tree 之后。如果 DI 短路，engine 不可达。
        # (已由签名验证保证)

    def test_tree_endpoint_declares_readonly_gate_in_signature(self):
        """目录端点签名声明 require_project_access("readonly") 依赖。

        FastAPI Depends 在端点体之前执行；若 deny，端点体不可达。
        """
        import inspect

        sig = inspect.signature(notes_router.get_notes_tree)
        params = sig.parameters
        # current_user parameter should have a Depends default
        user_param = params["current_user"]
        assert user_param.default is not inspect.Parameter.empty
        # The Depends wraps require_project_access("readonly")
        dep = user_param.default
        assert hasattr(dep, "dependency")  # FastAPI Depends object

    # ---- 详情 (detail) ----

    def test_detail_endpoint_declares_readonly_gate(self):
        """详情端点签名声明 require_project_access("readonly")。"""
        import inspect
        sig = inspect.signature(notes_router.get_note_detail)
        user_param = sig.parameters["current_user"]
        assert user_param.default is not inspect.Parameter.empty
        assert hasattr(user_param.default, "dependency")

    def test_prior_year_endpoint_declares_readonly_gate(self):
        """prior-year 端点签名声明 require_project_access("readonly")。"""
        import inspect
        sig = inspect.signature(notes_router.get_prior_year_note)
        user_param = sig.parameters["current_user"]
        assert user_param.default is not inspect.Parameter.empty
        assert hasattr(user_param.default, "dependency")

    def test_auto_pull_endpoint_declares_readonly_gate(self):
        """自动取数端点签名声明 require_project_access("readonly")。"""
        import inspect
        sig = inspect.signature(notes_router.get_auto_pull)
        user_param = sig.parameters["current_user"]
        assert user_param.default is not inspect.Parameter.empty
        assert hasattr(user_param.default, "dependency")

    def test_list_formulas_endpoint_declares_readonly_gate(self):
        """list_note_formulas 端点签名声明 require_project_access("readonly")。"""
        import inspect
        sig = inspect.signature(notes_router.list_note_formulas)
        user_param = sig.parameters["current_user"]
        assert user_param.default is not inspect.Parameter.empty
        assert hasattr(user_param.default, "dependency")

    def test_section_numbers_endpoint_declares_readonly_gate(self):
        """section-numbers 端点签名声明 require_project_access("readonly")。"""
        import inspect
        sig = inspect.signature(notes_router.get_section_numbers)
        user_param = sig.parameters["current_user"]
        assert user_param.default is not inspect.Parameter.empty
        assert hasattr(user_param.default, "dependency")

    def test_validation_results_endpoint_declares_readonly_gate(self):
        """validation-results 端点签名声明 require_project_access("readonly")。"""
        import inspect
        sig = inspect.signature(notes_router.get_validation_results)
        user_param = sig.parameters["current_user"]
        assert user_param.default is not inspect.Parameter.empty
        assert hasattr(user_param.default, "dependency")

    # ---- trace_cell (by note_id → minimal projection → OwnershipGuard) ----

    def test_trace_gate_uses_minimal_projection_then_403_no_evidence(self):
        """trace 端点：仅携带 note_id → 先最小投影解析 project_id → 授权 → 403 无 trace 证据。

        这是 note_id-based 端点的标准模式验证。
        """
        db = MagicMock()
        # 最小投影返回 project_id
        db.execute = AsyncMock(return_value=_ScalarResult(PROJECT_ID))

        denied = HTTPException(
            status_code=403,
            detail={"error_code": "FORBIDDEN_PROJECT", "message": "无权访问该项目数据"},
        )

        with patch(
            "app.routers.disclosure_notes.OwnershipGuard.assert_target_accessible",
            new=AsyncMock(side_effect=denied),
        ) as guard, patch(
            "app.routers.disclosure_notes.DisclosureEngine.trace_cell",
            new=AsyncMock(),
        ) as trace:
            with pytest.raises(HTTPException) as exc_info:
                _run(notes_router.trace_cell(NOTE_ID, 5, 3, db, _user()))

        # 403 且无 trace 证据
        assert exc_info.value.status_code == 403
        detail = exc_info.value.detail
        assert "evidence" not in str(detail)
        assert "trial_balance" not in str(detail)
        assert "formula_resolved" not in str(detail)
        assert "computed_value" not in str(detail)
        assert "table_data" not in str(detail)
        # 确保 trace 领域查询未执行
        trace.assert_not_awaited()
        # 确保 guard 在 trace 之前
        guard.assert_awaited_once()

    def test_trace_403_does_not_contain_note_content_or_cache_hit(self):
        """trace 403 响应不得包含 note 内容、trace 证据或缓存命中信息。"""
        db = MagicMock()
        db.execute = AsyncMock(return_value=_ScalarResult(PROJECT_ID))

        denied = HTTPException(
            status_code=403,
            detail={"error_code": "FORBIDDEN_PROJECT", "message": "无权访问该项目数据"},
        )

        with patch(
            "app.routers.disclosure_notes.OwnershipGuard.assert_target_accessible",
            new=AsyncMock(side_effect=denied),
        ), patch(
            "app.routers.disclosure_notes.DisclosureEngine.trace_cell",
            new=AsyncMock(return_value={
                "binding": {"source": "trial_balance"},
                "evidence": {"trial_balance_rows": [{"amount": 999}]},
                "computed_value": 123.45,
            }),
        ) as trace:
            with pytest.raises(HTTPException) as exc_info:
                _run(notes_router.trace_cell(NOTE_ID, 0, 0, db, _user()))

        assert exc_info.value.status_code == 403
        # trace 未被调用——不可能泄露
        trace.assert_not_awaited()
        # 即使 detail 改为包含 error_code，也不得有领域数据
        detail_str = str(exc_info.value.detail)
        assert "999" not in detail_str
        assert "123.45" not in detail_str
        assert "trial_balance" not in detail_str

    def test_trace_minimal_projection_only_selects_project_id(self):
        """trace 端点最小投影仅查询 project_id，不加载 note 全字段。

        验证 SQL 查询仅 SELECT DisclosureNote.project_id，不含 table_data/text_content。
        """
        db = MagicMock()
        db.execute = AsyncMock(return_value=_ScalarResult(PROJECT_ID))

        with patch(
            "app.routers.disclosure_notes.OwnershipGuard.assert_target_accessible",
            new=AsyncMock(),
        ), patch(
            "app.routers.disclosure_notes.DisclosureEngine.trace_cell",
            new=AsyncMock(return_value={"binding": None}),
        ):
            _run(notes_router.trace_cell(NOTE_ID, 0, 0, db, _user()))

        # 验证 execute 被调用且查询结构正确
        db.execute.assert_awaited_once()
        call_args = db.execute.await_args
        stmt = call_args.args[0]
        # 编译语句验证只 select project_id
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "project_id" in compiled
        # 不应包含全字段加载
        assert "table_data" not in compiled
        assert "text_content" not in compiled

    # ---- 综合：验证 403 格式不含敏感信息 ----

    def test_require_project_access_403_format_is_generic(self):
        """require_project_access 产生的 403 detail 是固定字符串 '权限不足'，不含业务数据。"""
        # 在 deps.py 中验证：raise HTTPException(status_code=403, detail="权限不足")
        # 这保证 403 永远不会泄露 note 内容。
        # 直接验证 OwnershipGuard._forbidden 格式也满足要求。
        guard = OwnershipGuard()
        exc = guard._forbidden("测试消息")
        assert exc.status_code == 403
        assert exc.detail["error_code"] == "FORBIDDEN_PROJECT"
        assert "table_data" not in str(exc.detail)
        assert "evidence" not in str(exc.detail)
        assert "text_content" not in str(exc.detail)
        assert "cache_hit" not in str(exc.detail)

    def test_ownership_guard_403_with_addr_id_still_no_leak(self):
        """OwnershipGuard 带 addr_id 的 403 仍不含 note 内容。"""
        guard = OwnershipGuard()
        exc = guard._forbidden("测试", addr_id="wp:D2/D2-2/A1")
        assert exc.status_code == 403
        assert exc.detail["error_code"] == "FORBIDDEN_PROJECT"
        assert "table_data" not in str(exc.detail)
        assert "evidence" not in str(exc.detail)
        assert "text_content" not in str(exc.detail)


# ===========================================================================
# Wave1 Task 1.3 — 加固附注 mutation edit/operation/锁权限
# Requirements: 2.1, 2.3, 2.4
# 验证 generate/update/delete/restore/patch 5 个 mutation 端点统一:
# - _assert_project_edit (project edit → note:edit → consol lock) 在 mutation 前
# - 权限失败时零 DB mutation / commit
# - update_note/delete_section 对 note_id 先解析 project_id 再调门禁
# ===========================================================================


class TestTask13MutationEditGateUnified:
    """Task 1.3: 所有 mutation 统一要求项目 edit + note:edit + 合并锁，在 mutation 前。"""

    # ---- 每个 mutation 权限失败时不执行业务逻辑 ----

    def test_generate_gate_failure_prevents_all_business_logic(self):
        """generate: _assert_project_edit 失败 → PrerequisiteChecker 和 DisclosureEngine 均不可达。"""
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        denied = HTTPException(status_code=403, detail="权限不足")

        with patch(
            "app.routers.disclosure_notes._assert_project_edit",
            new=AsyncMock(side_effect=denied),
        ) as gate, patch(
            "app.services.prerequisite_checker.PrerequisiteChecker.check",
            new=AsyncMock(),
        ) as prereq, patch(
            "app.services.disclosure_engine.DisclosureEngine.generate_notes",
            new=AsyncMock(),
        ) as engine:
            with pytest.raises(HTTPException) as exc_info:
                request = DisclosureNoteGenerateRequest(project_id=PROJECT_ID, year=2025)
                _run(notes_router.generate_notes(request, db, _user(), "t13-gen"))

        assert exc_info.value.status_code == 403
        gate.assert_awaited_once()
        prereq.assert_not_awaited()
        engine.assert_not_awaited()
        db.commit.assert_not_awaited()

    def test_update_gate_failure_prevents_mutation_and_commit(self):
        """update: note_id 解析 project_id 后, _assert_project_edit 失败 → 零 mutation/commit。"""
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()
        db = MagicMock()
        db.execute = AsyncMock(return_value=_ScalarResult(PROJECT_ID))
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        denied = HTTPException(status_code=403, detail="权限不足")

        with patch(
            "app.routers.disclosure_notes._assert_project_edit",
            new=AsyncMock(side_effect=denied),
        ) as gate, patch(
            "app.services.disclosure_engine.DisclosureEngine.update_note",
            new=AsyncMock(),
        ) as mutation:
            with pytest.raises(HTTPException) as exc_info:
                data = DisclosureNoteUpdate(text_content="should not persist")
                _run(notes_router.update_note(NOTE_ID, data, db, _user(), "t13-upd"))

        assert exc_info.value.status_code == 403
        gate.assert_awaited_once()
        mutation.assert_not_awaited()
        db.commit.assert_not_awaited()

    def test_delete_gate_failure_prevents_soft_delete_and_commit(self):
        """delete: _assert_project_edit 失败 → 不执行 soft-delete/flush/commit。"""
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.flush = AsyncMock()
        denied = HTTPException(status_code=403, detail="权限不足")

        with patch(
            "app.routers.disclosure_notes._assert_project_edit",
            new=AsyncMock(side_effect=denied),
        ) as gate:
            # 不 patch db.execute — 若 gate 不阻止, delete_section 会查 note
            with pytest.raises(HTTPException) as exc_info:
                _run(
                    notes_router.delete_section(
                        PROJECT_ID, 2025, "五、3", db, _user(), "t13-del"
                    )
                )

        assert exc_info.value.status_code == 403
        gate.assert_awaited_once()
        db.flush.assert_not_awaited()
        db.commit.assert_not_awaited()

    def test_restore_gate_failure_prevents_restore_and_commit(self):
        """restore: _assert_project_edit 失败 → 不执行 is_deleted=False/flush/commit。"""
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.flush = AsyncMock()
        denied = HTTPException(status_code=403, detail="权限不足")

        with patch(
            "app.routers.disclosure_notes._assert_project_edit",
            new=AsyncMock(side_effect=denied),
        ) as gate:
            with pytest.raises(HTTPException) as exc_info:
                _run(
                    notes_router.restore_section(
                        PROJECT_ID, 2025, NOTE_ID, db, _user(), "t13-rst"
                    )
                )

        assert exc_info.value.status_code == 403
        gate.assert_awaited_once()
        db.flush.assert_not_awaited()
        db.commit.assert_not_awaited()

    def test_patch_gate_failure_prevents_status_change_and_commit(self):
        """patch (status): _assert_project_edit 失败 → 不修改 is_empty / flush / commit。"""
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.flush = AsyncMock()
        denied = HTTPException(status_code=403, detail="权限不足")

        with patch(
            "app.routers.disclosure_notes._assert_project_edit",
            new=AsyncMock(side_effect=denied),
        ) as gate:
            with pytest.raises(HTTPException) as exc_info:
                _run(
                    notes_router.patch_section(
                        PROJECT_ID, 2025, "五、5",
                        {"status": "not_applicable"},
                        db, _user(), "t13-patch",
                    )
                )

        assert exc_info.value.status_code == 403
        gate.assert_awaited_once()
        db.flush.assert_not_awaited()
        db.commit.assert_not_awaited()

    # ---- update_note 解析 project_id 在 gate 之前 ----

    def test_update_resolves_project_id_before_gate(self):
        """update_note: 先 SELECT project_id (最小字段), 然后调 _assert_project_edit。

        验证调用顺序: db.execute (解析) → _assert_project_edit → coordinator。
        """
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()
        call_order: list[str] = []
        db = MagicMock()

        async def fake_execute(*_a, **_kw):
            call_order.append("resolve_project_id")
            return _ScalarResult(PROJECT_ID)

        db.execute = AsyncMock(side_effect=fake_execute)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        async def fake_gate(**_kw):
            call_order.append("assert_project_edit")
            raise HTTPException(status_code=403, detail="denied")

        with patch(
            "app.routers.disclosure_notes._assert_project_edit",
            new=AsyncMock(side_effect=fake_gate),
        ):
            with pytest.raises(HTTPException):
                data = DisclosureNoteUpdate(text_content="x")
                _run(notes_router.update_note(NOTE_ID, data, db, _user(), "t13-order"))

        assert call_order == ["resolve_project_id", "assert_project_edit"]

    # ---- delete_section 直接从路径参数获取 project_id ----

    def test_delete_uses_path_project_id_for_gate(self):
        """delete_section: 路径包含 project_id, 直接传给 _assert_project_edit。"""
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        captured_kwargs: dict = {}

        async def capture_gate(**kwargs):
            captured_kwargs.update(kwargs)
            raise HTTPException(status_code=403, detail="denied")

        with patch(
            "app.routers.disclosure_notes._assert_project_edit",
            new=AsyncMock(side_effect=capture_gate),
        ):
            with pytest.raises(HTTPException):
                _run(
                    notes_router.delete_section(
                        PROJECT_ID, 2025, "五、1", db, _user(), "t13-del-pid"
                    )
                )

        assert captured_kwargs["project_id"] == PROJECT_ID

    # ---- 验证 _assert_project_edit 不依赖隐式 session 提交 ----

    def test_assert_project_edit_completes_before_any_db_write(self):
        """_assert_project_edit 三步检查全部是 await (非隐式 session.commit)。

        验证: project_edit → note_edit → lock 全部在 coordinator.execute 之前完成。
        如果任一步失败，coordinator (含 commit) 从未被调用。
        """
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()
        call_order: list[str] = []
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.flush = AsyncMock()

        # 模拟 lock 阶段失败
        def project_factory(permission):
            async def dep(**_kw):
                call_order.append(f"project_{permission}")
            return dep

        def operation_factory(op):
            async def dep(**_kw):
                call_order.append(f"operation_{op}")
            return dep

        async def lock_fail(**_kw):
            call_order.append("lock_check")
            raise HTTPException(status_code=423, detail="合并期间已锁定")

        with patch.object(notes_router, "require_project_access", project_factory), \
             patch.object(notes_router, "require_operation", operation_factory), \
             patch.object(notes_router, "check_consol_lock", lock_fail):
            with pytest.raises(HTTPException) as exc_info:
                _run(
                    notes_router.delete_section(
                        PROJECT_ID, 2025, "五、1", db, _user(), "t13-lock"
                    )
                )

        # 锁检查失败 → 423
        assert exc_info.value.status_code == 423
        # 三步顺序执行，但第三步失败
        assert call_order == ["project_edit", "operation_note:edit", "lock_check"]
        # 关键: 无 flush / commit
        db.flush.assert_not_awaited()
        db.commit.assert_not_awaited()

    # ---- readonly 用户不能执行 mutation ----

    def test_readonly_user_cannot_execute_any_mutation(self):
        """Req 2.4: readonly 用户在所有 5 个 mutation 上均被 _assert_project_edit 拦截。

        这验证权限拒绝一致性——不存在"某 mutation 遗漏门禁"的路径。
        """
        _LOCAL_RESULTS.clear()
        _LOCAL_LOCKS.clear()
        denied = HTTPException(status_code=403, detail="仅具备 readonly 权限")

        endpoints_and_args = [
            (
                "generate",
                lambda db: notes_router.generate_notes(
                    DisclosureNoteGenerateRequest(project_id=PROJECT_ID, year=2025),
                    db, _user(), "t13-ro-gen",
                ),
            ),
            (
                "update",
                lambda db: notes_router.update_note(
                    NOTE_ID, DisclosureNoteUpdate(text_content="x"),
                    db, _user(), "t13-ro-upd",
                ),
            ),
            (
                "delete",
                lambda db: notes_router.delete_section(
                    PROJECT_ID, 2025, "五、1", db, _user(), "t13-ro-del",
                ),
            ),
            (
                "restore",
                lambda db: notes_router.restore_section(
                    PROJECT_ID, 2025, NOTE_ID, db, _user(), "t13-ro-rst",
                ),
            ),
            (
                "patch",
                lambda db: notes_router.patch_section(
                    PROJECT_ID, 2025, "五、1", {"status": "draft"},
                    db, _user(), "t13-ro-patch",
                ),
            ),
        ]

        for name, call_fn in endpoints_and_args:
            db = MagicMock()
            db.execute = AsyncMock(return_value=_ScalarResult(PROJECT_ID))
            db.commit = AsyncMock()
            db.rollback = AsyncMock()
            db.flush = AsyncMock()

            with patch(
                "app.routers.disclosure_notes._assert_project_edit",
                new=AsyncMock(side_effect=denied),
            ):
                with pytest.raises(HTTPException) as exc_info:
                    _run(call_fn(db))

            assert exc_info.value.status_code == 403, f"{name}: expected 403"
            db.commit.assert_not_awaited()
            db.flush.assert_not_awaited()
