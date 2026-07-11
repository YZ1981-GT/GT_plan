"""Property 16: Invalidation Path Convergence (PBT)

# Feature: acnr-consumer-wiring, Property 16: Invalidation Path Convergence

验证两条 WP 域失效入口 —— `WORKPAPER_SAVED` 事件路径
(`on_workpaper_saved` → `invalidate`) 与 `touch_wp_registry` 热路径
(`touch_wp_registry` → `invalidate`) —— 收敛到 **同一 canonical invalidate**：

1. 两条路径清理的缓存层集合 **完全一致**（L3 RuntimeIndex / L2 Overlay /
   FormulaReverseIndex / Legacy V1 delegate 四层）。
2. 两条路径都 **包含 FormulaReverseIndex 清理**（修复 Req 2.5 死代码风险：
   `touch_wp_registry` 曾直调 `address_registry.invalidate_async` 绕过 reverse_index）。
3. `touch_wp_registry` **不 re-publish 任何事件**（不调 event_bus.publish /
   publish_immediate / broadcast_raw），避免 handler 重复 fan-out（Req 10.4）。

使用 Hypothesis 随机化 project_id / wp_id / trigger 输入。

**Validates: Requirements 2.5, 2.6, 10.1, 10.2, 10.4**

Testing framework: hypothesis
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# 确保 backend 目录在 path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr.events import invalidate, on_workpaper_saved  # noqa: E402
from app.services.address_registry import address_registry  # noqa: E402
from app.services.event_bus import event_bus  # noqa: E402
from app.services.wp_parsed_data_service import touch_wp_registry  # noqa: E402

# ---------------------------------------------------------------------------
# Step patch targets — 与 events.invalidate() 内部按序 import 的 4 个符号一致
# ---------------------------------------------------------------------------

_L3_TARGET = "app.services.acnr.runtime.clear_runtime_entries"
_L2_TARGET = "app.services.acnr.overlay.clear_project_overlays"
_REV_TARGET = "app.services.formula_reverse_index.invalidate_reverse_index"
# Step 4（legacy V1 delegate）是 address_registry 单例上的 async 方法，用 patch.object

# canonical 4 层缓存的稳定标签
_LAYER_L3 = "L3_runtime"
_LAYER_L2 = "L2_overlay"
_LAYER_REV = "reverse_index"
_LAYER_LEGACY = "legacy_wp"
_ALL_LAYERS = {_LAYER_L3, _LAYER_L2, _LAYER_REV, _LAYER_LEGACY}


def _run_path_and_collect(coro_factory):
    """在打桩环境下运行一条失效路径，返回 (被清理的层集合, 事件 spies)。

    - 4 个失效 step 打桩为记录型 spy，把各自标签加入共享 set。
    - event_bus 的 publish / publish_immediate / broadcast_raw 同时打桩为 spy，
      用于断言"是否 re-publish 事件"。

    coro_factory: 无参 callable，返回要 await 的协程（例如
        lambda: touch_wp_registry(pid) 或 lambda: on_workpaper_saved(payload)）。
    """
    cleared: set[str] = set()

    l3_spy = MagicMock(side_effect=lambda *a, **k: cleared.add(_LAYER_L3))
    l2_spy = MagicMock(side_effect=lambda *a, **k: cleared.add(_LAYER_L2))
    rev_spy = MagicMock(side_effect=lambda *a, **k: cleared.add(_LAYER_REV))
    legacy_spy = AsyncMock(side_effect=lambda *a, **k: cleared.add(_LAYER_LEGACY))

    publish_spy = AsyncMock()
    publish_immediate_spy = AsyncMock()
    broadcast_raw_spy = MagicMock()

    with patch(_L3_TARGET, l3_spy), patch(_L2_TARGET, l2_spy), patch(
        _REV_TARGET, rev_spy
    ), patch.object(address_registry, "invalidate_async", legacy_spy), patch.object(
        event_bus, "publish", publish_spy
    ), patch.object(
        event_bus, "publish_immediate", publish_immediate_spy
    ), patch.object(
        event_bus, "broadcast_raw", broadcast_raw_spy
    ):
        asyncio.run(coro_factory())

    return cleared, {
        "publish": publish_spy,
        "publish_immediate": publish_immediate_spy,
        "broadcast_raw": broadcast_raw_spy,
    }


class TestInvalidationPathConvergence:
    """Property 16: WORKPAPER_SAVED 路径与 touch_wp_registry 路径失效收敛。"""

    # Feature: acnr-consumer-wiring, Property 16: Invalidation Path Convergence

    @given(
        project_id=st.uuids().map(str),
        wp_id=st.one_of(st.none(), st.uuids().map(str)),
        trigger=st.sampled_from(
            ["html_save", "univer_save", "onlyoffice_callback", "wp_structure", None]
        ),
    )
    @settings(
        max_examples=150,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_both_paths_clean_identical_layers_incl_reverse_index(
        self, project_id: str, wp_id: str | None, trigger: str | None
    ):
        """两条路径清理的缓存层集合一致，且都含 reverse_index clear。

        **Validates: Requirements 2.5, 2.6, 10.1, 10.2**
        """
        # Path A: touch_wp_registry 热路径
        cleared_touch, _ = _run_path_and_collect(
            lambda: touch_wp_registry(project_id)
        )

        # Path B: WORKPAPER_SAVED 事件路径（fake EventPayload 携带 project_id）
        payload = SimpleNamespace(
            project_id=project_id,
            extra={"wp_id": wp_id, "trigger": trigger},
        )
        cleared_event, _ = _run_path_and_collect(
            lambda: on_workpaper_saved(payload)
        )

        # (1) 两条路径清理的缓存层集合完全一致
        assert cleared_touch == cleared_event, (
            f"两条失效路径清理的缓存层不一致: touch={cleared_touch} "
            f"event={cleared_event} (project_id={project_id})"
        )

        # (2) 两条路径都清理了全部 4 层（canonical 全链），且都含 reverse_index
        assert cleared_touch == _ALL_LAYERS, (
            f"touch_wp_registry 未清理全部 canonical 缓存层: {cleared_touch}"
        )
        assert _LAYER_REV in cleared_touch, (
            "touch_wp_registry 未触发 FormulaReverseIndex 清理（Req 2.5 死代码风险回归）"
        )
        assert _LAYER_REV in cleared_event, (
            "WORKPAPER_SAVED 路径未触发 FormulaReverseIndex 清理"
        )

    @given(
        project_id=st.uuids().map(str),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_touch_wp_registry_does_not_republish_event(self, project_id: str):
        """touch_wp_registry 走 in-process 直调，绝不 re-publish 事件（无重复 fan-out）。

        **Validates: Requirements 10.4**
        """
        _, spies = _run_path_and_collect(lambda: touch_wp_registry(project_id))

        spies["publish"].assert_not_called()
        spies["publish_immediate"].assert_not_called()
        spies["broadcast_raw"].assert_not_called()

    @given(
        project_id=st.uuids().map(str),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_touch_wp_registry_delegates_legacy_wp_domain(self, project_id: str):
        """canonical invalidate 末步仍委托 legacy address_registry(domain='wp')（Req 10.2 无回归）。

        **Validates: Requirements 10.2**
        """
        cleared, _ = _run_path_and_collect(lambda: touch_wp_registry(project_id))
        assert _LAYER_LEGACY in cleared, (
            "touch_wp_registry 未委托 legacy address_registry.invalidate_async"
        )
