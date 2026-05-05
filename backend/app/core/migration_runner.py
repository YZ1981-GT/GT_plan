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


def _is_comment_only(stmt: str) -> bool:
    """判断一段 SQL 文本是否全部为注释或空白。

    逐行检查：非空行必须以 ``--`` 开头（单行注释），否则认为包含实际语句。

    Parameters
    ----------
    stmt : str
        已去除首尾空白的 SQL 片段

    Returns
    -------
    bool
        True 表示该片段只含注释/空行，可以跳过执行
    """
    for line in stmt.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            return False
    return True


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

    @staticmethod
    def _split_sql_statements(sql_content: str) -> list[str]:
        """将 SQL 文件内容分割为独立语句列表。

        处理规则：
        1. 识别 ``$tag$ ... $tag$`` 美元引号块（PL/pgSQL DO 块等），整体保留不按分号分割
        2. 按分号分割普通语句
        3. 过滤空语句和纯注释语句（以 ``--`` 开头的行）

        Parameters
        ----------
        sql_content : str
            SQL 文件的完整文本内容

        Returns
        -------
        list[str]
            可逐条执行的 SQL 语句列表（已去除首尾空白）
        """
        statements: list[str] = []
        current: list[str] = []   # 当前语句的字符缓冲
        in_dollar_quote = False    # 是否在 $tag$ 块内
        dollar_tag = ""            # 当前美元引号标签，如 $$ 或 $body$
        i = 0
        n = len(sql_content)

        while i < n:
            # 检测美元引号开始（$tag$ 格式，tag 可为空字符串）
            if not in_dollar_quote and sql_content[i] == '$':
                j = i + 1
                # tag 只能包含字母、数字、下划线
                while j < n and (sql_content[j].isalnum() or sql_content[j] == '_'):
                    j += 1
                if j < n and sql_content[j] == '$':
                    # 找到合法的美元引号标签
                    tag = sql_content[i:j + 1]  # 包含两端的 $
                    in_dollar_quote = True
                    dollar_tag = tag
                    current.append(sql_content[i:j + 1])
                    i = j + 1
                    continue
                # 不是合法标签，当作普通字符处理
                current.append(sql_content[i])
                i += 1
                continue

            # 在美元引号块内，检测结束标签
            if in_dollar_quote:
                tag_len = len(dollar_tag)
                if sql_content[i:i + tag_len] == dollar_tag:
                    current.append(dollar_tag)
                    i += tag_len
                    in_dollar_quote = False
                    dollar_tag = ""
                else:
                    current.append(sql_content[i])
                    i += 1
                continue

            # 普通模式：遇到分号则结束当前语句
            if sql_content[i] == ';':
                stmt = "".join(current).strip()
                if stmt and not _is_comment_only(stmt):
                    statements.append(stmt)
                current = []
                i += 1
                continue

            current.append(sql_content[i])
            i += 1

        # 处理末尾没有分号的语句
        remaining = "".join(current).strip()
        if remaining and not _is_comment_only(remaining):
            statements.append(remaining)

        return statements

    async def _apply_migration(self, mig: MigrationFile) -> None:
        """执行单个迁移脚本并记录到 schema_version。

        按分号分割 SQL 语句逐条执行，正确处理 ``DO $$ ... END $$;`` 块。
        """
        sql_content = mig.path.read_text(encoding="utf-8")
        logger.info("[Migration] 执行 %s (version=%s) ...", mig.filename, mig.version)

        statements = self._split_sql_statements(sql_content)
        logger.debug("[Migration] %s 共 %d 条语句", mig.filename, len(statements))

        async with self._engine.begin() as conn:
            for stmt in statements:
                await conn.execute(text(stmt))

            # 记录版本
            await conn.execute(
                text(
                    "INSERT INTO schema_version (version, filename, checksum) "
                    "VALUES (:version, :filename, :checksum)"
                ),
                {"version": mig.version, "filename": mig.filename, "checksum": mig.checksum},
            )

        logger.info("[Migration] ✅ %s 执行成功（%d 条语句）", mig.filename, len(statements))

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
