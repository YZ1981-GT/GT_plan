"""报表级合并穿透服务（consol-phase2-orchestration / Phase 2 衔接4 / 需求 5）.

读 `consol_trial.consolidation_breakdown` provenance（Phase 0 B1 aggregate_individual_sum
汇总时写入），反查"该合并报表科目由哪些子公司贡献多少 + 抵销额 + 合并数"，供前端
ConsolBreakdownDialog(source=report) 穿透展示（UI 留 Phase 3，后端 Phase 2 就位）。

数据契约（mirror Phase 0 consol_trial provenance / 附注穿透 notes/consol-breakdown）：
    {
      "account_code": str,
      "by_company": [{company_code, company_name, amount, ratio}],
      "elimination": str,        # consol_trial.consol_elimination
      "consolidated": str,       # consol_trial.consol_amount
      "individual_sum": str,     # consol_trial.individual_sum（has_breakdown=true 时）
      "computed_at": str | None,
      "has_breakdown": bool,
      "message": str | None,     # has_breakdown=false 时的友好提示（EH5）
    }

不重算（需求 5.2）：穿透数据全部复用 Phase 0 已落库的 consolidation_breakdown +
consol_trial 金额字段，本服务只读 + 计算占比（ratio），不调用任何重算逻辑。

S5 provenance 自洽（需求 5.3）：Σ by_company[*].amount == individual_sum 由 Phase 0 B1
汇总时保证；本端点仅原样surface，不修改金额。

错误处理（design.md §七 EH5 / 需求 5.4 / 风险 R6）：
- trial 行不存在，或 consolidation_breakdown 为空/None/无 by_company（未跑 B1）→ 返回
  空 by_company + has_breakdown=false + 中文友好提示，HTTP 200（不 404/500），不阻断前端。

Validates: Requirements 5.1, 5.2, 5.3, 5.4; Properties S5; Error scenarios EH5.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation_models import ConsolTrial

logger = logging.getLogger(__name__)

# 无合并明细时的中文友好提示（EH5）
EMPTY_BREAKDOWN_MESSAGE = "请先刷新合并数"

# 占比量化精度（4 位小数）
_RATIO_QUANT = Decimal("0.0001")


def _safe_decimal(value) -> Decimal:
    """防御性解析金额字符串/数字为 Decimal；无法解析返回 0。

    Phase 0 breakdown 的 amount 以字符串存储（避免 float 精度丢失），但老数据/
    异常数据可能是 None/空串/非法字符串，统一兜底为 Decimal("0")。
    """
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


async def get_report_consol_breakdown(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    account_code: str,
) -> dict:
    """获取某合并报表科目的子公司贡献明细（报表级穿透）.

    Args:
        db: AsyncSession
        project_id: 合并母项目 ID
        year: 报告年度
        account_code: 标准科目编码（对应 consol_trial.standard_account_code）

    Returns:
        dict：见模块 docstring 数据契约。无 breakdown 时友好空返回（HTTP 200）。
    """
    trial = await _load_trial_row(db, project_id, year, account_code)

    breakdown = trial.consolidation_breakdown if trial is not None else None
    raw_by_company = (
        breakdown.get("by_company") if isinstance(breakdown, dict) else None
    )

    # 空/None/非列表 → 友好空返回（EH5）：trial 不存在或未跑 B1
    if not raw_by_company or not isinstance(raw_by_company, list):
        return {
            "account_code": account_code,
            "by_company": [],
            "elimination": str(trial.consol_elimination) if trial is not None else "0",
            "consolidated": str(trial.consol_amount) if trial is not None else "0",
            "has_breakdown": False,
            "message": EMPTY_BREAKDOWN_MESSAGE,
        }

    # 计算各子公司占比（不改 ORM JSONB，构建新 dict 列表，避免污染 provenance）
    total = sum((_safe_decimal(c.get("amount")) for c in raw_by_company), Decimal("0"))
    augmented: list[dict] = []
    for c in raw_by_company:
        amount = _safe_decimal(c.get("amount"))
        ratio = (
            str((amount / total).quantize(_RATIO_QUANT)) if total != 0 else "0"
        )
        augmented.append(
            {
                "company_code": c.get("company_code"),
                "company_name": c.get("company_name"),
                "amount": str(amount),
                "ratio": ratio,
            }
        )

    return {
        "account_code": account_code,
        "by_company": augmented,
        "elimination": str(trial.consol_elimination),
        "consolidated": str(trial.consol_amount),
        "individual_sum": str(trial.individual_sum),
        "computed_at": breakdown.get("computed_at"),
        "has_breakdown": True,
        "message": None,
    }


async def _load_trial_row(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    account_code: str,
) -> ConsolTrial | None:
    """加载 (project_id, year, standard_account_code) 的合并试算表行（未软删）。"""
    stmt = (
        select(ConsolTrial)
        .where(
            ConsolTrial.project_id == project_id,
            ConsolTrial.year == year,
            ConsolTrial.standard_account_code == account_code,
            ConsolTrial.is_deleted.is_(False),
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
