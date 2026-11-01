"""经理精确 USCC 建项授权、计划快照与并发重验。

安全顺序：首次授权校验必须早于项目库存查询；真正写入前再在年度拓扑锁内锁定 actor、
授权和项目成员行，并按当前时间重验。授权变化统一抛 ``ProjectCreationGrantStale``，
由调用方映射为不泄露库存信息的 409。

spec: batch-project-authorization-and-lock-hardening R1/R2
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import ProjectUser, User
from app.models.project_creation_grant_models import ProjectCreationGrant
from app.services.uscc_validator import validate_uscc

logger = logging.getLogger(__name__)
_ROLE_BYPASS = {"admin", "partner"}


class ProjectCreationGrantStale(Exception):
    """actor、授权或成员基线在预校验后发生变化。"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _role_value(value: Any) -> str:
    role = getattr(value, "role", value)
    return str(getattr(role, "value", role) or "")


def _normalise_codes(codes: Iterable[Any]) -> list[str]:
    out: set[str] = set()
    for raw in codes:
        code = str(raw or "").strip().upper()
        if not code:
            continue
        valid, reason = validate_uscc(code)
        if not valid:
            raise HTTPException(status_code=422, detail=reason or "统一社会信用代码格式错误")
        out.add(code)
    return sorted(out)


def _is_effective(grant: ProjectCreationGrant, now: datetime) -> bool:
    start = _aware(grant.valid_from)
    end = _aware(grant.valid_until)
    return (
        not grant.is_deleted
        and grant.revoked_at is None
        and (start is None or start <= now)
        and (end is None or end > now)
    )


def _snapshot(grant: ProjectCreationGrant) -> dict[str, Any]:
    return {
        "id": str(grant.id),
        "company_code": grant.company_code,
        "version": int(grant.version),
        "valid_until": _aware(grant.valid_until).isoformat() if grant.valid_until else None,
    }


def _snapshot_map(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, list):
        raise ProjectCreationGrantStale("建项授权快照缺失")
    out: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ProjectCreationGrantStale("建项授权快照格式无效")
        code = str(item.get("company_code") or "").strip().upper()
        try:
            UUID(str(item.get("id")))
            version = int(item.get("version"))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ProjectCreationGrantStale("建项授权快照格式无效") from exc
        if not code or version < 1 or code in out:
            raise ProjectCreationGrantStale("建项授权快照格式无效")
        out[code] = item
    return out


def required_creation_codes(rows: Iterable[Any]) -> set[str]:
    """返回 create 行涉及的 company / parent / ultimate 精确代码集合。"""
    return {
        str(code).strip().upper()
        for row in rows
        if str(getattr(row, "action", "create")) == "create"
        for code in (
            getattr(row, "company_code", None),
            getattr(row, "parent_company_code", None),
            getattr(row, "ultimate_company_code", None),
        )
        if str(code or "").strip()
    }


async def _audit_denied(actor: Any, codes: Sequence[str], entrypoint: str) -> None:
    """拒绝审计只存代码集合摘要，普通日志不得出现原始 USCC。"""
    try:
        from app.services.audit_logger_enhanced import audit_logger

        digest = hashlib.sha256("\n".join(sorted(codes)).encode("utf-8")).hexdigest()
        await audit_logger.log_action(
            getattr(actor, "id", None),
            action="project.creation_grant.denied",
            object_type="project_creation_grant",
            details={
                "code_count": len(codes),
                "codes_sha256": digest,
                "entrypoint": entrypoint,
                "actor_role": _role_value(actor),
            },
        )
    except Exception:  # noqa: BLE001 — 审计降级不能改变授权判断
        logger.exception("记录建项授权拒绝审计失败")


