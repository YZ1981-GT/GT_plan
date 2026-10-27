"""测试侧 PG 判定（spec procedure-chain-hardening-and-java-contracts R20）。

原先 conftest 用 ``"postgresql" in DATABASE_URL`` 判断：``postgres://`` 开头的地址被当成「不是 PG」，pg_only 用例
整批静默跳过；CI / 本地都看不出来（显示 skipped，退出码 0）。现在：
- ``is_pg_url``：协议名以 ``postgres`` 开头即 PG（postgres / postgresql / postgresql+asyncpg / postgres+psycopg…）；
- ``pg_requirement_error``：设了 ``GT_REQUIRE_PG=1`` 而地址不是 PG、又收集到了 pg_only 用例 ⇒ 返回报错文字
  （conftest 据此抛 ``pytest.UsageError``，整次运行失败，而不是把这些用例跳过）。
"""
from __future__ import annotations

from typing import Sequence


def is_pg_url(url: str | None) -> bool:
    scheme = (url or "").split("://", 1)[0].strip().lower()
    return scheme.startswith("postgres")


def require_pg_enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def pg_requirement_error(db_url: str | None, require_pg: str | None, pg_only_nodeids: Sequence[str]) -> str | None:
    if not require_pg_enabled(require_pg) or is_pg_url(db_url) or not pg_only_nodeids:
        return None
    sample = "、".join(list(pg_only_nodeids)[:5])
    more = f" 等 {len(pg_only_nodeids)} 个" if len(pg_only_nodeids) > 5 else ""
    scheme = (db_url or "（未设置）").split("://", 1)[0]
    return (f"GT_REQUIRE_PG=1，但 DATABASE_URL 不是 PostgreSQL（协议：{scheme}）：pg_only 用例会被跳过 —— "
            f"{sample}{more}。请把 DATABASE_URL 指向 PostgreSQL，或去掉 GT_REQUIRE_PG。")
