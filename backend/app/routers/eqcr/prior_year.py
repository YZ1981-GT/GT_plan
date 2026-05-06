"""EQCR 历年对比 + 组成部分审计师聚合"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import Project, User

from .schemas import LinkPriorYearRequest

router = APIRouter()


@router.get("/projects/{project_id}/prior-year-comparison")
async def get_prior_year_comparison(
    project_id: UUID,
    years: int = 3,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取历年 EQCR 意见对比（需求 7）。

    使用 client_names_match 进行归一化匹配，兼容名称变体。
    """
    from app.models.eqcr_models import EqcrOpinion
    from app.services.client_lookup import client_names_match, normalize_client_name

    proj_q = select(Project).where(
        Project.id == project_id,
        Project.is_deleted == False,  # noqa: E712
    )
    project = (await db.execute(proj_q)).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    client_name = project.client_name
    current_year = (
        project.audit_period_end.year if project.audit_period_end else None
    )

    # 使用 client_names_match 进行归一化匹配
    candidates_q = (
        select(Project)
        .where(
            Project.id != project_id,
            Project.is_deleted == False,  # noqa: E712
        )
        .order_by(Project.audit_period_end.desc())
    )
    all_candidates = list((await db.execute(candidates_q)).scalars().all())

    prior_projects = [
        p for p in all_candidates
        if client_names_match(p.client_name, client_name)
    ][:years]

    # 获取当前项目的 EQCR 意见
    current_opinions_q = select(EqcrOpinion).where(
        EqcrOpinion.project_id == project_id,
        EqcrOpinion.is_deleted == False,  # noqa: E712
    )
    current_opinions = list((await db.execute(current_opinions_q)).scalars().all())
    current_by_domain: dict = {}
    for op in current_opinions:
        if op.domain not in current_by_domain:
            current_by_domain[op.domain] = {
                "verdict": op.verdict,
                "comment": op.comment,
                "created_at": op.created_at.isoformat() if op.created_at else None,
            }

    # 获取历年项目的 EQCR 意见
    prior_data = []
    for pp in prior_projects:
        pp_opinions_q = select(EqcrOpinion).where(
            EqcrOpinion.project_id == pp.id,
            EqcrOpinion.is_deleted == False,  # noqa: E712
        )
        pp_opinions = list((await db.execute(pp_opinions_q)).scalars().all())
        pp_by_domain: dict = {}
        for op in pp_opinions:
            if op.domain not in pp_by_domain:
                pp_by_domain[op.domain] = {
                    "verdict": op.verdict,
                    "comment": op.comment,
                    "created_at": op.created_at.isoformat() if op.created_at else None,
                }

        pp_year = pp.audit_period_end.year if pp.audit_period_end else None
        prior_data.append({
            "project_id": str(pp.id),
            "project_name": pp.name,
            "year": pp_year,
            "opinions_by_domain": pp_by_domain,
        })

    # 计算差异点
    differences = []
    domains = ["materiality", "estimate", "related_party", "going_concern", "opinion_type"]
    for domain in domains:
        current_verdict = current_by_domain.get(domain, {}).get("verdict")
        for pp_item in prior_data:
            prior_verdict = pp_item["opinions_by_domain"].get(domain, {}).get("verdict")
            if current_verdict and prior_verdict and current_verdict != prior_verdict:
                differences.append({
                    "domain": domain,
                    "current_verdict": current_verdict,
                    "prior_verdict": prior_verdict,
                    "prior_year": pp_item["year"],
                    "prior_project_id": pp_item["project_id"],
                })

    # 如果精确匹配无结果，提示手动关联
    match_method = "client_names_match" if prior_projects else "manual_link_suggested"

    return {
        "project_id": str(project_id),
        "client_name": client_name,
        "current_year": current_year,
        "current_opinions": current_by_domain,
        "prior_years": prior_data,
        "differences": differences,
        "has_differences": len(differences) > 0,
        "match_method": match_method,
    }


