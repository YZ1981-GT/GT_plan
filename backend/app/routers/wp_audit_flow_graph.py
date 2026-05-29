"""程序表流程导航图端点

GET /api/workpapers/{wp_id}/audit-flow-graph
从 schema.assertions + risk_assessment + programs + linked_workpapers 组装图数据。

锚定 spec workpaper-editor-slimdown Task 17.2 + 17.3
Validates: US-16（程序表流程导航图）
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.workpaper_models import WorkingPaper, WpIndex

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workpapers",
    tags=["wp-audit-flow-graph"],
)


# ─── Response Models ─────────────────────────────────────────────────────────


class AuditObjective(BaseModel):
    id: str
    name: str


class IdentifiedRisk(BaseModel):
    id: str
    description: str
    level: str  # 'significant' | 'normal' | 'low'
    source_wp_code: str = ""
    assertions: list[str] = []


class ProcedureNode(BaseModel):
    id: str
    program_no: int
    category: str
    status: str  # 'completed' | 'in_progress' | 'not_applicable' | 'pending'
    assertions: list[str] = []


class LinkedWorkpaper(BaseModel):
    wp_code: str
    wp_name: str
    status: str = "pending"
    exists: bool = False


class FlowEdge(BaseModel):
    from_id: str
    to_id: str
    type: str  # 'objective-risk' | 'risk-procedure' | 'procedure-workpaper'


class AuditFlowGraphResponse(BaseModel):
    objectives: list[AuditObjective]
    risks: list[IdentifiedRisk]
    procedures: list[ProcedureNode]
    workpapers: list[LinkedWorkpaper]
    edges: list[FlowEdge]


# ─── 5 项认定常量 ─────────────────────────────────────────────────────────

STANDARD_ASSERTIONS = [
    AuditObjective(id="assertion-existence", name="存在"),
    AuditObjective(id="assertion-completeness", name="完整性"),
    AuditObjective(id="assertion-rights", name="权利义务"),
    AuditObjective(id="assertion-accuracy", name="准确性"),
    AuditObjective(id="assertion-presentation", name="列报"),
]

# 认定名称 → ID 映射
_ASSERTION_ID_MAP = {
    "存在": "assertion-existence",
    "完整性": "assertion-completeness",
    "权利义务": "assertion-rights",
    "准确性": "assertion-accuracy",
    "列报": "assertion-presentation",
    # 英文 fallback
    "existence": "assertion-existence",
    "completeness": "assertion-completeness",
    "rights": "assertion-rights",
    "accuracy": "assertion-accuracy",
    "presentation": "assertion-presentation",
}


# ─── Endpoint ────────────────────────────────────────────────────────────────


@router.get("/{wp_id}/audit-flow-graph", response_model=AuditFlowGraphResponse)
async def get_audit_flow_graph(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取程序表的审计逻辑流程图数据。

    从底稿的 html_data 中提取：
    - assertions → 审计目标层
    - risk_assessment → 风险层
    - programs → 程序层
    - linked_workpapers → 底稿层
    - edges 由关联关系自动生成
    """
    # ─── 查底稿 ──────────────────────────────────────────────────────────
    wp_result = await db.execute(
        sa.select(WorkingPaper).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    working_paper = wp_result.scalars().first()
    if working_paper is None:
        raise HTTPException(status_code=404, detail="底稿不存在")

    project_id = working_paper.project_id
    parsed_data = working_paper.parsed_data or {}
    html_data = parsed_data.get("html_data", {})

    # 获取 wp_code
    wp_index_result = await db.execute(
        sa.select(WpIndex).where(WpIndex.id == working_paper.wp_index_id)
    )
    wp_index = wp_index_result.scalars().first()

    # ─── 从 html_data 提取图数据 ─────────────────────────────────────────
    # 尝试从第一个 sheet 的 html_data 中提取
    sheet_data = {}
    for sheet_name, data in html_data.items():
        if isinstance(data, dict) and data.get("programs"):
            sheet_data = data
            break

    # 如果没有 programs 数据，尝试从 schema 中获取
    if not sheet_data:
        # 返回空图（前端显示"暂无数据"）
        return AuditFlowGraphResponse(
            objectives=STANDARD_ASSERTIONS,
            risks=[],
            procedures=[],
            workpapers=[],
            edges=[],
        )

    # ─── 提取程序数据 ────────────────────────────────────────────────────
    programs_raw = sheet_data.get("programs", [])
    risk_assessment_raw = sheet_data.get("risk_assessment", [])
    assertions_raw = sheet_data.get("assertions", [])

    # 构建风险节点
    risks: list[IdentifiedRisk] = []
    for idx, risk in enumerate(risk_assessment_raw):
        if isinstance(risk, dict):
            risk_assertions = risk.get("assertions", [])
            if isinstance(risk_assertions, str):
                risk_assertions = [a.strip() for a in risk_assertions.split(",") if a.strip()]
            risks.append(IdentifiedRisk(
                id=f"risk-{idx}",
                description=risk.get("description", f"风险 {idx + 1}"),
                level=risk.get("level", "normal"),
                source_wp_code=risk.get("source_wp_code", ""),
                assertions=risk_assertions,
            ))

    # 构建程序节点
    procedures: list[ProcedureNode] = []
    linked_wp_codes: set[str] = set()

    for idx, prog in enumerate(programs_raw):
        if not isinstance(prog, dict):
            continue

        prog_assertions = prog.get("assertions", [])
        if isinstance(prog_assertions, str):
            prog_assertions = [a.strip() for a in prog_assertions.split(",") if a.strip()]

        status = prog.get("status", "pending")
        # 标准化 status
        if status in ("completed", "done", "已完成"):
            status = "completed"
        elif status in ("in_progress", "进行中"):
            status = "in_progress"
        elif status in ("not_applicable", "trimmed", "已裁剪"):
            status = "not_applicable"
        else:
            status = "pending"

        procedures.append(ProcedureNode(
            id=f"proc-{idx}",
            program_no=prog.get("program_no", idx + 1),
            category=prog.get("category", "常规★"),
            status=status,
            assertions=prog_assertions,
        ))

        # 收集关联底稿
        linked = prog.get("linked_workpapers", [])
        if isinstance(linked, list):
            for wp_ref in linked:
                if isinstance(wp_ref, str):
                    linked_wp_codes.add(wp_ref)
                elif isinstance(wp_ref, dict):
                    code = wp_ref.get("wp_code", "")
                    if code:
                        linked_wp_codes.add(code)

    # ─── 查询关联底稿存在性 ──────────────────────────────────────────────
    workpapers: list[LinkedWorkpaper] = []
    if linked_wp_codes:
        existing_result = await db.execute(
            sa.select(WpIndex.wp_code, WpIndex.wp_name).where(
                WpIndex.project_id == project_id,
                WpIndex.wp_code.in_(list(linked_wp_codes)),
                WpIndex.is_deleted == sa.false(),
            )
        )
        existing_map = {row.wp_code: row.wp_name for row in existing_result}

        for code in sorted(linked_wp_codes):
            workpapers.append(LinkedWorkpaper(
                wp_code=code,
                wp_name=existing_map.get(code, code),
                status="exists" if code in existing_map else "not_found",
                exists=code in existing_map,
            ))

    # ─── 构建 edges ──────────────────────────────────────────────────────
    edges: list[FlowEdge] = []

    # objective → risk edges (based on risk's assertions)
    for risk in risks:
        if risk.assertions:
            for assertion_name in risk.assertions:
                obj_id = _ASSERTION_ID_MAP.get(assertion_name)
                if obj_id:
                    edges.append(FlowEdge(from_id=obj_id, to_id=risk.id, type="objective-risk"))
        else:
            # No assertions specified → connect to all objectives (fallback)
            for obj in STANDARD_ASSERTIONS:
                edges.append(FlowEdge(from_id=obj.id, to_id=risk.id, type="objective-risk"))

    # risk → procedure edges (based on shared assertions)
    for proc in procedures:
        if not proc.assertions:
            continue
        proc_assertion_set = set(proc.assertions)
        for risk in risks:
            risk_assertion_set = set(risk.assertions) if risk.assertions else set()
            # Connect if they share at least one assertion
            if risk_assertion_set & proc_assertion_set:
                edges.append(FlowEdge(from_id=risk.id, to_id=proc.id, type="risk-procedure"))
            elif not risk_assertion_set:
                # Risk has no assertions → connect to all procedures (fallback)
                edges.append(FlowEdge(from_id=risk.id, to_id=proc.id, type="risk-procedure"))

    # procedure → workpaper edges
    for proc_idx, prog in enumerate(programs_raw):
        if not isinstance(prog, dict):
            continue
        linked = prog.get("linked_workpapers", [])
        if isinstance(linked, list):
            for wp_ref in linked:
                code = wp_ref if isinstance(wp_ref, str) else wp_ref.get("wp_code", "") if isinstance(wp_ref, dict) else ""
                if code:
                    edges.append(FlowEdge(
                        from_id=f"proc-{proc_idx}",
                        to_id=f"wp-{code}",
                        type="procedure-workpaper",
                    ))

    return AuditFlowGraphResponse(
        objectives=STANDARD_ASSERTIONS,
        risks=risks,
        procedures=procedures,
        workpapers=workpapers,
        edges=edges,
    )
