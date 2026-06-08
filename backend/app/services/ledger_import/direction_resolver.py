"""科目借贷方向判定 — 单一权威源（ledger-sign-convention-unify 需求 2、3）。

入库层 converter、trial_balance 生成层、迁移脚本三处共用本模块，杜绝各处各判一套。

判定优先级（需求 3.5）：
1. 备抵/反向科目特例（名称正则）——编码大类与正常方向相反，只能靠名称识别：
   - 资产备抵（累计折旧/摊销、坏账/减值/跌价准备、折耗）→ credit
   - 权益备抵（库存股）→ debit
2. 科目类别（复用 account_chart_service._infer_category，名称关键词优先 + 编码兜底）：
   - asset / expense → debit
   - liability / equity / revenue → credit
3. 名称为空 → 仅编码兜底，标低置信度。

direction ∈ {"debit", "credit"}；source 对齐 DirectionSource 枚举。
纯函数，不访问 DB。
"""

from __future__ import annotations

import re

from app.models.audit_platform_models import AccountCategory
from app.services.account_chart_service import _infer_category

# ---------------------------------------------------------------------------
# 备抵/反向科目正则（与前端 TrialBalance.vue getDirection 对齐）
# ---------------------------------------------------------------------------

# 资产备抵：挂资产类编码（1xxx）但正常余额在贷方
_CONTRA_CREDIT_PATTERN = re.compile(
    r"累计折旧|累计摊销|坏账准备|减值准备|跌价准备|折耗|减值损失准备"
)

# 权益备抵：挂权益类编码但正常余额在借方（库存股）
_CONTRA_DEBIT_PATTERN = re.compile(r"库存股")

# 借方正常的类别
_DEBIT_CATEGORIES = {AccountCategory.asset, AccountCategory.expense}
# 贷方正常的类别
_CREDIT_CATEGORIES = {
    AccountCategory.liability,
    AccountCategory.equity,
    AccountCategory.revenue,
}


def resolve_account_direction(code: str, name: str = "") -> tuple[str, str]:
    """判定科目正常借贷方向。

    Args:
        code: 科目编码
        name: 科目名称（用于备抵识别与类别名称关键词匹配）

    Returns:
        (direction, source)
        - direction ∈ {"debit", "credit"}
        - source ∈ DirectionSource 枚举值
    """
    name = (name or "").strip()
    code = (code or "").strip()

    # 1. 备抵/反向科目特例（名称优先级最高）
    if name:
        if _CONTRA_CREDIT_PATTERN.search(name):
            return "credit", "contra_account"
        if _CONTRA_DEBIT_PATTERN.search(name):
            return "debit", "contra_account"

    # 2. 按类别推断（_infer_category 已名称优先 + 编码兜底）
    category = _infer_category(code, name)

    if name:
        # 名称非空：判定来源标为类别推断（_infer_category 内部已优先用名称关键词）
        source = "account_category_inferred"
    else:
        # 名称为空：仅靠编码兜底，低置信度
        source = "account_category_inferred_low_confidence"

    if category in _CREDIT_CATEGORIES:
        return "credit", source
    # asset / expense / 其余兜底为借方
    return "debit", source


__all__ = ["resolve_account_direction"]
