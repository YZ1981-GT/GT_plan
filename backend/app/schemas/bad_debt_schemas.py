"""坏账准备明细表 D2-3 嵌套子表 Pydantic DTO/Schema

对应 design.md「Pydantic Schemas」章节。
金额字段统一用 condecimal(max_digits=18, decimal_places=2) 约束，与 V070 DDL 的
NUMERIC(18,2) 三层一致。

Requirements: 2.2, 2.3, 8.1, 8.2, 10.3
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, condecimal

from app.models.bad_debt_models import ProvisionMethod

# NUMERIC(18,2) 精度约束类型别名（可空）
Amount = condecimal(max_digits=18, decimal_places=2)


class RowAmounts(BaseModel):
    """13 金额列 (B~N) 的值对象"""

    amount_b: Amount | None = None  # 期初未审数
    amount_c: Amount | None = None  # 期初账项调整
    amount_d: Amount | None = None  # 重分类调整(期初)
    amount_e: Amount | None = None  # 期初审定数
    amount_f: Amount | None = None  # 本期计提
    amount_g: Amount | None = None  # 其他增加
    amount_h: Amount | None = None  # 本期转回
    amount_i: Amount | None = None  # 核销
    amount_j: Amount | None = None  # 其他减少
    amount_k: Amount | None = None  # 期末未审数
    amount_l: Amount | None = None  # 期末账项调整
    amount_m: Amount | None = None  # 重分类调整(期末)
    amount_n: Amount | None = None  # 期末审定数


class BalanceCheck(BaseModel):
    """平衡公式校验结果：N = E + F + G - H - I - J + L + M"""

    is_balanced: bool
    expected_n: Decimal
    actual_n: Decimal
    diff: Decimal


# ─── 请求 DTO ────────────────────────────────────────────────────────────────


class CreateParentRowDTO(BaseModel):
    """新增父行：必须指定计提方法 + 行标签"""

    provision_method: ProvisionMethod
    row_label: str = Field(..., min_length=1, max_length=200)


class CreateChildRowDTO(BaseModel):
    """新增子行：行标签 + 可选插入位置（默认末尾）。"""

    row_label: str = Field(..., min_length=1, max_length=200)
    amount_e: Amount | None = None  # 期初审定数
    amount_k: Amount | None = None  # 期末未审数
    amount_n: Amount | None = None  # 期末审定数
    insert_before_id: UUID | None = None  # 在指定子行之前插入
    insert_after_id: UUID | None = None   # 在指定子行之后插入


class UpdateRowDTO(BaseModel):
    """更新单行：含 version 乐观锁必传"""

    row_label: str | None = Field(None, max_length=200)
    amounts: RowAmounts | None = None
    version: int  # 乐观锁必传


# ─── 响应 DTO ────────────────────────────────────────────────────────────────


class ChildRowResponse(BaseModel):
    """子行响应"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    parent_row_id: UUID
    sort_order: int
    row_label: str
    amounts: RowAmounts
    version: int


class ParentRowResponse(BaseModel):
    """父行响应（嵌套 children）"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provision_method: ProvisionMethod
    provision_method_label: str
    sort_order: int
    row_label: str
    amounts: RowAmounts
    children: list[ChildRowResponse] = Field(default_factory=list)
    version: int
    is_editable: bool  # 无子行时可直接编辑金额


class SummaryRowResponse(BaseModel):
    """合计行响应"""

    amounts: RowAmounts
    balance_check: BalanceCheck


class BadDebtTreeResponse(BaseModel):
    """完整嵌套树响应"""

    wp_index_id: UUID
    summary: SummaryRowResponse
    parents: list[ParentRowResponse] = Field(default_factory=list)
    prefill_source: str | None = None  # "试算表 1231 坏账准备" or None
