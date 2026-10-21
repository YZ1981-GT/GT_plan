"""Formula-toolbar Task 3 — WorkpaperCapabilitySnapshot + server matrix."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.workpaper_capability import (
    CAPABILITY_KEYS,
    CapabilityPrincipal,
    assert_snapshot_action_allowed,
    build_capability_snapshot,
    decide_capability,
    denial_leaks_sensitive_metadata,
)


def _principal(**kwargs) -> CapabilityPrincipal:
    base = dict(
        role="assignee",
        user_id="u1",
        project_id="p1",
        wp_id="wp1",
        sheet_uid="s1",
        project_member=True,
        wp_visible=True,
    )
    base.update(kwargs)
    return CapabilityPrincipal(**base)  # type: ignore[arg-type]


def test_matrix_assignee_cannot_batch_ai_review() -> None:
    d = decide_capability(_principal(role="assignee"), "aiReviewBatch")
    assert d.allowed is False
    assert d.reason_code == "role_denied"
    assert d.zh_message and "无权" in d.zh_message
    assert not denial_leaks_sensitive_metadata(d.zh_message)


def test_matrix_admin_allows_all_keys() -> None:
    p = _principal(role="admin")
    for key in CAPABILITY_KEYS:
        assert decide_capability(p, key).allowed is True


def test_not_member_and_invisible_fail_closed() -> None:
    assert decide_capability(_principal(project_member=False), "formulaView").reason_code == (
        "not_project_member"
    )
    assert decide_capability(_principal(wp_visible=False), "guidanceRead").reason_code == (
        "wp_not_visible"
    )


def test_snapshot_covers_all_capability_keys() -> None:
    snap = build_capability_snapshot(_principal(role="lead"), owner_epoch=3)
    assert snap["snapshotVersion"] == "1.0"
    assert snap["ownerEpoch"] == 3
    assert len(snap["subjectDigest"]) == 64
    for key in CAPABILITY_KEYS:
        assert key in snap
        assert "allowed" in snap[key]
        assert "reasonCode" in snap[key]


def test_gate_blocks_uninitialized_expired_and_epoch_mismatch() -> None:
    now = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
    snap = build_capability_snapshot(
        _principal(role="lead"),
        owner_epoch=1,
        now=now,
        ttl_seconds=60,
    )
    assert assert_snapshot_action_allowed(
        snap, "formulaView", owner_epoch=1, now=now
    ).allowed is True

    assert assert_snapshot_action_allowed(
        {}, "formulaView", owner_epoch=1, now=now
    ).reason_code == "snapshot_uninitialized"

    assert assert_snapshot_action_allowed(
        snap, "formulaView", owner_epoch=2, now=now
    ).reason_code == "epoch_mismatch"

    expired_now = now + timedelta(seconds=61)
    assert assert_snapshot_action_allowed(
        snap, "formulaView", owner_epoch=1, now=expired_now
    ).reason_code == "snapshot_expired"


def test_gate_blocks_denied_key_without_hardcoded_true() -> None:
    snap = build_capability_snapshot(_principal(role="readonly"), owner_epoch=0)
    denied = assert_snapshot_action_allowed(snap, "formulaEditUser", owner_epoch=0)
    assert denied.allowed is False
    assert denied.zh_message
    assert "公式内容" not in denied.zh_message
    assert "thread" not in (denied.zh_message or "").casefold()


def test_all_deny_messages_are_zh_and_non_leaky() -> None:
    for role in ("anonymous", "readonly", "assignee", "reviewer"):
        snap = build_capability_snapshot(_principal(role=role), owner_epoch=0)
        for key in CAPABILITY_KEYS:
            decision = snap[key]
            if decision["allowed"]:
                continue
            assert decision["zhMessage"]
            assert not denial_leaks_sensitive_metadata(decision["zhMessage"])
            # ASCII-only English dumps are not acceptable as primary UI copy
            assert any("\u4e00" <= ch <= "\u9fff" for ch in decision["zhMessage"])


@pytest.mark.parametrize(
    "key",
    ["formulaView", "aiAssistChat", "humanReviewWrite", "guidanceRead"],
)
def test_server_revalidate_matches_matrix(key: str) -> None:
    snap = build_capability_snapshot(_principal(role="reviewer"), owner_epoch=9)
    gate = assert_snapshot_action_allowed(snap, key, owner_epoch=9)  # type: ignore[arg-type]
    direct = decide_capability(_principal(role="reviewer"), key)  # type: ignore[arg-type]
    assert gate.allowed == direct.allowed


# ── runtime-integrity：端点必须从 DB/认证用户重建快照，不信任 query/snapshot ──

import inspect
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.models.core import UserRole
from app.routers import wp_capability_snapshot as capability_router


def test_endpoint_signature_has_no_client_membership_or_role_knobs() -> None:
    params = inspect.signature(capability_router.get_capability_snapshot).parameters
    assert "project_member" not in params
    assert "wp_visible" not in params
    assert "role" not in params
    assert "db" in params


def test_real_user_roles_map_to_capability_roles() -> None:
    expected = {
        UserRole.admin: "admin",
        UserRole.partner: "supervisor",
        UserRole.manager: "lead",
        UserRole.auditor: "assignee",
        UserRole.qc: "reviewer",
        UserRole.eqcr: "reviewer",
        UserRole.readonly: "readonly",
    }
    for role, mapped in expected.items():
        assert capability_router._role_of(SimpleNamespace(role=role)) == mapped


@pytest.mark.asyncio
async def test_snapshot_project_mismatch_is_forbidden() -> None:
    wp_id, actual_project, claimed_project = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), role=UserRole.admin)
    with patch.object(
        capability_router,
        "authorize_wp_read",
        new=AsyncMock(return_value=actual_project),
    ):
        with pytest.raises(HTTPException) as exc:
            await capability_router.get_capability_snapshot(
                wp_id=wp_id,
                project_id=claimed_project,
                owner_epoch=1,
                sheet_uid="A1",
                db=AsyncMock(),
                user=user,
            )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_capability_assert_ignores_client_allow_for_readonly_user() -> None:
    wp_id, project_id = uuid.uuid4(), uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), role=UserRole.readonly)
    forged = build_capability_snapshot(_principal(role="admin", project_id=str(project_id), wp_id=str(wp_id)), owner_epoch=7)
    body = capability_router.CapabilityActionBody(
        capability="formulaEditUser", ownerEpoch=7, snapshot=forged,
    )
    with patch.object(
        capability_router,
        "authorize_wp_read",
        new=AsyncMock(return_value=project_id),
    ):
        with pytest.raises(HTTPException) as exc:
            await capability_router.assert_capability_action(
                wp_id=wp_id, body=body, db=AsyncMock(), user=user,
            )
    assert exc.value.status_code == 403
