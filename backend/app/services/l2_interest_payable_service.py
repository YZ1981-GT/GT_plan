"""L2 应付利息 — 业务逻辑服务

纯函数计算引擎（无DB依赖，可单独测试）+ 带DB的计提核对查询。

提供功能：
- 计提核对（L1/L3利息测算 vs L2账面计提）
- 按来源汇总应付利息（短期借款/长期借款/应付债券）
- 负债类公式验证（期末=期初+贷方-借方）

科目2231应付利息（贷方/负债类）：期末=期初+贷方-借方

Service只flush不commit（由调用方控制事务）。

Requirements: 4.4, 6.1-6.2
"""

from __future__ import annotations

import json
import logging
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# checklist_responses item_id 常量
_L2_DETAIL_ITEM_ID = "L2-detail-rows"
_L1_INTEREST_ITEM_ID = "L1-interest-calc-rows"
_L3_INTEREST_ITEM_ID = "L3-interest-calc-rows"

# 来源类别枚举
SOURCE_SHORT_TERM = "短期借款"
SOURCE_LONG_TERM = "长期借款"
SOURCE_BOND = "应付债券"
_VALID_SOURCES = {SOURCE_SHORT_TERM, SOURCE_LONG_TERM, SOURCE_BOND}


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：负债类公式验证
# ═══════════════════════════════════════════════════════════════════════════════


def validate_liability_formula(
    begin: float, credit: float, debit: float, end: float, tolerance: float = 0.01
) -> bool:
    """验证负债类公式：end == begin + credit - debit

    负债类科目（贷方余额）：
    - 贷方增加（计提利息）
    - 借方减少（支付利息）
    - 期末 = 期初 + 贷方 - 借方

    Args:
        begin: 期初余额
        credit: 贷方发生额（计提）
        debit: 借方发生额（支付）
        end: 期末余额（报告值）
        tolerance: 容差（默认0.01元）

    Returns:
        True if |end - (begin + credit - debit)| <= tolerance

    Requirements: 6.1
    """
    expected = begin + credit - debit
    return abs(end - expected) <= tolerance


def calc_liability_end_balance(begin: float, credit: float, debit: float) -> float:
    """计算负债类期末余额 = 期初 + 贷方 - 借方

    Requirements: 6.1
    """
    return begin + credit - debit


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：计提差异计算
# ═══════════════════════════════════════════════════════════════════════════════


def calc_accrual_diff(estimated: float, booked: float) -> float:
    """计提差异 = 测算利息 - 账面计提

    正数表示少计利息（账面偏低），负数表示多计利息（账面偏高）。

    Requirements: 4.4
    """
    return estimated - booked


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：按来源汇总
# ═══════════════════════════════════════════════════════════════════════════════


def aggregate_by_source(details: list[dict]) -> dict[str, float]:
    """按来源汇总应付利息金额

    将明细行按 sourceCategory 分组求和 currentAccrual 字段。
    未匹配已知来源类别的归入"其他"。

    Args:
        details: L2明细行列表，每行含 sourceCategory + currentAccrual

    Returns:
        {来源类别: 合计金额}，如 {"短期借款": 1000.0, "长期借款": 2000.0, ...}

    Requirements: 6.2
    """
    result: dict[str, float] = {}
    for row in details:
        source = row.get("sourceCategory", "").strip()
        if not source or source not in _VALID_SOURCES:
            source = "其他"
        amount = _safe_float(row.get("currentAccrual", 0))
        result[source] = result.get(source, 0.0) + amount
    return result


def aggregate_by_source_with_total(details: list[dict]) -> dict:
    """按来源汇总 + 总计

    Returns:
        {
            "by_source": {"短期借款": ..., "长期借款": ..., ...},
            "total": 总合计
        }

    Requirements: 6.2
    """
    by_source = aggregate_by_source(details)
    total = sum(by_source.values())
    return {"by_source": by_source, "total": total}


# ═══════════════════════════════════════════════════════════════════════════════
# DB查询：计提核对（L1/L3 vs L2）
# ═══════════════════════════════════════════════════════════════════════════════


