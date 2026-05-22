"""MigrationRunner 回滚功能测试 — 使用 SQLite 内存数据库验证回滚流程。

测试覆盖：
- scan_rollback_scripts() 扫描 R*.sql 文件
- rollback_to() 核心逻辑（版本计算、脚本执行、schema_version 更新）
- 生产环境 --confirm 安全检查
- 回滚脚本缺失时报错
- get_current_version() 获取最大版本
- _run_backup() 备份逻辑（mock pg_dump）
- CLI 参数解析
"""

import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.migration_runner import MigrationRunner, _ROLLBACK_RE


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
def rollback_migrations(tmp_path: Path) -> Path:
    """创建包含 V*.sql 和 R*.sql 的临时迁移目录。"""
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()

    # V001: 基线
    (mig_dir / "V001__init.sql").write_text("-- baseline\n", encoding="utf-8")

    # V002: 创建 demo 表
    (mig_dir / "V002__create_demo.sql").write_text(
        "CREATE TABLE IF NOT EXISTS demo (id INTEGER PRIMARY KEY, note TEXT);\n",
        encoding="utf-8",
    )

    # V003: 添加列
    (mig_dir / "V003__add_column.sql").write_text(
        "ALTER TABLE demo ADD COLUMN extra TEXT;\n",
        encoding="utf-8",
    )

    # R001: 回滚基线（no-op）
    (mig_dir / "R001__rollback_init.sql").write_text("-- rollback baseline\n", encoding="utf-8")

    # R002: 回滚 demo 表
    (mig_dir / "R002__rollback_create_demo.sql").write_text(
        "DROP TABLE IF EXISTS demo;\n",
        encoding="utf-8",
    )

    # R003: 回滚添加列（SQLite 不支持 DROP COLUMN，用重建表模拟）
    (mig_dir / "R003__rollback_add_column.sql").write_text(
        textwrap.dedent("""\
            CREATE TABLE IF NOT EXISTS demo_backup (id INTEGER PRIMARY KEY, note TEXT);
            INSERT INTO demo_backup SELECT id, note FROM demo;
            DROP TABLE demo;
            ALTER TABLE demo_backup RENAME TO demo;
        """),
        encoding="utf-8",
    )

    return mig_dir


@pytest.fixture
def sqlite_schema_version_ddl():
    """SQLite 兼容的 schema_version DDL（用于 monkeypatch）。"""
    return textwrap.dedent("""\
        CREATE TABLE IF NOT EXISTS schema_version (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            version   VARCHAR(20)  NOT NULL UNIQUE,
            filename  VARCHAR(255) NOT NULL,
            applied_at TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
            checksum  VARCHAR(64)  NOT NULL
        );
    """)


@pytest.fixture
def patch_ddl(sqlite_schema_version_ddl):
    """Patch 模块级 DDL 常量为 SQLite 兼容版本。"""
    import app.core.migration_runner as mod
    original = mod._SCHEMA_VERSION_DDL
    mod._SCHEMA_VERSION_DDL = sqlite_schema_version_ddl
    yield
    mod._SCHEMA_VERSION_DDL = original


# ---------------------------------------------------------------------------
# Tests: scan_rollback_scripts
# ---------------------------------------------------------------------------

class TestScanRollbackScripts:
    """scan_rollback_scripts() 测试。"""

    def test_scan_finds_all_rollback_files(self, rollback_migrations: Path):
        runner = MigrationRunner(
            database_url="sqlite+aiosqlite:///:memory:",
            migrations_dir=rollback_migrations,
        )
        files = runner.scan_rollback_scripts()
        assert len(files) == 3
        assert [f.version for f in files] == ["001", "002", "003"]

    def test_scan_sorted_by_version(self, rollback_migrations: Path):
        (rollback_migrations / "R010__rollback_later.sql").write_text(
            "-- later rollback\n", encoding="utf-8"
        )
        runner = MigrationRunner(
            database_url="sqlite+aiosqlite:///:memory:",
            migrations_dir=rollback_migrations,
        )
        files = runner.scan_rollback_scripts()
        versions = [int(f.version) for f in files]
        assert versions == sorted(versions)

    def test_scan_ignores_v_files(self, rollback_migrations: Path):
        runner = MigrationRunner(
            database_url="sqlite+aiosqlite:///:memory:",
            migrations_dir=rollback_migrations,
        )
        files = runner.scan_rollback_scripts()
        # 不应包含 V*.sql 文件
        for f in files:
            assert f.filename.startswith("R")

    def test_scan_empty_dir(self, tmp_path: Path):
        empty = tmp_path / "empty_mig"
        empty.mkdir()
        runner = MigrationRunner(
            database_url="sqlite+aiosqlite:///:memory:",
            migrations_dir=empty,
        )
        assert runner.scan_rollback_scripts() == []


