"""坏账准备明细表 D2-3 试算表辅助预填服务（BadDebtPrefillService）

对应 design.md「Components and Interfaces #3 PrefillService」与 requirements Req 4。

预填落点设计决策（重要）
------------------------------------------------------------------
Summary_Row 是运行时由 NestedTableService.sum_parents 计算的派生值、**不落库**
（见 bad_debt_nested_table_service.get_tree）。因此本服务不直接向某张表写入
Summary 单元格，而是采用「返回预填建议值 + 来源标注」的最小侵入方案：

1. 读取当前 Summary 的 期初未审数(amount_b) / 期末未审数(amount_k) 状态
   （通过 NestedTableService.get_tree 拿 summary.amounts）。
2. 查试算表科目 1231（坏账准备）：opening_balance → 期初未审数(B)、
   unadjusted_amount → 期末未审数(K)。
3. **仅当目标 Summary 单元格为 None（空）时**才产出预填建议值，已有值不覆盖。
4. 试算表无 1231 数据时跳过、不报错（no-op）。
5. 返回 PrefillResult，含来源标注字符串「试算表 1231 坏账准备」、是否实际预填、
   预填了哪些列及其建议值；由前端据此填充对应输入。

该方案对现有数据结构零侵入，符合「Summary 不落库」事实，且满足 Req 4.1~4.5。
service 只 flush 不 commit（本服务为只读查询，不产生写操作）。

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance
from app.services.bad_debt_nested_table_service import NestedTableService

# 坏账准备试算表科目编码
BAD_DEBT_ACCOUNT_CODE = "1231"
# 预填来源标注（供前端 tooltip 显示）
PREFILL_SOURCE = "试算表 1231 坏账准备"

# Summary 列 ← 试算表字段映射：
#   amount_b（期初未审数） ← TrialBalance.opening_balance
#   amount_k（期末未审数） ← TrialBalance.unadjusted_amount
_PREFILL_COLUMN_TB_FIELD = {
    "amount_b": "opening_balance",
    "amount_k": "unadjusted_amount",
}


class PrefillResult(BaseModel):
    """预填结果（返回建议值供前端填充，不落库）。"""

    wp_index_id: uuid.UUID
    prefilled: bool = False                       # 是否实际预填了至少一列
    source: str | None = None                     # 预填成功时为 PREFILL_SOURCE
    prefilled_columns: list[str] = Field(default_factory=list)  # 实际预填列名（amount_b/amount_k）
    values: dict[str, Decimal] = Field(default_factory=dict)    # 列名 → 建议值
    skipped_reason: str | None = None             # no-op 时的原因说明


class BadDebtPrefillService:
    """从试算表科目 1231 辅助预填 Summary_Row 期初/期末未审数。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def prefill_summary(
        self, wp_index_id: uuid.UUID, project_id: uuid.UUID, year: int
    ) -> PrefillResult:
        """生成 Summary_Row 期初/期末未审数预填建议。

        - 仅当目标 Summary 单元格为 None 时产出建议值（Req 4.3）。
        - 试算表无 1231 数据 → 跳过、不报错（Req 4.4）。
        - 预填成功 → source 标注「试算表 1231 坏账准备」（Req 4.5）。

        Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
        """
        # 1) 当前 Summary 状态（amount_b / amount_k 是否已有值）
        tree = await NestedTableService(self.db).get_tree(wp_index_id)
        current = tree.summary.amounts

        # 2) 查试算表 1231（按项目+年度，跨 company_code 聚合；软删排除）
        stmt = select(
            func.count(TrialBalance.id),
            func.sum(TrialBalance.opening_balance),
            func.sum(TrialBalance.unadjusted_amount),
        ).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.standard_account_code == BAD_DEBT_ACCOUNT_CODE,
            TrialBalance.is_deleted.is_(False),
        )
        row_count, opening_sum, unadjusted_sum = (await self.db.execute(stmt)).one()

        # 3) 试算表无 1231 数据 → no-op
        if not row_count:
            return PrefillResult(
                wp_index_id=wp_index_id,
                prefilled=False,
                skipped_reason="试算表无科目 1231 坏账准备数据",
            )

        tb_values: dict[str, Decimal | None] = {
            "amount_b": opening_sum,
            "amount_k": unadjusted_sum,
        }

        prefilled_columns: list[str] = []
        values: dict[str, Decimal] = {}

        # 4) 逐列：仅当 Summary 单元格为 None 且 TB 有值时预填
        for col, tb_value in tb_values.items():
            if getattr(current, col) is not None:
                continue  # 已有用户输入值，不覆盖（Req 4.3）
            if tb_value is None:
                continue  # TB 该字段无值，跳过
            quantized = Decimal(str(tb_value)).quantize(Decimal("0.01"))
            prefilled_columns.append(col)
            values[col] = quantized

        if not prefilled_columns:
            return PrefillResult(
                wp_index_id=wp_index_id,
                prefilled=False,
                skipped_reason="目标单元格已有值或试算表对应字段为空，无需预填",
            )

        return PrefillResult(
            wp_index_id=wp_index_id,
            prefilled=True,
            source=PREFILL_SOURCE,
            prefilled_columns=prefilled_columns,
            values=values,
        )


__all__ = [
    "BadDebtPrefillService",
    "PrefillResult",
    "PREFILL_SOURCE",
    "BAD_DEBT_ACCOUNT_CODE",
]
