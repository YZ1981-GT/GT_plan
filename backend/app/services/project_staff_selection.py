"""项目基本信息的人员档案校验与账号映射，不维护账号或团队委派。"""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_schemas import BasicInfoSchema
from app.models.staff_models import StaffMember, StaffTitle

STAFF_FIELDS = {"signing_partner_staff_id", "manager_staff_id"}


async def _load_staff(db: AsyncSession, staff_id: UUID | str, label: str) -> StaffMember:
    try:
        identity = UUID(str(staff_id))
    except ValueError as exc:
        raise HTTPException(422, f"{label}人员档案标识无效，请重新选择") from exc
    staff = await db.scalar(
        select(StaffMember).where(
            StaffMember.id == identity,
            StaffMember.is_deleted.is_(False),
        )
    )
    if staff is None:
        raise HTTPException(422, f"{label}人员档案不存在或已删除，请重新选择")
    return staff


async def resolve_staff_selection(
    data: BasicInfoSchema,
    db: AsyncSession,
    *,
    existing_basic_info: dict | None = None,
) -> BasicInfoSchema:
    """按字段是否提交区分旧协议、保留选择和显式清空。"""
    existing = existing_basic_info or {}
    supplied = data.model_fields_set
    has_existing = bool(STAFF_FIELDS.intersection(existing))
    if not STAFF_FIELDS.intersection(supplied) and not has_existing:
        return data

    selected = {
        field: getattr(data, field) if field in supplied else existing.get(field)
        for field in STAFF_FIELDS
    }
    partner_id = selected["signing_partner_staff_id"]
    manager_id = selected["manager_staff_id"]
    if manager_id is not None and partner_id is None:
        raise HTTPException(422, "选择项目经理前请先选择签字合伙人")

    partner = await _load_staff(db, partner_id, "签字合伙人") if partner_id is not None else None
    manager = await _load_staff(db, manager_id, "项目经理") if manager_id is not None else None
    if partner is not None and partner.title != StaffTitle.partner.value:
        raise HTTPException(422, "签字合伙人的人员档案职级必须为合伙人，请重新选择")
    if manager is not None and partner is not None:
        if manager.partner_id is not None:
            if manager.partner_id != partner.id:
                raise HTTPException(422, "项目经理不属于所选签字合伙人，请重新选择")
        else:
            matches = (await db.scalars(
                select(StaffMember.id).where(
                    StaffMember.is_deleted.is_(False),
                    StaffMember.title == StaffTitle.partner.value,
                    StaffMember.name == manager.partner_name,
                )
            )).all()
            if len(matches) > 1:
                raise HTTPException(422, "所属合伙人存在同名人员且未明确关联档案，请先维护人员归属")
            if matches != [partner.id]:
                raise HTTPException(422, "项目经理不属于所选签字合伙人，请重新选择")

    resolved = {
        "signing_partner_staff_id": partner.id if partner is not None else None,
        "manager_staff_id": manager.id if manager is not None else None,
        "signing_partner_id": partner.user_id if partner is not None else None,
        "manager_id": manager.user_id if manager is not None else None,
    }
    # 未提交档案字段时，账号改动不得绕过已保存的档案选择。
    for staff_field, user_field in (
        ("signing_partner_staff_id", "signing_partner_id"),
        ("manager_staff_id", "manager_id"),
    ):
        if (
            has_existing
            and staff_field not in supplied
            and user_field in supplied
            and getattr(data, user_field) != resolved[user_field]
        ):
            raise HTTPException(422, "账号选择与已保存的人员档案不一致，请通过人员档案重新选择")
    return data.model_copy(update=resolved)


def dump_basic_info(data: BasicInfoSchema) -> dict:
    """旧协议不补空档案键，避免把未提交误认成显式清空。"""
    return data.model_dump(mode="json", exclude=STAFF_FIELDS - data.model_fields_set)
