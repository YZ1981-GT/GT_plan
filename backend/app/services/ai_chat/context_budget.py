"""Context Budget Policy 与 Context Manifest（Task 14）

Feature: dsh-agent-panel-integration
Requirements:
  - 5.7：宿主/mention/OCR/review/RAG 共用预算，生成 included/trimmed/denied/unavailable
    manifest
  - 5.8：修复知识树 current user/project scope 传递
  - 5.9：manifest 展示与 citation jump 可操作且重新鉴权
Design: "Components and Interfaces → 4. ContextBudgetPolicy"

本模块实现两个核心抽象：

1. ``ContextBudgetPolicy`` — 统一的 token 预算分配策略，各部分按优先级竞争预算
2. ``ContextManifest`` — 记录每条上下文源的最终状态（included/trimmed/denied/unavailable）

## 预算分配优先级（从高到低）

1. system prompt（固定开销，不计入可变预算）
2. 宿主正文（doc_excerpt）— 40%
3. review prompt — 10%（复核模式时）
4. mentions — 25%
5. OCR / attachments — 10%
6. RAG knowledge hits — 15%

不启用复核模式时 review_prompt 的预算重新分配给 mentions 和 RAG。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "ContextBudgetPolicy",
    "ContextManifestEntry",
    "ContextManifest",
    "BudgetAllocation",
]


# ---------------------------------------------------------------------------
# 预算配置
# ---------------------------------------------------------------------------

#: 默认 token 总预算（可被环境变量 DOC_AI_TOKEN_BUDGET 覆盖）
DEFAULT_TOTAL_BUDGET = 8000

#: 各槽位预算比例（无 review 模式时自动重分配）
BUDGET_RATIOS = {
    "doc_excerpt": 0.40,
    "review_prompt": 0.10,
    "mentions": 0.25,
    "attachments": 0.10,
    "knowledge": 0.15,
}

#: review 模式关闭时的重分配比例
BUDGET_RATIOS_NO_REVIEW = {
    "doc_excerpt": 0.40,
    "review_prompt": 0.0,
    "mentions": 0.30,
    "attachments": 0.12,
    "knowledge": 0.18,
}


@dataclass(frozen=True)
class BudgetAllocation:
    """单次请求的各槽位 token 预算分配。"""

    total: int
    doc_excerpt: int
    review_prompt: int
    mentions: int
    attachments: int
    knowledge: int


# ---------------------------------------------------------------------------
# Manifest 条目
# ---------------------------------------------------------------------------


@dataclass
class ContextManifestEntry:
    """单条上下文源的状态记录。

    status 取值：
    - included: 完整纳入
    - trimmed: 因预算裁剪（保留 used_tokens 字段记录实际使用量）
    - denied: 授权拒绝
    - unavailable: 源数据不可用（加载失败、服务宕机等）
    """

    source_type: str  # doc_excerpt / mention / attachment / knowledge / review_prompt
    source_id: str  # 资源 ID 或标识
    label: str = ""
    status: str = "included"
    budget_tokens: int = 0  # 分配的预算
    used_tokens: int = 0  # 实际使用的 token 数
    reason: str = ""  # trimmed/denied/unavailable 的原因
    version: str = ""  # 数据版本/fingerprint（地址坐标 stale 检测用）
    stale: bool = False  # 是否为过期数据

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "status": self.status,
        }
        if self.label:
            d["label"] = self.label
        if self.used_tokens:
            d["used_tokens"] = self.used_tokens
        if self.reason:
            d["reason"] = self.reason
        if self.version:
            d["version"] = self.version
        if self.stale:
            d["stale"] = True
        return d


@dataclass
class ContextManifest:
    """完整的上下文 manifest（前端 ChatContextInspector 消费）。

    按 included → trimmed → denied → unavailable 分组展示。
    """

    entries: list[ContextManifestEntry] = field(default_factory=list)
    total_budget: int = 0
    total_used: int = 0
    manifest_version: str = "1"

    @property
    def included(self) -> list[ContextManifestEntry]:
        return [e for e in self.entries if e.status == "included"]

    @property
    def trimmed(self) -> list[ContextManifestEntry]:
        return [e for e in self.entries if e.status == "trimmed"]

    @property
    def denied(self) -> list[ContextManifestEntry]:
        return [e for e in self.entries if e.status == "denied"]

    @property
    def unavailable(self) -> list[ContextManifestEntry]:
        return [e for e in self.entries if e.status == "unavailable"]

    def as_dict(self) -> dict[str, Any]:
        """序列化为前端可消费的 JSON 结构。

        不输出空列表键（Phase A native_engine._manifest 的约定：
        空数组会被前端读成"没有任何裁剪"，那是假话）。
        """
        d: dict[str, Any] = {
            "manifest_version": self.manifest_version,
            "total_budget": self.total_budget,
            "total_used": self.total_used,
        }
        if self.included:
            d["included"] = [e.as_dict() for e in self.included]
        if self.trimmed:
            d["trimmed"] = [e.as_dict() for e in self.trimmed]
        if self.denied:
            d["denied"] = [e.as_dict() for e in self.denied]
        if self.unavailable:
            d["unavailable"] = [e.as_dict() for e in self.unavailable]
        return d

    def add(self, entry: ContextManifestEntry) -> None:
        self.entries.append(entry)
        if entry.status == "included" or entry.status == "trimmed":
            self.total_used += entry.used_tokens


# ---------------------------------------------------------------------------
# ContextBudgetPolicy
# ---------------------------------------------------------------------------


class ContextBudgetPolicy:
    """统一的 token 预算分配与裁剪策略。

    Usage::

        policy = ContextBudgetPolicy(total_budget=8000, review_mode=True)
        alloc = policy.allocate()
        # alloc.doc_excerpt = 3200, alloc.mentions = 2000, ...

        # 裁剪文本到分配预算
        text, used = policy.truncate_to_budget(long_text, alloc.doc_excerpt)

        # 记录到 manifest
        policy.manifest.add(ContextManifestEntry(
            source_type="doc_excerpt", source_id=host.resource_id,
            status="trimmed" if used < len(long_text)//3 else "included",
            budget_tokens=alloc.doc_excerpt, used_tokens=used,
        ))
    """

    def __init__(
        self,
        total_budget: int = DEFAULT_TOTAL_BUDGET,
        *,
        review_mode: bool = False,
    ) -> None:
        self._total = total_budget
        self._review_mode = review_mode
        self.manifest = ContextManifest(total_budget=total_budget)

    @property
    def total_budget(self) -> int:
        return self._total

    def allocate(self) -> BudgetAllocation:
        """计算各槽位的 token 预算。"""
        ratios = BUDGET_RATIOS if self._review_mode else BUDGET_RATIOS_NO_REVIEW
        return BudgetAllocation(
            total=self._total,
            doc_excerpt=int(self._total * ratios["doc_excerpt"]),
            review_prompt=int(self._total * ratios["review_prompt"]),
            mentions=int(self._total * ratios["mentions"]),
            attachments=int(self._total * ratios["attachments"]),
            knowledge=int(self._total * ratios["knowledge"]),
        )

    def truncate_to_budget(
        self, text: str, budget_tokens: int
    ) -> tuple[str, int]:
        """将文本裁剪到指定 token 预算内。

        返回 (truncated_text, estimated_token_count)。
        使用字符数 / 3 的粗估：中文约 1.5 char/token，英文约 4 char/token，
        取中间值 3 作为保守估计（宁可少用预算也不超限）。
        """
        if not text:
            return "", 0
        estimated = len(text) // 3
        if estimated <= budget_tokens:
            return text, estimated
        # 裁剪到 budget_tokens * 3 字符
        max_chars = budget_tokens * 3
        truncated = text[:max_chars]
        return truncated, budget_tokens

    def truncate_items_to_budget(
        self,
        items: list[tuple[str, str, int]],  # (id, content, priority)
        budget_tokens: int,
    ) -> tuple[list[tuple[str, str]], int]:
        """将多条内容按优先级裁剪到总预算内。

        Args:
            items: [(id, content, priority)] 高优先级数字小
            budget_tokens: 总 token 预算

        Returns:
            ([(id, truncated_content)], total_used_tokens)
        """
        sorted_items = sorted(items, key=lambda x: x[2])
        results: list[tuple[str, str]] = []
        remaining = budget_tokens

        for item_id, content, _priority in sorted_items:
            if remaining <= 0:
                break
            truncated, used = self.truncate_to_budget(content, remaining)
            if truncated:
                results.append((item_id, truncated))
                remaining -= used

        return results, budget_tokens - remaining
