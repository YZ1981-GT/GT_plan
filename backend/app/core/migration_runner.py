"""数据库版本化迁移运行器 — 基于 SQL 脚本目录的轻量级迁移方案。

设计决策 D6：使用版本化 SQL 脚本（非 Alembic），启动时自动检测并执行。

用法（在 FastAPI lifespan 中）::

    from app.core.migration_runner import MigrationRunner
    runner = MigrationRunner(database_url)
    await runner.run_pending()

目录结构::

    backend/migrations/
    ├── V001__init.sql
    ├── V002__add_schema_version.sql
    └── V003__example_add_comment.sql
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

logger = logging.getLogger("audit_platform.migration")

# 匹配 V001__xxx.sql 格式
_VERSION_RE = re.compile(r"^V(\d+)__.*\.sql$", re.IGNORECASE)

# schema_version 表 DDL
_SCHEMA_VERSION_DDL = """\
CREATE TABLE IF NOT EXISTS schema_version (
    id          SERIAL PRIMARY KEY,
    version     VARCHAR(20)  NOT NULL UNIQUE,
    filename    VARCHAR(255) NOT NULL,
    applied_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    checksum    VARCHAR(64)  NOT NULL
);
"""


@dataclass
class MigrationFile:
    """一个待执行的迁移脚本。"""

    version: str        # e.g. "001"
    filename: str       # e.g. "V001__init.sql"
    path: Path          # 完整路径
    checksum: str       # SHA-256 of file content


class MigrationRunner:
    """扫描 migrations/ 目录，按版本号顺序执行未应用的 SQL 脚本。

    Parameters
    ----------
    database_url : str
        asyncpg 连接字符串，例如 ``postgresql+asyncpg://...``
    migrations_dir : str | Path | None
        迁移脚本目录，默认为 ``backend/migrations/``
    engine : AsyncEngine | None
        可选：复用已有引擎（测试用）
    """

    def __init__(
        self,
        database_url: str | None = None,
        migrations_dir: str | Path | None = None,
        engine: AsyncEngine | None = None,
    ) -> None:
        if engine is not None:
            self._engine = engine
            self._owns_engine = False
        elif database_url:
            self._engine = create_async_engine(database_url, pool_pre_ping=True)
            self._owns_engine = True
        else:
            raise ValueError("必须提供 database_url 或 engine")

        if migrations_dir is None:
            # 默认：backend/migrations/
            self._migrations_dir = Path(__file__).resolve().parent.parent.parent / "migrations"
        else:
            self._migrations_dir = Path(migrations_dir)

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    async def run_pending(self) -> list[str]:
        """执行所有未应用的迁移，返回已执行的版本号列表。"""
        await self.ensure_schema_version_table()

        all_migrations = self.scan_migrations()
        applied = await self.get_applied_versions()

        pending = [m for m in all_migrations if m.version not in applied]
        if not pending:
            logger.info("[Migration] 数据库已是最新版本，无待执行迁移")
            return []

        executed: list[str] = []
        for mig in pending:
            await self._apply_migration(mig)
            executed.append(mig.version)

        logger.info("[Migration] 执行了 %d 个迁移: %s", len(executed), executed)
        return executed

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------

    def scan_migrations(self) -> list[MigrationFile]:
        """扫描 migrations/ 目录，返回按版本号排序的迁移文件列表。"""
        if not self._migrations_dir.is_dir():
            logger.warning("[Migration] 迁移目录不存在: %s", self._migrations_dir)
            return []

        result: list[MigrationFile] = []
        for f in sorted(self._migrations_dir.iterdir()):
            m = _VERSION_RE.match(f.name)
            if m and f.is_file():
                content = f.read_text(encoding="utf-8")
                checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
                result.append(MigrationFile(
                    version=m.group(1),   # "001", "002", ...
                    filename=f.name,
                    path=f,
                    checksum=checksum,
                ))

        # 按版本号数值排序
        result.sort(key=lambda x: int(x.version))
        return result

    # ------------------------------------------------------------------
    # 查询已应用版本
    # ------------------------------------------------------------------

    async def get_applied_versions(self) -> set[str]:
        """查询 schema_version 表，返回已应用的版本号集合。"""
        async with self._engine.begin() as conn:
            rows = await conn.execute(
                text("SELECT version FROM schema_version ORDER BY version")
            )
            return {row[0] for row in rows.fetchall()}

    # ------------------------------------------------------------------
    # 确保 schema_version 表存在
    # ------------------------------------------------------------------

    async def ensure_schema_version_table(self) -> None:
        """如果 schema_version 表不存在则创建。

        首次运行时，还会自动将 V001 标记为已应用（因为现有表已通过 create_all 创建）。
        """
        async with self._engine.begin() as conn:
            await conn.execute(text(_SCHEMA_VERSION_DDL))

            # 检查是否为全新的 schema_version 表（无记录）
            result = await conn.execute(text("SELECT COUNT(*) FROM schema_version"))
            count = result.scalar()

            if count == 0:
                # 首次运行：标记 V001 为已应用（现有 schema 基线）
                v001 = self._find_v001()
                if v001:
                    await conn.execute(
                        text(
                            "INSERT INTO schema_version (version, filename, checksum) "
                            "VALUES (:version, :filename, :checksum)"
                        ),
                        {"version": v001.version, "filename": v001.filename, "checksum": v001.checksum},
                    )
                    logger.info("[Migration] 首次运行，标记 V001 为已应用基线")

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    async def _apply_migration(self, mig: MigrationFile) -> None:
        """执行单个迁移脚本并记录到 schema_version。"""
        sql_content = mig.path.read_text(encoding="utf-8")
        logger.info("[Migration] 执行 %s (version=%s) ...", mig.filename, mig.version)

        async with self._engine.begin() as conn:
            # 执行迁移 SQL（可能包含多条语句）
            # 使用 connection.execute(text(...)) 逐条执行
            # 对于包含 DO $$ ... END $$; 等 PL/pgSQL 块，需要整体执行
            await conn.execute(text(sql_content))

            # 记录版本
            await conn.execute(
                text(
                    "INSERT INTO schema_version (version, filename, checksum) "
                    "VALUES (:version, :filename, :checksum)"
                ),
                {"version": mig.version, "filename": mig.filename, "checksum": mig.checksum},
            )

        logger.info("[Migration] ✅ %s 执行成功", mig.filename)

    def _find_v001(self) -> MigrationFile | None:
        """在迁移列表中查找 V001。"""
        for mig in self.scan_migrations():
            if mig.version == "001":
                return mig
        return None

    async def close(self) -> None:
        """关闭自建引擎（如果有）。"""
        if self._owns_engine:
            await self._engine.dispose()
