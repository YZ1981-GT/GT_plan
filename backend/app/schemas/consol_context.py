"""合并计算链路共享的不可变上下文。

``ConsolContext`` 是合并树、试算表、报表、附注和事件之间传递的运行时
身份协议。它只保存已解析的上下文值，不负责从数据库解析项目、树或模板；
调用方必须在切换目标项目后重新解析目标专属字段。
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ConsolContext(BaseModel):
    """合并计算的 typed、不可变上下文。

    ``node_key`` 表示单节点计算；``node_keys`` 表示一个明确的节点范围。
    project/year 是所有下游结果的硬边界，版本字段是由各自解析器产生的不透明
    标识，不能在这里凭空生成业务版本号。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    context_id: UUID = Field(default_factory=uuid4)
    run_id: UUID | None = None
    project_id: UUID
    year: int
    node_key: str | None = None
    node_keys: tuple[str, ...] = ()
    template_type: str | None = None
    report_scope: str | None = None
    period_end: date | None = None
    tree_fingerprint: str | None = None
    source_version: str | None = None
    formula_version: str | None = None
    template_version: str | None = None
    is_legacy: bool = False

    @field_validator("year")
    @classmethod
    def _validate_year(cls, value: int) -> int:
        if value < 1900 or value > 2200:
            raise ValueError("合并上下文年度必须在 1900 到 2200 之间")
        return value

    @field_validator(
        "node_key",
        "template_type",
        "report_scope",
        "tree_fingerprint",
        "source_version",
        "formula_version",
        "template_version",
    )
    @classmethod
    def _reject_blank_strings(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("合并上下文字段不能是空白字符串")
        return value

    @field_validator("node_keys")
    @classmethod
    def _validate_node_keys(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value):
            raise ValueError("合并上下文节点范围不能包含空白 node_key")
        if len(set(value)) != len(value):
            raise ValueError("合并上下文节点范围不能包含重复 node_key")
        return value

    @model_validator(mode="after")
    def _validate_node_scope(self) -> "ConsolContext":
        if self.node_key is not None and self.node_keys and self.node_key not in self.node_keys:
            raise ValueError("node_key 必须属于 node_keys 声明的节点范围")
        return self

    @classmethod
    def legacy(
        cls,
        project_id: UUID,
        year: int,
        *,
        node_key: str | None = None,
        template_type: str | None = None,
        report_scope: str | None = None,
    ) -> "ConsolContext":
        """为旧事件或旧入口构造上下文，不伪造任何版本标识。"""
        return cls(
            project_id=project_id,
            year=year,
            node_key=node_key,
            template_type=template_type,
            report_scope=report_scope,
            is_legacy=True,
        )

    def for_target(self, project_id: UUID, *, year: int | None = None) -> "ConsolContext":
        """派生目标项目的未解析上下文。

        运行 ID 保持不变，表示仍属于同一次编排；节点、模板、树和各类版本
        全部清空，要求目标项目的调用方重新解析后再建立目标上下文。
        """
        return type(self).model_validate({
            **self.model_dump(mode="python"),
            "project_id": project_id,
            "year": self.year if year is None else year,
            "node_key": None,
            "node_keys": (),
            "template_type": None,
            "report_scope": None,
            "period_end": None,
            "tree_fingerprint": None,
            "source_version": None,
            "formula_version": None,
            "template_version": None,
            "is_legacy": self.is_legacy,
        })

    def with_resolution(self, **updates: Any) -> "ConsolContext":
        """在目标项目重新解析后，生成带解析结果的不可变上下文。"""
        allowed = {
            "node_key",
            "node_keys",
            "template_type",
            "report_scope",
            "period_end",
            "tree_fingerprint",
            "source_version",
            "formula_version",
            "template_version",
            "is_legacy",
        }
        unknown = set(updates) - allowed
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"不允许通过 with_resolution 修改上下文身份字段：{names}")
        return type(self).model_validate({
            **self.model_dump(mode="python"),
            **updates,
        })

    def to_dict(self) -> dict[str, Any]:
        """返回可直接放入 JSON/EventPayload 的字典。"""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ConsolContext":
        """从 JSON 兼容字典恢复上下文。"""
        return cls.model_validate(value)

    def identity_dict(self) -> dict[str, Any]:
        """返回用于事件去重的稳定身份字段，不包含随机 context_id/run_id。"""
        return {
            "project_id": str(self.project_id),
            "year": self.year,
            "node_key": self.node_key,
            "node_keys": list(self.node_keys),
            "template_type": self.template_type,
            "report_scope": self.report_scope,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "tree_fingerprint": self.tree_fingerprint,
            "source_version": self.source_version,
            "formula_version": self.formula_version,
            "template_version": self.template_version,
        }
