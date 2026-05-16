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
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chain_execution import ChainExecution
from app.services.prerequisite_checker import PrerequisiteChecker

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
        await svc.full_recalc(project_id, year)
        return {"recalculated": True}

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

        # 2. Get project info for audit stage flags
        try:
            proj_result = await db.execute(
                sa.select(Project.template_type, Project.report_scope).where(Project.id == project_id)
            )
            proj_row = proj_result.first()
            template_type = (proj_row[0] if proj_row else None) or "soe"
            report_scope = (proj_row[1] if proj_row else None) or "standalone"
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass
            template_type, report_scope = "soe", "standalone"

        # Build project context flags for conditional triggers
        project_flags = {
            "consolidated": report_scope == "consolidated",
            "listed": template_type == "listed",
            "listed_or_segments": template_type == "listed",
            "listed_or_regulated": template_type == "listed",
            "listed_or_ipo": template_type == "listed",
            "small_soe_or_general": template_type == "soe",
            "large_soe": False,  # default; can be overridden by project metadata
            "first_engagement": False,  # default; can be overridden
            "group_audit": report_scope == "consolidated",
            # Default to False for cycle-specific flags; will be set based on TB analysis
        }

        # 3. Query TB to get actual account codes
        try:
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
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass
            tb_accounts = set()

        # 4. Determine cycle-specific flags from TB accounts
        prefix_to_flag = {
            "1001": "has_cash", "1002": "has_cash", "1012": "has_cash",
            "1122": "has_revenue", "6001": "has_revenue",
            "1401": "has_inventory", "1402": "has_inventory", "1403": "has_inventory",
            "1511": "has_investment", "1101": "has_investment",
            "1601": "has_fixed_assets", "1602": "has_fixed_assets",
            "1604": "has_construction",
            "1701": "has_intangibles", "1702": "has_intangibles",
            "5401": "has_rd", "6604": "has_rd",
            "2001": "has_debt", "2501": "has_debt",
            "1631": "has_lease", "2802": "has_lease",
        }
        for acc in tb_accounts:
            flag = prefix_to_flag.get(acc)
            if flag:
                project_flags[flag] = True
        # Related parties default True for SOE (regulatory requirement)
        project_flags.setdefault("has_related_parties", template_type == "soe")
        # Has policy change: assume False unless tracked elsewhere
        project_flags.setdefault("has_policy_change", False)

        # 5. Match workpapers
        # Strategy: Subtables (D2-2/E1-1) collapse to primary (D2/E1).
        # Each primary becomes ONE workpaper file with multiple sheets (auto-merged from sibling files).
        matched_primary: set[str] = set()  # 主编码集合（实际生成的 wp_index）
        matched_subtable_info: dict[str, list[str]] = {}  # primary → [subtables matched]
        matched_details: list[dict] = []

        for m in mappings:
            wp_code = m.get("wp_code", "")
            if not wp_code:
                continue

            # Determine primary code (collapse D2-2 → D2)
            primary_code = wp_code.split("-")[0] if "-" in wp_code else wp_code
            is_subtable = wp_code != primary_code

            # Case A: Account-based (D-N cycles, has account_codes)
            account_codes = m.get("account_codes", [])
            if account_codes and any(acc in tb_accounts for acc in account_codes):
                matched_primary.add(primary_code)
                if is_subtable:
                    matched_subtable_info.setdefault(primary_code, []).append(wp_code)
                continue

            # Case B: Audit-stage based (A/B/C/S cycles)
            trigger = m.get("trigger")
            if trigger == "must_have":
                matched_primary.add(primary_code)
                if is_subtable:
                    matched_subtable_info.setdefault(primary_code, []).append(wp_code)
                continue
            if trigger == "conditional":
                applies_when = m.get("applies_when")
                if applies_when and project_flags.get(applies_when):
                    matched_primary.add(primary_code)
                    if is_subtable:
                        matched_subtable_info.setdefault(primary_code, []).append(wp_code)
                continue

        if not matched_primary:
            return {"created": 0, "skipped_reason": "无匹配的底稿模板"}

        matched_codes = matched_primary  # for downstream code compatibility

        # 6. Build wp_code → name lookup (also build subtable name list per primary)
        code_name_map = {m["wp_code"]: m.get("wp_name", "") for m in mappings}

        # 7. Generate workpapers (with template file copy + metadata link)
        from app.services.wp_template_init_service import init_workpaper_from_template

        # Pre-load wp_template_metadata for matched codes (for audit_cycle/component_type)
        meta_map: dict[str, dict] = {}
        if matched_codes:
            try:
                meta_result = await db.execute(
                    sa.text("""
                        SELECT wp_code, audit_stage, cycle, component_type, file_format
                        FROM wp_template_metadata
                        WHERE wp_code = ANY(:codes)
                    """),
                    {"codes": list(matched_codes)},
                )
                for row in meta_result.mappings().all():
                    meta_map[row["wp_code"]] = dict(row)
            except Exception:
                try:
                    await db.rollback()
                except Exception:
                    pass

        created_count = 0
        copied_count = 0
        for code in sorted(matched_codes):
            try:
                # Idempotent check
                existing = await db.execute(
                    sa.select(WpIndex.id).where(
                        WpIndex.project_id == project_id,
                        WpIndex.wp_code == code,
                    )
                )
                existing_id = existing.scalar_one_or_none()
                if existing_id:
                    continue

                wp_name = code_name_map.get(code) or f"底稿{code}"

                # Resolve cycle: prefer metadata's cycle, fallback to first letter of code
                meta = meta_map.get(code, {})
                cycle = meta.get("cycle") or (code[0] if code and code[0].isalpha() else None)

                # Create WpIndex
                wp_index = WpIndex(
                    project_id=project_id,
                    wp_code=code,
                    wp_name=wp_name,
                    audit_cycle=cycle,
                    status=WpStatus.not_started,
                )
                db.add(wp_index)
                await db.flush()

                # Create WorkingPaper record (file_path will be updated by init_workpaper_from_template)
                wp = WorkingPaper(
                    wp_index_id=wp_index.id,
                    project_id=project_id,
                    source_type=WpSourceType.template,
                    file_path=f"storage/projects/{project_id}/workpapers/{code}.xlsx",
                    parsed_data={},
                )
                db.add(wp)
                await db.flush()
                created_count += 1

                # Copy template file from wp_templates/ to project storage
                try:
                    actual_path = init_workpaper_from_template(
                        project_id=project_id,
                        wp_id=wp.id,
                        wp_code=code,
                    )
                    if actual_path:
                        # Update file_path to match actual extension (xlsx vs docx vs xlsm)
                        wp.file_path = str(actual_path)
                        copied_count += 1
                except Exception as ce:
                    logger.warning("Template file copy failed for %s: %s", code, ce)
            except Exception as e:
                logger.warning("Failed to create workpaper for %s: %s", code, e)
                try:
                    await db.rollback()
                except Exception:
                    pass

        # Stats by cycle
        from collections import Counter
        cycle_stats = Counter(c[0] for c in matched_codes if c)
        matched_details = [
            {"cycle": cycle, "count": count}
            for cycle, count in sorted(cycle_stats.items())
        ]

        # Total subtables collapsed (sheets within primary workpapers)
        total_subtables = sum(len(subs) for subs in matched_subtable_info.values())

        return {
            "created": created_count,  # 主底稿数（实际生成的 wp_index 文件）
            "files_copied": copied_count,
            "primary_workpapers": len(matched_codes),  # = created
            "subtables_merged_as_sheets": total_subtables,  # 子表合并为 sheet
            "subtable_breakdown": {
                primary: subs
                for primary, subs in sorted(matched_subtable_info.items())
                if subs  # only show primaries with subtables
            },
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
