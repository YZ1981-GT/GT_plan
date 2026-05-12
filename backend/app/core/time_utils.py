"""时间工具 — 统一 UTC 时间获取

PG 数据库使用 TIMESTAMP WITHOUT TIME ZONE 存储 UTC 时间（naive）。
Python 代码中需要和 DB 列比较时，必须使用 naive datetime。

用法：
    from app.core.time_utils import utcnow

    cutoff = utcnow() - timedelta(hours=24)
    stmt = select(Model).where(Model.created_at < cutoff)
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """返回当前 UTC 时间（naive，无 tzinfo）。

    等价于已废弃的 datetime.utcnow()，但语义更明确。
    用于和 PG TIMESTAMP WITHOUT TIME ZONE 列比较。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
