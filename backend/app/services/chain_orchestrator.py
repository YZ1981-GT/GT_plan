"""ChainOrchestrator — 全链路编排服务

Requirements: 1.1-1.9
Design: D1 顺序管线 + 容错跳过, D8 互斥锁

执行顺序: recalc_tb → generate_workpapers → generate_reports → generate_notes
依赖自动补充: 请求 generate_notes 自动补充 generate_reports
互斥锁: pg_advisory_xact_lock / asyncio.Lock fallback (SQLite)
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chain_execution import ChainExecution
from app.services.prerequisite_checker import PrerequisiteChecker
from app.services.wp_generation_matching import (
    business_category_flags,
    match_workpapers,
    tb_account_flags,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ChainStep(str, Enum):
    RECALC_TB = "recalc_tb"
    GENERATE_WORKPAPERS = "generate_workpapers"
    GENERATE_REPORTS = "generate_reports"
    GENERATE_NOTES = "generate_notes"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STEP_ORDER = [
    ChainStep.RECALC_TB,
    ChainStep.GENERATE_WORKPAPERS,
    ChainStep.GENERATE_REPORTS,
    ChainStep.GENERATE_NOTES,
]

DEPENDENCIES: dict[ChainStep, list[ChainStep]] = {
    ChainStep.GENERATE_WORKPAPERS: [ChainStep.RECALC_TB],
    ChainStep.GENERATE_REPORTS: [ChainStep.RECALC_TB],
    ChainStep.GENERATE_NOTES: [ChainStep.GENERATE_REPORTS],
}

# Map step → prerequisite_checker action name
STEP_TO_ACTION: dict[ChainStep, str] = {
    ChainStep.RECALC_TB: "recalc",
    ChainStep.GENERATE_WORKPAPERS: "generate_workpapers",
    ChainStep.GENERATE_REPORTS: "generate_reports",
    ChainStep.GENERATE_NOTES: "generate_notes",
}

# In-memory locks for SQLite fallback (keyed by "project_id:year")
_memory_locks: dict[str, asyncio.Lock] = {}


# ---------------------------------------------------------------------------
# Progress callback type
# ---------------------------------------------------------------------------

ProgressCallback = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]


# ---------------------------------------------------------------------------
# ChainOrchestrator
# ---------------------------------------------------------------------------


class ChainOrchestrator:
    """全链路编排服务"""

    def __init__(self):
        self._prerequisite_checker = PrerequisiteChecker()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute_full_chain(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        steps: list[ChainStep] | None = None,
        force: bool = False,
        trigger_type: str = "manual",
        triggered_by: UUID | None = None,
        progress_cb: ProgressCallback | None = None,
    ) -> ChainExecution:
        """Execute the full chain (or subset of steps).

        Args:
            db: async database session
            project_id: project UUID
            year: fiscal year
            steps: subset of steps to execute (None = all 4)
            force: if True, skip prerequisites and mark as skipped
            trigger_type: manual/auto/batch
            triggered_by: user UUID who triggered
            progress_cb: async callback(event_type, payload) for SSE

        Returns:
            ChainExecution record with final status
        """
        # 1. Resolve steps with dependency auto-supplement
        resolved_steps = self._resolve_steps(steps)

        # Disable autoflush to prevent premature INSERT of ChainExecution
        original_autoflush = db.autoflush
        db.autoflush = False
        logger.info("execute_full_chain: autoflush=%s→False, steps=%s", original_autoflush, [s.value for s in resolved_steps])

        # 2. Acquire mutex lock (with session recovery)
        try:
            acquired = await self._try_acquire_lock(db, project_id, year)
            logger.info("Lock acquired: %s", acquired)
        except Exception:
            try:
                await db.rollback()
                acquired = await self._try_acquire_lock(db, project_id, year)
            except Exception as lock_err:
                logger.warning("Lock acquisition failed, proceeding without lock: %s", lock_err)
                acquired = True
        if not acquired:
            raise ChainConflictError(
                f"项目 {project_id} 年度 {year} 正在执行中，请稍后重试"
            )

        try:
            # 3. Execute steps sequentially (execution record created AFTER)
            failed_steps: set[ChainStep] = set()
            start_time = time.time()
            step_results: dict[str, dict] = {s.value: {"status": StepStatus.PENDING.value} for s in resolved_steps}

            # DEBUG: verify session is clean before loop
            _test = await db.execute(sa.text("SELECT 1"))
            logger.info("Session check before loop: %s", _test.scalar())
            failed_steps: set[ChainStep] = set()
            start_time = time.time()

            for step in resolved_steps:
                # Check if this step depends on a failed step
                deps = DEPENDENCIES.get(step, [])
                if any(d in failed_steps for d in deps):
                    step_results[step.value] = {
                        "status": StepStatus.SKIPPED.value,
                        "reason": "dependency_failed",
                    }
                    if progress_cb:
                        await progress_cb("step_skipped", {
                            "step": step.value,
                            "reason": "dependency_failed",
                        })
                    continue

                # Check prerequisites (skip entirely when force=True to avoid session issues)
                if not force:
                    action = STEP_TO_ACTION.get(step, step.value)
                    prereq = await self._prerequisite_checker.check(db, project_id, year, action)

                    if not prereq["ok"]:
                        step_results[step.value] = {
                            "status": StepStatus.SKIPPED.value,
                            "reason": "prerequisite_not_met",
                            "message": prereq["message"],
                        }
                        if progress_cb:
                            await progress_cb("step_skipped", {
                                "step": step.value,
                                "reason": prereq["message"],
                            })
                        continue

                # Execute the step
                step_start = time.time()
                step_results[step.value] = {"status": StepStatus.RUNNING.value, "started_at": datetime.now(timezone.utc).isoformat()}

                if progress_cb:
                    await progress_cb("step_started", {
                        "step": step.value,
                        "status": "running",
                        "started_at": datetime.now(timezone.utc).isoformat(),
                    })

                try:
                    summary = await self._execute_step(db, project_id, year, step)
                    step_duration = int((time.time() - step_start) * 1000)
                    step_results[step.value] = {
                        "status": StepStatus.COMPLETED.value,
                        "duration_ms": step_duration,
                        "summary": summary,
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    }
                    if progress_cb:
                        await progress_cb("step_completed", {
                            "step": step.value,
                            "status": "completed",
                            "duration_ms": step_duration,
                            "summary": summary,
                        })
                except Exception as e:
                    step_duration = int((time.time() - step_start) * 1000)
                    failed_steps.add(step)
                    step_results[step.value] = {
                        "status": StepStatus.FAILED.value,
                        "duration_ms": step_duration,
                        "error": str(e),
                    }
                    logger.exception("Chain step %s failed for project %s year %d", step.value, project_id, year)
                    # Recover session from aborted transaction state
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    if progress_cb:
                        await progress_cb("step_failed", {
                            "step": step.value,
                            "status": "failed",
                            "error_message": str(e),
                            "duration_ms": step_duration,
                        })

            # 5. Determine final status + create execution record
            total_duration = int((time.time() - start_time) * 1000)

            step_statuses = [v.get("status") for v in step_results.values()]
            if all(s == StepStatus.COMPLETED.value for s in step_statuses):
                final_status = "completed"
            elif all(s in (StepStatus.FAILED.value, StepStatus.SKIPPED.value) for s in step_statuses):
                final_status = "failed"
            elif any(s == StepStatus.FAILED.value for s in step_statuses):
                final_status = "partially_failed"
            else:
                final_status = "completed"

            # Create and persist execution record
            execution = ChainExecution(
                project_id=project_id,
                year=year,
                status=final_status,
                steps=step_results,
                trigger_type=trigger_type,
                triggered_by=triggered_by,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                total_duration_ms=total_duration,
            )
            # Commit step results first to preserve chain work even if execution record fails
            try:
                await db.commit()
            except Exception:
                try:
                    await db.rollback()
                except Exception:
                    pass

            # Now persist execution record (best-effort, in a new transaction)
            try:
                db.add(execution)
                await db.commit()
            except Exception:
                try:
                    db.expunge(execution)
                    await db.rollback()
                except Exception:
                    pass

            if progress_cb:
                await progress_cb("chain_completed", {
                    "execution_id": str(execution.id) if execution.id else "unknown",
                    "status": final_status,
                    "total_duration_ms": total_duration,
                    "results": step_results,
                })

            # Return execution-like object
            execution.status = final_status
            execution.steps = step_results
            execution.total_duration_ms = total_duration
            return execution

        finally:
            db.autoflush = original_autoflush
            try:
                await self._release_lock(db, project_id, year)
            except Exception:
                pass

    async def retry_execution(
        self,
        db: AsyncSession,
        project_id: UUID,
        execution_id: str,
        progress_cb: ProgressCallback | None = None,
    ) -> ChainExecution:
        """Retry failed steps from a previous execution."""
        result = await db.execute(
            sa.select(ChainExecution).where(
                ChainExecution.id == execution_id,
                ChainExecution.project_id == str(project_id),
            )
        )
        prev = result.scalar_one_or_none()
        if not prev:
            raise ValueError(f"Execution {execution_id} not found")

        # Collect failed steps
        failed_steps = [
            ChainStep(k) for k, v in prev.steps.items()
            if v.get("status") == StepStatus.FAILED.value
        ]
        if not failed_steps:
            raise ValueError("No failed steps to retry")

        return await self.execute_full_chain(
            db=db,
            project_id=project_id,
            year=prev.year,
            steps=failed_steps,
            force=True,
            trigger_type="retry",
            triggered_by=None,
            progress_cb=progress_cb,
        )

    async def get_execution_history(
        self,
        db: AsyncSession,
        project_id: UUID,
        limit: int = 100,
        status: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[ChainExecution]:
        """Get execution history for a project."""
        query = sa.select(ChainExecution).where(
            ChainExecution.project_id == str(project_id)
        )
        if status:
            query = query.where(ChainExecution.status == status)
        if start_time:
            query = query.where(ChainExecution.started_at >= start_time)
        if end_time:
            query = query.where(ChainExecution.started_at <= end_time)

        query = query.order_by(ChainExecution.started_at.desc()).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Step execution
    # ------------------------------------------------------------------

    async def _execute_step(
        self, db: AsyncSession, project_id: UUID, year: int, step: ChainStep
    ) -> dict[str, Any]:
        """Execute a single chain step and return summary."""
        if step == ChainStep.RECALC_TB:
            return await self._step_recalc_tb(db, project_id, year)
        elif step == ChainStep.GENERATE_WORKPAPERS:
            return await self._step_generate_workpapers(db, project_id, year)
        elif step == ChainStep.GENERATE_REPORTS:
            return await self._step_generate_reports(db, project_id, year)
        elif step == ChainStep.GENERATE_NOTES:
            return await self._step_generate_notes(db, project_id, year)
        else:
            raise ValueError(f"Unknown step: {step}")

    async def _step_recalc_tb(self, db: AsyncSession, project_id: UUID, year: int) -> dict:
        """Execute trial balance recalculation."""
        from app.services.trial_balance_service import TrialBalanceService
        svc = TrialBalanceService(db)
        result = await svc.full_recalc(project_id, year)
        fallback = result.get("income_expense_fallback_accounts", [])
        out: dict = {"recalculated": True}
        if fallback:
            out["warnings"] = [
                f"损益类科目 {', '.join(fallback[:10])}{'等' if len(fallback) > 10 else ''}"
                f" 的余额表缺少借方/贷方发生额列，已按期末余额绝对值替代（结果可能不准确，建议导入含发生额的余额表）"
            ]
        return out

    async def _step_generate_workpapers(self, db: AsyncSession, project_id: UUID, year: int) -> dict:
        """Execute workpaper generation with smart matching.

        Strategy:
        1. Account-based matching for D-N cycles (TB account → workpaper code)
        2. Audit-stage based for A/B/C/S cycles (must_have always; conditional by project flags)
        3. Include sub-tables (E1-1, E1-2, etc.) for D-N matched primary codes
        """
        from app.models.workpaper_models import WpIndex, WpStatus, WorkingPaper, WpSourceType
        from app.models.audit_platform_models import TrialBalance
        from app.models.core import Project
        import sqlalchemy as sa
        import json
        from pathlib import Path

        # 1. Load wp_account_mapping.json
        mapping_path = Path(__file__).parent.parent.parent / "data" / "wp_account_mapping.json"
        try:
            with open(mapping_path, "r", encoding="utf-8") as f:
                mapping_data = json.load(f)
            mappings = mapping_data.get("mappings", [])
        except Exception as e:
            return {"created": 0, "skipped_reason": f"加载科目映射失败: {e}"}

        # 2. Get project info for audit stage flags（读失败只回滚这次读：原先整会话 rollback，连试算表重算一起丢）
        try:
            async with db.begin_nested():
                proj_row = (await db.execute(
                    sa.select(
                        Project.template_type,
                        Project.report_scope,
                        Project.scenario,
                        Project.has_foreign_currency,
                        Project.audit_type,
                        Project.is_large_soe,
                        Project.wizard_state,
                        Project.business_category,
                    ).where(Project.id == project_id)
                )).first()
            template_type = (proj_row[0] if proj_row else None) or "soe"
            report_scope = (proj_row[1] if proj_row else None) or "standalone"
            scenario = (proj_row[2] if proj_row else None) or "normal"
            has_foreign_currency = bool(proj_row[3]) if proj_row else False
            audit_type = (proj_row[4] if proj_row else None) or "financial"
            is_large_soe = bool(proj_row[5]) if proj_row else False
            wizard_state = (proj_row[6] if proj_row else None) or {}
            business_category = (proj_row[7] if proj_row else None) or ""
        except SQLAlchemyError:
            logger.warning("chain_orchestrator: 读取项目信息失败，按默认口径匹配底稿", exc_info=True)
            template_type, report_scope = "soe", "standalone"
            scenario, has_foreign_currency = "normal", False
            audit_type, is_large_soe, wizard_state = "financial", False, {}
            business_category = ""

        # Build project context flags for conditional triggers
        audit_type_l = str(audit_type or "").lower()
        integrated_audit = (
            "integrated" in audit_type_l
            or "内控" in str(audit_type or "")
            or "icfr" in audit_type_l
            or "integrated" in str(scenario or "").lower()
        )
        listed_or_ipo = template_type == "listed" or scenario in ("ipo", "listed")
        project_flags = {
            "consolidated": report_scope == "consolidated",
            "listed": template_type == "listed",
            "listed_or_segments": template_type == "listed",
            "listed_or_regulated": template_type == "listed",
            "listed_or_ipo": listed_or_ipo,
            "small_soe_or_general": template_type == "soe",
            "large_soe": is_large_soe,
            "first_engagement": False,  # default; can be overridden
            "group_audit": report_scope == "consolidated",
            # E1 Sprint 2 Task 2.2: scenario 驱动文件级裁剪（F1.2）
            "scenario_normal": scenario == "normal",
            "scenario_ipo_or_above": scenario in ("ipo", "listed", "transfer", "restructure", "fraud_response"),
            "has_foreign_currency": has_foreign_currency,
            # B60 P3 attachment matrix flags (overridable via wizard_state.b60_attachment_flags)
            "integrated_audit": integrated_audit,
            "soe_annual": template_type == "soe",
            "needs_regulatory_filing": listed_or_ipo,
            "needs_it_audit": False,
            "it_team_executes": False,
            "uses_expert": False,
            # Default to False for cycle-specific flags; will be set based on TB analysis
        }
        # Merge explicit B60 matrix answers from project wizard / attachment_flags
        if isinstance(wizard_state, dict):
            b60_flags = wizard_state.get("b60_attachment_flags") or wizard_state.get("attachment_flags") or {}
            if isinstance(b60_flags, dict):
                for k, v in b60_flags.items():
                    if isinstance(v, bool):
                        project_flags[k] = v
            # Convenience: wizard may set has_it_audit / uses_expert at top level
            if isinstance(wizard_state.get("has_it_audit"), bool):
                project_flags["needs_it_audit"] = wizard_state["has_it_audit"]
            if isinstance(wizard_state.get("it_team_executes"), bool):
                project_flags["it_team_executes"] = wizard_state["it_team_executes"]
            if isinstance(wizard_state.get("uses_expert"), bool):
                project_flags["uses_expert"] = wizard_state["uses_expert"]
        # IT team execute implies needs_it_audit
        if project_flags.get("it_team_executes"):
            project_flags["needs_it_audit"] = True

        # business_category → biz_ flags for applicable_when matching (S32~S35 etc.).
        # Keep this in the shared predicate module so generation and render-config
        # cannot drift on normalization or the listed-template rule.
        project_flags.update(
            business_category_flags(business_category, template_type)
        )


        # 3. Query TB to get actual account codes
        try:
            async with db.begin_nested():
                tb_result = await db.execute(
                    sa.select(TrialBalance.standard_account_code)
                    .where(
                        TrialBalance.project_id == project_id,
                        TrialBalance.year == year,
                        TrialBalance.is_deleted == sa.false(),
                    )
                    .distinct()
                )
                tb_accounts = {r[0] for r in tb_result.all() if r[0]}
        except SQLAlchemyError:
            logger.warning("chain_orchestrator: 读取试算表科目失败，只按审计阶段匹配底稿", exc_info=True)
            tb_accounts = set()

        # 4. Determine cycle-specific flags from TB accounts（码表与改正说明见 wp_generation_matching.TB_ACCOUNT_FLAGS）
        project_flags.update(tb_account_flags(tb_accounts))
        # Related parties default True for SOE (regulatory requirement)
        project_flags.setdefault("has_related_parties", template_type == "soe")
        # Has policy change: assume False unless tracked elsewhere
        project_flags.setdefault("has_policy_change", False)

        # E1 Sprint 2 Task 2.32: scenario / has_foreign_currency / 1502 数字货币科目存在性
        # 三类 sheet 过滤规则（与 useUniverSheetNav scenarioFilter 对齐）：
        # (1) (修订前)/(示例)/(提示) → init 时统一过滤（前端导航 + chain merge 跳过）
        # (2) 双附注按 template_type 二选一（已通过 wp_account_mapping 控制）
        # (3) 双 E1-3 按 has_foreign_currency 二选一（前端 useUniverSheetNav 隐藏）
        # (4) 数字货币 E1-4 按 has_digital_currency 触发（TB 含 1502 科目存在性）
        project_flags["has_digital_currency"] = "1502" in tb_accounts
        # Strategy: Subtables (D2-2/E1-1) collapse to primary (D2/E1).
        # Each primary becomes ONE workpaper file with multiple sheets (auto-merged from sibling files).
        # 主编码集合（实际生成的 wp_index）+ primary → [subtables matched]；规则见 wp_generation_matching.match_workpapers
        matched_primary, matched_subtable_info = match_workpapers(mappings, tb_accounts, project_flags)

        # 5b. 执行中的自定义程序（is_custom、有 wp_code）与科目匹配结果合并后一起经保留范围判定
        #     （spec procedure-chain-hardening-and-java-contracts R11.1：原先自定义程序在裁剪过滤之后追加，绕过了保留范围）。
        #     读不到程序 / 裁剪结果即抛出、本步失败 —— 不按「无裁剪」继续。
        from app.models.procedure_models import ProcedureInstance
        from app.services.procedure_scope_retention import TrimScopeUnavailable, plan_generation
        from app.services.wp_generate_file import create_template_workpaper
        from app.services.wp_generation_receipt import GenerationReceipt
        from app.services.wp_name_source import resolve_wp_name

        try:
            async with db.begin_nested():
                custom_rows = (await db.execute(
                    sa.select(ProcedureInstance.wp_code, ProcedureInstance.procedure_name).where(
                        ProcedureInstance.project_id == project_id,
                        ProcedureInstance.is_deleted == sa.false(),
                        ProcedureInstance.is_custom == sa.true(),
                        ProcedureInstance.status == "execute",
                        ProcedureInstance.wp_code.isnot(None),
                    )
                )).all()
        except SQLAlchemyError as exc:
            raise TrimScopeUnavailable(f"读取自定义程序失败：{exc}") from exc
        custom_names = {code: name for code, name in custom_rows if code}
        if not matched_primary and not custom_names:
            return {**GenerationReceipt().to_payload(), "skipped_reason": "无匹配的底稿模板"}

        plan = await plan_generation(db, project_id, sorted(set(matched_primary) | set(custom_names)))
        receipt = GenerationReceipt.from_plan(plan)
        if plan.skipped_trimmed_codes:
            logger.info("chain_orchestrator: 程序裁剪过滤 %d 个主编码：%s",
                        len(plan.skipped_trimmed_codes), plan.skipped_trimmed_codes)
        matched_codes = set(plan.to_create) | set(plan.existing_codes) | set(plan.in_recycle_codes)
        if not matched_codes:
            return {**receipt.to_payload(), "skipped_reason": "所有匹配底稿均已被裁剪"}

        # 6. 名称 / 循环：wp_account_mapping → 自定义程序名；循环优先取模板元数据
        code_name_map = {m["wp_code"]: m.get("wp_name", "") for m in mappings}
        meta_map: dict[str, dict] = {}
        if plan.to_create:
            try:
                async with db.begin_nested():
                    meta_result = await db.execute(
                        sa.text("SELECT wp_code, cycle FROM wp_template_metadata WHERE wp_code IN :codes")
                        .bindparams(sa.bindparam("codes", expanding=True)),
                        {"codes": list(plan.to_create)},
                    )
                    meta_map = {row["wp_code"]: dict(row) for row in meta_result.mappings().all()}
            except SQLAlchemyError:
                logger.warning("chain_orchestrator: 读取底稿模板元数据失败，循环按编码首字母", exc_info=True)

        # 7. 逐码建底稿（单码保存点：失败只回滚该码、删掉已落文件、进回执 failures，不计入新建；
        #    原先先计数再复制、复制失败只记日志，单码失败还整会话 rollback）。表头不在本步填（计入 header_unfilled）。
        for code in plan.to_create:
            await create_template_workpaper(
                db, receipt, project_id=project_id, wp_code=code,
                wp_name=resolve_wp_name(code, code_name_map.get(code), custom_names.get(code)),
                audit_cycle=meta_map.get(code, {}).get("cycle") or (code[0] if code[0].isalpha() else None),
                scenario=scenario, has_foreign_currency=has_foreign_currency,
            )

        # Stats by cycle
        from collections import Counter
        cycle_stats = Counter(c[0] for c in matched_codes if c)
        matched_details = [
            {"cycle": cycle, "count": count}
            for cycle, count in sorted(cycle_stats.items())
        ]

        # Total subtables collapsed (sheets within primary workpapers)
        total_subtables = sum(len(subs) for subs in matched_subtable_info.values())

        # ─── 8. 为 skip 子底稿创建独立 wp_index（聚合组件内嵌 Tab 需要） ───────
        # 当主底稿(如 A1)已创建，其子表(如 A1-11~A1-16)在 wp_code_overrides 中标为 skip
        # 时，前端聚合组件(GtA1Dashboard/GtA17Bundle 等)需要通过 wp_index 查找这些子底稿
        # 的 wp_id 来渲染内嵌 Tab。只给本步之后在库里的主底稿建（新建成功 / 原已有；在回收站或建失败的不建），
        # 子底稿同样经保留范围判定（主底稿保留、子表自己被裁，如 A1-11 不适用）、逐码保存点。
        from app.services.wp_code_override_loader import load_wp_code_overrides
        _skip_overrides = load_wp_code_overrides()
        live_primary = sorted(set(receipt.created_codes) | set(plan.existing_codes))
        sub_codes = [
            code
            for primary_code in live_primary
            for code in sorted(c for c, ct in _skip_overrides.items() if ct == "skip" and c.startswith(primary_code + "-"))
        ]
        sub_plan = await plan_generation(db, project_id, list(dict.fromkeys(sub_codes)), scope=plan.scope)
        receipt.add_plan(sub_plan)
        sub_created: list[str] = []
        for sub_code in sub_plan.to_create:
            try:
                async with db.begin_nested():
                    sub_wp_index = WpIndex(
                        project_id=project_id,
                        wp_code=sub_code,
                        wp_name=resolve_wp_name(sub_code, code_name_map.get(sub_code)),
                        audit_cycle=sub_code[0] if sub_code[0].isalpha() else None,
                        status=WpStatus.not_started,
                    )
                    db.add(sub_wp_index)
                    await db.flush()
                    # 子底稿不落文件（内嵌在主底稿聚合组件里，打开时懒加载落文件并回写 file_path）
                    db.add(WorkingPaper(
                        wp_index_id=sub_wp_index.id,
                        project_id=project_id,
                        source_type=WpSourceType.template,
                        file_path=f"storage/projects/{project_id}/workpapers/{sub_code}.xlsx",
                        parsed_data={},
                    ))
                    await db.flush()
                sub_created.append(sub_code)
            except Exception as sub_err:  # noqa: BLE001 — 单码失败不影响其余，如实进回执
                receipt.add_failure(sub_code, sub_err)
                logger.warning("chain_orchestrator: skip sub-workpaper %s creation failed: %s", sub_code, sub_err)
        # ─── END skip 子底稿创建 ─────────────────────────────────────────────────

        return {
            **receipt.to_payload(),  # created = 新建的主底稿数（失败不计）；回执字段见 wp_generation_receipt
            "files_copied": len(receipt.created_codes) - len(receipt.blank_codes),
            "primary_workpapers": len(matched_codes),
            "subtables_merged_as_sheets": total_subtables,  # 子表合并为 sheet
            "subtable_breakdown": {
                primary: subs
                for primary, subs in sorted(matched_subtable_info.items())
                if subs  # only show primaries with subtables
            },
            "sub_workpapers_created": sub_created,
            "matched_accounts": len(tb_accounts),
            "metadata_loaded": len(meta_map),
            "by_cycle": matched_details,
            "project_flags": {k: v for k, v in project_flags.items() if v},
        }

    async def _step_generate_reports(self, db: AsyncSession, project_id: UUID, year: int) -> dict:
        """Execute report generation."""
        from app.services.report_engine import ReportEngine
        from app.models.core import Project
        import sqlalchemy as sa

        # Resolve applicable_standard from project's template_type + report_scope
        result = await db.execute(
            sa.select(Project.template_type, Project.report_scope).where(Project.id == project_id)
        )
        row = result.first()
        if row and row[0] and row[1]:
            applicable_standard = f"{row[0]}_{row[1]}"
        else:
            applicable_standard = "soe_standalone"  # safe default

        engine = ReportEngine(db)
        result = await engine.generate_all_reports(project_id, year, applicable_standard=applicable_standard)
        # Filter out non-list keys (like coverage_stats)
        report_types = [k for k, v in result.items() if isinstance(v, list)] if isinstance(result, dict) else []
        return {
            "applicable_standard": applicable_standard,
            "report_types": report_types,
            "coverage": result.get("coverage_stats", {}).get("coverage_pct") if isinstance(result, dict) else None,
        }

    async def _step_generate_notes(self, db: AsyncSession, project_id: UUID, year: int) -> dict:
        """Execute disclosure notes generation."""
        from app.services.disclosure_engine import DisclosureEngine
        from app.models.core import Project
        import sqlalchemy as sa

        # Get project's template_type for selecting note template
        result = await db.execute(
            sa.select(Project.template_type).where(Project.id == project_id)
        )
        template_type = (result.scalar_one_or_none() or "soe")

        engine = DisclosureEngine(db)
        notes = await engine.generate_notes(project_id, year, template_type=template_type)
        count = len(notes) if isinstance(notes, list) else 0
        return {"template_type": template_type, "generated": count}

    # ------------------------------------------------------------------
    # Dependency resolution
    # ------------------------------------------------------------------

    def _resolve_steps(self, steps: list[ChainStep] | None) -> list[ChainStep]:
        """Resolve steps with auto-supplement of dependencies.

        If steps is None, return all steps in order.
        Otherwise, add transitive dependencies and return in STEP_ORDER.
        """
        if steps is None:
            return list(STEP_ORDER)

        resolved: set[ChainStep] = set(steps)

        # Add transitive dependencies
        changed = True
        while changed:
            changed = False
            for step in list(resolved):
                for dep in DEPENDENCIES.get(step, []):
                    if dep not in resolved:
                        resolved.add(dep)
                        changed = True

        # Return in canonical order
        return [s for s in STEP_ORDER if s in resolved]

    # ------------------------------------------------------------------
    # Mutex lock
    # ------------------------------------------------------------------

    async def _try_acquire_lock(self, db: AsyncSession, project_id: UUID, year: int) -> bool:
        """Try to acquire mutual exclusion lock.

        Uses in-memory asyncio.Lock for simplicity and cross-DB compatibility.
        PG advisory locks cause session state issues when combined with ORM flush.
        """
        lock_key = f"{project_id}:{year}"
        if lock_key not in _memory_locks:
            _memory_locks[lock_key] = asyncio.Lock()
        lock = _memory_locks[lock_key]
        if lock.locked():
            return False
        await lock.acquire()
        return True

    async def _release_lock(self, db: AsyncSession, project_id: UUID, year: int) -> None:
        """Release the mutual exclusion lock."""
        lock_key = f"{project_id}:{year}"
        if lock_key in _memory_locks and _memory_locks[lock_key].locked():
            _memory_locks[lock_key].release()


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ChainConflictError(Exception):
    """Raised when a chain execution is already running for the same project/year."""
    pass


# Module-level singleton
chain_orchestrator = ChainOrchestrator()


# ---------------------------------------------------------------------------
# F2 / F3 / F4 sheet 合并去重 + scenario 文件裁剪工具 — re-export
# （spec workpaper-d-sales-cycle 任务 1.5 / 1.8 / 2.1）
#
# spec 任务文本声明 `_normalize_sheet_name` / `_merge_sheets_dedup` /
# `SCENARIO_TO_FILE_FILTER` / `_filter_files_by_scenario` 位于本模块；
# 实际实现位于 ``app.services.wp_template_init_service``（多文件合并 + 文件
# 加载的真实调用位置）。在此 re-export 以满足 spec 描述的模块位置，使
# `from app.services.chain_orchestrator import SCENARIO_TO_FILE_FILTER` 可用，
# 同时避免 chain_orchestrator → wp_template_init_service 的循环导入。
# ---------------------------------------------------------------------------

from app.services.wp_template_init_service import (  # noqa: E402,F401
    MEASUREMENT_MODEL_FILTER,
    SCENARIO_TO_FILE_FILTER,
    _ensure_d4_ipo_loaded,
    _filter_files_by_scenario,
    _merge_sheets_dedup,
    _normalize_sheet_name,
    _should_skip_historical_sheet,
)
