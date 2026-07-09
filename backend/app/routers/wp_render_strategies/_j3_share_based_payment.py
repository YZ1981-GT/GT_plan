"""J3 股份支付 — 专属渲染策略.

J3 无独立科目（跨多科目：资本公积3002/管理费用6602/应付职工薪酬2211）。
费用确认走 EventBus → M4(权益结算)/J1(现金结算)/K8K9(管理费用)。

Spec: .kiro/specs/j3-share-based-payment/
Requirements: 1.1, 5.1
"""
from __future__ import annotations
import logging
import sqlalchemy as sa
from ._context import RenderContext

logger = logging.getLogger(__name__)

J3_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "j3-share-based-payment"},
    {"sheet_name": "股份支付实质性程序表 J3A", "component_type": "j3-share-based-payment"},
    {"sheet_name": "股份支付情况表J3-1", "component_type": "j3-share-based-payment"},
    {"sheet_name": "股份支付检查表J3-2", "component_type": "j3-share-based-payment"},
]


async def render(ctx: RenderContext) -> dict | None:
    """渲染 J3 股份支付底稿数据.

    J3 特殊：无单一TB科目回写，仅读取 checklist_responses 中的方案数据。
    """
    responses_snapshot: dict = {}
    plans: list = []

    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, content, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 2000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "J3-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "content": row.content or "",
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("J3 render checklist read failed: %s", e)

    # 解析方案数据（JSON打包存储于 J3-plans-data）
    plans_raw = responses_snapshot.get("J3-plans-data", {})
    if plans_raw and plans_raw.get("content"):
        import json
        try:
            plans = json.loads(plans_raw["content"])
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "component_type": "j3-share-based-payment",
        "cross_account": True,
        "no_tb_writeback": True,
        "account_codes": ["3002", "6602", "2211"],
        "plans": plans,
        "responses": responses_snapshot,
        "sheets": J3_SHEETS,
        "bs_params": _extract_bs_params(responses_snapshot),
    }


def _extract_bs_params(responses: dict) -> dict:
    """从 checklist_responses 提取 BS参数."""
    import json
    bs_raw = responses.get("J3-bs-params", {})
    if bs_raw and bs_raw.get("content"):
        try:
            return json.loads(bs_raw["content"])
        except (json.JSONDecodeError, TypeError):
            pass
    return {"S": 0, "K": 0, "T": 0, "r": 0, "sigma": 0}
