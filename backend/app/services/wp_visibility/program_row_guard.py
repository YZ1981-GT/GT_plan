"""程序表行级编辑隔离（spec procedure-trim-generation-delegation-chain 需求 7 / ADR-7）。

用户裁决：程序执行人能看整张程序表，只能编辑派给自己的程序行。主编、主管（经理 / 合伙人 / 质控 / EQCR）、
admin 可编辑全部行；裁剪 / 恢复（「不适用」的进出）只归项目委派人（经理 / 合伙人 / admin），走细裁接口落到
程序行任务。服务端按自己推导的行归属合并，不信客户端：

- ``resolve_row_access``：本人在这张程序表上能改哪些行（``full_power`` / ``can_trim`` / ``own_program_nos``），
  以及各行执行人姓名（前端只读行显示）。
- ``merge_program_sheet``：委派人原样保存；可改全部行但不是委派人的（主编 / 质控 / EQCR）「不适用」的进出、
  裁剪理由与裁剪决定保持服务端。受限用户本人行只接受执行状态与执行说明（不含裁剪 / 恢复），其余行、新增或
  删除的行、裁剪决定、签字一律保留服务端已存内容。都返回被忽略的程序号。服务端还没存过这张表时，受限用户
  非本人行的执行状态只认「待执行 / 不适用」（模板原样），执行说明清空，自加行丢弃，签字与裁剪决定不收。
- ``assert_program_override_allowed``：程序表字段覆盖（``procedure_table:*``）对受限用户校验本人行。

纯读（除调用方保存外不写库）。
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureRowTask
from app.models.staff_models import StaffMember
from app.models.workpaper_models import WorkingPaper, WpIndex

FULL_POWER_KINDS = frozenset({"admin", "supervisor_scope", "lead"})
EDITABLE_FIELDS = ("status", "execution_summary")
TRACKED_FIELDS = ("status", "execution_summary", "trim_reason")
PRISTINE_STATUSES = frozenset({"pending", "not_applicable", "", None})
_TEMPLATE_ROW_ID = re.compile(r"^row-\d+$")


@dataclass(frozen=True)
class RowAccess:
    full_power: bool
    can_trim: bool
    own_program_nos: frozenset[str] = frozenset()
    assignees: dict[str, str] = field(default_factory=dict)
    template_code: str = ""

    def to_dict(self) -> dict:
        return {
            "full_power": self.full_power,
            "can_trim": self.can_trim,
            "own_program_nos": sorted(self.own_program_nos, key=_natural),
            "assignees": dict(self.assignees),
            "template_code": self.template_code,
        }


def _natural(no: str):
    return (0, int(no), "") if no.isdigit() else (1, 0, no)


def _norm(no) -> str:
    from app.services.procedure_row_trim_service import normalize_program_no

    return normalize_program_no(no)


async def _can_trim(db: AsyncSession, user, project_id: UUID) -> bool:
    from app.services.procedure_authorization import ensure_project_delegator

    try:
        await ensure_project_delegator(db, user, project_id)
    except HTTPException:
        return False
    return True


async def _row_tasks(db: AsyncSession, project_id: UUID, wp_index_ids, template_code: str):
    """有效（适用、未取消）的程序行任务：(程序号, 执行人 user_id, 执行人姓名)。``wp_index_ids=None`` 不限底稿。"""
    conds = [
        ProcedureRowTask.project_id == project_id,
        ProcedureRowTask.sheet_key == template_code,
        ProcedureRowTask.is_deleted == sa.false(),
        ProcedureRowTask.applicability_status == "execute",
        ProcedureRowTask.workflow_status != "cancelled",
        ProcedureRowTask.program_no.isnot(None),
    ]
    if wp_index_ids is not None:
        conds.append(ProcedureRowTask.wp_index_id.in_(list(wp_index_ids)))
    rows = (await db.execute(
        sa.select(ProcedureRowTask.program_no, StaffMember.user_id, StaffMember.name)
        .outerjoin(StaffMember, sa.and_(StaffMember.id == ProcedureRowTask.assignee_staff_id,
                                        StaffMember.is_deleted == sa.false()))
        .where(*conds)
    )).all()
    return [(_norm(r[0]), r[1], r[2]) for r in rows]


async def resolve_row_access(db: AsyncSession, user, wp: WorkingPaper, sheet_name: str) -> RowAccess:
    from app.routers.wp_render_strategies._a_program import resolve_program_template_code
    from app.services.wp_visibility.role_classifier import VisibilityRoleClassifier
    from app.services.wp_visibility.visibility_query import VisibilityQueryService

    wp_code = (await db.execute(sa.select(WpIndex.wp_code).where(WpIndex.id == wp.wp_index_id))).scalar_one_or_none()
    template_code = resolve_program_template_code(sheet_name or "", wp_code or "")
    ctx = await VisibilityRoleClassifier(db).classify(user, wp.project_id)
    grants = await VisibilityQueryService(db).grants_for_wp_index(ctx, wp.wp_index_id)
    full_power = any(g.access_kind in FULL_POWER_KINDS and not g.readonly for g in grants)
    tasks = await _row_tasks(db, wp.project_id, [wp.wp_index_id], template_code)
    own = frozenset(no for no, uid, _name in tasks if uid == user.id)
    assignees = {no: name for no, _uid, name in tasks if name}
    return RowAccess(full_power, await _can_trim(db, user, wp.project_id), own, assignees, template_code)


def _differs(a: dict, b: dict) -> bool:
    return any((a.get(f) or None) != (b.get(f) or None) for f in TRACKED_FIELDS)


def _keep_server_applicability(old: dict | None, new: dict) -> tuple[dict, list[str]]:
    """可改全部行但不是委派人（主编 / 质控 / EQCR）：「不适用」的进出与裁剪理由保持服务端（裁剪只归委派人）。"""
    old_rows = old.get("programs") if isinstance(old, dict) else None
    if not isinstance(old_rows, list) or not old_rows:
        return new, []  # 服务端还没存过：分不清模板默认的不适用与本次改的（残余风险，见 design）
    base_by_no = {_norm(r.get("program_no")): r for r in old_rows if isinstance(r, dict)}
    merged = copy.deepcopy(new)
    ignored: set[str] = set()
    for row in merged["programs"]:
        if not isinstance(row, dict):
            continue
        no = _norm(row.get("program_no"))
        base = base_by_no.get(no) or {}
        was = base.get("status") or "pending"
        if "not_applicable" in (row.get("status"), was) and row.get("status") != was:
            row["status"] = was
            ignored.add(no)
        if (row.get("trim_reason") or None) != (base.get("trim_reason") or None):
            if base.get("trim_reason"):
                row["trim_reason"] = base["trim_reason"]
            else:
                row.pop("trim_reason", None)
            ignored.add(no)
    merged["trim_decisions"] = copy.deepcopy(old.get("trim_decisions") or [])
    return merged, sorted(ignored, key=_natural)


def merge_program_sheet(old: dict | None, new: dict, access: RowAccess) -> tuple[dict, list[str]]:
    """程序表保存按服务端行归属合并，返回 ``(要存的数据, 被忽略的程序号)``。"""
    if not isinstance(new.get("programs"), list):
        return new, []
    if access.full_power:
        return (new, []) if access.can_trim else _keep_server_applicability(old, new)
    new_rows = [r for r in new["programs"] if isinstance(r, dict)]
    ignored: set[str] = set()
    old_rows = old.get("programs") if isinstance(old, dict) else None

    if isinstance(old_rows, list) and old_rows:
        merged = copy.deepcopy(old)
        base_by_no = {_norm(r.get("program_no")): r for r in merged["programs"] if isinstance(r, dict)}
        new_by_no = {_norm(r.get("program_no")): r for r in new_rows}
        ignored |= (set(new_by_no) ^ set(base_by_no))  # 新增 / 删除的行
        for no, row in new_by_no.items():
            target = base_by_no.get(no)
            if target is None or not _differs(row, target):
                continue
            if no not in access.own_program_nos:
                ignored.add(no)
                continue
            if (row.get("trim_reason") or None) != (target.get("trim_reason") or None):
                ignored.add(no)
            for f in EDITABLE_FIELDS:
                val = row.get(f)
                if (val or None) == (target.get(f) or None):
                    continue
                if f == "status" and "not_applicable" in (val, target.get("status")):
                    ignored.add(no)  # 裁剪 / 恢复只走细裁接口
                    continue
                target[f] = val
        return merged, sorted(ignored, key=_natural)

    # 服务端还没存过：非本人行回到模板原样
    merged = copy.deepcopy(new)
    rows: list[dict] = []
    for row in merged.get("programs") or []:
        if not isinstance(row, dict):
            continue
        no = _norm(row.get("program_no"))
        if not _TEMPLATE_ROW_ID.match(str(row.get("id") or "")):
            ignored.add(no)
            continue
        if no not in access.own_program_nos:
            pristine = row.get("status") if row.get("status") in PRISTINE_STATUSES else "pending"
            if pristine != row.get("status") or row.get("execution_summary"):
                ignored.add(no)
            row["status"] = pristine or "pending"
            row.pop("execution_summary", None)
        rows.append(row)
    merged["programs"] = rows
    merged["trim_decisions"] = []
    merged.pop("signatures", None)
    return merged, sorted(ignored, key=_natural)


async def guard_program_sheet_save(db: AsyncSession, user, wp: WorkingPaper, sheet_name: str,
                                   old: dict | None, new: dict) -> tuple[dict, list[str]]:
    """``/save`` 用：含程序行的 sheet 按行归属合并（委派人原样通过）。"""
    if not isinstance(new.get("programs"), list):
        return new, []
    try:
        async with db.begin_nested():  # 判定查询失败不拖垮保存事务
            access = await resolve_row_access(db, user, wp, sheet_name)
    except Exception as exc:  # noqa: BLE001 — 读不到归属就不能放行，也不能静默吞掉本人的改动
        raise HTTPException(status_code=503, detail="暂时无法确认程序行归属，请稍后重试") from exc
    return merge_program_sheet(old, new, access)


async def assert_program_override_allowed(db: AsyncSession, user, project_id: UUID, scope: str,
                                          item_key: str, field_name: str, value) -> None:
    """``procedure_table:*`` 字段覆盖：受限用户只能写派给本人的程序行，且不能借覆盖裁剪。"""
    if not (scope or "").startswith("procedure_table:"):
        return
    if getattr(getattr(user, "role", None), "value", None) == "admin":
        return
    from app.routers.wp_render_strategies._a_program import resolve_program_template_code
    from app.services.wp_visibility.effective_scope import resolve_member_scope

    member = await resolve_member_scope(db, project_id, user.id)
    if member.is_supervisor:
        return
    if field_name == "status" and value == "not_applicable" and not await _can_trim(db, user, project_id):
        raise HTTPException(status_code=403, detail="程序行裁剪须由项目委派人在控制台操作")
    from app.services.procedure_task_materialization_service import _base_wp_code

    suffix = scope.split(":", 1)[1]
    template_code = resolve_program_template_code(suffix, suffix)
    # 该程序表所属底稿的主编可写全部行
    lead = (await db.execute(sa.select(sa.func.count()).select_from(WorkingPaper).join(
        WpIndex, WpIndex.id == WorkingPaper.wp_index_id,
    ).where(
        WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == sa.false(),
        WpIndex.wp_code.in_({template_code, _base_wp_code(template_code)}), WorkingPaper.assigned_to == user.id,
    ))).scalar_one()
    if lead:
        return
    no = _norm(item_key)
    if any(t_no == no and uid == user.id for t_no, uid, _n in await _row_tasks(db, project_id, None, template_code)):
        return
    raise HTTPException(status_code=403, detail="只能填写派给本人的程序行")