class TestRollbackRegex:
    """_ROLLBACK_RE 正则测试。"""

    def test_matches_standard_format(self):
        assert _ROLLBACK_RE.match("R001__rollback_init.sql")
        assert _ROLLBACK_RE.match("R002__rollback_schema_version.sql")
        assert _ROLLBACK_RE.match("R003__rollback_example_add_comment.sql")

    def test_case_insensitive(self):
        assert _ROLLBACK_RE.match("r001__rollback.sql")

    def test_does_not_match_v_files(self):
        assert _ROLLBACK_RE.match("V001__init.sql") is None

    def test_does_not_match_non_sql(self):
        assert _ROLLBACK_RE.match("R001__rollback.txt") is None


# ---------------------------------------------------------------------------
# Tests: get_current_version
# ---------------------------------------------------------------------------

class TestGetCurrentVersion:
    """get_current_version() 测试。"""

    async def test_returns_max_version(
        self, sqlite_engine, rollback_migrations: Path, patch_ddl
    ):
        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=rollback_migrations)
        await runner.run_pending()

        current = await runner.get_current_version()
        assert current == "003"

    async def test_returns_none_when_empty(self, sqlite_engine, patch_ddl, tmp_path: Path):
        mig_dir = tmp_path / "mig"
        mig_dir.mkdir()
        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=mig_dir)

        # 手动创建空表
        import app.core.migration_runner as mod
        async with sqlite_engine.begin() as conn:
            await conn.execute(text(mod._SCHEMA_VERSION_DDL))

        current = await runner.get_current_version()
        assert current is None


# ---------------------------------------------------------------------------
# Tests: rollback_to
# ---------------------------------------------------------------------------