async def audit_grant_change(
    actor: Any,
    *,
    action: str,
    codes: Sequence[str],
    manager_user_id: UUID,
    reason: str,
) -> None:
    """授予/撤销后的最佳努力审计；只存代码摘要与数量。"""
    try:
        from app.services.audit_logger_enhanced import audit_logger

        normalised = sorted({str(code).strip().upper() for code in codes if str(code).strip()})
        digest = hashlib.sha256("\n".join(normalised).encode("utf-8")).hexdigest()
        await audit_logger.log_action(
            getattr(actor, "id", None),
            action=action,
            object_type="project_creation_grant",
            object_id=manager_user_id,
            details={
                "manager_user_id": str(manager_user_id),
                "code_count": len(normalised),
                "codes_sha256": digest,
                "reason": reason,
            },
        )
    except Exception:  # noqa: BLE001 — 主事务已经提交，审计走自己的降级队列
        logger.exception("记录建项授权变更审计失败")


async def _load_grants(
    db: AsyncSession,
    manager_user_id: UUID,
    codes: Sequence[str],
    *,
    lock: bool,
) -> list[ProjectCreationGrant]:
    if not codes:
        return []
    stmt = sa.select(ProjectCreationGrant).where(
        ProjectCreationGrant.grantee_user_id == manager_user_id,
        ProjectCreationGrant.company_code.in_(codes),
        ProjectCreationGrant.is_deleted == sa.false(),
    ).order_by(ProjectCreationGrant.company_code, ProjectCreationGrant.id)
    if lock:
        stmt = stmt.with_for_update(read=True)
    return list((await db.execute(stmt)).scalars().all())


async def authorize_creation_codes(
    db: AsyncSession,
    actor: Any | None,
    codes: Iterable[Any],
    *,
    entrypoint: str,
    lock: bool = False,
) -> list[dict[str, Any]]:
    """在任何项目库存查询前校验本次 create 所需的全部代码。"""
    normalised = _normalise_codes(codes)
    if actor is None or not normalised:
        return []
    role = _role_value(actor)
    if role in _ROLE_BYPASS:
        return []
    if role != "manager" or getattr(actor, "is_deleted", False) or getattr(actor, "is_active", True) is False:
        await _audit_denied(actor, normalised, entrypoint)
        raise HTTPException(status_code=403, detail={
            "error_code": "COMPANY_CREATION_NOT_AUTHORIZED",
            "message": "当前角色没有创建项目的权限",
        })

    now = _now()
    grants = await _load_grants(db, actor.id, normalised, lock=lock)
    effective = {grant.company_code: grant for grant in grants if _is_effective(grant, now)}
    missing_count = len(set(normalised) - set(effective))
    if missing_count:
        await _audit_denied(actor, normalised, entrypoint)
        raise HTTPException(status_code=403, detail={
            "error_code": "COMPANY_CREATION_NOT_AUTHORIZED",
            "message": f"有 {missing_count} 个企业代码暂无建项授权，请联系管理员授权",
        })
    return [_snapshot(effective[code]) for code in normalised]


async def _locked_actor_role(db: AsyncSession, actor: Any) -> str:
    """从数据库锁定并读取角色标量，不能命中 Session identity map 的旧 ORM 对象。"""
    cached_role = _role_value(actor)
    # admin 不依赖项目成员或 grant；兼容内部/SQLite 测试中未持久化的 admin actor。
    if cached_role == "admin":
        return cached_role
    stmt = sa.select(User.role, User.is_active, User.is_deleted).where(User.id == actor.id)
    if db.get_bind() is not None and db.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update(read=True)
    row = (await db.execute(stmt)).one_or_none()
    if row is None:
        raise ProjectCreationGrantStale("创建者不存在")
    actual_role = _role_value(row[0])
    if bool(row[2]) or not bool(row[1]) or actual_role != cached_role:
        raise ProjectCreationGrantStale("创建者状态或角色已变化")
    return actual_role


