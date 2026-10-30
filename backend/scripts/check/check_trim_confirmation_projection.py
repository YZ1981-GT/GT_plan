#!/usr/bin/env python3
"""
check_trim_confirmation_projection.py — 粗裁确认投影对拍（spec trim-generation-plan-followup-optimizations R3）

只读：在 READ ONLY 事务里用已消费的粗裁预览凭证重算投影，逐项目逐循环比对
``procedure_trim_cycle_confirmations``（来源凭证 / 操作人 / 时间 / 请求号 / 决定指纹 / 保存次数），
并与切换前的旧读法（扫描凭证 JSON）对拍。判据与写入同一实现：``app.services.procedure_trim_confirmation``。

Usage:
    python check_trim_confirmation_projection.py                 # 全库
    python check_trim_confirmation_projection.py --project <id>  # 单个项目

退出码：0 一致；1 不一致（fail-closed，先查原因再继续）；2 投影表不存在（V218 未应用）。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


async def run(project_id: UUID | None) -> int:
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.services.procedure_trim_confirmation import verify_projection

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            if conn.dialect.name == "postgresql":
                await conn.execute(sa.text("SET TRANSACTION READ ONLY"))
                exists = await conn.scalar(sa.text("SELECT to_regclass('procedure_trim_cycle_confirmations')"))
                if not exists:
                    print("[MISSING] procedure_trim_cycle_confirmations 不存在：V218 未应用")
                    return 2
            report = await verify_projection(AsyncSession(bind=conn), project_id)
            await conn.rollback()
    finally:
        await engine.dispose()

    print(f"[粗裁确认投影] 投影 {report.projection_rows} 行 / 凭证推导 {report.expected_rows} 行")
    problems = (
        [f"缺少 {p} {c}" for p, c in report.missing]
        + [f"多出 {p} {c}" for p, c in report.unexpected]
        + [f"字段不符 {p} {c}：{d}" for p, c, d in report.field_mismatches]
        + [f"与旧读法不符 {p} {c}：{d}" for p, c, d in report.legacy_mismatches]
    )
    if problems:
        print(f"[FAIL] {len(problems)} 处不一致：")
        for line in problems:
            print(f"  - {line}")
        return 1
    print("[OK] 投影与已消费凭证、旧读法逐项目逐循环一致")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="粗裁确认投影与预览凭证对拍（只读）")
    parser.add_argument("--project", type=UUID, default=None, help="只核对一个项目")
    args = parser.parse_args(argv)
    return asyncio.run(run(args.project))


if __name__ == "__main__":
    sys.exit(main())
