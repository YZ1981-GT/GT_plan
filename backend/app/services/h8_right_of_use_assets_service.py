"""H8 使用权资产 — 业务逻辑服务

纯函数计算引擎（无DB依赖，可单独测试）+ 带DB的联动校验逻辑。

提供功能：
- CAS21初始计量：H8 = H9初始 + 直接费用 - 激励（CAS21第16条）
- 折旧期确定：min(租赁期, 使用寿命)（CAS21第21条）
- 终止损益：租赁负债余额 - 使用权资产净值
- 简化处理判断：短期租赁(≤12月) / 低价值租赁(≤40000元)（CAS21第32条）
- H8-H9联动校验：初始计量一致性（±1元容差）

科目1901使用权资产（借方/资产类）+ 累计折旧（贷方/备抵类）

Service只flush不commit（由调用方控制事务）。

Requirements: 10.1-10.4, 11.1-11.4
"""

from __future__ import annotations

import json
import logging
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# checklist_responses item_id 常量
_H8_DETAIL_ITEM_ID = "H8-2-detail-rows"
_H9_INITIAL_ITEM_ID = "H9-1-initial-recognition"

# CAS21常量
SHORT_TERM_THRESHOLD_MONTHS = 12
LOW_VALUE_THRESHOLD_DEFAULT = 40000.0
LINKAGE_TOLERANCE = 1.0  # H8-H9联动容差（±1元）


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：CAS21计量引擎
# ═══════════════════════════════════════════════════════════════════════════════


def calc_initial_measurement(
    lease_liability: float, direct_cost: float, incentive: float
) -> float:
    """CAS21初始计量：H8 = H9初始 + 直接费用 - 激励

    CAS21第16条：使用权资产按成本进行初始计量。
    成本 = 租赁负债初始计量金额 + 初始直接费用 - 租赁激励

    Args:
        lease_liability: 租赁负债初始计量金额（来自H9）
        direct_cost: 初始直接费用
        incentive: 租赁激励（出租方给承租方的优惠）

    Returns:
        使用权资产初始计量金额

    Requirements: 10.1
    """
    return lease_liability + direct_cost - incentive


def calc_depreciation_period(lease_term: int, useful_life: int) -> int:
    """折旧期 = min(租赁期, 使用寿命)

    CAS21第21条：承租人应对使用权资产计提折旧。
    折旧期间为：租赁期与使用权资产剩余使用寿命两者孰短。
    若能合理确定租赁期届满时取得所有权，则按使用寿命折旧。

    Args:
        lease_term: 租赁期（月数）
        useful_life: 资产使用寿命（月数）

    Returns:
        折旧期间（月数）

    Requirements: 10.2
    """
    return min(lease_term, useful_life)


def calc_termination_gain_loss(
    liability_balance: float, rou_net_value: float
) -> float:
    """终止损益 = 租赁负债余额 - 使用权资产净值

    租赁提前终止或到期终止时：
    - 正数→收益（负债>资产，终止释放差额为收益）
    - 负数→损失（资产>负债，终止确认差额为损失）

    Args:
        liability_balance: 终止时租赁负债余额
        rou_net_value: 终止时使用权资产净值（原值-累计折旧-减值）

    Returns:
        终止损益金额

    Requirements: 10.3
    """
    return liability_balance - rou_net_value


def calc_remeasurement(old_rou: float, adjustment: float) -> float:
    """重新计量后使用权资产 = 原使用权资产 + 调整额

    CAS21第28条：因租赁变更导致租赁负债重新计量时，
    应相应调整使用权资产的账面价值。

    Args:
        old_rou: 重新计量前使用权资产账面价值
        adjustment: 调整额（正数增加，负数减少）

    Returns:
        重新计量后使用权资产账面价值

    Requirements: 10.4
    """
    return old_rou + adjustment


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：简化处理判断（CAS21第32条）
# ═══════════════════════════════════════════════════════════════════════════════


def is_short_term_lease(term_months: int) -> bool:
    """短期租赁判断：租赁期 ≤ 12个月

    CAS21第32条：短期租赁是指自租赁期开始日起，
    租赁期不超过12个月的租赁。包含购买选择权的租赁不属于短期租赁。

    Args:
        term_months: 租赁期（月数）

    Returns:
        True if 满足短期租赁条件

    Requirements: 8.2
    """
    return term_months <= SHORT_TERM_THRESHOLD_MONTHS


def is_low_value_lease(
    new_asset_value: float, threshold: float = LOW_VALUE_THRESHOLD_DEFAULT
) -> bool:
    """低价值资产租赁判断：全新价值 ≤ 阈值（默认40000元）

    CAS21第32条：低价值资产租赁是指单项租赁资产为全新资产时
    价值较低的租赁。判断标准基于全新资产价值，不受已折旧影响。

    Args:
        new_asset_value: 租赁资产全新时的价值
        threshold: 低价值阈值（默认40000元，可配置）

    Returns:
        True if 满足低价值租赁条件

    Requirements: 8.2
    """
    return new_asset_value <= threshold


