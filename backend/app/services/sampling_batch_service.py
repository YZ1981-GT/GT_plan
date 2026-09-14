"""抽样批次状态机（voucher-sampling-hardening Task 7.2）

抽样批次生命周期：draft → confirmed → filled → undone。
- filled / undone 为终态，不可非法回退。
- 幂等键去重与撤销唯一性由 DB 约束（V123 部分唯一索引）强制；本模块提供状态转移
  合法性判定（纯函数，可离线测），供服务层在写入前校验。

Validates: Requirements 5.1, 5.2, 5.3
Properties: Property 10
"""

from __future__ import annotations

# 合法状态集合
SAMPLING_BATCH_STATUSES = ("draft", "confirmed", "filled", "undone")

# 合法状态转移图：from → 可达 to 集合。filled/undone 为终态（filled 仅可转 undone 撤销）。
SAMPLING_BATCH_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"confirmed", "filled"},
    "confirmed": {"filled"},
    "filled": {"undone"},
    "undone": set(),  # 终态，不可再转
}


def is_valid_transition(from_status: str, to_status: str) -> bool:
    """判定状态转移是否合法（未知状态一律非法）。"""
    if from_status not in SAMPLING_BATCH_TRANSITIONS:
        return False
    return to_status in SAMPLING_BATCH_TRANSITIONS[from_status]


def assert_valid_transition(from_status: str, to_status: str) -> None:
    """非法转移抛 ValueError（服务层写入前调用）。"""
    if not is_valid_transition(from_status, to_status):
        raise ValueError(
            f"非法的抽样批次状态转移：{from_status} → {to_status}"
        )
