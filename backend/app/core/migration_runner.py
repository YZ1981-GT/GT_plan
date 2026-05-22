"""数据库版本化迁移运行器 — 基于 SQL 脚本目录的轻量级迁移方案。

设计决策 D6：使用版本化 SQL 脚本（非 Alembic），启动时自动检测并执行。

用法（在 FastAPI lifespan 中）::

    from app.core.migration_runner import MigrationRunner
    runner = MigrationRunner(database_url)
    await runner.run_pending()

回滚用法（CLI）::

    python -m app.core.migration_runner --rollback 002
    python -m app.core.migration_runner --rollback 002 --confirm  # 生产环境

目录结构::

    backend/migrations/
    ├── V001__init.sql
    ├── R001__rollback_init.sql
    ├── V002__add_schema_version.sql
    ├── R002__rollback_schema_version.sql
    └── V003__example_add_comment.sql
        R003__rollback_example_add_comment.sql
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

logger = logging.getLogger("audit_platform.migration")

# 匹配 V001__xxx.sql 格式
_VERSION_RE = re.compile(r"^V(\d+)__.*\.sql$", re.IGNORECASE)

# 匹配 R001__xxx.sql 格式（回滚脚本）
_ROLLBACK_RE = re.compile(r"^R(\d+)__.*\.sql$", re.IGNORECASE)

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

# 回滚追踪列 DDL（ALTER TABLE IF NOT EXISTS 模式）
_SCHEMA_VERSION_ROLLBACK_COLUMNS_DDL = """\
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'schema_version' AND column_name = 'operator'
    ) THEN
        ALTER TABLE schema_version ADD COLUMN operator VARCHAR(100);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'schema_version' AND column_name = 'rollback_note'
    ) THEN
        ALTER TABLE schema_version ADD COLUMN rollback_note TEXT;
    END IF;