def check_simplified_eligibility(
    term_months: int, new_asset_value: float, threshold: float = LOW_VALUE_THRESHOLD_DEFAULT
) -> dict:
    """综合判断是否可简化处理

    Returns:
        {
            "is_short_term": bool,
            "is_low_value": bool,
            "eligible": bool (满足任一即可简化),
            "reason": str
        }
    """
    short = is_short_term_lease(term_months)
    low = is_low_value_lease(new_asset_value, threshold)
    eligible = short or low

    if short and low:
        reason = "短期+低价值租赁"
    elif short:
        reason = "短期租赁(≤12月)"
    elif low:
        reason = f"低价值租赁(≤{threshold}元)"
    else:
        reason = "不符合简化条件，应确认使用权资产"

    return {
        "is_short_term": short,
        "is_low_value": low,
        "eligible": eligible,
        "reason": reason,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DB查询：H8-H9联动校验
# ═══════════════════════════════════════════════════════════════════════════════


class H8RightOfUseAssetsService:
    """H8使用权资产业务逻辑服务.

    核心功能：
    - CAS21初始计量验证
    - H8-H9联动校验
    - 简化处理条件检查

    Service只flush不commit（由调用方控制事务）。
    """

    @staticmethod
    def calc_initial_measurement(
        lease_liability: float, direct_cost: float, incentive: float
    ) -> float:
        """H8 = H9初始 + 直接费用 - 激励 (CAS21第16条)"""
        return calc_initial_measurement(lease_liability, direct_cost, incentive)

    @staticmethod
    def calc_depreciation_period(lease_term: int, useful_life: int) -> int:
        """折旧期 = min(租赁期, 使用寿命) (CAS21第21条)"""
        return calc_depreciation_period(lease_term, useful_life)

    @staticmethod
    def calc_termination_gain_loss(
        liability_balance: float, rou_net_value: float
    ) -> float:
        """终止损益 = 租赁负债余额 - 使用权资产净值"""
        return calc_termination_gain_loss(liability_balance, rou_net_value)

    @staticmethod
    def is_short_term_lease(term_months: int) -> bool:
        """短期租赁: ≤12个月 (CAS21第32条)"""
        return is_short_term_lease(term_months)

    @staticmethod
    def is_low_value_lease(
        new_asset_value: float, threshold: float = LOW_VALUE_THRESHOLD_DEFAULT
    ) -> bool:
        """低价值: 全新价值≤40000元 (CAS21第32条)"""
        return is_low_value_lease(new_asset_value, threshold)

    async def validate_h9_linkage(
        self, db: AsyncSession, project_id: str, wp_id: str
    ) -> dict:
        """H8-H9联动校验: H8初始-直接+激励 ≈ H9初始确认 (±1元容差)

        从 checklist_responses 读取 H8-2 明细行和 H9 初始确认金额，
        验证 CAS21 配对关系的一致性。

        校验逻辑：
        对每笔租赁合同：
            H8入账值 - 直接费用 + 激励 ≈ H9初始确认
            即：H8初始中的租赁负债部分 ≈ H9初始确认金额

        Args:
            db: 数据库会话
            project_id: 项目ID
            wp_id: H8底稿的wp_id

        Returns:
            {
                "is_consistent": bool,
                "total_h8_liability_part": float,
                "total_h9_initial": float,
                "difference": float,
                "details": [...per contract],
                "message": str
            }

        Requirements: 11.1-11.4
        """
        # ─── 加载H8明细行 ────────────────────────────────────────────────
        h8_details = await self._load_h8_details(db, wp_id)

        # ─── 加载H9初始确认 ──────────────────────────────────────────────
        h9_initial = await self._load_h9_initial(db, project_id)

        # ─── 逐笔比对 ────────────────────────────────────────────────────
        total_h8_liability_part = 0.0
        total_h9_initial = 0.0
        details: list[dict] = []

        for row in h8_details:
            contract_no = row.get("contractNo", "")
            h8_entry_value = _safe_float(row.get("entryValue", 0))
            direct_cost = _safe_float(row.get("directCost", 0))
            incentive_val = _safe_float(row.get("incentive", 0))

            # H8中的租赁负债部分 = 入账值 - 直接费用 + 激励
            h8_liability_part = h8_entry_value - direct_cost + incentive_val
            total_h8_liability_part += h8_liability_part

            # 查找H9对应合同
            h9_amount = _safe_float(h9_initial.get(contract_no, 0))
            total_h9_initial += h9_amount

            diff = h8_liability_part - h9_amount
            details.append({
                "contract_no": contract_no,
                "h8_liability_part": round(h8_liability_part, 2),
                "h9_initial": round(h9_amount, 2),
                "difference": round(diff, 2),
                "is_consistent": abs(diff) <= LINKAGE_TOLERANCE,
            })

        # ─── 汇总 ────────────────────────────────────────────────────────
        total_diff = total_h8_liability_part - total_h9_initial
        is_consistent = abs(total_diff) <= LINKAGE_TOLERANCE

        if is_consistent:
            message = "H8与H9联动一致"
        else:
            message = f"H8与H9不一致，差额：{total_diff:.2f}元，请检查"

        return {
            "is_consistent": is_consistent,
            "total_h8_liability_part": round(total_h8_liability_part, 2),
            "total_h9_initial": round(total_h9_initial, 2),
            "difference": round(total_diff, 2),
            "details": details,
            "message": message,
        }

    async def validate_simplified_processing(
        self, db: AsyncSession, wp_id: str
    ) -> dict:
        """简化处理验证: 标记为简化处理的租赁是否真正满足短期/低价值条件

        从 H8-13 简化处理检查表数据中验证每笔租赁的简化资格。

        Args:
            db: 数据库会话
            wp_id: H8底稿的wp_id

        Returns:
            {
                "total_count": int,
                "eligible_count": int,
                "ineligible_count": int,
                "ineligible_items": [...],
                "total_annual_rent": float,
                "message": str
            }
        """
        simplified_rows = await self._load_simplified_rows(db, wp_id)

        total_count = len(simplified_rows)
        eligible_count = 0
        ineligible_count = 0
        ineligible_items: list[dict] = []
        total_annual_rent = 0.0

        for row in simplified_rows:
            contract_no = row.get("contractNo", "")
            term_months = int(_safe_float(
                row.get("leaseTermMonths", row.get("termMonths", 0))
            ))
            new_value = _safe_float(row.get("newAssetValue", 0))
            annual_rent = _safe_float(
                row.get("annualRental", row.get("annualRent", 0))
            )
            if annual_rent <= 0:
                monthly = _safe_float(row.get("monthlyRent", 0))
                if monthly > 0:
                    annual_rent = monthly * 12

            total_annual_rent += annual_rent

            result = check_simplified_eligibility(term_months, new_value)
            if result["eligible"]:
                eligible_count += 1
            else:
                ineligible_count += 1
                ineligible_items.append({
                    "contract_no": contract_no,
                    "term_months": term_months,
                    "new_asset_value": new_value,
                    "reason": result["reason"],
                })

        if ineligible_count == 0:
            message = f"全部{total_count}笔租赁均符合简化处理条件"
        else:
            message = (
                f"{ineligible_count}笔租赁不符合简化条件，"
                f"应转为确认使用权资产"
            )

        return {
            "total_count": total_count,
            "eligible_count": eligible_count,
            "ineligible_count": ineligible_count,
            "ineligible_items": ineligible_items,
            "total_annual_rent": round(total_annual_rent, 2),
            "message": message,
        }

    # ─── 内部辅助 ────────────────────────────────────────────────────────

    async def _load_h8_details(self, db: AsyncSession, wp_id: str) -> list[dict]:
        """从 checklist_responses 加载H8-2明细行"""
        try:
            result = await db.execute(
                sa.text(
                    "SELECT remark FROM checklist_responses "
                    "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
                ),
                {"wp_id": wp_id, "item_id": _H8_DETAIL_ITEM_ID},
            )
            row = result.fetchone()
            if row and row.remark:
                return json.loads(row.remark)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("H8 service: 解析明细行JSON失败 wp_id=%s: %s", wp_id, e)
        except Exception as e:  # noqa: BLE001
            logger.warning("H8 service: 加载明细行失败 wp_id=%s: %s", wp_id, e)
        return []

    async def _load_h9_initial(
        self, db: AsyncSession, project_id: str
    ) -> dict[str, float]:
        """从同project下的H9底稿加载初始确认金额（按合同号索引）"""
        result_map: dict[str, float] = {}
        try:
            result = await db.execute(
                sa.text(
                    "SELECT cr.remark FROM checklist_responses cr "
                    "JOIN working_papers wp ON wp.id = cr.wp_id "
                    "WHERE wp.project_id = :project_id "
                    "AND cr.item_id = :item_id "
                    "LIMIT 1"
                ),
                {"project_id": project_id, "item_id": _H9_INITIAL_ITEM_ID},
            )
            row = result.fetchone()
            if row and row.remark:
                rows = json.loads(row.remark)
                for r in rows:
                    contract_no = r.get("contractNo", "")
                    amount = _safe_float(r.get("initialAmount", 0))
                    if contract_no:
                        result_map[contract_no] = amount
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(
                "H8 service: 解析H9初始确认JSON失败 project=%s: %s", project_id, e
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "H8 service: H9初始确认查询失败 project=%s: %s", project_id, e
            )
        return result_map

    async def _load_simplified_rows(
        self, db: AsyncSession, wp_id: str
    ) -> list[dict]:
        """从 checklist_responses 加载H8-13简化处理检查表行"""
        # 主 key 与前端/导入导出一致；兼容旧 item_id
        for item_id in ("H8-13-rows", "H8-13-simplified-rows"):
            try:
                result = await db.execute(
                    sa.text(
                        "SELECT remark FROM checklist_responses "
                        "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
                    ),
                    {"wp_id": wp_id, "item_id": item_id},
                )
                row = result.fetchone()
                if row and row.remark:
                    return json.loads(row.remark)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(
                    "H8 service: 解析简化处理JSON失败 wp_id=%s item=%s: %s",
                    wp_id, item_id, e,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "H8 service: 加载简化处理失败 wp_id=%s item=%s: %s",
                    wp_id, item_id, e,
                )
        return []


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
