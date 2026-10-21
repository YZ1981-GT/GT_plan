"""抽凭总体完整性核对 — 序时账 vs 科目余额表发生额（含科目映射反查）

spec: voucher-sampling-reconcile-balance-source
Task 1 + Task 2

核对口径：
- 科目码解析：优先通过 account_mapping 反查企业原始编码，无映射退回标准编码前缀匹配
- 序时账侧：项目 + 年度 + 数据集 + is_deleted=false + 凭证日期在年度内 + 解析后科目码
  → SUM(debit_amount), SUM(credit_amount)（带符号）
- 账面侧：同项目/年度/数据集 + 解析后科目码 → 余额表最高层行 debit_amount / credit_amount 合计
- 判定：借、贷方各自 |序时账 − 账面| ≤ |账面| × 可容忍比例

设计决策（见 design.md §2/§3）：
- 带符号：红字冲销在序时账是负数，余额表发生额是净额；绝对值会重复计入冲销
- 最高层行：余额表可能同时存在 1122 和 1122.01，取最高层 = 总账口径的「账面」
- 不受筛选影响：核对验证序时账**整体**与账面一致，筛选属于总体界定
- 只读查询包在 begin_nested() 内：失败不污染外层事务
- 映射优先：企业编码可能与标准编码不同，account_mapping 反查覆盖自定义编码体系
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import AccountMapping, TbBalance, TbLedger

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
    mapping_used: bool = False  # True = 使用了 account_mapping 反查的原始编码

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
            "reconcile_mapping_used": self.mapping_used,
        }


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


# ─── 科目映射反查 ────────────────────────────────────────────────────────────


async def resolve_effective_codes(
    db: AsyncSession,
    project_id: UUID,
    standard_codes: list[str],
) -> tuple[list[str], bool]:
    """将标准科目编码通过 account_mapping 表反查为企业原始编码。

    查找 account_mapping 中 standard_account_code 以 standard_codes 中任一为前缀、
    且 is_deleted=false 的所有 original_account_code。

    Returns:
        (effective_codes, mapping_used)
        - mapping_used=True: 返回的是映射表中的原始编码集合
        - mapping_used=False: 映射表中无匹配，退回标准编码原样（向后兼容）
    """
    if not standard_codes:
        return standard_codes, False

    try:
        async with db.begin_nested():
            mapping_table = AccountMapping.__table__
            prefix_conditions = [
                mapping_table.c.standard_account_code.like(f"{code}%")
                for code in standard_codes
            ]
            stmt = (
                sa.select(
                    mapping_table.c.original_account_code,
                    mapping_table.c.standard_account_code,
                )
                .where(
                    mapping_table.c.project_id == project_id,
                    mapping_table.c.is_deleted == sa.false(),
                    sa.or_(*prefix_conditions),
                )
                .distinct()
            )
            result = await db.execute(stmt)
            rows = result.all()
            original_codes = [row[0] for row in rows]

        if original_codes:
            # 部分映射处理：找出哪些标准码有映射、哪些没有
            mapped_standard_prefixes = {row[1] for row in rows}
            unmapped_standard_codes = [
                code for code in standard_codes
                if not any(
                    ms.startswith(code) or code.startswith(ms)
                    for ms in mapped_standard_prefixes
                )
            ]
            # 合并：映射到的原始码 + 未映射的标准码（向后兼容未映射的科目）
            combined = list(set(original_codes + unmapped_standard_codes))
            return combined, True
        # 无映射 → 退回标准编码，向后兼容
        return standard_codes, False

    except Exception:  # noqa: BLE001
        logger.warning(
            "科目映射反查失败 project=%s codes=%s，退回标准编码",
            project_id,
            standard_codes,
            exc_info=True,
        )
        return standard_codes, False


# ─── 核对主函数 ──────────────────────────────────────────────────────────────


async def resolve_population_reconcile(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    account_codes: list[str],
    dataset_id: Optional[UUID],
) -> PopulationReconcileFacts:
    """解析序时账 vs 科目余额表的总体完整性核对。

    1. 先通过 account_mapping 反查企业原始编码（无映射退回标准编码）
    2. 两条只读查询包在 SAVEPOINT 内；任何异常记 WARNING 并返回不可用，不污染外层事务。

    Args:
        db: 数据库会话
        project_id: 项目 ID
        year: 年度
        account_codes: 抽凭指定的标准科目码列表（如 ['1122']）
        dataset_id: 当前激活数据集 ID（None 时用 is_deleted 过滤降级）
    """
    if not account_codes:
        return PopulationReconcileFacts(
            available=False,
            unavailable_reason="未指定科目，无法执行总体完整性核对",
        )

    # ── 0. 映射反查：标准编码 → 企业原始编码 ─────────────────────────────
    effective_codes, mapping_used = await resolve_effective_codes(
        db, project_id, account_codes
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
                """科目前缀 OR 条件（用解析后的编码）。"""
                return sa.or_(
                    *[table.c.account_code.like(f"{code}%") for code in effective_codes]
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
                reason = (
                    f"科目余额表中无所选科目（{shown}）的行，"
                    "可能尚未导入余额表或科目编码不一致"
                )
                if not mapping_used:
                    reason += "；建议先在「科目映射」中确认映射关系"
                return PopulationReconcileFacts(
                    available=False,
                    unavailable_reason=reason,
                    mapping_used=mapping_used,
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
            mapping_used=mapping_used,
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
            mapping_used=mapping_used,
        )
