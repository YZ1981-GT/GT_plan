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
        """真实类型不一致（如 INTEGER vs VARCHAR）应报 type_mismatch。

        注：TIMESTAMP↔TIMESTAMPTZ 被 _types_compatible 刻意视为兼容（消除假阳性），
        故此处用 INTEGER vs VARCHAR 这种真正不兼容的组合验证 mismatch 检出。
        """
        det = SchemaDriftDetector(sqlite_engine)
        orm = {"users": {"age": {"type": "INTEGER", "nullable": True}}}
        db = {"users": {"age": {"type": "VARCHAR", "nullable": True}}}
        items = det._diff_columns(orm, db)
        assert len(items) == 1
        assert items[0].drift_type == "type_mismatch"
        assert "INTEGER" in items[0].detail
        assert "VARCHAR" in items[0].detail

    def test_timestamp_tz_compatible_no_false_positive(self, sqlite_engine):
        """TIMESTAMP ↔ TIMESTAMPTZ 视为兼容（时区差异不影响存取），不报 mismatch。"""
        det = SchemaDriftDetector(sqlite_engine)
        orm = {"users": {"created_at": {"type": "TIMESTAMP", "nullable": True}}}
        db = {"users": {"created_at": {"type": "TIMESTAMPTZ", "nullable": True}}}
        items = det._diff_columns(orm, db)
        assert items == []

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

    def test_v154_override_version_table_allowlisted_and_unmapped(self):
        """V154 版本台账：在 allowlist **且** 无 ORM 模型 —— 两条双向锁死。

        为什么两条一起断言而不是只断言 allowlist：

        单断言「在 allowlist」是**单向**的。将来有人给这张表补了 ORM 模型
        （合理动机：想用 ORM 查版本列表），allowlist 条目会留在原地，于是
        该表的**列级**漂移（ORM 加了列但迁移漏跑 → orm_extra）会被整表跳过
        —— allowlist 从「屏蔽已知噪音」退化成「掩盖真漂移」。这正是 memory
        里记的假绿第③源（守卫把错状态当基线锁死）。

        所以判据是：要么两者都成立（当前设计：裸 SQL + allowlist），
        要么两者都不成立（补了 ORM 模型就必须同时删 allowlist 条目）。

        表名不写字面量，从服务层的单一真源取 —— 避免两处各写一遍字面量后
        改一处漏一处（那样这条守卫会变成永真）。
        """
        from app.services.wp_template_override import OVERRIDE_VERSION_TABLE

        assert OVERRIDE_VERSION_TABLE in SchemaDriftDetector.KNOWN_ALLOWLIST, (
            f"{OVERRIDE_VERSION_TABLE} 不在 allowlist —— 启动会报 db_extra 漂移噪音。"
            "若已为它补 ORM 模型，请改本测试的另一半断言而不是删这一半"
        )

        # ORM 侧必须查不到它。用 detector 自己的 _import_all_models 保证
        # Base.metadata 完整（只 import app.models.__init__ 会漏 30+ 模块，
        # 那样这条断言会因 metadata 不完整而恒真 = 守卫缺陷）。
        SchemaDriftDetector._import_all_models()
        from app.models.base import Base

        mapped = {t.lower() for t in Base.metadata.tables.keys()}
        assert OVERRIDE_VERSION_TABLE not in mapped, (
            f"{OVERRIDE_VERSION_TABLE} 已被 ORM 映射，但仍留在 KNOWN_ALLOWLIST 里 —— "
            "整表被跳过后，它的列级漂移（如 ORM 加列而迁移漏跑）永远检测不到。"
            "请从 KNOWN_ALLOWLIST 删除该条目，并复核 V154 的三条触发器约束"
            "（不可变 / 禁删 / is_current 部分唯一索引）是否仍由 DB 承载"
        )

    def test_v155_oo_content_revision_table_allowlisted_and_unmapped(self):
        """V155 OO 内容修订号表：在 allowlist **且** 无 ORM 模型 —— 两条双向锁死。

        与上面 V154 那条同构（理由见其 docstring），本表的设计裁决理由不同：
        `revision` 的推进靠 `ON CONFLICT DO UPDATE SET revision = <表名>.revision + 1`
        在 DB 侧原子自增。映射进 ORM 后 `row.revision = x` 能绕过原子性，读-改-写竞态
        下两次改写会拿到同一个号 ⇒ doc_key 不轮转 ⇒ 退回「服务端已写盘、OO 仍显示空
        模板」那个缺陷。

        表名同样从服务层的单一真源取，不写字面量 —— 两处各写一遍字面量后改一处漏一处，
        这条守卫会退化成永真。
        """
        from app.services.onlyoffice_room_identity import OO_CONTENT_REVISION_TABLE

        assert OO_CONTENT_REVISION_TABLE in SchemaDriftDetector.KNOWN_ALLOWLIST, (
            f"{OO_CONTENT_REVISION_TABLE} 不在 allowlist —— 启动会报 db_extra 漂移噪音。"
            "若已为它补 ORM 模型，请改本测试的另一半断言而不是删这一半"
        )

        SchemaDriftDetector._import_all_models()
        from app.models.base import Base

        mapped = {t.lower() for t in Base.metadata.tables.keys()}
        assert OO_CONTENT_REVISION_TABLE not in mapped, (
            f"{OO_CONTENT_REVISION_TABLE} 已被 ORM 映射，但仍留在 KNOWN_ALLOWLIST 里 —— "
            "整表被跳过后，它的列级漂移（如 ORM 加列而迁移漏跑）永远检测不到。"
            "请从 KNOWN_ALLOWLIST 删除该条目，并复核 revision 自增是否仍由 DB 侧"
            "ON CONFLICT DO UPDATE 承载（而非 Python 侧读-改-写）"
        )


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
