"""一致性门控 — 5 项基础检查 mixin

1. 试算平衡（资产合计 = 负债合计 + 权益合计）
2. 报表平衡（BS 资产合计 = 负债+权益合计）
3. 利润表勾稽（营业收入 - 营业成本 - 费用 + 营业外 = 净利润）
4. 附注完整性（有数据的报表行次对应附注章节已生成）
5. 数据新鲜度（无 stale 标记）
"""
from __future__ import annotations

# 委托到 _impl 中的原始实现，避免代码重复
from app.services.consistency_gate._impl import ConsistencyGate as _Impl


class BaseChecksMixin:
    """5 项基础检查"""

    check_tb_balance = _Impl.check_tb_balance
    check_bs_balance = _Impl.check_bs_balance
    check_is_reconciliation = _Impl.check_is_reconciliation
    check_notes_completeness = _Impl.check_notes_completeness
    check_data_freshness = _Impl.check_data_freshness
