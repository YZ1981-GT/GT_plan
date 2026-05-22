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
from app.deps import get_current_user
from app.models.core import User
from app.services.consistency_gate import ConsistencyGate

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
    current_user: User = Depends(get_current_user),
):
    """QC 风险热力图 — 按循环×severity 聚合 VR 检查结果

    返回 11 行(D~N) × 3 列(blocking/warning/info) 矩阵 + 汇总。
    """
    gate = ConsistencyGate(db)

    # 获取项目年度（从最近的报表或默认 2025）
    from app.models.core import Project
    import sqlalchemy as sa
    proj = (await db.execute(
        sa.select(Project).where(Project.id == project_id)
    )).scalar_one_or_none()
    year = 2025  # 默认
    if proj and proj.audit_period_end:
        year = proj.audit_period_end.year

    matrix = []
    total = {"blocking": 0, "warning": 0, "info": 0}

    for cycle, methods in _CYCLE_CHECK_MAP.items():
        row = {"cycle": cycle, "blocking": 0, "warning": 0, "info": 0}
        for method_name in methods:
            method = getattr(gate, method_name, None)
            if not method:
                continue
            try:
                checks = await method(project_id, year)
                if not isinstance(checks, list):
                    checks = [checks]
                for check in checks:
                    if not check.passed:
                        sev = check.severity or "warning"
                        if sev in row:
                            row[sev] += 1
                            total[sev] += 1
            except Exception as e:
                logger.warning("VR heatmap: %s failed for cycle %s: %s", method_name, cycle, e)
                continue

        matrix.append(row)

    return {"matrix": matrix, "total": total}
