"""标准/自定义 procedure → 唯一一致 wp_index 联合解析器（Task 4 / 组件 C4）

Feature: procedure-delegation-visibility-isolation
Requirements:
  - 4.1/4.2：标准与自定义 procedure 均在目标项目内解析唯一 ``wp_index_id``。
  - 4.3：把 project、procedure、``wp_code``、既有 ``wp_index_id``/wp 绑定与全部已提供绑定来源
    作为 **联合解析上下文**。
  - 4.4：``sheet_name`` 只能在 4.3 的联合上下文内解释（本模块不用 sheet_name 推断 wp_index）。
  - 4.5：若 procedure 仅以 ``sheet_name``（页面级来源）产生全局唯一候选，拒绝该候选。
  - 4.6：多来源时每个来源分别产生唯一 ``wp_index_id`` 且要求全部一致。
  - 4.7：可见性只使用唯一一致结果。
  - 4.8/4.9/4.10：任一来源零候选 / 多候选 / 来源间不一致 → fail-closed 拒绝。
  - 4.11：拒绝时上层拒绝委派、可见性扩展、读取与写入（本模块只返回 fail-closed 结果，供 gate 消费）。
  - 4.12：拒绝时不改任何业务数据（本模块 **纯读**，从不写库）。
  - 4.13：拒绝时安全审计 outbox 记录 ``binding_conflict`` 及全部已提供绑定标识符
    （本模块产出 ``audit_reason='binding_conflict'`` 与 ``provided_identifiers`` 供 gate 落 outbox）。
Design: 组件 C4（ProcedureWpResolver）/ Property 4（binding 唯一或不改数据地拒绝）。

**边界（不越界到别的任务）**：
  - 页面级 ``sheet_name``/``sheet_key`` → ``sheet_key`` 的解析归 ``SheetBindingCatalog``（同 Task 4，
    见 ``sheet_binding_catalog.py``），只能在已确定的 project+wp_index+version 内进行，不做全局推断。
  - 安全审计 outbox 的实际持久化归统一门（Task 6）；本模块只提供 ``binding_conflict`` payload。
  - Delegation/可见性写事务归 Task 5/7；本模块纯读、只 flush 语义下不写。

约定：service 只读，绝不 flush/commit 写。asyncpg 用 ``= ANY(:list)`` 而非 IN tuple（此处均等值/小集合）。
所有分支 try/except → fail-closed（``query_error``），绝不 500 / 不泄露内部错误。
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureInstance, ProcedureRowTask
from app.models.workpaper_models import WorkingPaper, WpIndex

logger = logging.getLogger(__name__)


class BindingRejectReason(str, enum.Enum):
    """wp_index 解析拒绝原因（内部诊断；对外统一 fail-closed 404 / binding_conflict）。"""

    no_source = "no_source"              # 没有任何 identity 绑定来源（Req 4.5 前置）
    sheet_only = "sheet_only"            # 仅提供 sheet_name/sheet_key（页面级），无 identity 源（Req 4.5）
    zero_candidate = "zero_candidate"    # 某已提供来源 0 候选（Req 4.8）
    multi_candidate = "multi_candidate"  # 某已提供来源 >1 候选（Req 4.9）
    source_conflict = "source_conflict"  # 来源间解析到不同 wp_index（Req 4.10）
    query_error = "query_error"          # 查询异常 → fail-closed 拒绝


# identity 绑定来源（可独立解析 wp_index 的来源）；sheet_name/sheet_key 是页面级来源，**不在此列**。
_IDENTITY_SOURCES: tuple[str, ...] = (
    "wp_index_id",
    "wp_id",
    "wp_code",
    "procedure_row_task_id",
    "procedure_instance_id",
    "procedure_code",
)


@dataclass(frozen=True)
class ProcedureBindingSources:
    """procedure→wp_index 的全部已提供绑定来源（联合解析上下文，Req 4.3）。

    ``project_id`` 为必需上下文。其余字段按是否为 None 判定"是否已提供"；每个已提供的
    **identity** 来源都必须独立解析出唯一 wp_index 且彼此一致。页面级 ``sheet_key``/``sheet_name``
    不参与 wp_index 推断（Req 4.4/4.5），仅供 ``SheetBindingCatalog`` 在已确定 wp_index 内解析。
    """

    project_id: UUID
    # identity 来源
    procedure_instance_id: UUID | None = None
    procedure_row_task_id: UUID | None = None
    procedure_code: str | None = None
    audit_cycle: str | None = None            # 可选：为 procedure_code 收窄（同 code 跨 cycle）
    wp_index_id: UUID | None = None
    wp_id: UUID | None = None
    wp_code: str | None = None
    # 页面级来源（不推断 wp_index）
    sheet_key: str | None = None
    sheet_name: str | None = None
    version: str | None = None

    def provided_identity_sources(self) -> tuple[str, ...]:
        """返回已提供的 identity 来源名（procedure_code 不含单独的 audit_cycle）。"""
        names: list[str] = []
        for name in _IDENTITY_SOURCES:
            if getattr(self, name, None) is not None:
                names.append(name)
        return tuple(names)

    def has_page_only(self) -> bool:
        """仅提供了页面级来源（sheet_name/sheet_key），无任何 identity 来源。"""
        return (
            not self.provided_identity_sources()
            and (self.sheet_name is not None or self.sheet_key is not None)
        )

    def provided_identifiers(self) -> dict[str, str]:
        """全部已提供绑定标识符（供 binding_conflict 审计，Req 4.13）。

        不含业务正文/敏感元数据，只含定位用标识符（id / code / 名称）。
        """
        out: dict[str, str] = {"project_id": str(self.project_id)}
        for name in (
            "procedure_instance_id",
            "procedure_row_task_id",
            "procedure_code",
            "audit_cycle",
            "wp_index_id",
            "wp_id",
            "wp_code",
            "sheet_key",
            "sheet_name",
            "version",
        ):
            val = getattr(self, name, None)
            if val is not None:
                out[name] = str(val)
        return out


@dataclass(frozen=True)
class WpBindingResolution:
    """联合解析结果（不可变，纯读产出）。

    - ``ok``：True 表示全部已提供 identity 来源唯一且一致，``wp_index_id`` 可用。
    - ``wp_index_id``：ok 时为唯一一致结果；否则 None。
    - ``reason``：ok=False 时的拒绝原因（``BindingRejectReason``）。
    - ``audit_reason``：ok=False 时固定 ``"binding_conflict"``（Req 4.13）；ok 时 None。
    - ``provided_identifiers``：全部已提供绑定标识符（供 gate 落 outbox）。
    - ``per_source``：每个已提供 identity 来源解析到的候选集合（诊断/审计用）。
    """

    ok: bool
    wp_index_id: UUID | None
    reason: BindingRejectReason | None
    audit_reason: str | None
    provided_identifiers: dict[str, str] = field(default_factory=dict)
    per_source: dict[str, tuple[str, ...]] = field(default_factory=dict)


# binding_conflict 覆盖的拒绝原因（对外统一 External_Not_Found；内部审计 reason=binding_conflict）
_CONFLICT_REASONS = frozenset(
    {
        BindingRejectReason.sheet_only,
        BindingRejectReason.zero_candidate,
        BindingRejectReason.multi_candidate,
        BindingRejectReason.source_conflict,
        BindingRejectReason.query_error,
        BindingRejectReason.no_source,
    }
)


class ProcedureWpResolver:
    """把 procedure 的全部已提供绑定来源唯一且一致地解析为 ``wp_index_id``（纯读 / fail-closed）。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def resolve(self, sources: ProcedureBindingSources) -> WpBindingResolution:
        """联合解析唯一一致 ``wp_index_id``（Req 4.1–4.14）。"""
        identity_sources = sources.provided_identity_sources()

        # Req 4.5：仅页面级来源（sheet_name/sheet_key）不得推断 wp_index（禁止全局唯一推断）。
        if not identity_sources:
            reason = (
                BindingRejectReason.sheet_only
                if sources.has_page_only()
                else BindingRejectReason.no_source
            )
            return self._reject(sources, reason)

        per_source: dict[str, frozenset[UUID]] = {}
        try:
            for name in identity_sources:
                per_source[name] = await self._candidates_for(sources, name)
        except Exception as exc:  # noqa: BLE001 — fail-closed，不 500 泄露
            logger.warning(
                "procedure→wp_index 解析查询异常 project=%s: %s",
                sources.project_id,
                exc,
            )
            return self._reject(sources, BindingRejectReason.query_error, per_source)

        # Req 4.8/4.9：每个已提供来源必须恰好 1 候选。
        for name in identity_sources:
            candidates = per_source[name]
            if len(candidates) == 0:
                return self._reject(
                    sources, BindingRejectReason.zero_candidate, per_source
                )
            if len(candidates) > 1:
                return self._reject(
                    sources, BindingRejectReason.multi_candidate, per_source
                )

        # Req 4.6/4.10：所有来源的唯一候选必须一致。
        unique_ids = {next(iter(per_source[name])) for name in identity_sources}
        if len(unique_ids) != 1:
            return self._reject(
                sources, BindingRejectReason.source_conflict, per_source
            )

        wp_index_id = next(iter(unique_ids))
        return WpBindingResolution(
            ok=True,
            wp_index_id=wp_index_id,
            reason=None,
            audit_reason=None,
            provided_identifiers=sources.provided_identifiers(),
            per_source={k: tuple(str(v) for v in ids) for k, ids in per_source.items()},
        )

    # ------------------------------------------------------------------
    # 每来源候选解析（各返回该来源在目标项目内的候选 wp_index 集合）
    # ------------------------------------------------------------------
    async def _candidates_for(
        self, sources: ProcedureBindingSources, name: str
    ) -> frozenset[UUID]:
        if name == "wp_index_id":
            return await self._from_wp_index_id(sources.project_id, sources.wp_index_id)
        if name == "wp_id":
            return await self._from_wp_id(sources.project_id, sources.wp_id)
        if name == "wp_code":
            return await self._from_wp_code(sources.project_id, sources.wp_code)
        if name == "procedure_row_task_id":
            return await self._from_row_task(
                sources.project_id, sources.procedure_row_task_id
            )
        if name == "procedure_instance_id":
            return await self._from_instance_id(
                sources.project_id, sources.procedure_instance_id
            )
        if name == "procedure_code":
            return await self._from_procedure_code(
                sources.project_id, sources.procedure_code, sources.audit_cycle
            )
        return frozenset()

    async def _from_wp_index_id(
        self, project_id: UUID, wp_index_id: UUID | None
    ) -> frozenset[UUID]:
        if wp_index_id is None:
            return frozenset()
        rows = (
            await self.db.execute(
                sa.select(WpIndex.id).where(
                    WpIndex.id == wp_index_id,
                    WpIndex.project_id == project_id,
                    WpIndex.is_deleted == sa.false(),
                )
            )
        ).scalars().all()
        return frozenset(rows)

    async def _from_wp_id(
        self, project_id: UUID, wp_id: UUID | None
    ) -> frozenset[UUID]:
        if wp_id is None:
            return frozenset()
        rows = (
            await self.db.execute(
                sa.select(WorkingPaper.wp_index_id).where(
                    WorkingPaper.id == wp_id,
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == sa.false(),
                )
            )
        ).scalars().all()
        return frozenset(r for r in rows if r is not None)

    async def _from_wp_code(
        self, project_id: UUID, wp_code: str | None
    ) -> frozenset[UUID]:
        code = (wp_code or "").strip()
        if not code:
            return frozenset()
        rows = (
            await self.db.execute(
                sa.select(WpIndex.id).where(
                    WpIndex.project_id == project_id,
                    WpIndex.wp_code == code,
                    WpIndex.is_deleted == sa.false(),
                )
            )
        ).scalars().all()
        return frozenset(rows)

    async def _from_row_task(
        self, project_id: UUID, task_id: UUID | None
    ) -> frozenset[UUID]:
        if task_id is None:
            return frozenset()
        rows = (
            await self.db.execute(
                sa.select(ProcedureRowTask.wp_index_id).where(
                    ProcedureRowTask.id == task_id,
                    ProcedureRowTask.project_id == project_id,
                    ProcedureRowTask.is_deleted == sa.false(),
                )
            )
        ).scalars().all()
        return frozenset(r for r in rows if r is not None)

    async def _from_instance_id(
        self, project_id: UUID, instance_id: UUID | None
    ) -> frozenset[UUID]:
        """标准/自定义 procedure 实例 → 经其 wp_id / wp_code 绑定解析 wp_index。

        ProcedureInstance 本身不存 wp_index_id，其到底稿的绑定通过 wp_id（优先）或 wp_code。
        实例缺失、或既无 wp_id 又无 wp_code → 零候选（fail-closed）。
        """
        if instance_id is None:
            return frozenset()
        row = (
            await self.db.execute(
                sa.select(ProcedureInstance.wp_id, ProcedureInstance.wp_code).where(
                    ProcedureInstance.id == instance_id,
                    ProcedureInstance.project_id == project_id,
                    ProcedureInstance.is_deleted == sa.false(),
                )
            )
        ).first()
        if row is None:
            return frozenset()
        wp_id, wp_code = row
        if wp_id is not None:
            return await self._from_wp_id(project_id, wp_id)
        if wp_code:
            return await self._from_wp_code(project_id, wp_code)
        return frozenset()

    async def _from_procedure_code(
        self, project_id: UUID, procedure_code: str | None, audit_cycle: str | None
    ) -> frozenset[UUID]:
        """procedure_code（可选 audit_cycle 收窄）→ 全部匹配实例的 wp_index 候选并集。

        标准/自定义 procedure 可能有多个实例（跨 cycle / 父子）。收集所有匹配实例经
        wp_id/wp_code 解析到的 **去重** wp_index 集合；若结果非唯一（0 或 >1），由上层判 fail-closed。
        """
        code = (procedure_code or "").strip()
        if not code:
            return frozenset()
        conds = [
            ProcedureInstance.project_id == project_id,
            ProcedureInstance.procedure_code == code,
            ProcedureInstance.is_deleted == sa.false(),
        ]
        if audit_cycle:
            conds.append(ProcedureInstance.audit_cycle == audit_cycle.strip())
        rows = (
            await self.db.execute(
                sa.select(ProcedureInstance.wp_id, ProcedureInstance.wp_code).where(*conds)
            )
        ).all()
        if not rows:
            return frozenset()
        # 收集每个实例的 wp_index 候选并集（各实例经 wp_id 优先，其次 wp_code）。
        result: set[UUID] = set()
        wp_ids: list[UUID] = []
        wp_codes: set[str] = set()
        for wp_id, wp_code in rows:
            if wp_id is not None:
                wp_ids.append(wp_id)
            elif wp_code:
                wp_codes.add(wp_code.strip())
        if wp_ids:
            # asyncpg：用 = ANY(:list)，禁止 IN tuple 参数
            r = (
                await self.db.execute(
                    sa.select(WorkingPaper.wp_index_id).where(
                        WorkingPaper.id == sa.any_(wp_ids),
                        WorkingPaper.project_id == project_id,
                        WorkingPaper.is_deleted == sa.false(),
                    )
                )
            ).scalars().all()
            result.update(x for x in r if x is not None)
        if wp_codes:
            r2 = (
                await self.db.execute(
                    sa.select(WpIndex.id).where(
                        WpIndex.wp_code == sa.any_(list(wp_codes)),
                        WpIndex.project_id == project_id,
                        WpIndex.is_deleted == sa.false(),
                    )
                )
            ).scalars().all()
            result.update(r2)
        return frozenset(result)

    # ------------------------------------------------------------------
    def _reject(
        self,
        sources: ProcedureBindingSources,
        reason: BindingRejectReason,
        per_source: dict[str, frozenset[UUID]] | None = None,
    ) -> WpBindingResolution:
        audit_reason = "binding_conflict" if reason in _CONFLICT_REASONS else None
        return WpBindingResolution(
            ok=False,
            wp_index_id=None,
            reason=reason,
            audit_reason=audit_reason,
            provided_identifiers=sources.provided_identifiers(),
            per_source=(
                {k: tuple(str(v) for v in ids) for k, ids in per_source.items()}
                if per_source
                else {}
            ),
        )
