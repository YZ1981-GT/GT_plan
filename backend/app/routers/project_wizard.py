"""项目初始化向导 API 路由

Validates: Requirements 1.1-1.8
"""

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access, require_role
from app.models.audit_platform_schemas import (
    BasicInfoSchema,
    ProjectCreateResponse,
    ValidationResult,
    WizardState,
    WizardStep,
    WizardStepSaveResponse,
)
from app.models.core import Project, User
from app.services import project_wizard_service
from app.services.project_audit_year import resolve_project_audit_year
from app.services.project_creation_coordinator import create_project_for_actor
from app.services.project_creation_security import enforce_creation_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])
_PROJECT_CREATE_USER = require_role(["admin", "partner", "manager"])


def _extract_project_audit_year(project: Project) -> int | None:
    """提取项目审计年度（委托 project_audit_year 通用规则）。"""
    return resolve_project_audit_year(project)


def _to_project_response(project: Project) -> ProjectCreateResponse:
    from app.services.project_classification import project_classification

    audit_year = resolve_project_audit_year(project)
    classification = project_classification(project)
    return ProjectCreateResponse(
        id=project.id,
        name=project.name,
        client_name=project.client_name,
        short_name=project.short_name,
        company_code=project.company_code,
        audit_year=audit_year,
        project_type=project.project_type.value if project.project_type else None,
        status=project.status.value,
        template_type=project.template_type,
        company_subtype=project.company_subtype,
        business_category=classification.category_code,
        scenario=classification.scenario,
        project_classification=classification.as_dict(),
        report_scope=project.report_scope,
        parent_company_name=project.parent_company_name,
        parent_company_code=project.parent_company_code,
        relation_to_parent=project.relation_to_parent,
        ultimate_company_name=project.ultimate_company_name,
        ultimate_company_code=project.ultimate_company_code,
        parent_project_id=project.parent_project_id,
        consol_level=project.consol_level or 1,
        consol_lock=bool(project.consol_lock),
        created_at=project.created_at,
        notices=list(getattr(project, "_group_notices", None) or []),
        current_audit_phase=project.current_audit_phase or "final",
        interim_cutoff_date=project.interim_cutoff_date,
    )


