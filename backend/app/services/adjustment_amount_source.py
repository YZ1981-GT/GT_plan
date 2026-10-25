"""adjustment_amount_source.py — 调整分录取数单一权威源.

spec: adj-formula-repair-and-approval-gate-wiring · 设计 §三 组件 1
与 formula_management/four_table_source.py 同构——后者是四表库取数的单一入口。

本模块提供：
- normalize_adj_type: 第二参归一（兼容 aje_net/AJE/审计调整 等全部既有写法）
- adj_net: 单点取数函数
- adj_net_batch: 批量对偶（多科目 × 两类型一次查询，避免按报表行次汇总时 N+1）

口径矩阵（各行不同是刻意的，见 ADR-ADJ-002/003）：
| 用途                          | review_status | origin        |
|-------------------------------|---------------|---------------|
| TB 调整列（参与审定数计算）    | 仅 approved   | 排除 workpaper |
| ADJ() 底稿呈现               | 仅 approved   | 不排除         |
| 交叉核对                      | 与 ADJ() 一致 | 不排除         |
| 试算平衡表调整列（按报表行次） | 仅 approved   | 排除 workpaper |

🔴 第 4 行是 spec tb-adjustment-column-formula-closure Phase 0 补的第四处收敛。
改造前 `trial_balance_service.get_summary_with_adjustments` 自写聚合且
**三个过滤全缺**（无 review_status ⇒ draft 被计入；无 origin ⇒ 与审定表 writeback
双计；查主表 adjustments 的遗留冗余列而非明细表 ⇒ 科目错配），
与本表第 1 行同语义却给出不同的数 —— 那正是它必须收敛进来的理由。

差异通过 include_statuses / exclude_origins **显式参数**体现在调用点，
不再靠注释声称一致而实际不同。

## 两个公式写法的语义差异（**不要混用**）

spec tb-adjustment-column-formula-closure Phase 1 Task 1.12。
平台有两种在公式里取调整额的写法，读的是**不同的东西**：

| 写法 | 数据源 | 语义 | 何时用 |
|------|--------|------|--------|
| ``TB(code,'AJE调整')``  | ``trial_balance.aje_adjustment`` | **持久化快照** —— 由 ``recalc_adjustments`` 落列，是上一次重算的结果 | 需要与试算表展示值、审定数计算逐字一致时 |
| ``ADJ(code,'aje_net')`` | ``adj_net_batch``（现算） | **实时汇总** —— 按当前 approved 分录即时聚合 | 需要反映"此刻的分录状态"时 |

两者**可以不等**，不等即说明快照过期（新分录已确认但尚未重算）。

🔴 这不是缺陷而是设计：``recalc_adjustments`` 是显式触发的（事件驱动 +
``ADJUSTMENT_APPROVED`` handler），不在每次读取时重算。真库现状就是
持久化列全 0 而实时值非 0。

差异由 ``consistency_check_service._check_adjustment_snapshot_vs_realtime``
（``check_full_chain`` 第 6 项）**显式报告**，不静默取其中一个、也不自动重算
（需求 3.3）。守卫见 ``tests/test_adj_snapshot_drift_signal.py``。

``ADJ()`` 只暴露归一净额（``*_net``），**不给** ``*_dr``/``*_cr``：
公式引擎属计算域，取原始借贷参与算式会对贷方正常类方向反掉（Phase 0 的 B4 缺陷）。
``ADJ(code,'aje_dr')`` 走 ``normalize_adj_type`` 归一失败路径报错，而非静默返回借方合计。

ADR-ADJ-001: 科目列统一走 adjustment_entries.standard_account_code + JOIN adjustments
ADR-ADJ-005: 展示用原始借贷（未归一）与计算用归一净额并存，见 adj_net_batch 返回值
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

import sqlalchemy as sa

if TYPE_CHECKING:
    from collections.abc import Collection

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 类型归一表（模块级常量）
# ---------------------------------------------------------------------------
# key = raw 字面量的 lower()，value = 归一后的标准值
_ADJ_TYPE_NORMALIZE: dict[str, str] = {
    # AJE 族
    "aje_net": "aje",
    "aje": "aje",
    "审计调整": "aje",
    # RJE 族
    "rje_net": "rje",
    "rje": "rje",
    "重分类": "rje",
}

# ADR-ADJ-003: 试算表调整列默认只纳入 approved
DEFAULT_INCLUDE_STATUSES: frozenset[str] = frozenset({"approved"})


def normalize_adj_type(raw: str) -> str:
    """将调整类型字面量归一到 ``"aje"`` 或 ``"rje"``。

    同时兼容既有写法：aje_net / AJE / 审计调整 / rje_net / RJE / 重分类。
    不可归一时 **raise ValueError**，禁止静默省略 adjustment_type 过滤。

    >>> normalize_adj_type("aje_net")
    'aje'
    >>> normalize_adj_type("RJE")
    'rje'
    >>> normalize_adj_type("审计调整")
    'aje'
    """
    if not raw or not raw.strip():
        raise ValueError(f"调整类型为空，无法归一: {raw!r}")
    key = raw.strip().lower()
    result = _ADJ_TYPE_NORMALIZE.get(key)
    if result is None:
        raise ValueError(
            f"无法将调整类型 {raw!r} 归一到 aje/rje。"
            f"合法值: {sorted(_ADJ_TYPE_NORMALIZE.keys())}"
        )
    return result


# ---------------------------------------------------------------------------
# 合法字面量白名单（供 CI 守卫使用）
# ---------------------------------------------------------------------------
VALID_ADJ_TYPE_LITERALS: frozenset[str] = frozenset(_ADJ_TYPE_NORMALIZE.keys())


async def adj_net(
    db: "AsyncSession",
    *,
    project_id: UUID,
    year: int,
    account_code: str,
    adj_type: str,
    include_statuses: frozenset[str] | None = None,
    exclude_origins: frozenset[str] = frozenset(),
) -> Decimal:
    """从调整分录表取指定科目的 AJE/RJE 净额（单点取数，三处调用点的唯一实现）。

    ADR-ADJ-001: 科目列走 adjustment_entries.standard_account_code + JOIN adjustments
    （origin / review_status 只在主表 adjustments）。

    符号归一：按 direction_resolver 将 SUM(debit-credit) 归一到科目自然方向
    （贷方类取反），与 trial_balance.aje_adjustment/rje_adjustment 口径一致。

    Args:
        db: 异步 DB session（只读，只 flush 不 commit）
        project_id: 项目 ID
        year: 会计年度
        account_code: 标准科目编码
        adj_type: 归一前的原始字面量（内部调 normalize_adj_type）
        include_statuses: 纳入的 review_status 集合。
            None = 使用 DEFAULT_INCLUDE_STATUSES（仅 approved，ADR-ADJ-003）。
            传空 frozenset() = 不过滤（纳入所有状态）。
        exclude_origins: 排除的 origin 集合。
            如 frozenset({"workpaper"})（TB 列传此值防 V124 双计）。
            空集 = 不排除（公式取数口径，ADR-ADJ-002）。

    Returns:
        按科目自然方向归一后的净额 Decimal（无数据返回 Decimal("0")）。
    """
    from app.models.audit_platform_models import Adjustment, AdjustmentEntry
    from app.services.ledger_import.direction_resolver import resolve_account_direction

    normalized_type = normalize_adj_type(adj_type)

    # 有效的 statuses 集合（None → 默认口径）
    statuses = include_statuses if include_statuses is not None else DEFAULT_INCLUDE_STATUSES

    # 构建查询：ADR-ADJ-001 统一走 entry 表 + JOIN 主表
    q = sa.select(
        sa.func.coalesce(
            sa.func.sum(AdjustmentEntry.debit_amount - AdjustmentEntry.credit_amount), 0
        ).label("net"),
        sa.func.max(AdjustmentEntry.account_name).label("account_name"),
    ).join(
        Adjustment, AdjustmentEntry.adjustment_id == Adjustment.id
    ).where(
        Adjustment.project_id == project_id,
        Adjustment.year == year,
        Adjustment.is_deleted == sa.false(),
        AdjustmentEntry.standard_account_code == account_code,
        Adjustment.adjustment_type == normalized_type,
    )

    # review_status 过滤（非空集才加条件）
    if statuses:
        q = q.where(Adjustment.review_status.in_(list(statuses)))

    # origin 排除（非空集才加条件）
    if exclude_origins:
        for origin in exclude_origins:
            q = q.where(
                sa.or_(Adjustment.origin.is_(None), Adjustment.origin != origin)
            )

    result = await db.execute(q)
    row = result.first()

    if row is None or row[0] is None:
        return Decimal("0")

    raw_net = Decimal(str(row[0]))
    account_name = (row[1] if len(row) > 1 else None) or ""

    # 符号归一：贷方类取反
    direction, _src = resolve_account_direction(account_code, account_name)
    sign = Decimal("-1") if direction == "credit" else Decimal("1")
    result = sign * raw_net

    # C1 实测修正：贷方类无数据时 `-1 * Decimal("0")` 得 **Decimal("-0")**。
    # 虽然 `-0 == 0` 为 True，但它会以 "-0" 形态流向前端展示 / Excel 写格 /
    # 字符串比较，属可见的脏值。归零为规范的 Decimal("0")。
    if result.is_zero():
        return Decimal("0")
    return result


async def adj_net_batch(
    db: "AsyncSession",
    *,
    project_id: UUID,
    year: int,
    account_codes: "Collection[str]",
    include_statuses: frozenset[str] | None = None,
    exclude_origins: frozenset[str] = frozenset(),
) -> dict[str, dict[str, Decimal]]:
    """批量取多科目的 AJE/RJE 调整额（``adj_net`` 的批量对偶）。

    spec: tb-adjustment-column-formula-closure Phase 0 Task 0.3

    与 ``adj_net`` **同源同口径**：同一份 JOIN + 同一组过滤 + 同一套符号归一。
    差别仅在于一次查询返回多科目 × 两种调整类型，供试算平衡表按报表行次汇总时
    避免 N+1（一张报表动辄上百个科目）。

    🔴 **为何返回 6 个键而非只返回净额**：试算平衡表要展示「审计调整借方/贷方」
    「重分类调整借方/贷方」四列，只给净额填不出这四列；而审定数又必须用**归一后**
    净额才方向正确（见 ADR-ADJ-005）。两种口径都是调用方的正当需求，故本函数
    返回完整事实（原始借贷 + 归一净额），由调用方选用，**禁**在此替调用方裁剪。

    Returns:
        ``{标准科目编码: {"aje_net", "aje_dr", "aje_cr", "rje_net", "rje_dr", "rje_cr"}}``

        - ``*_dr`` / ``*_cr``：**原始**借方/贷方合计（未做符号归一，恒非负）。
          用于展示「分录实际借贷了多少」。
        - ``*_net``：按科目自然方向**归一后**的净额（贷方类取反），与
          ``adj_net`` 单点返回值、``trial_balance.aje_adjustment`` 列口径一致。
          用于参与审定数计算。

        只返回**有数据**的科目；调用方对缺失科目应按 0 处理（用 ``.get(code, {})``）。

    Args:
        account_codes: 标准科目编码集合。**空集合直接返回 ``{}``**（不发查询），
            与调用点既有的 ``if all_account_codes:`` 守卫语义一致。
        include_statuses: 同 ``adj_net``。None = ``DEFAULT_INCLUDE_STATUSES``（仅 approved）。
            传空 ``frozenset()`` = 不过滤。
        exclude_origins: 同 ``adj_net``。试算表调整列传 ``{"workpaper"}`` 防 V124 双计。

    Note:
        符号归一用的 ``account_name`` 取自 ``AdjustmentEntry.account_name``
        （``MAX`` 聚合），与 ``adj_net`` 一致。⚠️ ``recalc_adjustments`` 用的是
        ``trial_balance.account_name``，两个来源不同 ⇒ ``resolve_account_direction``
        结果可能不同，**不可假定二者等价**（见 evidence/phase0-pre-existing-red.md）。
    """
    from app.models.audit_platform_models import Adjustment, AdjustmentEntry
    from app.services.ledger_import.direction_resolver import resolve_account_direction

    codes = [c for c in (account_codes or []) if c]
    if not codes:
        return {}

    statuses = include_statuses if include_statuses is not None else DEFAULT_INCLUDE_STATUSES

    # 查询与 adj_net 逐条对应：同一 JOIN（ADR-ADJ-001）、同一过滤、只多了分组
    q = sa.select(
        AdjustmentEntry.standard_account_code.label("code"),
        Adjustment.adjustment_type.label("adj_type"),
        sa.func.coalesce(sa.func.sum(AdjustmentEntry.debit_amount), 0).label("dr"),
        sa.func.coalesce(sa.func.sum(AdjustmentEntry.credit_amount), 0).label("cr"),
        sa.func.max(AdjustmentEntry.account_name).label("account_name"),
    ).join(
        Adjustment, AdjustmentEntry.adjustment_id == Adjustment.id
    ).where(
        Adjustment.project_id == project_id,
        Adjustment.year == year,
        Adjustment.is_deleted == sa.false(),
        AdjustmentEntry.standard_account_code.in_(codes),
    ).group_by(
        AdjustmentEntry.standard_account_code,
        Adjustment.adjustment_type,
    )

    if statuses:
        q = q.where(Adjustment.review_status.in_(list(statuses)))

    if exclude_origins:
        for origin in exclude_origins:
            q = q.where(
                sa.or_(Adjustment.origin.is_(None), Adjustment.origin != origin)
            )

    result = await db.execute(q)

    out: dict[str, dict[str, Decimal]] = {}
    for row in result.fetchall():
        code = row.code
        if not code:
            continue
        # adjustment_type 可能是 Enum 实例或裸字符串（两种写法在库内并存）
        raw_type = getattr(row.adj_type, "value", row.adj_type)
        try:
            norm_type = normalize_adj_type(str(raw_type))
        except ValueError:
            # 不可归一的类型不静默丢弃 —— 记日志后跳过，避免污染净额
            logger.warning(
                "adj_net_batch: 科目 %s 出现无法归一的 adjustment_type=%r，已跳过",
                code, raw_type,
            )
            continue

        dr = Decimal(str(row.dr or 0))
        cr = Decimal(str(row.cr or 0))

        direction, _src = resolve_account_direction(code, row.account_name or "")
        sign = Decimal("-1") if direction == "credit" else Decimal("1")
        net = sign * (dr - cr)
        # 与 adj_net 一致：贷方类无数据时 -1*0 得 Decimal("-0")，归零为规范 0
        if net.is_zero():
            net = Decimal("0")

        bucket = out.setdefault(code, {
            "aje_net": Decimal("0"), "aje_dr": Decimal("0"), "aje_cr": Decimal("0"),
            "rje_net": Decimal("0"), "rje_dr": Decimal("0"), "rje_cr": Decimal("0"),
        })
        bucket[f"{norm_type}_net"] += net
        bucket[f"{norm_type}_dr"] += dr
        bucket[f"{norm_type}_cr"] += cr

    return out
