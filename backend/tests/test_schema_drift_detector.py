"""migration-runner-resilience spec / Sprint 2 / Task 2.5

SchemaDriftDetector 单元测试。

策略：
- 大部分逻辑（_diff_tables / _diff_columns / _normalize_type / _camel_to_snake）
  是纯函数，直接测
- 涉及 PG information_schema 的部分用 pg_only mark + 真 PG 跑（CI 可选）
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.schema_drift_detector import (
    DriftItem,
    SchemaDriftDetector,
    run_drift_check_with_timeout,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def sqlite_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    yield engine
    await engine.dispose()


# ---------------------------------------------------------------------------
# 纯函数测试
# ---------------------------------------------------------------------------

class TestNormalizeType:
    """_normalize_type：PG 别名归一。"""

    def test_varchar_with_length(self):
        assert SchemaDriftDetector._normalize_type("VARCHAR(100)") == "VARCHAR"

    def test_character_varying_alias(self):
        assert SchemaDriftDetector._normalize_type("CHARACTER VARYING") == "VARCHAR"

    def test_timestamp_with_tz(self):
        assert SchemaDriftDetector._normalize_type("TIMESTAMP WITH TIME ZONE") == "TIMESTAMPTZ"

    def test_int_aliases(self):
        assert SchemaDriftDetector._normalize_type("INT") == "INTEGER"
        assert SchemaDriftDetector._normalize_type("INT4") == "INTEGER"
        assert SchemaDriftDetector._normalize_type("INT8") == "BIGINT"

    def test_bool_alias(self):
        assert SchemaDriftDetector._normalize_type("BOOL") == "BOOLEAN"

    def test_empty_input(self):
        assert SchemaDriftDetector._normalize_type("") == ""


class TestCamelToSnake:
    def test_basic(self):
        assert SchemaDriftDetector._camel_to_snake("CamelCase") == "camel_case"

    def test_with_acronym(self):
        assert SchemaDriftDetector._camel_to_snake("APIResponse") == "api_response"

    def test_enum_suffix(self):
        assert SchemaDriftDetector._camel_to_snake("OpinionTypeEnum") == "opinion_type_enum"


class TestDiffTables:
    """_diff_tables：表级差异检测。"""

    def test_orm_extra_table(self, sqlite_engine):
        det = SchemaDriftDetector(sqlite_engine)
        orm = {"users": {}, "orders": {}}
        db = {"users": {}}
        items = det._diff_tables(orm, db)
        assert len(items) == 1
        assert items[0].drift_type == "orm_extra"
        assert items[0].table == "orders"
        assert items[0].column is None

    def test_db_extra_table(self, sqlite_engine):
        det = SchemaDriftDetector(sqlite_engine)
        orm = {"users": {}}
        db = {"users": {}, "legacy_t": {}}
        items = det._diff_tables(orm, db)
        assert len(items) == 1
        assert items[0].drift_type == "db_extra"
        assert items[0].table == "legacy_t"

    def test_no_diff(self, sqlite_engine):
        det = SchemaDriftDetector(sqlite_engine)
        orm = {"users": {}, "orders": {}}
        db = {"users": {}, "orders": {}}
        assert det._diff_tables(orm, db) == []


class TestDiffColumns:
    """_diff_columns：列级差异检测。"""

    def test_orm_extra_column(self, sqlite_engine):
        det = SchemaDriftDetector(sqlite_engine)
        orm = {"users": {"id": {"type": "INTEGER", "nullable": False},
                         "email": {"type": "VARCHAR", "nullable": False}}}
        db = {"users": {"id": {"type": "INTEGER", "nullable": False}}}
        items = det._diff_columns(orm, db)
        assert len(items) == 1
        assert items[0].drift_type == "orm_extra"
        assert items[0].table == "users"
        assert items[0].column == "email"

    def test_db_extra_column(self, sqlite_engine):
        det = SchemaDriftDetector(sqlite_engine)
        orm = {"users": {"id": {"type": "INTEGER", "nullable": False}}}
        db = {"users": {"id": {"type": "INTEGER", "nullable": False},
                        "deprecated_col": {"type": "TEXT", "nullable": True}}}
        items = det._diff_columns(orm, db)
        assert len(items) == 1
        assert items[0].drift_type == "db_extra"
        assert items[0].column == "deprecated_col"

    def test_type_mismatch(self, sqlite_engine):
        det = SchemaDriftDetector(sqlite_engine)
        orm = {"users": {"created_at": {"type": "TIMESTAMP", "nullable": True}}}
        db = {"users": {"created_at": {"type": "TIMESTAMPTZ", "nullable": True}}}
        items = det._diff_columns(orm, db)
        assert len(items) == 1
        assert items[0].drift_type == "type_mismatch"
        assert "TIMESTAMP" in items[0].detail
        assert "TIMESTAMPTZ" in items[0].detail

    def test_alias_normalized_no_false_positive(self, sqlite_engine):
        """VARCHAR(100) vs CHARACTER VARYING 应归一，不报 mismatch。"""
        det = SchemaDriftDetector(sqlite_engine)
        orm = {"users": {"name": {"type": "VARCHAR(100)", "nullable": True}}}
        db = {"users": {"name": {"type": "CHARACTER VARYING", "nullable": True}}}
        items = det._diff_columns(orm, db)
        assert items == []


class TestKnownAllowlist:
    """KNOWN_ALLOWLIST：系统/历史残留表不参与 drift。"""

    def test_allowlist_contains_system_tables(self):
        assert "schema_version" in SchemaDriftDetector.KNOWN_ALLOWLIST
        assert "schema_migration_failures" in SchemaDriftDetector.KNOWN_ALLOWLIST
        assert "schema_drift_log" in SchemaDriftDetector.KNOWN_ALLOWLIST
        assert "alembic_version" in SchemaDriftDetector.KNOWN_ALLOWLIST


class TestNonPgSkip:
    """非 PG 方言（SQLite 测试）退化为返回空。"""

    async def test_scan_returns_empty_on_sqlite(self, sqlite_engine):
        det = SchemaDriftDetector(sqlite_engine)
        items = await det.scan()
        assert items == []

    async def test_write_log_noop_on_sqlite(self, sqlite_engine):
        det = SchemaDriftDetector(sqlite_engine)
        # 不应抛异常
        await det.write_log([
            DriftItem(table="t1", column="c1", drift_type="orm_extra", detail="test")
        ])

    async def test_query_drift_returns_empty_on_sqlite(self, sqlite_engine):
        items = await SchemaDriftDetector.query_drift(sqlite_engine)
        assert items == []


class TestRunDriftCheckWithTimeout:
    """run_drift_check_with_timeout：超时和异常隔离。"""

    async def test_timeout_returns_empty(self, sqlite_engine):
        """超时后返回空列表，不抛异常。"""
        async def slow_scan(self):
            await asyncio.sleep(2)
            return []

        with patch.object(SchemaDriftDetector, "scan", new=slow_scan):
            items = await run_drift_check_with_timeout(sqlite_engine, timeout_seconds=0.1)
            assert items == []

    async def test_exception_returns_empty(self, sqlite_engine):
        """scan 抛异常后返回空列表，不阻塞启动。"""
        async def boom_scan(self):
            raise RuntimeError("simulated failure")

        with patch.object(SchemaDriftDetector, "scan", new=boom_scan):
            items = await run_drift_check_with_timeout(sqlite_engine)
            assert items == []

    async def test_normal_returns_items(self, sqlite_engine):
        """正常 scan + write_log 走通。"""
        sample_items = [
            DriftItem(table="t1", column="c1", drift_type="orm_extra", detail="test"),
        ]

        async def good_scan(self):
            return sample_items

        async def noop_write(self, items):
            pass

        with patch.object(SchemaDriftDetector, "scan", new=good_scan), \
             patch.object(SchemaDriftDetector, "write_log", new=noop_write):
            items = await run_drift_check_with_timeout(sqlite_engine)
            assert items == sample_items