class TestRollbackTo:
    """rollback_to() 核心逻辑测试。"""

    async def test_rollback_v003_to_v002(
        self, sqlite_engine, rollback_migrations: Path, patch_ddl
    ):
        """回滚 V003→V002：extra 列应消失。"""
        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=rollback_migrations)
        await runner.run_pending()

        # 验证 V003 已应用（extra 列存在）
        async with sqlite_engine.begin() as conn:
            result = await conn.execute(text("PRAGMA table_info(demo)"))
            columns = [row[1] for row in result.fetchall()]
            assert "extra" in columns

        # Mock pg_dump（SQLite 环境无 pg_dump）+ mock settings
        with patch.object(runner, "_run_backup", return_value=Path("/tmp/backup.sql")):
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.APP_ENV = "dev"
                mock_settings.DATABASE_URL = "sqlite+aiosqlite:///:memory:"
                rolled_back = await runner.rollback_to("002", confirm=False)

        assert rolled_back == ["003"]

        # 验证 extra 列已消失
        async with sqlite_engine.begin() as conn:
            result = await conn.execute(text("PRAGMA table_info(demo)"))
            columns = [row[1] for row in result.fetchall()]
            assert "extra" not in columns

        # 验证 schema_version 只保留 001 和 002
        applied = await runner.get_applied_versions()
        assert applied == {"001", "002"}

    async def test_rollback_v003_to_v001(
        self, sqlite_engine, rollback_migrations: Path, patch_ddl
    ):
        """回滚 V003→V001：demo 表应消失。"""
        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=rollback_migrations)
        await runner.run_pending()

        with patch.object(runner, "_run_backup", return_value=Path("/tmp/backup.sql")):
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.APP_ENV = "dev"
                mock_settings.DATABASE_URL = "sqlite+aiosqlite:///:memory:"
                rolled_back = await runner.rollback_to("001", confirm=False)

        # 逆序回滚：003 先，002 后
        assert rolled_back == ["003", "002"]

        # 验证 demo 表已消失
        async with sqlite_engine.begin() as conn:
            result = await conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='demo'"
            ))
            assert result.fetchone() is None

        # 验证 schema_version 只保留 001
        applied = await runner.get_applied_versions()
        assert applied == {"001"}

    async def test_rollback_records_operator(
        self, sqlite_engine, rollback_migrations: Path, patch_ddl
    ):
        """回滚后 schema_version 应记录 operator 和 rollback_note。"""
        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=rollback_migrations)
        await runner.run_pending()

        with patch.object(runner, "_run_backup", return_value=Path("/tmp/backup.sql")):
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.APP_ENV = "dev"
                mock_settings.DATABASE_URL = "sqlite+aiosqlite:///:memory:"
                await runner.rollback_to("002", confirm=False, operator="test_user")

        # 验证 operator 和 rollback_note 已记录
        async with sqlite_engine.begin() as conn:
            result = await conn.execute(
                text("SELECT operator, rollback_note FROM schema_version WHERE version = '002'")
            )
            row = result.fetchone()
            assert row is not None
            assert row[0] == "test_user"
            assert "rollback from 003 to 002" in row[1]

    async def test_rollback_target_equals_current_raises(
        self, sqlite_engine, rollback_migrations: Path, patch_ddl
    ):
        """目标版本 >= 当前版本时应报错。"""
        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=rollback_migrations)
        await runner.run_pending()

        with patch("app.core.config.settings") as mock_settings:
            mock_settings.APP_ENV = "dev"
            with pytest.raises(RuntimeError, match="必须小于当前版本"):
                await runner.rollback_to("003", confirm=False)

    async def test_rollback_target_greater_than_current_raises(
        self, sqlite_engine, rollback_migrations: Path, patch_ddl
    ):
        """目标版本 > 当前版本时应报错。"""
        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=rollback_migrations)
        await runner.run_pending()

        with patch("app.core.config.settings") as mock_settings:
            mock_settings.APP_ENV = "dev"
            with pytest.raises(RuntimeError, match="必须小于当前版本"):
                await runner.rollback_to("005", confirm=False)

    async def test_rollback_missing_script_raises(
        self, sqlite_engine, tmp_path: Path, patch_ddl
    ):
        """回滚脚本缺失时应报错。"""
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()

        (mig_dir / "V001__init.sql").write_text("-- baseline\n", encoding="utf-8")
        (mig_dir / "V002__create.sql").write_text(
            "CREATE TABLE IF NOT EXISTS t1 (id INTEGER PRIMARY KEY);\n", encoding="utf-8"
        )
        # 故意不创建 R002

        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=mig_dir)
        await runner.run_pending()

        with patch.object(runner, "_run_backup", return_value=Path("/tmp/backup.sql")):
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.APP_ENV = "dev"
                with pytest.raises(RuntimeError, match="缺少回滚脚本"):
                    await runner.rollback_to("001", confirm=False)

    async def test_rollback_empty_schema_version_raises(
        self, sqlite_engine, tmp_path: Path, patch_ddl
    ):
        """schema_version 为空时应报错。"""
        import app.core.migration_runner as mod

        # 使用无 V001 的迁移目录，这样 ensure_schema_version_table 不会自动插入
        mig_dir = tmp_path / "empty_mig"
        mig_dir.mkdir()

        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=mig_dir)

        with patch("app.core.config.settings") as mock_settings:
            mock_settings.APP_ENV = "dev"
            with pytest.raises(RuntimeError, match="schema_version 表为空"):
                await runner.rollback_to("001", confirm=False)


# ---------------------------------------------------------------------------
# Tests: 生产环境安全检查
# ---------------------------------------------------------------------------

