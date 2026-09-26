# -*- coding: utf-8 -*-
"""F1 红判据 Property 1 + Property 5。

spec: f1-sync-coverage-and-first-canary · Task 3

Property 1: canary 打通后 migration_state 与 legacy_reasons 正确变更
  现状必红：`xlsx/gt-f1-prepayment` 仍为 `legacy_fake_bidirectional`。

Property 5: `assert_entry_selectable` 对真 manifest 真调且默认严格
  变异：`WP_CODES` 改为真码 `{"F1"}` ⇒ 必抛（manifest 里是 `["F1P"]`）。
  🔴 对 E1 同类缺陷（FC-2）的防复发判据。
"""
from __future__ import annotations

import pytest

from app.services.workpaper_sync.entry_profile import (
    load_entry_manifest,
    manifest_entries_by_id,
)


F1_ENTRY_ID = "xlsx/gt-f1-prepayment"


# ═══════════════════════════════════════════════════════════════════════════
# Property 1：migration_state 正确（现状必红）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty1MigrationState:
    """canary 打通后 migration_state 从 legacy_fake_bidirectional → adapter_registered。"""

    def test_f1_entry_exists_in_manifest(self) -> None:
        manifest = load_entry_manifest()
        entries = manifest_entries_by_id(manifest)
        assert F1_ENTRY_ID in entries, f"{F1_ENTRY_ID} 不在 manifest 里"

    @pytest.mark.xfail(
        reason="🔴 现状必红：F1 尚未接入，migration_state 仍为 legacy_fake_bidirectional",
        strict=True,
    )
    def test_migration_state_is_adapter_registered(self) -> None:
        manifest = load_entry_manifest()
        entries = manifest_entries_by_id(manifest)
        entry = entries[F1_ENTRY_ID]
        assert entry.get("migration_state") == "adapter_registered", (
            f"F1 migration_state={entry.get('migration_state')!r}，"
            "期望 adapter_registered（Task 9 发布链通过后转绿）"
        )

    @pytest.mark.xfail(
        reason="🔴 现状必红：F1 的三条 legacy_reasons 尚未消除",
        strict=True,
    )
    def test_legacy_reasons_all_cleared(self) -> None:
        manifest = load_entry_manifest()
        entries = manifest_entries_by_id(manifest)
        entry = entries[F1_ENTRY_ID]
        reasons = entry.get("evidence", {}).get("legacy_reasons", [])
        assert reasons == [], (
            f"F1 legacy_reasons={reasons}，期望全部消除"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 5：assert_entry_selectable 对真 manifest 真调且默认严格
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty5EntrySelectable:
    """🔴 FC-2 对 E1 同类缺陷的防复发判据：
    F1 provider 的 WP_CODES 必须是幻影码 {"F1P"}（manifest 冻结值），
    不是真码 {"F1"}。assert_entry_selectable 对真 manifest 真调。
    """

    def test_provider_module_exists(self) -> None:
        """F1 provider 模块可 import。✅ Task 7 已创建。"""
        from app.services.workpaper_sync import phase5_f1_prepayment  # noqa: F401

    def test_wp_codes_is_phantom(self) -> None:
        """WP_CODES 应为幻影码 {"F1P"}，不是真码 {"F1"}（FC-2）。"""
        from app.services.workpaper_sync.phase5_f1_prepayment import WP_CODES
        assert WP_CODES == frozenset({"F1P"}), (
            f"WP_CODES={WP_CODES}，应为幻影码 {{'F1P'}}（FC-2）"
        )

    def test_assert_entry_selectable_on_real_manifest(self) -> None:
        """对真 manifest 真调 assert_entry_selectable，不像 E1 只断言常量。"""
        from app.services.workpaper_sync.phase5_f1_prepayment import (
            WP_CODES,
            assert_entry_selectable,
            TemplateResolutionFacts,
        )
        resolution = TemplateResolutionFacts(
            by_wp_code={code: [None] for code in WP_CODES},
            parent_code="F1",
            parent_resolved_path=None,
        )
        entry = assert_entry_selectable(resolution=resolution)
        assert entry is not None

    def test_mutation_true_code_raises(self) -> None:
        """变异：WP_CODES 改为真码 {"F1"} 时 assert_entry_selectable 必抛。"""
        from app.services.workpaper_sync.phase5_f1_prepayment import (
            assert_entry_selectable,
            EntrySelectionError,
            TemplateResolutionFacts,
        )
        mutated_codes = frozenset({"F1"})
        resolution = TemplateResolutionFacts(
            by_wp_code={code: [None] for code in mutated_codes},
            parent_code="F1",
            parent_resolved_path=None,
        )
        with pytest.raises(EntrySelectionError):
            assert_entry_selectable(resolution=resolution)
