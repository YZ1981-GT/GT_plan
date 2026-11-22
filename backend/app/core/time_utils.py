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


def ensure_utc_aware(value: datetime | None) -> datetime | None:
    """将可能为 naive 的时间归一为 UTC aware datetime。

    数据库读回的 ``TIMESTAMP WITHOUT TIME ZONE`` 按 UTC 解释；带时区的
    值统一转换到 UTC，便于在 Python 中安全比较或计算。
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
