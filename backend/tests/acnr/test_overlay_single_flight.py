"""PBT: Overlay Single-Flight 防护 — 10 并发同 project → DB 仅调 1 次 [P15]

Property 15 (P15): Single-flight 不重复查询。
验证 Req-13: 多个并发请求同时触发同一 project_id 的 Overlay 缓存重建，
系统确保只有一个 DB 查询实际执行（single-flight 语义）。

测试策略:
- asyncio.gather 10 并发调用 get_overlay_cached(same project_id, session)
- Mock DB 层 load_project_overlays_from_pg 计数调用次数
- Assert: DB 查询仅执行 1 次（single-flight 保证）
- 额外验证: 不同 project 互不阻塞（Req-13.3）
- 额外验证: DB 异常时锁释放不死锁（Req-13.4）

**Validates: Requirements 13.1, 13.2, 13.3, 13.4**
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ─── Path setup ──────────────────────────────────────────────────────────────
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr.overlay import (
    OverlayPatch,
    clear_all_overlays,
    get_overlay_cached,
    get_project_overlays,
    is_cache_loaded,
    populate_cache,
)

# ─── Helpers ─────────────────────────────────────────────────────────────────


def _run(coro):
    """Run async coroutine synchronously (PBT-compatible)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── Hypothesis Strategies ────────────────────────────────────────────────────

