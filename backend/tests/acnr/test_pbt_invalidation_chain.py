"""Property 14: Invalidation Chain Completeness (PBT)

# Feature: acnr-consumer-wiring, Property 14: Invalidation Chain Completeness

验证 `acnr.events.invalidate()` 的 4 步失效链完整性：
无论任意 step 组合是否抛异常，4 步（L3 RuntimeIndex → L2 Overlay →
FormulaReverseIndex → Legacy V1 delegate）都必须各被调用恰好一次，
且前序 step 抛出的异常绝不会跳过后续 step；`invalidate()` 本身永不 re-raise。

使用 Hypothesis 注入随机异常组合（长度 4 的 bool 元组决定哪些 step raise）。

**Validates: Requirements 2.1, 2.2, 2.3**

Testing framework: hypothesis
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# 确保 backend 目录在 path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr.events import invalidate  # noqa: E402
from app.services.address_registry import address_registry  # noqa: E402

# ---------------------------------------------------------------------------
# Step patch targets — 与 events.invalidate() 内部按序 import 的 4 个符号一致
# ---------------------------------------------------------------------------

_L3_TARGET = "app.services.acnr.runtime.clear_runtime_entries"
_L2_TARGET = "app.services.acnr.overlay.clear_project_overlays"
_REV_TARGET = "app.services.formula_reverse_index.invalidate_reverse_index"
# Step 4（legacy V1 delegate）是 address_registry 单例上的 async 方法，用 patch.object


# ---------------------------------------------------------------------------
# Property Test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _stub_durable_epoch():
    """Step 5 Durable_Epoch（DB-first）与本测试的 4 步缓存链正交 —— 打桩避免在
    asyncio.run per-example loop 中开真实 DB 连接（跨 loop asyncpg 清理 RuntimeWarning）。
    """
    with patch(
        "app.services.acnr.cache_epoch.increment_epoch",
        new=AsyncMock(return_value=0),
    ):
        yield


class TestInvalidationChainCompleteness:
    """Property 14: 4 步失效链完整性 — 任意异常组合下全步必达。"""

    # Feature: acnr-consumer-wiring, Property 14: Invalidation Chain Completeness

    @given(
        raise_flags=st.tuples(
            st.booleans(),  # step1 L3 clear_runtime_entries raises?
            st.booleans(),  # step2 L2 clear_project_overlays raises?
            st.booleans(),  # step3 invalidate_reverse_index raises?
            st.booleans(),  # step4 legacy invalidate_async raises?
        )
    )
    @settings(
        max_examples=150,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_all_four_steps_always_invoked(self, raise_flags: tuple):
        """无论哪些 step 抛异常，4 步均被调用恰好一次，且 invalidate 不 re-raise。

        **Validates: Requirements 2.1, 2.2, 2.3**
        """
        r_l3, r_l2, r_rev, r_legacy = raise_flags

        # 同步 step：MagicMock spy，按 flag 决定是否抛异常
        l3_spy = MagicMock(side_effect=RuntimeError("L3 fail") if r_l3 else None)
        l2_spy = MagicMock(side_effect=RuntimeError("L2 fail") if r_l2 else None)
        rev_spy = MagicMock(
            side_effect=RuntimeError("reverse_index fail") if r_rev else None
        )
        # 异步 step：AsyncMock spy（await 时抛异常）
        legacy_spy = AsyncMock(
            side_effect=RuntimeError("legacy fail") if r_legacy else None
        )

        with patch(_L3_TARGET, l3_spy), patch(_L2_TARGET, l2_spy), patch(
            _REV_TARGET, rev_spy
        ), patch.object(address_registry, "invalidate_async", legacy_spy):
            # invalidate() 必须永不抛异常（失效失败仅 warning，不阻断主流程）
            try:
                asyncio.run(invalidate("proj-p14", trigger="pbt"))
            except Exception as exc:  # noqa: BLE001
                pytest.fail(
                    f"invalidate() re-raised despite catch-all contract: {exc!r} "
                    f"(raise_flags={raise_flags})"
                )

        # (a) 每步恰好被调用一次，与该步/其他步是否抛异常无关
        assert l3_spy.call_count == 1, (
            f"L3 clear not invoked exactly once (flags={raise_flags})"
        )
        assert l2_spy.call_count == 1, (
            f"L2 overlay clear not invoked exactly once — 前序异常不得跳过后续步 "
            f"(flags={raise_flags})"
        )
        assert rev_spy.call_count == 1, (
            f"reverse_index clear not invoked exactly once — 前序异常不得跳过后续步 "
            f"(flags={raise_flags})"
        )
        assert legacy_spy.await_count == 1, (
            f"legacy invalidate_async not awaited exactly once — 前序异常不得跳过 "
            f"末步 legacy delegate (flags={raise_flags})"
        )

    @given(raise_flags=st.tuples(st.booleans(), st.booleans(), st.booleans(), st.booleans()))
    @settings(
        max_examples=150,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_legacy_delegate_receives_wp_domain(self, raise_flags: tuple):
        """末步 legacy delegate 始终以 domain='wp' 调用（无论前序异常）。

        **Validates: Requirements 2.3**
        """
        r_l3, r_l2, r_rev, r_legacy = raise_flags
        l3_spy = MagicMock(side_effect=RuntimeError("L3") if r_l3 else None)
        l2_spy = MagicMock(side_effect=RuntimeError("L2") if r_l2 else None)
        rev_spy = MagicMock(side_effect=RuntimeError("rev") if r_rev else None)
        legacy_spy = AsyncMock(side_effect=RuntimeError("legacy") if r_legacy else None)

        with patch(_L3_TARGET, l3_spy), patch(_L2_TARGET, l2_spy), patch(
            _REV_TARGET, rev_spy
        ), patch.object(address_registry, "invalidate_async", legacy_spy):
            asyncio.run(invalidate("proj-p14", trigger="pbt"))

        legacy_spy.assert_awaited_once()
        _args, kwargs = legacy_spy.call_args
        assert kwargs.get("domain") == "wp", (
            f"legacy delegate 未以 domain='wp' 调用: kwargs={kwargs} (flags={raise_flags})"
        )