async def lock_and_revalidate_creation_codes(
    db: AsyncSession,
    actor: Any | None,
    codes: Iterable[Any],
    *,
    expected_snapshots: Any,
) -> list[dict[str, Any]]:
    """锁定 actor / grant 并按当前时间、ID、版本、有效期逐值重验。"""
    normalised = _normalise_codes(codes)
    if actor is None:
        return []
    role = await _locked_actor_role(db, actor)
    if role in _ROLE_BYPASS:
        if expected_snapshots not in (None, []):
            raise ProjectCreationGrantStale("角色变化后授权快照不再匹配")
        return []
    if role != "manager":
        raise ProjectCreationGrantStale("创建者角色不再允许建项")

    expected = _snapshot_map(expected_snapshots)
    if set(expected) != set(normalised):
        raise ProjectCreationGrantStale("建项授权代码集合已变化")
    now = _now()
    grants = await _load_grants(db, actor.id, normalised, lock=True)
    effective = {grant.company_code: grant for grant in grants if _is_effective(grant, now)}
    if set(effective) != set(normalised):
        raise ProjectCreationGrantStale("建项授权已撤销或过期")
    current = [_snapshot(effective[code]) for code in normalised]
    for item in current:
        old = expected[item["company_code"]]
        if (
            str(old.get("id")) != item["id"]
            or int(old.get("version", 0)) != item["version"]
            or old.get("valid_until") != item["valid_until"]
        ):
            raise ProjectCreationGrantStale("建项授权版本已变化")
    return current


async def revalidate_plan_grants(
    db: AsyncSession,
    actor: Any | None,
    rows: Iterable[Any],
    dependencies: dict[str, Any],
) -> None:
    """按持久计划中的 grant 快照重验 create 行授权。"""
    if not isinstance(dependencies, dict):
        raise ProjectCreationGrantStale("计划授权基线无效")
    await lock_and_revalidate_creation_codes(
        db,
        actor,
        required_creation_codes(rows),
        expected_snapshots=dependencies.get("creation_grants"),
    )


async def lock_actor_and_project_memberships(
    db: AsyncSession,
    actor: Any | None,
    project_ids: Iterable[UUID],
) -> None:
    """冻结非 admin 创建者及其项目成员行，权限判定须紧随其后。"""
    if actor is None or _role_value(actor) == "admin":
        return
    await _locked_actor_role(db, actor)
    ids = sorted({UUID(str(value)) for value in project_ids}, key=str)
    if not ids:
        return
    stmt = sa.select(ProjectUser.id).where(
        ProjectUser.user_id == actor.id,
        ProjectUser.project_id.in_(ids),
        ProjectUser.is_deleted == sa.false(),
    )
    if db.get_bind() is not None and db.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update(read=True)
    await db.execute(stmt)


async def grant_many(
    db: AsyncSession,
    *,
    manager_user_id: UUID,
    company_codes: Iterable[Any],
    valid_until: datetime | None,
    reason: str,
    actor: Any,
) -> list[ProjectCreationGrant]:
    """批量授予；有效授权重复请求幂等，过期/撤销后新建一条新 ID。只 flush。"""
    codes = _normalise_codes(company_codes)
    if not codes:
        raise HTTPException(status_code=422, detail="请至少提供一个企业代码")
    now = _now()
    until = _aware(valid_until)
    if until is not None and until <= now:
        raise HTTPException(status_code=422, detail="授权有效期必须晚于当前时间")
    reason = str(reason or "").strip()
    if len(reason) < 3:
        raise HTTPException(status_code=422, detail="授权原因至少填写 3 个字符")

    target_stmt = sa.select(User).where(User.id == manager_user_id).with_for_update()
    target = (await db.execute(target_stmt)).scalar_one_or_none()
    if (
        target is None
        or target.is_deleted
        or not target.is_active
        or _role_value(target) != "manager"
    ):
        raise HTTPException(status_code=422, detail="授权目标必须是已启用的现场经理")

    existing = await _load_grants(db, manager_user_id, codes, lock=True)
    by_code = {grant.company_code: grant for grant in existing}
    result: list[ProjectCreationGrant] = []
    for code in codes:
        grant = by_code.get(code)
        if grant is not None and _is_effective(grant, now):
            result.append(grant)
            continue
        if grant is not None:
            # 过期行仍占活动唯一索引；封存旧行后新建，旧计划因 ID 变化必 stale。
            grant.is_deleted = True
            grant.deleted_at = now
            grant.revoked_at = grant.revoked_at or now
            grant.revoked_by = getattr(actor, "id", None)
            grant.version = int(grant.version) + 1
            grant.updated_at = now
            await db.flush()
        fresh = ProjectCreationGrant(
            grantee_user_id=manager_user_id,
            company_code=code,
            valid_from=now,
            valid_until=until,
            source="admin",
            reason=reason,
            granted_by=getattr(actor, "id", None),
        )
        db.add(fresh)
        result.append(fresh)
    await db.flush()
    return result


