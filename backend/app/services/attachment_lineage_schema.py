"""附件溯源 ``attachment_lineage.project_id`` 列就绪判定（spec formula-hub-integrity-closure，需求 7.1，ADR-FHIC-13）。

迁移 V227 给 ``attachment_lineage`` 加可空列 ``project_id``。代码可能先于迁移运行：迁移失败只记入
``schema_migration_failures``、应用照常启动（F56），部署顺序也可能出错。列不存在时：

- 附件三端点（``routers/attachment_lineage.py``）返回 503 ``ATTACHMENT_LINEAGE_MIGRATION_PENDING``；
- 溯源的附件子源（``unified_lineage_service._query_attachments``）抛 :class:`AttachmentLineageMigrationPending`，
  ``query_lineage`` 把它记入响应的 ``errors``；

两处都在判定之后才触达 ``attachment_lineage``。

判定查 ``information_schema.columns``（SQLite 测试库查 ``PRAGMA table_info``）。只缓存「已就绪」：迁移补上后
下一次判定即生效，未就绪每次重查。缓存按库区分（测试进程会连多个库），测试用 :func:`clear_lineage_schema_cache`
清空。已缓存「已就绪」的进程在执行 R227 回滚后需重启才会改判。
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

MIGRATION_VERSION = "V227"
TABLE = "attachment_lineage"
COLUMN = "project_id"
ERROR_CODE = "ATTACHMENT_LINEAGE_MIGRATION_PENDING"
MESSAGE = f"附件溯源迁移 {MIGRATION_VERSION} 未完成，请先执行迁移"
STATUS_CODE = 503

_PG_COLUMN_SQL = text(
    "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
    "WHERE table_schema = current_schema() AND table_name = :table AND column_name = :column)"
)

#: 已判定就绪的库（引擎 URL，密码已隐去）
_ready_databases: set[str] = set()


class AttachmentLineageMigrationPending(Exception):
    """``attachment_lineage.project_id`` 列不存在（迁移 V227 未执行或失败）。"""

    status_code = STATUS_CODE
    error_code = ERROR_CODE

    def __init__(self) -> None:
        self.message = MESSAGE
        super().__init__(MESSAGE)

    def to_detail(self) -> dict[str, str]:
        return {"error_code": ERROR_CODE, "message": MESSAGE}


def _bind_of(db: Any) -> Any:
    """会话绑定的引擎 / 连接；传入的本身是连接或引擎则原样返回。"""
    if isinstance(db, (AsyncConnection, AsyncEngine)):
        return db
    bind = getattr(db, "bind", None)
    if bind is None:
        try:
            bind = db.get_bind()
        except Exception:  # noqa: BLE001 —— 取不到绑定时按未知方言处理（不缓存）
            bind = None
    return bind


def _database_key(bind: Any) -> str | None:
    """缓存键：引擎 URL（隐去密码）。SQLite 内存库每个引擎各是一个库、URL 却相同 ⇒ 不缓存。"""
    engine = getattr(bind, "engine", bind)
    url = getattr(engine, "url", None)
    if not isinstance(url, URL):
        return None
    if url.get_backend_name() == "sqlite" and url.database in (None, "", ":memory:"):
        return None
    return url.render_as_string(hide_password=True)


def _dialect_name(bind: Any) -> str:
    name = getattr(getattr(bind, "dialect", None), "name", "")
    return name if isinstance(name, str) else ""


async def lineage_project_column_ready(db: Any) -> bool:
    """``attachment_lineage.project_id`` 列是否存在（只缓存 True）。"""
    bind = _bind_of(db)
    key = _database_key(bind)
    if key is not None and key in _ready_databases:
        return True
    if _dialect_name(bind) == "sqlite":
        rows = (await db.execute(text(f"PRAGMA table_info({TABLE})"))).fetchall()
        ready = any(row[1] == COLUMN for row in rows)
    else:
        ready = bool((await db.execute(_PG_COLUMN_SQL, {"table": TABLE, "column": COLUMN})).scalar())
    if ready and key is not None:
        _ready_databases.add(key)
    return ready


async def ensure_lineage_project_column(db: Any) -> None:
    """列未就绪 ⇒ HTTP 503 ``ATTACHMENT_LINEAGE_MIGRATION_PENDING``（附件三端点在触达该表之前调用）。"""
    if not await lineage_project_column_ready(db):
        raise HTTPException(status_code=STATUS_CODE, detail=AttachmentLineageMigrationPending().to_detail())


def clear_lineage_schema_cache() -> None:
    """清空「已就绪」缓存（测试用）。"""
    _ready_databases.clear()
