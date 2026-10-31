"""QC 风险热力图聚合 API — Phase 2 F2

GET /api/projects/{project_id}/qc/vr-heatmap

按循环(D~N) × severity(blocking/warning/info) 分组统计 VR 规则检查结果。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access, require_project_audit_year
from app.models.core import User
from app.services.consistency_gate import ConsistencyGate, check_status, five_state_counts, not_passed_checks

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/qc",
    tags=["QC风险热力图"],
)

# 循环→检查方法映射
_CYCLE_CHECK_MAP: dict[str, list[str]] = {
    "D": ["check_d4_revenue_reconciliation"],
    "E": ["check_e1_cfs_reconciliation"],
    "F": ["check_f5_f2_triangle_reconciliation"],
    "G": ["check_g_cycle_triangle_reconciliation"],
    "H": ["check_h_cycle_triangle_reconciliation"],
    "I": ["check_i_cycle_triangle_reconciliation"],
    "J": ["check_j_cycle_triangle_reconciliation"],
    "K": ["check_k_cycle_triangle_reconciliation"],
    "L": ["check_l_cycle_triangle_reconciliation"],
    "M": ["check_m_cycle_triangle_reconciliation"],
    "N": ["check_n_cycle_triangle_reconciliation"],
}


@router.get("/vr-heatmap")
async def get_vr_heatmap(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """QC 风险热力图 — 按循环×severity 聚合 VR 检查结果

    返回 11 行(D~N) × 3 列(blocking/warning/info) 矩阵 + 汇总。
    """
    gate = ConsistencyGate(db)

    # 获取项目审计年度（统一项目年度解析，缺失时明确返回 422）
    # 2026-10-29 整合：ADR-FHIC-14 要求「年度为空 ⇒ 422」，与 audit-year-calendar-fallback-ratchet
    # 已落地的共享 helper require_project_audit_year 同义（它在年度缺失时抛 422），取共享 helper 不另写内联分支。
    year = await require_project_audit_year(db, project_id)

    matrix = []
    total = {"blocking": 0, "warning": 0, "info": 0}
    total_status = five_state_counts([])

    for cycle, methods in _CYCLE_CHECK_MAP.items():
        row = {"cycle": cycle, "blocking": 0, "warning": 0, "info": 0}
        cycle_checks: list = []
        for method_name in methods:
            method = getattr(gate, method_name, None)
            if not method:
                continue
            try:
                checks = await method(project_id, year)
                if not isinstance(checks, list):
                    checks = [checks]
                cycle_checks.extend(checks)
                for check in checks:
                    # 严重级计数保持「失败」含义（ADR-FHIC-14 第 5 点展示行）：未执行 / 不适用 / 异常另计五态
                    if check_status(check) == "failed":
                        sev = check.severity or "warning"
                        if sev in row:
                            row[sev] += 1
                            total[sev] += 1
            except Exception as e:
                logger.warning("VR heatmap: %s failed for cycle %s: %s", method_name, cycle, e)
                continue

        row["status_counts"] = five_state_counts(cycle_checks)
        row["not_passed_checks"] = not_passed_checks(cycle_checks)
        for state, n in row["status_counts"].items():
            total_status[state] += n
        matrix.append(row)

    return {"matrix": matrix, "total": total, "status_counts": total_status}
