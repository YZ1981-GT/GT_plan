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
from app.deps import get_current_user
from app.routers.password_confirm import require_confirmation_token
from app.models.audit_platform_schemas import (
    BasicInfoSchema,
    ProjectCreateResponse,
    ValidationResult,
    WizardState,
    WizardStep,
)
from app.models.core import Project, User
from app.services import project_wizard_service
from app.services.project_audit_year import resolve_project_audit_year

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _extract_project_audit_year(project: Project) -> int | None:
    """提取项目审计年度（委托 project_audit_year 通用规则）。"""
    return resolve_project_audit_year(project)


def _to_project_response(project: Project) -> ProjectCreateResponse:
    audit_year = resolve_project_audit_year(project)
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
        report_scope=project.report_scope,
        parent_project_id=project.parent_project_id,
        consol_level=project.consol_level or 1,
        consol_lock=bool(project.consol_lock),
        created_at=project.created_at,
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
    current_user: User = Depends(get_current_user),
) -> ProjectCreateResponse:
    """创建审计项目（向导步骤1-基本信息）。

    Validates: Requirements 1.2, 1.3
    """
    project = await project_wizard_service.create_project(data, db)
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
    """列出可挂为子公司的候选单体项目（需求 5.1）。

    候选 = 用户可见 + 非本项目 + report_scope != consolidated +
    （未挂到其他集团 或 已挂到本项目）。仅 consolidated 项目可调（R3：不影响非合并流程）。
    """
    from sqlalchemy import select, or_
    from app.models.core import ProjectUser

    parent = await db.get(Project, project_id)
    if parent is None or parent.is_deleted:
        raise HTTPException(status_code=404, detail="项目不存在")
    if parent.report_scope != "consolidated":
        raise HTTPException(status_code=400, detail="仅合并项目可配置合并范围")

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
    return [_to_project_response(p) for p in result.scalars().all()]


@router.post("/{project_id}/attach-subsidiaries", response_model=list[ProjectCreateResponse])
async def attach_subsidiaries(
    project_id: UUID,
    body: AttachSubsidiariesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProjectCreateResponse]:
    """把选中的已有单体项目挂为本合并项目的子公司（需求 5.1）。

    - 仅 consolidated 项目可调（R3：非合并项目流程不变）。
    - 设置子项目 parent_project_id = 本项目；consol_level = 母 + 1。
    - 成功后广播 CONSOL_SCOPE_CHANGED（需求 5.2）→ 前端树自动刷新。
    - 仅 admin/partner 或有写权限者可操作（沿用项目可见性，权限不足的子项目跳过）。
    """
    from sqlalchemy import select
    from app.models.core import ProjectUser

    parent = await db.get(Project, project_id)
    if parent is None or parent.is_deleted:
        raise HTTPException(status_code=404, detail="项目不存在")
    if parent.report_scope != "consolidated":
        raise HTTPException(status_code=400, detail="仅合并项目可配置合并范围")

    # 可写项目集合（admin/partner 全可写，其他角色仅自己参与的项目）
    allowed_ids: set[UUID] | None = None
    if current_user.role.value not in ("admin", "partner"):
        mine = await db.execute(
            select(ProjectUser.project_id).where(
                ProjectUser.user_id == current_user.id,
                ProjectUser.is_deleted == False,  # noqa: E712
            )
        )
        allowed_ids = {r[0] for r in mine.all()}

    attached: list[Project] = []
    for child_id in body.child_project_ids:
        if child_id == project_id:
            continue
        if allowed_ids is not None and child_id not in allowed_ids:
            continue
        child = await db.get(Project, child_id)
        if child is None or child.is_deleted:
            continue
        if child.report_scope == "consolidated":
            continue  # 不允许把合并项目挂为子公司
        child.parent_project_id = project_id
        child.consol_level = (parent.consol_level or 1) + 1
        attached.append(child)

    await db.commit()
    for c in attached:
        await db.refresh(c)

    # 需求 5.2：合并范围变更广播，前端树自动刷新（ADR-CONSOL-303）
    if attached:
        from app.services.consol_scope_service import _emit_scope_changed
        _emit_scope_changed(project_id, _extract_project_audit_year(parent))

    return [_to_project_response(c) for c in attached]


