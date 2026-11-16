#!/usr/bin/env python3
"""同步 operation 结算后复核（**只读探针**）—— spec `frozen-contract-read-path-and-legacy-operation-settlement` 任务 9 / R3.4。

R3.4 原文：
    该 operation 终态 / 冲突行 resolved-or-superseded 状态 / 版本链指针 /
    审计轨迹逐项可查，写成可重跑的只读探针。

本文件是 **IO + CLI 层**；八条形态判据与全部值对象在
:mod:`scripts.check.sync_settlement_review`（纯函数，离线可逐条驱动）。这样切的原因：

* 判据能在离线用例里逐条证明「它真的会红」，不必每次建临时 schema；
* 「探针是只读的」这条判据可以**静态**断言（AST 扫两个模块里的
  `insert/update/delete/commit` 调用），不必靠人读；
* `check_file_size.py` 的门限是 800 行，判据与 IO 分开后两侧都有余量。

═══ 四段事实（R3.4 逐项） ═══

| 段 | 事实 |
| --- | --- |
| ① | operation 终态（`state` + `accepted_at` / `finished_at` + `error_code`/`error_stage`） |
| ② | 冲突行 resolved-or-superseded（总数 / 已裁决 / 已作废 / 已被观测同步取代 / 仍未处理 / 三列齐备率） |
| ③ | 版本链指针（application / base version / `current_revision` / result representation + generation + content revision / entry current pointer） |
| ④ | 审计轨迹（operation append-only event 时序 + 冲突行 `resolved_by`/`resolved_at`/`resolved_value`） |

═══ 只读由库强制，不靠自觉 ═══

PG 上整个复核跑在 `SET TRANSACTION READ ONLY` 里，任何写语句会被数据库拒绝；
结束一律 `ROLLBACK`（`finally` 里）。SQLite 没有等价的会话级开关，按 dialect 检测跳过 ——
**跳过不写成「已只读」**，报告里如实标 `read_only_enforced=false`
（memory 铁律：PG-only 能力必加方言检测）。

═══ 可重跑（可证伪形式） ═══

`--json` 输出里唯一的非确定性字段是 `generated_at`；它对内容取 `content_digest` 之前
先被抹掉，所以同一输入的两次运行 `content_digest` **恒定**。`--compare` 用同一口径对拍
（只忽略 `generated_at`，不按浮点容差 / 时间窗放宽）。

═══ 退出码 ═══

| 码 | 含义 |
| --- | --- |
| 0 | 全部通过 |
| 1 | 发现不一致（逐条点名是哪条 operation 的哪条判据） |
| 2 | 环境/解析失败（连不上库、表不存在、报告读不出）—— **不与被判不一致混淆** |

═══ 用法 ═══

    python backend/scripts/check/check_sync_operation_settlement.py --operation <uuid>
    python backend/scripts/check/check_sync_operation_settlement.py --all
    python backend/scripts/check/check_sync_operation_settlement.py --all --json
    python backend/scripts/check/check_sync_operation_settlement.py --compare a.json b.json

🔴 本脚本**不写任何表**，因此可以安全地对共享库跑。它对「历史数据缺口」的处置是
**如实报告 + 棘轮**，不是修数据。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import UUID

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):  # pragma: no cover - 非交互终端
    pass

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.check.sync_settlement_review import (  # noqa: E402
    KNOWN_LEGACY_GAPS,
    NONDETERMINISTIC_KEYS,
    REPORT_SCHEMA,
    OperationReport,
    TimelineEvent,
    VersionChain,
    build_verdicts,
    is_terminal_operation_state,
    summarize_conflicts,
)

__all__ = ["build_document", "collect_report", "compare_documents", "main"]

#: 「已离开 created」的可复核状态集（`created` 排除 —— 它还没结算，没有可复核的内容）。
#:
#: 🔴 必须**覆盖全部 operation 终态**（守卫 `test_the_reviewable_states_cover_every_terminal_state`
#: 逐值比对 `models.TERMINAL_STATES["operation"]`）。漏一个就有一类 operation 永不被复核 ——
#: 首版漏了 `duplicate`（终态但 `application_id IS NULL`，折叠到别人身上的 shell），
#: 那正是「登记了却不覆盖」的形态。
_REVIEWABLE_STATES: tuple[str, ...] = (
    "conflict",
    "applied",
    "refresh_required",
    "superseded",
    "authorization_stale",
    "rejected",
    "duplicate",
    "error",
)

#: 本节全部查询都是 `SELECT`。守卫用 AST 断言这两个模块里没有任何
#: `insert/update/delete/commit` 调用（`test_sync_operation_settlement_probe`）。
#:
#: 🔴 **条件用 Python 拼、不用 SQL 布尔参数**：`(:flag = false OR …)` 在 SQLite 上
#: 会踩「布尔是整数」的坑，而这里的两条条件都只由 CLI 决定、不含用户输入 ⇒
#: 拼进 WHERE 既安全又方言无关。
_OP_SELECT = """
SELECT o.id, o.project_id, o.wp_id, o.entry_id, o.direction, o.state,
       o.application_id, o.room_id, o.definition_bundle_id,
       o.accepted_at, o.finished_at, o.error_code, o.error_stage
  FROM working_paper_sync_operation o
