"""formula_runtime.coordinator — FormulaRuntimeCoordinator.

Task 13 | Req 1,3,7,8 | P2,P3,P8,P9

Coordinates formula evaluation and mutation plan generation.
Called by DraftRefreshOrchestrator to replace the placeholder scope handlers
with real domain mutations via:

1. Collect formula definitions & targets from DB
2. Batch ACNR resolve + ownership/binding validation
3. FormulaValueLoader.load_many to build FormulaContext
4. Call engine.execute_batch
5. Convert MutationIntents to FormulaMutations via adapters' prepare_many
6. Return mutation plan (not committed)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WpFormula
from app.services.formula_management.engine import (
    BatchExecutionResult,
    BatchFormulaContext,
    BatchFormulaDefinition,
    CanonicalFormulaTarget as EngineTarget,
    MutationIntent,
    execute_batch,
)
from app.services.formula_runtime.contracts import (
    CanonicalFormulaTarget,
    FormulaMutation,
)
from app.services.formula_runtime.value_loader import FormulaValueLoader

logger = logging.getLogger(__name__)


# ─── Result dataclass ────────────────────────────────────────────────────────


@dataclass
class MutationPlanResult:
    """Mutation plan result — NOT COMMITTED."""

    mutations: list[FormulaMutation] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    hints: list[dict] = field(default_factory=list)
    scope_failures: list[dict] = field(default_factory=list)


# ─── Scope → domain mapping ─────────────────────────────────────────────────

_SCOPE_DOMAIN_MAP: dict[str, str] = {
    "report": "report",
    "workpaper": "workpaper",
    "adjudication": "adjudication",
    "note": "note",
}

#: `scope_failures[].kind` 的「本项目无公式定义」取值（单一真源）。
#:
#: spec: formula-management-runtime-closure Task 11（Requirements 6.4, 6.5）
#: 前端 `GtRefreshScopeDialog.vue` 与守卫 `test_formula_type_runtime_status.py`
#: 都按这个字面量识别该态，禁在两侧各写一份字符串。
NO_FORMULAS_KIND = "no_formulas"


# ─── Coordinator ─────────────────────────────────────────────────────────────


class FormulaRuntimeCoordinator:
    """Coordinates formula evaluation and mutation plan generation.

    Does NOT commit. Caller (orchestrator/service) is responsible for
    transaction management.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def generate_mutation_plan(
        self,
        project_id: UUID,
        year: int,
        scopes: list[str],
    ) -> MutationPlanResult:
        """Generate a mutation plan for the given scopes.

        Steps:
          1. Load formula definitions from DB filtered by scopes/domain
          2. Build canonical targets from formula definitions
          3. Batch load values via FormulaValueLoader
          4. Call engine.execute_batch to evaluate formulas
          5. Convert MutationIntents → FormulaMutations via adapter prepare_many
          6. Return plan (mutations, issues, hints, scope_failures) — not committed
        """
        plan = MutationPlanResult()

        # ── Step 1: Load formula definitions from DB ─────────────────────
        formulas = await self._load_formulas(project_id, year, scopes)
        if not formulas:
            logger.info(
                "FormulaRuntimeCoordinator: no formulas found for project=%s year=%d scopes=%s",
                project_id, year, scopes,
            )
            # 🔴 空结果必须可见（spec formula-management-runtime-closure Task 11 /
            # Requirements 6.4, 6.5）：改造前这里静默 early-return，而 `wp_formula`
            # 全库 **0 行** ⇒ 整条 mutation plan 流水线从上线起从未有真实数据流经过，
            # 上层（draft_refresh → GtRefreshScopeDialog）显示的是「刷新成功、0 处变更」
            # —— 与「公式都算过了、确实没有需要改的」不可区分。
            # 追加一条 scope_failures 让「本项目尚未定义任何公式」这一事实透到 UI。
            plan.scope_failures.append({
                "addr_id": "",
                "kind": NO_FORMULAS_KIND,
                "detail": (
                    f"项目 {project_id} 年度 {year} 无公式定义"
                    f"（wp_formula 表内该项目 0 行，scopes={scopes}）"
                ),
            })
            return plan

        # ── Step 2: Build BatchFormulaDefinition + canonical targets ──────
        batch_defs, all_ref_addr_ids, targets_by_formula = self._build_batch_definitions(
            formulas, project_id, year
        )

        if not batch_defs:
            return plan

        # ── Step 3: Batch load values via FormulaValueLoader ─────────────
        # Build canonical targets for all referenced addr_ids
        ref_targets = self._build_ref_targets(all_ref_addr_ids, project_id, year)
        loader = FormulaValueLoader(self._session)
        load_result = await loader.load_many(ref_targets)

        # Build BatchFormulaContext from load result
        context = BatchFormulaContext(
            values=load_result.values,
            missing={i.addr_id for i in load_result.issues if i.kind == "miss"},
            ambiguous={i.addr_id for i in load_result.issues if i.kind == "ambiguous"},
        )

        # Record load issues as scope failures
        for issue in load_result.issues:
            if issue.kind in ("miss", "ambiguous"):
                plan.scope_failures.append({
                    "addr_id": issue.addr_id,
                    "kind": issue.kind,
                    "detail": issue.detail,
                })

        # ── Step 4: Execute batch ────────────────────────────────────────
        exec_result: BatchExecutionResult = execute_batch(
            formulas=batch_defs,
            context=context,
        )

        # Collect issues, hints, errors
        plan.issues.extend(exec_result.issues)
        plan.hints.extend(exec_result.hints)
        for error in exec_result.errors:
            plan.scope_failures.append(error)

        # ── Step 5: Convert MutationIntents → FormulaMutations ───────────
        mutations = await self._intents_to_mutations(
            exec_result.intents, project_id, year, scopes
        )
        plan.mutations = mutations

        return plan

    # ═══════════════════════════════════════════════════════════════════════
    # Internal helpers
    # ═══════════════════════════════════════════════════════════════════════

    async def _load_formulas(
        self,
        project_id: UUID,
        year: int,
        scopes: list[str],
    ) -> list[WpFormula]:
        """Load WpFormula definitions filtered by project and scope-relevant domains."""
        # Map scopes → formula_type filter is not needed; we load all formulas
        # for the project. Scope filtering is done by target domain in step 5.
        stmt = (
            select(WpFormula)
            .where(
                WpFormula.project_id == project_id,
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    def _build_batch_definitions(
        self,
        formulas: list[WpFormula],
        project_id: UUID,
        year: int,
    ) -> tuple[list[BatchFormulaDefinition], set[str], dict[str, EngineTarget | None]]:
        """Convert WpFormula ORM objects to BatchFormulaDefinition list.

        Returns:
            (batch_defs, all_ref_addr_ids, targets_by_formula_id)
        """
        batch_defs: list[BatchFormulaDefinition] = []
        all_ref_addr_ids: set[str] = set()
        targets_by_formula: dict[str, EngineTarget | None] = {}

        for formula in formulas:
            # Extract ref addr_ids from formula.refs (JSONB list)
            ref_ids: list[str] = []
            if isinstance(formula.refs, list):
                for ref_entry in formula.refs:
                    if isinstance(ref_entry, str):
                        ref_ids.append(ref_entry)
                    elif isinstance(ref_entry, dict):
                        addr = ref_entry.get("addr_id") or ref_entry.get("formula_ref", "")
                        if addr:
                            ref_ids.append(addr)

            all_ref_addr_ids.update(ref_ids)

            # Build target for auto_calc formulas
            target: EngineTarget | None = None
            ftype = (formula.formula_type or "auto_calc").strip()
            if ftype == "auto_calc" and formula.target_cell:
                # Build a target from the formula's context
                # Domain is inferred from formula context (category/sheet/wp)
                domain = self._infer_domain(formula)
                target = EngineTarget(
                    domain=domain,
                    project_id=project_id,
                    year=year,
                    addr_id=f"{formula.wp_id}/{formula.sheet_name}/{formula.target_cell}",
                    locator={
                        "wp_id": str(formula.wp_id),
                        "item": formula.sheet_name,
                        "cell": formula.target_cell,
                    },
                    wp_id=formula.wp_id,
                )

            targets_by_formula[str(formula.id)] = target

            batch_defs.append(BatchFormulaDefinition(
                id=str(formula.id),
                formula_type=ftype,
                expression=formula.expression or "",
                target=target,
                ref_addr_ids=ref_ids,
                issue_description=formula.issue_description,
                hint_text=formula.hint_text,
                addr_id=f"{formula.wp_id}/{formula.sheet_name}/{formula.target_cell}" if formula.target_cell else None,
            ))

        return batch_defs, all_ref_addr_ids, targets_by_formula

    def _build_ref_targets(
        self,
        addr_ids: set[str],
        project_id: UUID,
        year: int,
    ) -> list[CanonicalFormulaTarget]:
        """Build minimal CanonicalFormulaTarget list for value loading.

        For addr_ids we infer domain from the addr_id structure.
        """
        targets: list[CanonicalFormulaTarget] = []
        for addr_id in addr_ids:
            domain = self._domain_from_addr_id(addr_id)
            locator = self._locator_from_addr_id(addr_id, domain)
            targets.append(CanonicalFormulaTarget(
                domain=domain,
                project_id=project_id,
                year=year,
                addr_id=addr_id,
                locator=locator,
            ))
        return targets

    async def _intents_to_mutations(
        self,
        intents: list[MutationIntent],
        project_id: UUID,
        year: int,
        scopes: list[str],
    ) -> list[FormulaMutation]:
        """Convert MutationIntents from engine to FormulaMutation via adapters' prepare_many.

        Filters intents by requested scopes (domain matching).
        """
        if not intents:
            return []

        # Filter intents by scope
        scope_domains = set()
        for s in scopes:
            mapped = _SCOPE_DOMAIN_MAP.get(s)
            if mapped:
                scope_domains.add(mapped)
            # workpaper:{cycle} → workpaper domain
            if s.startswith("workpaper"):
                scope_domains.add("workpaper")

        # Group intents by domain
        by_domain: dict[str, list[MutationIntent]] = {}
        for intent in intents:
            if intent.target is None:
                continue
            domain = intent.target.domain
            if domain not in scope_domains:
                continue
            by_domain.setdefault(domain, []).append(intent)

        mutations: list[FormulaMutation] = []

        for domain, domain_intents in by_domain.items():
            adapter = self._get_adapter(domain)
            if adapter is None:
                # No adapter available — build mutations directly
                for intent in domain_intents:
                    mutations.append(self._intent_to_mutation(intent, project_id, year))
                continue

            # Use adapter.prepare_many to build mutations
            targets_for_adapter = []
            values_for_adapter: dict[str, Any] = {}
            for intent in domain_intents:
                t = intent.target
                canon = CanonicalFormulaTarget(
                    domain=t.domain,
                    project_id=t.project_id or project_id,
                    year=t.year or year,
                    addr_id=t.addr_id,
                    locator=dict(t.locator) if t.locator else {},
                    wp_id=t.wp_id,
                )
                targets_for_adapter.append(canon)
                values_for_adapter[t.addr_id] = intent.computed_value

            try:
                prepared = await adapter.prepare_many(targets_for_adapter, values_for_adapter)
                # Attach source_formula_id
                intent_map = {i.target.addr_id: i for i in domain_intents}
                for m in prepared:
                    source_id = None
                    if m.target.addr_id in intent_map:
                        fid = intent_map[m.target.addr_id].formula_id
                        try:
                            from uuid import UUID as _UUID
                            source_id = _UUID(fid)
                        except (ValueError, TypeError):
                            pass
                    mutations.append(FormulaMutation(
                        target=m.target,
                        before_value=m.before_value,
                        after_value=m.after_value,
                        expected_version=m.expected_version,
                        source_formula_id=source_id,
                    ))
            except Exception as exc:
                logger.warning(
                    "Adapter prepare_many failed for domain=%s: %s: %s",
                    domain, type(exc).__name__, exc,
                )
                # Fallback: build mutations without before_value
                for intent in domain_intents:
                    mutations.append(self._intent_to_mutation(intent, project_id, year))

        return mutations

    def _get_adapter(self, domain: str) -> Any | None:
        """Get the domain mutation adapter instance for the given domain."""
        try:
            if domain == "workpaper":
                from app.services.formula_runtime.adapters.workpaper import WorkpaperMutationAdapter
                return WorkpaperMutationAdapter(self._session)
            elif domain == "adjudication":
                from app.services.formula_runtime.adapters.adjudication import AdjudicationMutationAdapter
                return AdjudicationMutationAdapter(self._session)
            elif domain == "report":
                from app.services.formula_runtime.adapters.report import ReportMutationAdapter
                return ReportMutationAdapter(self._session)
            elif domain == "note":
                from app.services.formula_runtime.adapters.note import NoteMutationAdapter
                return NoteMutationAdapter(self._session)
        except Exception as exc:
            logger.warning("Could not load adapter for domain=%s: %s", domain, exc)
        return None

    @staticmethod
    def _intent_to_mutation(
        intent: MutationIntent,
        project_id: UUID,
        year: int,
    ) -> FormulaMutation:
        """Fallback conversion of MutationIntent to FormulaMutation without adapter."""
        t = intent.target
        target = CanonicalFormulaTarget(
            domain=t.domain,
            project_id=t.project_id or project_id,
            year=t.year or year,
            addr_id=t.addr_id,
            locator=dict(t.locator) if t.locator else {},
            wp_id=t.wp_id,
        )
        source_id = None
        try:
            from uuid import UUID as _UUID
            source_id = _UUID(intent.formula_id)
        except (ValueError, TypeError):
            pass
        return FormulaMutation(
            target=target,
            before_value=None,
            after_value=intent.computed_value,
            expected_version=None,
            source_formula_id=source_id,
        )

    @staticmethod
    def _infer_domain(formula: WpFormula) -> str:
        """Infer target domain from formula context.

        Uses category or sheet_name heuristics.
        """
        cat = (formula.category or "").lower()
        if "adjudication" in cat or "审定" in cat:
            return "adjudication"
        if "report" in cat or "报表" in cat:
            return "report"
        if "note" in cat or "附注" in cat:
            return "note"
        return "workpaper"

    @staticmethod
    def _domain_from_addr_id(addr_id: str) -> str:
        """Infer domain from addr_id structure.

        Known patterns:
        - report:{row_code} → report
        - note:{section}!{r}:{c} → note
        - tb:... or adjudication:... → adjudication (tb domain in loader)
        - others → workpaper
        """
        lower = addr_id.lower()
        if lower.startswith("report:") or lower.startswith("report/"):
            return "report"
        if lower.startswith("note:") or lower.startswith("note/"):
            return "note"
        if lower.startswith("tb:") or lower.startswith("adjudication:"):
            return "tb"
        return "workpaper"

    @staticmethod
    def _locator_from_addr_id(addr_id: str, domain: str) -> dict[str, str]:
        """Build a minimal locator from addr_id for value loading."""
        if domain == "tb":
            # tb:{account_code} or tb:{account_code}:{column}
            parts = addr_id.split(":", 2)
            code = parts[1] if len(parts) > 1 else ""
            col = parts[2] if len(parts) > 2 else "期末余额"
            return {"account_code": code, "column": col}
        if domain == "report":
            # report:{report_type}/{row_code} or report:{row_code}
            content = addr_id.split(":", 1)[1] if ":" in addr_id else addr_id
            parts = content.split("/", 1)
            if len(parts) == 2:
                return {"report_type": parts[0], "row_code": parts[1]}
            return {"row_code": content}
        if domain == "note":
            # note:{section}!{r}:{c}
            content = addr_id.split(":", 1)[1] if ":" in addr_id else addr_id
            if "!" in content:
                section, cell = content.split("!", 1)
                return {"section": section, "cell": cell}
            return {"section": content}
        # workpaper: {wp_id}/{sheet}/{cell}
        parts = addr_id.split("/", 2)
        if len(parts) >= 3:
            return {"wp_id": parts[0], "item": parts[1], "cell": parts[2]}
        if len(parts) == 2:
            return {"wp_id": parts[0], "item": parts[1]}
        return {}
