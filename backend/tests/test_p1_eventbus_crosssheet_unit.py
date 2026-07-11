"""P1 单元测试 — CrossSheetResolver project_id 传递 + EventBus 失效链

Spec: acnr-consumer-wiring (task 1.5)
Requirements:
  - 1.4: CrossSheetResolver 将 project_id 传递给 full_resolve
  - 2.1: WORKPAPER_SAVED → invalidate 调用 invalidate_reverse_index
  - 2.2: reverse_index 失效异常不 re-raise
  - 2.3: 失效顺序 L3 → L2 → ReverseIndex → Legacy V1
  - 2.4: extra_sheets 不影响 reverse_index 完整失效

以 example-based 单测覆盖（非 Hypothesis）。
"""

import asyncio
import types

import pytest

import app.services.acnr.events as acnr_events
import app.services.custom_query.cross_sheet_resolver as csr_mod
from app.services.custom_query.cross_sheet_resolver import CrossSheetResolver


# ─── Requirement 1.4: project_id 传递给 full_resolve ─────────────────────────


class TestProjectIdPassedToFullResolve:
    """Req 1.4: CrossSheetResolver 将 project_id 透传给 ACNR full_resolve。"""

    def _snapshot(self) -> dict:
        """单节点 snapshot（无跨 sheet 引用，BFS 只处理起始节点）。"""
        return {
            "univer_snapshot": {
                "sheets": [
                    {"name": "审定表D2-1", "cellData": {"1": {"0": {"v": 100}}}},
                ]
            }
        }

    def test_project_id_forwarded(self, monkeypatch):
        """resolve() 调 _sync_resolve 时应带上构造函数中的 project_id。"""
        captured: dict = {}

        def fake_sync_resolve(*, formula_ref=None, uri=None, project_id=None):
            captured["project_id"] = project_id
            captured["formula_ref"] = formula_ref
            captured["uri"] = uri
            # 返回命中结果，验证 addr_id 被用作 node uri
            return types.SimpleNamespace(found=True, addr_id="D2/D2-1/A2")

        monkeypatch.setattr(csr_mod, "_sync_resolve", fake_sync_resolve)

        resolver = CrossSheetResolver(project_id="proj-123")
        result = resolver.resolve(
            parsed_data=self._snapshot(),
            sheet_name="审定表D2-1",
            cell_ref="A2",
            max_depth=3,
        )

        assert captured["project_id"] == "proj-123"
        # 命中时使用 addr_id 作为 node uri（Req 1.2 副带验证）
        assert result.chain[0].uri == "D2/D2-1/A2"
        assert result.chain[0].resolve_missed is False

    def test_none_project_id_forwarded(self, monkeypatch):
        """未提供 project_id 时透传 None（不报错）。"""
        captured: dict = {}

        def fake_sync_resolve(*, formula_ref=None, uri=None, project_id=None):
            captured["project_id"] = project_id
            return types.SimpleNamespace(found=False, addr_id=None)

        monkeypatch.setattr(csr_mod, "_sync_resolve", fake_sync_resolve)

        resolver = CrossSheetResolver()  # 无 project_id
        result = resolver.resolve(
            parsed_data=self._snapshot(),
            sheet_name="审定表D2-1",
            cell_ref="A2",
        )

        assert captured["project_id"] is None
        # miss → snapshot fallback，标记 resolve_missed（Req 1.3 副带验证）
        assert result.chain[0].uri == "审定表D2-1!A2"
        assert result.chain[0].resolve_missed is True

    def test_project_id_forwarded_with_parent_wp_code(self, monkeypatch):
        """有 parent_wp_code 时用 grammar_v1 3 参 formula_ref，且仍带 project_id。"""
        captured: dict = {}

        def fake_sync_resolve(*, formula_ref=None, uri=None, project_id=None):
            captured["project_id"] = project_id
            captured["formula_ref"] = formula_ref
            return types.SimpleNamespace(found=True, addr_id="D2/D2-1/A2")

        monkeypatch.setattr(csr_mod, "_sync_resolve", fake_sync_resolve)

        resolver = CrossSheetResolver(project_id="proj-777", parent_wp_code="D2")
        resolver.resolve(
            parsed_data=self._snapshot(),
            sheet_name="审定表D2-1",
            cell_ref="A2",
        )

        assert captured["project_id"] == "proj-777"
        assert captured["formula_ref"] == "WP('D2','审定表D2-1','A2')"


# ─── Requirement 2.1–2.4: invalidation chain ────────────────────────────────


