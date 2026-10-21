"""抽凭总体完整性核对 — 序时账 vs 科目余额表发生额

spec: voucher-sampling-reconcile-balance-source
Task 1

核对口径：
- 序时账侧：项目 + 年度 + 数据集 + is_deleted=false + 凭证日期在年度内 + 科目前缀
  → SUM(debit_amount), SUM(credit_amount)（带符号）
- 账面侧：同项目/年度/数据集 + 同科目前缀 → 余额表最高层行 debit_amount / credit_amount 合计
- 判定：借、贷方各自 |序时账 − 账面| ≤ |账面| × 可容忍比例

设计决策（见 design.md §2）：
- 带符号：红字冲销在序时账是负数，余额表发生额是净额；绝对值会重复计入冲销
- 最高层行：余额表可能同时存在 1122 和 1122.01，取最高层 = 总账口径的「账面」
- 不受筛选影响：核对验证序时账**整体**与账面一致，筛选属于总体界定
- 只读查询包在 begin_nested() 内：失败不污染外层事务
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbBalance, TbLedger

logger = logging.getLogger(__name__)


# ─── 数据类 ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PopulationReconcileFacts:
    """总体完整性核对结果。

    available=True 时 ledger_*/book_* 有值；
    available=False 时 unavailable_reason 给出中文原因。
    """

    available: bool
    basis: Optional[str] = None  # 'tb_balance_movement' | None
    ledger_debit: Optional[Decimal] = None
    ledger_credit: Optional[Decimal] = None
    book_debit: Optional[Decimal] = None
    book_credit: Optional[Decimal] = None
    unavailable_reason: Optional[str] = None

    def to_stats(self) -> dict:
        """输出 API 扁平字段（向后兼容 book_amount / reconcile_available / reconcile_basis）。"""
        book_amount: Optional[str] = None
        if self.book_debit is not None and self.book_credit is not None:
            # book_amount = 借+贷 绝对值合计，供手工核对口径 / 旧前端回落
            book_amount = str(abs(self.book_debit) + abs(self.book_credit))
        return {
            "book_amount": book_amount,
            "reconcile_available": self.available,
            "reconcile_basis": self.basis,
            "reconcile_ledger_debit": (
                str(self.ledger_debit) if self.ledger_debit is not None else None
            ),
            "reconcile_ledger_credit": (
                str(self.ledger_credit) if self.ledger_credit is not None else None
            ),
            "reconcile_book_debit": (
                str(self.book_debit) if self.book_debit is not None else None
            ),
            "reconcile_book_credit": (
                str(self.book_credit) if self.book_credit is not None else None
            ),
            "reconcile_unavailable_reason": self.unavailable_reason,
        }


_UNAVAILABLE = PopulationReconcileFacts(available=False)


# ─── 纯函数：最高层行选取 ───────────────────────────────────────────────────


def select_top_level_codes(codes: list[str]) -> list[str]:
    """从科目码集合中选出最高层（没有「也在集合中的更短前缀」的码）。

    例如 ['1122', '1122.01', '1122.02', '1221'] → ['1122', '1221']
    （1122.01 和 1122.02 被 1122 覆盖）。

    🔴 判据是「科目码前缀关系」，不是 level 字段 —— level 可能为 NULL 或不准。
    """
    if not codes:
        return []
    sorted_codes = sorted(codes, key=len)
    top: list[str] = []
    for code in sorted_codes:
        # 如果 top 中已有某个码是 code 的前缀（即 code 以它开头），则 code 是子级
        is_child = any(
            code.startswith(prefix) and len(code) > len(prefix)
            for prefix in top
        )
        if not is_child:
            top.append(code)
    return top


# ─── 核对主函数 ──────────────────────────────────────────────────────────────


async def resolve_population_reconcile(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    account_codes: list[str],
    dataset_id: Optional[UUID],
) -> PopulationReconcileFacts:
    """解析序时账 vs 科目余额表的总体完整性核对。

    两条只读查询包在 SAVEPOINT 内；任何异常记 WARNING 并返回不可用，不污染外层事务。

    Args:
        db: 数据库会话
        project_id: 项目 ID
        year: 年度
        account_codes: 抽凭指定的科目码列表（如 ['1122']）
        dataset_id: 当前激活数据集 ID（None 时用 is_deleted 过滤降级）
    """
    if not account_codes:
        return PopulationReconcileFacts(
            available=False,
            unavailable_reason="未指定科目，无法执行总体完整性核对",
        )

    try:
        async with db.begin_nested():
            # ── 构建公共过滤条件 ────────────────────────────────────────────
            def _base_filter(table):
                """项目 + 年度 + 数据集 + is_deleted=false。"""
                conditions = [
                    table.c.project_id == project_id,
                    table.c.year == year,
                    table.c.is_deleted == sa.false(),
                ]
                if dataset_id is not None and hasattr(table.c, "dataset_id"):
                    conditions.append(table.c.dataset_id == dataset_id)
                return sa.and_(*conditions)

            def _prefix_filter(table):
                """科目前缀 OR 条件。"""
                return sa.or_(
                    *[table.c.account_code.like(f"{code}%") for code in account_codes]
                )

            # ── 1. 余额表：取范围内所有行的 account_code，再选最高层 ────────
            bal_table = TbBalance.__table__
            code_stmt = (
                sa.select(bal_table.c.account_code)
                .where(_base_filter(bal_table), _prefix_filter(bal_table))
                .distinct()
            )
            code_result = await db.execute(code_stmt)
            all_codes_in_range = [row[0] for row in code_result.all()]

            if not all_codes_in_range:
                shown = "、".join(account_codes[:5])
                if len(account_codes) > 5:
                    shown += f" 等 {len(account_codes)} 个"
                return PopulationReconcileFacts(
                    available=False,
                    unavailable_reason=(
                        f"科目余额表中无所选科目（{shown}）的行，"
                        "可能尚未导入余额表或科目编码不一致"
                    ),
                )

            top_codes = select_top_level_codes(all_codes_in_range)

            # 汇总最高层行的借贷发生额
            bal_agg_stmt = sa.select(
                sa.func.coalesce(sa.func.sum(bal_table.c.debit_amount), 0),
                sa.func.coalesce(sa.func.sum(bal_table.c.credit_amount), 0),
            ).where(
                _base_filter(bal_table),
                bal_table.c.account_code.in_(top_codes),
            )
            bal_row = (await db.execute(bal_agg_stmt)).one()
            book_debit = Decimal(str(bal_row[0]))
            book_credit = Decimal(str(bal_row[1]))

            # ── 2. 序时账：全年全科目带符号合计（不受抽样筛选影响）──────────
            led_table = TbLedger.__table__
            led_agg_stmt = sa.select(
                sa.func.coalesce(sa.func.sum(led_table.c.debit_amount), 0),
                sa.func.coalesce(sa.func.sum(led_table.c.credit_amount), 0),
            ).where(
                _base_filter(led_table),
                _prefix_filter(led_table),
                led_table.c.voucher_date >= date(year, 1, 1),
                led_table.c.voucher_date <= date(year, 12, 31),
            )
            led_row = (await db.execute(led_agg_stmt)).one()
            ledger_debit = Decimal(str(led_row[0]))
            ledger_credit = Decimal(str(led_row[1]))

        return PopulationReconcileFacts(
            available=True,
            basis="tb_balance_movement",
            ledger_debit=ledger_debit,
            ledger_credit=ledger_credit,
            book_debit=book_debit,
            book_credit=book_credit,
        )

    except Exception:  # noqa: BLE001 — 核对取数失败不阻断抽样
        logger.warning(
            "总体完整性核对取数失败 project=%s year=%s codes=%s",
            project_id,
            year,
            account_codes,
            exc_info=True,
        )
        # 🔴 不在此处 rollback —— begin_nested() 的 __aexit__ 在异常时已回滚保存点。
        # 手动 rollback 会回滚外层事务（把已 flush 的抽样快照也撤销）。
        return PopulationReconcileFacts(
            available=False,
            unavailable_reason="总体完整性核对取数失败，请检查数据完整性后重试",
        )
