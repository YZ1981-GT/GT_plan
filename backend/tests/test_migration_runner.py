"""MigrationRunner 单元测试 — 使用 SQLite 内存数据库验证迁移流程。

注意：SQLite 不支持 PL/pgSQL（DO $$ ... END $$;），所以测试用简单 DDL。
"""

import hashlib
import textwrap
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.migration_runner import MigrationRunner, MigrationFile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def sqlite_engine():
    """创建 SQLite 内存异步引擎。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture
def tmp_migrations(tmp_path: Path) -> Path:
    """创建临时迁移目录，包含 3 个测试用 SQL 脚本。"""
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()

    # V001: 基线（空操作）
    (mig_dir / "V001__init.sql").write_text(
        "-- baseline, no-op\n", encoding="utf-8"
    )

    # V002: 创建 schema_version 表（SQLite 兼容语法）
    (mig_dir / "V002__add_schema_version.sql").write_text(textwrap.dedent("""\
        CREATE TABLE IF NOT EXISTS schema_version (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            version   VARCHAR(20)  NOT NULL UNIQUE,
            filename  VARCHAR(255) NOT NULL,
            applied_at TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
            checksum  VARCHAR(64)  NOT NULL
        );
    """), encoding="utf-8")

    # V003: 创建一个示例表
    (mig_dir / "V003__create_demo.sql").write_text(
        "CREATE TABLE IF NOT EXISTS demo (id INTEGER PRIMARY KEY, note TEXT);\n",
        encoding="utf-8",
    )

    return mig_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestScanMigrations:
    """scan_migrations() 测试。"""

    def test_scan_finds_all_sql_files(self, tmp_migrations: Path):
        runner = MigrationRunner(database_url="sqlite+aiosqlite:///:memory:", migrations_dir=tmp_migrations)
        files = runner.scan_migrations()
        assert len(files) == 3
        assert [f.version for f in files] == ["001", "002", "003"]

    def test_scan_sorted_by_version(self, tmp_migrations: Path):
        # 添加一个 V010 文件
        (tmp_migrations / "V010__later.sql").write_text("-- later\n", encoding="utf-8")
        runner = MigrationRunner(database_url="sqlite+aiosqlite:///:memory:", migrations_dir=tmp_migrations)
        files = runner.scan_migrations()
        versions = [int(f.version) for f in files]
        assert versions == sorted(versions)

    def test_scan_ignores_non_matching_files(self, tmp_migrations: Path):
        (tmp_migrations / "README.md").write_text("# readme\n", encoding="utf-8")
        (tmp_migrations / "notes.txt").write_text("notes\n", encoding="utf-8")
        runner = MigrationRunner(database_url="sqlite+aiosqlite:///:memory:", migrations_dir=tmp_migrations)
        files = runner.scan_migrations()
        # 仍然只有 3 个 V*.sql 文件
        assert len(files) == 3

    def test_scan_empty_dir(self, tmp_path: Path):
        empty = tmp_path / "empty_mig"
        empty.mkdir()
        runner = MigrationRunner(database_url="sqlite+aiosqlite:///:memory:", migrations_dir=empty)
        assert runner.scan_migrations() == []

    def test_scan_missing_dir(self, tmp_path: Path):
        runner = MigrationRunner(
            database_url="sqlite+aiosqlite:///:memory:",
            migrations_dir=tmp_path / "nonexistent",
        )
        assert runner.scan_migrations() == []

    def test_checksum_is_sha256(self, tmp_migrations: Path):
        runner = MigrationRunner(database_url="sqlite+aiosqlite:///:memory:", migrations_dir=tmp_migrations)
        files = runner.scan_migrations()
        for f in files:
            content = f.path.read_text(encoding="utf-8")
            expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
            assert f.checksum == expected


class TestEnsureSchemaVersionTable:
    """ensure_schema_version_table() 测试。"""

    async def test_creates_table_and_marks_v001(self, sqlite_engine, tmp_migrations: Path):
        """首次运行时应创建 schema_version 表并标记 V001。"""
        # SQLite 版本的 schema_version DDL（覆盖模块级常量）
        import app.core.migration_runner as mod
        original_ddl = mod._SCHEMA_VERSION_DDL
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
            runner = MigrationRunner(engine=sqlite_engine, migrations_dir=tmp_migrations)
            await runner.ensure_schema_version_table()

            async with sqlite_engine.begin() as conn:
                result = await conn.execute(text("SELECT version, filename FROM schema_version"))
                rows = result.fetchall()
                assert len(rows) == 1
                assert rows[0][0] == "001"
                assert rows[0][1] == "V001__init.sql"
        finally:
            mod._SCHEMA_VERSION_DDL = original_ddl

    async def test_idempotent(self, sqlite_engine, tmp_migrations: Path):
        """多次调用不会重复插入。"""
        import app.core.migration_runner as mod
        original_ddl = mod._SCHEMA_VERSION_DDL
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
            runner = MigrationRunner(engine=sqlite_engine, migrations_dir=tmp_migrations)
            await runner.ensure_schema_version_table()
            await runner.ensure_schema_version_table()  # 第二次调用

            async with sqlite_engine.begin() as conn:
                result = await conn.execute(text("SELECT COUNT(*) FROM schema_version"))
                assert result.scalar() == 1  # 仍然只有 V001
        finally:
            mod._SCHEMA_VERSION_DDL = original_ddl


class TestRunPending:
    """run_pending() 完整流程测试。"""

    async def test_runs_all_pending(self, sqlite_engine, tmp_migrations: Path):
        """首次运行应执行 V002 和 V003（V001 被 ensure 自动标记）。"""
        import app.core.migration_runner as mod
        original_ddl = mod._SCHEMA_VERSION_DDL
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
            runner = MigrationRunner(engine=sqlite_engine, migrations_dir=tmp_migrations)
            executed = await runner.run_pending()

            # V001 被 ensure 标记，V002 和 V003 被执行
            assert "002" in executed
            assert "003" in executed
            assert "001" not in executed  # V001 已被 ensure 标记

            # 验证 demo 表已创建（V003）
            async with sqlite_engine.begin() as conn:
                result = await conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='demo'"
                ))
                assert result.fetchone() is not None

            # 验证 schema_version 记录了所有版本
            applied = await runner.get_applied_versions()
            assert applied == {"001", "002", "003"}
        finally:
            mod._SCHEMA_VERSION_DDL = original_ddl

    async def test_second_run_is_noop(self, sqlite_engine, tmp_migrations: Path):
        """第二次运行不应执行任何迁移。"""
        import app.core.migration_runner as mod
        original_ddl = mod._SCHEMA_VERSION_DDL
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
            runner = MigrationRunner(engine=sqlite_engine, migrations_dir=tmp_migrations)
            await runner.run_pending()  # 第一次
            executed = await runner.run_pending()  # 第二次
            assert executed == []
        finally:
            mod._SCHEMA_VERSION_DDL = original_ddl

    async def test_incremental_migration(self, sqlite_engine, tmp_migrations: Path):
        """添加新迁移文件后，只执行新增的。"""
        import app.core.migration_runner as mod
        original_ddl = mod._SCHEMA_VERSION_DDL
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
            runner = MigrationRunner(engine=sqlite_engine, migrations_dir=tmp_migrations)
            await runner.run_pending()  # 执行 V001-V003

            # 添加 V004
            (tmp_migrations / "V004__add_column.sql").write_text(
                "ALTER TABLE demo ADD COLUMN extra TEXT;\n", encoding="utf-8"
            )

            executed = await runner.run_pending()
            assert executed == ["004"]

            # 验证列已添加
            async with sqlite_engine.begin() as conn:
                result = await conn.execute(text("PRAGMA table_info(demo)"))
                columns = [row[1] for row in result.fetchall()]
                assert "extra" in columns
        finally:
            mod._SCHEMA_VERSION_DDL = original_ddl


class TestGetAppliedVersions:
    """get_applied_versions() 测试。"""

    async def test_empty_table(self, sqlite_engine, tmp_migrations: Path):
        """空 schema_version 表返回空集合（ensure 会标记 V001，所以手动创建空表）。"""
        import app.core.migration_runner as mod
        original_ddl = mod._SCHEMA_VERSION_DDL
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
            # 手动创建空表（不通过 ensure，避免自动标记 V001）
            async with sqlite_engine.begin() as conn:
                await conn.execute(text(mod._SCHEMA_VERSION_DDL))

            runner = MigrationRunner(engine=sqlite_engine, migrations_dir=tmp_migrations)
            versions = await runner.get_applied_versions()
            assert versions == set()
        finally:
            mod._SCHEMA_VERSION_DDL = original_ddl


class TestMigrationRunnerInit:
    """构造函数参数校验。"""

    def test_requires_url_or_engine(self):
        with pytest.raises(ValueError, match="必须提供"):
            MigrationRunner()

    def test_accepts_engine(self, sqlite_engine):
        runner = MigrationRunner(engine=sqlite_engine)
        assert runner._engine is sqlite_engine
        assert runner._owns_engine is False

    def test_accepts_url(self):
        runner = MigrationRunner(database_url="sqlite+aiosqlite:///:memory:")
        assert runner._owns_engine is True


class TestSplitSqlStatements:
    """_split_sql_statements() 单元测试 — 纯逻辑，无需数据库。"""

    # ------------------------------------------------------------------
    # 基础分割
    # ------------------------------------------------------------------

    def test_single_statement(self):
        sql = "CREATE TABLE foo (id INTEGER PRIMARY KEY);"
        stmts = MigrationRunner._split_sql_statements(sql)
        assert len(stmts) == 1
        assert stmts[0] == "CREATE TABLE foo (id INTEGER PRIMARY KEY)"

    def test_multiple_statements(self):
        sql = textwrap.dedent("""\
            CREATE TABLE foo (id INTEGER PRIMARY KEY);
            CREATE TABLE bar (id INTEGER PRIMARY KEY);
            CREATE TABLE baz (id INTEGER PRIMARY KEY);
        """)
        stmts = MigrationRunner._split_sql_statements(sql)
        assert len(stmts) == 3
        assert stmts[0].startswith("CREATE TABLE foo")
        assert stmts[1].startswith("CREATE TABLE bar")
        assert stmts[2].startswith("CREATE TABLE baz")

    def test_no_trailing_semicolon(self):
        """末尾没有分号的语句也应被收集。"""
        sql = "SELECT 1"
        stmts = MigrationRunner._split_sql_statements(sql)
        assert len(stmts) == 1
        assert stmts[0] == "SELECT 1"

    # ------------------------------------------------------------------
    # 过滤空语句和注释
    # ------------------------------------------------------------------

    def test_filters_empty_statements(self):
        """连续分号之间的空内容应被过滤。"""
        sql = "CREATE TABLE foo (id INTEGER);;; CREATE TABLE bar (id INTEGER);"
        stmts = MigrationRunner._split_sql_statements(sql)
        assert len(stmts) == 2

    def test_filters_comment_only_statements(self):
        """纯注释片段应被过滤。"""
        sql = textwrap.dedent("""\
            -- 这是注释
            CREATE TABLE foo (id INTEGER PRIMARY KEY);
            -- 另一条注释
            CREATE TABLE bar (id INTEGER PRIMARY KEY);
        """)
        stmts = MigrationRunner._split_sql_statements(sql)
        assert len(stmts) == 2
        assert all("CREATE TABLE" in s for s in stmts)

    def test_filters_whitespace_only(self):
        """纯空白内容应被过滤。"""
        sql = "   \n\t  "
        stmts = MigrationRunner._split_sql_statements(sql)
        assert stmts == []

    def test_comment_only_file(self):
        """全注释文件（如 V001__init.sql）应返回空列表。"""
        sql = "-- baseline, no-op\n"
        stmts = MigrationRunner._split_sql_statements(sql)
        assert stmts == []

    def test_inline_comment_preserved_in_statement(self):
        """语句内的行内注释应保留（不影响执行）。"""
        sql = textwrap.dedent("""\
            CREATE TABLE foo (
                id INTEGER PRIMARY KEY, -- 主键
                name TEXT               -- 名称
            );
        """)
        stmts = MigrationRunner._split_sql_statements(sql)
        assert len(stmts) == 1
        assert "CREATE TABLE foo" in stmts[0]

    # ------------------------------------------------------------------
    # 美元引号块（DO $$ ... END $$;）
    # ------------------------------------------------------------------

    def test_dollar_quote_block_not_split(self):
        """DO $$ ... END $$; 块内的分号不应触发分割。"""
        sql = textwrap.dedent("""\
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'my_enum') THEN
                    CREATE TYPE my_enum AS ENUM ('a', 'b', 'c');
                END IF;
            END
            $$;
        """)
        stmts = MigrationRunner._split_sql_statements(sql)
        # 整个 DO 块应作为一条语句
        assert len(stmts) == 1
        assert "DO $$" in stmts[0]
        assert "END IF;" in stmts[0]

    def test_dollar_quote_followed_by_normal_statement(self):
        """DO $$ 块后面跟普通语句，应正确分割为两条。"""
        sql = textwrap.dedent("""\
            DO $$
            BEGIN
                RAISE NOTICE 'hello; world';
            END
            $$;
            CREATE TABLE after_block (id INTEGER PRIMARY KEY);
        """)
        stmts = MigrationRunner._split_sql_statements(sql)
        assert len(stmts) == 2
        assert "DO $$" in stmts[0]
        assert "CREATE TABLE after_block" in stmts[1]

    def test_named_dollar_quote_tag(self):
        """$body$ 等命名标签也应正确处理。"""
        sql = textwrap.dedent("""\
            DO $body$
            BEGIN
                UPDATE foo SET x = 1 WHERE y = 2;
            END
            $body$;
        """)
        stmts = MigrationRunner._split_sql_statements(sql)
        assert len(stmts) == 1
        assert "$body$" in stmts[0]

    def test_multiple_statements_with_dollar_block(self):
        """多条普通语句 + DO 块的混合文件。"""
        sql = textwrap.dedent("""\
            CREATE TABLE t1 (id INTEGER PRIMARY KEY);
            CREATE TABLE t2 (id INTEGER PRIMARY KEY);
            DO $$
            BEGIN
                INSERT INTO t1 VALUES (1);
                INSERT INTO t2 VALUES (1);
            END
            $$;
            CREATE INDEX idx_t1 ON t1 (id);
        """)
        stmts = MigrationRunner._split_sql_statements(sql)
        assert len(stmts) == 4
        assert stmts[0].startswith("CREATE TABLE t1")
        assert stmts[1].startswith("CREATE TABLE t2")
        assert "DO $$" in stmts[2]
        assert stmts[3].startswith("CREATE INDEX")

    # ------------------------------------------------------------------
    # 多语句迁移文件集成（SQLite 兼容）
    # ------------------------------------------------------------------

    async def test_multi_statement_migration_executes_all(
        self, sqlite_engine, tmp_path: Path
    ):
        """多语句 SQL 文件应逐条执行，所有表都被创建。"""
        import app.core.migration_runner as mod
        original_ddl = mod._SCHEMA_VERSION_DDL
        mod._SCHEMA_VERSION_DDL = textwrap.dedent("""\
            CREATE TABLE IF NOT EXISTS schema_version (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                version   VARCHAR(20)  NOT NULL UNIQUE,
                filename  VARCHAR(255) NOT NULL,
                applied_at TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
                checksum  VARCHAR(64)  NOT NULL
            );
        """)
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()

        # V001: 基线（纯注释，无实际语句）
        (mig_dir / "V001__init.sql").write_text("-- baseline\n", encoding="utf-8")

        # V002: 多语句迁移（SQLite 兼容）
        (mig_dir / "V002__multi_stmt.sql").write_text(textwrap.dedent("""\
            -- 创建两张表
            CREATE TABLE IF NOT EXISTS alpha (id INTEGER PRIMARY KEY, val TEXT);
            CREATE TABLE IF NOT EXISTS beta (id INTEGER PRIMARY KEY, val TEXT);
            -- 插入初始数据
            INSERT INTO alpha (id, val) VALUES (1, 'hello');
            INSERT INTO beta (id, val) VALUES (1, 'world');
        """), encoding="utf-8")

        try:
            runner = MigrationRunner(engine=sqlite_engine, migrations_dir=mig_dir)
            executed = await runner.run_pending()

            assert "002" in executed

            async with sqlite_engine.begin() as conn:
                # 验证两张表都已创建
                for table in ("alpha", "beta"):
                    result = await conn.execute(text(
                        f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
                    ))
                    assert result.fetchone() is not None, f"表 {table} 未创建"

                # 验证数据已插入
                r = await conn.execute(text("SELECT val FROM alpha WHERE id=1"))
                assert r.scalar() == "hello"

                r = await conn.execute(text("SELECT val FROM beta WHERE id=1"))
                assert r.scalar() == "world"
        finally:
            mod._SCHEMA_VERSION_DDL = original_ddl

    async def test_comment_only_migration_executes_without_error(
        self, sqlite_engine, tmp_path: Path
    ):
        """纯注释迁移文件（如 V001）应正常执行，不报错。"""
        import app.core.migration_runner as mod
        original_ddl = mod._SCHEMA_VERSION_DDL
        mod._SCHEMA_VERSION_DDL = textwrap.dedent("""\
            CREATE TABLE IF NOT EXISTS schema_version (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                version   VARCHAR(20)  NOT NULL UNIQUE,
                filename  VARCHAR(255) NOT NULL,
                applied_at TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
                checksum  VARCHAR(64)  NOT NULL
            );
        """)
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()

        (mig_dir / "V001__init.sql").write_text("-- baseline, no-op\n", encoding="utf-8")
        (mig_dir / "V002__comment_only.sql").write_text(
            "-- 这个文件只有注释\n-- 没有实际 SQL\n", encoding="utf-8"
        )

        try:
            runner = MigrationRunner(engine=sqlite_engine, migrations_dir=mig_dir)
            # 不应抛出异常
            executed = await runner.run_pending()
            assert "002" in executed
        finally:
            mod._SCHEMA_VERSION_DDL = original_ddl
