"""试算平衡表公式求值的 FormulaContext 数据底座（L2 预载层）。

spec: tb-adjustment-column-formula-closure（Phase 0，B7 修复的承载模块）

## 为什么是独立模块

`trial_balance_service.get_summary_with_adjustments` 原先用
`execute_formula(f, tb_amount_map, row_values)`，它内部走
`FormulaContext.from_simple_map` —— **只产 3 键**（期末余额 / 审定数 / 未审数）。
而 `formula_engine.COLUMN_ALIASES` 注册了 14 个列名，其余 11 个落进
`_resolve_tb_column` 的「已注册但该科目无数据」态：**恒 0、只记 trace、不报错**。

实测后果：真库利润表公式普遍写 `SUM_TB('6001~6099','本期发生额')`，
于是 **income_statement 78 行未审数全空**（缺陷编号 B7）。

本模块把「按标准科目码预载公式引擎可解析的全部列名」这件事收敛成单一实现，
理由与 `four_table/occurrence_by_standard_code.py` 相同：
调用方不止一个（Phase 1 的 `ADJ()` 落地后同样需要这份底座），
留在 service 里必然出现第二份各自漂移的拷贝。

## 语义约束（**不可改**）

`期末余额` / `审定数` / `未审数` 三键**一律等于 unadjusted_amount**。

这不是疏漏：调用方的公式只负责算**未审数列**，与 `from_simple_map` 的既有行为
逐字一致（零回归）。把「审定数」改成真的 `audited_amount` 会让未审数列变成
审定数列 —— 那是语义破坏而非修复。审定数由调用方在公式求值**之后**按
`unadj + aje_net + rje_net` 另算（见 ADR-ADJ-005 双口径）。

## 各键权威来源

| 键 | 来源 |
|----|------|
| 期末余额 / 审定数 / 未审数 | `trial_balance.unadjusted_amount`（见上方语义约束） |
| 年初余额 | `trial_balance.opening_balance` |
| 本期发生额 | `unadjusted − opening`（与 `report_engine._period_amount` 未审模式同口径） |
| 本期借方 / 本期贷方 | `tb_balance` 经共享件按标准码归集（叶子聚合，防父子双算） |
| AJE调整 / RJE调整 | `adjustment_amount_source.adj_net_batch` 的**归一净额**（与 TB 持久化列同源） |
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Callable
from uuid import UUID

import sqlalchemy as sa

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

__all__ = ["build_tb_formula_data", "PRELOADED_COLUMN_KEYS"]

#: 本模块保证写入每个科目的规范列名。
#:
#: 🔴 **本常量被 `build_tb_formula_data` 实际用于校验输出**（而非仅作文档）：
#: 每构造完一个科目的字典就断言键集 == 本常量。
#:
#: 这条自校验是补上来的 —— 首版本常量只出现在 `__all__` 与 docstring 里，
#: 实现另手写一份 9 个键的字面量，两份清单**无任何一致性检查**，是漂移温床；
#: 且首版注释声称「守卫据此断言」而那个守卫并不存在，属假声明。
#:
#: 判据按**键存在性**而非按值 —— `本期借方` 无 `tb_balance` 数据时的 0 是诚实的 0，
#: 真缺陷形态是规范名根本不在 tb_data 里（`_resolve_tb_column` 的「已注册但无数据」态）。
PRELOADED_COLUMN_KEYS: tuple[str, ...] = (
    "期末余额",
    "审定数",
    "未审数",
    "年初余额",
    "本期发生额",
    "AJE调整",
    "RJE调整",
    "本期借方",
    "本期贷方",
)


async def build_tb_formula_data(
    db: "AsyncSession",
    *,
    tb: sa.Table,
    project_id: UUID,
    year: int,
    company_code: str,
    adj_lookup: Callable[[str, str], Decimal],
) -> dict[str, dict[str, Decimal]]:
    """按标准科目码构造 `FormulaContext.tb_data`，预载 `PRELOADED_COLUMN_KEYS` 全部键。

    Args:
        db: 异步会话。
        tb: `trial_balance` 表对象（由调用方传入，避免本模块重复解析 ORM/Core 双形态）。
        project_id / year / company_code: 取数范围。
        adj_lookup: `(account_code, key) -> Decimal` 调整额查询，key ∈
            {aje_net, aje_dr, aje_cr, rje_net, rje_dr, rje_cr}。由调用方基于
            `adj_net_batch` 的结果构造 —— 本模块**不自查调整表**，
            以免成为口径矩阵的第 5 行。

    Returns:
        `{标准科目码: {列名: Decimal}}`。仅含 `trial_balance` 里有行的科目。
    """
    all_tb_q = sa.select(
        tb.c.standard_account_code,
        tb.c.unadjusted_amount,
        tb.c.opening_balance,
    ).where(
        tb.c.project_id == project_id,
        tb.c.year == year,
        tb.c.company_code == company_code,
        tb.c.is_deleted == sa.false(),
    )
    rows = (await db.execute(all_tb_q)).fetchall()

    unadj_map: dict[str, Decimal] = {}
    opening_map: dict[str, Decimal] = {}
    for r in rows:
        code = r.standard_account_code
        if not code:
            continue
        unadj_map[code] = unadj_map.get(code, Decimal("0")) + (
            r.unadjusted_amount or Decimal("0")
        )
        opening_map[code] = opening_map.get(code, Decimal("0")) + (
            r.opening_balance or Decimal("0")
        )

    tb_data: dict[str, dict[str, Decimal]] = {}
    for code, unadj in unadj_map.items():
        opening = opening_map.get(code, Decimal("0"))
        tb_data[code] = {
            "期末余额": unadj,
            "审定数": unadj,
            "未审数": unadj,
            "年初余额": opening,
            "本期发生额": unadj - opening,
            "AJE调整": adj_lookup(code, "aje_net"),
            "RJE调整": adj_lookup(code, "rje_net"),
            # 🔴 借贷发生额先置 0 占位，下方共享件有数据时覆盖。
            # **必须占位**：`_resolve_tb_column` 区分「已注册但无数据」（记 trace）
            # 与「有键值为 0」（诚实的 0）。`aggregate_occurrence` 有意不产零值键，
            # 若这里不占位，无 tb_balance 数据的科目会落进「无数据」态 ——
            # 那与 B7 的缺陷形态完全一样，只是范围小一点。
            "本期借方": Decimal("0"),
            "本期贷方": Decimal("0"),
        }

    # 借贷发生额两键：复用共享件（**禁**在此另写一份 tb_balance 查询）。
    # fail-open —— 发生额取数失败不应阻断整张报表，其余列名照常可用。
    try:
        from app.services.four_table.occurrence_by_standard_code import (
            fetch_occurrence_by_standard_code,
            merge_occurrence_into_tb_data,
        )

        occurrence = await fetch_occurrence_by_standard_code(db, project_id, year)
        merge_occurrence_into_tb_data(tb_data, occurrence)
    except Exception:
        logger.warning(
            "试算平衡表：发生额取数失败（project=%s year=%s），"
            "本期借方/本期贷方两列将为 0",
            project_id,
            year,
            exc_info=True,
        )

    # ── 输出自校验：键集必须恰为 PRELOADED_COLUMN_KEYS ──
    #
    # 🔴 让常量**真的参与运行**，而不是当文档挂着。上面的字面量与常量是两份清单，
    # 少写一个键就会退化成 B7 的「已注册但无数据」态（恒 0、只记 trace、不报错），
    # 那是最难发现的形态 —— 本断言把它变成启动即炸。
    #
    # 用 `assert` 而非 raise：这是**编程错误**（代码与常量不同步）而非数据异常，
    # 与本模块其余 fail-open 策略（数据取不到就降级）性质不同。
    expected = set(PRELOADED_COLUMN_KEYS)
    for code, cols in tb_data.items():
        missing = expected - set(cols)
        assert not missing, (
            f"科目 {code} 缺预载键 {sorted(missing)} —— "
            f"实现与 PRELOADED_COLUMN_KEYS 不同步，缺键会让公式取数静默返 0"
        )

    return tb_data


#: 公式里出现这些 token 之一，才需要载入调整额（避免为不用调整额的公式白查一次）。
_ADJ_TOKENS: tuple[str, ...] = ("ADJ(", "AJE调整", "RJE调整")


async def load_adj_map_if_needed(
    db: "AsyncSession",
    *,
    project_id: UUID,
    year: int,
    formula: str | None,
    account_codes: "set[str]",
    exclude_origins: frozenset[str],
) -> dict[str, dict[str, Decimal]] | None:
    """公式用到调整额时批量取数，否则返 ``None``（不发查询）。

    spec: tb-adjustment-column-formula-closure Phase 1

    ## 为什么在这里而不在 `formula_engine`

    `formula_engine` 的定位是 **L1 纯内核**（文件头声明「无 DB/async 耦合」）。
    把 `adj_net_batch` 调用写在它里面会破坏这个声明 —— 取数是 L2 的职责。
    本函数就是那个 L2 取数口，`FormulaEngine.execute` 调它。

    ## `exclude_origins` 必须由调用方显式给

    口径矩阵（见 `adjustment_amount_source` 文件头）有两行都涉及 ``ADJ()``：
    - 第 2 行「ADJ() 底稿呈现」：``frozenset()``（不排除，审计师要看到全部来源）
    - 第 4 行「试算平衡表调整列」：``frozenset({"workpaper"})``（防 V124 双计）

    本函数**不设默认值**，迫使调用方明示自己属哪一行 —— 给默认值会让
    下一个调用方在不知道有两种口径的情况下静默继承一个。

    Returns:
        ``adj_net_batch`` 的原样返回值；公式不含调整额 token 时返 ``None``。
        取数失败时返 ``None`` 并留 warning（fail-open，``ADJ()`` 得 0）。
    """
    if not formula or not any(t in formula for t in _ADJ_TOKENS):
        return None
    if not account_codes:
        return None
    try:
        from app.services.adjustment_amount_source import (
            DEFAULT_INCLUDE_STATUSES,
            adj_net_batch,
        )

        return await adj_net_batch(
            db,
            project_id=project_id,
            year=year,
            account_codes=account_codes,
            include_statuses=DEFAULT_INCLUDE_STATUSES,
            exclude_origins=exclude_origins,
        )
    except Exception:
        logger.warning(
            "调整额取数失败（project=%s year=%s formula=%s），ADJ()/AJE调整 将返 0",
            project_id,
            year,
            formula,
            exc_info=True,
        )
        return None