@router.post("/projects/{project_id}/link-prior-year")
async def link_prior_year(
    project_id: UUID,
    payload: LinkPriorYearRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动指定上年项目（兜底，当 client_name 匹配失败时使用）。"""
    from app.models.eqcr_models import EqcrOpinion

    proj_q = select(Project).where(
        Project.id == project_id,
        Project.is_deleted == False,  # noqa: E712
    )
    project = (await db.execute(proj_q)).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="当前项目不存在")

    prior_q = select(Project).where(
        Project.id == payload.prior_project_id,
        Project.is_deleted == False,  # noqa: E712
    )
    prior_project = (await db.execute(prior_q)).scalar_one_or_none()
    if prior_project is None:
        raise HTTPException(status_code=404, detail="指定的上年项目不存在")

    pp_opinions_q = select(EqcrOpinion).where(
        EqcrOpinion.project_id == payload.prior_project_id,
        EqcrOpinion.is_deleted == False,  # noqa: E712
    )
    pp_opinions = list((await db.execute(pp_opinions_q)).scalars().all())
    pp_by_domain: dict = {}
    for op in pp_opinions:
        if op.domain not in pp_by_domain:
            pp_by_domain[op.domain] = {
                "verdict": op.verdict,
                "comment": op.comment,
                "created_at": op.created_at.isoformat() if op.created_at else None,
            }

    pp_year = prior_project.audit_period_end.year if prior_project.audit_period_end else None

    return {
        "linked": True,
        "prior_project_id": str(prior_project.id),
        "prior_project_name": prior_project.name,
        "prior_year": pp_year,
        "opinions_by_domain": pp_by_domain,
    }


@router.get("/projects/{project_id}/component-auditors")
async def get_eqcr_component_auditors(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """EQCR 视角的组成部分审计师聚合（需求 11）。"""
    from app.models.consolidation_models import (
        ComponentAuditor,
        ComponentInstruction,
        ComponentResult,
    )
    from app.models.eqcr_models import EqcrOpinion

    auditors_q = (
        select(ComponentAuditor)
        .where(
            ComponentAuditor.project_id == project_id,
            ComponentAuditor.is_deleted == False,  # noqa: E712
        )
        .order_by(ComponentAuditor.company_code)
    )
    auditors = list((await db.execute(auditors_q)).scalars().all())

    opinions_q = select(EqcrOpinion).where(
        EqcrOpinion.project_id == project_id,
        EqcrOpinion.domain == "component_auditor",
        EqcrOpinion.is_deleted == False,  # noqa: E712
    )
    opinions = list((await db.execute(opinions_q)).scalars().all())
    opinions_by_auditor: dict[str, list] = {}
    for op in opinions:
        aid = (op.extra_payload or {}).get("auditor_id", "")
        opinions_by_auditor.setdefault(aid, []).append(op)

    result = []
    for a in auditors:
        instr_q = select(ComponentInstruction).where(
            ComponentInstruction.component_auditor_id == a.id,
            ComponentInstruction.is_deleted == False,  # noqa: E712
        )
        instructions = list((await db.execute(instr_q)).scalars().all())

        res_q = select(ComponentResult).where(
            ComponentResult.component_auditor_id == a.id,
            ComponentResult.is_deleted == False,  # noqa: E712
        )
        results = list((await db.execute(res_q)).scalars().all())

        auditor_opinions = opinions_by_auditor.get(str(a.id), [])

        result.append({
            "id": str(a.id),
            "company_code": a.company_code,
            "firm_name": a.firm_name,
            "contact_person": a.contact_person,
            "competence_rating": a.competence_rating.value if a.competence_rating else None,
            "rating_basis": a.rating_basis,
            "independence_confirmed": a.independence_confirmed,
            "independence_date": str(a.independence_date) if a.independence_date else None,
            "instruction_count": len(instructions),
            "result_count": len(results),
            "eqcr_opinions": [
                {
                    "id": str(op.id),
                    "verdict": op.verdict,
                    "comment": op.comment,
                    "created_at": op.created_at.isoformat() if op.created_at else None,
                }
                for op in auditor_opinions
            ],
        })

    return {
        "project_id": str(project_id),
        "auditors": result,
        "total_count": len(result),
    }
