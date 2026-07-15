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
    | ``report``                | ``ReportEngine.generate_unadjusted_report`` | ``report:{row_code}``   | ``report:*``        |
    | ``adjudication`` /        | 审定表回写 + 底稿生成               | ``audit_sheet:{...}``   | ``workpaper:{wp_code}`` |
    | ``workpaper:{cycle}``     |                                     |                         |                     |
    | ``note``                  | ``execute_note_formulas``           | ``note:{section}!{r}:{c}`` | ``note:{section}`` |
    | 未识别 scope              | 不分派                              | 无                      | 无（零写入）        |

**实际生成器签名与 design §18 骨架的差异（以实际为准，Req 21.1 编排层适配）**：

- ``ReportEngine.generate_unadjusted_report(project_id, year, report_type)`` —— 位置参数，
  且每次只产一种报表；本层对四张主表逐一调用并归集行（design 骨架的 ``report_type=...``
  是示意）。
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
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from typing import Any
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
from app.services.formula_management.refresh_scope_discovery import (
    RefreshScopeDiscovery,
)

logger = logging.getLogger(__name__)

# wp_code 循环前缀提取（与 RefreshScopeDiscovery §③ 同口径：re.match(r'([A-N])', wp_code)）。
_CYCLE_PREFIX_RE = re.compile(r"([A-N])")


class DraftRefreshOrchestrator:
    """全局刷新生成编排层（Req 21）。

    按勾选 ``scopes`` 分派各上游生成器产出 ``RefreshUnit`` + ``page_keys``，经
    ``DraftRefreshService.refresh_with_presets`` 统一治理（幂等 / Draft / 覆盖 / 快照 /
    审计）。service 只 ``flush``，router ``commit``。
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.svc = DraftRefreshService()

    async def generate(
        self,
        *,
        project_id: UUID,
        year: int,
        operator: Any,
        scopes: Sequence[str],
        confirm_overwrite: bool = False,
    ) -> tuple[RefreshResult, PresetApplication]:
        """按勾选 ``scopes`` 分派生成器产初稿，交治理层统一编排（Req 21）。

        步骤：

        1. **① 校验 scopes ⊆ RefreshScopeDiscovery.discover**（Req 20 共用发现口径）：
           未知键**忽略并 warning**（不静默丢弃），保序去重。
        2. **② 按被勾选 scope 分派对应生成器** → 归集 ``RefreshUnit`` + ``page_keys``；
           未被勾选的域完全不触碰（零 units / 零 page_keys → 零写入，Req 21.3）。
        3. **③ 交治理层** ``refresh_with_presets``：按 ``page_key`` 套预设（Req 21.2）+
           合并生成 ``units`` → 幂等 / Draft 标记 / 覆盖排除 / 快照 / 审计；
           ``affected_count = len(refreshed_units)``（Req 21.4，不再恒为 0）；
           生成单元复用治理层 Draft 标记 + ``last_computed_at`` + 覆盖前快照（Req 21.5）。
        4. **④ 审计留痕范围**：把本次实际执行的 ``selected`` 写入
           ``draft_refresh_audit.detail.scopes``（Req 21.6，复用 Req 4 留痕契约）。

        Args:
            project_id: 目标项目。
            year: 目标年度。
            operator: 触发刷新的合伙人（``User``，取 ``id`` / ``role``）。
            scopes: 合伙人在勾选弹窗（Req 19.6）提交的 Refresh_Scope_Item 键。
            confirm_overwrite: 是否确认覆盖团队人工编辑单元（Req 4.4）。

        Returns:
            ``(RefreshResult, PresetApplication)``：治理层刷新结果 + 预设套用明细。
        """
        # ── ① 校验 scopes ⊆ 动态发现集合（Req 20 共用口径；未知键忽略并 warning）──
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

        # ── ② 按被勾选 scope 分派生成器 → 归集 units + page_keys ──────────────
        units: list[RefreshUnit] = []
        page_keys: list[str] = []
        for scope in selected:
            gen_units, gen_pages = await self._dispatch(
                scope, project_id=project_id, year=year
            )
            units.extend(gen_units)
            page_keys.extend(gen_pages)
        page_keys = list(dict.fromkeys(page_keys))  # 去重（多 scope 可能派生同页）

        # ── ③ 交治理层：套预设 + 合并生成 units → 统一编排（幂等/Draft/覆盖/快照/审计）──
        result, application = await self.svc.refresh_with_presets(
            self.db,
            project_id=project_id,
            year=year,
            operator=operator,
            scope=selected,
            page_keys=page_keys,
            extra_units=units,
            confirm_overwrite=confirm_overwrite,
        )

        # ── ④ 审计留痕记录本次实际执行的勾选范围（Req 21.6，复用 Req 4 留痕）──────
        if result.status == "success" and result.refresh_id is not None:
            await self._record_scopes_to_audit(result.refresh_id, selected)

        return result, application

    # ═══════════════════════════════════════════════════════════════════════
    # scope → 生成器分派
    # ═══════════════════════════════════════════════════════════════════════
    async def _dispatch(
        self, scope: str, *, project_id: UUID, year: int
    ) -> tuple[list[RefreshUnit], list[str]]:
        """把单个 scope 分派到对应生成器（Req 21.1）。

        Task 13: report/workpaper/adjudication/note 四个 scope 全部走
        FormulaRuntimeCoordinator 产出真实 mutation plan。
        未识别 scope 返回空 ``([], [])``。
        """
        if scope in ("report", "note", "adjudication") or scope.startswith("workpaper"):
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
        report/note scopes also going through the real mutation pipeline.

        Returns (units derived from mutations, page_keys for preset library).
        Does NOT commit — consistent with service-only-flush contract.
        """
        from app.services.formula_runtime.coordinator import (
            FormulaRuntimeCoordinator,
            MutationPlanResult,
        )

        coordinator = FormulaRuntimeCoordinator(self.db)
        plan: MutationPlanResult = await coordinator.generate_mutation_plan(
            project_id=project_id,
            year=year,
            scopes=[scope],
        )

        # Convert mutations to RefreshUnit for the treatment layer
        units: list[RefreshUnit] = []
        for mutation in plan.mutations:
            unit_scope = f"{mutation.target.domain}:{mutation.target.addr_id}"
            units.append(
                RefreshUnit(
                    unit_scope=unit_scope,
                    after_value=mutation.after_value,
                )
            )

        # Build page_keys based on scope type
        page_keys: list[str] = []
        if scope == "report":
            page_keys.append("report:*")
        elif scope == "note":
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
