"""formula_runtime.contracts — 核心 contracts 定义。

定义公式运行时的规范目标身份、变更载体、执行计划/结果
以及统一领域变更协议 DomainMutationAdapter。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal, Mapping, Protocol, runtime_checkable
from uuid import UUID

JSONValue = dict | list | str | int | float | bool | None


@dataclass(frozen=True)
class CanonicalFormulaTarget:
    """公式引用/目标的规范身份。"""

    domain: Literal["workpaper", "adjudication", "report", "note"]
    project_id: UUID
    year: int
    addr_id: str
    locator: Mapping[str, str]  # 领域专属定位信息
    wp_id: UUID | None = None


@dataclass(frozen=True)
class FormulaMutation:
    """单个领域变更。"""

    target: CanonicalFormulaTarget
    before_value: JSONValue
    after_value: JSONValue
    expected_version: str | None = None
    source_formula_id: UUID | None = None


@dataclass
class AppliedMutation:
    """成功应用后的 mutation 结果。"""

    target: CanonicalFormulaTarget
    applied_version: str
    applied_at: str  # ISO datetime


@dataclass
class RestoredMutation:
    """成功恢复后的 mutation 结果。"""

    target: CanonicalFormulaTarget
    restored_version: str
    conflict: bool = False
    conflict_detail: str | None = None


@dataclass
class ExecutionPlan:
    """公式执行计划。"""

    run_id: UUID
    project_id: UUID
    year: int
    scopes: list[str]
    transaction_mode: Literal["all_or_nothing", "partial_success"] = "all_or_nothing"
    mutations: list[FormulaMutation] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    hints: list[dict] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """公式执行结果。"""

    run_id: UUID
    status: Literal["success", "partial_success", "failed", "no_effect", "idempotent_hit"]
    applied_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    applied: list[AppliedMutation] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)
    rollback_available: bool = True


@runtime_checkable
class DomainMutationAdapter(Protocol):
    """统一领域变更协议。"""

    domain: str

    async def prepare_many(
        self,
        targets: list[CanonicalFormulaTarget],
        values: dict[str, Any],
    ) -> list[FormulaMutation]: ...

    async def apply_many(
        self,
        mutations: list[FormulaMutation],
    ) -> list[AppliedMutation]: ...

    async def restore_many(
        self,
        snapshots: list[FormulaMutation],
    ) -> list[RestoredMutation]: ...

    async def read_versions(
        self,
        targets: list[CanonicalFormulaTarget],
    ) -> dict[str, str]: ...