async def revoke_grant(
    db: AsyncSession,
    *,
    grant_id: UUID,
    expected_version: int,
    reason: str,
    actor: Any,
) -> ProjectCreationGrant:
    """按版本 CAS 撤销一条活动授权。只 flush。"""
    grant = (await db.execute(
        sa.select(ProjectCreationGrant).where(
            ProjectCreationGrant.id == grant_id,
            ProjectCreationGrant.is_deleted == sa.false(),
        ).with_for_update()
    )).scalar_one_or_none()
    if grant is None:
        raise HTTPException(status_code=404, detail="建项授权不存在或已撤销")
    if int(grant.version) != int(expected_version):
        raise HTTPException(status_code=409, detail={
            "error_code": "PROJECT_CREATION_GRANT_STALE",
            "message": "建项授权已变化，请刷新后重试",
        })
    if len(str(reason or "").strip()) < 3:
        raise HTTPException(status_code=422, detail="撤销原因至少填写 3 个字符")
    now = _now()
    grant.is_deleted = True
    grant.deleted_at = now
    grant.revoked_at = now
    grant.revoked_by = getattr(actor, "id", None)
    grant.version = int(grant.version) + 1
    grant.updated_at = now
    await db.flush()
    return grant


async def list_grants(
    db: AsyncSession,
    *,
    manager_user_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """列出未撤销授权；停用、删除或改角色账号显示 suspended。"""
    granter = sa.orm.aliased(User)
    stmt = (
        sa.select(ProjectCreationGrant, User, granter.username)
        .join(User, User.id == ProjectCreationGrant.grantee_user_id)
        .outerjoin(granter, granter.id == ProjectCreationGrant.granted_by)
        .where(ProjectCreationGrant.is_deleted == sa.false())
        .order_by(ProjectCreationGrant.created_at.desc(), ProjectCreationGrant.id)
    )
    if manager_user_id is not None:
        stmt = stmt.where(ProjectCreationGrant.grantee_user_id == manager_user_id)
    now = _now()
    rows: list[dict[str, Any]] = []
    for grant, manager, granter_name in (await db.execute(stmt)).all():
        if manager.is_deleted or not manager.is_active or _role_value(manager) != "manager":
            status = "suspended"
        elif not _is_effective(grant, now):
            status = "expired"
        else:
            status = "active"
        rows.append({
            "id": str(grant.id),
            "manager_user_id": str(grant.grantee_user_id),
            "manager_username": manager.username,
            "company_code": grant.company_code,
            "valid_from": _aware(grant.valid_from).isoformat(),
            "valid_until": _aware(grant.valid_until).isoformat() if grant.valid_until else None,
            "version": int(grant.version),
            "source": grant.source,
            "reason": grant.reason,
            "granted_by": str(grant.granted_by) if grant.granted_by else None,
            "granted_by_username": granter_name or "系统回填",
            "status": status,
            "created_at": _aware(grant.created_at).isoformat() if grant.created_at else None,
        })
    return rows


__all__ = [
    "ProjectCreationGrantStale",
    "audit_grant_change",
    "authorize_creation_codes",
    "grant_many",
    "list_grants",
    "lock_actor_and_project_memberships",
    "lock_and_revalidate_creation_codes",
    "required_creation_codes",
    "revalidate_plan_grants",
    "revoke_grant",
]
