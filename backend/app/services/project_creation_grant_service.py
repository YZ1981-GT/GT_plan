"""精确 USCC 的经理建项授权、计划快照与管理操作。"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import ProjectUser, User
from app.models.project_creation_grant_models import ProjectCreationGrant
from app.services.uscc_validator import normalize_uscc_input, validate_uscc

GRANT_DENIED_CODE = "COMPANY_CREATION_NOT_AUTHORIZED"
_ROLE_BYPASS = frozenset({"admin", "partner"})


class ProjectCreationGrantStale(RuntimeError):
    """计划引用的授权已撤销、过期或改变。"""


def _role_value(actor: Any | None) -> str | None:
    role = getattr(actor, "role", None)
    return getattr(role, "value", role)


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def normalize_company_code(value: object) -> str:
    """授权判断与入库值同口径（R1.3）：先经统一规范化（NFKC → strip → upper）再校验。

    规范化为空（None / 空串 / 全空白）时仍以空串进入 ``validate_uscc``，报 422
    「统一社会信用代码必须为 18 位」；不得直接返回 None，否则空值不再被拒绝。
    """
    code = normalize_uscc_input(value) or ""
    valid, reason = validate_uscc(code)
    if not valid:
        raise HTTPException(status_code=422, detail=reason or "统一社会信用代码格式错误")
    return code


def required_creation_codes(rows: Iterable[Any]) -> set[str]:
    """manager 创建前必须获准查询/创建的精确企业代码。"""
    codes: set[str] = set()
    for row in rows:
        if getattr(row, "action", None) != "create":
            continue
        for raw in (
            getattr(row, "company_code", None),
            getattr(row, "parent_company_code", None),
            getattr(row, "ultimate_company_code", None),
        ):
            if raw:
                codes.add(normalize_company_code(raw))
    return codes


def _codes_digest(codes: Iterable[str]) -> str:
    body = "\x1f".join(sorted(set(codes))).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


async def _audit(
    actor: Any,
    action: str,
    *,
    codes: Iterable[str],
    entrypoint: str,
    extra: dict[str, Any] | None = None,
) -> None:
    try:
        from app.services.audit_logger_enhanced import audit_logger

        code_set = sorted(set(codes))
        await audit_logger.log_action(
            user_id=actor.id,
            action=action,
            object_type="project_creation_grant",
            details={
                "company_codes_sha256": _codes_digest(code_set),
                "company_code_count": len(code_set),
                "entrypoint": entrypoint,
                "actor_role": _role_value(actor),
                **(extra or {}),
            },
        )
    except Exception:
        # 审计是纵深防御；失败不能把授权放宽，也不能污染主事务。
        return


def _snapshot(grant: ProjectCreationGrant) -> dict[str, Any]:
    return {
        "id": str(grant.id),
        "company_code": grant.company_code,
        "version": grant.version,
        "valid_until": grant.valid_until.isoformat() if grant.valid_until else None,
    }


async def authorize_creation_codes(
    db: AsyncSession,
    actor: Any | None,
    codes: Iterable[str],
    *,
    entrypoint: str,
) -> list[dict[str, Any]]:
    """在任何项目库存查询前授权；返回供持久计划使用的 grant 快照。"""
    required = sorted({normalize_company_code(code) for code in codes})
    if not required or actor is None:
        return []
    role = _role_value(actor)
    if role in _ROLE_BYPASS:
        return []
    if role != "manager":
        await _audit(actor, "project.creation.denied", codes=required, entrypoint=entrypoint)
        raise HTTPException(
            status_code=403,
            detail={"error_code": GRANT_DENIED_CODE, "message": "当前角色无项目创建权限"},
        )
    now = datetime.now(timezone.utc)
    rows = list((await db.execute(sa.select(ProjectCreationGrant).where(
        ProjectCreationGrant.grantee_user_id == actor.id,
        ProjectCreationGrant.company_code.in_(required),
        ProjectCreationGrant.is_deleted == sa.false(),
        ProjectCreationGrant.valid_from <= now,
        sa.or_(ProjectCreationGrant.valid_until.is_(None), ProjectCreationGrant.valid_until > now),
    ))).scalars().all())
    by_code = {row.company_code: row for row in rows}
    missing = [code for code in required if code not in by_code]
    if missing:
        await _audit(actor, "project.creation.denied", codes=required, entrypoint=entrypoint,
                     extra={"missing_count": len(missing)})
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": GRANT_DENIED_CODE,
                "message": f"有 {len(missing)} 个企业代码暂无建项授权，请联系管理员授权",
            },
        )
    return [_snapshot(by_code[code]) for code in required]


async def _locked_actor_role(db: AsyncSession, actor: Any) -> str | None:
    """共享锁冻结 active/role，并用标量列绕过 Session identity map 的旧对象。"""
    role = _role_value(actor)
    if not isinstance(actor, User):
        return role
    current = (await db.execute(
        sa.select(User.role, User.is_active, User.is_deleted)
        .where(User.id == actor.id)
        .with_for_update(read=True)
    )).one_or_none()
    if current is None:
        raise ProjectCreationGrantStale("建项用户状态或角色已变化")
    current_role = getattr(current.role, "value", current.role)
    if (
        current.is_deleted or not current.is_active
        or current_role != role
    ):
        raise ProjectCreationGrantStale("建项用户状态或角色已变化")
    return str(current_role)


async def lock_actor_and_project_memberships(
    db: AsyncSession,
    actor: Any,
    project_ids: Iterable[UUID],
) -> None:
    """冻结操作者安全属性及其现有项目成员行，随后权限重验才可用于写路径。

    只有 admin 绕过项目成员判定；partner 的建项授权可直通，但项目级权限仍依赖成员行，
    因此必须同样加锁，否则撤权可穿过“权限检查 → 写入”窗口。
    """
    role = await _locked_actor_role(db, actor)
    ids = sorted(set(project_ids), key=str)
    if not ids or role == "admin":
        return
    await db.execute(
        sa.select(ProjectUser.id)
        .where(
            ProjectUser.user_id == actor.id,
            ProjectUser.project_id.in_(ids),
            ProjectUser.is_deleted == sa.false(),
        )
        .order_by(ProjectUser.project_id)
        .with_for_update(read=True)
    )


async def lock_and_revalidate_creation_codes(
    db: AsyncSession,
    actor: Any,
    codes: Iterable[str],
    *,
    expected_snapshots: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """年度锁后冻结 actor→grant，并按当前时间/可选计划快照重验。"""
    required = sorted({normalize_company_code(code) for code in codes})
    role = await _locked_actor_role(db, actor)
    if not required or role in _ROLE_BYPASS:
        return []
    if role != "manager":
        raise ProjectCreationGrantStale("建项角色已变化")
    grants = list((await db.execute(
        sa.select(ProjectCreationGrant)
        .where(
            ProjectCreationGrant.grantee_user_id == actor.id,
            ProjectCreationGrant.company_code.in_(required),
            ProjectCreationGrant.is_deleted == sa.false(),
        )
        .order_by(ProjectCreationGrant.id)
        .with_for_update(read=True)
    )).scalars().all())
    current = {grant.company_code: grant for grant in grants}
    now = datetime.now(timezone.utc)
    if set(current) != set(required):
        raise ProjectCreationGrantStale("建项授权已撤销或不存在")
    snapshots = [_snapshot(current[code]) for code in required]
    for grant in grants:
        if (
            grant.revoked_at is not None
            or _aware(grant.valid_from) > now
            or (grant.valid_until is not None and _aware(grant.valid_until) <= now)
        ):
            raise ProjectCreationGrantStale("建项授权已撤销或过期")
    if expected_snapshots is not None:
        expected = {
            str(item.get("company_code") or ""): item
            for item in expected_snapshots if isinstance(item, dict)
        }
        if set(expected) != set(required):
            raise ProjectCreationGrantStale("计划建项授权范围不匹配")
        for snapshot in snapshots:
            old = expected[snapshot["company_code"]]
            if (
                old.get("id") != snapshot["id"]
                or old.get("version") != snapshot["version"]
                or old.get("valid_until") != snapshot["valid_until"]
            ):
                raise ProjectCreationGrantStale("建项授权已改变")
    return snapshots


async def revalidate_plan_grants(
    db: AsyncSession,
    actor: Any,
    rows: Iterable[Any],
    dependencies: dict[str, Any],
) -> None:
    """锁定并重验预校验时的授权；角色降级或 grant 漂移均 fail-closed。"""
    required = required_creation_codes(rows)
    if not required or actor is None:
        return
    raw = dependencies.get("creation_grants")
    if not isinstance(raw, list):
        raise ProjectCreationGrantStale("计划缺少建项授权基线")
    await lock_and_revalidate_creation_codes(
        db, actor, required, expected_snapshots=raw,
    )


async def _manager(db: AsyncSession, manager_user_id: UUID, *, lock: bool = False) -> User:
    stmt = sa.select(User).where(User.id == manager_user_id)
    if lock:
        stmt = stmt.with_for_update()
    user = (await db.execute(stmt)).scalar_one_or_none()
    if (
        user is None or user.is_deleted or not user.is_active
        or _role_value(user) != "manager"
    ):
        raise HTTPException(status_code=422, detail="授权对象必须是已启用的现场经理")
    return user


async def list_grants(
    db: AsyncSession,
    *,
    manager_user_id: UUID | None = None,
) -> list[dict[str, Any]]:
    stmt = sa.select(ProjectCreationGrant).where(ProjectCreationGrant.is_deleted == sa.false())
    if manager_user_id is not None:
        stmt = stmt.where(ProjectCreationGrant.grantee_user_id == manager_user_id)
    grants = list((await db.execute(stmt.order_by(
        ProjectCreationGrant.grantee_user_id, ProjectCreationGrant.company_code
    ))).scalars().all())
    user_ids = {
        value for grant in grants for value in (grant.grantee_user_id, grant.granted_by) if value
    }
    users = list((await db.execute(sa.select(User).where(User.id.in_(user_ids)))).scalars().all()) if user_ids else []
    names = {user.id: user.username for user in users}
    usable_managers = {
        user.id for user in users
        if not user.is_deleted and user.is_active and _role_value(user) == "manager"
    }
    now = datetime.now(timezone.utc)

    def status_of(grant: ProjectCreationGrant) -> str:
        # 授权门按当前账号状态 fail-closed；列表必须同口径展示，不能把失效授权显示成有效。
        if grant.grantee_user_id not in usable_managers:
            return "suspended"
        if grant.valid_until and _aware(grant.valid_until) <= now:
            return "expired"
        return "active"

    return [
        {
            "id": str(grant.id),
            "manager_user_id": str(grant.grantee_user_id),
            "manager_username": names.get(grant.grantee_user_id, ""),
            "company_code": grant.company_code,
            "valid_from": grant.valid_from.isoformat(),
            "valid_until": grant.valid_until.isoformat() if grant.valid_until else None,
            "version": grant.version,
            "source": grant.source,
            "reason": grant.reason,
            "granted_by": str(grant.granted_by) if grant.granted_by else None,
            "granted_by_username": names.get(grant.granted_by, "") if grant.granted_by else "系统回填",
            "status": status_of(grant),
            "created_at": grant.created_at.isoformat() if grant.created_at else None,
        }
        for grant in grants
    ]


async def grant_many(
    db: AsyncSession,
    *,
    manager_user_id: UUID,
    company_codes: Iterable[str],
    valid_until: datetime | None,
    reason: str,
    actor: Any,
) -> list[ProjectCreationGrant]:
    await _manager(db, manager_user_id, lock=True)
    codes = sorted({normalize_company_code(code) for code in company_codes})
    if not codes or len(codes) > 500:
        raise HTTPException(status_code=422, detail="每次须授权 1-500 个企业代码")
    cleaned_reason = str(reason or "").strip()
    if not 3 <= len(cleaned_reason) <= 500:
        raise HTTPException(status_code=422, detail="授权原因须为 3-500 个字符")
    now = datetime.now(timezone.utc)
    if valid_until is not None:
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=timezone.utc)
        if valid_until <= now:
            raise HTTPException(status_code=422, detail="授权到期时间必须晚于当前时间")
    existing_rows = list((await db.execute(
        sa.select(ProjectCreationGrant)
        .where(
            ProjectCreationGrant.grantee_user_id == manager_user_id,
            ProjectCreationGrant.company_code.in_(codes),
            ProjectCreationGrant.is_deleted == sa.false(),
        )
        .order_by(ProjectCreationGrant.company_code)
        .with_for_update()
    )).scalars().all())
    by_code = {grant.company_code: grant for grant in existing_rows}
    results: list[ProjectCreationGrant] = []
    for code in codes:
        grant = by_code.get(code)
        if grant is not None:
            unchanged = (
                grant.revoked_at is None
                and _aware(grant.valid_until) == _aware(valid_until)
                and grant.reason == cleaned_reason
                and _aware(grant.valid_from) <= now
                and (grant.valid_until is None or _aware(grant.valid_until) > now)
            )
            if not unchanged:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error_code": "PROJECT_CREATION_GRANT_CONFLICT",
                        "message": "该企业代码已有不同版本的有效授权，请刷新后先撤销",
                    },
                )
            results.append(grant)
            continue
        grant = ProjectCreationGrant(
            grantee_user_id=manager_user_id,
            company_code=code,
            valid_from=now,
            valid_until=valid_until,
            source="admin",
            reason=cleaned_reason,
            granted_by=actor.id,
        )
        db.add(grant)
        results.append(grant)
    await db.flush()
    return results


async def revoke_grant(
    db: AsyncSession,
    *,
    grant_id: UUID,
    expected_version: int,
    reason: str,
    actor: Any,
) -> ProjectCreationGrant:
    grantee_id = await db.scalar(sa.select(ProjectCreationGrant.grantee_user_id).where(
        ProjectCreationGrant.id == grant_id
    ))
    if grantee_id is None:
        raise HTTPException(status_code=404, detail="建项授权不存在或已撤销")
    # 全部授权生命周期写统一 users→grant 锁序，避免与创建的共享锁形成死锁。
    await db.execute(sa.select(User.id).where(User.id == grantee_id).with_for_update())
    grant = (await db.execute(
        sa.select(ProjectCreationGrant)
        .where(ProjectCreationGrant.id == grant_id)
        .with_for_update()
    )).scalar_one_or_none()
    if grant is None or grant.is_deleted:
        raise HTTPException(status_code=404, detail="建项授权不存在或已撤销")
    if grant.version != expected_version:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "PROJECT_CREATION_GRANT_STALE",
                "message": "建项授权已被其他管理员修改，请刷新后重试",
            },
        )
    cleaned_reason = str(reason or "").strip()
    if not 3 <= len(cleaned_reason) <= 500:
        raise HTTPException(status_code=422, detail="撤销原因须为 3-500 个字符")
    now = datetime.now(timezone.utc)
    grant.is_deleted = True
    grant.deleted_at = now
    grant.revoked_at = now
    grant.revoked_by = actor.id
    grant.version += 1
    await db.flush()
    return grant


async def audit_grant_change(
    actor: Any,
    *,
    action: str,
    codes: Iterable[str],
    manager_user_id: UUID,
    reason: str,
) -> None:
    await _audit(
        actor,
        action,
        codes=codes,
        entrypoint="admin_grant_management",
        extra={
            "manager_user_id": str(manager_user_id),
            "reason": str(reason).strip()[:500],
        },
    )


__all__ = [
    "GRANT_DENIED_CODE",
    "ProjectCreationGrantStale",
    "audit_grant_change",
    "authorize_creation_codes",
    "grant_many",
    "list_grants",
    "lock_actor_and_project_memberships",
    "normalize_company_code",
    "required_creation_codes",
    "revalidate_plan_grants",
    "revoke_grant",
]
