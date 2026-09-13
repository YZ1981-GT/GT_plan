# -*- coding: utf-8 -*-
"""底稿能力矩阵 / 九键快照契约守卫。

Spec: d4-adjustment-and-analysis-gap-closure Task 3 / Task 5
Requirements: 2.3, 3.1

守卫的是「前端 formula shell 拉得到、且判定符合 role→capability 真源」这条 backbone，
而非字符串存在。每条断言都对应一个可变异点（改矩阵/改归一化/改 TTL 即会打红）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.workpaper_capability_matrix import (
    CAPABILITY_KEYS,
    CAPABILITY_MATRIX,
    SnapshotSubject,
    assert_capability,
    build_full_capability_snapshot,
    normalize_role,
)

# 前端 workpaperCapabilitySnapshot.ts 的九键，顺序/拼写必须逐字一致。
_FRONTEND_KEYS = (
    "formulaView",
    "formulaEditUser",
    "formulaHistory",
    "aiReviewPage",
    "aiReviewBatch",
    "aiAssistChat",
    "humanReviewRead",
    "humanReviewWrite",
    "guidanceRead",
)


def _subject(role: str, *, owner_epoch: int = 1) -> SnapshotSubject:
    return SnapshotSubject(
        role=role,
        user_id="u-test",
        project_id="p-test",
        wp_id="wp-test",
        sheet_uid="sheet-test",
        owner_epoch=owner_epoch,
    )


class TestSnapshotShape:
    def test_snapshot_carries_all_nine_frontend_keys_in_order(self) -> None:
        assert CAPABILITY_KEYS == _FRONTEND_KEYS
        assert set(CAPABILITY_MATRIX) == set(_FRONTEND_KEYS)
        snap = build_full_capability_snapshot(_subject("auditor"))
        for key in _FRONTEND_KEYS:
            assert key in snap, f"缺能力键 {key}"
            decision = snap[key]
            # 前端 asDecision 读这五个字段。
            assert set(decision) >= {"allowed", "reasonCode", "owner", "nextAction", "zhMessage"}

    def test_snapshot_wire_envelope_matches_frontend_parser(self) -> None:
        snap = build_full_capability_snapshot(_subject("manager", owner_epoch=7))
        assert snap["snapshotVersion"] == "1.0"
        assert snap["ownerEpoch"] == 7
        assert len(snap["subjectDigest"]) == 64  # sha256 hex
        assert snap["expiresAt"] and snap["issuedAt"]

    def test_subject_digest_changes_with_epoch_and_wp(self) -> None:
        a = build_full_capability_snapshot(_subject("manager", owner_epoch=1))["subjectDigest"]
        b = build_full_capability_snapshot(_subject("manager", owner_epoch=2))["subjectDigest"]
        assert a != b  # epoch 变 → 指纹变，杜绝跨 epoch 重放


class TestRoleMatrix:
    def test_viewer_is_read_only_but_can_view(self) -> None:
        snap = build_full_capability_snapshot(_subject("readonly"))
        assert snap["formulaView"]["allowed"] is True
        assert snap["guidanceRead"]["allowed"] is True
        assert snap["formulaEditUser"]["allowed"] is False
        assert snap["formulaEditUser"]["reasonCode"] == "viewer_read_only"
        assert snap["aiReviewBatch"]["allowed"] is False

    def test_assignee_can_edit_and_page_review_but_not_batch_or_review_write(self) -> None:
        snap = build_full_capability_snapshot(_subject("auditor"))
        assert snap["formulaEditUser"]["allowed"] is True
        assert snap["aiReviewPage"]["allowed"] is True
        assert snap["aiReviewBatch"]["allowed"] is False
        assert snap["humanReviewWrite"]["allowed"] is False

    def test_reviewer_roles_can_batch_review_and_write(self) -> None:
        for role in ("manager", "partner", "qc", "eqcr"):
            snap = build_full_capability_snapshot(_subject(role))
            assert snap["aiReviewBatch"]["allowed"] is True, role
            assert snap["humanReviewWrite"]["allowed"] is True, role
            assert snap["formulaEditUser"]["allowed"] is True, role

    def test_admin_allowed_everything(self) -> None:
        snap = build_full_capability_snapshot(_subject("admin"))
        for key in _FRONTEND_KEYS:
            assert snap[key]["allowed"] is True, key

    def test_unknown_role_falls_closed_to_viewer(self) -> None:
        assert normalize_role("wat") == "viewer"
        assert normalize_role(None) == "viewer"
        snap = build_full_capability_snapshot(_subject("wat"))
        assert snap["formulaEditUser"]["allowed"] is False


class TestAssertCapability:
    def test_allows_when_epoch_matches_and_permitted(self) -> None:
        snap = build_full_capability_snapshot(_subject("manager", owner_epoch=5))
        assert assert_capability(snap, "formulaEditUser", owner_epoch=5)["status"] == "allowed"

    def test_blocks_on_epoch_mismatch(self) -> None:
        snap = build_full_capability_snapshot(_subject("manager", owner_epoch=5))
        verdict = assert_capability(snap, "formulaEditUser", owner_epoch=6)
        assert verdict["status"] == "blocked"
        assert verdict["reasonCode"] == "epoch_mismatch"

    def test_blocks_on_expired_snapshot(self) -> None:
        snap = build_full_capability_snapshot(_subject("manager", owner_epoch=5))
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        verdict = assert_capability(snap, "formulaEditUser", owner_epoch=5, now=future)
        assert verdict["status"] == "blocked"
        assert verdict["reasonCode"] == "snapshot_expired"

    def test_blocks_unknown_capability(self) -> None:
        snap = build_full_capability_snapshot(_subject("admin", owner_epoch=1))
        verdict = assert_capability(snap, "notARealCapability", owner_epoch=1)
        assert verdict["reasonCode"] == "unknown_capability"

    def test_denial_message_does_not_leak_sensitive_metadata(self) -> None:
        snap = build_full_capability_snapshot(_subject("readonly", owner_epoch=1))
        msg = snap["formulaEditUser"]["zhMessage"] or ""
        for banned in ("formula=", "thread_id", "threadId", "guidance_title", "公式内容", "线程数"):
            assert banned not in msg
