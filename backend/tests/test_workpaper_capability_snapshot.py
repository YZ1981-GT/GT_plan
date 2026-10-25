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
