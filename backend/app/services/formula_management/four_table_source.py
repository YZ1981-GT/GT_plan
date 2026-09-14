"""四表库叶子源只读守卫 + 取数契约（Formula Management Library · Task 2.3）。

四表库（``trial_balance`` / ``tb_balance`` / ``tb_ledger`` / ``tb_aux_balance``）是
公式取数的**叶子源**：只可被 ``TB()`` / ``PREV()`` / ``AUX()`` 读取，**不可**被
``auto_calc`` 回填型公式写入（否则原始数据被公式污染，取数口径失真）。

本模块提供两组能力：

1. **只读守卫（Req 12.2）**：``guard_four_table_leaf_readonly`` 在**定义/保存**公式
   时，若目标地址指向四表库单元且公式为 ``auto_calc`` 回填型，则拒绝。
   ``execute_formula`` 的 auto_calc 分支亦做防御性检查，绝不把值写回四表库。

2. **取数契约（Req 12.1/12.3/12.4/12.5）**：``tb_value`` / ``prev_value`` /
   ``aux_value`` 统一经 ``get_active_filter`` 读取（禁止裸写 ``is_deleted==False``）：
   - ``tb_balance`` 保留 direction v1 **借正贷负**（``debit - credit``），使备抵类
     科目（累计折旧、库存股等）取数不失真（Req 12.3）。
   - 损益类科目（编码 5xxx/6xxx）取 ``tb_ledger`` **发生额**（单边：收入取贷方、
     费用/成本取借方），而非期末余额（Req 12.4）。
   - 辅助维度按 ``aux_type`` **分组读取** ``tb_aux_balance``：查询强制约束到单一
     ``aux_type``，避免同一科目余额在多个维度类型间冗余重复计数（Req 12.5）。

工程铁律：四表库取数一律经 ``get_active_filter`` 统一入口（dataset 版本治理 +
``is_deleted`` 过滤），不在此散落裸过滤条件。

Requirements: 12.1, 12.2, 12.3, 12.4, 12.5
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    TbAuxBalance,
    TbBalance,
    TbLedger,
    TrialBalance,
)
from app.services.dataset_query import get_active_filter
from app.services.ledger_import.direction_resolver import resolve_account_direction

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 四表库身份识别 + 只读守卫（Req 12.2）
# ─────────────────────────────────────────────────────────────────────────────
FOUR_TABLE_NAMES: frozenset[str] = frozenset(
    {"trial_balance", "tb_balance", "tb_ledger", "tb_aux_balance"}
)

# 四表库地址的 ACNR 形态（对齐 acnr/resolver.py 的非 wp 域检测）：
#   URI 前缀 tb:// / aux://；公式函数 TB(/PREV(/AUX(/SUM_TB(；索引命名空间 tb:/aux:
_FOUR_TABLE_URI_PREFIXES: tuple[str, ...] = ("tb://", "aux://")
_FOUR_TABLE_FORMULA_FUNCS: tuple[str, ...] = ("TB(", "PREV(", "AUX(", "SUM_TB(")
_FOUR_TABLE_INDEX_NS: tuple[str, ...] = ("tb:", "aux:")


class FourTableReadonlyError(ValueError):
    """尝试对四表库叶子源单元定义 auto_calc 回填公式时抛出。"""


def is_four_table_target(target: object) -> bool:
    """判断目标地址是否指向四表库单元。

    识别以下任一形态即视为四表库地址：
    - 直接含四表库表名（``trial_balance`` / ``tb_balance`` / ``tb_ledger`` /
      ``tb_aux_balance``）；
    - ACNR 非 wp 域 URI 前缀 ``tb://`` / ``aux://``；
    - 取数公式函数起始 ``TB(`` / ``PREV(`` / ``AUX(`` / ``SUM_TB(``；
    - 索引命名空间前缀 ``tb:`` / ``aux:``（区别于 ``tb://``，如 ``TB:1001``）。

    非四表库地址（如底稿单元 ``WP('D2','s','E1')`` / 报表行 ``report/BS/1``）返回
    False。
    """
    if not target:
        return False
    s = str(target).strip()
    if not s:
        return False
    low = s.lower()
    up = s.upper()

    if any(name in low for name in FOUR_TABLE_NAMES):
        return True
    if low.startswith(_FOUR_TABLE_URI_PREFIXES):
        return True
    if up.startswith(_FOUR_TABLE_FORMULA_FUNCS):
        return True
    if low.startswith(_FOUR_TABLE_INDEX_NS):
        return True
    return False


def guard_four_table_leaf_readonly(*, formula_type: str | None, target: object) -> None:
    """只读守卫：目标为四表库单元时拒绝定义 auto_calc 回填公式（Req 12.2）。

    仅 ``auto_calc``（回填型）被拒绝；``logic_check`` / ``reasonability``（不改值）
    可正常引用四表库地址作条件/提示，不受此守卫限制。

    Raises:
        FourTableReadonlyError: 当 ``formula_type == 'auto_calc'`` 且 ``target`` 指向
            四表库单元时。
    """
    if (formula_type or "").strip() == "auto_calc" and is_four_table_target(target):
        raise FourTableReadonlyError(
            f"四表库为只读叶子源，禁止对其单元定义 auto_calc 回填公式：{target!r}。"
            "四表库仅可被 TB()/PREV()/AUX() 读取。"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 取数契约辅助
# ─────────────────────────────────────────────────────────────────────────────
_PNL_CODE_PREFIXES: tuple[str, ...] = ("5", "6")  # 损益类（成本/费用/收入）


def _dec(value: object) -> Decimal:
    """安全转 Decimal，None → 0。"""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _is_pnl(account_code: str) -> bool:
    """损益类科目判定：编码首位为 5 或 6（成本/费用/收入）。"""
    code = (account_code or "").strip()
    return bool(code) and code[0] in _PNL_CODE_PREFIXES


def _normalize_column(column: str | None) -> str:
    """把中文/英文列名归一为 ``opening`` / ``closing`` / ``period``。"""
    c = (column or "").strip()
    if c in ("年初余额", "期初余额", "年初", "期初", "opening", "opening_balance"):
        return "opening"
    if c in ("本期发生额", "发生额", "period", "period_amount"):
        return "period"
    # 期末余额 / 审定数 / closing 及默认
    return "closing"


def _signed_v1(debit: object, credit: object, balance: object) -> Decimal:
    """v1 借正贷负带符号值（Req 12.3）。

    优先使用借/贷发生额 ``debit - credit``（天然借正贷负，备抵类科目自然为负、
    不失真）；两者皆无数据时回退余额列（``tb_balance`` 余额按 v1 口径已是借正贷负）。
    """
    if debit is not None or credit is not None:
        return _dec(debit) - _dec(credit)
    return _dec(balance)


async def _balance_signed(
    db: AsyncSession,
    table_model,
    *,
    project_id: UUID,
    year: int,
    account_code: str,
    which: str,  # opening | closing
    extra_conds: Optional[list] = None,
    current_user_id: UUID | None = None,
) -> Decimal:
    """从余额型表（tb_balance / tb_aux_balance）读单一科目的 v1 借正贷负值。

    经 ``get_active_filter`` 统一过滤；对同一 account_code 的多行（多公司/多维度
    成员）汇总。debit/credit 列不做 coalesce（保留 None 信号供 ``_signed_v1``
    判断是否回退余额列）。
    """
    tbl = table_model.__table__
    flt = await get_active_filter(
        db, tbl, project_id, year, current_user_id=current_user_id
    )
    if which == "opening":
        d_col, c_col, b_col = (
            tbl.c.opening_debit,
            tbl.c.opening_credit,
            tbl.c.opening_balance,
        )
    else:
        d_col, c_col, b_col = (
            tbl.c.closing_debit,
            tbl.c.closing_credit,
            tbl.c.closing_balance,
        )
    conds = [flt, tbl.c.account_code == account_code]
    if extra_conds:
        conds.extend(extra_conds)
    q = sa.select(
        sa.func.sum(d_col),
        sa.func.sum(c_col),
        sa.func.sum(b_col),
    ).where(*conds)
    debit_sum, credit_sum, balance_sum = (await db.execute(q)).one()
    return _signed_v1(debit_sum, credit_sum, balance_sum)


async def _ledger_occurrence(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    account_code: str,
    current_user_id: UUID | None = None,
) -> Decimal:
    """损益类科目从 ``tb_ledger`` 取单边发生额（Req 12.4）。

    经 ``get_active_filter`` 统一过滤；按科目自然方向取单边：收入类（贷方正常）取
    贷方发生额，费用/成本类（借方正常）取借方发生额（对齐 trial_balance_service
    的「本期发生额」口径），而非期末余额。
    """
    tbl = TbLedger.__table__
    flt = await get_active_filter(
        db, tbl, project_id, year, current_user_id=current_user_id
    )
    q = sa.select(
        sa.func.max(tbl.c.account_name),
        sa.func.coalesce(sa.func.sum(tbl.c.debit_amount), 0),
        sa.func.coalesce(sa.func.sum(tbl.c.credit_amount), 0),
    ).where(flt, tbl.c.account_code == account_code)
    account_name, debit_sum, credit_sum = (await db.execute(q)).one()
    direction, _source = resolve_account_direction(account_code, account_name or "")
    # 单边发生额：收入取贷方、费用/成本取借方。
    occurrence = credit_sum if direction == "credit" else debit_sum
    return _dec(occurrence)


# ─────────────────────────────────────────────────────────────────────────────
# 取数公开入口：TB() / PREV() / AUX()
# ─────────────────────────────────────────────────────────────────────────────
async def tb_value(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    account_code: str,
    column: str = "期末余额",
    current_user_id: UUID | None = None,
) -> Decimal:
    """``TB(account_code, column)`` 取数（Req 12.1/12.3/12.4）。

    - 损益类科目（5xxx/6xxx）：取 ``tb_ledger`` 发生额（不取期末余额，Req 12.4）；
      请求 ``opening`` 列时返回 0（损益类无期初余额）。
    - 资产负债权益类：从 ``tb_balance`` 取 v1 借正贷负值（Req 12.3）；
      ``period``（本期发生额）= 期末 − 期初。

    统一经 ``get_active_filter`` 读取（Req 12.1）。
    """
    col = _normalize_column(column)

    if _is_pnl(account_code):
        if col == "opening":
            return Decimal("0")  # 损益类无期初余额
        return await _ledger_occurrence(
            db,
            project_id=project_id,
            year=year,
            account_code=account_code,
            current_user_id=current_user_id,
        )

    if col == "opening":
        return await _balance_signed(
            db,
            TbBalance,
            project_id=project_id,
            year=year,
            account_code=account_code,
            which="opening",
            current_user_id=current_user_id,
        )
    if col == "period":
        closing = await _balance_signed(
            db,
            TbBalance,
            project_id=project_id,
            year=year,
            account_code=account_code,
            which="closing",
            current_user_id=current_user_id,
        )
        opening = await _balance_signed(
            db,
            TbBalance,
            project_id=project_id,
            year=year,
            account_code=account_code,
            which="opening",
            current_user_id=current_user_id,
        )
        return closing - opening
    # closing（期末余额 / 审定数）
    return await _balance_signed(
        db,
        TbBalance,
        project_id=project_id,
        year=year,
        account_code=account_code,
        which="closing",
        current_user_id=current_user_id,
    )


async def prev_value(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    account_code: str,
    column: str = "期末余额",
    current_user_id: UUID | None = None,
) -> Decimal:
    """``PREV(account_code, column)`` 取上年（year-1）同口径数据（Req 12.1）。

    语义与 ``tb_value`` 一致，仅年度前推一年，同样经 ``get_active_filter`` 读取。
    """
    return await tb_value(
        db,
        project_id=project_id,
        year=year - 1,
        account_code=account_code,
        column=column,
        current_user_id=current_user_id,
    )


async def aux_value(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    account_code: str,
    aux_type: str,
    aux_code: str | None = None,
    column: str = "期末余额",
    current_user_id: UUID | None = None,
) -> Decimal:
    """``AUX(account_code, aux_type[, aux_code], column)`` 辅助维度取数（Req 12.5）。

    查询**强制约束到单一 ``aux_type``**（必传），因 ``tb_aux_balance`` 同一科目余额
    在不同维度类型间冗余存储，跨 aux_type 汇总会重复计数。给定 ``aux_code`` 时进一步
    定位到该维度成员，否则汇总该 aux_type 下全部成员（= 该科目在此维度类型的合计）。

    值为 v1 借正贷负（Req 12.3 一致口径），统一经 ``get_active_filter`` 读取。
    """
    tbl = TbAuxBalance.__table__
    extra: list = [tbl.c.aux_type == aux_type]
    if aux_code is not None:
        extra.append(tbl.c.aux_code == aux_code)
    col = _normalize_column(column)
    which = "opening" if col == "opening" else "closing"
    if col == "period":
        closing = await _balance_signed(
            db,
            TbAuxBalance,
            project_id=project_id,
            year=year,
            account_code=account_code,
            which="closing",
            extra_conds=extra,
            current_user_id=current_user_id,
        )
        opening = await _balance_signed(
            db,
            TbAuxBalance,
            project_id=project_id,
            year=year,
            account_code=account_code,
            which="opening",
            extra_conds=extra,
            current_user_id=current_user_id,
        )
        return closing - opening
    return await _balance_signed(
        db,
        TbAuxBalance,
        project_id=project_id,
        year=year,
        account_code=account_code,
        which=which,
        extra_conds=extra,
        current_user_id=current_user_id,
    )


__all__ = [
    "FOUR_TABLE_NAMES",
    "FourTableReadonlyError",
    "is_four_table_target",
    "guard_four_table_leaf_readonly",
    "tb_value",
    "prev_value",
    "aux_value",
]

# 引用 TrialBalance 以在四表库表名集合语义上保持显式（trial_balance 亦为叶子源）。
_ = TrialBalance
