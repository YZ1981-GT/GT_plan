"""公式推送的 platform durable job executor（B4）。"""
from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from app.core.database import async_session
from app.deps import assert_project_permission
from app.models.core import User
from app.services import platform_job_service as jobs
from app.services.formula_push import engine
from app.services.platform_job_registry import (
    ExecutorOutcome,
    ProgressReporter,
    register_executor,
)

OPERATION = "formula_push"
MAX_CODES = 50


class FormulaPushJobError(RuntimeError):
    retryable = False


class FormulaPushLeaseLost(FormulaPushJobError):
    """进度 fence 拒绝，旧 worker 不能再继续产生可见副作用。"""


async def execute_formula_push(
    claim: jobs.PlatformJobClaim,
    report: ProgressReporter,
) -> ExecutorOutcome:
    """执行时重验 edit 权限，运行推送，再由 platform worker 围栏写 job 终态。"""
    payload = claim.payload_ref
    try:
        year = int(payload.get("year"))
    except (TypeError, ValueError) as exc:
        raise FormulaPushJobError("公式推送任务缺少有效年度") from exc
    if not 2000 <= year <= 2100:
        raise FormulaPushJobError("公式推送任务年度超出 2000..2100")

    raw_codes = payload.get("wp_codes")
    if raw_codes is not None and not isinstance(raw_codes, list):
        raise FormulaPushJobError("公式推送任务 wp_codes 形态无效")
    codes = [str(code).strip() for code in raw_codes or [] if str(code).strip()]
    if raw_codes is not None and not codes:
        raise FormulaPushJobError("公式推送任务 wp_codes 不能为空列表")
    if len(codes) > MAX_CODES:
        raise FormulaPushJobError("公式推送任务 wp_codes 超过 50 项上限")

    if not await report(0, 1, "校验项目权限与公式配置", "authorizing"):
        raise FormulaPushLeaseLost("公式推送任务租约已失效")

    try:
        async with async_session() as db:
            user = (
                await db.execute(sa.select(User).where(User.id == claim.actor_id))
            ).scalar_one_or_none()
            if user is None:
                raise FormulaPushJobError("公式推送任务发起人已不存在")
            await assert_project_permission(db, user, claim.project_id, "edit")
            result = await engine.run_and_commit(
                db,
                project_id=claim.project_id,
                year=year,
                trigger=engine.MANUAL,
                triggered_by=claim.actor_id,
                dry_run=False,
                codes=codes or None,
            )
    except engine.PushActionError as exc:
        raise FormulaPushJobError(str(exc)) from exc

    if not await report(1, 1, "公式推送完成，正在保存结果", "finalizing"):
        raise FormulaPushLeaseLost("公式推送任务租约已失效")
    summary: dict[str, Any] = result.summary()
    return ExecutorOutcome(
        result_ref={
            "summary": summary,
            "formula_push_run_id": summary.get("run_id"),
        }
    )


register_executor(OPERATION, execute_formula_push)
