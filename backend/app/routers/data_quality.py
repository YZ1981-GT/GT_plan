"""数据质量检查端点（F7/F29/D3/D10）

GET /api/projects/{pid}/data-quality/check?checks=all|debit_credit|balance_vs_ledger|mapping|report_balance
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.data_quality_service import DataQualityService

router = APIRouter(
    prefix="/api/projects/{project_id}/data-quality",
    tags=["data-quality"],
)


@router.get("/check")
async def run_data_quality_check(
    project_id: UUID,
    checks: str = Query("all", description="要执行的检查项，逗号分隔或 all"),
    year: int = Query(2025, description="检查年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行数据质量检查套件

    checks 参数支持:
    - all: 执行全部检查
    - debit_credit_balance: 借贷平衡
    - balance_vs_ledger: 余额表 vs 序时账
    - mapping_completeness: 科目映射完整性
    - report_balance: 报表平衡
    - profit_reconciliation: 利润表勾稽

    可组合: checks=debit_credit_balance,mapping_completeness
    """
    # 映射简写到完整名称
    check_aliases = {
        "debit_credit": "debit_credit_balance",
        "mapping": "mapping_completeness",
    }

    # 处理别名
    if checks != "all":
        parts = [c.strip() for c in checks.split(",")]
        resolved = [check_aliases.get(c, c) for c in parts]
        checks = ",".join(resolved)

    service = DataQualityService(db)
    result = await service.run_checks(project_id, year, checks)
    return result
