"""单项目创建的授权、创建者归属与事务编排。"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_schemas import BasicInfoSchema
from app.models.core import Project
from app.services import project_wizard_service
from app.services.project_creation_grant_service import (
    ProjectCreationGrantStale,
    authorize_creation_codes,
    lock_and_revalidate_creation_codes,
    lock_actor_and_project_memberships,
)
from app.services.group_topology_lock import lock_topology_years
from app.services.uscc_validator import validate_uscc


async def create_project_for_actor(
    data: BasicInfoSchema,
    db: AsyncSession,
    actor: Any,
) -> Project:
    """授权必须先于项目库存查询；创建与 creator 成员在同一事务提交。"""
    for label, code in (
        ("上级企业代码", data.parent_company_code),
        ("最终控制方代码", data.ultimate_company_code),
    ):
        if not code:
            continue
        valid, reason = validate_uscc(str(code).strip().upper())
        if not valid:
            raise HTTPException(status_code=422, detail=f"{label}：{reason or '格式错误'}")
    explicit_codes = [code for code in (
        data.company_code, data.parent_company_code, data.ultimate_company_code,
    ) if code]
    snapshots = await authorize_creation_codes(
        db,
        actor,
        explicit_codes,
        entrypoint="single_project",
    )
    await lock_topology_years(db, [data.audit_year])
    try:
        # 年度锁等待之后必须按当前时间冻结显式授权，不能沿用等待前的有效期判断。
        await lock_and_revalidate_creation_codes(
            db, actor, explicit_codes, expected_snapshots=snapshots,
        )
    except ProjectCreationGrantStale as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "PROJECT_CREATION_GRANT_STALE",
                "message": "建项授权已变化，请重新提交",
            },
        ) from exc

    # 库存可为同企业另一口径或上级补齐最终控制方。补齐后必须重新授权最终代码，
    # 否则请求只授权 company/parent 也能把未授权 ultimate 写进新项目。
    from app.services.group_links import prepare_group_fields

    notices = await prepare_group_fields(
        db,
        data,
        project_id=None,
        report_scope=data.report_scope or "standalone",
        inherit=True,
    )
    final_codes = [code for code in (
        data.company_code, data.parent_company_code, data.ultimate_company_code,
    ) if code]
    final_snapshots = await authorize_creation_codes(
        db,
        actor,
        final_codes,
        entrypoint="single_project_final",
    )
    try:
        await lock_and_revalidate_creation_codes(
            db, actor, final_codes, expected_snapshots=final_snapshots,
        )
    except ProjectCreationGrantStale as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "PROJECT_CREATION_GRANT_STALE",
                "message": "建项授权已变化，请重新提交",
            },
        ) from exc

    role = actor.role.value
    if role == "manager":
        # creation grant 只允许创建，不授予既有项目读写权；先查轻量 ID，再逐项目 edit。
        company_codes = sorted({str(code).strip().upper() for code in final_codes})
        existing_ids = list((await db.execute(sa.select(Project.id).where(
            Project.company_code.in_(company_codes),
            Project.audit_year == data.audit_year,
            Project.is_deleted == sa.false(),
        ))).scalars().all())
        await lock_actor_and_project_memberships(db, actor, existing_ids)
        from app.deps import assert_project_permission

        try:
            for project_id in sorted(existing_ids, key=str):
                await assert_project_permission(db, actor, project_id, "edit")
        except HTTPException as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "PROJECT_CREATION_EXISTING_ACCESS_REQUIRED",
                    "message": "该企业或关联企业已有项目，请联系项目负责人处理",
                },
            ) from exc
        data = data.model_copy(update={"manager_id": actor.id, "signing_partner_id": None})
    try:
        project = await project_wizard_service.create_project(
            data,
            db,
            auto_commit=False,
            group_fields_prepared=True,
        )
        # create_project 只会附上同口径外推提示；库存继承提示由本协调器生成，二者都要返回。
        project._group_notices = [  # type: ignore[attr-defined]
            *notices,
            *(getattr(project, "_group_notices", None) or []),
        ]
        project.created_by = actor.id
        project.updated_by = actor.id
        from app.services.assignment_service import AssignmentService

        assignments = AssignmentService(db)
        if role == "manager":
            from app.services.procedure_authorization import (
                resolve_user_active_staff_id_optional,
            )

            staff_id = await resolve_user_active_staff_id_optional(db, actor.id)
            if staff_id is None:
                # 未绑定人员档案：只加项目成员（经理、编辑），不写团队委派（R7）。
                await assignments.initialize_creator_members(
                    [project.id], user_id=actor.id, assigned_by=actor.id,
                    role_key="manager", require_pending=False,
                )
            else:
                # R11：创建者不给本人发委派通知——与批量口径一致，走 initialize_project_managers（只写委派和成员行）。
                await assignments.initialize_project_managers(
                    [project.id], staff_id=staff_id,
                    user_id=actor.id, assigned_by=actor.id,
                    require_pending=False,
                )
        elif role == "partner":
            await assignments.initialize_project_partners(
                [project.id], user_id=actor.id, assigned_by=actor.id,
                require_pending=False,
            )
        await db.commit()
        await db.refresh(project)
        return project
    except Exception:
        await db.rollback()
        raise


__all__ = ["create_project_for_actor"]
