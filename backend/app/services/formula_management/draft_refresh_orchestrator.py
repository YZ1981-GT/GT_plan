"""全局刷新生成编排层（DraftRefreshOrchestrator）.

公式管理库（formula-management-library）Task 16.1 / 设计 §18（Req 21）。

**缺口（实证）**：``draft_refresh.py`` 的 ``/draft-refresh`` 直调
``DraftRefreshService.refresh()`` 时**不传 ``units``（默认空）、不调
``refresh_with_presets``、不传 ``page_keys``、不调用报表引擎/审定表回写/附注生成器**
→ 合伙人触发全局刷新只写审计、``affected_count=0``、零初稿。``DraftRefreshService``
是**治理编排层**（幂等 / Draft 标记 / 覆盖排除 / 快照 / 审计），等上游"喂 ``RefreshUnit``"，
但全局入口缺少驱动各生成器产出 ``RefreshUnit`` 的**生成编排层**。

**本模块**位于 router 与生成器/治理层之间——**按勾选 ``scopes`` 分派到各上游生成器
产出 ``RefreshUnit``，再交 ``DraftRefreshService.refresh_with_presets`` 统一治理**
（幂等 / Draft / 覆盖 / 快照 / 审计）。它不重复生成逻辑（生成归各既有引擎），只做
"scope → 生成器"的分派与结果归集。

**scope → 生成器映射（Req 21.1，design §18 表）**：

    | Refresh_Scope_Item        | 生成器                              | unit_scope              | page_key            |
    |---------------------------|-------------------------------------|-------------------------|---------------------|
    | ``report``                | 执行段 ``refresh_report_scope``（试算表重算 + ``generate_all_reports``，ADR-FHIC-08） | 无 | 预设库 ``report:`` 键 |
    | ``adjudication`` /        | 审定表回写 + 底稿生成               | ``audit_sheet:{...}``   | ``workpaper:{wp_code}`` |
    | ``workpaper:{cycle}``     |                                     |                         |                     |
    | ``note``                  | ``execute_note_formulas``           | ``note:{section}!{r}:{c}`` | ``note:{section}`` |
    | 未识别 scope              | 不分派                              | 无                      | 无（零写入）        |

**实际生成器签名与 design §18 骨架的差异（以实际为准，Req 21.1 编排层适配）**：

- 报表范围（spec formula-hub-integrity-closure ADR-FHIC-07 / 08）：计划段只登记预设页面、不经 coordinator、不产
  mutation；执行段在取锁后走 ``refresh_report_scope.execute_report_scope``（试算表重算 + 按项目真实准则、审定模式
  调 ``ReportEngine.generate_all_reports``），金额变化数 / 仅重算数 / 失败行由逐行分类得出。
- ``AdjudicationWritebackService.writeback_batch(project_id, year, formulas, *, ctx, company_code)``
  —— **需要一份 ``FormulaRecord`` 列表**（design 骨架假设的 ``writeback_batch(..., scope=scope)``
  参数不存在）。且其 ``FormulaRecord.target_cell`` 语义为 **standard_account_code**（审定科目），
  而底稿单元格公式（``wp_formula.target_cell``）是**单元坐标**（如 ``B5``）——二者语义不匹配，
  编排层没有干净的"项目级审定表 FormulaRecord 源"可喂给 ``writeback_batch``。故本层对
  ``adjudication`` / ``workpaper:{cycle}`` **不直接驱动 ``writeback_batch``**（避免用坐标充当
  科目码的假回写），而是**从 ``wp_index`` 派生 ``page_keys``**（``workpaper:{wp_code}``），
  由治理层 ``refresh_with_presets`` 经**预设库**为这些页面生成初稿单元（真实的"底稿生成"路径）。
  该接口不匹配已**记 warning**，不静默假装成功（见 :meth:`_dispatch_workpaper`）。
- ``execute_note_formulas(db, project_id, year, note_section, *)`` —— 每次只处理一个
  ``note_section``；本层先查 ``disclosure_notes`` 现存 section 再逐一执行（design 骨架的
  ``note_section=...`` 是示意）。

**工程铁律**：service 只 ``flush``，router 层 ``commit``（本编排层不 ``commit``）。
四表库取数经既有引擎的 ``get_active_filter`` 统一入口（本层不裸查四表库）。

**三段式**（spec formula-hub-integrity-closure ADR-FHIC-07）：``generate`` = ①计划（只读、不取锁，
每个 scope 一份 :class:`ScopePlan`）→ ②冻结判定（``formula_runtime.freeze``：计划含 Runtime mutation
⇒ 409）→ ③执行（:meth:`DraftRefreshOrchestrator._acquire_project_lock` 之后先做幂等判定 —— ``refresh_idempotency``
的纯函数 + ``refresh_idempotency_store`` 取数：同一有效键的首次运行仍在执行 ⇒ 409，已有结论 ⇒ 命中、返回首次运行的
结果、不写入不发事件；判定为执行才交治理层写入，再执行报表范围，按需求 3.2 汇总写回结果对象与本次审计，ADR-FHIC-08）。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import DraftRefreshAudit, WpIndex
from app.services.draft_refresh_service import (
    DraftRefreshService,
    PresetApplication,
    RefreshResult,
    RefreshUnit,
)
from app.services.formula_management.refresh_idempotency import (
    DETAIL_BASE_KEY,
    DETAIL_FP_KEY,
    decide,
    effective_key,
    hit_preset_application,
    hit_result,
    plan_fp,
    runtime_revisions,
    write_key,
)
from app.services.formula_management.refresh_idempotency_store import (
    count_occupied,
    find_prior,
    report_basis,
)
from app.services.formula_management.refresh_outcome import (
    OutcomeTotals,
    ScopeOutcome,
    derive_outcome,
    split_unchanged,
    summarize,
)
from app.services.formula_management.refresh_report_scope import (
    REPORT_SCOPE,
    ROLLBACK_UNAVAILABLE_WARNING,
    execute_report_scope,
)
from app.services.formula_management.refresh_scope_discovery import (
    RefreshScopeDiscovery,
)
from app.services.formula_runtime.contracts import ExecutionResult


logger = logging.getLogger(__name__)

# wp_code 循环前缀提取（与 RefreshScopeDiscovery §③ 同口径：re.match(r'([A-N])', wp_code)）。
_CYCLE_PREFIX_RE = re.compile(r"([A-N])")

ScopeKind = Literal["runtime", "report", "marker"]


@dataclass(frozen=True)
class ScopePlan:
    """单个刷新范围的只读计划（ADR-FHIC-07 第①段：在锁外产出，不写库）。

    ``mutations`` 只装 ``FormulaRuntimeCoordinator`` 产出的 ``FormulaMutation``（冻结判定只看它；``kind="report"`` 恒为
    空）；``units`` / ``page_keys`` 是交治理层打 Draft 标记 / 套预设的输入。
    """

    scope: str
    kind: ScopeKind
    mutations: tuple[Any, ...] = ()
    units: tuple[RefreshUnit, ...] = ()
    page_keys: tuple[str, ...] = ()


def _scope_kind(scope: str) -> ScopeKind:
    """范围类别：``report`` = 报表；``runtime`` = 由 coordinator 产计划的附注 / 审定 / 底稿；其余 ``marker``。"""
    if scope == "report":
        return "report"
    if scope in ("note", "adjudication") or scope.startswith("workpaper"):
        return "runtime"
    return "marker"


@dataclass(frozen=True)
class GovernedInputs:
    """治理层那一段的输入（ADR-FHIC-08）：取项目锁后、幂等判定前由 :meth:`DraftRefreshOrchestrator._governed_inputs`
    合并各范围计划算一次，计划指纹与执行段共用同一份（执行段不再重算）。"""

    units: tuple[RefreshUnit, ...]
    page_keys: tuple[str, ...]
    runtime_mutations: tuple[Any, ...]
    application: PresetApplication
    formula_revision: str
    preset_revision: str


class DraftRefreshOrchestrator:
    """全局刷新生成编排层（Req 21）。

    按勾选 ``scopes`` 分派各上游生成器产出 ``RefreshUnit`` + ``page_keys``，经
    ``DraftRefreshService.refresh_with_presets`` 统一治理（幂等 / Draft / 覆盖 / 快照 /
    审计）。service 只 ``flush``，router ``commit``。
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.svc = DraftRefreshService()
        #: 本次 generate 期间由 coordinator 报出的、需要透到用户的告警。
        #:
        #: spec: formula-management-runtime-closure Task 11（Requirements 6.4）——
        #: 🔴 改造前 `plan.scope_failures` **只进 logger.warning**，而 `wp_formula`
        #: 全库 0 行 ⇒ 合伙人点「全局一键刷新」看到的是「刷新成功、已应用 0 个单元」，
        #: 与「公式都算过了、确实没有需要改的」**不可区分**。
        #: `no_formulas` 这一态必须透到响应体 `warnings`（前端 GtRefreshScopeDialog
        #: 已有 warnings 渲染区，故零前端改动即可见）。
        self._coordinator_warnings: list[str] = []
        # 完整 FormulaMutation 仅在本次 generate 生命周期内保存；禁止降格成 RefreshUnit
        # 后丢失 locator/before/version/source_formula_id。
        self._runtime_mutations: list[Any] = []

    async def generate(
        self,
        *,
        project_id: UUID,
        year: int,
        operator: Any,
        scopes: Sequence[str],
        confirm_overwrite: bool = False,
        transaction_mode: str = "all_or_nothing",
        idempotency_key: str | None = None,
    ) -> tuple[Any, PresetApplication | dict[str, Any]]:
        """按勾选 ``scopes`` 分派生成器产初稿，交治理层统一编排（Req 21）。

        三段式（ADR-FHIC-07）：

        1. **① 计划**（:meth:`_plan`，只读、不取锁）：校验 scopes ⊆ ``RefreshScopeDiscovery.discover``
           （未知键忽略并 warning，保序去重），逐个被勾选 scope 经 :meth:`_dispatch` 产
           :class:`ScopePlan`；未被勾选的域完全不触碰（Req 21.3）。
        2. **② 冻结判定**（已解冻，任务 26 删除了 ``freeze.py`` 与本判定段）。
        3. **③ 执行**（ADR-FHIC-08）：:meth:`_acquire_project_lock` 之后先做**幂等判定** —— :meth:`_governed_inputs`
           合并计划（runtime mutation 去重、预设页面、预设套用与两个 revision，算一次、执行段共用），算 ``plan_fp``（四表
           快照指纹等，勾选报表范围时加报表四项），有效键 = 请求键或 ``plan_fp``，查本项目年度属于该键的最近一条审计：
           ``executing`` ⇒ ``RefreshInProgress``（路由 409）；首次运行已有结论 ⇒ **命中**，直接返回 ``hit_result`` 与首次运行
           存的预设套用，不调 :meth:`_execute`（不写入、不发事件），也不跑下面的④⑤；否则 :meth:`_execute` —— runtime /
           marker 路径交治理层（套预设 + Draft 标记 / 覆盖排除 / 快照 / 审计；``idempotency_checked=True``、写入键 =
           ``write_key(有效键, 已占用条数)``），报表范围（勾选了才执行）走 ``refresh_report_scope``，再按需求 3.2 / 3.3
           把各范围汇总写回结果对象（``outcome`` / 派生 ``status`` / 三个计数 / ``affected_count = applied + recomputed`` /
           失败 / 提交后事件）与本次审计（``affected_count`` 列 + ``detail`` 五键 + 有效键与 ``plan_fp``）。
        4. **④ 留痕**：本次执行写了审计就把实际执行的 ``selected`` 写入 ``draft_refresh_audit.detail.scopes``
           （Req 21.6）；不再看 ``status``：``failed`` 由路由整体回滚，留痕随之消失。

        计划在锁外产出，并发写由 mutation 自带的 ``expected_version`` CAS 兜住（既有机制）。

        Args:
            project_id: 目标项目。
            year: 目标年度。
            operator: 触发刷新的合伙人（``User``，取 ``id`` / ``role``）。
            scopes: 合伙人在勾选弹窗（Req 19.6）提交的 Refresh_Scope_Item 键。
            confirm_overwrite: 是否确认覆盖团队人工编辑单元（Req 4.4）。

        Returns:
            ``(结果对象, 预设套用)``：执行时 = 治理层结果（``ExecutionResult`` / ``RefreshResult``）经汇总写回后的对象 +
            ``PresetApplication``；命中时 = ``hit_result``（``status=idempotent_hit``）+ 首次运行存的预设套用 dict（没存则为
            本次 ``build_preset_draft_units(page_keys).to_dict()``）。``post_commit_events`` 由路由在提交成功后投递，
            ``outcome == "failed"`` 时路由整体回滚。

        Raises:
            RefreshInProgress: 同一有效键的首次运行仍在执行（审计 ``result_status == "executing"``，ADR-FHIC-08）。
            SavepointLost: 报表范围执行中事务被调用链内部回滚（``refresh_report_scope``），结果无法如实报告。
        """
        # ── ① 计划：只读、不取锁 ──────────────────────────────────────────────
        plans = await self._plan(project_id=project_id, year=year, scopes=scopes)
        selected = [plan.scope for plan in plans]

        # ── ②（已解冻，任务 26）────────────────────────────────────────────────

        # ── ③ 执行：取项目锁后先做幂等判定，再交治理层、执行报表范围、汇总写回（ADR-FHIC-08）────────
        await self._acquire_project_lock(project_id)
        inputs = self._governed_inputs(plans)
        fingerprint = await self._plan_fingerprint(
            selected, inputs, project_id=project_id, year=year,
            confirm_overwrite=confirm_overwrite, transaction_mode=transaction_mode,
        )
        effective = effective_key(idempotency_key, fingerprint)
        prior = await find_prior(self.db, project_id, year, effective)
        if decide(prior) == "hit":  # executing ⇒ decide 抛 RefreshInProgress，原样上抛（路由 409）
            # 命中：不写入、不发事件，也不跑④⑤；预设套用回放首次运行存的，没存则用本次的纯映射
            stored = hit_preset_application(prior)
            return hit_result(prior), stored if stored is not None else inputs.application.to_dict()
        occupied = await count_occupied(self.db, project_id, year, effective)
        result, application, audit_id = await self._execute(
            plans,
            inputs,
            project_id=project_id,
            year=year,
            operator=operator,
            confirm_overwrite=confirm_overwrite,
            transaction_mode=transaction_mode,
            idempotency_key=write_key(effective, occupied),
            idempotency_detail={DETAIL_BASE_KEY: effective, DETAIL_FP_KEY: fingerprint},
        )

        # ── ④ 审计留痕记录本次实际执行的勾选范围（Req 21.6，复用 Req 4 留痕）──────
        # 本次执行写了审计就记（不再看 status：failed 由路由整体回滚，留痕随之消失；阻断时没有审计）。
        if audit_id is not None:
            await self._record_scopes_to_audit(audit_id, selected)

        # ── ⑤ 把 coordinator 的「无公式定义」等告警透到响应体（Task 11 / R6.4）──
        # fail-open：`result` 可能没有 `warnings` 属性（不同实现），此时只落日志。
        if self._coordinator_warnings:
            existing = getattr(result, "warnings", None)
            if isinstance(existing, list):
                for w in self._coordinator_warnings:
                    if w not in existing:
                        existing.append(w)
            else:
                logger.warning(
                    "RefreshResult 无 warnings 通道，coordinator 告警仅落日志：%s",
                    self._coordinator_warnings,
                )

        return result, application

    # ═══════════════════════════════════════════════════════════════════════
    # 三段式：计划 → 冻结判定 → 项目锁 → 执行（ADR-FHIC-07）
    # ═══════════════════════════════════════════════════════════════════════
    async def _plan(
        self, *, project_id: UUID, year: int, scopes: Sequence[str]
    ) -> list[ScopePlan]:
        """计划段（只读、不取锁）：每个被勾选的合法 scope 产一份 :class:`ScopePlan`。"""
        # ── 校验 scopes ⊆ 动态发现集合（Req 20 共用口径；未知键忽略并 warning）──
        discovered = await RefreshScopeDiscovery(self.db).discover(
            project_id=project_id, year=year
        )
        valid = {item.key for item in discovered}

        selected: list[str] = []
        for scope in scopes:
            if scope in valid:
                selected.append(scope)
            else:
                logger.warning(
                    "全局刷新忽略未知刷新范围键 %r（不在 RefreshScopeDiscovery "
                    "发现集合内，Req 20 共用发现口径）",
                    scope,
                )
        selected = list(dict.fromkeys(selected))  # 保序去重

        # ── 按被勾选 scope 分派生成器（只读产计划）；_dispatch 把 coordinator 的完整
        #    mutation 追加进 _runtime_mutations，本 scope 新增的那一段即其 Runtime 计划 ──
        self._coordinator_warnings = []
        self._runtime_mutations = []
        plans: list[ScopePlan] = []
        for scope in selected:
            start = len(self._runtime_mutations)
            units, page_keys = await self._dispatch(
                scope, project_id=project_id, year=year
            )
            plans.append(
                ScopePlan(
                    scope=scope,
                    kind=_scope_kind(scope),
                    mutations=tuple(self._runtime_mutations[start:]),
                    units=tuple(units),
                    page_keys=tuple(page_keys),
                )
            )
        return plans

    async def _acquire_project_lock(self, project_id: UUID) -> None:
        """项目级事务咨询锁，防并发刷新互相覆盖；只在冻结判定通过之后调用（ADR-FHIC-07 第③段）。

        单独成方法供测试观测：被冻结的请求必须 0 次调用。SQLite 测试方言没有
        ``pg_advisory_xact_lock``，跳过（单进程测试隔离即可）。
        """
        lock_key = int.from_bytes(project_id.bytes[:8], "big") & 0x7FFFFFFFFFFFFFFF
        bind = self.db.get_bind()
        if bind is None or bind.dialect.name != "sqlite":
            await self.db.execute(sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})

    def _governed_inputs(self, plans: Sequence[ScopePlan]) -> GovernedInputs:
        """合并各范围计划（已持项目锁、只读）：Draft 单元、预设页面（保序去重）、runtime mutation（按目标 + 来源去重）、
        预设套用（``build_preset_draft_units``，纯映射）与两个 revision（``refresh_idempotency.runtime_revisions``）。"""
        page_keys = tuple(dict.fromkeys(key for plan in plans for key in plan.page_keys))
        # 同一公式可能被多个 workpaper scope 发现；按目标+来源去重，禁止重复 apply 自冲突。
        deduped: dict[tuple[str, str, str], Any] = {}
        for mutation in (m for plan in plans for m in plan.mutations):
            key = (
                mutation.target.domain,
                mutation.target.addr_id,
                str(mutation.source_formula_id or ""),
            )
            deduped[key] = mutation
        application = self.svc.build_preset_draft_units(page_keys)
        formula_revision, preset_revision = runtime_revisions(deduped.values(), application.units)
        return GovernedInputs(
            units=tuple(unit for plan in plans for unit in plan.units),
            page_keys=page_keys,
            runtime_mutations=tuple(deduped.values()),
            application=application,
            formula_revision=formula_revision,
            preset_revision=preset_revision,
        )

    async def _plan_fingerprint(
        self,
        selected: Sequence[str],
        inputs: GovernedInputs,
        *,
        project_id: UUID,
        year: int,
        confirm_overwrite: bool,
        transaction_mode: str,
    ) -> str:
        """计划指纹 ``plan_fp``（已持项目锁、只读）：四表快照指纹（``DraftRefreshService._compute_tb_snapshot_hash``）+
        ``inputs`` 的两个 revision，勾选报表范围时再取报表四项（``refresh_idempotency_store.report_basis``）。"""
        tb_snapshot_hash = await self.svc._compute_tb_snapshot_hash(self.db, project_id, year)
        report = await report_basis(self.db, project_id, year) if REPORT_SCOPE in selected else None
        return plan_fp(
            scopes=selected,
            transaction_mode=transaction_mode,
            confirm_overwrite=confirm_overwrite,
            tb_snapshot_hash=tb_snapshot_hash,
            formula_revision=inputs.formula_revision,
            preset_revision=inputs.preset_revision,
            report=report,
        )

    async def _execute(
        self,
        plans: Sequence[ScopePlan],
        inputs: GovernedInputs,
        *,
        project_id: UUID,
        year: int,
        operator: Any,
        confirm_overwrite: bool,
        transaction_mode: str,
        idempotency_key: str,
        idempotency_detail: dict[str, str],
    ) -> tuple[Any, PresetApplication, UUID | None]:
        """执行段（已持项目锁、幂等判定为执行，ADR-FHIC-08）：runtime / marker 路径 → 报表范围（勾选了才执行）→ 汇总写回。

        ``idempotency_key`` = 写进审计 ``idempotency_key`` 列的写入键，``idempotency_detail`` = 增写进本次审计 ``detail`` 的
        有效键与计划指纹。返回 ``(结果对象, 预设套用明细, 本次执行写下的审计 id)``。治理层前置校验阻断（``blocked``，
        四表库在路由预检之后变得不完整）时什么都没写：不执行报表范围、不汇总，审计 id 为 ``None``。
        """
        result, application = await self._execute_governed(
            plans,
            inputs,
            project_id=project_id,
            year=year,
            operator=operator,
            confirm_overwrite=confirm_overwrite,
            idempotency_key=idempotency_key,
            transaction_mode=transaction_mode,
        )
        if result.status == "blocked":
            return result, application, None
        outcomes = [self._governed_outcome(result)]
        report_ran = any(plan.kind == "report" for plan in plans)
        if report_ran:
            outcomes.append(await execute_report_scope(self.db, project_id=project_id, year=year))
        audit_id = getattr(result, "refresh_id", None) or getattr(result, "run_id", None)
        await self._write_back(
            result, outcomes, transaction_mode=transaction_mode, report_ran=report_ran, audit_id=audit_id,
            idempotency_detail=idempotency_detail,
        )
        return result, application, audit_id

    @staticmethod
    def _governed_outcome(result: Any) -> ScopeOutcome:
        """治理层那一段的计数：runtime 路径 = ``execute_refresh``（``ExecutionResult``），marker 路径 = ``refresh()``。"""
        return ScopeOutcome(
            "runtime" if isinstance(result, ExecutionResult) else "marker",
            value_changes=result.applied_count,
            recomputed=result.recomputed_count,
            draft_marked=result.draft_marked_count,
            failures=list(result.failures),
        )

    async def _write_back(
        self,
        result: Any,
        outcomes: Sequence[ScopeOutcome],
        *,
        transaction_mode: str,
        report_ran: bool,
        audit_id: UUID | None,
        idempotency_detail: dict[str, str],
    ) -> None:
        """按需求 3.2 / 3.3 汇总各范围，写回结果对象与本次审计（``affected_count`` 列 + ``detail`` 五键，供幂等回放；
        ``detail`` 另增写 ``idempotency_detail`` = 有效键 ``idempotency_base`` 与计划指纹 ``plan_fp``，供幂等查找）。

        ``status`` 换成状态表派生值（``RefreshResult`` 原 ``success`` 被替换，``ExecutionResult`` 含报表范围时重派生）；
        ``failures`` 并入报表范围的失败；报表范围执行过 ⇒ ``rollback_available=False`` + 中文说明（ADR-FHIC-08）。
        ``draft_refresh_audit.result_status`` 保持治理层写法不变，整体结果记在 ``detail.outcome``。

        派生 ``outcome == "failed"`` ⇒ 路由整体回滚，本次各范围的写入（报表行、Draft 标记、试算表重算等）都不存在：结果对象与
        审计 ``detail`` 的 applied / recomputed / draft_marked / affected 都记 0（需求 3「只报真实结果」，与服务层 all_or_nothing
        失败「三个计数都记 0」同口径；审计随路由回滚一并撤销，写入值仍与响应一致），``failures`` 照旧并入。
        """
        outcome, status = derive_outcome(outcomes, transaction_mode)
        totals = summarize(outcomes)
        if outcome == "failed":  # 路由整体回滚 ⇒ 本次写入都不存在，四个计数如实记 0（failures 照旧并入）
            totals = OutcomeTotals(failures=totals.failures)
        affected = totals.value_changes + totals.recomputed
        result.outcome, result.status = outcome, status
        result.applied_count = totals.value_changes
        result.recomputed_count = totals.recomputed
        result.draft_marked_count = totals.draft_marked
        added = [failure for item in outcomes[1:] for failure in item.failures]
        result.failures = [*result.failures, *added]
        if isinstance(result, RefreshResult):  # ExecutionResult 的 affected_count 由 to_dict 按 applied + recomputed 算
            result.affected_count = affected
        if isinstance(result, ExecutionResult):  # RefreshResult 的 failed_count 由 to_dict 按 len(failures) 算
            result.failed_count += len(added)
        result.post_commit_events = [event for item in outcomes for event in item.post_commit_events]
        if report_ran:
            result.rollback_available = False
            if ROLLBACK_UNAVAILABLE_WARNING not in result.warnings:
                result.warnings.append(ROLLBACK_UNAVAILABLE_WARNING)
        if audit_id is None:
            return
        audit = (
            await self.db.execute(sa.select(DraftRefreshAudit).where(DraftRefreshAudit.id == audit_id))
        ).scalar_one_or_none()
        if audit is None:
            return
        audit.affected_count = affected
        audit.detail = {
            **(audit.detail or {}),
            "outcome": outcome,
            "affected_count": affected,
            "applied_count": totals.value_changes,
            "recomputed_count": totals.recomputed,
            "draft_marked_count": totals.draft_marked,
            **idempotency_detail,
        }
        await self.db.flush()

    async def _execute_governed(
        self,
        plans: Sequence[ScopePlan],
        inputs: GovernedInputs,
        *,
        project_id: UUID,
        year: int,
        operator: Any,
        confirm_overwrite: bool,
        transaction_mode: str,
        idempotency_key: str,
    ) -> tuple[Any, PresetApplication]:
        """治理层那一段：把 :meth:`_governed_inputs` 合并好的输入交 ``execute_refresh`` / ``refresh_with_presets``
        （Req 21.2 / 21.4 / 21.5）。

        两条路径都传 ``idempotency_checked=True``（幂等判定归编排器，ADR-FHIC-08）、``idempotency_key`` = 编排器给的写入键；
        runtime 路径的两个 revision 取 ``inputs``（与计划指纹同一份）。marker 路径的预设套用仍由 ``refresh_with_presets``
        按同一份 ``page_keys`` 生成（服务层不变；``build_preset_draft_units`` 是纯映射）。
        """
        selected = [plan.scope for plan in plans]
        runtime_mutations, application = inputs.runtime_mutations, inputs.application

        if runtime_mutations:
            from app.services.formula_runtime.coordinator import FormulaRuntimeCoordinator

            coordinator = FormulaRuntimeCoordinator(self.db)
            adapters = coordinator.build_adapter_map(
                {mutation.target.domain for mutation in runtime_mutations}
            )
            if application.units:
                self._coordinator_warnings.append(
                    f"{len(application.units)} 条预设已登记为待编制草稿；无规范业务 binding 的预设不计入已应用数"
                )
            # 需求 3.2：before / after 规范化后相等的 mutation 不下发写入方，计入仅重算
            to_write, unchanged = split_unchanged(runtime_mutations)
            result = await self.svc.execute_refresh(
                self.db,
                project_id=project_id,
                year=year,
                scopes=selected,
                mutations=to_write,
                adapters=adapters,
                draft_units=application.units,
                confirm_overwrite=confirm_overwrite,
                transaction_mode=transaction_mode,
                idempotency_key=idempotency_key,
                operator=operator,
                formula_definition_revision=inputs.formula_revision,
                preset_revision=inputs.preset_revision,
                idempotency_checked=True,
                recomputed_count=len(unchanged),
            )
            audit = (
                await self.db.execute(
                    sa.select(DraftRefreshAudit).where(DraftRefreshAudit.id == result.run_id)
                )
            ).scalar_one_or_none()
            if audit is not None:
                audit.detail = {
                    **(audit.detail or {}),
                    "scopes": selected,
                    "preset_application": application.to_dict(),
                    "warnings": list(self._coordinator_warnings),
                }
                await self.db.flush()
        else:
            # 无 runtime mutation（含仅报表范围）时走 marker-only 治理路径：零单元照样写一条审计，告警明确透出。
            result, application = await self.svc.refresh_with_presets(
                self.db,
                project_id=project_id,
                year=year,
                operator=operator,
                scope=selected,
                page_keys=inputs.page_keys,
                extra_units=inputs.units,
                confirm_overwrite=confirm_overwrite,
                idempotency_checked=True,
                idempotency_key=idempotency_key,
            )
        return result, application

    # ═══════════════════════════════════════════════════════════════════════
    # scope → 生成器分派
    # ═══════════════════════════════════════════════════════════════════════
    async def _dispatch(
        self, scope: str, *, project_id: UUID, year: int
    ) -> tuple[list[RefreshUnit], list[str]]:
        """把单个 scope 分派到对应生成器（Req 21.1）。

        - ``report``（spec formula-hub-integrity-closure ADR-FHIC-07 第①段）：只登记，不经 coordinator、不产 mutation /
          RefreshUnit；返回 ``([], 预设库 report: 键)``，执行段走报表权威生成路径（ADR-FHIC-08）。
        - ``workpaper`` / ``adjudication`` / ``note``（Task 13）：经 FormulaRuntimeCoordinator 产出真实 mutation plan。
        - 未识别 scope 返回空 ``([], [])``。
        """
        if scope == "report":
            return [], self._report_page_keys()
        if scope in ("note", "adjudication") or scope.startswith("workpaper"):
            return await self._dispatch_via_coordinator(
                scope, project_id=project_id, year=year
            )
        # 未识别 scope → 空（不写；此分支为二次防御，generate 已按发现集合过滤）
        logger.warning("DraftRefreshOrchestrator 未识别刷新范围 %r，跳过（不生成）", scope)
        return [], []

    async def _dispatch_via_coordinator(
        self, scope: str, *, project_id: UUID, year: int
    ) -> tuple[list[RefreshUnit], list[str]]:
        """Route scope through FormulaRuntimeCoordinator for real domain mutations.

        Task 13 (Req 1,3,7,8 | P2,P3,P8,P9): replaces the placeholder
        page_keys-only path for workpaper/adjudication and keeps the
        note scope also going through the real mutation pipeline. The report
        scope no longer comes here (ADR-FHIC-07: registered only, see :meth:`_dispatch`).

        Returns (units derived from mutations, page_keys for preset library).
        Does NOT commit — consistent with service-only-flush contract.
        """
        from app.services.formula_runtime.coordinator import (
            NO_FORMULAS_KIND,
            FormulaRuntimeCoordinator,
            MutationPlanResult,
        )

        coordinator = FormulaRuntimeCoordinator(self.db)
        plan: MutationPlanResult = await coordinator.generate_mutation_plan(
            project_id=project_id,
            year=year,
            scopes=[scope],
        )

        # 保留完整 mutation，交 generate 统一去重并由 execute_refresh 真正 apply。
        # 禁止转成 RefreshUnit 丢失 locator/before/version/source_formula_id。
        # getattr 自愈：__init__ 已建 _runtime_mutations；但诊断/测试可能用 __new__ 绕过
        # __init__ 直接调 _dispatch —— 此处兜底建空列表，避免 AttributeError 而非静默。
        if not hasattr(self, "_runtime_mutations"):
            self._runtime_mutations = []
        self._runtime_mutations.extend(plan.mutations)
        # 兼容直接调用 _dispatch 的既有诊断/测试：仍返回只读 RefreshUnit 投影；
        # generate 的 runtime 分支不消费这些投影写值，而是使用上面的完整 mutation。
        units: list[RefreshUnit] = [
            RefreshUnit(
                unit_scope=f"{mutation.target.domain}:{mutation.target.addr_id}",
                before_value=mutation.before_value,
                after_value=mutation.after_value,
            )
            for mutation in plan.mutations
        ]

        # Build page_keys based on scope type
        page_keys: list[str] = []
        if scope == "note":
            # Derive page_keys from mutation targets
            note_sections: set[str] = set()
            for m in plan.mutations:
                section = m.target.locator.get("section", "")
                if section:
                    note_sections.add(f"note:{section}")
            page_keys.extend(sorted(note_sections))
        elif scope == "adjudication" or scope.startswith("workpaper"):
            # Derive page_keys from wp_index for preset library
            cycle = self._scope_cycle(scope)
            wp_codes = await self._wp_codes(
                project_id=project_id,
                cycle=cycle,
                adjudication_only=(scope == "adjudication"),
            )
            page_keys.extend(f"workpaper:{code}" for code in wp_codes)

        # Log scope failures / issues for observability
        if plan.scope_failures:
            logger.warning(
                "FormulaRuntimeCoordinator scope_failures for scope=%r: %d items",
                scope, len(plan.scope_failures),
            )
            # Task 11（R6.4）：`no_formulas` 这一态必须**透到用户**，不能只落日志
            # —— 否则「本项目尚未定义任何公式」会显示成「刷新成功、0 处变更」。
            for failure in plan.scope_failures:
                if failure.get("kind") != NO_FORMULAS_KIND:
                    continue
                detail = failure.get("detail") or "本项目尚未定义任何公式"
                msg = f"范围 {scope}：{detail}"
                if msg not in self._coordinator_warnings:
                    self._coordinator_warnings.append(msg)
        if plan.issues:
            logger.info(
                "FormulaRuntimeCoordinator issues for scope=%r: %d items",
                scope, len(plan.issues),
            )

        return units, page_keys

    # ═══════════════════════════════════════════════════════════════════════
    # 内部只读辅助
    # ═══════════════════════════════════════════════════════════════════════
    @staticmethod
    def _report_page_keys() -> list[str]:
        """报表范围的预设页面 = 预设库里全部 ``report:`` 键（需求 3.3：``preset_application`` 与改造前一致）。

        spec chain-closure-phase1 R2：原实现写死 ``page_keys.append("report:*")``，而预设库的 report 域键是**具体**的
        （report:balance_sheet / income_statement / cash_flow_statement / equity_statement / cash_flow_supplement /
        impairment_provision / cross_check），``"report:*" in preset_index`` 实测恒 False ⇒ 该 scope preset_count 恒 0，
        锁死 343 条报表域预设公式。改为从预设库实际键派生（不写死报表类型清单：预设库增删类型时自动跟随，也避免按
        FinancialReportType 枚举派生而漏掉 cross_check / impairment_provision）。
        """
        try:
            from app.services.formula_management.preset_library import build_preset_index

            return sorted(k for k in build_preset_index() if k.startswith("report:"))
        except Exception as exc:  # noqa: BLE001 — 预设库不可用不阻断刷新
            logger.warning("report scope 预设键派生失败，本次不套报表预设: %s: %s", type(exc).__name__, exc)
            return []

    @staticmethod
    def _scope_cycle(scope: str) -> str | None:
        """从 ``workpaper:{cycle}`` 提取循环字母；``adjudication`` 等无循环返回 ``None``。"""
        if scope.startswith("workpaper:"):
            suffix = scope.split(":", 1)[1].strip().upper()
            return suffix or None
        return None

    async def _wp_codes(
        self,
        *,
        project_id: UUID,
        cycle: str | None,
        adjudication_only: bool,
    ) -> list[str]:
        """读取项目现存 ``wp_index`` wp_code（只读），按循环 / 审定表过滤。

        - ``cycle`` 非空 → 仅返回循环前缀（``re.match(r'([A-N])')``）匹配的 wp_code。
        - ``adjudication_only`` → 仅返回审定表页面（``wp_code`` 以 ``-1`` 结尾）。

        ``wp_index`` 是项目级（无 year / dataset 语义），沿用既有 ``is_deleted=false`` 过滤。
        """
        rows = await self.db.execute(
            sa.select(WpIndex.wp_code)
            .where(
                WpIndex.project_id == project_id,
                WpIndex.is_deleted == sa.false(),
            )
            .distinct()
        )
        codes: list[str] = []
        for (wp_code,) in rows.all():
            if not wp_code:
                continue
            code = str(wp_code)
            if adjudication_only and not code.endswith("-1"):
                continue
            if cycle is not None:
                m = _CYCLE_PREFIX_RE.match(code.upper())
                if not m or m.group(1) != cycle:
                    continue
            codes.append(code)
        return sorted(set(codes))

    async def _record_scopes_to_audit(
        self, refresh_id: UUID, scopes: list[str]
    ) -> None:
        """把本次实际执行的勾选范围写入 ``draft_refresh_audit.detail.scopes``（Req 21.6）。

        JSONB 需重新赋新对象触发 ORM 脏标记（就地改 dict 不一定被追踪）。仅 flush 不 commit。
        """
        audit = (
            await self.db.execute(
                sa.select(DraftRefreshAudit).where(DraftRefreshAudit.id == refresh_id)
            )
        ).scalar_one_or_none()
        if audit is None:
            return
        audit.detail = {**(audit.detail or {}), "scopes": list(scopes)}
        await self.db.flush()