_concurrency_st = st.just(10)  # 固定 10 并发
_wp_code_st = st.from_regex(r"[A-N][1-9][0-9]?", fullmatch=True)
_sheet_code_st = st.from_regex(r"[A-N][1-9][0-9]?-[1-9]", fullmatch=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Property 15: Single-flight 不重复查询
# ═══════════════════════════════════════════════════════════════════════════════


class TestP15SingleFlightOverlay:
    """P15: Single-flight 不重复查询 — 10 并发同 project → DB 仅调 1 次。

    **Validates: Requirements 13.1, 13.2, 13.3, 13.4**
    """

    @settings(max_examples=5, deadline=None)
    @given(
        parent_wp_code=_wp_code_st,
        sheet_code=_sheet_code_st,
    )
    def test_concurrent_cache_miss_single_db_call(
        self,
        parent_wp_code: str,
        sheet_code: str,
    ):
        """Req-13.1 + Req-13.2: 10 并发同 project → DB 仅调 1 次 + 结果广播给所有等待者。

        **Validates: Requirements 13.1, 13.2**
        """
        clear_all_overlays()

        async def _test():
            project_id = str(uuid.uuid4())
            addr_id = f"{parent_wp_code}/{sheet_code}"

            # Mock DB result
            mock_patches: dict[str, OverlayPatch] = {
                addr_id: OverlayPatch(
                    project_id=project_id,
                    addr_id=addr_id,
                    overrides={"test": "value"},
                    overlay_type="cust",
                )
            }

            db_call_count = 0

            async def _mock_load(session, pid):
                nonlocal db_call_count
                db_call_count += 1
                # Simulate DB latency to ensure all 10 coroutines queue up
                await asyncio.sleep(0.05)
                populate_cache(pid, mock_patches)
                return mock_patches

            mock_session = AsyncMock()

            with patch(
                "app.services.acnr.overlay.load_project_overlays_from_pg",
                side_effect=_mock_load,
            ):
                # Launch 10 concurrent calls for the SAME project
                tasks = [
                    get_overlay_cached(project_id, mock_session)
                    for _ in range(10)
                ]
                results = await asyncio.gather(*tasks)

            # Assert: DB called exactly ONCE (single-flight)
            assert db_call_count == 1, (
                f"Expected 1 DB call (single-flight), got {db_call_count}"
            )

            # Assert: All 10 results are identical (broadcast)
            for i, result in enumerate(results):
                assert result == mock_patches, (
                    f"Result[{i}] should match DB result (broadcast)"
                )

            # Assert: Cache is now loaded
            assert is_cache_loaded(project_id)

        _run(_test())

    @settings(max_examples=5, deadline=None)
    @given(
        wp_code_a=_wp_code_st,
        wp_code_b=_wp_code_st,
    )
    def test_different_projects_not_blocked(
        self,
        wp_code_a: str,
        wp_code_b: str,
    ):
        """Req-13.3: 不同 project 的请求互不阻塞。

        **Validates: Requirements 13.3**
        """
        clear_all_overlays()

        async def _test():
            project_a = str(uuid.uuid4())
            project_b = str(uuid.uuid4())

            call_log: list[str] = []

            async def _mock_load(session, pid):
                call_log.append(pid)
                await asyncio.sleep(0.02)
                populate_cache(pid, {})
                return {}

            mock_session = AsyncMock()

            with patch(
                "app.services.acnr.overlay.load_project_overlays_from_pg",
                side_effect=_mock_load,
            ):
                # Concurrent calls for TWO different projects
                tasks = [
                    get_overlay_cached(project_a, mock_session),
                    get_overlay_cached(project_b, mock_session),
                ]
                await asyncio.gather(*tasks)

            # Both projects should have been loaded (each independently)
            assert project_a in call_log, "Project A should be loaded"
            assert project_b in call_log, "Project B should be loaded"
            assert is_cache_loaded(project_a)
            assert is_cache_loaded(project_b)

        _run(_test())

    @settings(max_examples=5, deadline=None)
    @given(
        parent_wp_code=_wp_code_st,
    )
    def test_db_exception_releases_lock_no_deadlock(
        self,
        parent_wp_code: str,
    ):
        """Req-13.4: DB 异常时释放锁允许后续请求重试（不死锁）。

        **Validates: Requirements 13.4**
        """
        clear_all_overlays()

        async def _test():
            project_id = str(uuid.uuid4())

            call_count = 0

            async def _mock_load_fail_then_succeed(session, pid):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # First call fails (DB exception)
                    raise RuntimeError("Simulated DB failure")
                # Second call succeeds
                populate_cache(pid, {})
                return {}

            mock_session = AsyncMock()

            with patch(
                "app.services.acnr.overlay.load_project_overlays_from_pg",
                side_effect=_mock_load_fail_then_succeed,
            ):
                # First call: should raise (DB failure)
                with pytest.raises(RuntimeError, match="Simulated DB failure"):
                    await get_overlay_cached(project_id, mock_session)

                # Lock should be released — second call should succeed
                result = await get_overlay_cached(project_id, mock_session)
                assert result == {}
                assert is_cache_loaded(project_id)

            # Total: 2 DB calls (first failed, second succeeded)
            assert call_count == 2

        _run(_test())

    @settings(max_examples=5, deadline=None)
    @given(
        parent_wp_code=_wp_code_st,
        sheet_code=_sheet_code_st,
    )
    def test_cache_hit_skips_lock_entirely(
        self,
        parent_wp_code: str,
        sheet_code: str,
    ):
        """Fast path: cache hit returns immediately without acquiring lock.

        **Validates: Requirements 13.1**
        """
        clear_all_overlays()

        async def _test():
            project_id = str(uuid.uuid4())
            addr_id = f"{parent_wp_code}/{sheet_code}"

            # Pre-populate cache
            patches = {
                addr_id: OverlayPatch(
                    project_id=project_id,
                    addr_id=addr_id,
                    overrides={"cached": True},
                    overlay_type="alias",
                )
            }
            populate_cache(project_id, patches)

            db_call_count = 0

            async def _mock_load(session, pid):
                nonlocal db_call_count
                db_call_count += 1
                return {}

            mock_session = AsyncMock()

            with patch(
                "app.services.acnr.overlay.load_project_overlays_from_pg",
                side_effect=_mock_load,
            ):
                # 10 concurrent calls with cache already populated
                tasks = [
                    get_overlay_cached(project_id, mock_session)
                    for _ in range(10)
                ]
                results = await asyncio.gather(*tasks)

            # No DB calls (all cache hits)
            assert db_call_count == 0, (
                f"Expected 0 DB calls (cache hit), got {db_call_count}"
            )

            # All results match cached data
            for result in results:
                assert result == patches

        _run(_test())
