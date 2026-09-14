"""Task 10 backend — review thread key migration."""

from __future__ import annotations

from app.services.workpaper_capability.review_thread_keys import (
    apply_review_key_migration,
    build_canonical_review_thread_key,
    build_legacy_review_thread_key,
    dry_run_review_key_migration,
    parse_legacy_review_thread_key,
)


def test_canonical_and_legacy_keys() -> None:
    c = build_canonical_review_thread_key(
        project_id="p1", wp_id="wp1", anchor_id="sec-a", sheet_uid="s1",
    )
    assert c.wire == "p1/wp1/s1/sec-a"
    assert build_legacy_review_thread_key("wp1", "sec-a") == "wp1:sec-a"
    assert parse_legacy_review_thread_key("wp1:sec-a") == ("wp1", "sec-a")


def test_honest_degrade_without_fabricating_cell() -> None:
    c = build_canonical_review_thread_key(
        project_id="p1", wp_id="wp1", anchor_id="sec-a",
    )
    assert c.sheet_scope == "page"
    whole = build_canonical_review_thread_key(
        project_id="p1", wp_id="wp1", anchor_id="doc", whole_workbook=True,
    )
    assert whole.sheet_scope == "whole-workbook"


def test_dry_run_collision_and_idempotent_apply() -> None:
    report = dry_run_review_key_migration(
        project_id="p1",
        legacy_keys=["wp1:sec1", "wp1:sec1", "orphan-key", "wp2:sec2"],
    )
    assert report["dryRun"] is True
    assert report["collisions"] >= 1
    assert report["orphans"] == 1
    applied = apply_review_key_migration(report)
    assert applied["dryRun"] is False
    assert any(r["detail"] == "applied" for r in applied["rows"] if r["status"] == "mapped")
