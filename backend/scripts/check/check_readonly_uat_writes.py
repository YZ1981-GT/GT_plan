"""只读 UAT 的服务端零写入证据（spec trim-generation-plan-followup-optimizations R5.5）。

审计中间件（``app.middleware.audit_log.AuditLogMiddleware``）给每个成功的写请求（POST / PUT / PATCH / DELETE，
登录 / 刷新除外）记一行 ``logs``。本脚本在只读事务里统计某只读账号在给定时刻之后留下的这类记录：
浏览器防火墙的 attemptedWrites 是客户端证据，这里是服务端证据，两者都为零才算只读走查通过。

退出码：0 零写入 / 1 有写入 / 2 账号不存在或不是只读专用账号 / 3 参数错误。输出 JSON（不含请求体）。

用法（backend 目录）：python scripts/check/check_readonly_uat_writes.py --username <name> --since <ISO 时间>
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import sqlalchemy as sa  # noqa: E402

EXIT_CLEAN, EXIT_WRITES, EXIT_ACCOUNT, EXIT_USAGE = 0, 1, 2, 3


def parse_since(raw: str) -> datetime:
    value = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def check(username: str, since: datetime, *, engine=None) -> tuple[int, dict]:
    from app.core.config import settings
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    owns_engine = engine is None
    if owns_engine:
        connect_args = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=connect_args)
    try:
        async with engine.connect() as conn:
            async with conn.begin() as transaction:
                await conn.execute(sa.text("SET TRANSACTION READ ONLY"))
                user = (await conn.execute(sa.text(
                    "SELECT id, role::text AS role FROM users WHERE username = :u"), {"u": username})).first()
                report: dict = {"username": username, "since": since.isoformat()}
                if user is None or user.role != "readonly":
                    report["error"] = "账号不存在" if user is None else f"账号角色是 {user.role}，不是只读专用账号"
                    await transaction.rollback()
                    return EXIT_ACCOUNT, report
                rows = (await conn.execute(sa.text(
                    "SELECT action_type, object_type, created_at FROM logs "
                    "WHERE user_id = :uid AND created_at >= :since ORDER BY created_at"),
                    {"uid": user.id, "since": since})).all()
                await transaction.rollback()
        report["logs"] = len(rows)
        report["samples"] = [
            {"action_type": r.action_type, "object_type": r.object_type, "created_at": r.created_at.isoformat()}
            for r in rows[:10]
        ]
        return (EXIT_WRITES if rows else EXIT_CLEAN), report
    finally:
        if owns_engine:
            await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读 UAT 服务端零写入证据")
    parser.add_argument("--username", required=True)
    parser.add_argument("--since", required=True, help="ISO 时间（走查开始时刻）")
    args = parser.parse_args(argv)
    try:
        since = parse_since(args.since)
    except ValueError as exc:
        print(f"参数错误：{exc}", file=sys.stderr)
        return EXIT_USAGE
    code, report = asyncio.run(check(args.username, since))
    print(json.dumps(report, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
