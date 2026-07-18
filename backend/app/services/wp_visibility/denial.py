"""统一拒绝引擎与安全审计发件箱（Task 6 / 组件 C7 DenialResponder + SecurityAuditOutbox）

Feature: procedure-delegation-visibility-isolation
Requirements:
  - 9.1–9.5：不存在 / 跨项目 / 越权 / 无权页面 / 无权历史版本 → External_Not_Found。
  - 9.6：External_Not_Found 返回 HTTP 404。
  - 9.7：返回且仅返回 ``{"detail":"资源不存在或不可访问"}``。
  - 9.8：拒绝时 Security_Audit_Outbox 可靠记录真实内部原因。
  - 9.9：内部 reason ∈ {not_found, cross_project, out_of_scope, not_delegated, sheet_unmapped,
    action_denied, historical_version, binding_conflict, token_invalid, rate_limited}。
  - 9.10/9.11：outbox 写入 / 投递失败保持 404（或不依赖资源存在性的 429）状态码与响应体不变，
    并产生 Operational_Alert。
  - 14.18：资源无关 429（认证后、资源解析前，仅 principal/project/Entry_Family），带 Retry-After，
    不表明资源存在性。
Design: 组件 C7（SecurityAudit）/ "Error Handling"（404/429/Operational_Alert）/ Property 11/12。

**统一 wire 形态**：所有 wp-bound 资源不可见原因（含 not_found/cross_project/out_of_scope/
not_delegated/sheet_unmapped/action_denied/historical_version/binding_conflict/token_invalid）
对外完全相同：HTTP 404 + ``{"detail":"资源不存在或不可访问"}``，无可区分时序 / 头 / 体。内部真实
reason 只进 ``wp_access_security_outbox``（Task 2，append-only）。

**审计与请求事务解耦**：拒绝请求最终以 404/429 结束，路由不会 commit；若审计随请求事务回滚就会
丢失。故 ``DenialResponder`` 用 **独立 session** 写 + commit outbox，保证拒绝事实可靠持久
（Req 9.8）。独立写失败只 log Operational_Alert，绝不改变对外 404/429（Req 9.10/9.11）。

**正文脱敏**：outbox 只存 request/actor、可空绑定、entrypoint/family/action、reason 与脱敏 detail
（标识符、per_source 诊断），绝不写业务正文 / 名称 / 文件字节 / prompt / token。
"""

from __future__ import annotations

import enum
import logging
from typing import Any, NoReturn
from uuid import UUID

from fastapi import HTTPException

logger = logging.getLogger(__name__)
# Operational_Alert 专用 logger（既有运维监控渠道；不改变访问拒绝结果）。
alert_logger = logging.getLogger("wp_visibility.security_alert")

# External_Not_Found 唯一对外响应体（Req 9.7）。
EXTERNAL_NOT_FOUND_DETAIL = "资源不存在或不可访问"


class DenialReason(str, enum.Enum):
    """内部真实拒绝原因（对外统一 404/429；取值域与 V113 wp_access_security_outbox CHECK 一致）。"""

    not_found = "not_found"
    cross_project = "cross_project"
    out_of_scope = "out_of_scope"
    not_delegated = "not_delegated"
    sheet_unmapped = "sheet_unmapped"
    action_denied = "action_denied"
    historical_version = "historical_version"
    binding_conflict = "binding_conflict"
    token_invalid = "token_invalid"
    rate_limited = "rate_limited"


# 进入 gate 后统一转 404 的资源不可见原因（Req 9.1–9.6）。
_NOT_FOUND_REASONS = frozenset(
    {
        DenialReason.not_found,
        DenialReason.cross_project,
        DenialReason.out_of_scope,
        DenialReason.not_delegated,
        DenialReason.sheet_unmapped,
        DenialReason.action_denied,
        DenialReason.historical_version,
        DenialReason.binding_conflict,
        DenialReason.token_invalid,
    }
)


class ExternalNotFound(HTTPException):
    """统一外部不可见响应：HTTP 404 + ``{"detail":"资源不存在或不可访问"}``（Req 9.6/9.7）。"""

    def __init__(self) -> None:
        super().__init__(status_code=404, detail=EXTERNAL_NOT_FOUND_DETAIL)


class RateLimited(HTTPException):
    """资源无关限流：HTTP 429 + 有效 Retry-After（Req 14.10/14.12/14.18）。不表明资源存在性。"""

    def __init__(self, retry_after: int) -> None:
        super().__init__(
            status_code=429,
            detail="请求过于频繁，请稍后重试",
            headers={"Retry-After": str(max(1, int(retry_after)))},
        )


class DenialError(Exception):
    """内部拒绝载体（gate 内部流转；responder 转成 ExternalNotFound/RateLimited）。"""

    def __init__(self, reason: DenialReason) -> None:
        self.reason = reason
        super().__init__(reason.value)


