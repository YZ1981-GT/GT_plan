# -*- coding: utf-8 -*-
"""底稿 HTML↔在线编辑切换耗时报告（只读）。

spec: workpaper-sync-switch-performance · 需求 1.4（P0）

读 ``working_paper_sync_operation`` + ``working_paper_content_application`` + 最后一条 operation 事件，
按底稿列出最近 N 次切换：

* ``html_to_oo``：创建 → 完成耗时 + 走的哪条路（``descriptor_issued`` 全量物化 /
  ``business_identity_reused`` 复用 / ``store_fingerprint_reused`` 指纹直通）；
* ``oo_to_html``：回调 → 落盘（durable）延迟 + 落盘 → 合并完成耗时。

🔴 口径：事件表 ``occurred_at`` 是 PG ``now()`` = 事务开始时间，阶段内细分请看
``[sync-timing]`` 结构化日志（logger ``workpaper_sync.timing``）；本工具只报端到端。

用法::

    $env:PYTHONIOENCODING='utf-8'
    .\\.venv\\Scripts\\python.exe backend/scripts/analyze/report_sync_switch_timings.py --wp <wp_id>
    .\\.venv\\Scripts\\python.exe backend/scripts/analyze/report_sync_switch_timings.py --limit 20 --json out.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_SQL = """
SELECT o.id::text AS operation_id, o.wp_id::text AS wp_id, o.entry_id, o.direction, o.state,
       o.error_code, o.created_at, o.finished_at,
       a.durable_at, a.finished_at AS application_finished_at,
       (SELECT e.stage FROM working_paper_sync_operation_event e
         WHERE e.operation_id = o.id ORDER BY e.sequence_no DESC LIMIT 1) AS last_stage
FROM working_paper_sync_operation o
LEFT JOIN working_paper_content_application a ON a.id = o.application_id
WHERE (CAST(:wp AS uuid) IS NULL OR o.wp_id = CAST(:wp AS uuid))
ORDER BY o.created_at DESC
LIMIT :limit
"""

#: html_to_oo 的终态 stage → 中文路径名（未登记的原样显示，不猜）。
PATH_LABELS: Mapping[str, str] = {
    "descriptor_issued": "全量物化",
    "business_identity_reused": "业务身份复用",
    "store_fingerprint_reused": "store 指纹直通",
}


def _seconds(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return round((end - start).total_seconds(), 2)


def summarize(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """纯函数：一行 operation → 一条报告记录（便于守卫离线验证）。"""
    out: list[dict[str, Any]] = []
    for row in rows:
        direction = str(row.get("direction") or "")
        record: dict[str, Any] = {
            "operation_id": row.get("operation_id"),
            "wp_id": row.get("wp_id"),
            "entry_id": row.get("entry_id"),
            "direction": direction,
            "state": row.get("state"),
            "created_at": (
                row["created_at"].isoformat() if row.get("created_at") is not None else None
            ),
            "total_s": _seconds(row.get("created_at"), row.get("finished_at")),
        }
        if direction == "html_to_oo":
            stage = str(row.get("last_stage") or "")
            record["path"] = PATH_LABELS.get(stage, stage or None)
        elif direction == "oo_to_html":
            record["durable_s"] = _seconds(row.get("created_at"), row.get("durable_at"))
            record["apply_s"] = _seconds(row.get("durable_at"), row.get("application_finished_at"))
        if row.get("error_code"):
            record["error_code"] = row.get("error_code")
        out.append(record)
    return out


def render(records: list[dict[str, Any]]) -> str:
    lines = []
    for r in records:
        if r["direction"] == "html_to_oo":
            detail = f"路径={r.get('path')}"
        elif r["direction"] == "oo_to_html":
            detail = f"落盘={r.get('durable_s')}s 合并={r.get('apply_s')}s"
        else:
            detail = ""
        lines.append(
            f"{r['created_at'] or '-':32s} {r['direction']:10s} {str(r['state']):12s} "
            f"总计={r['total_s']}s {detail}"
        )
    return "\n".join(lines) if lines else "（无记录）"


async def _fetch(*, wp: str | None, limit: int) -> list[dict[str, Any]]:
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    engine = create_async_engine(str(settings.DATABASE_URL), poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(sa.text(_SQL), {"wp": wp, "limit": int(limit)})
            return [dict(row._mapping) for row in result]
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wp", default=None, help="底稿 id（缺省 = 全部底稿）")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", default=None, help="同时写 JSON 到该路径")
    args = parser.parse_args(argv)
    records = summarize(asyncio.run(_fetch(wp=args.wp, limit=args.limit)))
    print(render(records))
    if args.json:
        Path(args.json).write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
