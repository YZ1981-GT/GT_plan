"""坏账准备明细表 D2-3 嵌套子表 ORM 模型

对应迁移 V070__bad_debt_detail_rows.sql。
致同 2025 修订版 D2-3（应收账款坏账准备明细表）两层嵌套结构：
- Parent_Row（计提类别，provision_method 有值，parent_row_id 为 NULL）
- Child_Row（明细行，parent_row_id 指向父行，provision_method 为 NULL）

provision_method 用 VARCHAR(30) + 应用层枚举（ProvisionMethod），不建 PG enum type。

Requirements: 1.1, 1.2, 2.1, 2.6, 8.1
"""

import enum
import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ProvisionMethod(str, enum.Enum):
    """坏账计提方法枚举（应用层校验，DB 侧用 VARCHAR(30) 存储）"""

    INDIVIDUAL = "INDIVIDUAL"                    # 按单项评估计提
    CREDIT_RISK_AGING = "CREDIT_RISK_AGING"      # 信用风险组合-账龄分析法
    CREDIT_RISK_OTHER = "CREDIT_RISK_OTHER"      # 信用风险组合-其他组合
    OTHER = "OTHER"                              # 其他


# 枚举值 → 中文显示名映射（供 API GET provision-methods 与前端渲染）
PROVISION_METHOD_LABELS: dict[ProvisionMethod, str] = {
    ProvisionMethod.INDIVIDUAL: "按单项评估计提",
    ProvisionMethod.CREDIT_RISK_AGING: "信用风险组合-账龄分析法",
    ProvisionMethod.CREDIT_RISK_OTHER: "信用风险组合-其他组合",
    ProvisionMethod.OTHER: "其他",
}


class BadDebtDetailRow(Base, TimestampMixin):
    """坏账准备明细表 D2-3 嵌套行（父行与子行统一存储）

    - is_parent: parent_row_id 为 NULL 且 provision_method 有值
    - is_child: parent_row_id 指向某父行
    - children: self-referential 一对多，级联删除子行，按 sort_order 排序
    - version: 乐观锁，并发更新冲突检测
    """

    __tablename__ = "bad_debt_detail_rows"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    wp_index_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("wp_index.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_row_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("bad_debt_detail_rows.id", ondelete="CASCADE"),
        nullable=True,
    )
    provision_method: Mapped[str | None] = mapped_column(
        String(30), nullable=True,
        comment="计提方法枚举(仅父行): INDIVIDUAL|CREDIT_RISK_AGING|CREDIT_RISK_OTHER|OTHER",
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    row_label: Mapped[str] = mapped_column(String(200), nullable=False)

    # ─── 13 金额列 (B~N，排除 A 项目名) ──────────────────────────────────────
    amount_b: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)  # 期初未审数
    amount_c: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)  # 期初账项调整
    amount_d: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)  # 重分类调整(期初)
    amount_e: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)  # 期初审定数
    amount_f: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)  # 本期计提
    amount_g: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)  # 其他增加
    amount_h: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)  # 本期转回
    amount_i: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)  # 核销
    amount_j: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)  # 其他减少
    amount_k: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)  # 期末未审数
    amount_l: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)  # 期末账项调整
    amount_m: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)  # 重分类调整(期末)
    amount_n: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)  # 期末审定数

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # ─── self-referential relationships ─────────────────────────────────────
    children: Mapped[list["BadDebtDetailRow"]] = relationship(
        "BadDebtDetailRow",
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="BadDebtDetailRow.sort_order",
    )
    parent: Mapped["BadDebtDetailRow | None"] = relationship(
        "BadDebtDetailRow",
        remote_side="BadDebtDetailRow.id",
        back_populates="children",
    )

    @property
    def is_parent(self) -> bool:
        """父行：无父引用且有计提方法"""
        return self.parent_row_id is None and self.provision_method is not None

    @property
    def is_child(self) -> bool:
        """子行：有父引用"""
        return self.parent_row_id is not None

    __table_args__ = (
        Index("ix_bad_debt_rows_wp_index", "wp_index_id"),
        Index("ix_bad_debt_rows_parent", "parent_row_id"),
        Index(
            "uq_bad_debt_provision_method",
            "wp_index_id", "provision_method",
            unique=True,
            postgresql_where=text("provision_method IS NOT NULL"),
        ),
    )