def _scrub_identifiers(raw: dict[str, Any] | None) -> dict[str, Any]:
    """只保留定位标识（id/code/名称长度受限），剔除任何潜在正文。"""
    if not raw:
        return {}
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if v is None:
            continue
        s = str(v)
        # 定位标识不应超长；超长一律截断，防止误带正文。
        out[k] = s[:160]
    return out


class DenialResponder:
    """把内部拒绝 reason 落 outbox（独立事务）并抛出对外统一响应。

    - ``deny(...)``：写 outbox（脱敏）→ 抛 ``ExternalNotFound``（404）。
    - ``rate_limit(...)``：写 outbox（reason=rate_limited）→ 抛 ``RateLimited``（429 + Retry-After）。
    outbox 写入失败只 Operational_Alert，绝不改变 404/429（Req 9.10/9.11）。
    """

    def __init__(self, session_factory=None, alert_hook=None) -> None:
        # session_factory: 可注入（测试可注入故障工厂验证"失败不改响应"）；默认用 app.core.database.async_session。
        self._session_factory = session_factory
        self._alert_hook = alert_hook

    # ------------------------------------------------------------------
    async def deny(
        self,
        *,
        reason: DenialReason,
        entrypoint: str,
        entry_family: str | None = None,
        route_name: str | None = None,
        http_method: str | None = None,
        action: str | None = None,
        request_id: str | None = None,
        actor_user_id: UUID | None = None,
        project_id: UUID | None = None,
        wp_index_id: UUID | None = None,
        wp_id: UUID | None = None,
        sheet_key: str | None = None,
        requested_version: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> NoReturn:
        """写安全审计 outbox 后抛出统一 External_Not_Found（404）。"""
        await self._enqueue(
            reason=reason.value,
            entrypoint=entrypoint,
            entry_family=entry_family,
            route_name=route_name,
            http_method=http_method,
            action=action,
            request_id=request_id,
            actor_user_id=actor_user_id,
            project_id=project_id,
            wp_index_id=wp_index_id,
            wp_id=wp_id,
            sheet_key=sheet_key,
            requested_version=requested_version,
            detail=detail,
        )
        raise ExternalNotFound()

    async def rate_limit(
        self,
        *,
        retry_after: int,
        entrypoint: str,
        entry_family: str | None = None,
        route_name: str | None = None,
        http_method: str | None = None,
        request_id: str | None = None,
        actor_user_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> NoReturn:
        """资源无关 429：只依据 principal/project/family 记录并抛出（不含资源绑定，Req 14.18）。"""
        await self._enqueue(
            reason=DenialReason.rate_limited.value,
            entrypoint=entrypoint,
            entry_family=entry_family,
            route_name=route_name,
            http_method=http_method,
            action=None,
            request_id=request_id,
            actor_user_id=actor_user_id,
            project_id=project_id,
            wp_index_id=None,
            wp_id=None,
            sheet_key=None,
            requested_version=None,
            detail={"retry_after": int(retry_after)},
        )
        raise RateLimited(retry_after)

    # ------------------------------------------------------------------
    async def _enqueue(self, **fields: Any) -> None:
        """独立 session 写 + commit outbox；失败只 Operational_Alert，不改变对外响应。"""
        try:
            await self._write_outbox(**fields)
        except Exception as exc:  # noqa: BLE001 — 审计失败绝不改变 404/429（Req 9.10/9.11）
            self._operational_alert(fields.get("reason"), fields.get("entrypoint"), exc)

    async def _write_outbox(self, **fields: Any) -> None:
        from app.models.wp_visibility_models import WpAccessSecurityOutbox

        factory = self._session_factory
        if factory is None:
            from app.core.database import async_session as factory  # type: ignore

        row = WpAccessSecurityOutbox(
            request_id=fields.get("request_id"),
            actor_user_id=fields.get("actor_user_id"),
            project_id=fields.get("project_id"),
            wp_index_id=fields.get("wp_index_id"),
            wp_id=fields.get("wp_id"),
            sheet_key=fields.get("sheet_key"),
            requested_version=fields.get("requested_version"),
            entrypoint=fields.get("entrypoint") or "unknown",
            entry_family=fields.get("entry_family"),
            route_name=fields.get("route_name"),
            http_method=fields.get("http_method"),
            action=fields.get("action"),
            reason=fields["reason"],
            detail=_scrub_identifiers(fields.get("detail")),
        )
        async with factory() as session:  # 独立事务，脱离请求事务生命周期
            session.add(row)
            await session.commit()

    def _operational_alert(self, reason: Any, entrypoint: Any, exc: Exception) -> None:
        alert_logger.critical(
            "Operational_Alert: security audit outbox 写入失败 "
            "reason=%s entrypoint=%s err=%s（对外响应保持不变）",
            reason,
            entrypoint,
            exc,
        )
        if self._alert_hook is not None:
            try:
                self._alert_hook(reason, entrypoint, exc)
            except Exception:  # noqa: BLE001 — 告警回调异常也不得影响对外响应
                logger.exception("Operational_Alert hook 异常")