"""

#: ② 冲突行：三列 + 两列**全部**读回来，计数在 Python 侧滚动（`summarize_conflicts`）。
_CONFLICT_SQL = """
SELECT c.id, c.resolved_at, c.resolved_by, c.resolved_value,
       c.abandoned_at, c.abandon_reason, c.abandoned_by, c.superseded_at
  FROM working_paper_sync_conflict c
 WHERE {op_id_expr}
 ORDER BY c.sheet_key, c.table_key, c.row_key, c.stable_field_key, c.oo_location
"""

#: ③ 版本链第 1 跳：application + 它冻结的 base content version 的 revision。
#:
#: 🔴 `base_content_version_revision` 是「revision 前进了没有」的**唯一**正确基线。
#: `application.current_revision` 是 `working_paper.content_revision`（另一个计数器）
#: 在 correlation 时的快照 —— 拿它当基线会给出假红（详见 `sync_settlement_review`）。
_APPLICATION_SQL = """
SELECT a.id, a.state, a.current_revision, a.base_version_id,
       a.base_representation_id, a.result_representation_id,
       a.result_revision, a.merged_projection_sha256,
       bv.revision AS base_content_version_revision
  FROM working_paper_content_application a
  LEFT JOIN working_paper_content_version bv ON bv.id = a.base_version_id
 WHERE {app_id_expr}
"""

#: ③ 版本链第 2 跳：entry 级 current pointer（历史 wp 可能整行不存在）。
_ENTRY_STATE_SQL = """
SELECT s.current_representation_id, s.representation_generation
  FROM working_paper_sync_entry_state s
 WHERE {wp_id_expr} AND s.entry_id = :entry_id
"""

#: ③ 版本链第 3 跳：result representation → 它所属 content version 的 revision。
#: 少这一跳，「内容落地」就只剩一个非空判断（假绿形态）。
_REPRESENTATION_SQL = """
SELECT r.generation, r.content_version_id, v.revision
  FROM working_paper_content_representation r
  LEFT JOIN working_paper_content_version v ON v.id = r.content_version_id
 WHERE {rep_id_expr}
"""

#: ④ 审计轨迹：append-only event 时序。
_EVENT_SQL = """
SELECT e.sequence_no, e.from_state, e.to_state, e.stage, e.actor_type,
       e.actor_id, e.error_code, e.occurred_at
  FROM working_paper_sync_operation_event e
 WHERE {op_id_expr}
 ORDER BY e.sequence_no