END
$$;
"""


def _is_comment_only(stmt: str) -> bool:
    """判断一段 SQL 文本是否全部为注释或空白。

    支持两种注释格式：
    - ``--`` 单行注释
    - ``/* ... */`` 块注释（可跨行）

    Parameters
    ----------
    stmt : str
        已去除首尾空白的 SQL 片段

    Returns
    -------
    bool
        True 表示该片段只含注释/空行，可以跳过执行
    """
    # 先去掉所有 /* ... */ 块注释（使用顶部已导入的 re 模块），再检查剩余内容
    stripped = re.sub(r'/\*.*?\*/', '', stmt, flags=re.DOTALL)
    for line in stripped.splitlines():
        line = line.strip()
        if line and not line.startswith("--"):
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

    def scan_rollback_scripts(self) -> list[MigrationFile]:
        """扫描 migrations/ 目录，返回按版本号排序的回滚脚本列表。"""
        if not self._migrations_dir.is_dir():
            logger.warning("[Migration] 迁移目录不存在: %s", self._migrations_dir)
            return []

        result: list[MigrationFile] = []
        for f in sorted(self._migrations_dir.iterdir()):
            m = _ROLLBACK_RE.match(f.name)
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

    async def get_current_version(self) -> str | None:
        """获取当前最大已应用版本号。"""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("SELECT MAX(version) FROM schema_version")
            )
            return result.scalar()

    # ------------------------------------------------------------------
    # 回滚 API
    # ------------------------------------------------------------------

    async def rollback_to(
        self,
        target_version: str,
        confirm: bool = False,
        operator: str | None = None,
    ) -> list[str]:
        """回滚到指定版本（逆序执行 R*.sql 脚本）。

        Parameters
        ----------
        target_version : str
            目标版本号（如 "002"），回滚后数据库将处于此版本状态。
            即：target_version 本身保留，大于 target 的版本被回滚。
        confirm : bool
            生产环境必须传 True，否则拒绝执行。
        operator : str | None
            操作人标识，记录到 schema_version 表。

        Returns
        -------
        list[str]
            已回滚的版本号列表（逆序）。

        Raises
        ------
        RuntimeError
            生产环境未传 --confirm / 目标版本无效 / 回滚脚本缺失。
        """
        from app.core.config import settings

        # 生产环境安全检查
        if settings.APP_ENV.lower() in ("prod", "production") and not confirm:
            raise RuntimeError(
                "生产环境回滚需要 --confirm 参数。"
                "请确认已通知相关人员并做好备份后重新执行。"
            )

        await self.ensure_schema_version_table()

        current_version = await self.get_current_version()
        if current_version is None:
            raise RuntimeError("schema_version 表为空，无法回滚")

        # 验证目标版本
        target_int = int(target_version)
        current_int = int(current_version)

        if target_int >= current_int:
            raise RuntimeError(
                f"目标版本 {target_version} 必须小于当前版本 {current_version}"
            )

        # 计算需回滚的版本列表（从当前到 target+1，逆序）
        applied = await self.get_applied_versions()
        versions_to_rollback = sorted(
            [v for v in applied if int(v) > target_int],
            key=lambda x: int(x),
            reverse=True,  # 逆序：从高到低回滚
        )

        if not versions_to_rollback:
            logger.info("[Migration] 无需回滚，当前已在目标版本")
            return []

        # 检查所有回滚脚本是否存在
        rollback_scripts = {m.version: m for m in self.scan_rollback_scripts()}
        missing = [v for v in versions_to_rollback if v not in rollback_scripts]
        if missing:
            raise RuntimeError(
                f"以下版本缺少回滚脚本 (R*.sql): {missing}。"
                "请先创建对应的回滚脚本。"
            )

        # 执行 pg_dump 备份
        backup_path = self._run_backup(current_version, target_version)
        logger.info("[Migration] 备份完成: %s", backup_path)

        # 逆序执行回滚脚本
        rolled_back: list[str] = []
        for version in versions_to_rollback:
            rollback_mig = rollback_scripts[version]
            await self._execute_rollback_script(rollback_mig)
            rolled_back.append(version)

        # 更新 schema_version 表：删除已回滚版本的记录
        async with self._engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM schema_version WHERE version > :target"),
                {"target": target_version},
            )
            # 插入回滚日志记录（使用特殊 version 标记）
            rollback_note = (
                f"rollback from {current_version} to {target_version} "
                f"at {datetime.now().isoformat()}"
            )
            # 更新目标版本行的 operator 和 rollback_note
            await conn.execute(
                text(
                    "UPDATE schema_version SET operator = :operator, "
                    "rollback_note = :note WHERE version = :version"
                ),
                {
                    "operator": operator or os.environ.get("USERNAME") or os.environ.get("USER") or "unknown",
                    "note": rollback_note,
                    "version": target_version,
                },
            )

        logger.info(
            "[Migration] ✅ 回滚完成: %s → %s（回滚了 %d 个版本: %s）",
            current_version, target_version, len(rolled_back), rolled_back,
        )
        return rolled_back

    # ------------------------------------------------------------------
    # 备份
    # ------------------------------------------------------------------

    def _get_sync_database_url(self) -> str:
        """获取同步数据库 URL（去除 +asyncpg）。"""
        from app.core.config import settings
        url = settings.DATABASE_URL
        # 去除 +asyncpg 后缀，得到 psycopg2 兼容的 URL
        return url.replace("+asyncpg", "")

    def _run_backup(self, from_version: str, to_version: str) -> Path:
        """执行 pg_dump 备份。

        Parameters
        ----------
        from_version : str
            当前版本号
        to_version : str
            目标版本号

        Returns
        -------
        Path
            备份文件路径
        """
        # 确保备份目录存在
        backup_dir = Path(__file__).resolve().parent.parent.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"backup_{from_version}_to_{to_version}_{timestamp}.sql"

        # 解析数据库连接参数
        sync_url = self._get_sync_database_url()
        parsed = urlparse(sync_url)

        # 构建 pg_dump 命令
        pg_dump_cmd = ["pg_dump"]

        if parsed.hostname:
            pg_dump_cmd.extend(["-h", parsed.hostname])
        if parsed.port:
            pg_dump_cmd.extend(["-p", str(parsed.port)])
        if parsed.username:
            pg_dump_cmd.extend(["-U", parsed.username])

        # 数据库名（去除前导 /）
        db_name = parsed.path.lstrip("/") if parsed.path else "audit_platform"
        pg_dump_cmd.extend(["-f", str(backup_file), db_name])

        # 设置 PGPASSWORD 环境变量
        env = os.environ.copy()
        if parsed.password:
            env["PGPASSWORD"] = parsed.password

        logger.info("[Migration] 执行备份: %s", " ".join(pg_dump_cmd))

        result = subprocess.run(
            pg_dump_cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,  # 5 分钟超时
        )

        if result.returncode != 0:
            logger.warning(
                "[Migration] pg_dump 警告/错误 (returncode=%d): %s",
                result.returncode, result.stderr,
            )
            # 不阻断回滚流程，仅警告（备份失败不应阻止紧急回滚）
            if not backup_file.exists():
                logger.error("[Migration] 备份文件未生成，但继续回滚流程")

        return backup_file

    async def _execute_rollback_script(self, mig: MigrationFile) -> None:
        """执行单个回滚脚本。"""
        sql_content = mig.path.read_text(encoding="utf-8")
        logger.info("[Migration] 执行回滚 %s (version=%s) ...", mig.filename, mig.version)

        statements = self._split_sql_statements(sql_content)
        logger.debug("[Migration] %s 共 %d 条语句", mig.filename, len(statements))

        async with self._engine.begin() as conn:
            for stmt in statements:
                await conn.execute(text(stmt))

        logger.info("[Migration] ✅ 回滚 %s 执行成功（%d 条语句）", mig.filename, len(statements))

    # ------------------------------------------------------------------
    # 确保 schema_version 表存在
    # ------------------------------------------------------------------

    async def ensure_schema_version_table(self) -> None:
        """如果 schema_version 表不存在则创建。

        首次运行时，还会自动将 V001 标记为已应用（因为现有表已通过 create_all 创建）。
        同时确保回滚追踪列存在（operator / rollback_note）。
        """
        async with self._engine.begin() as conn:
            await conn.execute(text(_SCHEMA_VERSION_DDL))

            # 确保回滚追踪列存在（仅 PostgreSQL 支持 DO $$ 块，SQLite 跳过）
            dialect_name = self._engine.dialect.name
            if dialect_name == "postgresql":
                await conn.execute(text(_SCHEMA_VERSION_ROLLBACK_COLUMNS_DDL))
            elif dialect_name == "sqlite":
                # SQLite: 尝试直接 ALTER TABLE（忽略已存在的列错误）
                for col, col_type in [("operator", "VARCHAR(100)"), ("rollback_note", "TEXT")]:
                    try:
                        await conn.execute(text(
                            f"ALTER TABLE schema_version ADD COLUMN {col} {col_type}"
                        ))
                    except Exception:
                        pass  # 列已存在，忽略

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
        2. 识别 ``/* ... */`` 块注释，整体保留（由 _is_comment_only 过滤）
        3. 按分号分割普通语句
        4. 过滤空语句和纯注释语句（``--`` 单行注释 + ``/* */`` 块注释）

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
        in_block_comment = False   # 是否在 /* */ 块注释内
        in_line_comment = False    # 是否在 -- 单行注释内（R10 修复：之前缺，注释内 ; 会破坏分句）
        i = 0
        n = len(sql_content)

        while i < n:
            # 检测 -- 单行注释开始（不在美元引号块/块注释内）
            if not in_dollar_quote and not in_block_comment and not in_line_comment and sql_content[i:i+2] == '--':
                in_line_comment = True
                current.append('--')
                i += 2
                continue

            # 在单行注释内，遇换行结束
            if in_line_comment:
                if sql_content[i] == '\n':
                    in_line_comment = False
                current.append(sql_content[i])
                i += 1
                continue

            # 检测 /* 块注释开始（不在美元引号块内）
            if not in_dollar_quote and not in_block_comment and sql_content[i:i+2] == '/*':
                in_block_comment = True
                current.append('/*')
                i += 2
                continue

            # 在块注释内，检测 */ 结束
            if in_block_comment:
                if sql_content[i:i+2] == '*/':
                    in_block_comment = False
                    current.append('*/')
                    i += 2
                else:
                    current.append(sql_content[i])
                    i += 1
                continue

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


# ------------------------------------------------------------------
# CLI 入口
# ------------------------------------------------------------------

def _cli_main() -> None:
    """CLI 入口：支持 --rollback <target_version> [--confirm] 参数。

    用法::

        # 回滚到版本 002（开发环境）
        python -m app.core.migration_runner --rollback 002

        # 回滚到版本 002（生产环境，需 --confirm）
        python -m app.core.migration_runner --rollback 002 --confirm

        # 执行待应用迁移（默认行为）
        python -m app.core.migration_runner
    """
    import argparse
    import asyncio
    import sys

    from app.core.config import settings

    parser = argparse.ArgumentParser(
        description="数据库迁移运行器 — 支持前进迁移和回滚",
    )
    parser.add_argument(
        "--rollback",
        metavar="TARGET_VERSION",
        help="回滚到指定版本号（如 002），大于该版本的迁移将被逆序回滚",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="生产环境回滚确认（APP_ENV=production 时必须传此参数）",
    )
    parser.add_argument(
        "--operator",
        help="操作人标识（记录到 schema_version 表），默认取系统用户名",
    )

    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    runner = MigrationRunner(database_url=settings.DATABASE_URL)

    async def _run() -> None:
        try:
            if args.rollback:
                # 标准化版本号（补零到 3 位）
                target = args.rollback.zfill(3)
                rolled_back = await runner.rollback_to(
                    target_version=target,
                    confirm=args.confirm,
                    operator=args.operator,
                )
                if rolled_back:
                    print(f"✅ 回滚完成，已回滚版本: {rolled_back}")
                else:
                    print("ℹ️  无需回滚，已在目标版本")
            else:
                # 默认：执行待应用迁移
                executed = await runner.run_pending()
                if executed:
                    print(f"✅ 迁移完成，已执行版本: {executed}")
                else:
                    print("ℹ️  数据库已是最新版本")
        except RuntimeError as e:
            print(f"❌ 错误: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            await runner.close()

    asyncio.run(_run())


if __name__ == "__main__":
    _cli_main()
