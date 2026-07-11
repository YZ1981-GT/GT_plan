"""审定表回写契约（Adjudication Writeback）— Formula Management Library · Req 13。

职责（design §Components 6 / Req 13）：

- 审定表（``xxx-1``）的 **auto_calc** 公式执行 → 把结果**回写**到
  ``trial_balance.audited_amount``（**仅 audited，不动 unadjusted**，Req 13.1/13.2）。
- 回写完成后记录该公式的**最近计算时间**（``last_computed_at``），供
  ``Formula_Source_Tooltip`` 展示（Req 13.3）。
- 若公式引用地址**悬空**（ACNR ``full_resolve`` found=false 且非 fail-open），
  **拒绝回写**并返回问题清单（Issue_List，Req 13.4）。
- 审定数发生回写变更后，经 **ACNR 失效链**（``acnr.events.invalidate``）触发下游
  报表/附注失效——**复用**既有失效链，**不自建**失效逻辑（Req 13.5）。

工程铁律：
- **service 只 flush 不 commit**，由 router 层统一 commit。
- 求值统一委托 ``formula_management.engine.execute_formula``（auto_calc），
  引用解析统一走 ``engine.resolve_ref``（封装 ACNR full_resolve，fail-open）。
- 四表库取数经 ``get_active_filter`` 统一入口（Req 12.1）。
- 禁止在公式引用中拼接 ``wp_code+sheet+cell`` 裸字符串（Req 11.5）。

Requirements: 13.1, 13.2, 13.3, 13.4, 13.5
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance
from app.services.dataset_query import get_active_filter
from app.services.formula_engine import FormulaContext
from app.services.formula_management.engine import (
    FormulaRecord,
    IssueItem,
    execute_formula,
    resolve_ref,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 结果结构
# ═══════════════════════════════════════════════════════════════════════════════
@dataclass
class AdjudicationWritebackResult:
    """审定表回写执行结果。

    - ``updated_accounts``：本次成功回写 audited_amount 的科目编码列表。
    - ``values``：科目编码 → 回写后的审定金额。
    - ``issues``：悬空引用拒写 / 求值失败 / 科目缺失等问题清单（不改任何值）。
    - ``last_computed_at``：科目编码 → 该公式最近计算时间（Req 13.3）。
    - ``changed``：本批次是否发生了任何 audited_amount 变更（用于是否触发失效链）。
    """

    updated_accounts: list[str] = field(default_factory=list)
    values: dict[str, Decimal] = field(default_factory=dict)
    issues: list[IssueItem] = field(default_factory=list)
    last_computed_at: dict[str, datetime] = field(default_factory=dict)
    changed: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# Service
# ═══════════════════════════════════════════════════════════════════════════════
class AdjudicationWritebackService:
    """审定表（``xxx-1``）auto_calc 公式 → 回写 ``trial_balance.audited_amount``。

    核心约束：
    - 仅回写 ``audited_amount``，**绝不修改** ``unadjusted_amount``（Req 13.2）。
    - 悬空引用拒写并返回 Issue_List（Req 13.4）。
    - 回写变更后经 ACNR 失效链触发下游报表/附注失效（Req 13.5）。
    - 仅 flush，不 commit。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── 求值上下文构建（四表库叶子源，get_active_filter 统一入口）────────────
    async def build_context(self, project_id: UUID, year: int) -> FormulaContext:
        """从 ``trial_balance`` 载入未审/审定/调整数据构建求值上下文。

        每个科目提供多列取数别名，供审定表 auto_calc 公式引用：
        ``未审数`` / ``审定数`` / ``期末余额`` / ``AJE调整`` / ``RJE调整`` / ``年初余额``。

        四表库取数经 ``get_active_filter`` 统一入口读取（Req 12.1），
        而非裸写 ``is_deleted==False``。
        """
        active = await get_active_filter(
            self.db, TrialBalance.__table__, project_id, year
        )
        stmt = sa.select(
            TrialBalance.standard_account_code,
            TrialBalance.unadjusted_amount,
            TrialBalance.audited_amount,
            TrialBalance.aje_adjustment,
            TrialBalance.rje_adjustment,
            TrialBalance.opening_balance,
        ).where(active)
        result = await self.db.execute(stmt)

        tb_data: dict[str, dict[str, Decimal]] = {}
        for row in result.fetchall():
            code = row.standard_account_code
            unadj = Decimal(str(row.unadjusted_amount or 0))
            audited = Decimal(str(row.audited_amount or 0))
            aje = Decimal(str(row.aje_adjustment or 0))
            rje = Decimal(str(row.rje_adjustment or 0))
            opening = Decimal(str(row.opening_balance or 0))
            tb_data[code] = {
                "未审数": unadj,
                "审定数": audited,
                "期末余额": audited,
                "AJE调整": aje,
                "RJE调整": rje,
                "年初余额": opening,
            }
        return FormulaContext(tb_data=tb_data)

    # ─── 单条公式回写 ────────────────────────────────────────────────────────
    async def writeback_formula(
        self,
        project_id: UUID,
        year: int,
        formula: FormulaRecord,
        *,
        ctx: FormulaContext,
        company_code: str | None = None,
        result: AdjudicationWritebackResult | None = None,
    ) -> AdjudicationWritebackResult:
        """执行一条审定表 auto_calc 公式并回写 ``audited_amount``。

        ``formula.target_cell`` 视为**标准科目编码**（``standard_account_code``），
        即回写目标科目。

        步骤：
        1. 仅接受 ``auto_calc`` 类型（审定表回写语义），其余类型拒绝并记 Issue。
        2. 先经 ``resolve_ref`` 校验所有引用；**悬空**（found=false 且非 fail-open）
           → 拒写并向 Issue_List 追加一条问题项（Req 13.4），**不执行回写**。
        3. 经 ``execute_formula`` 求值（``resolve_refs=False``，引用已在步骤 2 校验）。
        4. 求值成功 → 回写 ``trial_balance.audited_amount``（仅 audited，Req 13.2），
           记 ``last_computed_at``（Req 13.3）。

        Returns:
            累积的 AdjudicationWritebackResult（可传入 ``result`` 复用做批量累积）。
        """
        result = result or AdjudicationWritebackResult()
        account_code = (formula.target_cell or "").strip()

        # ── 步骤 1：仅审定表 auto_calc 参与回写 ──────────────────────────────
        if (formula.formula_type or "").strip() != "auto_calc":
            result.issues.append(
                IssueItem(
                    formula_id=formula.id,
                    addr_id=formula.addr_id,
                    description=(
                        f"审定表回写仅支持 auto_calc 公式，收到 "
                        f"formula_type='{formula.formula_type}'，已拒绝回写"
                    ),
                )
            )
            return result

        if not account_code:
            result.issues.append(
                IssueItem(
                    formula_id=formula.id,
                    addr_id=formula.addr_id,
                    description="审定表公式缺少目标科目（target_cell 为空），已拒绝回写",
                )
            )
            return result

        # ── 步骤 2：悬空引用校验 → 拒写（Req 13.4）──────────────────────────
        dangling = await self._collect_dangling_refs(
            formula, project_id=project_id
        )
        if dangling:
            result.issues.append(
                IssueItem(
                    formula_id=formula.id,
                    addr_id=formula.addr_id,
                    description=(
                        f"审定表公式引用悬空，拒绝回写科目 {account_code}："
                        f"{', '.join(dangling)}"
                    ),
                )
            )
            return result

        # ── 步骤 3：求值（引用已校验，避免重复解析）────────────────────────
        exec_result = await execute_formula(
            self.db,
            formula=formula,
            ctx=ctx,
            project_id=str(project_id),
            resolve_refs=False,
        )
        if exec_result.errors or formula.target_cell not in exec_result.values:
            # 求值失败：保留 audited 原值不变，记描述性问题（不阻断批次其余执行）。
            desc = (
                "; ".join(exec_result.errors)
                if exec_result.errors
                else f"公式求值未产生目标单元 {account_code} 的值"
            )
            result.issues.append(
                IssueItem(
                    formula_id=formula.id,
                    addr_id=formula.addr_id,
                    description=f"审定表公式求值失败，未回写科目 {account_code}：{desc}",
                )
            )
            return result

        value = exec_result.values[formula.target_cell]

        # ── 步骤 4：回写 audited_amount（仅 audited，不动 unadjusted）────────
        written = await self._write_audited(
            project_id, year, account_code, value, company_code=company_code
        )
        if written == 0:
            result.issues.append(
                IssueItem(
                    formula_id=formula.id,
                    addr_id=formula.addr_id,
                    description=(
                        f"试算表中未找到科目 {account_code}"
                        f"（project={project_id}, year={year}），未回写"
                    ),
                )
            )
            return result

        result.updated_accounts.append(account_code)
        result.values[account_code] = value
        if exec_result.last_computed_at is not None:
            result.last_computed_at[account_code] = exec_result.last_computed_at
        result.changed = True

        logger.info(
            "审定表回写(flush): project=%s year=%s account=%s audited=%s rows=%d",
            project_id, year, account_code, value, written,
        )
        return result

    # ─── 批量回写 + 失效链 ───────────────────────────────────────────────────
    async def writeback_batch(
        self,
        project_id: UUID,
        year: int,
        formulas: list[FormulaRecord],
        *,
        ctx: FormulaContext | None = None,
        company_code: str | None = None,
    ) -> AdjudicationWritebackResult:
        """批量执行审定表 auto_calc 公式回写，全部完成后触发 ACNR 失效链。

        单条公式失败（悬空/求值错误/科目缺失）不阻断其余公式执行（记 Issue 后继续）。
        本批次若发生任何 audited_amount 变更（``changed=True``），回写 flush 后经
        ``acnr.events.invalidate`` 触发下游报表/附注失效（Req 13.5，复用不自建）。

        service 只 flush，router 层 commit。
        """
        result = AdjudicationWritebackResult()
        if not formulas:
            return result

        if ctx is None:
            ctx = await self.build_context(project_id, year)

        for formula in formulas:
            await self.writeback_formula(
                project_id,
                year,
                formula,
                ctx=ctx,
                company_code=company_code,
                result=result,
            )

        if result.changed:
            # 仅 flush（不 commit），使回写在本事务内可见，再触发失效链。
            await self.db.flush()
            await self._invalidate_downstream(project_id)

        return result

    # ═══════════════════════════════════════════════════════════════════════
    # 内部工具
    # ═══════════════════════════════════════════════════════════════════════
    async def _collect_dangling_refs(
        self, formula: FormulaRecord, *, project_id: UUID
    ) -> list[str]:
        """返回公式中悬空引用的可读标识列表。

        悬空 = ACNR ``full_resolve`` found=false **且非 fail-open**。
        fail-open（ACNR 基础设施不可用）**不视为悬空**（Req 11.3），避免因解析器
        故障误拒合法公式；此时回退既有解析路径继续执行。
        """
        dangling: list[str] = []
        for ref in formula.refs or []:
            formula_ref, addr_id = _normalize_ref(ref)
            if formula_ref is None and addr_id is None:
                continue
            rr = await resolve_ref(
                formula_ref=formula_ref,
                addr_id=addr_id,
                project_id=str(project_id),
                db=self.db,
            )
            if not rr.found and not rr.fail_open:
                dangling.append(formula_ref or addr_id or "<unknown>")
        return dangling

    async def _write_audited(
        self,
        project_id: UUID,
        year: int,
        account_code: str,
        value: Decimal,
        *,
        company_code: str | None = None,
    ) -> int:
        """把 ``value`` 回写到匹配科目的 ``audited_amount``（仅 audited）。

        返回被更新的行数。**绝不修改** ``unadjusted_amount``（Req 13.2）。
        """
        try:
            audited = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return 0

        conds = [
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.standard_account_code == account_code,
            TrialBalance.is_deleted == sa.false(),
        ]
        if company_code:
            conds.append(TrialBalance.company_code == company_code)

        stmt = sa.select(TrialBalance).where(*conds)
        rows = (await self.db.execute(stmt)).scalars().all()
        if not rows:
            return 0

        for row in rows:
            # 仅回写 audited_amount，不动 unadjusted_amount（Req 13.2）
            row.audited_amount = audited

        # 仅 flush，不 commit（工程铁律）
        await self.db.flush()
        return len(rows)

    async def _invalidate_downstream(self, project_id: UUID) -> None:
        """审定数变更后经 ACNR 失效链触发下游报表/附注失效（Req 13.5）。

        **复用** ``acnr.events.invalidate``（canonical 失效链：L3 → L2 →
        FormulaReverseIndex → legacy WP 域），**不自建**失效逻辑。invalidate 本身
        不抛异常（失效失败仅 warning，不阻断主流程）。
        """
        try:
            from app.services.acnr.events import invalidate

            await invalidate(str(project_id), trigger="adjudication_writeback")
        except Exception as exc:  # noqa: BLE001 — 失效不阻断回写主流程
            logger.warning(
                "审定表回写后 ACNR 失效链触发失败（不阻断）: project=%s: %s",
                project_id, exc,
            )


def _normalize_ref(ref: Any) -> tuple[str | None, str | None]:
    """把一条引用归一化为 ``(formula_ref, addr_id)``。

    支持 ``{"formula_ref": ...}`` / ``{"addr_id": ...}`` / 裸字符串（按 formula_ref）。
    """
    if isinstance(ref, dict):
        return ref.get("formula_ref"), ref.get("addr_id")
    if isinstance(ref, str):
        return ref, None
    return None, None
