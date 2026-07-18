"""Entry integration helpers · 附件/文件/导入导出/批量/非 HTTP 执行器接入 gate
（Task 10 / 组件 C10 EntryIntegration）

Feature: procedure-delegation-visibility-isolation
Requirements:
  - 8.6：文件内容/下载/预览/导入/导出/转换入口独立 gate 判定。
  - 8.7：附件 upload/read/download/delete 入口独立 gate 判定。
  - 8.8：编辑器/文件读取/保存/回调/转换入口独立 gate 判定（本模块只覆盖 file/convert，编辑器归 Task 11）。
  - 8.13/8.14：单项 / 批量·导入·导出·嵌套资源入口对每个资源独立 gate。
  - 8.16：callback/后台/延迟任务 **实际执行时** 对每个资源重新 gate（re-gate）。
  - 8.17：新增/变更入口提供服务前接入 gate + Action_Matrix。
  - 9.1–9.7：不存在/跨项目/越权/未映射页统一 External_Not_Found（404）。
  - 13.13–13.15：非 HTTP 执行器登记 kind/callable，并在执行时 re-gate；稳定 test id。
  - 16.17：撤权后排队任务拒绝。
Design: 组件 C10（EntryIntegration）/ C9（BindingAdapters）/ "Binding adapters ... 批量写在任何
  副作用前逐资源 preflight，显式任一拒绝则按原子模式整体失败" / "callback/worker/retry/dead-letter
  callables RE-gate at actual execution time"。

本模块是 HTTP 与非 HTTP 入口接入统一门的 **薄编排层**：
  - 只装配 ``WpBoundRequest``（经 ``BindingAdapters``）并调用 ``resolve_wp_binding_and_access()``。
  - 不读业务正文、不写业务数据；service 仍只 flush（router 提交）。
  - 附件绑定：attachment → project + links → wp（Design "Binding adapters"）。附件本身可能不绑定到
    具体底稿（项目级证据），此时仅做 wp-link 隔离层的 **additive** 校验，不替换既有项目级授权。
  - 批量：export 用 **可见集** 过滤（不泄露不可见底稿存在性）；import/write 在任何副作用前 **逐资源
    preflight**，显式任一拒绝则整请求失败（原子）。
  - 非 HTTP：worker/callback/retry/dead-letter 在实际执行时 re-gate（``entry_kind`` 非 http）。
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wp_visibility.contracts import WpAccessContext
from app.services.wp_visibility.denial import (
    DenialReason,
    DenialResponder,
    ExternalNotFound,
    RateLimited,
)
from app.services.wp_visibility.wp_bound_gate import (
    BindingAdapters,
    RateLimiter,
    resolve_wp_binding_and_access,
)

logger = logging.getLogger(__name__)

__all__ = [
    "HTTP_ADAPTERS",
    "WORKER_ADAPTERS",
    "CALLBACK_ADAPTERS",
    "gate_wp",
    "try_gate_wp",
    "enforce_attachment_wp_visibility",
    "gate_attachment_associate",
    "make_bulk_preflight",
    "make_bulk_visible_filter",
]

# 入口 kind 对应的 BindingAdapters（entry_kind 影响审计/ledger 的 http vs 非 http 归类）。
HTTP_ADAPTERS = BindingAdapters(entry_kind="http")
WORKER_ADAPTERS = BindingAdapters(entry_kind="worker")
CALLBACK_ADAPTERS = BindingAdapters(entry_kind="callback")

_ADAPTERS_BY_KIND: dict[str, BindingAdapters] = {
    "http": HTTP_ADAPTERS,
    "worker": WORKER_ADAPTERS,
    "callback": CALLBACK_ADAPTERS,
    "retry": WORKER_ADAPTERS,
    "dead_letter": WORKER_ADAPTERS,
}


class _SilentResponder(DenialResponder):
    """可见性过滤专用响应器：拒绝是预期结果（非安全事件），不写安全 outbox。

    用于 export 可见集过滤 —— 不可见底稿被静默排除，不构成需要审计的拒绝事件，也不泄露存在性。
    仍抛 ``ExternalNotFound`` / ``RateLimited``（由 ``try_gate_wp`` 捕获转 None）。
    """

    async def _enqueue(self, **fields) -> None:  # noqa: D401 — 静默
        return None


_SILENT_RESPONDER = _SilentResponder()


# ---------------------------------------------------------------------------
# 通用 wp gate 封装
# ---------------------------------------------------------------------------
async def gate_wp(
    db: AsyncSession,
    current_user,
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
    entry_kind: str = "http",
    requested_sheet_key: str | None = None,
    requested_version: str | None = None,
    source_state: str = "none",
    target_state: str = "none",
    client_wp_id: UUID | None = None,
    client_wp_index_id: UUID | None = None,
    review_reason: str | None = None,
    request_id: str | None = None,
    responder: DenialResponder | None = None,
    rate_limiter: RateLimiter | None = None,
) -> WpAccessContext:
    """装配 ``WpBoundRequest`` 并调用统一门；deny → ``ExternalNotFound``（404）。"""
    adapters = _ADAPTERS_BY_KIND.get(entry_kind, HTTP_ADAPTERS)
    request = adapters.wp(
        entrypoint=entrypoint,
        action=action,
        method=method,
        wp_id=wp_id,
        wp_index_id=wp_index_id,
        wp_code=wp_code,
        project_id=project_id,
        route_name=route_name,
        entry_family=entry_family,
        requested_sheet_key=requested_sheet_key,
        requested_version=requested_version,
        source_state=source_state,
        target_state=target_state,
        client_wp_id=client_wp_id,
        client_wp_index_id=client_wp_index_id,
        review_reason=review_reason,
        request_id=request_id,
    )
    return await resolve_wp_binding_and_access(
        db, current_user, request, rate_limiter=rate_limiter, responder=responder
    )


async def try_gate_wp(
    db: AsyncSession,
    current_user,
    *,
    entrypoint: str,
    action: str,
    method: str,
    wp_id: UUID | None = None,
    requested_sheet_key: str | None = None,
    entry_kind: str = "http",
    entry_family: str | None = None,
) -> WpAccessContext | None:
    """静默 gate：allow → ``WpAccessContext``；deny/限流 → None（不写安全 outbox）。

    仅用于 **可见集过滤**（export）等拒绝属预期的路径，不用于显式请求授权。
    """
    try:
        return await gate_wp(
            db,
            current_user,
            entrypoint=entrypoint,
            action=action,
            method=method,
            wp_id=wp_id,
            requested_sheet_key=requested_sheet_key,
            entry_kind=entry_kind,
            entry_family=entry_family,
            responder=_SILENT_RESPONDER,
        )
    except (ExternalNotFound, RateLimited):
        return None


# ---------------------------------------------------------------------------
# 附件 wp-link 可见性隔离（additive；不替换既有项目级授权）
# ---------------------------------------------------------------------------
async def _linked_wp_ids(db: AsyncSession, attachment_id: UUID) -> list[UUID]:
    """附件关联的底稿 wp_id 列表（未软删的关联；Design attachment→links→wp）。"""
    from app.models.attachment_models import Attachment, AttachmentWorkingPaper

    rows = (
        await db.execute(
            sa.select(AttachmentWorkingPaper.wp_id)
            .join(Attachment, Attachment.id == AttachmentWorkingPaper.attachment_id)
            .where(
                AttachmentWorkingPaper.attachment_id == attachment_id,
                Attachment.is_deleted == sa.false(),
            )
        )
    ).scalars().all()
    # 去重保序
    seen: set[UUID] = set()
    out: list[UUID] = []
    for wid in rows:
        if wid is not None and wid not in seen:
            seen.add(wid)
            out.append(wid)
    return out


async def enforce_attachment_wp_visibility(
    db: AsyncSession,
    current_user,
    *,
    attachment_id: UUID,
    action: str,
    method: str,
    entrypoint: str,
    entry_family: str = "attachment",
    responder: DenialResponder | None = None,
) -> WpAccessContext | None:
    """附件 wp-link 隔离层（Req 8.7 / 9.3）。

    - 附件 **绑定到底稿**（存在关联）：要求当前用户对至少一个关联底稿 gate 可见（allow）；
      全部不可见 → ``ExternalNotFound``（404）。返回首个命中的 ``WpAccessContext``。
    - 附件 **未绑定底稿**（项目级证据）：返回 None，交由调用方既有项目级授权处置（additive，不放宽也不收紧）。

    调用方须在本函数之前完成既有项目级授权（如 ``_ensure_project_access``），本层只 **收紧**
    到「关联底稿可见」，不替换项目级检查。
    """
    linked = await _linked_wp_ids(db, attachment_id)
    if not linked:
        return None  # 项目级证据：既有项目级授权已足够

    resp = responder if responder is not None else DenialResponder()
    for wid in linked:
        ctx = await try_gate_wp(
            db,
            current_user,
            entrypoint=entrypoint,
            action=action,
            method=method,
            wp_id=wid,
            entry_family=entry_family,
        )
        if ctx is not None:
            return ctx
    # 关联了底稿但一个都不可见 → 统一 404（不泄露真实原因）。
    await resp.deny(
        reason=DenialReason.not_delegated,
        entrypoint=entrypoint,
        entry_family=entry_family,
        http_method=method,
        action=action,
        actor_user_id=getattr(current_user, "id", None),
        detail={"attachment_id": str(attachment_id)},
    )
    raise AssertionError("unreachable")  # deny 为 NoReturn


# ---------------------------------------------------------------------------
# 附件 associate 多资源校验（Task 10 headline）
# ---------------------------------------------------------------------------
async def gate_attachment_associate(
    db: AsyncSession,
    current_user,
    *,
    attachment_id: UUID,
    target_wp_id: UUID,
    requested_sheet_key: str | None = None,
    review_reason: str | None = None,
    responder: DenialResponder | None = None,
    request_id: str | None = None,
) -> WpAccessContext:
    """associate 多资源门（Req 8.7 / 8.13 / 9.1–9.3）：**全部通过或整请求失败（副作用前）**。

    依次校验（任一失败 → ``ExternalNotFound`` 404，副作用前）：
      1. 附件存在且未软删（否则 not_found）。
      2. 目标底稿存在且未软删（否则 not_found）。
      3. 附件项目 == 目标底稿项目（否则 cross_project）。
      4. **源附件权限**：附件若关联到底稿，要求当前用户对源附件可见（read）；未关联则由项目同项目 +
         目标写权限隐含（附件在同一项目，第 4 步经第 5 步的项目建立）。
      5. **目标 sheet 写权限**：对目标底稿以 ``attach_associate`` 动作过 gate（仅 lead/admin/
         supervisor_scope 在矩阵中登记该动作 → assignee/reviewer 被拒），返回其 ``WpAccessContext``。

    返回目标底稿的 allow ``WpAccessContext``（第 5 步结果）。
    """
    from app.models.attachment_models import Attachment
    from app.models.workpaper_models import WorkingPaper

    resp = responder if responder is not None else DenialResponder()
    actor_id = getattr(current_user, "id", None)

    # ── 1. 附件项目 ──
    att_project = (
        await db.execute(
            sa.select(Attachment.project_id).where(
                Attachment.id == attachment_id,
                Attachment.is_deleted == sa.false(),
            )
        )
    ).scalar_one_or_none()
    if att_project is None:
        await resp.deny(
            reason=DenialReason.not_found,
            entrypoint="attachment.associate",
            entry_family="attachment",
            http_method="POST",
            action="attach_associate",
            actor_user_id=actor_id,
            request_id=request_id,
            detail={"attachment_id": str(attachment_id)},
        )

    # ── 2. 目标底稿项目 ──
    wp_project = (
        await db.execute(
            sa.select(WorkingPaper.project_id).where(
                WorkingPaper.id == target_wp_id,
                WorkingPaper.is_deleted == sa.false(),
            )
        )
    ).scalar_one_or_none()
    if wp_project is None:
        await resp.deny(
            reason=DenialReason.not_found,
            entrypoint="attachment.associate",
            entry_family="attachment",
            http_method="POST",
            action="attach_associate",
            actor_user_id=actor_id,
            project_id=att_project,
            wp_id=target_wp_id,
            request_id=request_id,
        )

    # ── 3. 同项目校验（跨项目 associate 拒绝）──
    if att_project != wp_project:
        await resp.deny(
            reason=DenialReason.cross_project,
            entrypoint="attachment.associate",
            entry_family="attachment",
            http_method="POST",
            action="attach_associate",
            actor_user_id=actor_id,
            project_id=wp_project,
            wp_id=target_wp_id,
            request_id=request_id,
            detail={"attachment_id": str(attachment_id)},
        )

    # ── 4. 源附件权限（若关联到底稿，要求当前用户对源附件可见）──
    await enforce_attachment_wp_visibility(
        db,
        current_user,
        attachment_id=attachment_id,
        action="attach_read",
        method="GET",
        entrypoint="attachment.read",
        responder=resp,
    )

    # ── 5. 目标 sheet/底稿写权限（attach_associate 仅 lead/admin/supervisor_scope）──
    return await gate_wp(
        db,
        current_user,
        entrypoint="attachment.associate",
        action="attach_associate",
        method="POST",
        wp_id=target_wp_id,
        project_id=wp_project,
        entry_family="attachment",
        requested_sheet_key=requested_sheet_key,
        review_reason=review_reason,
        request_id=request_id,
        responder=resp,
    )


# ---------------------------------------------------------------------------
# 批量：可见集过滤（export）+ 逐资源 preflight（import/write，原子）
# ---------------------------------------------------------------------------
def make_bulk_visible_filter(
    db: AsyncSession,
    current_user,
    *,
    entrypoint: str = "workpaper.detail",
    action: str = "read_detail",
    method: str = "GET",
    entry_kind: str = "http",
    entry_family: str = "bulk",
) -> Callable[[str | UUID | None, str | None], Awaitable[bool]]:
    """构造 export 可见集过滤闭包：返回 ``async (wp_id, sheet_code) -> bool``。

    默认以「读详情」可见性判定（可读即可纳入交付 ZIP）。不可见底稿静默返回 False（从 manifest 中
    剔除，不泄露存在性）；wp_id 缺失/非法返回 False。``entry_family`` 仅用于审计/限流归类。
    """

    async def _visible(wp_id: str | UUID | None, sheet_code: str | None) -> bool:
        wid = _coerce_uuid(wp_id)
        if wid is None:
            return False
        ctx = await try_gate_wp(
            db,
            current_user,
            entrypoint=entrypoint,
            action=action,
            method=method,
            wp_id=wid,
            requested_sheet_key=sheet_code,
            entry_kind=entry_kind,
            entry_family=entry_family,
        )
        return ctx is not None

    return _visible


def make_bulk_preflight(
    db: AsyncSession,
    current_user,
    *,
    entrypoint: str = "workpaper.import",
    action: str = "import_data",
    method: str = "POST",
    entry_kind: str = "http",
    entry_family: str = "bulk",
    responder: DenialResponder | None = None,
) -> Callable[[str | UUID | None, str | None], Awaitable[None]]:
    """构造 import/write 逐资源 preflight 闭包：返回 ``async (wp_id, sheet_code) -> None``。

    显式请求的任一资源被拒 → 抛 ``ExternalNotFound``（404），由调用方在 **任何副作用前** 传播 →
    整请求失败（原子）。不 fail-soft 跳过，不泄露存在性（统一 404）。wp_id 缺失/非法 → 拒绝。
    """

    async def _preflight(wp_id: str | UUID | None, sheet_code: str | None) -> None:
        wid = _coerce_uuid(wp_id)
        resp = responder if responder is not None else DenialResponder()
        if wid is None:
            await resp.deny(
                reason=DenialReason.not_found,
                entrypoint=entrypoint,
                entry_family=entry_family,
                http_method=method,
                action=action,
                actor_user_id=getattr(current_user, "id", None),
            )
        await gate_wp(
            db,
            current_user,
            entrypoint=entrypoint,
            action=action,
            method=method,
            wp_id=wid,
            requested_sheet_key=sheet_code,
            entry_kind=entry_kind,
            entry_family=entry_family,
            responder=resp,
        )

    return _preflight


def _coerce_uuid(value: str | UUID | None) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None
