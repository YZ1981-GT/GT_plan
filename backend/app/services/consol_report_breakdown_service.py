"""报表级合并穿透服务（consol-phase2-orchestration / Phase 2 衔接4 / 需求 5）.

两条路径（spec consol-autotree-linkage-closure R8.2）：

- 报表行次（报表页右键「查看合并明细」传的就是行次）：读时计算（``_row_breakdown`` →
  ``consol_report_view_service.child_contributions``，与报表差额表同一求值），``basis = "read_time"``，
  ``by_company`` 每行带 ``node_key / kind / source / pct / source_project_id``，``consolidated`` = 后端合计，
  ``elimination`` = 直接下级里差额节点之和；
- 纯数字科目码：读 `consol_trial.consolidation_breakdown` provenance（Phase 0 B1 aggregate_individual_sum
  汇总时写入），反查"该合并报表科目由哪些子公司贡献多少 + 抵销额 + 合并数"（下面的契约与约束只说这条路径）。

数据契约（mirror Phase 0 consol_trial provenance / 附注穿透 notes/consol-breakdown）：
    {
      "account_code": str,
      "by_company": [{company_code, company_name, amount, ratio,
                      node_key?, role?, entity_kind?, display_name?, source_project_id?}],
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
    *,
    node_key: str | None = None,
) -> dict:
    """获取某合并报表行 / 科目的下级构成（报表级穿透）.

    Args:
        db: AsyncSession
        project_id: 合并母项目 ID
        year: 报告年度
        account_code: 报表行次（如 ``BS-006``，报表页右键传的就是行次）或标准科目编码（纯数字）
        node_key: 汇总节点；省略 = 根合并节点（只对行次生效）

    Returns:
        dict：见模块 docstring 数据契约。无 breakdown 时友好空返回（HTTP 200）。

    🔴 报表页右键传的是行次，旧实现拿它按科目码查 ``consol_trial`` ⇒ 恒空（spec consol-autotree-linkage-closure
    R8.2）。行次改为读时计算，与报表差额表 / 汇总穿透同一求值；纯数字仍按科目码读已落库的穿透明细。
    """
    if not account_code.isdigit():
        by_row = await _row_breakdown(db, project_id, year, account_code, node_key=node_key)
        if by_row is not None:
            return by_row
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
        row = {
            "company_code": c.get("company_code"),
            "company_name": c.get("company_name"),
            "amount": str(amount),
            "ratio": ratio,
        }
        # 三码树溯源（spec consol-tree-three-code-autobuild 需求 5.9）：来自哪个节点（本部/分公司/子公司），
        # 以及可跳转的单户项目；旧数据没有这些键时不输出，保持旧契约
        for key in ("node_key", "role", "entity_kind", "display_name", "source_project_id"):
            if c.get(key) is not None:
                row[key] = c.get(key)
        augmented.append(row)

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


async def _row_breakdown(
    db: AsyncSession, project_id: UUID, year: int, row_code: str, *, node_key: str | None = None,
) -> dict | None:
    """报表行次 ⇒ 读时计算各直接下级的构成（``child_contributions``），映射为本端点契约。

    不是合并项目 / 报表配置里没有该行次 ⇒ ``None``（调用方按科目码路径友好空返回）。
    节点不存在 / 不是汇总节点 ⇒ ``ViewError``（路由转 404 / 400）。
    ``consolidated`` 取后端合计；``elimination`` = 直接下级里差额节点之和（本级调整与抵销）；
    读时路径不给 ``individual_sum``：直接下级含下级汇总节点（已扣下级抵销），不是「个别数之和」。
    """
    from app.services.consol_calc_basis import to_cents
    from app.services.consol_report_view_service import child_contributions, load_view_context

    ctx = await load_view_context(db, project_id, year)
    if ctx is None:
        return None
    row = next((r for r in ctx.rows if r.row_code == row_code), None)
    if row is None:
        return None
    result = await child_contributions(
        ctx.basis, ctx.rows, report_type=row.report_type, row_code=row_code, node_key=node_key,
    )
    base = {
        "account_code": row_code,
        "row_code": row_code,
        "row_name": row.row_name,
        "report_type": row.report_type,
        "node_key": result["node_key"],
        "node_label": result["node_label"],
        "consolidated": result["total"],
        "linear": result["linear"],
        "basis": "read_time",
        "computed_at": None,
    }
    if result["total"] is None:
        return {**base, "by_company": [], "elimination": None, "has_breakdown": False,
                "message": f"该行合并数留空：{result['note'] or '无法计算'}"}
    total = _safe_decimal(result["total"])
    elim_sum = Decimal("0")
    by_company: list[dict] = []
    for r in result["rows"]:
        amount = None if r["amount"] is None else _safe_decimal(r["amount"])
        if amount is not None and r["kind"] == "elim":
            elim_sum += amount
        by_company.append({
            "company_code": r["company_code"],
            "company_name": r["company_name"],
            "display_name": r["company_name"],
            "amount": r["amount"],
            "ratio": None if amount is None else (str((amount / total).quantize(_RATIO_QUANT)) if total else "0"),
            "pct": r["pct"],
            "node_key": r["node_key"],
            "kind": r["kind"],
            "source": r["source"],
            "source_project_id": r["project_id"],
            "reason": r["reason"],
        })
    return {
        **base,
        "by_company": by_company,
        "elimination": str(to_cents(elim_sum)) if result["linear"] else None,
        "has_breakdown": True,
        "message": result["note"],
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
