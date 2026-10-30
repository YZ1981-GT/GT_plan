"""表间审核执行 · 五表可观测性 + run_id 贯穿（formula-manager-closure Phase 6 Task 6.4）.

## 这个模块在干什么

审计报告第十节整改步骤 6 的验收口径：

    每次执行写 run/issue/hint/outbox/audit 并可查询；去掉"执行 0 条仍成功"。

本模块把**表间审核执行**（`logic_check.execute_report_cross_checks`，Phase 6 Task 6.2
已接通 year 契约 + `cross_check_results` 落库）升级为「一次执行 = 一个 run_id，贯穿
run / issue / hint / outbox / audit 五类产出，且均可按 run_id 查询」，并消除
"执行 0 条仍成功"——没有任何可执行勾稽时显式返回 `no_result`（无结果），不冒充
`success`。

## 五表真实名与 run_id 来源

| 逻辑角色 | 真实表 / 写入点                                     | run_id 来源 |
|----------|------------------------------------------------------|-------------|
| run      | ``draft_refresh_audit``（``DraftRefreshAudit``）     | ``id`` 列（本次生成的 run_id 即 run 记录主键） |
| issue    | ``cross_check_results``（``CrossCheckResult`` ORM）  | 写进每行 ``details.run_id`` |
| hint     | run 记录 ``detail.hints`` + outbox payload           | 随 run 记录 / outbox 带 run_id |
| outbox   | ``formula_runtime_outbox``（``FormulaRuntimeOutbox``）| ``run_id`` 列（FK→draft_refresh_audit.id） |
| audit    | ``append_audit_log`` 哈希链（``audit_log_entries``） | 写进 ``details.run_id`` |

**为什么 run 记录必须先写**：``formula_runtime_outbox.run_id`` 是 FK →
``draft_refresh_audit.id``。不先写 run 记录，outbox INSERT 会违反外键约束。故
执行顺序固定为 **run → issue → hint(随 run) → outbox → audit**，五处共用同一 run_id。

## 0 条语义（去掉"执行 0 条仍成功"）

7 条勾稽种子是**固定公式集**，``run_cross_checks`` 无论有无数据都会迭代 7 条产出
7 个 ``outcome`` —— 故"0 条"**不是** outcome 个数为 0，而是**没有任何可供勾稽的
报表源数据**（``financial_report`` 该项目/年度 0 行）。改造前 router 直接对
"全 0 的 row_cache"跑 7 条勾稽并返回"全部通过"，把"根本没有数据可核"伪装成
"执行成功、勾稽全过"。本模块据**报表源行数**判定：

- 报表源行数 == 0 → ``status = "no_result"``（无结果），run 记录 ``result_status``
  落 ``blocked``（DraftRefreshAudit 合法取值之一），detail 标 ``no_result``；
  **不写 outbox**（无值变更可传播）、不写 issue（没有真实勾稽产出可归档）。
- 报表源行数 > 0 → ``status = "executed"``，正常写五表。

``CrossCheckRunResult.executed_count`` 在此语义下 = 报表源行数（0 即无结果），不是
固定的 7；``issue_count`` / ``hint_count`` 仍为真实产出计数。

## 工程铁律

service 只 ``flush`` 不 ``commit``；router 层统一 ``commit``。PG / SQLite 双兼容
（outbox 的 ``ON CONFLICT`` 与 ``append_audit_log`` 的 SQLite 分支均已就绪）。
落库逐值对拍由 Phase 7 最小数据运行坐实——本模块只做接线 + 可查询 + run_id 贯穿 +
0 条语义。

Requirements: 10（传播侧）、11.4（run_id 贯穿）。
design §5 步骤 6、§8 错误处理表（执行 0 条显式"无结果"）。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import FinancialReport
from app.models.workpaper_models import DraftRefreshAudit, FormulaRuntimeOutbox
from app.models.wp_optimization_models import CrossCheckResult as CrossCheckResultRow
from app.services.audit_log_helper import append_audit_log
from app.services.formula_management.logic_check import (
    CROSS_CHECK_STATUS_FAILED,
    CROSS_CHECK_STATUS_PASSED,
    CrossCheckResult,
    execute_report_cross_checks,
)
from app.services.formula_runtime.outbox import write_outbox_event

logger = logging.getLogger(__name__)

#: 执行有可执行勾稽时的 run 状态（对外契约 ``status`` 字段）。
STATUS_EXECUTED = "executed"
#: 没有任何可执行勾稽时的 run 状态（"无结果"，去掉"执行 0 条仍成功"）。
STATUS_NO_RESULT = "no_result"

#: run 记录（``draft_refresh_audit``）的 ``scope`` 字面量 —— 表间审核执行。
_RUN_SCOPE = "formula:report-cross-check"
#: run 记录的 ``operator_role`` 占位（表间审核为只读计算，无角色写操作语义）。
_DEFAULT_OPERATOR_ROLE = "readonly"
#: outbox 事件类型（表间审核结论可供下游 stale / 质量评分消费）。
_OUTBOX_EVENT_TYPE = "cross_check_executed"


@dataclass
class CrossCheckRunResult:
    """一次表间审核执行的运行结果（run_id 贯穿五表）。"""

    run_id: uuid.UUID
    status: str  # STATUS_EXECUTED | STATUS_NO_RESULT
    executed_count: int
    issue_count: int
    hint_count: int
    result: CrossCheckResult
    #: 本次是否写了 outbox（0 条时为 False —— 无值变更可传播）。
    outbox_written: bool = False
    #: 便于直接序列化的 hint 文案列表。
    hints: list[str] = field(default_factory=list)

    @property
    def is_no_result(self) -> bool:
        return self.status == STATUS_NO_RESULT


def _issue_run_id_tag(details: dict[str, Any] | None, run_id: uuid.UUID) -> dict[str, Any]:
    """给 cross_check_results.details 打上 run_id（issue ↔ run 关联）。"""
    merged = dict(details or {})
    merged["run_id"] = str(run_id)
    return merged


async def _write_run_record(
    db: AsyncSession,
    *,
    run_id: uuid.UUID,
    project_id: uuid.UUID,
    year: int,
    operator_id: uuid.UUID,
    operator_role: str,
    executed_count: int,
    issue_count: int,
    hint_count: int,
    status: str,
) -> None:
    """写 run 记录（``draft_refresh_audit``）—— 五表的锚点，必须最先写。

    ``result_status`` 列只接受 {success, blocked, rolled_back}（String(20)）：
    - 有执行 → ``success``；
    - 0 条无结果 → ``blocked``（= 未产出有效结果，语义最贴切），并在 detail
      显式标 ``no_result`` 供查询区分。
    """
    result_status = "success" if status == STATUS_EXECUTED else "blocked"
    run = DraftRefreshAudit(
        id=run_id,
        project_id=project_id,
        year=year,
        operator_id=operator_id,
        operator_role=operator_role or _DEFAULT_OPERATOR_ROLE,
        scope=_RUN_SCOPE,
        # 表间审核只读、无 TB 快照；用确定性占位（run_id 派生）保证非空且可追溯。
        tb_snapshot_hash=uuid.uuid5(uuid.NAMESPACE_OID, str(run_id)).hex,
        affected_count=executed_count,
        result_status=result_status,
        detail={
            "kind": "report_cross_check",
            "status": status,
            "executed_count": executed_count,
            "issue_count": issue_count,
            "hint_count": hint_count,
        },
    )
    db.add(run)
    await db.flush()


async def _persist_issues_with_run_id(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    year: int,
    run_id: uuid.UUID,
    result: CrossCheckResult,
) -> int:
    """落库勾稽结论（``cross_check_results``），每行 details 带 run_id。

    与 ``logic_check.persist_cross_check_results`` 同口径（先删同键旧行再插），但
    额外把 run_id 写进 details，使 issue ↔ run 可按 run_id 关联查询。fail-open：
    落库失败只记 WARNING 返 0，不阻断。
    """
    if not result.outcomes:
        return 0

    issue_by_formula = {}
    for issue in result.issues:
        issue_by_formula.setdefault(issue.formula_id, issue)

    try:
        rule_ids = [o.formula_id for o in result.outcomes]
        await db.execute(
            sa.delete(CrossCheckResultRow).where(
                CrossCheckResultRow.project_id == project_id,
                CrossCheckResultRow.year == year,
                CrossCheckResultRow.rule_id.in_(rule_ids),
            )
        )
        written = 0
        for outcome in result.outcomes:
            issue = issue_by_formula.get(outcome.formula_id)
            left = issue.left_value if issue else None
            right = issue.right_value if issue else None
            diff = (left - right) if (left is not None and right is not None) else None
            db.add(
                CrossCheckResultRow(
                    project_id=project_id,
                    year=year,
                    rule_id=outcome.formula_id,
                    left_amount=left,
                    right_amount=right,
                    difference=diff,
                    status=(
                        CROSS_CHECK_STATUS_PASSED
                        if outcome.passed
                        else CROSS_CHECK_STATUS_FAILED
                    ),
                    details=_issue_run_id_tag(
                        {
                            "description": outcome.description,
                            "expression": outcome.expression,
                            "issue_description": issue.description if issue else None,
                            "source": "formula_management.logic_check",
                        },
                        run_id,
                    ),
                )
            )
            written += 1
        await db.flush()
        return written
    except Exception as exc:  # noqa: BLE001 — fail-open（只读勾稽结果仍应返回）
        logger.warning(
            "cross_check_results 落库失败（project=%s year=%s run=%s）：%s",
            project_id, year, run_id, exc,
        )
        return 0


async def _write_outbox(
    db: AsyncSession,
    *,
    run_id: uuid.UUID,
    project_id: uuid.UUID,
    year: int,
    issue_count: int,
    hint_count: int,
) -> bool:
    """写 outbox 事件（``formula_runtime_outbox``），run_id 贯穿。

    event_key 以 run_id 派生保证幂等（同 run 重复调用不重复写）。fail-open。
    """
    try:
        await write_outbox_event(
            db,
            run_id=run_id,
            event_type=_OUTBOX_EVENT_TYPE,
            event_key=f"cross-check:{run_id}",
            payload={
                "project_id": str(project_id),
                "year": year,
                "issue_count": issue_count,
                "hint_count": hint_count,
            },
        )
        return True
    except Exception as exc:  # noqa: BLE001 — fail-open（传播失败不阻断勾稽返回）
        logger.warning(
            "formula_runtime_outbox 写入失败（run=%s）：%s", run_id, exc
        )
        return False


async def _write_audit(
    db: AsyncSession,
    *,
    run_id: uuid.UUID,
    project_id: uuid.UUID,
    operator_id: uuid.UUID,
    status: str,
    executed_count: int,
    issue_count: int,
) -> None:
    """写审计哈希链（``append_audit_log``），run_id 写进 details。

    复用 ``formula_changed`` event_type（report/consol 统一公式执行留痕入口）。
    best_effort（ADR-ALC-07）：审计写入失败只记 WARNING，不阻断勾稽结果返回。
    """
    try:
        async with db.begin_nested():
            await append_audit_log(
                db,
                {
                    "user_id": operator_id,
                    "project_id": project_id,
                    "action": "formula_cross_check_executed",
                    "resource_type": "report_cross_check",
                    "resource_id": str(run_id),
                    "details": {
                        "event_type": "formula_changed",
                        "module": "report_cross_check",
                        "row_code": "*",
                        "action": "execute",
                        "old_formula": None,
                        "new_formula": None,
                        "result_value": None,
                        "run_id": str(run_id),
                        "status": status,
                        "executed_count": executed_count,
                        "issue_count": issue_count,
                    },
                },
            )
    except Exception as exc:  # noqa: BLE001 — best_effort
        logger.warning("cross-check 审计写入失败（run=%s）：%s", run_id, exc)


async def _count_source_rows(
    db: AsyncSession, *, project_id: uuid.UUID, year: int
) -> int:
    """数该项目/年度的报表源行数（``financial_report`` 未删除行）。

    = 0 → 无任何可勾稽的数据（"0 条"），据此判「无结果」而非在全 0 数据上跑出
    "全部通过"的假成功。
    """
    return (
        await db.execute(
            sa.select(sa.func.count(FinancialReport.id)).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.is_deleted == sa.false(),
            )
        )
    ).scalar_one()


async def execute_cross_check_run(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    year: int,
    operator_id: uuid.UUID,
    operator_role: str = _DEFAULT_OPERATOR_ROLE,
) -> CrossCheckRunResult:
    """执行一次表间审核，五表贯穿同一 run_id，并据 0 条判「无结果」。

    执行顺序（固定，outbox 有 FK→run 记录）：

      1. 计算勾稽（``execute_report_cross_checks(persist=False)``，不自行落库——
         落 issue 的责任收归本模块以统一打 run_id）。
      2. 生成 run_id，写 run 记录（``draft_refresh_audit``）。
      3. 若 ``executed_count == 0``：status=no_result，不写 issue/outbox，只写
         run + audit（留下"本次无结果"这一事实可查）。
      4. 否则：写 issue（带 run_id）→ outbox（run_id）→ audit（run_id）。

    service 只 flush，调用方（router）commit。

    Returns:
        ``CrossCheckRunResult``：run_id + status + 计数 + 原始 CrossCheckResult。
    """
    # ── 0. 数报表源行数：0 行 = 没有可勾稽的数据 = "无结果"（非在全 0 上假成功）──
    source_rows = await _count_source_rows(db, project_id=project_id, year=year)

    # ── 1. 计算勾稽（本模块统一落 issue，故 persist=False） ──────────────
    result = await execute_report_cross_checks(
        db, project_id=project_id, year=year, persist=False
    )
    issue_count = len(result.issues)
    hint_count = len(result.hints)
    hints = [h.hint_text for h in result.hints]

    status = STATUS_EXECUTED if source_rows > 0 else STATUS_NO_RESULT
    # executed_count 对外语义 = 本次有多少可勾稽的源行（0 即无结果），不是固定 7。
    executed_count = source_rows
    if status == STATUS_NO_RESULT:
        # 无源数据时在全 0 row_cache 上跑出的 7 条"通过"是假象 —— 丢弃它，换成空
        # 结果，使对外 issue_list/results 为空（"无结果"不带任何假产出）。
        result = CrossCheckResult(
            issues=[], outcomes=[], last_computed_at=None, hints=[]
        )
        issue_count = 0
        hint_count = 0
        hints = []

    # ── 2. 写 run 记录（锚点，最先写；outbox FK 依赖它）───────────────────
    run_id = uuid.uuid4()
    await _write_run_record(
        db,
        run_id=run_id,
        project_id=project_id,
        year=year,
        operator_id=operator_id,
        operator_role=operator_role,
        executed_count=executed_count,
        issue_count=issue_count,
        hint_count=hint_count,
        status=status,
    )

    outbox_written = False
    if status == STATUS_EXECUTED:
        # ── 3a. issue（带 run_id）──────────────────────────────────────
        await _persist_issues_with_run_id(
            db, project_id=project_id, year=year, run_id=run_id, result=result
        )
        # ── 3b. outbox（run_id 贯穿）───────────────────────────────────
        outbox_written = await _write_outbox(
            db,
            run_id=run_id,
            project_id=project_id,
            year=year,
            issue_count=issue_count,
            hint_count=hint_count,
        )
    # ── 4. audit（run_id 贯穿；0 条也留痕"本次无结果"）───────────────────
    await _write_audit(
        db,
        run_id=run_id,
        project_id=project_id,
        operator_id=operator_id,
        status=status,
        executed_count=executed_count,
        issue_count=issue_count,
    )

    return CrossCheckRunResult(
        run_id=run_id,
        status=status,
        executed_count=executed_count,
        issue_count=issue_count,
        hint_count=hint_count,
        result=result,
        outbox_written=outbox_written,
        hints=hints,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 按 run_id 查询（可查询性验收）
# ─────────────────────────────────────────────────────────────────────────────


async def get_run_record(
    db: AsyncSession, run_id: uuid.UUID
) -> DraftRefreshAudit | None:
    """按 run_id 查 run 记录（``draft_refresh_audit``）。"""
    return (
        await db.execute(
            sa.select(DraftRefreshAudit).where(DraftRefreshAudit.id == run_id)
        )
    ).scalar_one_or_none()


async def get_issues_by_run(
    db: AsyncSession, run_id: uuid.UUID
) -> list[CrossCheckResultRow]:
    """按 run_id 查勾稽结论行（``cross_check_results`` 的 details.run_id 匹配）。

    PG 用 JSONB ``->>``；SQLite 用 ``json_extract``（双兼容）。
    """
    bind = db.get_bind()
    is_sqlite = bind is not None and bind.dialect.name == "sqlite"
    if is_sqlite:
        cond = sa.text("json_extract(details, '$.run_id') = :rid").bindparams(
            rid=str(run_id)
        )
    else:
        cond = CrossCheckResultRow.details["run_id"].astext == str(run_id)
    rows = (
        await db.execute(sa.select(CrossCheckResultRow).where(cond))
    ).scalars().all()
    return list(rows)


async def get_outbox_by_run(
    db: AsyncSession, run_id: uuid.UUID
) -> list[FormulaRuntimeOutbox]:
    """按 run_id 查 outbox 事件（``formula_runtime_outbox``）。"""
    rows = (
        await db.execute(
            sa.select(FormulaRuntimeOutbox).where(
                FormulaRuntimeOutbox.run_id == run_id
            )
        )
    ).scalars().all()
    return list(rows)
