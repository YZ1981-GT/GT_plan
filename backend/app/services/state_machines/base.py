"""状态机基类 — V3 收官增强 Req 10

定义 Transition / StateMachine 基础结构，供 5 类业务实例状态机复用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Transition:
    """单条状态转移定义。"""

    from_: str
    action: str
    to: str
    role_required: set[str] = field(default_factory=set)
    guards: list[str] = field(default_factory=list)


@dataclass
class StateMachine:
    """业务实例状态机定义。"""

    name: str
    states: list[str]
    transitions: list[Transition]
    action_labels_zh: dict[str, str] = field(default_factory=dict)
    status_labels_zh: dict[str, str] = field(default_factory=dict)

    @property
    def all_actions(self) -> list[str]:
        """返回所有可能的 action（去重保序）。"""
        seen: set[str] = set()
        actions: list[str] = []
        for t in self.transitions:
            if t.action not in seen:
                seen.add(t.action)
                actions.append(t.action)
        return actions

    def get_transitions_from(self, status: str) -> list[Transition]:
        """获取从指定状态出发的所有转移。"""
        return [t for t in self.transitions if t.from_ == status]

    def to_mermaid_nodes(self) -> list[dict[str, Any]]:
        """将状态机转换为 mermaid stateDiagram 节点列表。"""
        nodes: list[dict[str, Any]] = []
        for t in self.transitions:
            nodes.append({
                "from": t.from_,
                "to": t.to,
                "action": t.action,
                "action_zh": self.action_labels_zh.get(t.action, t.action),
            })
        return nodes
