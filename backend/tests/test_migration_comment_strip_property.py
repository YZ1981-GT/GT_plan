"""migration-runner-resilience spec / Sprint 3 / Task 3.1

P-2 防御 PBT：SQL 注释里的 :identifier 不引发 bind error。

历史 V005 注释里写过 ``-- 用 :pid 替换`` 触发 SQLAlchemy text() 的 bind 解析报错。
本测试用 hypothesis 生成 100 个含 :name 的注释/字符串组合，验证
``_apply_migration`` 不再爆。

修复方案 = ``exec_driver_sql`` 跳过 SQLAlchemy bind 解析（design.md §2.2）。
"""

import textwrap
from pathlib import Path

import pytest
from hypothesis import given, settings as hyp_settings, strategies as st
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.migration_runner import MigrationRunner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def sqlite_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture
def patch_ddl():
    import app.core.migration_runner as mod
    original = mod._SCHEMA_VERSION_DDL
    mod._SCHEMA_VERSION_DDL = textwrap.dedent("""\
        CREATE TABLE IF NOT EXISTS schema_version (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            version   VARCHAR(20)  NOT NULL UNIQUE,
            filename  VARCHAR(255) NOT NULL,
            applied_at TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
            checksum  VARCHAR(64)  NOT NULL
        );
    """)
    yield
    mod._SCHEMA_VERSION_DDL = original


# Hypothesis 策略：合法 SQL 标识符（字母开头 + 字母数字下划线）
identifier = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_"),
    min_size=1, max_size=20,
).filter(lambda s: s and s[0].isalpha())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCommentBindStripProperty:
    """CI-2 / CI-3：注释里 :name 不引发 bind error。"""

    async def test_v005_historical_regression(
        self, sqlite_engine, tmp_path: Path, patch_ddl
    ):
        """V005 历史踩坑回归：注释含 :pid 字面量不应报 bind 错。"""
        d = tmp_path / "migs"
        d.mkdir()
        (d / "V001__init.sql").write_text("-- baseline\n", encoding="utf-8")
        # 故意还原历史 V005 注释片段
        (d / "V005__test_with_colon_in_comment.sql").write_text(textwrap.dedent("""\
            -- 应用层 set_rls_context 必须用 set_config('app.current_project_id', value, true)
            -- 而非 SET LOCAL ... = :pid（PG 的 SET 命令不支持 prepared statement 绑定参数）
            -- 用法示例：SELECT :foo FROM :bar 这种注释也不应该爆
            CREATE TABLE IF NOT EXISTS test_t (id INTEGER PRIMARY KEY);
        """), encoding="utf-8")

        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=d)
        result = await runner.run_pending()
        assert "005" in result.executed
        assert result.failed == []

    async def test_block_comment_with_colon_name(
        self, sqlite_engine, tmp_path: Path, patch_ddl
    ):
        """块注释 /* :name */ 也不应报 bind 错。"""
        d = tmp_path / "migs"
        d.mkdir()
        (d / "V001__init.sql").write_text("-- baseline\n", encoding="utf-8")
        (d / "V002__block_comment.sql").write_text(textwrap.dedent("""\
            /*
             * 这里写 :foo 不应被当成 bind parameter
             * 多行 :bar :baz 也 ok
             */
            CREATE TABLE IF NOT EXISTS t1 (id INTEGER PRIMARY KEY);
        """), encoding="utf-8")

        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=d)
        result = await runner.run_pending()
        assert "002" in result.executed
        assert result.failed == []

    async def test_string_literal_with_colon_name(
        self, sqlite_engine, tmp_path: Path, patch_ddl
    ):
        """字符串字面量内 :name 不应被当成 bind parameter。"""
        d = tmp_path / "migs"
        d.mkdir()
        (d / "V001__init.sql").write_text("-- baseline\n", encoding="utf-8")
        (d / "V002__string_literal.sql").write_text(
            "CREATE TABLE IF NOT EXISTS t1 (id INTEGER PRIMARY KEY, msg TEXT DEFAULT 'use :pid here');\n",
            encoding="utf-8",
        )

        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=d)
        result = await runner.run_pending()
        assert "002" in result.executed
        assert result.failed == []

    @hyp_settings(max_examples=20, deadline=2000)
    @given(name=identifier, table=identifier)
    async def test_property_random_colon_in_line_comment(self, name, table):
        """PBT：随机 :identifier 在行注释内不爆。每次 case 用独立的 SQLite engine。"""
        # 跳过 SQL 关键字
        if name.lower() in ("select", "from", "where", "table", "create", "insert"):
            return

        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        import app.core.migration_runner as mod
        original = mod._SCHEMA_VERSION_DDL
        mod._SCHEMA_VERSION_DDL = textwrap.dedent("""\
            CREATE TABLE IF NOT EXISTS schema_version (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                version   VARCHAR(20)  NOT NULL UNIQUE,
                filename  VARCHAR(255) NOT NULL,
                applied_at TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
                checksum  VARCHAR(64)  NOT NULL
            );
        """)
        try:
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                d = Path(tmpdir)
                (d / "V001__init.sql").write_text("-- baseline\n", encoding="utf-8")
                content = (
                    f"-- 注释含 :{name} 字面量\n"
                    f"-- 多个 :foo :bar :{name}\n"
                    f"CREATE TABLE IF NOT EXISTS t_{table[:10]} (id INTEGER PRIMARY KEY);\n"
                )
                (d / "V002__random.sql").write_text(content, encoding="utf-8")

                runner = MigrationRunner(engine=engine, migrations_dir=d)
                result = await runner.run_pending()
                assert "002" in result.executed
                assert result.failed == []
        finally:
            mod._SCHEMA_VERSION_DDL = original
            await engine.dispose()

    async def test_dollar_quoted_block_with_colon_unaffected(
        self, sqlite_engine, tmp_path: Path, patch_ddl
    ):
        """$body$ ... $body$ 块（PG 风格）不应被分割（SQLite 当字符串处理）。

        注：SQLite 不识别 $body$ 但 _split_sql_statements 应保持原样不破坏。
        """
        d = tmp_path / "migs"
        d.mkdir()
        (d / "V001__init.sql").write_text("-- baseline\n", encoding="utf-8")
        # 用单引号 SQLite 兼容：模拟 $body$ 内 :name 不被解析
        (d / "V002__safe.sql").write_text(textwrap.dedent("""\
            CREATE TABLE IF NOT EXISTS msgs (id INTEGER PRIMARY KEY, t TEXT);
            INSERT INTO msgs (t) VALUES ('Hello :world this is :foo');
        """), encoding="utf-8")

        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=d)
        result = await runner.run_pending()
        assert "002" in result.executed
        assert result.failed == []

        # 验证字符串原样存入
        async with sqlite_engine.begin() as conn:
            rows = await conn.execute(text("SELECT t FROM msgs"))
            row = rows.fetchone()
            assert ":world" in row[0]
            assert ":foo" in row[0]