# ---------------------------------------------------------------------------
# Phase 2 增强（group-tree-architecture Task 15.2 / 16.1）：
#   PATCH /api/projects/{project_id}/parent-code  — 调整上级企业代码（拖拽调层级）
#   GET   /api/projects/{project_id}/parent-code-history — 层级变更历史（读 app_audit_log）
# ---------------------------------------------------------------------------


class UpdateParentCodeRequest(BaseModel):
    """调整 parent_company_code 请求。

    parent_company_code 为 None 或空串 → 脱挂到顶层（指向最终控制方根或独立）。
    """
    parent_company_code: str | None = None


class UpdateParentCodeResponse(BaseModel):
    id: str
    parent_company_code: str | None
    parent_project_id: str | None


async def _would_form_cycle(
    db: AsyncSession,
    project: Project,
    new_parent_code: str,
) -> bool:
    """后端二次校验：将 project.parent_company_code 设为 new_parent_code 是否形成循环。

    从 new_parent_code 出发，沿 parent_company_code → company_code 链向上遍历
    （限定同一 ultimate 分组、未删除项目）。若遍历途中遇到 project 自身的
    company_code → 形成循环（project 成为自己的祖先），返回 True。

    带 visited 集合防止遍历途中已存在的环导致死循环。
    parent 指向不存在的代码 → 链断裂（脱挂），不算循环，返回 False。
    """
    from sqlalchemy import select

    own_code = (project.company_code or "").strip()
    target_code = (new_parent_code or "").strip()
    if not target_code:
        return False
    # 自己当自己的上级 → 直接判循环
    if own_code and target_code == own_code:
        return True
    if not own_code:
        # 自身无 company_code，无法成为任何节点的祖先 → 不可能循环
        return False

    # 同一 ultimate 分组内的候选项目（按 company_code 索引）
    ultimate = (project.ultimate_company_code or "").strip()
    stmt = select(Project).where(Project.is_deleted == False)  # noqa: E712
    if ultimate:
        stmt = stmt.where(Project.ultimate_company_code == ultimate)
    res = await db.execute(stmt)
    by_code: dict[str, Project] = {}
    for p in res.scalars().all():
        c = (p.company_code or "").strip()
        if c and c not in by_code:
            by_code[c] = p

    visited: set[str] = set()
    current_code = target_code
    while current_code:
        if current_code == own_code:
            return True  # 走回自身 → 循环
        if current_code in visited:
            return False  # 已存在的环（不含自身），链终止
        visited.add(current_code)
        node = by_code.get(current_code)
        if node is None:
            return False  # 链断裂（指向不存在企业）→ 脱挂，无循环
        current_code = (node.parent_company_code or "").strip()
    return False


