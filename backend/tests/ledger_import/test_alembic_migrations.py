"""S7-8: Alembic 迁移 upgrade→downgrade→upgrade 循环测试。

针对 ledger_import 相关的 3 个近期迁移：
- ledger_import_column_mapping_20260508
- ledger_import_raw_extra_20260508
- ledger_import_aux_triplet_idx_20260508

测试策略：
- 用独立 PG 临时数据库（通过环境变量）或 SQLite 模拟（部分能力受限）
- 直接调 upgrade(rev) → downgrade(prev) → upgrade(rev) 验证 idempotent
- 若环境不满足（无 DATABASE_URL_TEST 或 PG 不可用）则 skip

注意：
- SQLite 对 Index `postgresql_where` 会忽略，不能真正测 partial index
- 真正的 round-trip 需要 PG（CI 的 backend-tests job 有 postgres:16 service）
"""
from __future__ import annotations

import os
import pytest


pytestmark_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST") and not os.environ.get("DATABASE_URL"),
    reason="需要 DATABASE_URL_TEST 或 DATABASE_URL 指向测试 PG",
)


# ledger_import 相关迁移链（按依赖顺序）
LEDGER_MIGRATIONS = [
    "ledger_import_column_mapping_20260508",
    "ledger_import_raw_extra_20260508",
    "ledger_import_aux_triplet_idx_20260508",
]


def _get_alembic_config():
    """构造 Alembic Config（动态读 alembic.ini）。"""
    from pathlib import Path
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_dir / "alembic.ini"))

    # 用绝对路径覆盖 script_location（alembic.ini 里是相对 backend 的 'alembic'）
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))

    # 用测试 DB URL 覆盖（拓扑测试不需要真 DB，但 Config 解析 alembic.ini 时可能带占位）
    test_url = (
        os.environ.get("DATABASE_URL_TEST")
        or os.environ.get("DATABASE_URL")
        or "postgresql://test:test@localhost:5432/audit_test"
    )
    sync_url = test_url.replace("+asyncpg", "").replace("postgresql+psycopg", "postgresql")
    cfg.set_main_option("sqlalchemy.url", sync_url)
    return cfg


@pytestmark_db
@pytest.mark.parametrize("revision", LEDGER_MIGRATIONS)
def test_migration_round_trip(revision):
    """每个迁移都支持 upgrade → downgrade → upgrade 循环。

    验证点：
    1. upgrade 到该版本不报错
    2. downgrade 回退一版不报错（验证 downgrade() 实现正确）
    3. 再次 upgrade 不报错（验证幂等性）
    """
    from alembic import command

    cfg = _get_alembic_config()

    # Step 1: upgrade 到目标版本
    try:
        command.upgrade(cfg, revision)
    except Exception as exc:
        pytest.fail(f"upgrade {revision} failed: {exc}")

    # Step 2: downgrade 回退一版（-1 用 Alembic 相对语法）
    try:
        command.downgrade(cfg, f"{revision}:-1")
    except Exception as exc:
        pytest.fail(f"downgrade {revision}:-1 failed: {exc}")

    # Step 3: 再次 upgrade 验证幂等
    try:
        command.upgrade(cfg, revision)
    except Exception as exc:
        pytest.fail(f"re-upgrade {revision} failed: {exc}")


def test_all_migrations_reachable():
    """所有迁移节点在 Alembic 拓扑里可达（不是孤儿分支）。

    此测试不依赖真实 DB，只读 migrations 目录，CI 本地都能跑。
    """
    from alembic.script import ScriptDirectory

    cfg = _get_alembic_config()
    script = ScriptDirectory.from_config(cfg)

    known_revs = {rev.revision for rev in script.walk_revisions()}
    for migration in LEDGER_MIGRATIONS:
        assert migration in known_revs, (
            f"迁移 {migration} 不在 Alembic 拓扑中（可能 down_revision 错误）"
        )



def test_no_stray_migrations_in_app_migrations():
    """防止把 Alembic 迁移文件误放到 backend/app/migrations/ （Sprint 7 踩坑）。

    Alembic 只识别 script_location 指向的目录（backend/alembic/versions/）。
    若 .py 迁移文件放到 backend/app/migrations/ 会被完全忽略，生产环境不执行。
    """
    from pathlib import Path

    backend_dir = Path(__file__).resolve().parents[2]
    app_migrations = backend_dir / "app" / "migrations"

    if not app_migrations.exists():
        return  # 目录不存在即安全

    stray = []
    for py_file in app_migrations.glob("*.py"):
        if py_file.name.startswith("__"):
            continue
        content = py_file.read_text(encoding="utf-8")
        # Alembic 迁移特征：含 `revision = ` 和 `down_revision = `
        if "revision = " in content and "down_revision = " in content:
            stray.append(py_file.name)

    if stray:
        pytest.fail(
            f"发现 {len(stray)} 个 Alembic 迁移文件误放在 app/migrations/: {stray}\n"
            f"应移到 backend/alembic/versions/ 才会被 Alembic 执行。"
        )
