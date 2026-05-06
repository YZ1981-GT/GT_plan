"""QC 审计日志合规抽查路由 — Round 3 需求 12

GET    /api/qc/audit-log-compliance/findings     — 获取日志合规命中条目
POST   /api/qc/audit-log-compliance/run          — 手动触发日志合规规则执行
PATCH  /api/qc/audit-log-compliance/findings/{entry_id}/status — 标记审查状态

权限：role='qc' | 'admin'
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/qc/audit-log-compliance", tags=["qc-audit-log-compliance"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class AuditLogFinding(BaseModel):
    """日志合规命中条目"""

    id: str
    entry_id: str
    ts: Optional[str] = None
    action_type: str
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    ip: Optional[str] = None
    rule_code: str
    rule_title: Optional[str] = None
    severity: str
    message: str
    review_status: str = "pending"  # pending / reviewed / escalated
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None


class AuditLogComplianceResponse(BaseModel):
    """日志合规抽查结果"""

    items: list[AuditLogFinding]
    total: int


class RunComplianceRequest(BaseModel):
    """手动触发日志合规规则执行"""

    project_id: Optional[UUID] = Field(None, description="项目 ID（可选，不传则全局）")
    time_window_hours: int = Field(
        720, ge=1, le=8760, description="时间窗口（小时），默认 30 天"
    )


class UpdateFindingStatusRequest(BaseModel):
    """更新命中条目审查状态"""

    status: Literal["reviewed", "escalated"] = Field(
        ..., description="审查状态: reviewed=已审查, escalated=需上报"
    )


# ---------------------------------------------------------------------------
# In-memory store for findings (production would use a DB table)
# For this implementation, we store findings in a simple dict keyed by entry_id
# ---------------------------------------------------------------------------

# 使用模块级存储（生产环境应持久化到数据库表）
_findings_store: dict[str, dict] = {}
_findings_list: list[dict] = []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/findings")
async def get_audit_log_findings(
    project_id: Optional[UUID] = Query(None, description="按项目过滤"),
    status: Optional[str] = Query(None, description="按审查状态过滤: pending/reviewed/escalated"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页条数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin"])),
) -> dict:
    """获取日志合规命中条目列表。"""
    filtered = _findings_list

    if project_id:
        filtered = [f for f in filtered if f.get("project_id") == str(project_id)]

    if status:
        filtered = [f for f in filtered if f.get("review_status") == status]

    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    items = filtered[start:end]

    return {"items": items, "total": total}


@router.post("/run")
async def run_audit_log_compliance(
    body: RunComplianceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin"])),
) -> dict:
    """手动触发日志合规规则执行。

    对 audit_log_entries 表执行 scope='audit_log' 的 QC 规则，
    将命中条目存入 findings 列表。
    """
    import uuid
    from datetime import timedelta

    from app.models.qc_rule_models import QcRuleDefinition
    from app.services.qc_rule_executor import execute_audit_log_rule

    # 查询所有 scope='audit_log' 且 enabled 的规则
    stmt = select(QcRuleDefinition).where(
        QcRuleDefinition.scope == "audit_log",
        QcRuleDefinition.enabled == True,  # noqa: E712
    )
    # 兼容 SoftDeleteMixin
    if hasattr(QcRuleDefinition, "is_deleted"):
        stmt = stmt.where(QcRuleDefinition.is_deleted == False)  # noqa: E712

    result = await db.execute(stmt)
    rules = result.scalars().all()

    if not rules:
        return {"message": "无可用的审计日志规则", "findings_count": 0}

    # 计算时间窗口
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    time_window_start = now - timedelta(hours=body.time_window_hours)

    new_findings: list[dict] = []

    for rule in rules:
        try:
            exec_result = await execute_audit_log_rule(
                rule,
                db,
                project_id=body.project_id,
                time_window_start=time_window_start,
                time_window_end=now,
            )

            if exec_result.findings:
                for finding in exec_result.findings:
                    finding_id = str(uuid.uuid4())
                    entry = {
                        "id": finding_id,
                        "entry_id": finding.get("entry_id", ""),
                        "ts": finding.get("ts"),
                        "action_type": finding.get("action_type", ""),
                        "user_id": finding.get("user_id"),
                        "user_name": None,  # 后续可关联 User 表
                        "ip": finding.get("ip"),
                        "rule_code": rule.rule_code,
                        "rule_title": rule.title,
                        "severity": finding.get("severity", rule.severity),
                        "message": finding.get("message", ""),
                        "review_status": "pending",
                        "reviewed_by": None,
                        "reviewed_at": None,
                        "project_id": str(body.project_id) if body.project_id else None,
                    }
                    new_findings.append(entry)
                    _findings_store[finding_id] = entry

        except Exception as e:
            logger.error(
                "[AUDIT_LOG_COMPLIANCE] Rule %s execution failed: %s",
                rule.rule_code,
                e,
            )
            continue

    # 追加到全局列表（去重：同一 entry_id + rule_code 不重复）
    existing_keys = {(f["entry_id"], f["rule_code"]) for f in _findings_list}
    for f in new_findings:
        key = (f["entry_id"], f["rule_code"])
        if key not in existing_keys:
            _findings_list.append(f)
            existing_keys.add(key)

    # 按时间倒序排列
    _findings_list.sort(key=lambda x: x.get("ts") or "", reverse=True)

    return {
        "message": f"执行完成，共 {len(rules)} 条规则",
        "findings_count": len(new_findings),
        "total_findings": len(_findings_list),
    }


@router.patch("/findings/{finding_id}/status")
async def update_finding_status(
    finding_id: str,
    body: UpdateFindingStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin"])),
) -> dict:
    """标记日志合规命中条目的审查状态。"""
    from fastapi import HTTPException

    finding = _findings_store.get(finding_id)
    if not finding:
        # 也在 _findings_list 中查找
        finding = next((f for f in _findings_list if f["id"] == finding_id), None)

    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    finding["review_status"] = body.status
    finding["reviewed_by"] = str(current_user.id)
    finding["reviewed_at"] = now.isoformat()

    # 同步更新 _findings_store
    _findings_store[finding_id] = finding

    return finding


@router.get("/summary")
async def get_compliance_summary(
    project_id: Optional[UUID] = Query(None, description="按项目过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin"])),
) -> dict:
    """获取日志合规抽查摘要（用于报告生成）。"""
    filtered = _findings_list
    if project_id:
        filtered = [f for f in filtered if f.get("project_id") == str(project_id)]

    total = len(filtered)
    pending = len([f for f in filtered if f.get("review_status") == "pending"])
    reviewed = len([f for f in filtered if f.get("review_status") == "reviewed"])
    escalated = len([f for f in filtered if f.get("review_status") == "escalated"])

    # 按规则分组统计
    by_rule: dict[str, int] = {}
    for f in filtered:
        code = f.get("rule_code", "unknown")
        by_rule[code] = by_rule.get(code, 0) + 1

    # 按严重程度分组
    by_severity: dict[str, int] = {}
    for f in filtered:
        sev = f.get("severity", "info")
        by_severity[sev] = by_severity.get(sev, 0) + 1

    return {
        "total": total,
        "pending": pending,
        "reviewed": reviewed,
        "escalated": escalated,
        "by_rule": by_rule,
        "by_severity": by_severity,
        "findings": filtered[:20],  # 前 20 条用于报告摘要
    }
