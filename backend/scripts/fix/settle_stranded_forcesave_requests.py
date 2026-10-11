#!/usr/bin/env python
"""结算历史遗留的 forcesave request：application 已落终态、request 仍停 open（D1 欠账）。

═══ 为什么需要 ════════════════════════════════════════════════════════════════

D1 修复之前，生产代码从不写 `correlated → terminal`（`REQUEST_EDGES` 登记了这条边，但零
写入方）。修复（`request_settlement.settle_requests_of_terminal_application`，在 application
落终态的同一事务里调用）只对**此后**的 application 生效；此前每一次 OO→HTML
保存留下的 request 都停在 `correlated`。真库 2026-10-11 现算 68 条（applied 66 +
authorization_stale 2，最早 2026-09-11），横跨全部企业、全部 entry。

这些行不再挡新会话（新会话走新 generation 或复用 pristine room），但它们让「request
已终结」这条事实在历史数据上不成立：同代际的 participant 离开恒 409、close barrier 的
predecessor 计数恒不归零，排障时也会被误导。

═══ 不另写一套规则 ═══════════════════════════════════════════════════════════

逐个终态 application 调用**同一个** `request_settlement.settle_requests_of_terminal_application`
（目标状态取单源 `REQUEST_STATE_FOR_TERMINAL_APPLICATION`）。本脚本只负责「找出谁需要结算」与
「一个 application 一个事务」。

═══ 用法 ════════════════════════════════════════════════════════════════════

    # 只读预演（一行库都不写）
    python backend/scripts/fix/settle_stranded_forcesave_requests.py --check
    # 真结算（逐 application 独立事务；重跑幂等：已终结的 request 原样跳过）
    python backend/scripts/fix/settle_stranded_forcesave_requests.py --apply --json out.json

`--json` 记录每条被改写 request 的 id 与前后状态（回滚依据：修复前它们全部是 open 态，
原值逐条记在报告里）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ROOT = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.models.workpaper_sync_models import (  # noqa: E402
    WorkpaperContentApplication,
    WorkpaperForcesaveRequest,
)
from app.services.workpaper_sync.models import (  # noqa: E402
    REQUEST_STATE_FOR_TERMINAL_APPLICATION,
    RequestState,
    is_terminal,
)
from app.services.workpaper_sync.repository import WorkpaperSyncRepository  # noqa: E402
from app.services.workpaper_sync.request_settlement import (  # noqa: E402
    settle_requests_of_terminal_application,
)

#: request 的非终态（由状态机现算，不手写清单）。
_OPEN_REQUEST_STATES: tuple[str, ...] = tuple(
    s.value for s in RequestState if not is_terminal("request", s)
)
_TERMINAL_APPLICATION_STATES: tuple[str, ...] = tuple(
    s.value for s in REQUEST_STATE_FOR_TERMINAL_APPLICATION
)

#: application ↔ request 的绑定（origin + primary shell + 直指 primary 的 duplicate shell），
#: 与 `settle_requests_of_terminal_application` 的取数口径一致。
_STRANDED_SQL = sa.text(
    """
    WITH linked AS (
        SELECT a.id AS app_id, a.origin_request_id AS req_id
          FROM working_paper_content_application a
        UNION
        SELECT a.id, o.forcesave_request_id
          FROM working_paper_content_application a
          JOIN working_paper_sync_operation o ON o.application_id = a.id
         WHERE o.forcesave_request_id IS NOT NULL
        UNION
        SELECT a.id, d.forcesave_request_id
          FROM working_paper_content_application a
          JOIN working_paper_sync_operation p ON p.application_id = a.id
          JOIN working_paper_sync_operation d ON d.duplicate_of_operation_id = p.id
         WHERE d.forcesave_request_id IS NOT NULL
    )
    SELECT a.id AS app_id, a.state AS app_state, r.id AS req_id, r.state AS req_state
      FROM linked l
      JOIN working_paper_content_application a ON a.id = l.app_id
      JOIN working_paper_forcesave_request r ON r.id = l.req_id
     WHERE a.state = ANY(:app_states) AND r.state = ANY(:req_states)
     ORDER BY a.created_at, r.request_sequence
    """
)


def _engine() -> Any:
    """独立 NullPool 引擎（复用共享池会把连接绑在已关闭的 event loop 上）。"""
    from app.core.config import settings

    return create_async_engine(
        str(settings.DATABASE_URL),
        poolclass=NullPool,
        connect_args={"ssl": False} if settings.DB_DISABLE_SSL else {},
        echo=False,
    )


async def _stranded(Session: Any) -> list[dict[str, str]]:
    async with Session() as s:
        rows = (
            await s.execute(
                _STRANDED_SQL,
                {
                    "app_states": list(_TERMINAL_APPLICATION_STATES),
                    "req_states": list(_OPEN_REQUEST_STATES),
                },
            )
        ).all()
    return [
        {
            "application_id": str(r.app_id),
            "application_state": str(r.app_state),
            "request_id": str(r.req_id),
            "request_state": str(r.req_state),
        }
        for r in rows
    ]


async def run(*, apply: bool) -> dict[str, Any]:
    engine = _engine()
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        before = await _stranded(Session)
        report: dict[str, Any] = {
            "mode": "apply" if apply else "check",
            "stranded_before": len(before),
            "by_state_before": dict(
                Counter(f"{r['application_state']}→{r['request_state']}" for r in before)
            ),
            "settled": [],
            "errors": [],
        }
        if not apply:
            report["candidates"] = before
            return report
        prior = {r["request_id"]: r["request_state"] for r in before}
        for app_id in dict.fromkeys(r["application_id"] for r in before):
            try:
                async with Session() as s:
                    app = (
                        await s.execute(
                            sa.select(WorkpaperContentApplication)
                            .where(WorkpaperContentApplication.id == app_id)
                            .with_for_update()
                        )
                    ).scalar_one()
                    settled = await settle_requests_of_terminal_application(
                        WorkpaperSyncRepository(s), app
                    )
                    states = {
                        str(i): str(st)
                        for i, st in (
                            await s.execute(
                                sa.select(
                                    WorkpaperForcesaveRequest.id,
                                    WorkpaperForcesaveRequest.state,
                                ).where(WorkpaperForcesaveRequest.id.in_(list(settled)))
                            )
                        ).all()
                    } if settled else {}
                    await s.commit()
                for rid in settled:
                    report["settled"].append(
                        {
                            "application_id": app_id,
                            "application_state": str(app.state),
                            "request_id": str(rid),
                            "from": prior.get(str(rid)),
                            "to": states.get(str(rid)),
                        }
                    )
            except Exception as exc:  # noqa: BLE001 - 逐 application 隔离，失败进报告
                report["errors"].append(
                    {"application_id": app_id, "error": f"{type(exc).__name__}: {exc}"[:400]}
                )
        after = await _stranded(Session)
        report["stranded_after"] = len(after)
        report["by_transition"] = dict(
            Counter(f"{r['from']}→{r['to']}" for r in report["settled"])
        )
        return report
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="结算 application 已终态而 request 仍 open 的历史行")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="只读预演")
    mode.add_argument("--apply", action="store_true", help="逐 application 独立事务结算")
    parser.add_argument("--json", type=Path, default=None, help="完整报告输出路径")
    args = parser.parse_args(argv)
    report = asyncio.run(run(apply=bool(args.apply)))
    if args.json is not None:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    summary = {k: v for k, v in report.items() if k not in ("candidates", "settled")}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if report["mode"] == "apply":
        return 0 if not report["errors"] and report.get("stranded_after") == 0 else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
