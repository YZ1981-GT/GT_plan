"""ProjectYearScopeGuard — 项目/年度信任边界（Task 3.1, Wave 2）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R1, R3, R4, R12
Design: §3.1 信任边界, §7.2 稳定失败类别
Properties: P1 (项目隔离)

信任边界铁律（design §3.1）：

1. 客户端提供的 ``project_id/audit_year/role/path/target_id`` 均不可信；对象归属
   **从数据库对象关系重新解析**（``resolve_object_scope``）。
2. scope（+ capability）校验 **先于** 目标名称、路径、``stat/open/read`` 或任何字节 IO。
   本 guard 只做 scope 判定，不触碰文件；facade 保证 guard 在业务 IO 之前运行。
3. 不存在与无权访问对外使用 **同一脱敏错误** ``SCOPE_NOT_FOUND_OR_FORBIDDEN``
   （不泄露路径、目标客户、项目或对象名称，design §7.2）。

成员判定复用既有项目成员模型（``project_users``），与 ``deps.require_project_access``
口径一致：admin/partner 视为全项目可读写；其余角色须为项目成员（未软删）。Service
Identity 的 scope 由其执行的已批准任务限定——本 guard 要求 service actor 显式携带被授权
的 project_id（调用方在 enqueue 任务时绑定），并同样要求对象归属一致。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)

# 系统角色中天然具备全项目可见性的角色（与 deps.get_visible_project_ids 一致）。
_GLOBAL_VISIBILITY_ROLES: frozenset[str] = frozenset({"admin", "partner"})


@dataclass(frozen=True)
class ObjectScope:
    """从数据库重新解析出的对象权威 scope。"""

    project_id: uuid.UUID
    audit_year: int | None


# ---------------------------------------------------------------------------
# 对象权威 scope 数据源白名单（表名/列名来自受控字典，非用户输入 → 无注入面）。
# 每项：object_type -> (table, id_column, project_column, year_column|None, active_predicate|None)
# ---------------------------------------------------------------------------
_OBJECT_SCOPE_SOURCES: dict[str, tuple[str, str, str, str | None, str | None]] = {
    "attachment": ("attachments", "id", "project_id", "audit_year", "is_deleted = false"),
    "attachment_version": ("attachment_versions", "id", "project_id", "audit_year", None),
    "upload_attempt": ("evidence_upload_attempts", "id", "project_id", "audit_year", None),
    "evidence_ref": ("evidence_refs", "id", "project_id", "audit_year", None),
    "evidence_dependency": ("evidence_dependencies", "id", "project_id", "audit_year", None),
    "ocr_job": ("ocr_jobs", "id", "project_id", "audit_year", None),
    "ocr_result": ("ocr_results", "id", "project_id", "audit_year", None),
    "ocr_writeback": ("ocr_writebacks", "id", "project_id", "audit_year", None),
    "citation_snapshot": ("citation_snapshots", "id", "project_id", "audit_year", None),
    "archive_manifest": ("archive_manifests", "id", "project_id", "audit_year", None),
    "legal_hold": ("legal_holds", "id", "project_id", "audit_year", None),
    "command_root": ("evidence_audit_command_roots", "id", "project_id", "audit_year", None),
}


class ProjectYearScopeGuard:
    """项目/年度信任边界 guard（scope-first，脱敏拒绝）。"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # -- scope 成员判定 ----------------------------------------------------

    async def authorize_scope(
        self,
        *,
        actor_role: str,
        actor: ActorContext,
        project_id: uuid.UUID,
        audit_year: int | None = None,
    ) -> None:
        """校验 actor 对请求 scope 有访问权；无权/不存在均抛脱敏
        ``SCOPE_NOT_FOUND_OR_FORBIDDEN``。

        - 人工 actor：全局可见角色（admin/partner）放行；其余须为项目成员（未软删）。
        - service actor：由其执行的已批准任务 scope 限定——调用方须已把 project_id 绑定到
          任务；本 guard 只确认项目存在（防止对不存在项目伪造 scope）。
        """
        if not await self._project_exists(project_id):
            raise self._denied()

        if actor.is_service:
            # service 的项目授权由任务编排在 enqueue 时绑定；此处只做存在性 + 后续对象归属一致。
            return

        if actor_role in _GLOBAL_VISIBILITY_ROLES:
            return

        if not await self._is_project_member(project_id, actor.actor_user_id):
            raise self._denied()

    # -- 对象归属重新解析 --------------------------------------------------

    async def resolve_object_scope(
        self, object_type: str, object_id: uuid.UUID | str
    ) -> ObjectScope | None:
        """从数据库重新解析对象权威 ``(project_id, audit_year)``；不存在返回 None。

        客户端声明的 scope 一律不采信——归属只以对象表为准（design §3.1）。
        """
        source = _OBJECT_SCOPE_SOURCES.get(object_type)
        if source is None:
            raise ValueError(f"unsupported object_type: {object_type!r}")
        table, id_col, project_col, year_col, active_pred = source

        cols = [f"{project_col} AS project_id"]
        cols.append(f"{year_col} AS audit_year" if year_col else "NULL AS audit_year")
        where = [f"{id_col} = :oid"]
        if active_pred:
            where.append(active_pred)
        stmt = sa.text(
            f"SELECT {', '.join(cols)} FROM {table} WHERE {' AND '.join(where)} LIMIT 1"
        )
        row = (await self._db.execute(stmt, {"oid": str(object_id)})).mappings().first()
        if row is None or row["project_id"] is None:
            return None
        return ObjectScope(
            project_id=uuid.UUID(str(row["project_id"])),
            audit_year=row["audit_year"],
        )

    async def authorize_object(
        self,
        *,
        actor_role: str,
        actor: ActorContext,
        object_type: str,
        object_id: uuid.UUID | str,
        requested_project_id: uuid.UUID | None = None,
        requested_year: int | None = None,
    ) -> ObjectScope:
        """重新解析对象归属并授权；返回权威 ``ObjectScope``。

        流程（全部在读取任何目标字节/路径之前）：
          1. 从 DB 解析权威 scope；不存在 → 脱敏 ``SCOPE_NOT_FOUND_OR_FORBIDDEN``。
          2. 若调用方声明了 requested_project_id/year，与权威 scope 不一致 → 同一脱敏错误
             （客户端声明的 scope 不可信）。
          3. 用权威 scope 做成员判定（``authorize_scope``）。
        """
        scope = await self.resolve_object_scope(object_type, object_id)
        if scope is None:
            raise self._denied()

        if requested_project_id is not None and requested_project_id != scope.project_id:
            raise self._denied()
        if (
            requested_year is not None
            and scope.audit_year is not None
            and requested_year != scope.audit_year
        ):
            raise self._denied()

        await self.authorize_scope(
            actor_role=actor_role,
            actor=actor,
            project_id=scope.project_id,
            audit_year=scope.audit_year,
        )
        return scope

    # -- 内部 --------------------------------------------------------------

    async def _project_exists(self, project_id: uuid.UUID) -> bool:
        row = (
            await self._db.execute(
                sa.text(
                    "SELECT 1 FROM projects WHERE id = :pid "
                    "AND COALESCE(is_deleted, false) = false LIMIT 1"
                ),
                {"pid": str(project_id)},
            )
        ).first()
        return row is not None

    async def _is_project_member(
        self, project_id: uuid.UUID, user_id: uuid.UUID | None
    ) -> bool:
        if user_id is None:
            return False
        row = (
            await self._db.execute(
                sa.text(
                    "SELECT 1 FROM project_users WHERE project_id = :pid "
                    "AND user_id = :uid AND is_deleted = false LIMIT 1"
                ),
                {"pid": str(project_id), "uid": str(user_id)},
            )
        ).first()
        return row is not None

    @staticmethod
    def _denied() -> EvidenceGovernanceError:
        return EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "scope not found or forbidden",
        )
