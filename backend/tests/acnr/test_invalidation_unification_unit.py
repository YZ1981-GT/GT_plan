"""Unit tests for invalidation path unification (Task 11.4).

# Feature: acnr-consumer-wiring, Task 11.4 — Invalidation Unification Unit Tests

覆盖两块行为：

1. `acnr.events.invalidate_domain(project_id, *, domain, wp_id=None)` 的按域委托：
   - domain == "wp" → 汇入 canonical `invalidate()`（trigger="touch_wp_registry"），
     不走 legacy `address_registry.invalidate_async`。
   - domain in {tb, report, note, aux} → 委托 legacy
     `address_registry.invalidate_async(pid, domain=domain)`，不调 canonical invalidate。
   - 空 project_id → 短路，无任何调用。

2. `wp_parsed_data_service.touch_wp_registry` 异常吞噬：
   - canonical invalidate 抛异常时，touch_wp_registry 仅 warning，不 re-raise。

**Validates: Requirements 10.3, 11.3**

Testing framework: pytest (example-based unit tests; async 走 asyncio.run)
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# 确保 backend 目录在 path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr import events  # noqa: E402
from app.services.acnr.events import invalidate_domain  # noqa: E402
from app.services.address_registry import address_registry  # noqa: E402
from app.services import wp_parsed_data_service  # noqa: E402

_CANONICAL_TARGET = "app.services.acnr.events.invalidate"


# ---------------------------------------------------------------------------
# 1. invalidate_domain — wp 域汇入 canonical invalidate
# ---------------------------------------------------------------------------


class TestInvalidateDomainWp:
    """domain=="wp" 委托 canonical invalidate（Req 11.3 / 10.3）。"""

    def test_wp_domain_calls_canonical_invalidate(self):
        """invalidate_domain(pid, domain="wp") → 调 canonical invalidate。"""
        canonical_spy = AsyncMock()
        legacy_spy = AsyncMock()

        with patch(_CANONICAL_TARGET, canonical_spy), patch.object(
            address_registry, "invalidate_async", legacy_spy
        ):
            asyncio.run(invalidate_domain("proj-wp", domain="wp"))

        # canonical invalidate 被调用恰好一次，trigger="touch_wp_registry"
        canonical_spy.assert_awaited_once()
        args, kwargs = canonical_spy.call_args
        assert args[0] == "proj-wp"
        assert kwargs.get("trigger") == "touch_wp_registry"
        # wp 域不直接走 legacy delegate（legacy 由 canonical 内部负责）
        legacy_spy.assert_not_awaited()

    def test_wp_domain_forwards_wp_id(self):
        """wp 域应把 wp_id 透传给 canonical invalidate（增量失效用）。"""
        canonical_spy = AsyncMock()

        with patch(_CANONICAL_TARGET, canonical_spy):
            asyncio.run(
                invalidate_domain("proj-wp", domain="wp", wp_id="wp-123")
            )

        canonical_spy.assert_awaited_once()
        _args, kwargs = canonical_spy.call_args
        assert kwargs.get("wp_id") == "wp-123"


# ---------------------------------------------------------------------------
# 2. invalidate_domain — 非 wp 域委托 legacy invalidate_async
# ---------------------------------------------------------------------------


class TestInvalidateDomainLegacy:
    """domain in {tb, report, note, aux} 委托 legacy（Req 11.3）。"""

    @pytest.mark.parametrize("domain", ["tb", "report", "note", "aux"])
    def test_non_wp_domain_delegates_to_legacy(self, domain: str):
        """非 wp 域 → address_registry.invalidate_async(pid, domain=domain)，
        不调 canonical invalidate。"""
        canonical_spy = AsyncMock()
        legacy_spy = AsyncMock()

        with patch(_CANONICAL_TARGET, canonical_spy), patch.object(
            address_registry, "invalidate_async", legacy_spy
        ):
            asyncio.run(invalidate_domain("proj-x", domain=domain))

        # legacy delegate 被调用恰好一次，带正确 domain
        legacy_spy.assert_awaited_once()
        args, kwargs = legacy_spy.call_args
        assert args[0] == "proj-x"
        assert kwargs.get("domain") == domain
        # 非 wp 域绝不汇入 canonical invalidate
        canonical_spy.assert_not_awaited()

    def test_legacy_exception_is_swallowed(self):
        """非 wp 域 legacy 抛异常时，invalidate_domain 仅 warning，不 re-raise。"""
        legacy_spy = AsyncMock(side_effect=RuntimeError("legacy boom"))

        with patch.object(address_registry, "invalidate_async", legacy_spy):
            # 不应抛异常
            asyncio.run(invalidate_domain("proj-x", domain="tb"))

        legacy_spy.assert_awaited_once()


# ---------------------------------------------------------------------------
# 3. invalidate_domain — 空 project_id 短路
# ---------------------------------------------------------------------------


class TestInvalidateDomainShortCircuit:
    """空 project_id → 短路，无任何下游调用。"""

    @pytest.mark.parametrize("domain", ["wp", "tb", "report", "note", "aux"])
    def test_empty_project_id_no_calls(self, domain: str):
        canonical_spy = AsyncMock()
        legacy_spy = AsyncMock()

        with patch(_CANONICAL_TARGET, canonical_spy), patch.object(
            address_registry, "invalidate_async", legacy_spy
        ):
            asyncio.run(invalidate_domain("", domain=domain))

        canonical_spy.assert_not_awaited()
        legacy_spy.assert_not_awaited()


# ---------------------------------------------------------------------------
# 4. touch_wp_registry — invalidate 抛异常不 raise（仅 warning）
# ---------------------------------------------------------------------------


class TestTouchWpRegistryExceptionSwallow:
    """touch_wp_registry 异常吞噬（Req 10.3）。"""

    def test_touch_wp_registry_does_not_raise_when_invalidate_raises(self):
        """canonical invalidate 抛异常时，touch_wp_registry 不 re-raise。"""
        boom = AsyncMock(side_effect=RuntimeError("invalidate boom"))

        with patch(_CANONICAL_TARGET, boom):
            try:
                asyncio.run(
                    wp_parsed_data_service.touch_wp_registry("proj-touch")
                )
            except Exception as exc:  # noqa: BLE001
                pytest.fail(
                    f"touch_wp_registry re-raised despite catch-all: {exc!r}"
                )

        # 确实进入了 canonical invalidate（并抛错被吞）
        boom.assert_awaited_once()
        _args, kwargs = boom.call_args
        assert kwargs.get("trigger") == "touch_wp_registry"

    def test_touch_wp_registry_logs_warning_on_failure(self, caplog):
        """异常路径应记录 warning（不静默丢失）。"""
        boom = AsyncMock(side_effect=RuntimeError("invalidate boom"))

        with patch(_CANONICAL_TARGET, boom):
            with caplog.at_level(
                logging.WARNING, logger=wp_parsed_data_service.logger.name
            ):
                asyncio.run(
                    wp_parsed_data_service.touch_wp_registry("proj-touch")
                )

        assert any(
            "touch_wp_registry" in rec.message and rec.levelno == logging.WARNING
            for rec in caplog.records
        ), f"expected a warning log, got: {[r.message for r in caplog.records]}"

    def test_touch_wp_registry_happy_path_calls_canonical(self):
        """正常路径：touch_wp_registry 调 canonical invalidate（trigger 正确）。"""
        canonical_spy = AsyncMock()

        with patch(_CANONICAL_TARGET, canonical_spy):
            asyncio.run(wp_parsed_data_service.touch_wp_registry("proj-ok"))

        canonical_spy.assert_awaited_once()
        args, kwargs = canonical_spy.call_args
        assert args[0] == "proj-ok"
        assert kwargs.get("trigger") == "touch_wp_registry"