def _patch_invalidation_steps(monkeypatch, call_order: list, *, raising: set | None = None):
    """Monkeypatch 4 个失效 step，记录调用顺序到 call_order。

    raising: 需抛异常的 step 名集合（用于验证异常隔离）。
    返回时各 step 被替换为记录函数。
    """
    raising = raising or set()

    import app.services.acnr.runtime as runtime_mod
    import app.services.acnr.overlay as overlay_mod
    import app.services.formula_reverse_index as fri_mod
    from app.services.address_registry import address_registry

    def make_step(name):
        def _step(*args, **kwargs):
            call_order.append(name)
            if name in raising:
                raise RuntimeError(f"{name} boom")
        return _step

    def async_step_factory(name):
        async def _astep(*args, **kwargs):
            call_order.append(name)
            if name in raising:
                raise RuntimeError(f"{name} boom")
        return _astep

    monkeypatch.setattr(runtime_mod, "clear_runtime_entries", make_step("L3"))
    monkeypatch.setattr(overlay_mod, "clear_project_overlays", make_step("L2"))
    monkeypatch.setattr(fri_mod, "invalidate_reverse_index", make_step("ReverseIndex"))
    monkeypatch.setattr(
        address_registry, "invalidate_async", async_step_factory("Legacy")
    )


class TestInvalidationChainOrder:
    """Req 2.3: 失效顺序 L3 → L2 → ReverseIndex → Legacy V1。"""

    def test_execution_order(self, monkeypatch):
        call_order: list = []
        _patch_invalidation_steps(monkeypatch, call_order)

        asyncio.run(acnr_events.invalidate("proj-1", trigger="html_save"))

        assert call_order == ["L3", "L2", "ReverseIndex", "Legacy"]

    def test_reverse_index_always_called(self, monkeypatch):
        """Req 2.1: WORKPAPER_SAVED 路径下 invalidate_reverse_index 必被调用。"""
        call_order: list = []
        _patch_invalidation_steps(monkeypatch, call_order)

        asyncio.run(acnr_events.invalidate("proj-1"))

        assert "ReverseIndex" in call_order


class TestInvalidationExceptionIsolation:
    """Req 2.2: 各 step 异常独立隔离，不 re-raise，不中断后续 step。"""

    def test_reverse_index_exception_not_raised(self, monkeypatch):
        call_order: list = []
        _patch_invalidation_steps(monkeypatch, call_order, raising={"ReverseIndex"})

        # 不应抛异常
        asyncio.run(acnr_events.invalidate("proj-1"))

        # ReverseIndex 抛异常后，Legacy 仍应执行
        assert call_order == ["L3", "L2", "ReverseIndex", "Legacy"]

    def test_all_steps_run_despite_all_raising(self, monkeypatch):
        """即使每一步都抛异常，全部 4 步仍被调用（Req 2.2 + 2.3 完整性）。"""
        call_order: list = []
        _patch_invalidation_steps(
            monkeypatch,
            call_order,
            raising={"L3", "L2", "ReverseIndex", "Legacy"},
        )

        asyncio.run(acnr_events.invalidate("proj-1"))

        assert call_order == ["L3", "L2", "ReverseIndex", "Legacy"]


class TestExtraSheetsDoesNotAffectReverseIndex:
    """Req 2.4: 无论 extra_sheets 传什么，reverse_index 都被完整失效。"""

    @pytest.mark.parametrize(
        "extra_sheets",
        [
            None,
            [],
            ["D2-1"],
            ["D2-1", "D2-2", "D2-3"],
        ],
    )
    def test_reverse_index_invalidated_regardless_of_extra_sheets(
        self, monkeypatch, extra_sheets
    ):
        call_order: list = []
        _patch_invalidation_steps(monkeypatch, call_order)

        asyncio.run(
            acnr_events.invalidate(
                "proj-1",
                wp_id="wp-42",
                trigger="univer_save",
                extra_sheets=extra_sheets,
            )
        )

        # reverse_index 始终被调用，且顺序不变
        assert "ReverseIndex" in call_order
        assert call_order == ["L3", "L2", "ReverseIndex", "Legacy"]

    def test_empty_project_id_short_circuits(self, monkeypatch):
        """project_id 为空时直接返回，不触发任何失效 step。"""
        call_order: list = []
        _patch_invalidation_steps(monkeypatch, call_order)

        asyncio.run(acnr_events.invalidate("", extra_sheets=["D2-1"]))

        assert call_order == []
