"""Wp_Bound_Gate · resolve_wp_binding_and_access（Task 6 / 组件 C8 WpBoundGate）

Feature: procedure-delegation-visibility-isolation
Requirements:
  - 8.1：读取敏感元数据/业务内容或产生副作用之前完成授权判定。
  - 8.2：判定前仅读取 Binding_Minimum 所需最少关系（project/wp_index/wp file_version/sheet catalog）。
  - 8.3/8.4：页面级资源校验服务端解析的 wp_index 与 Sheet_Key 属于允许范围；客户端提供的
    附件/页面/版本/编辑器绑定与服务端解析不一致 → 拒绝。
  - 8.18/8.19：所有入口统一调用 ``resolve_wp_binding_and_access()``；先解析 Binding_Minimum，
    再返回 binding/role/access_kind/allowed_sheet_keys/current_version（``WpAccessContext``）。
  - 7.1–7.10：每个 AccessGrant 独立完整命中 Action_Matrix 九维后才并集页面/动作；多身份禁止拼接维度。
  - 7.5：Operation_Reviewer 复核动作必须同时命中 Action_Matrix 与 Review_Whitelist。
  - 9.1–9.11：不存在/跨项目/越权/未映射页/历史版本统一 External_Not_Found（404 + 固定 detail）；
    拒绝真实 reason 落安全 outbox；outbox 失败保持 404/429 并 Operational_Alert（经 ``DenialResponder``）。
  - 14.18/14.19：资源无关 429 在解析前依据 principal+project+Entry_Family 产生且不表明存在性；
    进入 gate 后全部不可见原因统一 404。
Design: 组件 C8 / "Core contracts and gate" / Architecture flowchart / Error Handling /
  Property 8/9/10/11/12。

**固定执行顺序（Design Architecture）**：
  认证（调用方提供 current_user）
  → 资源无关限流（principal+project+family，429 不表明存在性）
  → Binding_Minimum（project 反查 + ProcedureWpResolver 唯一解析 wp_index）
  → 角色/scope/grants/current version
  → path/body/claims 绑定一致性（client_wp*/version/sheet/token_claims）
  → 每个 grant 独立完整匹配 Action_Matrix（reviewer 另需 Review_Whitelist）
  → allow 后才读正文或 mutate（本函数只返回 WpAccessContext，不读正文/不写业务数据）。

**拒绝与限流统一走 C7 ``DenialResponder``（denial.py）**：进入 gate 后任何不可见原因 →
``responder.deny(reason=...)``（写安全 outbox → 抛 ``ExternalNotFound`` 404，wire body 恒
``{"detail":"资源不存在或不可访问"}``）；解析前限流 → ``responder.rate_limit(...)``（429 + Retry-After，
资源无关）。outbox 写入/投递失败仅 Operational_Alert，绝不改变 404/429（Req 9.10/9.11 / Property 12）。

**skeleton + adapters（Task 9–11 消费）**：本模块提供统一 callable 与最小 ``BindingAdapters`` 构造器
（wp/task → ResourceRef/WpBoundRequest）。实际 per-route 接入、sheet/version 提取与 token 全量校验由
Task 9–11 完成；``RateLimiter`` 由 Task 13/17 注入冻结 Rate_Limit_Profile（默认 ``NullRateLimiter``
measurement mode，永不限流）。

约定：service 纯读、不 flush/commit 业务写。asyncpg 等值/小集合查询。所有解析异常 fail-closed 拒绝。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Mapping, NoReturn, Protocol
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureInstance, ProcedureRowTask
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.wp_visibility.action_matrix import ActionMatrix, MatrixEntry, MatrixKey
from app.services.wp_visibility.contracts import (
    ALL_PAGES,
    AccessGrant,
    ResourceRef,
    VisibilityRole,
    WpAccessContext,
    WpBoundRequest,
)
from app.services.wp_visibility.denial import DenialReason, DenialResponder
from app.services.wp_visibility.epoch_cache import PersistentEpochCache
from app.services.wp_visibility.procedure_wp_resolver import (
    ProcedureBindingSources,
    ProcedureWpResolver,
)
from app.services.wp_visibility.role_classifier import VisibilityRoleClassifier
from app.services.wp_visibility.sheet_binding_catalog import SheetBindingCatalog
from app.services.wp_visibility.visibility_query import VisibilityQueryService

logger = logging.getLogger(__name__)

__all__ = [
    "RateLimitDecision",
    "RateLimiter",
    "NullRateLimiter",
    "WpBoundGate",
    "BindingAdapters",
    "resolve_wp_binding_and_access",
]


# ---------------------------------------------------------------------------
# 资源无关限流接口（Task 13/17 注入真实 Rate_Limit_Profile；默认 measurement-mode no-op）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RateLimitDecision:
    """限流判定结果：``allowed=False`` 时携带有效 ``retry_after``（秒）。"""

    allowed: bool
    retry_after: int = 1


class RateLimiter(Protocol):
    """资源无关限流器接口（仅 principal+project+family，绝不读资源存在性，Req 14.18）。

    返回 None 视为放行（等价 ``RateLimitDecision(allowed=True)``）。Task 13/17 用冻结
    ``Rate_Limit_Profile`` 实现；本任务默认 ``NullRateLimiter``（measurement mode，永不限流）。
    """

    def check(
        self,
        *,
        principal: UUID,
        project_id: UUID | None,
        entry_family: str,
    ) -> RateLimitDecision | None: ...


class NullRateLimiter:
    """限流 no-op（**测试双替身**）：永不限流。生产默认由 Task 13 换成 measurement-mode 限流器。"""

    def check(
        self, *, principal: UUID, project_id: UUID | None, entry_family: str
    ) -> RateLimitDecision | None:
        return None


_NULL_RATE_LIMITER: RateLimiter = NullRateLimiter()


def _default_rate_limiter() -> RateLimiter:
    """gate 生产默认限流器（Task 13 组件 C15）：measurement-mode，inert profile 时永不限流、
    只观测；Task 17 冻结容量 profile 后同一 seam 即强制阈值。测试仍可注入 ``NullRateLimiter``。"""
    from app.services.wp_visibility.rate_limit_profile import get_default_rate_limiter

    return get_default_rate_limiter()


def _family_of(request: WpBoundRequest) -> str:
    """Entry_Family（限流/审计维度）：显式 entry_family 优先，否则取 entrypoint 前缀。"""
    if request.entry_family:
        return request.entry_family
    ep = request.entrypoint or ""
    return ep.split(".", 1)[0] if ep else "unknown"


# ---------------------------------------------------------------------------
# Wp_Bound_Gate
# ---------------------------------------------------------------------------
class WpBoundGate:
    """统一底稿资源授权门。``resolve`` / 模块级 ``resolve_wp_binding_and_access`` 是唯一入口。"""

    def __init__(
        self,
        db: AsyncSession,
        *,
        rate_limiter: RateLimiter | None = None,
        responder: DenialResponder | None = None,
        epoch_cache: "PersistentEpochCache | None" = None,
    ) -> None:
        self.db = db
        # 生产默认 = measurement-mode 限流器（Task 13）；显式注入 NullRateLimiter 作测试双替身。
        self.rate_limiter = rate_limiter if rate_limiter is not None else _default_rate_limiter()
        self.responder = responder if responder is not None else DenialResponder()
        # 持久 epoch 缓存（Task 13 组件 C15）：注入后授权结果按 (user,project,wp_index,epoch) 缓存，
        # 撤权 ≤1s 收敛且绝不 stale-allow（Property 18）。None → 每次 authoritative 现取（默认，向后兼容）。
        self.epoch_cache = epoch_cache
        self.resolver = ProcedureWpResolver(db)
        self.classifier = VisibilityRoleClassifier(db)
        self.query = VisibilityQueryService(db)

    async def resolve(
        self, current_user, request: WpBoundRequest
    ) -> WpAccessContext:
        """执行固定顺序流水线；allow → ``WpAccessContext``，deny → ``ExternalNotFound``（404），
        限流 → ``RateLimited``（429）。"""
        ref = request.resource_ref
        family = _family_of(request)
        actor_id = getattr(current_user, "id", None)

        # ── 步骤 2：资源无关限流（principal+project+family，解析前；Req 14.18）──
        decision = self.rate_limiter.check(
            principal=actor_id,
            project_id=ref.project_id,
            entry_family=family,
        )
        if decision is not None and not decision.allowed:
            await self.responder.rate_limit(
                retry_after=decision.retry_after,
                entrypoint=request.entrypoint,
                entry_family=family,
                route_name=request.route_name,
                http_method=request.method,
                request_id=request.request_id,
                actor_user_id=actor_id,
                project_id=ref.project_id,
            )

        # ── 步骤 3：Binding_Minimum — 解析 project + 唯一 wp_index ──
        project_id = await self._resolve_project_id(ref)
        if project_id is None:
            await self._deny(request, DenialReason.not_found, actor_id, None)

        # 跨项目：客户端声明 project 与反查出的资源 project 不一致 → cross_project（Req 9.2）。
        if ref.project_id is not None and project_id != ref.project_id:
            await self._deny(
                request, DenialReason.cross_project, actor_id, ref.project_id
            )

        resolution = await self.resolver.resolve(
            ProcedureBindingSources(
                project_id=project_id,
                procedure_instance_id=ref.procedure_instance_id,
                procedure_row_task_id=ref.procedure_row_task_id,
                procedure_code=ref.procedure_code,
                audit_cycle=ref.audit_cycle,
                wp_index_id=ref.wp_index_id,
                wp_id=ref.wp_id,
                wp_code=ref.wp_code,
                sheet_key=request.requested_sheet_key,
                version=request.requested_version,
            )
        )
        if not resolution.ok or resolution.wp_index_id is None:
            # 零/多候选、来源冲突、查询异常 → binding_conflict（Req 4.13 / 9.9）；无源 → not_found。
            reason = (
                DenialReason.binding_conflict
                if resolution.audit_reason == "binding_conflict"
                else DenialReason.not_found
            )
            await self._deny(
                request, reason, actor_id, project_id,
                detail=resolution.provided_identifiers,
            )
        wp_index_id = resolution.wp_index_id

        # ── 步骤 4：角色/scope/grants/current version ──
        ctx = await self.classifier.classify(current_user, project_id)
        if self.epoch_cache is not None:
            # 按 (user,project,wp_index,持久 epoch) 缓存 grants；撤权→epoch 递增后旧条目永不匹配，
            # ≤1s DB 核对 + Redis 即时淘汰双路径收敛，epoch 不可得则 authoritative 现取（fail-closed）。
            grants = await self.epoch_cache.get_or_load(
                self.db,
                user_id=actor_id,
                project_id=project_id,
                wp_index_id=wp_index_id,
                loader=lambda: self.query.grants_for_wp_index(ctx, wp_index_id),
            )
        else:
            grants = await self.query.grants_for_wp_index(ctx, wp_index_id)
        if not grants:
            # 可见集为空：未委派 / 越权 / scope 外（fail-closed，统一 404）。
            await self._deny(
                request, DenialReason.not_delegated, actor_id, project_id,
                wp_index_id=wp_index_id,
            )

        wp_id, current_version = await self._resolve_current_version(
            project_id, wp_index_id
        )

        # ── 步骤 5：path/body/claims 绑定一致性（Req 8.4 / 9.5 / 10）──
        # 客户端声明的 wp_index / wp 必须与服务端解析一致。
        if ref.client_wp_index_id is not None and ref.client_wp_index_id != wp_index_id:
            await self._deny(
                request, DenialReason.binding_conflict, actor_id, project_id,
                wp_index_id=wp_index_id, wp_id=wp_id,
            )
        if ref.client_wp_id is not None and ref.client_wp_id != wp_id:
            await self._deny(
                request, DenialReason.binding_conflict, actor_id, project_id,
                wp_index_id=wp_index_id, wp_id=wp_id,
            )

        # 版本一致性：请求历史版本（≠ Current_Version）统一 404（gate 只授权 Current_Version）。
        if (
            request.requested_version is not None
            and current_version is not None
            and str(request.requested_version) != str(current_version)
        ):
            await self._deny(
                request, DenialReason.historical_version, actor_id, project_id,
                wp_index_id=wp_index_id, wp_id=wp_id,
            )

        # 页面级：解析并校验 sheet_key 属于本 wp_index（Req 8.3 / 5.9）。
        resolved_sheet_key: str | None = None
        if request.requested_sheet_key is not None:
            catalog = await SheetBindingCatalog.build(
                self.db, project_id, wp_index_id, current_version
            )
            sr = catalog.resolve_sheet_key(request.requested_sheet_key)
            if not sr.ok or sr.sheet_key is None:
                await self._deny(
                    request, DenialReason.sheet_unmapped, actor_id, project_id,
                    wp_index_id=wp_index_id, wp_id=wp_id,
                )
            resolved_sheet_key = sr.sheet_key

        # token claims（OnlyOffice/WOPI，Req 10）：
        #   - 有原始签名令牌 request.signed_token → 全量校验（签名/过期/jti/非空/逐 claim 绑定，Task 11）。
        #   - 仅有 token_claims dict → 一致性绑定校验（骨架路径，供非签名场景与既有测试）。
        if request.signed_token is not None or request.token_claims is not None:
            if not self._token_valid(
                request, project_id, wp_id, resolution.provided_identifiers,
                current_version, resolved_sheet_key,
            ):
                await self._deny(
                    request, DenialReason.token_invalid, actor_id, project_id,
                    wp_index_id=wp_index_id, wp_id=wp_id, sheet_key=resolved_sheet_key,
                )

        # ── 步骤 6：每个 grant 独立完整匹配 Action_Matrix（多身份并集，禁止拼接）──
        matched = self._match_grants(ctx.role, grants, request, resolved_sheet_key)
        if not matched:
            # 有可见性但动作不允许 → action_denied；请求特定 sheet 但无 grant 覆盖 → sheet_unmapped。
            reason = DenialReason.action_denied
            if resolved_sheet_key is not None and not any(
                g.covers_sheet(resolved_sheet_key) for g in grants
            ):
                reason = DenialReason.sheet_unmapped
            await self._deny(
                request, reason, actor_id, project_id,
                wp_index_id=wp_index_id, wp_id=wp_id, sheet_key=resolved_sheet_key,
            )

        # ── 步骤 7：allow — 并集命中的页面/access_kind（禁止跨身份拼接维度，Req 7.10）──
        access_kinds = frozenset(g.access_kind for g, _e in matched)
        allowed_sheet_keys = self._union_pages(matched)
        readonly = all(g.readonly for g, _e in matched)
        return WpAccessContext(
            project_id=project_id,
            wp_index_id=wp_index_id,
            role=ctx.role,
            access_kinds=access_kinds,
            allowed_sheet_keys=allowed_sheet_keys,
            resolved_sheet_key=resolved_sheet_key,
            current_version=current_version,
            readonly=readonly,
            wp_id=wp_id,
        )

    # ------------------------------------------------------------------
    # 拒绝快捷（写 outbox → 抛 ExternalNotFound；DenialResponder.deny 为 NoReturn）
    # ------------------------------------------------------------------
    async def _deny(
        self,
        request: WpBoundRequest,
        reason: DenialReason,
        actor_id: UUID | None,
        project_id: UUID | None,
        *,
        wp_index_id: UUID | None = None,
        wp_id: UUID | None = None,
        sheet_key: str | None = None,
        detail: Mapping | None = None,
    ) -> NoReturn:  # deny 写 outbox 后抛 ExternalNotFound，永不正常返回
        await self.responder.deny(
            reason=reason,
            entrypoint=request.entrypoint,
            entry_family=_family_of(request),
            route_name=request.route_name,
            http_method=request.method,
            action=request.action,
            request_id=request.request_id,
            actor_user_id=actor_id,
            project_id=project_id,
            wp_index_id=wp_index_id,
            wp_id=wp_id,
            sheet_key=sheet_key or request.requested_sheet_key,
            requested_version=request.requested_version,
            detail=dict(detail) if detail else None,
        )

    # ------------------------------------------------------------------
    # 步骤 6 内部：grant × matrix 匹配
    # ------------------------------------------------------------------
    def _match_grants(
        self,
        role: VisibilityRole,
        grants: list[AccessGrant],
        request: WpBoundRequest,
        resolved_sheet_key: str | None,
    ) -> list[tuple[AccessGrant, MatrixEntry]]:
        """逐 grant 用自身 access_kind/identity/页面独立命中完整矩阵条目（Req 7.9）。"""
        matched: list[tuple[AccessGrant, MatrixEntry]] = []
        for g in grants:
            key = MatrixKey(
                user_class=role.value,
                access_kind=g.access_kind,
                identity=g.identity,
                entrypoint=request.entrypoint,
                route=request.route_name,
                method=request.method,
                action=request.action,
                source_state=request.source_state,
                target_state=request.target_state,
            )
            entry = ActionMatrix.lookup(key)
            if entry is None:
                continue  # 该身份未登记此动作 → 该 grant 不授权（不拼接，Req 7.3/7.4）
            # History_Only（readonly grant）拒绝一切写动作（Req 5.12–5.14）。
            if g.readonly and entry.access_mode == "mutation":
                continue
            # 页面隔离：请求特定 sheet 时，该 grant 必须覆盖该 sheet（Req 5.8/8.3）。
            if resolved_sheet_key is not None and not g.covers_sheet(resolved_sheet_key):
                continue
            # reviewer 复核写动作：另需命中 Review_Whitelist（Req 7.5 / Property 9）。
            if g.access_kind == "reviewer" and entry.access_mode == "mutation":
                if not ActionMatrix.is_review_whitelisted(key):
                    continue
                # changes_requested reason 必填（Review_Whitelist 语义）。
                if request.target_state == "changes_requested" and not (
                    request.review_reason or ""
                ).strip():
                    continue
            matched.append((g, entry))
        return matched

    @staticmethod
    def _union_pages(
        matched: list[tuple[AccessGrant, MatrixEntry]],
    ) -> frozenset[str] | str:
        """命中 grant 的页面并集（任一 ALL_PAGES → ALL_PAGES）。"""
        pages: set[str] = set()
        for g, _e in matched:
            if g.allowed_sheet_keys == ALL_PAGES:
                return ALL_PAGES
            pages |= set(g.allowed_sheet_keys)  # type: ignore[arg-type]
        return frozenset(pages)

    # ------------------------------------------------------------------
    # Binding_Minimum 辅助（仅读定位关系，不读业务正文）
    # ------------------------------------------------------------------
    async def _resolve_project_id(self, ref: ResourceRef) -> UUID | None:
        """解析 project：从最强 identity 反查资源真实 project；显式 project 仅在无法反查时兜底。

        反查真实 project 是 cross_project 检测（Req 9.2）的前提：客户端声明 ``ref.project_id``
        与资源真实 project 不一致时，``resolve`` 会据此判 cross_project；无强 identity 可反查
        （如仅 wp_code）时返回声明 project，由 ProcedureWpResolver 的项目过滤兜底为 binding_conflict。
        """
        real = await self._reverse_project(ref)
        if ref.project_id is not None:
            return real if real is not None else ref.project_id
        return real

    async def _reverse_project(self, ref: ResourceRef) -> UUID | None:
        """从 wp_id/wp_index_id/task/instance 反查资源真实 project（纯读定位关系）。"""
        try:
            if ref.wp_id is not None:
                pid = (
                    await self.db.execute(
                        sa.select(WorkingPaper.project_id).where(
                            WorkingPaper.id == ref.wp_id,
                            WorkingPaper.is_deleted == sa.false(),
                        )
                    )
                ).scalar_one_or_none()
                if pid is not None:
                    return pid
            if ref.wp_index_id is not None:
                pid = (
                    await self.db.execute(
                        sa.select(WpIndex.project_id).where(
                            WpIndex.id == ref.wp_index_id,
                            WpIndex.is_deleted == sa.false(),
                        )
                    )
                ).scalar_one_or_none()
                if pid is not None:
                    return pid
            if ref.procedure_row_task_id is not None:
                pid = (
                    await self.db.execute(
                        sa.select(ProcedureRowTask.project_id).where(
                            ProcedureRowTask.id == ref.procedure_row_task_id,
                            ProcedureRowTask.is_deleted == sa.false(),
                        )
                    )
                ).scalar_one_or_none()
                if pid is not None:
                    return pid
            if ref.procedure_instance_id is not None:
                pid = (
                    await self.db.execute(
                        sa.select(ProcedureInstance.project_id).where(
                            ProcedureInstance.id == ref.procedure_instance_id,
                            ProcedureInstance.is_deleted == sa.false(),
                        )
                    )
                ).scalar_one_or_none()
                if pid is not None:
                    return pid
        except Exception as exc:  # noqa: BLE001 — fail-closed
            logger.warning("gate project 反查异常: %s", exc)
            return None
        return None

    async def _resolve_current_version(
        self, project_id: UUID, wp_index_id: UUID
    ) -> tuple[UUID | None, str | None]:
        """当前底稿 wp_id + Current_Version（无 WP → nullable，"底稿尚未生成"）。"""
        try:
            row = (
                await self.db.execute(
                    sa.select(WorkingPaper.id, WorkingPaper.file_version)
                    .where(
                        WorkingPaper.project_id == project_id,
                        WorkingPaper.wp_index_id == wp_index_id,
                        WorkingPaper.is_deleted == sa.false(),
                    )
                    .order_by(WorkingPaper.file_version.desc())
                    .limit(1)
                )
            ).first()
        except Exception as exc:  # noqa: BLE001 — fail-closed（版本未知 → None）
            logger.warning("gate current_version 解析异常: %s", exc)
            return None, None
        if row is None:
            return None, None
        return row[0], str(row[1])

    @staticmethod
    def _token_valid(
        request: WpBoundRequest,
        project_id: UUID | None,
        wp_id: UUID | None,
        provided_identifiers: Mapping[str, str],
        current_version: str | None,
        resolved_sheet_key: str | None,
    ) -> bool:
        """OnlyOffice/WOPI 令牌校验分派（Task 11 / 组件 C11 EditorSecurity）。

        - ``request.signed_token`` 存在 → 全量校验（签名/过期/jti/非空/逐 claim 绑定/写权限）。
          secret 从 ``settings.ONLYOFFICE_JWT_SECRET`` 读取；缺失 fail-closed（Req 10.9）。
        - 否则回退 dict 一致性校验（``_token_claims_consistent``）。
        """
        from app.services.wp_visibility import editor_security as _es

        if request.signed_token is not None:
            from app.core.config import settings

            expected: dict[str, str] = {}
            if project_id is not None:
                expected["project_id"] = str(project_id)
            if wp_id is not None:
                expected["wp_id"] = str(wp_id)
            prov_code = provided_identifiers.get("wp_code")
            if prov_code:
                expected["wp_code"] = str(prov_code)
            if current_version is not None:
                expected["version"] = str(current_version)
            # sheet 绑定：URL 请求的 sheet（requested_sheet_key）优先，其次服务端解析 sheet_key。
            sheet = request.requested_sheet_key or resolved_sheet_key
            if sheet is not None:
                expected["sheet_name"] = str(sheet)
            # 动作绑定：token claim.action 必须等于本入口的 action。
            if request.action:
                expected["action"] = str(request.action)
            require_write = request.action in _es.WRITE_ACTIONS
            result = _es.validate_editor_token(
                request.signed_token,
                secret=settings.ONLYOFFICE_JWT_SECRET,
                expected=expected,
                require_write=require_write,
            )
            return result.ok
        return WpBoundGate._token_claims_consistent(
            request, wp_id, provided_identifiers, current_version
        )

    @staticmethod
    def _token_claims_consistent(
        request: WpBoundRequest,
        wp_id: UUID | None,
        provided_identifiers: Mapping[str, str],
        current_version: str | None,
    ) -> bool:
        """OnlyOffice/WOPI claim 逐项与服务端解析一致（骨架；signed_token 走 _token_valid 全量）。

        本骨架只校验"已提供 claim 与服务端解析非空且相等"：wp_id / wp_code / version / sheet / action。
        缺失/为空/不一致 → False（token_invalid）。签名与过期校验在 Task 11 的 EditorSecurity。
        """
        claims = request.token_claims or {}
        # 任一提供的 claim 为空即失败（Req 10.1 每个 claim 非空）。
        for k in ("wp_id", "wp_code", "sheet_name", "version", "action"):
            if k in claims and not (claims.get(k) or "").strip():
                return False
        c_wp = claims.get("wp_id")
        if c_wp and wp_id is not None and c_wp != str(wp_id):
            return False
        c_code = claims.get("wp_code")
        prov_code = provided_identifiers.get("wp_code")
        if c_code and prov_code and c_code != prov_code:
            return False
        c_ver = claims.get("version")
        if c_ver and current_version is not None and c_ver != str(current_version):
            return False
        c_action = claims.get("action")
        if c_action and c_action != request.action:
            return False
        return True


# ---------------------------------------------------------------------------
# 统一 callable（Task 8–11 全入口共用）
# ---------------------------------------------------------------------------
async def resolve_wp_binding_and_access(
    db: AsyncSession,
    current_user,
    request: WpBoundRequest,
    *,
    rate_limiter: RateLimiter | None = None,
    responder: DenialResponder | None = None,
    epoch_cache: PersistentEpochCache | None = None,
) -> WpAccessContext:
    """唯一服务端授权门（Req 8.18/8.19）。

    先解析 Binding_Minimum，再返回 binding/role/access_kind/allowed_sheet_keys/current_version。
    deny → ``ExternalNotFound``（对外 404）；限流 → ``RateLimited``（对外 429）。
    ``rate_limiter`` 默认 = measurement-mode 限流器（Task 13）；``epoch_cache`` 注入后授权结果
    按持久 epoch 缓存并 ≤1s 收敛（Property 18）。
    """
    gate = WpBoundGate(
        db, rate_limiter=rate_limiter, responder=responder, epoch_cache=epoch_cache
    )
    return await gate.resolve(current_user, request)


# ---------------------------------------------------------------------------
# BindingAdapters（C9）：最小 ResourceRef/WpBoundRequest 构造器（Task 9–11 消费）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BindingAdapters:
    """把各入口的原始参数装配为 ``WpBoundRequest``（最小绑定；不读业务正文）。

    Task 9–11 per-route 接入时用这些构造器统一产出 gate 请求；页面/版本/claims 由各入口按需填。
    这里只提供稳定的构造 shape，不含任何 IO 或授权逻辑。
    """

    entry_kind: str = "http"

    def wp(
        self,
        *,
        entrypoint: str,
        action: str,
        method: str,
        wp_id: UUID | None = None,
        wp_index_id: UUID | None = None,
        wp_code: str | None = None,
        project_id: UUID | None = None,
        route_name: str | None = None,
        entry_family: str | None = None,
        requested_sheet_key: str | None = None,
        requested_version: str | None = None,
        source_state: str = "none",
        target_state: str = "none",
        client_wp_id: UUID | None = None,
        client_wp_index_id: UUID | None = None,
        token_claims: Mapping[str, str] | None = None,
        signed_token: str | None = None,
        review_reason: str | None = None,
        request_id: str | None = None,
    ) -> WpBoundRequest:
        return WpBoundRequest(
            entry_kind=self.entry_kind,  # type: ignore[arg-type]
            entrypoint=entrypoint,
            action=action,
            method=method,
            route_name=route_name,
            entry_family=entry_family,
            resource_ref=ResourceRef(
                project_id=project_id,
                wp_id=wp_id,
                wp_index_id=wp_index_id,
                wp_code=wp_code,
                client_wp_id=client_wp_id,
                client_wp_index_id=client_wp_index_id,
            ),
            requested_sheet_key=requested_sheet_key,
            requested_version=requested_version,
            source_state=source_state,
            target_state=target_state,
            token_claims=token_claims,
            signed_token=signed_token,
            review_reason=review_reason,
            request_id=request_id,
        )

    def task(
        self,
        *,
        entrypoint: str,
        action: str,
        method: str,
        task_id: UUID,
        project_id: UUID | None = None,
        route_name: str | None = None,
        entry_family: str | None = None,
        requested_sheet_key: str | None = None,
        source_state: str = "none",
        target_state: str = "none",
        review_reason: str | None = None,
        request_id: str | None = None,
    ) -> WpBoundRequest:
        return WpBoundRequest(
            entry_kind=self.entry_kind,  # type: ignore[arg-type]
            entrypoint=entrypoint,
            action=action,
            method=method,
            route_name=route_name,
            entry_family=entry_family,
            resource_ref=ResourceRef(
                project_id=project_id, procedure_row_task_id=task_id
            ),
            requested_sheet_key=requested_sheet_key,
            source_state=source_state,
            target_state=target_state,
            review_reason=review_reason,
            request_id=request_id,
        )
