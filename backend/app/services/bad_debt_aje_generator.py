"""坏账准备明细表 D2-3 调整分录建议生成器（BadDebtAjeGenerator）

对应 design.md「Components and Interfaces #4 AjeGenerator」与 requirements Req 5。

核心语义（铁律）
------------------------------------------------------------------
调整分录借贷方向**必须基于「审定数 vs 未审数差额」的补提/冲回业务语义判断**，
严禁用金额正负猜符号（避免 sign-convention 同类连环 bug）：

- 差额 diff = 期末审定数(N) - 期末未审数(K)
- diff > 0（审定 > 未审 → 需补提坏账准备）：
    借 信用减值损失/资产减值损失（费用，借方增加）
    贷 坏账准备 1231（资产备抵，贷方增加 = 准备增加）
- diff < 0（审定 < 未审 → 需冲回坏账准备）：
    借 坏账准备 1231（备抵减少）
    贷 信用减值损失/资产减值损失（费用冲回）
- diff == 0：不生成建议（返回 None）
- 金额 amount = |diff|（绝对值，恒为正）

方向口径与 direction_resolver 一致性
------------------------------------------------------------------
坏账准备(1231) 经 resolve_account_direction 归一为 "credit"（资产备抵特例），
信用减值损失/资产减值损失（费用）归一为 "debit"。补提即沿各自正常方向增加，
冲回则两边反向。本模块在生成建议时用 direction_resolver 标注每个分录行的
"normal_direction"，便于审计追溯与下游一致校验，但**借/贷的归属仍由补提/冲回
语义决定**，不依赖金额符号。

建议为 suggested 状态，确认后才由 AdjustmentService 写入正式调整分录表
（本服务只生成建议、不写正式表）。重算时调用方以新建议覆盖旧建议。

service 只 flush 不 commit（本服务为只读计算，不产生写操作）。

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.bad_debt_account_codes import (
    bad_debt_provision_account,
    impairment_loss_account,
)
from app.services.bad_debt_nested_table_service import NestedTableService
from app.services.ledger_import.direction_resolver import resolve_account_direction


class AjeDirection(str, Enum):
    """调整方向：补提 / 冲回。"""

    PROVISION = "PROVISION"   # 补提（审定 > 未审）
    REVERSAL = "REVERSAL"     # 冲回（审定 < 未审）


class AjeEntryLine(BaseModel):
    """单条分录行（借或贷）。"""

    account_code: str
    account_name: str
    side: str                 # "debit" | "credit"（本分录中的借贷归属，由补提/冲回语义决定）
    amount: Decimal           # 金额，恒为正（绝对值）
    normal_direction: str     # direction_resolver 归一的科目正常方向，供追溯


class AjeSuggestion(BaseModel):
    """坏账准备调整分录建议（suggested 状态，未写正式表）。"""

    wp_index_id: uuid.UUID
    direction: AjeDirection
    amount: Decimal                       # |审定数 - 未审数|
    audited_n: Decimal                    # 期末审定数
    unaudited_k: Decimal                  # 期末未审数
    debit_account: str                    # 借方科目编码
    credit_account: str                   # 贷方科目编码
    summary: str                          # 摘要说明
    status: str = "suggested"
    lines: list[AjeEntryLine] = Field(default_factory=list)


def _v(value: Decimal | None) -> Decimal:
    """None 视作 0，量化两位小数。"""
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"))


class BadDebtAjeGenerator:
    """根据 Summary_Row 审定数与未审数差额生成建议调整分录。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_suggestion(
        self, wp_index_id: uuid.UUID
    ) -> AjeSuggestion | None:
        """计算 Summary_Row 期末审定数(N) - 期末未审数(K) 差额并生成建议分录。

        - 零差额 → 返回 None（不生成）。
        - 审定 > 未审（补提）→ 借 信用减值损失 / 贷 坏账准备 1231。
        - 审定 < 未审（冲回）→ 借 坏账准备 1231 / 贷 信用减值损失。
        - 金额 = |差额|。

        Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
        """
        tree = await NestedTableService(self.db).get_tree(wp_index_id)
        amounts = tree.summary.amounts

        audited_n = _v(amounts.amount_n)
        unaudited_k = _v(amounts.amount_k)
        diff = (audited_n - unaudited_k).quantize(Decimal("0.01"))

        # 零差额 → 不生成（Req 5.1）
        if diff == Decimal("0.00"):
            return None

        amount = abs(diff)

        provision_code, provision_name = bad_debt_provision_account()
        loss_code, loss_name = impairment_loss_account()

        # 各科目正常方向（direction_resolver 归一，仅用于追溯标注）
        loss_normal, _ = resolve_account_direction(loss_code, loss_name)
        provision_normal, _ = resolve_account_direction(provision_code, provision_name)

        if diff > Decimal("0.00"):
            # 补提：借 信用减值损失 / 贷 坏账准备
            direction = AjeDirection.PROVISION
            debit_account = loss_code
            credit_account = provision_code
            summary = (
                f"补提坏账准备：期末审定数 {audited_n} 大于未审数 {unaudited_k}，"
                f"差额 {amount}，借记{loss_name}、"
                f"贷记{provision_name}"
            )
            lines = [
                AjeEntryLine(
                    account_code=loss_code,
                    account_name=loss_name,
                    side="debit",
                    amount=amount,
                    normal_direction=loss_normal,
                ),
                AjeEntryLine(
                    account_code=provision_code,
                    account_name=provision_name,
                    side="credit",
                    amount=amount,
                    normal_direction=provision_normal,
                ),
            ]
        else:
            # 冲回：借 坏账准备 / 贷 信用减值损失
            direction = AjeDirection.REVERSAL
            debit_account = provision_code
            credit_account = loss_code
            summary = (
                f"冲回坏账准备：期末审定数 {audited_n} 小于未审数 {unaudited_k}，"
                f"差额 {amount}，借记{provision_name}、"
                f"贷记{loss_name}"
            )
            lines = [
                AjeEntryLine(
                    account_code=provision_code,
                    account_name=provision_name,
                    side="debit",
                    amount=amount,
                    normal_direction=provision_normal,
                ),
                AjeEntryLine(
                    account_code=loss_code,
                    account_name=loss_name,
                    side="credit",
                    amount=amount,
                    normal_direction=loss_normal,
                ),
            ]

        return AjeSuggestion(
            wp_index_id=wp_index_id,
            direction=direction,
            amount=amount,
            audited_n=audited_n,
            unaudited_k=unaudited_k,
            debit_account=debit_account,
            credit_account=credit_account,
            summary=summary,
            status="suggested",
            lines=lines,
        )


__all__ = [
    "BadDebtAjeGenerator",
    "AjeSuggestion",
    "AjeEntryLine",
    "AjeDirection",
    "bad_debt_provision_account",
    "impairment_loss_account",
]