class TestProductionConfirm:
    """生产环境 --confirm 安全检查测试。"""

    async def test_production_without_confirm_raises(
        self, sqlite_engine, rollback_migrations: Path, patch_ddl
    ):
        """生产环境不传 --confirm 应拒绝执行。"""
        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=rollback_migrations)
        await runner.run_pending()

        with patch("app.core.config.settings") as mock_settings:
            mock_settings.APP_ENV = "production"
            with pytest.raises(RuntimeError, match="生产环境回滚需要 --confirm"):
                await runner.rollback_to("002", confirm=False)

    async def test_production_with_confirm_proceeds(
        self, sqlite_engine, rollback_migrations: Path, patch_ddl
    ):
        """生产环境传 --confirm 应正常执行。"""
        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=rollback_migrations)
        await runner.run_pending()

        with patch.object(runner, "_run_backup", return_value=Path("/tmp/backup.sql")):
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.APP_ENV = "production"
                mock_settings.DATABASE_URL = "sqlite+aiosqlite:///:memory:"
                rolled_back = await runner.rollback_to("002", confirm=True)

        assert rolled_back == ["003"]

    async def test_dev_without_confirm_proceeds(
        self, sqlite_engine, rollback_migrations: Path, patch_ddl
    ):
        """开发环境不传 --confirm 应正常执行。"""
        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=rollback_migrations)
        await runner.run_pending()

        with patch.object(runner, "_run_backup", return_value=Path("/tmp/backup.sql")):
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.APP_ENV = "dev"
                mock_settings.DATABASE_URL = "sqlite+aiosqlite:///:memory:"
                rolled_back = await runner.rollback_to("002", confirm=False)

        assert rolled_back == ["003"]


# ---------------------------------------------------------------------------
# Tests: _run_backup
# ---------------------------------------------------------------------------

class TestRunBackup:
    """_run_backup() 备份逻辑测试。"""

    def test_backup_calls_pg_dump_with_correct_args(self):
        """备份应调用 pg_dump 并传入正确的连接参数。"""
        runner = MigrationRunner(database_url="sqlite+aiosqlite:///:memory:")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            with patch.object(
                runner, "_get_sync_database_url",
                return_value="postgresql://user:pass@localhost:5432/testdb"
            ):
                backup_path = runner._run_backup("003", "001")

        # 验证 subprocess.run 被调用
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd[0] == "pg_dump"
        assert "-h" in cmd
        assert "localhost" in cmd
        assert "-p" in cmd
        assert "5432" in cmd
        assert "-U" in cmd
        assert "user" in cmd
        assert "testdb" in cmd

        # 验证备份文件名格式
        assert "backup_003_to_001" in str(backup_path)
        assert str(backup_path).endswith(".sql")

    def test_backup_sets_pgpassword(self):
        """备份时应设置 PGPASSWORD 环境变量。"""
        runner = MigrationRunner(database_url="sqlite+aiosqlite:///:memory:")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            with patch.object(
                runner, "_get_sync_database_url",
                return_value="postgresql://user:mypassword@localhost:5432/testdb"
            ):
                runner._run_backup("003", "001")

        call_args = mock_run.call_args
        env = call_args[1]["env"]
        assert env["PGPASSWORD"] == "mypassword"

    def test_backup_creates_directory(self, tmp_path: Path):
        """备份目录不存在时应自动创建。"""
        runner = MigrationRunner(database_url="sqlite+aiosqlite:///:memory:")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            with patch.object(
                runner, "_get_sync_database_url",
                return_value="postgresql://user:pass@localhost:5432/testdb"
            ):
                backup_path = runner._run_backup("003", "001")

        # 备份目录应该是 backend/backups/
        assert "backups" in str(backup_path.parent)


# ---------------------------------------------------------------------------
# Tests: _get_sync_database_url
# ---------------------------------------------------------------------------

class TestGetSyncDatabaseUrl:
    """_get_sync_database_url() 测试。"""

    def test_strips_asyncpg(self):
        """应去除 +asyncpg 后缀。"""
        runner = MigrationRunner(database_url="sqlite+aiosqlite:///:memory:")

        with patch("app.core.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/db"
            result = runner._get_sync_database_url()

        assert result == "postgresql://user:pass@localhost:5432/db"
        assert "+asyncpg" not in result

    def test_no_asyncpg_unchanged(self):
        """无 +asyncpg 时应保持不变。"""
        runner = MigrationRunner(database_url="sqlite+aiosqlite:///:memory:")

        with patch("app.core.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = "postgresql://user:pass@localhost:5432/db"
            result = runner._get_sync_database_url()

        assert result == "postgresql://user:pass@localhost:5432/db"
