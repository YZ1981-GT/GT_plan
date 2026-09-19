"""坏账准备明细表 D2-3 自动汇总引擎（AutoSumEngine）

纯计算模块，无任何 DB 依赖：接收行金额数据（RowAmounts）列表，返回汇总结果。
对应 design.md「Components and Interfaces #2 AutoSumEngine」。

三级汇总：Child_Row → Parent_Row（sum_children）→ Summary_Row（sum_parents）。
平衡公式：N = E + F + G - H - I - J + L + M（validate_balance_formula）。

口径铁律：
- 全程使用 Decimal，结果 quantize 到两位小数（Decimal("0.01")），禁止 float。
- None 视作 0 参与求和；但若某列所有输入全为 None，该列汇总返回 None（不返回 0），
  以区分"无数据"与"合计为零"。

Requirements: 3.1, 3.2, 3.3, 3.4, 3.6, 10.3
"""

from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

from app.schemas.bad_debt_schemas import BalanceCheck, RowAmounts

# 两位小数量化基准
_TWO_PLACES = Decimal("0.01")
# 平衡校验容差
_BALANCE_TOLERANCE = Decimal("0.01")


class AutoSumEngine:
    """坏账准备明细表三级汇总 + 平衡公式校验（纯静态方法）。"""

    # 13 个金额列 amount_b ~ amount_n（排除 A 项目名）
    AMOUNT_COLUMNS: ClassVar[list[str]] = [f"amount_{c}" for c in "bcdefghijklmn"]

    @staticmethod
    def _quantize(value: Decimal) -> Decimal:
        """统一量化到两位小数。"""
        return value.quantize(_TWO_PLACES)

    @classmethod
    def _sum_rows(cls, rows: list[RowAmounts]) -> RowAmounts:
        """逐列独立求和的内部实现。

        每一列：
        - None 视作 0 参与累加；
        - 若该列在所有行中均为 None，则该列汇总返回 None（区分无数据与零）；
        - 否则返回量化到两位小数的 Decimal 合计。
        """
        result: dict[str, Decimal | None] = {}
        for col in cls.AMOUNT_COLUMNS:
            total = Decimal("0")
            has_value = False
            for row in rows:
                raw = getattr(row, col)
                if raw is None:
                    continue
                has_value = True
                # 强制 Decimal，杜绝 float 漂移
                total += Decimal(str(raw))
            result[col] = cls._quantize(total) if has_value else None
        return RowAmounts(**result)

    @classmethod
    def sum_children(cls, children: list[RowAmounts]) -> RowAmounts:
        """父行 = 其全部子行 13 列逐列合计。

        Requirements: 3.1, 3.3, 3.6
        """
        return cls._sum_rows(children)

    @classmethod
    def sum_parents(cls, parents: list[RowAmounts]) -> RowAmounts:
        """合计行 = 全部父行 13 列逐列合计。

        Requirements: 3.2, 3.3, 3.6
        """
        return cls._sum_rows(parents)

    @staticmethod
    def validate_balance_formula(row: RowAmounts) -> BalanceCheck:
        """校验平衡公式 N = E + F + G - H - I - J + L + M。

        None 视作 0 参与计算；is_balanced = |expected_n - actual_n| < 0.01。

        Requirements: 3.4
        """

        def v(col: str) -> Decimal:
            raw = getattr(row, col)
            return Decimal("0") if raw is None else Decimal(str(raw))

        expected_n = (
            v("amount_e")
            + v("amount_f")
            + v("amount_g")
            - v("amount_h")
            - v("amount_i")
            - v("amount_j")
            + v("amount_l")
            + v("amount_m")
        ).quantize(_TWO_PLACES)

        actual_n = v("amount_n").quantize(_TWO_PLACES)
        diff = (expected_n - actual_n).quantize(_TWO_PLACES)
        is_balanced = abs(expected_n - actual_n) < _BALANCE_TOLERANCE

        return BalanceCheck(
            is_balanced=is_balanced,
            expected_n=expected_n,
            actual_n=actual_n,
            diff=diff,
        )
