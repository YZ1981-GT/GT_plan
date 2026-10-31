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

from app.models.workpaper_models import WorkingPaper, WpFormula, WpIndex
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
from app.services.formula_runtime.typed_eval import (
    BatchDefinition as TypedBatchDefinition,
    PlanResult as TypedPlanResult,
    plan_batch,
)
from app.services.formula_runtime.value_loader import FormulaValueLoader
from app.services.wp_cell_reader import WpCellRead, _year_gate
from app.services.wp_ref_strict import read_wp_ref_strict

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
    "consol_worksheet": "consol_worksheet",
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
        formulas, wp_codes = await self._load_formulas(project_id, year, scopes)
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

        # ── Step 2: Build typed_eval definitions ──────────────────────────
        typed_defs = await self._build_typed_eval_definitions(formulas, wp_codes)
        if not typed_defs:
            return plan

        # ── Step 3: Year verdict (once for the batch) ────────────────────
        year_verdict = await _year_gate(self._session, project_id, year)

        # ── Step 4: plan_batch (typed_eval) ──────────────────────────────
        async def _read(wp_code: str, second: str, third: str | None) -> WpCellRead:
            return await read_wp_ref_strict(
                self._session, project_id, None, wp_code, second, third,
            )

        # 🔴 `eval_fn` 必传：`plan_batch` 在 `eval_fn is None` 时把 ok 结果的 `value` 置 None
        # （只建图、不求值），而下面 Step 5 产 MutationIntent 的条件里有 `outcome.value is not None`
        # ⇒ 不传就等于「全部有效公式都不产 mutation」，整条 Runtime 写入路径静默失效。
        # 2026-10-29 由需求 1.10 的 29 行重放用例（`test_runtime_replay_29_pg.py`）抓出：
        # 当时 13 条 blocked 与金标准完全一致，而 16 条 ok 产出 0 条 mutation。
        # 求值口径与预览端点 `typed_eval.evaluate_single` 同一个（严格 WP 代入，ADR-FHIC-06 第 7 点）。
        async def _eval(expression: str, wp_values: dict[str, Any]) -> tuple[Any, list[str]]:
            from app.services.wp_formula_eval_service import evaluate_wp_formula_expression

            return await evaluate_wp_formula_expression(
                self._session,
                project_id=project_id,
                year=year,
                expression=expression,
                wp_values=wp_values,
                strict_wp=True,
            )

        typed_result: TypedPlanResult = await plan_batch(
            typed_defs, year_verdict=year_verdict, read_ref=_read, eval_fn=_eval,
        )

        # ── Step 5: Convert typed_eval outcomes → FormulaMutations ───────
        # typed_eval PlanOutcome with state="ok" are mutation candidates;
        # blocked outcomes go to scope_failures.
        # We still need targets and adapters for actual mutations.
        batch_defs, all_ref_addr_ids, targets_by_formula = self._build_batch_definitions(
            formulas, project_id, year
        )

        # Build engine-compatible intents from typed_eval outcomes
        # 🔴 求值返回的 errors 非空 = 取不到数 / 写法无法识别 / L1 失败：`evaluate_wp_formula_expression` 此时返回的
        # value 是占位 0（需求 2.3「写入方须判 ok」），state 仍是 "ok"。照产 mutation 就是把「取不到」写成 0
        # （需求 1.3「取不到一律 blocked，不按 0 代入」）；value 为 None 时原先既不写也不报，静默丢掉 ⇒ 两种都进 scope_failures。
        intents: list[MutationIntent] = []
        for outcome in typed_result.outcomes:
            fid = str(outcome.formula_id)
            target = targets_by_formula.get(fid)
            eval_failed = outcome.state == "ok" and (bool(outcome.errors) or outcome.value is None)
            if outcome.state == "ok" and not eval_failed and target is not None:
                intents.append(MutationIntent(
                    formula_id=fid,
                    target=target,
                    computed_value=outcome.value,
                    formula_type="auto_calc",
                ))
            elif outcome.state == "blocked" or eval_failed:
                addr = ""
                if target is not None:
                    addr = target.addr_id or fid
                detail = outcome.reason or "；".join(outcome.errors) or (
                    "求值未得到数值" if eval_failed else "评估被拒")
                plan.scope_failures.append({
                    "addr_id": addr,
                    "kind": "typed_eval_blocked",
                    "detail": detail,
                })

        mutations = await self._intents_to_mutations(
            intents, project_id, year, scopes
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
    ) -> tuple[list[WpFormula], dict[UUID, str]]:
        """按项目、source_scope 年度、目标 domain 与 workpaper 循环过滤公式。

        Returns: (selected_formulas, wp_codes: {wp_id: wp_code})
        """
        result = await self._session.execute(
            select(WpFormula).where(WpFormula.project_id == project_id)
        )
        formulas = list(result.scalars().all())
        if not formulas:
            return [], {}

        wanted_domains: set[str] = set()
        wanted_cycles: set[str] = set()
        for scope in scopes:
            if scope.startswith("workpaper"):
                wanted_domains.add("workpaper")
                if ":" in scope:
                    cycle = scope.split(":", 1)[1].strip().upper()
                    if cycle:
                        wanted_cycles.add(cycle)
            elif scope in _SCOPE_DOMAIN_MAP:
                wanted_domains.add(_SCOPE_DOMAIN_MAP[scope])

        wp_ids = {formula.wp_id for formula in formulas if formula.wp_id}
        wp_codes: dict[UUID, str] = {}
        if wp_ids:
            rows = await self._session.execute(
                select(WorkingPaper.id, WpIndex.wp_code)
                .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
                .where(WorkingPaper.id.in_(wp_ids))
            )
            wp_codes = {row.id: str(row.wp_code or "") for row in rows}

        selected: list[WpFormula] = []
        for formula in formulas:
            source_scope = formula.source_scope if isinstance(formula.source_scope, dict) else {}
            source_year = source_scope.get("year")
            if source_year is not None and int(source_year) != year:
                continue
            domain = self._infer_domain(formula)
            if wanted_domains and domain not in wanted_domains:
                continue
            if domain == "workpaper" and wanted_cycles:
                code = wp_codes.get(formula.wp_id, "").upper()
                if not code or code[0] not in wanted_cycles:
                    continue
            selected.append(formula)
        return selected, wp_codes

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

            # Build a target for auto_calc formulas. 当前只对工作底稿 A1 目标具备
            # 可验证的写入载体；report/note/adjudication 必须由各自显式 binding 构造，
            # 禁止拿 sheet_name/target_cell 猜 locator 后写错库。
            target: EngineTarget | None = None
            ftype = (formula.formula_type or "auto_calc").strip()
            domain = self._infer_domain(formula)
            if ftype == "auto_calc" and formula.target_cell and domain == "workpaper":
                target = EngineTarget(
                    domain="workpaper",
                    project_id=project_id,
                    year=year,
                    addr_id=f"{formula.wp_id}/{formula.sheet_name}/{formula.target_cell}",
                    locator={
                        "wp_id": str(formula.wp_id),
                        "storage_kind": "parsed_data",
                        "sheet_name": formula.sheet_name,
                        "cell_ref": formula.target_cell,
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

    async def _build_typed_eval_definitions(
        self,
        formulas: list[WpFormula],
        wp_codes: dict[UUID, str],
    ) -> list[TypedBatchDefinition]:
        """将 WpFormula ORM 列表转为 typed_eval.BatchDefinition。

        body:
          - 按已存三元组优先填 stable_sheet_key / row_key / field_key
          - 取 parsed_data 供 _check_target_sheet 做目标表校验
          - ACNR full_resolve 不参与身份判定（ADR-FHIC-06 第 9 点）
        """
        # 预取 parsed_data（目标表校验用）
        wp_ids = list({f.wp_id for f in formulas if f.wp_id})
        pd_map: dict[UUID, dict | None] = {}
        if wp_ids:
            from sqlalchemy import select as sa_select
            rows = (await self._session.execute(
                sa_select(WorkingPaper.id, WorkingPaper.parsed_data)
                .where(WorkingPaper.id.in_(wp_ids))
            )).all()
            pd_map = {r[0]: r[1] for r in rows}

        defs: list[TypedBatchDefinition] = []
        for formula in formulas:
            code = wp_codes.get(formula.wp_id, "").upper()
            defs.append(TypedBatchDefinition(
                formula_id=str(formula.id),
                wp_code=code or str(formula.wp_id),
                expression=formula.expression or "",
                stable_sheet_key=formula.stable_sheet_key,
                row_key=formula.row_key,
                field_key=formula.field_key,
                stable_key_needs_review=formula.stable_key_needs_review,
                sheet_name=formula.sheet_name,
                target_cell=formula.target_cell,
                # 读到了底稿行却没有 parsed_data（NULL）⇒ 按「已提供、为空」校验（目标表必然不存在）；
                # 没读到（不在 pd_map）⇒ None，交由 typed_eval 不校验
                target_parsed_data=(pd_map[formula.wp_id] or {}) if formula.wp_id in pd_map else None,
            ))
        return defs

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
                raise RuntimeError(f"no_adapter_for_domain:{domain}")

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
                logger.error(
                    "Adapter prepare_many failed for domain=%s: %s: %s",
                    domain, type(exc).__name__, exc,
                )
                raise RuntimeError(
                    f"adapter_prepare_failed:{domain}:{type(exc).__name__}:{exc}"
                ) from exc

        return mutations

    def build_adapter_map(self, domains: set[str] | list[str]) -> dict[str, Any]:
        """为本次计划构造唯一 adapter 映射；缺 adapter fail-closed。"""
        result: dict[str, Any] = {}
        for domain in sorted(set(domains)):
            adapter = self._get_adapter(domain)
            if adapter is None:
                raise RuntimeError(f"no_adapter_for_domain:{domain}")
            result[domain] = adapter
        return result

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
            elif domain == "consol_worksheet":
                from app.services.formula_runtime.adapters.consol_worksheet import ConsolWorksheetMutationAdapter
                return ConsolWorksheetMutationAdapter(self._session)
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