"""


# ═══════════════════════════════════════════════════════════════════════════
# 方言适配（PG 原生 uuid / SQLite 32 位十六进制文本）
# ═══════════════════════════════════════════════════════════════════════════


def _uuid_expr(column: str, param: str, *, is_sqlite: bool) -> str:
    """UUID 比较表达式。两边语义相同，只差绑定形态。"""
    if is_sqlite:
        return f"lower(CAST(:{param} AS text)) = lower({column})"
    return f"{column} = CAST(:{param} AS uuid)"


def _bind_uuid(value: Any, *, is_sqlite: bool) -> Any:
    """按方言绑定 UUID：SQLite 存 32 位十六进制文本，PG 走原生 uuid。"""
    if value is None:
        return None
    return str(value) if is_sqlite else value


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _uuid_text(value: Any) -> str | None:
    return None if value is None else str(value)


# ═══════════════════════════════════════════════════════════════════════════
# 只读采集（唯一碰 IO 的地方）
# ═══════════════════════════════════════════════════════════════════════════


async def collect_report(
    conn: Any,
    *,
    operation_id: UUID | None,
    include_orphans: bool,
) -> tuple[OperationReport, ...]:
    """在**已有的只读连接**上采集逐项事实。本函数不做任何事务控制。"""
    import sqlalchemy as sa

    is_sqlite = conn.dialect.name == "sqlite"
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if operation_id is not None:
        clauses.append(_uuid_expr("o.id", "op_id", is_sqlite=is_sqlite))
        params["op_id"] = _bind_uuid(operation_id, is_sqlite=is_sqlite)
    else:
        placeholders = ", ".join(f"'{s}'" for s in _REVIEWABLE_STATES)
        clauses.append(f"o.state IN ({placeholders})")
        if not include_orphans:
            # `html_to_oo` 方向没有 application，③ 段对它不适用；默认只列
            # 「有 application」的那些，避免输出被 784 条无 application 的行淹没。
            # `--include-orphans` 时连它们一起列（那时 ③ 段会显示 entry_state / room）。
            clauses.append("(o.application_id IS NOT NULL OR o.direction = 'html_to_oo')")
    stmt = f"{_OP_SELECT} WHERE {' AND '.join(clauses)} ORDER BY o.created_at, o.id"
    op_rows = (await conn.execute(sa.text(stmt), params)).mappings().all()

    reports: list[OperationReport] = []
    for op in op_rows:
        op_bind = {"op_id": _bind_uuid(op["id"], is_sqlite=is_sqlite)}
        conflict_rows = (
            await conn.execute(
                sa.text(
                    _CONFLICT_SQL.format(
                        op_id_expr=_uuid_expr(
                            "c.operation_id", "op_id", is_sqlite=is_sqlite
                        )
                    )
                ),
                op_bind,
            )
        ).mappings().all()
        rollup = summarize_conflicts(conflict_rows)

        chain = await _load_version_chain(conn, op=op, is_sqlite=is_sqlite)

        timeline = tuple(
            TimelineEvent(
                sequence_no=int(e["sequence_no"]),
                from_state=e["from_state"],
                to_state=str(e["to_state"]),
                stage=e["stage"],
                actor_type=str(e["actor_type"]),
                actor_id=_uuid_text(e["actor_id"]),
                error_code=e["error_code"],
                occurred_at=_iso(e["occurred_at"]) or "",
            )
            for e in (
                await conn.execute(
                    sa.text(
                        _EVENT_SQL.format(
                            op_id_expr=_uuid_expr(
                                "e.operation_id", "op_id", is_sqlite=is_sqlite
                            )
                        )
                    ),
                    op_bind,
                )
            ).mappings().all()
        )

        state = str(op["state"])
        direction = str(op["direction"])
        reports.append(
            OperationReport(
                operation_id=_uuid_text(op["id"]) or "",
                entry_id=str(op["entry_id"]),
                wp_id=_uuid_text(op["wp_id"]) or "",
                project_id=_uuid_text(op["project_id"]) or "",
                direction=direction,
                state=state,
                is_terminal=is_terminal_operation_state(state),
                accepted_at=_iso(op["accepted_at"]),
                finished_at=_iso(op["finished_at"]),
                error_code=op["error_code"],
                error_stage=op["error_stage"],
                conflicts=rollup,
                version_chain=chain,
                timeline=timeline,
                verdicts=build_verdicts(
                    state=state,
                    direction=direction,
                    rollup=rollup,
                    chain=chain,
                    timeline=timeline,
                ),
            )
        )
    return tuple(reports)


async def _load_representation_facts(
    conn: Any, *, rep_id: Any, is_sqlite: bool
) -> Mapping[str, Any] | None:
    """③ 版本链的**第三跳**：representation → 它的 generation + content version revision。

    🔴 独立成函数的原因是可测性：这一跳是「状态变了但内容没落地」判据的**唯一**证据来源
    （只查 operation 表只能看到外键非空）。把它内联在 `_load_version_chain` 里时，
    真库守卫只能通过「有 application 的完整链路」间接打到它 —— 而构造那样一条链路
    需要 room / request / incoming artifact 三张父表，成本高且与判据无关。
    抽出来后，守卫可以直接对一条真实 representation 调用它（变异 m3 即由此被抓到：
    首版把这一跳内联，短路它时真库守卫**全绿**）。
    """
    import sqlalchemy as sa

    if rep_id is None:
        return None
    return (
        await conn.execute(
            sa.text(
                _REPRESENTATION_SQL.format(
                    rep_id_expr=_uuid_expr("r.id", "rep_id", is_sqlite=is_sqlite)
                )
            ),
            {"rep_id": _bind_uuid(rep_id, is_sqlite=is_sqlite)},
        )
    ).mappings().first()


async def _load_version_chain(
    conn: Any, *, op: Mapping[str, Any], is_sqlite: bool
) -> VersionChain:
    """③ 版本链指针 —— **必须逐跳 JOIN 现读**。

    🔴 只查 operation 表本身是不够的：`result_representation_id` 是个外键，
    「它指向的行真的存在吗」「它属于哪个 revision」只能现读。
    """
    import sqlalchemy as sa

    app_id = op["application_id"]
    app_row: Mapping[str, Any] | None = None
    if app_id is not None:
        app_row = (
            await conn.execute(
                sa.text(
                    _APPLICATION_SQL.format(
                        app_id_expr=_uuid_expr("a.id", "app_id", is_sqlite=is_sqlite)
                    )
                ),
                {"app_id": _bind_uuid(app_id, is_sqlite=is_sqlite)},
            )
        ).mappings().first()

    entry_row = (
        await conn.execute(
            sa.text(
                _ENTRY_STATE_SQL.format(
                    wp_id_expr=_uuid_expr("s.wp_id", "wp_id", is_sqlite=is_sqlite)
                )
            ),
            {
                "wp_id": _bind_uuid(op["wp_id"], is_sqlite=is_sqlite),
                "entry_id": str(op["entry_id"]),
            },
        )
    ).mappings().first()

    result_rep_id = None if app_row is None else app_row["result_representation_id"]
    rep_row = await _load_representation_facts(conn, rep_id=result_rep_id, is_sqlite=is_sqlite)

    return VersionChain(
        application_id=_uuid_text(app_id),
        application_state=None if app_row is None else str(app_row["state"]),
        definition_bundle_id=_uuid_text(op["definition_bundle_id"]),
        base_version_id=None if app_row is None else _uuid_text(app_row["base_version_id"]),
        base_representation_id=(
            None if app_row is None else _uuid_text(app_row["base_representation_id"])
        ),
        current_revision=(
            None
            if app_row is None or app_row["current_revision"] is None
            else int(app_row["current_revision"])
        ),
        base_content_version_revision=(
            None
            if app_row is None or app_row["base_content_version_revision"] is None
            else int(app_row["base_content_version_revision"])
        ),
        result_representation_id=_uuid_text(result_rep_id),
        result_revision=(
            None
            if app_row is None or app_row["result_revision"] is None
            else int(app_row["result_revision"])
        ),
        merged_projection_sha256=(
            None if app_row is None else app_row["merged_projection_sha256"]
        ),
        entry_state_present=entry_row is not None,
        entry_current_representation_id=(
            None if entry_row is None else _uuid_text(entry_row["current_representation_id"])
        ),
        entry_representation_generation=(
            None if entry_row is None else int(entry_row["representation_generation"])
        ),
        result_representation_generation=(
            None if rep_row is None else int(rep_row["generation"])
        ),
        result_content_version_revision=(
            None if rep_row is None or rep_row["revision"] is None else int(rep_row["revision"])
        ),
        room_id=_uuid_text(op["room_id"]),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 报告组装 / 对拍
# ═══════════════════════════════════════════════════════════════════════════


def build_document(
    reports: Sequence[OperationReport],
    *,
    read_only_enforced: bool,
    dialect: str,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """把逐条报告滚成可对拍的文档。

    `generated_at` 是**唯一**的非确定性字段，且它**不进** `content_digest` ——
    所以同一输入的两次运行 digest 恒定。「可重跑」由此变成可证伪的断言，
    而不是一句承诺。
    """
    stamp = generated_at or datetime.now(timezone.utc)
    body = {
        "dialect": dialect,
        "read_only_enforced": read_only_enforced,
        "operation_count": len(reports),
        "failure_count": sum(1 for r in reports if not r.ok),
        "known_gap_ids": sorted(KNOWN_LEGACY_GAPS),
        "operations": [r.as_dict() for r in reports],
    }
    return {
        "schema": REPORT_SCHEMA,
        "generated_at": stamp.isoformat(),
        "content_digest": _content_digest(body),
        **body,
    }


def _content_digest(body: Mapping[str, Any]) -> str:
    """对内容取 sha256（`sort_keys` ⇒ 键序稳定；`generated_at` 不在 body 里）。"""
    canonical = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _strip_nondeterministic(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            k: _strip_nondeterministic(v)
            for k, v in value.items()
            if k not in NONDETERMINISTIC_KEYS
        }
    if isinstance(value, list):
        return [_strip_nondeterministic(v) for v in value]
    return value


def compare_documents(left: Mapping[str, Any], right: Mapping[str, Any]) -> list[str]:
    """对拍两份报告，返回差异描述列表（空 = 逐字段相同）。

    🔴 只忽略 `NONDETERMINISTIC_KEYS`（生成时刻）。**不**按浮点容差 / 时间窗之类
    的方式放宽 —— 那些放宽会让「可重跑」这条判据本身失效。
    """
    a = _strip_nondeterministic(dict(left))
    b = _strip_nondeterministic(dict(right))
    problems: list[str] = []
    if a.get("schema") != b.get("schema"):
        return [f"schema 不同：{a.get('schema')!r} vs {b.get('schema')!r}"]
    if a.get("content_digest") != b.get("content_digest"):
        problems.append(
            f"content_digest 不同：{a.get('content_digest')!r} vs {b.get('content_digest')!r}"
        )
    la = a.get("operations") or []
    lb = b.get("operations") or []
    if len(la) != len(lb):
        problems.append(f"operation 条数不同：{len(la)} vs {len(lb)}")
    for x, y in zip(la, lb, strict=False):
        if x.get("operation_id") != y.get("operation_id"):
            problems.append(
                f"operation 顺序/集合不同：{x.get('operation_id')} vs {y.get('operation_id')}"
            )
            continue
        for key in sorted(set(x) | set(y)):
            if x.get(key) != y.get(key):
                problems.append(f"{x.get('operation_id')} 的 {key} 不同")
    return problems


def render_text(doc: Mapping[str, Any]) -> str:
    """人读格式：逐项摊开四段事实 + 八条判据结论。"""
    lines: list[str] = [
        f"[同步 operation 结算后复核] schema={doc['schema']} "
        f"generated_at={doc['generated_at']}",
        f"  dialect={doc['dialect']} read_only_enforced={doc['read_only_enforced']} "
        f"operations={doc['operation_count']} failures={doc['failure_count']} "
        f"content_digest={doc['content_digest'][:16]}…",
    ]
    for op in doc["operations"]:
        lines.append("")
        lines.append(
            f"[{'OK  ' if op['ok'] else 'FAIL'}] {op['operation_id']}  {op['direction']}  "
            f"state={op['state']} terminal={op['is_terminal']}"
        )
        lines.append(f"       entry={op['entry_id']}  wp={op['wp_id']}")
        lines.append(
            f"  ① 终态/时间戳：accepted_at={op['accepted_at']} "
            f"finished_at={op['finished_at']} "
            f"error={op['error_code']}@{op['error_stage']}"
        )
        c = op["conflicts"]
        lines.append(
            f"  ② 冲突行：total={c['total']} resolved={c['resolved']} "
            f"abandoned={c['abandoned']} superseded={c['superseded']} "
            f"unsettled={c['unsettled']} 三列齐备={c['triplet_complete']} "
            f"裁决成对={c['resolution_pair_complete']} "
            f"settled={c['settled']} fully={c['is_fully_settled']}"
        )
        v = op["version_chain"]
        lines.append(
            f"  ③ 版本链：app={v['application_id']}({v['application_state']}) "
            f"rev {v['base_content_version_revision']}→{v['result_revision']}"
            f"/cv={v['result_content_version_revision']} "
            f"(wp.content_revision={v['current_revision']}) "
            f"rep={v['result_representation_id']}"
            f"(gen={v['result_representation_generation']}) "
            f"base_rep={v['base_representation_id']}"
        )
        lines.append(
            f"        entry_state={v['entry_state_present']} "
            f"entry_current={v['entry_current_representation_id']}"
            f"(gen={v['entry_representation_generation']}) room={v['room_id']}"
        )
        lines.append(f"  ④ 审计轨迹 {len(op['timeline'])} 条：")
        for e in op["timeline"]:
            lines.append(
                f"       #{e['sequence_no']} {e['from_state']} → {e['to_state']} "
                f"stage={e['stage']} actor={e['actor_type']}:{e['actor_id']} "
                f"at={e['occurred_at']}"
            )
        for verdict in op["verdicts"]:
            mark = "  ok  " if verdict["ok"] else " FAIL "
            gap = f" [已登记缺口 {verdict['known_gap']}]" if verdict["known_gap"] else ""
            lines.append(f"  [{mark}] {verdict['rule_id']}{gap}：{verdict['detail']}")
    lines.append("")
    if doc["failure_count"]:
        lines.append(f"[FAIL] {doc['failure_count']} 条 operation 有不一致（见上方 FAIL 行）")
    else:
        lines.append(f"[OK] {doc['operation_count']} 条 operation 全部通过")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


async def _run(args: argparse.Namespace) -> int:
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    engine = create_async_engine(args.database_url or settings.DATABASE_URL, poolclass=NullPool)
    read_only_enforced = False
    dialect = "unknown"
    try:
        async with engine.connect() as conn:
            dialect = conn.dialect.name
            if dialect == "postgresql":
                # 🔴 只读由库强制：本事务里任何写语句都会被数据库拒绝。
                await conn.execute(sa.text("SET TRANSACTION READ ONLY"))
                read_only_enforced = True
            try:
                reports = await collect_report(
                    conn,
                    operation_id=args.operation,
                    include_orphans=args.include_orphans,
                )
            finally:
                # 只读事务一律回滚（PG 上 `SET TRANSACTION READ ONLY` 也必须显式收尾）。
                await conn.rollback()
    finally:
        await engine.dispose()

    doc = build_document(reports, read_only_enforced=read_only_enforced, dialect=dialect)
    payload = (
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True)
        if args.json
        else render_text(doc)
    )
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8", newline="\n")
        print(f"[OK] 报告已写入 {args.output}")
    else:
        print(payload)
    return 0 if doc["failure_count"] == 0 else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "同步 operation 结算后复核（只读）：终态 / 冲突行 resolved-or-superseded / "
            "版本链指针 / 审计轨迹逐项可查"
        )
    )
    select = parser.add_mutually_exclusive_group()
    select.add_argument("--operation", type=UUID, default=None, help="只复核这一条 operation")
    select.add_argument(
        "--all",
        dest="review_all",
        action="store_true",
        help=f"复核全部已离开 created 的 operation（{', '.join(_REVIEWABLE_STATES)}）",
    )
    parser.add_argument(
        "--include-orphans",
        action="store_true",
        help=(
            "连同没有 application 的 operation 一起复核 —— 只影响 html_to_oo 方向的"
            "输出量（784 条），不影响判据"
        ),
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON（便于对拍）")
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "把报告写到文件（UTF-8，不换行包裹）。**优先用这个而不是 shell 重定向** —— "
            "PowerShell 的 `Out-File` / `>` 会按控制台宽度折行，把 JSON 写坏"
        ),
    )
    parser.add_argument(
        "--database-url", default=None, help="覆盖 DATABASE_URL（默认取 app.core.config.settings）"
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("LEFT", "RIGHT"),
        default=None,
        help="对拍两份 --json 输出（忽略 generated_at）",
    )
    args = parser.parse_args(argv)

    if args.compare:
        left_path, right_path = (Path(p) for p in args.compare)
        try:
            left = json.loads(left_path.read_text(encoding="utf-8-sig"))
            right = json.loads(right_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            print(f"[ERROR] 读不出报告：{exc}", file=sys.stderr)
            return 2
        problems = compare_documents(left, right)
        if problems:
            print(f"[FAIL] 两份报告不一致（{len(problems)} 处）：")
            for line in problems:
                print(f"  - {line}")
            return 1
        print("[OK] 两份报告逐字段一致（已忽略 generated_at）")
        return 0

    if args.operation is None and not args.review_all:
        parser.error("必须给 --operation <uuid> 或 --all")

    try:
        return asyncio.run(_run(args))
    except Exception as exc:  # noqa: BLE001 - 环境失败与「发现不一致」必须可区分
        print(f"[ERROR] 复核无法进行：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
