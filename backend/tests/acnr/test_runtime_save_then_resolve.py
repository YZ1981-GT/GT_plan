"""集成测试: Runtime 保存后立即可解析 — P6

**Validates: Requirements 5.1**

Property: save parsed_data → rebuild_runtime_for_wp → resolve_l3 → found

验证保存后立即可被搜索到的完整链路。
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services.acnr.runtime import (
    clear_all_runtime_entries,
    clear_runtime_entries_for_wp,
    get_runtime_entries,
    rebuild_runtime_for_wp,
    resolve_l3,
    register_custom,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_mock_db():
    """创建 mock db，ownership 校验始终通过。"""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=AsyncMock(
        scalar_one_or_none=lambda: 1
    ))
    return mock_db


# ─── Integration Tests ───────────────────────────────────────────────────────


class TestSaveThenResolve:
    """P6: 保存 parsed_data 后立即可 resolve。"""

    def setup_method(self):
        clear_all_runtime_entries()

    def test_rebuild_then_resolve_found(self):
        """save → rebuild → resolve = found。"""
        project_id = "proj-save-resolve"
        wp_id = "wp-001"
        parsed_data = [
            {"cell_address": "A1", "wp_code": "D2"},
            {"cell_address": "B3", "wp_code": "D2"},
        ]

        async def _run():
            db = _make_mock_db()
            entries = await rebuild_runtime_for_wp(
                db, project_id, wp_id, parsed_data,
                addr_profile="custom_flat",
            )
            assert len(entries) == 2

            # resolve 精确匹配
            status, result = resolve_l3(project_id, "D2/D2/A1")
            assert status == "found"
            assert result.cell_address == "A1"
            assert result.wp_code == "D2"

            # resolve 精确匹配 B3
            status2, result2 = resolve_l3(project_id, "D2/D2/B3")
            assert status2 == "found"
            assert result2.cell_address == "B3"

        asyncio.run(_run())

    def test_rebuild_replaces_old_entries(self):
        """rebuild 替换旧条目（增量重建只更新该 wp）。"""
        project_id = "proj-rebuild-replace"
        wp_id = "wp-rebuild"

        async def _run():
            db = _make_mock_db()

            # 第一次注册
            await rebuild_runtime_for_wp(
                db, project_id, wp_id,
                [{"cell_address": "A1", "wp_code": "D3"}],
                addr_profile="custom_flat",
            )
            status, _ = resolve_l3(project_id, "D3/D3/A1")
            assert status == "found"

            # 第二次 rebuild —— 用新数据替换
            await rebuild_runtime_for_wp(
                db, project_id, wp_id,
                [{"cell_address": "C5", "wp_code": "D3"}],
                addr_profile="custom_flat",
            )

            # 旧条目 A1 应已不存在
            status_old, _ = resolve_l3(project_id, "D3/D3/A1")
            assert status_old == "miss", "旧条目 A1 应在 rebuild 后消失"

            # 新条目 C5 应存在
            status_new, _ = resolve_l3(project_id, "D3/D3/C5")
            assert status_new == "found"

        asyncio.run(_run())

    def test_rebuild_does_not_affect_other_wp(self):
        """rebuild wp_A 不影响 wp_B。"""
        project_id = "proj-rebuild-isolate"
        wp_a = "wp-a"
        wp_b = "wp-b"

        async def _run():
            db = _make_mock_db()

            # 注册 wp_B
            await register_custom(
                db, project_id, wp_b,
                [{"cell_address": "X1", "wp_code": "F1"}],
                addr_profile="custom_flat",
            )

            # rebuild wp_A（清旧 + 注册新）
            await rebuild_runtime_for_wp(
                db, project_id, wp_a,
                [{"cell_address": "Y2", "wp_code": "K1"}],
                addr_profile="custom_flat",
            )

            # wp_B 仍在
            status_b, _ = resolve_l3(project_id, "F1/F1/X1")
            assert status_b == "found", "wp_B 条目不应受 wp_A rebuild 影响"

            # wp_A 新条目在
            status_a, _ = resolve_l3(project_id, "K1/K1/Y2")
            assert status_a == "found"

        asyncio.run(_run())

    def test_resolve_l3_miss_empty_project(self):
        """空项目 resolve 返回 miss。"""
        status, result = resolve_l3("nonexistent-project", "anything")
        assert status == "miss"
        assert result is None

    def test_resolve_l3_exact_vs_prefix(self):
        """精确匹配优先于前缀匹配。"""
        project_id = "proj-exact-priority"
        wp_id = "wp-exact"

        async def _run():
            db = _make_mock_db()

            # 注册两个：一个 addr_id 恰好等于某个前缀目标
            await register_custom(
                db, project_id, wp_id,
                [
                    {"cell_address": "A1", "wp_code": "D2"},
                    {"cell_address": "A2", "wp_code": "D2"},
                ],
                addr_profile="custom_flat",
            )

            # 精确匹配 D2/D2/A1 → found（不是 ambiguous）
            status, result = resolve_l3(project_id, "D2/D2/A1")
            assert status == "found"
            assert result.cell_address == "A1"

        asyncio.run(_run())

    def test_resolve_l3_ambiguous_returns_list(self):
        """多候选同前缀返回 ambiguous + 列表。"""
        project_id = "proj-ambiguous"
        wp_id = "wp-amb"

        async def _run():
            db = _make_mock_db()

            await register_custom(
                db, project_id, wp_id,
                [
                    {"cell_address": "A1", "wp_code": "D2"},
                    {"cell_address": "B2", "wp_code": "D2"},
                ],
                addr_profile="custom_flat",
            )

            # 用 "D2" 作 target → prefix "D2/" 匹配两个
            status, result = resolve_l3(project_id, "D2")
            assert status == "ambiguous"
            assert isinstance(result, list)
            assert len(result) == 2

        asyncio.run(_run())

    def test_resolve_l3_no_false_startswith_match(self):
        """startswith 修复：D2 不匹配 D20/... 或 D2-2/...。"""
        project_id = "proj-no-false"
        wp_id = "wp-nofalse"

        async def _run():
            db = _make_mock_db()

            # 注册 D20/D20/A1（不应被 target="D2" 匹配）
            await register_custom(
                db, project_id, wp_id,
                [{"cell_address": "A1", "wp_code": "D20"}],
                addr_profile="custom_flat",
            )

            # target "D2" → prefix "D2/" 不匹配 "D20/D20/A1"
            status, _ = resolve_l3(project_id, "D2")
            assert status == "miss", "D2 不应匹配 D20 的条目"

            # target "D2-" → prefix "D2-/" 不匹配 "D20/D20/A1"
            status2, _ = resolve_l3(project_id, "D2-")
            assert status2 == "miss"

        asyncio.run(_run())

    def test_cold_start_empty_parsed_data(self):
        """rebuild 传入空 parsed_data 不崩溃。"""
        project_id = "proj-cold"
        wp_id = "wp-cold"

        async def _run():
            db = _make_mock_db()
            entries = await rebuild_runtime_for_wp(
                db, project_id, wp_id, [],
            )
            assert entries == []

        asyncio.run(_run())

    def test_incremental_invalidate_via_clear_for_wp(self):
        """clear_runtime_entries_for_wp 返回清除数量。"""
        project_id = "proj-clear-count"
        wp_id = "wp-count"

        async def _run():
            db = _make_mock_db()
            await register_custom(
                db, project_id, wp_id,
                [
                    {"cell_address": "A1", "wp_code": "K1"},
                    {"cell_address": "A2", "wp_code": "K1"},
                    {"cell_address": "A3", "wp_code": "K1"},
                ],
            )

            removed = clear_runtime_entries_for_wp(project_id, wp_id)
            assert removed == 3

            entries = get_runtime_entries(project_id)
            assert len(entries) == 0

        asyncio.run(_run())