@router.patch("/{project_id}/parent-code", response_model=UpdateParentCodeResponse)
async def update_parent_code(
    project_id: UUID,
    body: UpdateParentCodeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UpdateParentCodeResponse:
    """调整项目的上级企业代码（parent_company_code）。

    用于树形拖拽调整层级（Task 15）。后端二次校验循环引用（Task 15.2），
    并将变更写入 app_audit_log（who/when/old/new，Task 16.1）。

    - parent_company_code 为空/None → 脱挂到顶层。
    - 设为自身 company_code 或形成循环 → 400 拒绝。
    - 同步解析 parent_project_id（匹配同 ultimate 内 company_code 的项目；
      找不到则置 None，与批量导入脱挂行为一致）。
    - 审计日志写入失败不阻断主更新（try/except 吞，仅告警）。
    """
    project = await db.get(Project, project_id)
    if project is None or project.is_deleted:
        raise HTTPException(status_code=404, detail="项目不存在")

    old_value = project.parent_company_code
    new_value = (body.parent_company_code or "").strip() or None

    # 后端二次校验：循环引用
    if new_value is not None:
        own_code = (project.company_code or "").strip()
        if own_code and new_value == own_code:
            raise HTTPException(status_code=400, detail="不能将项目的上级设为自身")
        if await _would_form_cycle(db, project, new_value):
            raise HTTPException(
                status_code=400, detail="该调整会形成循环引用（项目成为自己的祖先）"
            )

    # 更新 parent_company_code
    project.parent_company_code = new_value

    # 同步解析 parent_project_id（与批量导入解析逻辑一致：匹配同 ultimate 内 company_code）
    new_parent_project_id = None
    if new_value is not None:
        from sqlalchemy import select

        stmt = select(Project).where(
            Project.company_code == new_value,
            Project.is_deleted == False,  # noqa: E712
            Project.id != project.id,
        )
        ultimate = (project.ultimate_company_code or "").strip()
        if ultimate:
            stmt = stmt.where(Project.ultimate_company_code == ultimate)
        res = await db.execute(stmt)
        candidates = res.scalars().all()
        target = None
        if candidates:
            # 优先同年度
            ay = project.audit_year
            if ay is not None:
                for c in candidates:
                    if c.audit_year == ay:
                        target = c
                        break
            target = target or candidates[0]
        if target is not None:
            new_parent_project_id = target.id
    project.parent_project_id = new_parent_project_id

    # Task 16.1：写 app_audit_log（who/when/old/new）。失败不阻断主更新。
    try:
        from sqlalchemy import text

        details = {"old": old_value, "new": new_value}
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
        # 审计日志写入失败不应阻断主更新。
        logger.warning("parent_company_code 变更审计日志写入失败: %s", exc)

    await db.commit()
    await db.refresh(project)

    return UpdateParentCodeResponse(
        id=str(project.id),
        parent_company_code=project.parent_company_code,
        parent_project_id=str(project.parent_project_id) if project.parent_project_id else None,
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
    current_user: User = Depends(get_current_user),
) -> list[ParentCodeHistoryEntry]:
    """查询项目的上级企业代码变更历史（读 app_audit_log，Task 16.1 读侧）。

    供前端"查看层级变更历史"右键菜单接入。表/数据缺失时返回空列表（容错）。
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
    project_attrs = {
        "entity_type": (project.applicable_standard_v2 or {}).get("entity_type"),
        "scope": (project.applicable_standard_v2 or {}).get("scope"),
        "scenario": project.scenario,
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


@router.put("/{project_id}/wizard/{step}", response_model=WizardState)
async def update_step(
    project_id: UUID,
    step: WizardStep,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WizardState:
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


from pydantic import BaseModel as _BaseModel


class BatchDeleteRequest(_BaseModel):
    project_ids: list[UUID]


@router.delete("/{project_id}")
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """软删除单个项目（前端已有二次确认弹窗，仅 admin/partner/manager 可操作）"""
    from fastapi import HTTPException
    if current_user.role.value not in ("admin", "partner", "manager"):
        raise HTTPException(status_code=403, detail="权限不足，仅管理员/合伙人/项目经理可删除项目")
    from sqlalchemy import select
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)  # noqa: E712
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    project.is_deleted = True
    await db.commit()
    return {"id": str(project_id), "deleted": True}


@router.post("/batch-delete")
async def batch_delete_projects(
    body: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量软删除项目（前端已有二次确认弹窗，仅 admin/partner/manager 可操作）"""
    from fastapi import HTTPException
    if current_user.role.value not in ("admin", "partner", "manager"):
        raise HTTPException(status_code=403, detail="权限不足，仅管理员/合伙人/项目经理可删除项目")
    from sqlalchemy import select, update
    count = 0
    for pid in body.project_ids:
        result = await db.execute(
            select(Project).where(Project.id == pid, Project.is_deleted == False)  # noqa: E712
        )
        p = result.scalar_one_or_none()
        if p:
            p.is_deleted = True
            count += 1
    await db.commit()
    return {"deleted_count": count, "requested": len(body.project_ids)}
