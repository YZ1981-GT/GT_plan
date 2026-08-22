"""MCP Budget Tracker（dsh-agent-panel-integration Task 25 / Req 11.8）

Per-run call 数量与字节预算管控。超预算后明确失败且无后续工具调用。

配置单一真源：
  - AI_MCP_MAX_CALLS_PER_RUN（默认 50）
  - AI_MCP_MAX_BYTES_PER_CALL（默认 65536）

Property 29：子 Agent 继承相同配额约束（budget 绑定 run 而非 token）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from app.core.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "McpBudget",
    "McpBudgetTracker",
    "McpBudgetExceeded",
]


class McpBudgetExceeded(Exception):
    """MCP 配额超限（tool_budget_exceeded）。"""

    def __init__(self, resource: str, current: int, limit: int) -> None:
        self.resource = resource
        self.current = current
        self.limit = limit
        super().__init__(
            f"MCP {resource} 配额超限：当前 {current}，上限 {limit}"
        )


@dataclass
class McpBudget:
    """单个 run 的 MCP 使用统计。"""

    run_id: UUID
    max_calls: int
    max_bytes_per_call: int
    calls_used: int = 0
    total_bytes: int = 0

    @property
    def calls_remaining(self) -> int:
        return max(0, self.max_calls - self.calls_used)

    @property
    def is_exhausted(self) -> bool:
        return self.calls_used >= self.max_calls

    def to_dict(self) -> dict:
        return {
            "run_id": str(self.run_id),
            "max_calls": self.max_calls,
            "max_bytes_per_call": self.max_bytes_per_call,
            "calls_used": self.calls_used,
            "calls_remaining": self.calls_remaining,
            "total_bytes": self.total_bytes,
        }


class McpBudgetTracker:
    """Per-run MCP 配额追踪器。

    线程安全说明：本进程内 run→budget 映射，ChatRunCoordinator 保证
    一个 run 只有一个 executor，因此同一 run 的 budget 不会并发修改。
    """

    def __init__(self) -> None:
        self._budgets: dict[UUID, McpBudget] = {}

    def get_or_create(self, run_id: UUID) -> McpBudget:
        """获取或创建 run 的 budget（首次调用时按配置初始化）。"""
        if run_id not in self._budgets:
            self._budgets[run_id] = McpBudget(
                run_id=run_id,
                max_calls=settings.AI_MCP_MAX_CALLS_PER_RUN,
                max_bytes_per_call=settings.AI_MCP_MAX_BYTES_PER_CALL,
            )
        return self._budgets[run_id]

    def check_and_consume(
        self,
        run_id: UUID,
        *,
        response_bytes: int = 0,
    ) -> McpBudget:
        """消费一次调用配额。

        🔴 超限后明确抛出 McpBudgetExceeded，MCP server 收到后必须停止后续调用。

        Args:
            run_id: 所属 run
            response_bytes: 本次调用的响应字节数

        Returns:
            更新后的 budget

        Raises:
            McpBudgetExceeded: calls 超限或单次 bytes 超限
        """
        budget = self.get_or_create(run_id)

        # 调用次数检查
        if budget.calls_used >= budget.max_calls:
            raise McpBudgetExceeded("calls", budget.calls_used, budget.max_calls)

        # 单次字节检查
        if response_bytes > budget.max_bytes_per_call:
            raise McpBudgetExceeded(
                "bytes_per_call", response_bytes, budget.max_bytes_per_call
            )

        # 消费
        budget.calls_used += 1
        budget.total_bytes += response_bytes
        return budget

    def pre_check(self, run_id: UUID) -> None:
        """调用前预检（不消费配额，只检查是否还有余量）。

        在真正执行工具前调用，避免发起注定会被拒绝的请求。
        """
        budget = self.get_or_create(run_id)
        if budget.is_exhausted:
            raise McpBudgetExceeded("calls", budget.calls_used, budget.max_calls)

    def release(self, run_id: UUID) -> None:
        """run 结束后释放 budget 跟踪。"""
        self._budgets.pop(run_id, None)

    def get_status(self, run_id: UUID) -> McpBudget | None:
        """查询 run 的当前配额状态。"""
        return self._budgets.get(run_id)