class L2InterestPayableService:
    """L2 应付利息业务服务层

    核心功能：
    - 计提核对（L1/L3利息测算 vs L2账面计提）
    - 按来源汇总应付利息
    - 负债类公式验证

    Service只flush不commit（由调用方控制事务）。
    """

    async def get_accrual_reconciliation(
        self, db: AsyncSession, wp_id: str, project_id: str | None = None
    ) -> dict:
        """计提核对：获取L1/L3利息测算 vs L2账面计提对比

        从 checklist_responses 表读取：
        - L2明细 (item_id='L2-detail-rows') → 账面计提合计
        - L1利息 (item_id='L1-interest-calc-rows') → L1测算合计
        - L3利息 (item_id='L3-interest-calc-rows') → L3测算合计

        L1/L3数据通过 cross-project JOIN (同project下的其他wp) 获取。

        Args:
            db: 数据库会话
            wp_id: 当前L2底稿的wp_id
            project_id: 项目ID（可选，若None则从wp_id推断）

        Returns:
            {
                "l1_interest": L1利息测算合计,
                "l3_interest": L3利息测算合计,
                "total_estimated": L1+L3合计,
                "l2_booked": L2账面计提合计,
                "diff": 差异(测算-账面),
                "is_consistent": 是否一致(|diff|<0.01),
                "by_source": 按来源拆分明细
            }

        Requirements: 4.4
        """
        # ─── L2账面计提 ──────────────────────────────────────────────────
        l2_details = await self._load_detail_rows(db, wp_id)
        l2_booked = sum(_safe_float(r.get("currentAccrual", 0)) for r in l2_details)
        by_source = aggregate_by_source(l2_details)

        # ─── L1利息测算（同project跨wp JOIN） ───────────────────────────
        l1_interest = await self._load_cross_project_interest(
            db, wp_id, _L1_INTEREST_ITEM_ID
        )

        # ─── L3利息测算（同project跨wp JOIN） ───────────────────────────
        l3_interest = await self._load_cross_project_interest(
            db, wp_id, _L3_INTEREST_ITEM_ID
        )

        # ─── 汇总 ────────────────────────────────────────────────────────
        total_estimated = l1_interest + l3_interest
        diff = calc_accrual_diff(total_estimated, l2_booked)
        is_consistent = abs(diff) < 0.01

        return {
            "l1_interest": round(l1_interest, 2),
            "l3_interest": round(l3_interest, 2),
            "total_estimated": round(total_estimated, 2),
            "l2_booked": round(l2_booked, 2),
            "diff": round(diff, 2),
            "is_consistent": is_consistent,
            "by_source": {k: round(v, 2) for k, v in by_source.items()},
        }

    async def aggregate_by_source(self, db: AsyncSession, wp_id: str) -> dict[str, float]:
        """按来源汇总应付利息（短期借款/长期借款/应付债券）

        从 checklist_responses 读取L2明细行，按 sourceCategory 分组求和。

        Args:
            db: 数据库会话
            wp_id: L2底稿的wp_id

        Returns:
            {来源类别: 合计金额}

        Requirements: 6.1-6.2
        """
        details = await self._load_detail_rows(db, wp_id)
        return aggregate_by_source(details)

    def validate_liability_formula(
        self, begin: float, credit: float, debit: float, end: float
    ) -> bool:
        """验证负债类公式：end == begin + credit - debit

        委托给模块级纯函数，方便单元测试。

        Requirements: 6.1
        """
        return validate_liability_formula(begin, credit, debit, end)

    # ─── 内部辅助 ────────────────────────────────────────────────────────

    async def _load_detail_rows(self, db: AsyncSession, wp_id: str) -> list[dict]:
        """从 checklist_responses 加载L2明细行"""
        try:
            result = await db.execute(
                sa.text(
                    "SELECT remark FROM checklist_responses "
                    "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
                ),
                {"wp_id": wp_id, "item_id": _L2_DETAIL_ITEM_ID},
            )
            row = result.fetchone()
            if row and row.remark:
                return json.loads(row.remark)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("L2 service: 解析明细行JSON失败 wp_id=%s: %s", wp_id, e)
        except Exception as e:  # noqa: BLE001
            logger.warning("L2 service: 加载明细行失败 wp_id=%s: %s", wp_id, e)
        return []

    async def _load_cross_project_interest(
        self, db: AsyncSession, wp_id: str, item_id: str
    ) -> float:
        """从同project下的其他wp加载利息测算合计

        通过 cross-project JOIN:
        working_papers wp1 (当前L2) JOIN working_paper wp2 (同project)
        → checklist_responses cr (目标item_id)
        """
        total: float = 0.0
        try:
            result = await db.execute(
                sa.text(
                    "SELECT cr.remark FROM checklist_responses cr "
                    "JOIN working_paper wp1 ON wp1.id = cr.wp_id "
                    "JOIN working_paper wp2 ON wp2.project_id = wp1.project_id "
                    "WHERE wp2.id = :wp_id "
                    "AND cr.item_id = :item_id "
                    "LIMIT 1"
                ),
                {"wp_id": wp_id, "item_id": item_id},
            )
            row = result.fetchone()
            if row and row.remark:
                rows = json.loads(row.remark)
                for r in rows:
                    total += _safe_float(r.get("calculatedInterest", 0))
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(
                "L2 service: 解析跨项目利息JSON失败 item_id=%s: %s", item_id, e
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "L2 service: 跨项目利息查询失败 item_id=%s: %s", item_id, e
            )
        return total


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def _safe_float(val: Any) -> float:
    """安全转 float，None/非数值返回 0.0"""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0