@router.get("", response_model=list[ProjectCreateResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProjectCreateResponse]:
    """获取项目列表（按用户可见性过滤）

    admin/partner 可见所有项目，其他角色只能看到自己参与的项目。
    """
    from sqlalchemy import select
    from app.models.core import ProjectUser

    if current_user.role.value in ("admin", "partner"):
        # 管理员和合伙人可见所有项目
        result = await db.execute(
            select(Project).where(Project.is_deleted == False)  # noqa: E712
        )
    else:
        # 其他角色只能看到自己参与的项目
        my_project_ids = await db.execute(
            select(ProjectUser.project_id).where(
                ProjectUser.user_id == current_user.id,
                ProjectUser.is_deleted == False,  # noqa: E712
            )
        )
        pids = [r[0] for r in my_project_ids.all()]
        if not pids:
            return []
        result = await db.execute(
            select(Project).where(
                Project.id.in_(pids),
                Project.is_deleted == False,  # noqa: E712
            )
        )

    projects = result.scalars().all()
    return [_to_project_response(p) for p in projects]


@router.get("/list-with-progress")
async def list_projects_with_progress(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """仪表盘甘特视图专用：项目列表 + 进度 + 派生时间窗 + 负责人姓名。

    派生规则（避免改 Project 模型）：
      - start_date = audit_year-12-01（典型审计期开始：年报年末）
      - due_date   = (audit_year+1)-04-30（典型审计报告截止）
      - overall_progress = sum(已完成 wp count) / sum(wp count) * 100
        已完成 = WorkingPaper.status in (locked, archived)；空集时为 0
      - partner_name / manager_name = JOIN users.username

    单次 SQL 聚合（项目数 N）+ 单次 SQL 取 wp 进度（GROUP BY project_id）+ 单次 users JOIN，
    总计 3 次 IO，不会随 N 退化。
    """
    from datetime import date
    from sqlalchemy import select, func
    from app.models.core import ProjectUser
    from app.models.workpaper_models import WorkingPaper

    # 1. 项目可见性过滤
    if current_user.role.value in ("admin", "partner"):
        proj_result = await db.execute(
            select(Project).where(Project.is_deleted == False)  # noqa: E712
        )
    else:
        my_pids = await db.execute(
            select(ProjectUser.project_id).where(
                ProjectUser.user_id == current_user.id,
                ProjectUser.is_deleted == False,  # noqa: E712
            )
        )
        pids = [r[0] for r in my_pids.all()]
        if not pids:
            return []
        proj_result = await db.execute(
            select(Project).where(
                Project.id.in_(pids),
                Project.is_deleted == False,  # noqa: E712
            )
        )
    projects = proj_result.scalars().all()
    if not projects:
        return []
    proj_ids = [p.id for p in projects]

    # 2. 一次性聚合 wp 进度（review_passed/archived 占比 = 完成度）
    from sqlalchemy import case
    progress_q = (
        select(
            WorkingPaper.project_id,
            func.count(WorkingPaper.id).label("total"),
            func.sum(
                case((WorkingPaper.status.in_(("review_passed", "archived")), 1), else_=0)
            ).label("done"),
        )
        .where(
            WorkingPaper.project_id.in_(proj_ids),
            WorkingPaper.is_deleted == False,  # noqa: E712
        )
        .group_by(WorkingPaper.project_id)
    )
    progress_rows = (await db.execute(progress_q)).all()
    progress_map = {
        row[0]: round((int(row[2] or 0) / int(row[1])) * 100, 1) if int(row[1]) > 0 else 0.0
        for row in progress_rows
    }

    # 3. 一次性取 partner/manager 名称（users 表无 display_name 列，用 username）
    user_ids = {p.partner_id for p in projects if p.partner_id} | {p.manager_id for p in projects if p.manager_id}
    name_map: dict = {}
    if user_ids:
        from app.models.core import User as UserModel
        user_rows = (await db.execute(
            select(UserModel.id, UserModel.username).where(UserModel.id.in_(list(user_ids)))
        )).all()
        for uid, uname in user_rows:
            name_map[uid] = uname

    # 4. 组装
    out: list[dict] = []
    for p in projects:
        ay = _extract_project_audit_year(p)
        start_date_iso: str | None = None
        due_date_iso: str | None = None
        if ay:
            try:
                start_date_iso = date(ay, 12, 1).isoformat()
                due_date_iso = date(ay + 1, 4, 30).isoformat()
            except ValueError:
                pass
        out.append({
            "id": str(p.id),
            "name": p.name,
            "client_name": p.client_name,
            "audit_year": ay,
            "project_type": p.project_type.value if p.project_type else None,
            "status": p.status.value,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "start_date": start_date_iso,
            "due_date": due_date_iso,
            "overall_progress": progress_map.get(p.id, 0.0),
            "partner_name": name_map.get(p.partner_id) if p.partner_id else None,
            "manager_name": name_map.get(p.manager_id) if p.manager_id else None,
        })
    return out


@router.get("/{project_id}", response_model=ProjectCreateResponse)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectCreateResponse:
    from sqlalchemy import select
    from app.models.core import ProjectUser

    query = select(Project).where(
        Project.id == project_id,
        Project.is_deleted == False,  # noqa: E712
    )
    if current_user.role.value not in ("admin", "partner"):
        query = query.join(ProjectUser, ProjectUser.project_id == Project.id).where(
            ProjectUser.user_id == current_user.id,
            ProjectUser.is_deleted == False,  # noqa: E712
        )
    result = await db.execute(query)
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return _to_project_response(project)


@router.post("", response_model=ProjectCreateResponse)
async def create_project(
    data: BasicInfoSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_PROJECT_CREATE_USER),
) -> ProjectCreateResponse:
    """创建审计项目；manager 须持精确 USCC 授权并在同事务成为项目经理。"""
    await enforce_creation_rate_limit(current_user, entrypoint="single_project")
    project = await create_project_for_actor(data, db, current_user)
    return _to_project_response(project)


# ---------------------------------------------------------------------------
# Phase 3 需求 5.1: 配置合并范围 — 把已有单体项目挂为子公司（attach subsidiaries）
# ---------------------------------------------------------------------------


class AttachSubsidiariesRequest(BaseModel):
    """配置合并范围请求：把若干已有单体项目挂到本合并项目下作子公司。"""
    child_project_ids: list[UUID]


@router.get("/{project_id}/available-subsidiaries", response_model=list[ProjectCreateResponse])
async def list_available_subsidiaries(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProjectCreateResponse]:
    """列出可纳入本合并项目的候选单体项目（需求 5.1；consol-tree-three-code-autobuild 任务 6.3）。

    候选 = 用户可见 + 非合并项目 + 同审计年度 + 有企业代码 + 不是本企业 +
    **不在本企业树中**（已按三码识别的下级不再列出）+ 未被其他合并项目消费（派生链接为空或指向本项目）。
    返回的 ``relation_to_parent`` 为纳入后将采用的关系（已填取原值，未填按企业名称推断）。
    仅 consolidated 项目可调（R3：不影响非合并流程）。
    """
    from sqlalchemy import or_, select

    from app.models.core import ProjectUser
    from app.services.consol_tree_service import build_tree, iter_nodes
    from app.services.group_relation import infer_relation_from_name, normalize_relation
    from app.services.project_audit_year import resolve_project_audit_year

    parent = await db.get(Project, project_id)
    if parent is None or parent.is_deleted:
        raise HTTPException(status_code=404, detail="项目不存在")
    if parent.report_scope != "consolidated":
        raise HTTPException(status_code=400, detail="仅合并项目可配置合并范围")

    parent_code = (parent.company_code or "").strip()
    year = resolve_project_audit_year(parent)
    tree = await build_tree(db, project_id)
    in_tree = {n.company_code for n in iter_nodes(tree)} if tree is not None else set()

    query = select(Project).where(
        Project.is_deleted == False,  # noqa: E712
        Project.id != project_id,
        or_(Project.report_scope != "consolidated", Project.report_scope.is_(None)),
        or_(
            Project.parent_project_id.is_(None),
            Project.parent_project_id == project_id,
        ),
    )
    if current_user.role.value not in ("admin", "partner"):
        query = query.join(ProjectUser, ProjectUser.project_id == Project.id).where(
            ProjectUser.user_id == current_user.id,
            ProjectUser.is_deleted == False,  # noqa: E712
        )
    result = await db.execute(query)
    out: list[ProjectCreateResponse] = []
    for p in result.scalars().all():
        code = (p.company_code or "").strip()
        if not code or code == parent_code or code in in_tree:
            continue
        if resolve_project_audit_year(p) != year:
            continue
        resp = _to_project_response(p)
        try:
            explicit = normalize_relation(p.relation_to_parent)
        except ValueError:
            explicit = None
        resp.relation_to_parent = explicit or infer_relation_from_name(p.client_name)
        out.append(resp)
    return out


@router.post("/{project_id}/attach-subsidiaries", response_model=list[ProjectCreateResponse])
async def attach_subsidiaries(
    project_id: UUID,
    body: AttachSubsidiariesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProjectCreateResponse]:
    """把选中的已有单体项目纳入本合并项目（需求 5.1；consol-tree-three-code-autobuild 需求 7.5）。

    - 仅 consolidated 项目可调（R3：非合并项目流程不变）。
    - 改写下级项目（及其同企业另一口径项目）的集团关系：上级 = 本企业、控制方 = 本企业的控制方
      （空则本企业）、关系缺省按名称；再按三码重算派生链接 —— 不直接写 parent_project_id。
    - 跳过：合并项目、本企业自己的单户项目、其他审计年度的项目。
    - 成功后广播 CONSOL_SCOPE_CHANGED（需求 5.2）→ 前端树自动刷新。
    - 仅 admin/partner 或有写权限者可操作（沿用项目可见性，权限不足的子项目跳过）。
    """
    from app.services.project_subsidiary_attachment_service import (
        attach_subsidiaries as attach_existing_subsidiaries,
    )

    attached, year = await attach_existing_subsidiaries(
        db,
        parent_project_id=project_id,
        child_project_ids=body.child_project_ids,
        actor=current_user,
    )
    await db.commit()
    for child in attached:
        await db.refresh(child)

    # 链接没变（已纳入过）时 sync 不广播，因此对本合并项目显式推一次。
    if attached:
        from app.services.consol_scope_service import _emit_scope_changed

        _emit_scope_changed(project_id, year)
    return [_to_project_response(child) for child in attached]


# ---------------------------------------------------------------------------
# Phase 2 增强（group-tree-architecture Task 15.2 / 16.1）：
#   PATCH /api/projects/{project_id}/parent-code  — 调整上级企业代码（拖拽调层级）
#   GET   /api/projects/{project_id}/parent-code-history — 层级变更历史（读 app_audit_log）
# ---------------------------------------------------------------------------


class UpdateParentCodeRequest(BaseModel):
    """调整 parent_company_code 请求。

    parent_company_code 为 None 或空串 → 脱挂到顶层（指向最终控制方根或独立）。
    parent_company_name：新上级本年度没有建项时用作上级企业名称（建了项以项目上的名称为准）。
    """
    parent_company_code: str | None = None
    parent_company_name: str | None = None


class UpdateParentCodeResponse(BaseModel):
    id: str
    parent_company_code: str | None
    parent_project_id: str | None
    parent_company_name: str | None = None
    synced: list[dict] = []
    notices: list[str] = []


# 旧 _would_form_cycle（跨年度、按项目而非企业、把「上级=本企业」判成环）已由
# consol_group_tree.would_form_cycle 取代（同年度、企业实体、需求 1.5 口径）。


@router.patch("/{project_id}/parent-code", response_model=UpdateParentCodeResponse)
async def update_parent_code(
    project_id: UUID,
    body: UpdateParentCodeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
) -> UpdateParentCodeResponse:
    """调整项目的上级企业（「合并」总览页拖拽调层级，spec consol-autotree-linkage-closure R3）。

    两口径同写（代码、名称、关系、控制方补齐、向导回填数据）、校验（USCC 422 / 成环 400）与整年派生链接重算
    都在 ``group_links.reparent_project``；本路由只做鉴权（本项目 edit 级成员或管理员，原来只要求登录）、
    审计日志（app_audit_log，SAVEPOINT：写失败只回滚这一步）与提交。返回同步了哪些项目与字段。
    """
    from app.services.group_links import reparent_project

    project = await db.get(Project, project_id)
    if project is None or project.is_deleted:
        raise HTTPException(status_code=404, detail="项目不存在")

    old_value = project.parent_company_code
    new_value = (body.parent_company_code or "").strip() or None
    result = await reparent_project(db, project, new_value, name_hint=body.parent_company_name)

    # Task 16.1：写 app_audit_log（who/when/old/new）。失败不阻断主更新。
    try:
        from sqlalchemy import text

        details = {"old": old_value, "new": new_value, "parent_company_name": result["parent_company_name"],
                   "synced": [s["id"] for s in result["synced"]]}
        async with db.begin_nested():
            await db.execute(
                text(
                    "INSERT INTO app_audit_log "
                    "(id, user_id, action, resource_type, resource_id, details, created_at) "
                    "VALUES (gen_random_uuid(), :user_id, :action, :resource_type, "
                    ":resource_id, CAST(:details AS jsonb), :now)"
                ),
                {
                    "user_id": str(current_user.id),
                    "action": "project.parent_code.change",
                    "resource_type": "project",
                    "resource_id": str(project_id),
                    "details": json.dumps(details, ensure_ascii=False),
                    "now": datetime.now(timezone.utc),
                },
            )
    except Exception as exc:  # noqa: BLE001
        # app_audit_log 是 PG 专用表（gen_random_uuid/::jsonb），SQLite 测试会失败，
        # 审计日志写入失败不应阻断主更新（SAVEPOINT 已回滚这一步）。
        logger.warning("parent_company_code 变更审计日志写入失败: %s", exc)

    await db.commit()
    await db.refresh(project)

    return UpdateParentCodeResponse(
        id=str(project.id),
        parent_company_code=project.parent_company_code,
        parent_project_id=str(project.parent_project_id) if project.parent_project_id else None,
        parent_company_name=result["parent_company_name"],
        synced=result["synced"],
        notices=result["notices"],
    )


class ParentCodeHistoryEntry(BaseModel):
    user_id: str | None
    created_at: str | None
    old: str | None
    new: str | None


@router.get("/{project_id}/parent-code-history", response_model=list[ParentCodeHistoryEntry])
async def get_parent_code_history(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> list[ParentCodeHistoryEntry]:
    """查询项目的上级企业代码变更历史（读 app_audit_log，Task 16.1 读侧）。

    供前端"查看层级变更历史"右键菜单接入。表/数据缺失时返回空列表（容错）。
    鉴权：本项目成员（只读即可）或管理员（与改上级同一处收紧，原来只要求登录 ⇒ 可读任意项目的历史）。
    """
    entries: list[ParentCodeHistoryEntry] = []
    try:
        from sqlalchemy import text

        rows = await db.execute(
            text(
                "SELECT user_id, created_at, details FROM app_audit_log "
                "WHERE action = :action AND resource_id = :rid "
                "ORDER BY created_at DESC"
            ),
            {"action": "project.parent_code.change", "rid": str(project_id)},
        )
        for user_id, created_at, details in rows.all():
            old_v = None
            new_v = None
            if isinstance(details, dict):
                old_v = details.get("old")
                new_v = details.get("new")
            elif isinstance(details, str):
                try:
                    parsed = json.loads(details)
                    old_v = parsed.get("old")
                    new_v = parsed.get("new")
                except (ValueError, AttributeError):
                    pass
            entries.append(ParentCodeHistoryEntry(
                user_id=str(user_id) if user_id is not None else None,
                created_at=created_at.isoformat() if hasattr(created_at, "isoformat") else (
                    str(created_at) if created_at is not None else None
                ),
                old=old_v,
                new=new_v,
            ))
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取 parent_company_code 变更历史失败: %s", exc)
        return []
    return entries


class TemplateRecommendationResponse(BaseModel):
    """企业子类型推荐响应（需求 7.6 + 14.3 回填）。"""
    subtype: str | None
    confidence: str
    candidates: list[str]
    matched_rules: list[str]
    source: str
    # 需求 1.7/1.8/14.3：项目当前已保存的企业子类型（用户手动设置时优先）
    current_subtype: str | None = None
    # 需求 1.7 ③：为空/未确认时前端展示「待确认企业子类型」非阻断横幅
    needs_confirmation: bool = False


@router.get(
    "/{project_id}/template-recommendation",
    response_model=TemplateRecommendationResponse,
)
async def get_template_recommendation(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TemplateRecommendationResponse:
    """根据项目属性推荐企业子类型（模板 A/B/C/D）。

    从 Project 行提取属性（applicable_standard_v2.entity_type / scenario /
    template_type / report_scope / 公司名）喂给 MatchingRulesService。
    规则推荐优先于 listed/non_listed fallback（需求 7.7）。
    需求 1.7/1.8/14.3：返回 current_subtype（项目已保存值，用户手动优先）+
    needs_confirmation（为空时引导前端展示「待确认企业子类型」横幅）。

    Validates: Requirements 1.4, 1.7, 1.8, 7.2, 7.5, 7.6, 7.7
    """
    from app.services.matching_rules_service import (
        backfill_company_subtype,
        recommend_company_subtype,
    )

    project = await db.get(Project, project_id)
    if project is None or project.is_deleted:
        raise HTTPException(status_code=404, detail="项目不存在")

    # fallback 推断依赖 company_type（listed/non_listed），从模板/准则属性派生
    from app.services.project_classification import project_classification

    project_attrs = {
        "entity_type": (project.applicable_standard_v2 or {}).get("entity_type"),
        "scope": (project.applicable_standard_v2 or {}).get("scope"),
        "scenario": project_classification(project).scenario,
        "template_type": project.template_type,
        "report_scope": project.report_scope,
        "company_name": project.name,
        "client_name": project.client_name,
        "applicable_standard_v2": project.applicable_standard_v2,
    }
    result = recommend_company_subtype(project_attrs)
    backfill = backfill_company_subtype(
        project_attrs, existing_subtype=project.company_subtype
    )
    return TemplateRecommendationResponse(
        **result.to_dict(),
        current_subtype=project.company_subtype,
        needs_confirmation=backfill.needs_confirmation,
    )


@router.get("/{project_id}/wizard", response_model=WizardState)
async def get_wizard_state(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WizardState:
    """获取向导当前状态（支持断点续做）。

    Validates: Requirements 1.4, 1.5
    """
    return await project_wizard_service.get_wizard_state(project_id, db)


@router.put("/{project_id}/wizard/{step}", response_model=WizardStepSaveResponse)
async def update_step(
    project_id: UUID,
    step: WizardStep,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WizardStepSaveResponse:
    """更新指定步骤数据并持久化。

    Validates: Requirements 1.3, 1.4, 1.5
    """
    return await project_wizard_service.update_step(project_id, step, data, db)


@router.post(
    "/{project_id}/wizard/validate/{step}",
    response_model=ValidationResult,
)
async def validate_step(
    project_id: UUID,
    step: WizardStep,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ValidationResult:
    """校验指定步骤是否满足前进条件。

    Validates: Requirements 1.8
    """
    return await project_wizard_service.validate_step(project_id, step, db)


@router.post("/{project_id}/wizard/confirm", response_model=ProjectCreateResponse)
async def confirm_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectCreateResponse:
    """确认创建项目，状态 created → planning。

    Validates: Requirements 1.7
    """
    project = await project_wizard_service.confirm_project(
        project_id, db, changed_by=current_user.id
    )
    return _to_project_response(project)


# ── 删除项目 ──


class BatchDeleteRequest(BaseModel):
    project_ids: list[UUID]


@router.delete("/{project_id}")
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """软删除单个项目（R9：admin 任意；其余须是本项目 edit 级成员）。"""
    from sqlalchemy import select
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)  # noqa: E712
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    from app.services.group_topology_lock import lock_topology_years

    year = resolve_project_audit_year(project)
    await lock_topology_years(db, [year])
    await db.refresh(project)
    if project.is_deleted:
        raise HTTPException(status_code=404, detail="项目不存在")
    if resolve_project_audit_year(project) != year:
        raise HTTPException(status_code=409, detail="项目年度已变化，请刷新后重试")
    # 记下删除人与删除时间（回收站「删除人 / 删除时间」读它们；原先只置 is_deleted，两列恒空）
    project.soft_delete()
    project.updated_by = current_user.id
    # 需求 7.2：删除后按三码重算本年度派生链接（下级不再指向已删的合并项目）
    from app.services.group_links import sync_group_links_for

    await sync_group_links_for(db, project)
    await db.commit()
    return {"id": str(project_id), "deleted": True}


@router.post("/batch-delete")
async def batch_delete_projects(
    body: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量软删除项目（R9：admin 任意；其余须是本项目 edit 级成员。无权限的报错但不阻断其他项目）。"""
    from fastapi import HTTPException
    from sqlalchemy import select

    from app.deps import assert_project_permission
    from app.services.group_links import sync_group_links_for
    from app.services.group_topology_lock import lock_topology_years

    requested_ids = list(dict.fromkeys(body.project_ids))
    initial = list((await db.execute(
        select(Project).where(Project.id.in_(requested_ids), Project.is_deleted == False)  # noqa: E712
    )).scalars().all())

    # 逐项权限校验（无权限的跳过，不阻断其他项目）
    forbidden_ids: set[UUID] = set()
    for project in initial:
        try:
            await assert_project_permission(db, current_user, project.id, "edit")
        except HTTPException:
            forbidden_ids.add(project.id)
    initial = [project for project in initial if project.id not in forbidden_ids]
    if not initial and forbidden_ids:
        raise HTTPException(status_code=403, detail="权限不足，无法删除选中的项目")
    initial_years = {
        project.id: resolve_project_audit_year(project) for project in initial
    }
    await lock_topology_years(db, initial_years.values())
    # 锁后重读并核对年度，避免先按旧年度写删除、再逆序补锁新年度。
    deleted_stmt = select(Project).where(
        Project.id.in_(requested_ids), Project.is_deleted == False  # noqa: E712
    ).execution_options(populate_existing=True)
    deleted = list((await db.execute(deleted_stmt)).scalars().all())
    if any(
        resolve_project_audit_year(project) != initial_years.get(project.id)
        for project in deleted
    ):
        raise HTTPException(status_code=409, detail="项目年度已变化，请刷新后重试")
    for project in deleted:
        project.soft_delete()
        project.updated_by = current_user.id
    # 需求 7.2：整批删除后按涉及的年度各重算一次派生链接
    await sync_group_links_for(db, *deleted)
    await db.commit()
    return {"deleted_count": len(deleted), "requested": len(body.project_ids)}
