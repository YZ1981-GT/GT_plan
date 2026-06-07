"""质控闭环工作台 — P2-1 实现

聚合 QC 规则命中、抽查任务、问题整改、质量趋势；
QC 问题关联底稿、单元格、附件、复核记录；
问题状态流：identified → assigned → responded → verified → closed；
关闭问题必须填写依据或 EvidenceRef。

Requirements: 3.1, 3.2, 3.3
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.evidence_ref import EvidenceRef

logger = logging.getLogger(__name__)


# ─── 问题状态枚举 ─────────────────────────────────────────────────────────────

class QCIssueStatus(str, Enum):
    """QC 问题状态流 (Requirements 3.3)"""
    identified = "identified"
    assigned = "assigned"
    responded = "responded"
    verified = "verified"
    closed = "closed"


# 状态流转规则：当前状态 → 允许的下一步状态
_STATE_TRANSITIONS: dict[QCIssueStatus, list[QCIssueStatus]] = {
    QCIssueStatus.identified: [QCIssueStatus.assigned],
    QCIssueStatus.assigned: [QCIssueStatus.responded, QCIssueStatus.identified],
    QCIssueStatus.responded: [QCIssueStatus.verified, QCIssueStatus.assigned],
    QCIssueStatus.verified: [QCIssueStatus.closed, QCIssueStatus.assigned],
    QCIssueStatus.closed: [],  # 终态不可再流转
}


# ─── 问题关联类型 ─────────────────────────────────────────────────────────────

class QCIssueLinkType(str, Enum):
    """QC 问题关联对象类型"""
    workpaper = "workpaper"
    cell = "cell"
    attachment = "attachment"
    review_record = "review_record"


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class QCIssueLink(BaseModel):
    """问题关联对象"""
    link_type: QCIssueLinkType
    target_id: str
    label: Optional[str] = None
    route: Optional[str] = None


class QCIssueCreate(BaseModel):
    """创建 QC 问题"""
    project_id: str
    title: str
    description: Optional[str] = None
    severity: str = "medium"  # low / medium / high / critical
    assignee_id: Optional[str] = None
    links: list[QCIssueLink] = []
    issue_type_code: Optional[str] = None


class QCIssueCloseRequest(BaseModel):
    """关闭 QC 问题请求 — 必须有 evidence_ref 或 justification (Property 4)"""
    evidence_ref: Optional[EvidenceRef] = None
    justification: Optional[str] = None

    @model_validator(mode="after")
    def _require_evidence_or_justification(self) -> "QCIssueCloseRequest":
        """Property 4: 重大问题不可无依据关闭。"""
        if not self.evidence_ref and not self.justification:
            raise ValueError(
                "关闭 QC 问题必须提供 evidence_ref 或 justification"
            )
        return self


class QCIssueTransition(BaseModel):
    """状态流转请求"""
    target_status: QCIssueStatus
    comment: Optional[str] = None
    assignee_id: Optional[str] = None
    evidence_ref: Optional[EvidenceRef] = None
    justification: Optional[str] = None


# ─── 问题内存模型（P2 不建新表，用内存聚合 + 现有 QC 数据） ─────────────────────

class QCIssue:
    """QC 问题实体 — 内存聚合模型"""

    def __init__(
        self,
        *,
        id: str | None = None,
        project_id: str,
        title: str,
        description: str | None = None,
        status: QCIssueStatus = QCIssueStatus.identified,
        severity: str = "medium",
        creator_id: str | None = None,
        assignee_id: str | None = None,
        links: list[dict[str, Any]] | None = None,
        evidence_ref: dict[str, Any] | None = None,
        justification: str | None = None,
        issue_type_code: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        closed_at: datetime | None = None,
    ):
        self.id = id or str(uuid4())
        self.project_id = project_id
        self.title = title
        self.description = description
        self.status = status
        self.severity = severity
        self.creator_id = creator_id
        self.assignee_id = assignee_id
        self.links = links or []
        self.evidence_ref = evidence_ref
        self.justification = justification
        self.issue_type_code = issue_type_code
        now = datetime.now(timezone.utc)
        self.created_at = created_at or now
        self.updated_at = updated_at or now
        self.closed_at = closed_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "severity": self.severity,
            "creator_id": self.creator_id,
            "assignee_id": self.assignee_id,
            "links": self.links,
            "evidence_ref": self.evidence_ref,
            "justification": self.justification,
            "issue_type_code": self.issue_type_code,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
        }


# ─── 状态机 ───────────────────────────────────────────────────────────────────

def can_transition(current: QCIssueStatus, target: QCIssueStatus) -> bool:
    """检查状态流转是否合法。"""
    allowed = _STATE_TRANSITIONS.get(current, [])
    return target in allowed


def validate_close_requirements(
    issue: QCIssue,
    evidence_ref: EvidenceRef | None = None,
    justification: str | None = None,
) -> tuple[bool, str]:
    """验证关闭条件：必须有 evidence_ref 或 justification。

    Returns:
        (is_valid, error_message)
    """
    if not evidence_ref and not justification:
        return False, "关闭 QC 问题必须提供 evidence_ref 或 justification"
    return True, ""


# ─── 质控闭环工作台服务 ────────────────────────────────────────────────────────

class QCWorkbenchService:
    """质控闭环工作台服务

    聚合 QC 规则命中、抽查任务、问题整改、质量趋势。
    QC 问题关联底稿、单元格、附件、复核记录。
    实现 identified → assigned → responded → verified → closed 状态流。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── P2-1.1 聚合 QC 规则命中、抽查任务、问题整改、质量趋势 ────────

    async def get_qc_workbench(self, project_id: UUID) -> dict[str, Any]:
        """聚合 QC 工作台全部数据。"""
        from app.services.qc_dashboard_service import QCDashboardService

        qc_svc = QCDashboardService(self.db)

        # QC 总览（规则命中、通过率等）
        try:
            overview = await qc_svc.get_overview(project_id)
        except Exception as e:
            logger.warning(f"[QCWorkbench] overview fetch failed: {e}")
            overview = {"total": 0, "qc_passed": 0, "qc_blocking": 0}

        # 质量趋势：基于 QC 通过率
        quality_trend = self._compute_quality_trend(overview)

        return {
            "project_id": str(project_id),
            "sections": [
                {
                    "id": "qc_rule_hits",
                    "title": "QC 规则命中",
                    "data": {
                        "total_checked": overview.get("qc_checked", 0),
                        "blocking": overview.get("qc_blocking", 0),
                        "pass_rate": overview.get("qc_pass_rate", 0),
                        "recent_failures": overview.get("recent_failures", [])[:5],
                    },
                },
                {
                    "id": "issue_rectification",
                    "title": "问题整改",
                    "data": {
                        "review_distribution": overview.get("review_distribution", {}),
                    },
                },
                {
                    "id": "quality_trend",
                    "title": "质量趋势",
                    "data": quality_trend,
                },
                {
                    "id": "cycle_matrix",
                    "title": "循环质量矩阵",
                    "data": overview.get("cycle_matrix", {}),
                },
            ],
        }

    def _compute_quality_trend(self, overview: dict[str, Any]) -> dict[str, Any]:
        """简单质量趋势摘要。"""
        pass_rate = overview.get("qc_pass_rate", 0)
        if pass_rate >= 90:
            trend_label = "良好"
        elif pass_rate >= 70:
            trend_label = "需关注"
        else:
            trend_label = "需整改"

        return {
            "current_pass_rate": pass_rate,
            "trend_label": trend_label,
            "total": overview.get("total", 0),
        }

    # ─── P2-1.2 QC 问题关联底稿、单元格、附件、复核记录 ─────────────────

    def build_issue_links(
        self,
        project_id: str,
        *,
        workpaper_id: str | None = None,
        cell_ref: str | None = None,
        attachment_id: str | None = None,
        review_record_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """构建 QC 问题关联列表。"""
        links = []
        if workpaper_id:
            links.append({
                "link_type": QCIssueLinkType.workpaper.value,
                "target_id": workpaper_id,
                "label": f"底稿 {workpaper_id[:8]}",
                "route": f"/projects/{project_id}/workpapers/{workpaper_id}/edit",
            })
        if cell_ref:
            links.append({
                "link_type": QCIssueLinkType.cell.value,
                "target_id": cell_ref,
                "label": f"单元格 {cell_ref}",
                "route": f"/projects/{project_id}/workpapers/{workpaper_id}/edit#cell={cell_ref}" if workpaper_id else None,
            })
        if attachment_id:
            links.append({
                "link_type": QCIssueLinkType.attachment.value,
                "target_id": attachment_id,
                "label": f"附件 {attachment_id[:8]}",
                "route": f"/projects/{project_id}/attachments/{attachment_id}",
            })
        if review_record_id:
            links.append({
                "link_type": QCIssueLinkType.review_record.value,
                "target_id": review_record_id,
                "label": f"复核记录 {review_record_id[:8]}",
                "route": f"/projects/{project_id}/review-conversations",
            })
        return links

    # ─── P2-1.3 问题状态流转 ──────────────────────────────────────────────

    def transition_issue(
        self,
        issue: QCIssue,
        transition: QCIssueTransition,
    ) -> tuple[bool, str]:
        """执行问题状态流转。

        Returns:
            (success, error_message)
        """
        current = issue.status
        target = transition.target_status

        # 检查流转合法性
        if not can_transition(current, target):
            return False, (
                f"不允许从 {current.value} 流转到 {target.value}。"
                f"允许的目标状态: {[s.value for s in _STATE_TRANSITIONS.get(current, [])]}"
            )

        # P2-1.4: 关闭必须有依据
        if target == QCIssueStatus.closed:
            valid, err = validate_close_requirements(
                issue,
                evidence_ref=transition.evidence_ref,
                justification=transition.justification,
            )
            if not valid:
                return False, err
            # 记录关闭依据
            if transition.evidence_ref:
                issue.evidence_ref = transition.evidence_ref.model_dump()
            if transition.justification:
                issue.justification = transition.justification
            issue.closed_at = datetime.now(timezone.utc)

        # 执行流转
        issue.status = target
        issue.updated_at = datetime.now(timezone.utc)

        # 分配责任人
        if transition.assignee_id and target == QCIssueStatus.assigned:
            issue.assignee_id = transition.assignee_id

        return True, ""

    # ─── P2-1.4 关闭问题验证 ─────────────────────────────────────────────

    def close_issue(
        self,
        issue: QCIssue,
        close_request: QCIssueCloseRequest,
    ) -> tuple[bool, str]:
        """关闭 QC 问题 — 必须提供依据 (Property 4)。

        先验证当前状态是否允许关闭（只有 verified 可以 close），
        再验证关闭依据。
        """
        if issue.status != QCIssueStatus.verified:
            return False, (
                f"只有 verified 状态的问题可以关闭，当前状态: {issue.status.value}"
            )

        transition = QCIssueTransition(
            target_status=QCIssueStatus.closed,
            evidence_ref=close_request.evidence_ref,
            justification=close_request.justification,
        )
        return self.transition_issue(issue, transition)

    # ─── 创建问题 ─────────────────────────────────────────────────────────

    def create_issue(self, create_req: QCIssueCreate, creator_id: str) -> QCIssue:
        """创建新的 QC 问题。"""
        issue = QCIssue(
            project_id=create_req.project_id,
            title=create_req.title,
            description=create_req.description,
            severity=create_req.severity,
            creator_id=creator_id,
            assignee_id=create_req.assignee_id,
            links=[link.model_dump() for link in create_req.links],
            issue_type_code=create_req.issue_type_code,
        )

        # 若指定了 assignee，直接进入 assigned 状态
        if create_req.assignee_id:
            issue.status = QCIssueStatus.assigned

        return issue
