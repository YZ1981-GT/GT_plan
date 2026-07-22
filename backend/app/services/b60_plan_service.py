# -*- coding: utf-8 -*-
"""B60 适用性矩阵 / 计划版本 / 缺附件生成 / SCOT 行 / 质控

Source of truth:
  Project.wizard_state.b60_attachment_flags
  Project.wizard_state.b60_scot_rows
  Project.wizard_state.b60d_archive
  AuditPlan.plan_version

Service only flushes; router commits.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.core import Project
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus

logger = logging.getLogger(__name__)

_PLATFORM_FIELDS = Path(__file__).resolve().parents[2] / "data" / "wp_platform_fields" / "B60.json"
_MAPPING_PATH = Path(__file__).resolve().parents[2] / "data" / "wp_account_mapping.json"

FLAG_DEFS: dict[str, dict] = {
    "integrated_audit": {"label": "整合审计 / 仅内控审计", "wp_codes": ["B60A"]},
    "listed_or_ipo": {"label": "IPO / 申报或上市年审特殊考虑", "wp_codes": ["B60B"]},
    "soe_annual": {"label": "国有企业年度财务报表审计", "wp_codes": ["B60C"]},
    "needs_regulatory_filing": {"label": "需向监管机构报送审计计划", "wp_codes": ["B60D"]},
    "needs_it_audit": {"label": "适用 IT 审计", "wp_codes": ["B60-2-1"]},
    "it_team_executes": {"label": "IT 团队执行测试", "wp_codes": ["B60-2-2", "B60-2-3"]},
    "uses_expert": {"label": "利用评估（或其他）专家", "wp_codes": ["B60-3"]},
}

ALWAYS_REQUIRED = ["B60", "B60-1"]

WP_FALLBACK_NAMES = {
    "B60": "总体审计策略及具体审计计划",
    "B60-1": "审计项目工时预算与控制表",
    "B60-2-1": "IT复杂性判断表",
    "B60-2-2": "IT审计进场前通知表",
    "B60-2-3": "IT审计计划备忘录",
    "B60-3": "评估专家工作计划",
    "B60A": "对内控审计的特殊考虑",
    "B60B": "对IPO申报财务报表审计的特殊考虑",
    "B60C": "对国有企业年度财务报表审计的特殊考虑",
    "B60D": "向监管机构报送总体审计策略和具体审计计划的函副本",
}

# 非 PIE 默认可折叠/标不适用的章节（主稿）
NON_PIE_COLLAPSE_SECTIONS = [
    {"id": "ch9_kam", "title": "九、关键审计事项", "default": "不适用可删除"},
    {"id": "ch13_other_info", "title": "十三、其他信息", "default": "不适用可删除"},
    {"id": "ch4_peer", "title": "四、（二）同行业公司对比分析", "default": "非证券期货业务可删除"},
    {"id": "ch4_nonfin", "title": "四、（三）财务与非财务信息印证", "default": "非证券期货业务可删除"},
]

MUST_KEEP_SECTIONS = ["一、审计工作范围", "三、审计安排", "五、重要性", "六、重大错报风险", "七、SCOT+", "十五、计划更新"]


class AttachmentFlagsPayload(BaseModel):
    flags: dict[str, bool] = Field(default_factory=dict)
    materiality_reference: str | None = None
    auto_generate_missing: bool = True


class MissingAttachment(BaseModel):
    flag: str
    flag_label: str
    wp_code: str
    present: bool


class SimplificationHint(BaseModel):
    is_pie: bool
    collapse_sections: list[dict] = Field(default_factory=list)
    must_keep_sections: list[str] = Field(default_factory=list)
    note: str = ""


class AttachmentFlagsResponse(BaseModel):
    flags: dict[str, bool]
    flag_defs: dict[str, dict]
    missing_attachments: list[MissingAttachment]
    always_required_missing: list[str]
    materiality_reference: str | None = None
    plan_version: int | None = None
    generated_wp_codes: list[str] = Field(default_factory=list)
    simplification: SimplificationHint | None = None
    scot_rows: list[dict] = Field(default_factory=list)
    b60d_archive: dict | None = None


class PlanUpdatePayload(BaseModel):
    reason: str | None = Field(default=None, description="第十五章更新理由摘要")
    bump_version: bool = True
    confirm_major_change: bool = False
    materiality_reference: str | None = None
    flags: dict[str, bool] | None = None


class PlanUpdateResponse(BaseModel):
    plan_version: int
    materiality_reference: str | None = None
    flags: dict[str, bool]
    reason: str | None = None


class ScotRow(BaseModel):
    scot_id: str = ""
    name: str = ""
    cycle_code: str = ""
    risk_id: str = ""
    procedure_wp_index: str = ""
    rely_on_controls: str = ""  # 是/否/待测


class ScotRowsPayload(BaseModel):
    rows: list[ScotRow] = Field(default_factory=list)


class ScotRowsResponse(BaseModel):
    rows: list[dict]


class B60dArchivePayload(BaseModel):
    filed_plan_version: int
    delivery_date: str | None = None
    recipient: str | None = None
    delivery_method: str | None = None
    consistent_with_b60: bool = True


class B60dArchiveResponse(BaseModel):
    archive: dict
    plan_version: int | None = None
    version_match: bool | None = None


class QcFinding(BaseModel):
    code: str
    severity: str
    message: str
    suggested_action: str = ""
    location: dict = Field(default_factory=dict)


class QcStatusResponse(BaseModel):
    findings: list[QcFinding]
    flags: dict[str, bool]
    plan_version: int | None = None
    materiality_reference: str | None = None


def _load_platform_attachment_map() -> dict[str, list[str]]:
    try:
        raw = json.loads(_PLATFORM_FIELDS.read_text(encoding="utf-8"))
        out: dict[str, list[str]] = {}
        for k, v in (raw.get("attachment_flags") or {}).items():
            codes = v.get("wp_codes") if isinstance(v, dict) else None
            if codes:
                out[k] = list(codes)
        return out or {k: v["wp_codes"] for k, v in FLAG_DEFS.items()}
    except Exception:
        return {k: v["wp_codes"] for k, v in FLAG_DEFS.items()}


def _wp_name_lookup() -> dict[str, str]:
    names = dict(WP_FALLBACK_NAMES)
    try:
        data = json.loads(_MAPPING_PATH.read_text(encoding="utf-8"))
        for m in data.get("mappings") or []:
            code = m.get("wp_code")
            name = m.get("wp_name")
            if code and name:
                names[code] = name
    except Exception:
        pass
    return names


def default_flags_from_project(project: Project) -> dict[str, bool]:
    audit_type = str(project.audit_type or "").lower()
    scenario = str(project.scenario or "")
    template_type = str(project.template_type or "")
    integrated = (
        "integrated" in audit_type
        or "内控" in str(project.audit_type or "")
        or "icfr" in audit_type
        or "integrated" in scenario.lower()
    )
    listed_or_ipo = template_type == "listed" or scenario in ("ipo", "listed")
    return {
        "integrated_audit": integrated,
        "listed_or_ipo": listed_or_ipo,
        "soe_annual": template_type == "soe",
        "needs_regulatory_filing": listed_or_ipo,
        "needs_it_audit": False,
        "it_team_executes": False,
        "uses_expert": False,
    }


def is_pie_project(project: Project) -> bool:
    template_type = str(project.template_type or "")
    scenario = str(project.scenario or "")
    bc = str(getattr(project, "business_category", None) or "")
    if template_type == "listed" or scenario in ("ipo", "listed"):
        return True
    if bc.upper().startswith("A"):
        return True
    return False


def simplification_for_project(project: Project) -> SimplificationHint:
    pie = is_pie_project(project)
    if pie:
        return SimplificationHint(
            is_pie=True,
            collapse_sections=[],
            must_keep_sections=MUST_KEEP_SECTIONS,
            note="公众利益实体/上市或 IPO：完整适用各章；不适用项仍须显式标注。",
        )
    return SimplificationHint(
        is_pie=False,
        collapse_sections=list(NON_PIE_COLLAPSE_SECTIONS),
        must_keep_sections=MUST_KEEP_SECTIONS,
        note="非 PIE：可将下列章节标「不适用」或删除；一/三/五/六/七/十五不可省略。",
    )


def normalize_flags(raw: dict | None, *, defaults: dict[str, bool] | None = None) -> dict[str, bool]:
    base = dict(defaults or {k: False for k in FLAG_DEFS})
    if isinstance(raw, dict):
        for k in FLAG_DEFS:
            if k in raw and isinstance(raw[k], bool):
                base[k] = raw[k]
    if base.get("it_team_executes"):
        base["needs_it_audit"] = True
    return base


async def _get_project(db: AsyncSession, project_id: UUID) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


async def _existing_wp_codes(db: AsyncSession, project_id: UUID) -> set[str]:
    result = await db.execute(
        select(WpIndex.wp_code).where(
            WpIndex.project_id == project_id,
            WpIndex.is_deleted.is_(False),
        )
    )
    return {r[0] for r in result.all() if r[0]}


async def _get_or_create_audit_plan(db: AsyncSession, project_id: UUID):
    from app.models.collaboration_models import AuditPlan

    result = await db.execute(select(AuditPlan).where(AuditPlan.project_id == project_id))
    plan = result.scalar_one_or_none()
    if plan is None:
        plan = AuditPlan(project_id=project_id, plan_version=1)
        db.add(plan)
        await db.flush()
    return plan


async def ensure_workpapers_for_codes(
    project_id: UUID, codes: list[str], db: AsyncSession
) -> list[str]:
    """幂等创建缺失的 WpIndex + WorkingPaper + 模板文件。返回新创建的 wp_code 列表。"""
    from app.services.wp_template_init_service import init_workpaper_from_template

    if not codes:
        return []
    project = await _get_project(db, project_id)
    existing = await _existing_wp_codes(db, project_id)
    names = _wp_name_lookup()
    scenario = str(project.scenario or "normal")
    has_fc = bool(getattr(project, "has_foreign_currency", False))
    created: list[str] = []

    for code in codes:
        if code in existing:
            continue
        try:
            wp_index = WpIndex(
                project_id=project_id,
                wp_code=code,
                wp_name=names.get(code) or f"底稿{code}",
                audit_cycle="B",
                status=WpStatus.not_started,
            )
            db.add(wp_index)
            await db.flush()
            wp = WorkingPaper(
                wp_index_id=wp_index.id,
                project_id=project_id,
                source_type=WpSourceType.template,
                file_path=f"storage/projects/{project_id}/workpapers/{code}",
                parsed_data={},
            )
            db.add(wp)
            await db.flush()
            try:
                actual_path = init_workpaper_from_template(
                    project_id=project_id,
                    wp_id=wp.id,
                    wp_code=code,
                    scenario=scenario,
                    has_foreign_currency=has_fc,
                )
                if actual_path is not None:
                    wp.file_path = str(actual_path)
            except Exception as e:
                logger.warning("B60 ensure template copy failed for %s: %s", code, e)
            created.append(code)
            existing.add(code)
        except Exception as e:
            logger.warning("B60 ensure_workpapers failed for %s: %s", code, e)
    return created


async def evaluate_missing_attachments(
    project_id: UUID, flags: dict[str, bool], db: AsyncSession
) -> list[MissingAttachment]:
    existing = await _existing_wp_codes(db, project_id)
    flag_to_codes = _load_platform_attachment_map()
    out: list[MissingAttachment] = []
    for flag, enabled in flags.items():
        if not enabled:
            continue
        codes = flag_to_codes.get(flag) or FLAG_DEFS.get(flag, {}).get("wp_codes") or []
        label = FLAG_DEFS.get(flag, {}).get("label", flag)
        for code in codes:
            out.append(
                MissingAttachment(
                    flag=flag,
                    flag_label=label,
                    wp_code=code,
                    present=code in existing,
                )
            )
    return out


async def get_attachment_flags(project_id: UUID, db: AsyncSession) -> AttachmentFlagsResponse:
    project = await _get_project(db, project_id)
    defaults = default_flags_from_project(project)
    ws = project.wizard_state or {}
    stored = ws.get("b60_attachment_flags") or ws.get("attachment_flags") or {}
    flags = normalize_flags(stored if stored else None, defaults=defaults)
    if not stored:
        flags = defaults

    plan = None
    try:
        from app.models.collaboration_models import AuditPlan

        result = await db.execute(select(AuditPlan).where(AuditPlan.project_id == project_id))
        plan = result.scalar_one_or_none()
    except Exception:
        plan = None

    missing = await evaluate_missing_attachments(project_id, flags, db)
    always_missing = [c for c in ALWAYS_REQUIRED if c not in await _existing_wp_codes(db, project_id)]
    scot_rows = ws.get("b60_scot_rows") if isinstance(ws.get("b60_scot_rows"), list) else []
    archive = ws.get("b60d_archive") if isinstance(ws.get("b60d_archive"), dict) else None

    return AttachmentFlagsResponse(
        flags=flags,
        flag_defs={k: {"label": v["label"], "wp_codes": v["wp_codes"]} for k, v in FLAG_DEFS.items()},
        missing_attachments=missing,
        always_required_missing=always_missing,
        materiality_reference=(plan.materiality_reference if plan else None)
        or (ws.get("b60_materiality_reference") if isinstance(ws, dict) else None),
        plan_version=plan.plan_version if plan else None,
        generated_wp_codes=[],
        simplification=simplification_for_project(project),
        scot_rows=scot_rows,
        b60d_archive=archive,
    )


async def save_attachment_flags(
    project_id: UUID, payload: AttachmentFlagsPayload, db: AsyncSession
) -> AttachmentFlagsResponse:
    project = await _get_project(db, project_id)
    defaults = default_flags_from_project(project)
    ws = dict(project.wizard_state or {})
    existing_stored = ws.get("b60_attachment_flags") or ws.get("attachment_flags") or {}
    if payload.flags:
        flags = normalize_flags(payload.flags, defaults=defaults)
    else:
        flags = normalize_flags(existing_stored if existing_stored else None, defaults=defaults)

    unknown = set(payload.flags or {}) - set(FLAG_DEFS)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={"error_code": "UNKNOWN_FLAG", "detail": f"未知 flag: {sorted(unknown)}"},
        )

    ws["b60_attachment_flags"] = flags
    if payload.materiality_reference is not None:
        ws["b60_materiality_reference"] = payload.materiality_reference
    project.wizard_state = ws
    flag_modified(project, "wizard_state")

    plan = await _get_or_create_audit_plan(db, project_id)
    if payload.materiality_reference is not None:
        plan.materiality_reference = payload.materiality_reference

    await db.flush()

    generated: list[str] = []
    if payload.auto_generate_missing:
        missing = await evaluate_missing_attachments(project_id, flags, db)
        to_create = [m.wp_code for m in missing if not m.present]
        existing = await _existing_wp_codes(db, project_id)
        for c in ALWAYS_REQUIRED:
            if c not in existing and c not in to_create:
                to_create.append(c)
        generated = await ensure_workpapers_for_codes(project_id, to_create, db)
        await db.flush()

    resp = await get_attachment_flags(project_id, db)
    resp.generated_wp_codes = generated
    return resp


async def bump_plan_version(
    project_id: UUID,
    db: AsyncSession,
    *,
    reason: str | None = None,
    materiality_reference: str | None = None,
    flags: dict[str, bool] | None = None,
    confirm_major_change: bool = False,
) -> PlanUpdateResponse:
    if not confirm_major_change:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "CONFIRM_MAJOR_CHANGE_REQUIRED",
                "detail": "第十五章重大更新须确认 confirm_major_change=true",
            },
        )
    if not (reason or "").strip():
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "REASON_REQUIRED",
                "detail": "请填写第十五章更新理由（reason）",
            },
        )

    project = await _get_project(db, project_id)
    if flags is not None:
        await save_attachment_flags(
            project_id,
            AttachmentFlagsPayload(
                flags=flags,
                materiality_reference=materiality_reference,
                auto_generate_missing=False,
            ),
            db,
        )
        project = await _get_project(db, project_id)

    plan = await _get_or_create_audit_plan(db, project_id)
    plan.plan_version = int(plan.plan_version or 1) + 1
    if materiality_reference is not None:
        plan.materiality_reference = materiality_reference
    try:
        from app.models.collaboration_models import AuditPlanStatus

        plan.status = AuditPlanStatus.revised
    except Exception:
        pass

    ws = dict(project.wizard_state or {})
    ws["b60_plan_update"] = {
        "plan_version": plan.plan_version,
        "reason": reason,
        "confirmed": True,
    }
    if materiality_reference is not None:
        ws["b60_materiality_reference"] = materiality_reference
    project.wizard_state = ws
    flag_modified(project, "wizard_state")
    await db.flush()

    stored = (project.wizard_state or {}).get("b60_attachment_flags") or {}
    return PlanUpdateResponse(
        plan_version=plan.plan_version,
        materiality_reference=plan.materiality_reference,
        flags=normalize_flags(stored, defaults=default_flags_from_project(project)),
        reason=reason,
    )


async def get_scot_rows(project_id: UUID, db: AsyncSession) -> ScotRowsResponse:
    project = await _get_project(db, project_id)
    ws = project.wizard_state or {}
    rows = ws.get("b60_scot_rows") if isinstance(ws.get("b60_scot_rows"), list) else []
    return ScotRowsResponse(rows=rows)


async def save_scot_rows(
    project_id: UUID, payload: ScotRowsPayload, db: AsyncSession
) -> ScotRowsResponse:
    project = await _get_project(db, project_id)
    rows = [r.model_dump() for r in payload.rows]
    ws = dict(project.wizard_state or {})
    ws["b60_scot_rows"] = rows
    project.wizard_state = ws
    flag_modified(project, "wizard_state")
    await db.flush()
    return ScotRowsResponse(rows=rows)


async def save_b60d_archive(
    project_id: UUID, payload: B60dArchivePayload, db: AsyncSession
) -> B60dArchiveResponse:
    project = await _get_project(db, project_id)
    plan = await _get_or_create_audit_plan(db, project_id)
    archive = {
        "filed_plan_version": payload.filed_plan_version,
        "delivery_date": payload.delivery_date,
        "recipient": payload.recipient,
        "delivery_method": payload.delivery_method,
        "consistent_with_b60": payload.consistent_with_b60,
    }
    ws = dict(project.wizard_state or {})
    ws["b60d_archive"] = archive
    project.wizard_state = ws
    flag_modified(project, "wizard_state")
    await db.flush()
    match = int(payload.filed_plan_version) == int(plan.plan_version or 1)
    return B60dArchiveResponse(
        archive=archive,
        plan_version=plan.plan_version,
        version_match=match,
    )


async def evaluate_qc(project_id: UUID, db: AsyncSession) -> QcStatusResponse:
    state = await get_attachment_flags(project_id, db)
    findings: list[QcFinding] = []

    for m in state.missing_attachments:
        if not m.present:
            findings.append(
                QcFinding(
                    code="B60-ATTACH-MISSING",
                    severity="warning",
                    message=f"适用性矩阵已勾选「{m.flag_label}」，但项目中缺少底稿 {m.wp_code}",
                    suggested_action="保存矩阵并开启 auto_generate_missing，或手动生成底稿",
                    location={"flag": m.flag, "wp_code": m.wp_code},
                )
            )

    for code in state.always_required_missing:
        findings.append(
            QcFinding(
                code="B60-CORE-MISSING",
                severity="warning",
                message=f"B60 核心底稿缺失：{code}",
                suggested_action=f"请生成 {code}",
                location={"wp_code": code},
            )
        )

    mat = (state.materiality_reference or "").strip()
    if not mat:
        findings.append(
            QcFinding(
                code="B60-MATERIALITY-REF-MISSING",
                severity="warning",
                message="未填写重要性结论索引（应指向 B19-1；计算过程见 B15）",
                suggested_action="在 B60 矩阵面板填写 materiality_reference，例如「B19-1」",
                location={"field": "materiality_reference"},
            )
        )
    elif "B19" not in mat and "B15" not in mat:
        findings.append(
            QcFinding(
                code="B60-MATERIALITY-REF-WEAK",
                severity="info",
                message=f"重要性索引「{mat}」未包含 B19-1/B15，请确认是否正确",
                suggested_action="建议填写含 B19-1（结论）与/或 B15（计算）的索引",
                location={"field": "materiality_reference", "value": mat},
            )
        )

    project = await _get_project(db, project_id)
    ws = project.wizard_state or {}
    scot_rows = ws.get("b60_scot_rows")
    if isinstance(scot_rows, list) and scot_rows:
        for i, row in enumerate(scot_rows):
            if not isinstance(row, dict):
                continue
            if not row.get("cycle_code") or not row.get("risk_id"):
                findings.append(
                    QcFinding(
                        code="B60-SCOT-INCOMPLETE",
                        severity="warning",
                        message=f"SCOT+ 第 {i + 1} 行缺少循环代码或 risk_id",
                        suggested_action="补全 cycle_code / risk_id（与 B50 勾稽）",
                        location={"row": i + 1, "row_data": row},
                    )
                )
    elif state.flags.get("listed_or_ipo") or is_pie_project(project):
        findings.append(
            QcFinding(
                code="B60-SCOT-EMPTY",
                severity="info",
                message="尚未录入结构化 SCOT+ 行（可选，便于与 B50 勾稽）",
                suggested_action="在矩阵面板 SCOT+ 简表中补充行",
                location={"field": "b60_scot_rows"},
            )
        )

    # B60D version consistency (CW-422)
    if state.flags.get("needs_regulatory_filing"):
        archive = ws.get("b60d_archive") if isinstance(ws.get("b60d_archive"), dict) else None
        existing = await _existing_wp_codes(db, project_id)
        if "B60D" in existing or archive:
            filed = (archive or {}).get("filed_plan_version")
            pv = state.plan_version
            if filed is None:
                findings.append(
                    QcFinding(
                        code="B60D-VERSION-UNDECLARED",
                        severity="warning",
                        message="已启用监管报送，但未登记 B60D 报送对应的计划版本",
                        suggested_action="在矩阵面板填写 B60D 存档的 filed_plan_version",
                        location={"field": "b60d_archive.filed_plan_version"},
                    )
                )
            elif pv is not None and int(filed) != int(pv):
                findings.append(
                    QcFinding(
                        code="B60D-VERSION-MISMATCH",
                        severity="warning",
                        message=f"B60D 报送版本 v{filed} 与当前计划版本 v{pv} 不一致",
                        suggested_action="更新报送副本或将存档版本改为当前 plan_version 后重新报送",
                        location={
                            "filed_plan_version": filed,
                            "plan_version": pv,
                        },
                    )
                )

    return QcStatusResponse(
        findings=findings,
        flags=state.flags,
        plan_version=state.plan_version,
        materiality_reference=state.materiality_reference,
    )
