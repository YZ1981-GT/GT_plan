"""公式推送运行结果（纯数据，不引用 ORM 对象：dry_run 回滚保存点后仍可安全读取）。

spec: chain-closure-phase2-formula-push-engine · 任务 10（由 engine.py 拆出，行数门禁 ≤800）
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

#: 判定动作之外的两种结果
SKIPPED = "skipped"
CONFLICT = "conflict"
FALLBACK_TO_TOTAL = "fallback_to_total"  # spec: formula-push-note-row-matching · 需求 1.1


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _jsonable(value: Any) -> Any:
    """JSONB 可存的值（Decimal → float；非有限数 → None）。"""
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


@dataclass
class PushItem:
    """运行明细里的一项（一个目标的判定结果，或一个跳过原因）。"""

    rule_id: str
    stage: str
    domain: str
    addr_id: str | None
    action: str
    state: str | None = None
    formula: Any = None
    current: Any = None
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {k: _jsonable(v) for k, v in asdict(self).items()}


@dataclass
class RunResult:
    """一次推送的结果（纯数据，不引用 ORM 对象：dry_run 回滚保存点后仍可安全读取）。"""

    project_id: UUID
    year: int
    trigger: str
    dry_run: bool = False
    run_id: UUID | None = None
    status: str = "succeeded"
    items: list[PushItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    workpapers: list[dict[str, Any]] = field(default_factory=list)
    #: 实际写入的底稿条目 id（SSE 给前端提示条用）
    changed_items: list[str] = field(default_factory=list)
    #: 实际写入的附注章节
    note_sections: list[str] = field(default_factory=list)
    #: 有写入的底稿
    wp_ids: list[str] = field(default_factory=list)
    forced: list[str] = field(default_factory=list)

    def count(self, *actions: str) -> int:
        return sum(1 for i in self.items if i.action in actions)

    @property
    def written_count(self) -> int:
        return self.count("write")

    @property
    def unchanged_count(self) -> int:
        return self.count("unchanged")

    @property
    def kept_count(self) -> int:
        return self.count("keep_locked", "keep_manual", "keep_pending")

    @property
    def skipped_count(self) -> int:
        return self.count(SKIPPED, CONFLICT)

    @property
    def stages(self) -> list[str]:
        """有实际写入的阶段（前端据此判断：只有源值阶段有写入才弹提示条）。"""
        return sorted({i.stage for i in self.items if i.action == "write"})

    def add_warning(self, text: str) -> None:
        if text and text not in self.warnings:
            self.warnings.append(text)

    def summary(self) -> dict[str, Any]:
        """接口 / SSE 用的摘要（不含逐项明细）。"""
        return {
            "project_id": str(self.project_id),
            "year": self.year,
            "run_id": str(self.run_id) if self.run_id else None,
            "trigger": self.trigger,
            "dry_run": self.dry_run,
            "status": self.status,
            "written_count": self.written_count,
            "unchanged_count": self.unchanged_count,
            "kept_count": self.kept_count,
            "skipped_count": self.skipped_count,
            "stages": self.stages,
            "wp_ids": list(self.wp_ids),
            "changed_items": list(self.changed_items),
            "note_sections": list(self.note_sections),
            "warnings": list(self.warnings),
        }

    def detail(self) -> dict[str, Any]:
        """运行记录 ``formula_push_run.detail``。"""
        return {
            "wp": list(self.workpapers),
            "items": [i.as_dict() for i in self.items],
            "warnings": list(self.warnings),
            "changed_items": list(self.changed_items),
            "note_sections": list(self.note_sections),
            "stages": self.stages,
            "forced": list(self.forced),
        }
