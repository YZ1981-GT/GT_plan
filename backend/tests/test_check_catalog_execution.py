"""S2 Task 3 (ADR-CCN-03)：校对目录执行状态 — 守卫与功能测试。

守卫：标为 wired 的来源入口函数必须真实存在。
last_run：带 project_id 时查询结果表最近一次执行摘要。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.services.formula_check_catalog import (
    SOURCES,
    CheckSource,
    _execution_status,
    build_check_catalog,
)


class TestExecutionStatusLogic:
    """execution 判定逻辑"""

    def test_no_executor_is_display_only(self):
        src = CheckSource(
            key="test", label="", category="", runs_in="", edit_where="",
            loader=lambda: [], executor_entry=None,
        )
        assert _execution_status(src) == "display_only"

    def test_valid_executor_is_wired(self):
        src = CheckSource(
            key="test", label="", category="", runs_in="", edit_where="",
            loader=lambda: [],
            executor_entry="app.services.formula_check_catalog.build_check_catalog",
        )
        assert _execution_status(src) == "wired"

    def test_nonexistent_executor_is_not_executable(self):
        src = CheckSource(
            key="test", label="", category="", runs_in="", edit_where="",
            loader=lambda: [],
            executor_entry="app.services.nonexistent_module.func",
        )
        assert _execution_status(src) == "not_executable"


class TestWiredGuard:
    """守卫：SOURCES 中 executor_entry 非 None 的来源入口必须可导入"""

    @pytest.mark.parametrize(
        "source",
        [s for s in SOURCES if s.executor_entry is not None],
        ids=lambda s: s.key,
    )
    def test_wired_entry_importable(self, source: CheckSource):
        status = _execution_status(source)
        assert status == "wired", (
            f"来源 {source.key} 的 executor_entry={source.executor_entry} "
            f"无法导入（status={status}），应修正入口或改为 None"
        )

    def test_mutation_mislabeled_wired_detected(self):
        """变异：把不存在的入口标为 wired → 守卫必须红"""
        bad_src = CheckSource(
            key="bad", label="", category="", runs_in="", edit_where="",
            loader=lambda: [],
            executor_entry="app.services.THIS_DOES_NOT_EXIST.run",
        )
        assert _execution_status(bad_src) != "wired"


class TestCatalogResponse:
    """build_check_catalog 响应结构"""

    @pytest.mark.asyncio
    async def test_catalog_has_execution_field(self):
        result = await build_check_catalog(None)
        for s in result["sources"]:
            assert "execution" in s, f"来源 {s['key']} 缺少 execution 字段"
        assert "wired_count" in result

    @pytest.mark.asyncio
    async def test_wired_count_only_counts_wired(self):
        result = await build_check_catalog(None)
        manual_count = sum(1 for s in result["sources"] if s["execution"] == "wired")
        assert result["wired_count"] == manual_count


class TestLastRun:
    """S2 ADR-CCN-03：last_run 逻辑"""

    @pytest.mark.asyncio
    async def test_no_project_id_no_last_run_data(self):
        """不带 project_id 时，有 result_table 的来源只标注「不落库」或无 last_run 数据键"""
        result = await build_check_catalog(None)
        for s in result["sources"]:
            if s.get("result_table") is None:
                # 不落库来源标注
                assert s.get("last_run") is None
                assert s.get("last_run_note") == "本类结果不落库"
            # 有 result_table 但无 project_id → 不查（无 last_run 键）
            # 这些来源在无 project_id 时 _summary 里 last_run 参数为 None

    @pytest.mark.asyncio
    async def test_with_project_id_queries_last_run(self):
        """带 project_id 时，有 result_table 的来源查询 last_run"""
        mock_db = AsyncMock()
        # mock db.execute 返回空结果（never_run）
        mock_mapping = MagicMock()
        mock_mapping.mappings.return_value.one_or_none.return_value = {
            "last_at": None, "total": 0, "failed": 0,
        }
        mock_db.execute = AsyncMock(return_value=mock_mapping)
        # begin_nested for from_db sources
        mock_db.begin_nested = AsyncMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_db),
            __aexit__=AsyncMock(),
        ))
        # scalars() for from_db sources
        mock_scalars = MagicMock()
        mock_scalars.scalars.return_value = []
        # We need to handle multiple execute calls differently
        call_count = [0]
        original_execute = mock_db.execute

        async def smart_execute(*args, **kwargs):
            call_count[0] += 1
            # Return scalars mock for ORM queries, mapping mock for text queries
            arg0 = args[0] if args else None
            if hasattr(arg0, 'text') or (isinstance(arg0, str)):
                return mock_mapping
            # Check if it's a sa.text() call
            import sqlalchemy as sa
            if isinstance(arg0, sa.sql.elements.TextClause):
                return mock_mapping
            # ORM select
            return mock_scalars

        mock_db.execute = AsyncMock(side_effect=smart_execute)

        pid = UUID("00000000-0000-0000-0000-000000000099")
        result = await build_check_catalog(mock_db, project_id=pid)
        # 有 result_table 的来源应有 last_run
        for s in result["sources"]:
            if s.get("result_table") is not None:
                assert "last_run" in s, f"来源 {s['key']} 带 project_id 时应有 last_run"

    @pytest.mark.asyncio
    async def test_no_result_table_last_run_null_with_note(self):
        """没有 result_table 的来源 → last_run=null + 注明不落库"""
        result = await build_check_catalog(None)
        no_table = [s for s in result["sources"] if s.get("result_table") is None]
        assert len(no_table) > 0
        for s in no_table:
            assert s.get("last_run") is None
            assert "不落库" in s.get("last_run_note", "")
