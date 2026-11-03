"""formula_runtime.contracts — 核心 contracts 定义。

定义公式运行时的规范目标身份、变更载体、执行计划/结果
以及统一领域变更协议 DomainMutationAdapter。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Mapping, Protocol, runtime_checkable
from uuid import UUID

if TYPE_CHECKING:
    from app.models.audit_platform_schemas import EventPayload

JSONValue = dict | list | str | int | float | bool | None


@dataclass(frozen=True)
class CanonicalFormulaTarget:
    """公式引用/目标的规范身份。"""

    domain: Literal["workpaper", "adjudication", "report", "note", "consol_worksheet"]
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
    """公式执行结果。

    ``outcome`` / ``recomputed_count`` / ``draft_marked_count`` / ``post_commit_events`` 由 Draft Refresh 结果聚合
    （``formula_management.refresh_outcome``，需求 3.2 / 3.3）写回；``outcome`` 取值见 ``refresh_outcome.OUTCOMES``，
    未经聚合（如回滚）为 ``None``。``affected_count = applied_count + recomputed_count``（Draft 标记数单列、不计入）；
    ``post_commit_events`` 是提交成功后才投递的事件，不进 ``to_dict``。
    """

    run_id: UUID
    status: Literal[
        "success", "recomputed", "draft_marked", "partial_success", "failed", "no_effect", "idempotent_hit",
        "rolled_back", "conflict",
    ]
    applied_count: int = 0
    restored_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    applied: list[AppliedMutation] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rollback_available: bool = True
    outcome: str | None = None
    recomputed_count: int = 0
    draft_marked_count: int = 0
    post_commit_events: list[EventPayload] = field(default_factory=list, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "outcome": self.outcome,
            "run_id": str(self.run_id),
            "affected_count": self.applied_count + self.recomputed_count,
            "applied_count": self.applied_count,
            "recomputed_count": self.recomputed_count,
            "draft_marked_count": self.draft_marked_count,
            "restored_count": self.restored_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "idempotent": self.status == "idempotent_hit",
            "rollback_available": self.rollback_available,
            "failures": list(self.failures),
            "conflicts": list(self.conflicts),
            "warnings": list(self.warnings),
        }


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
