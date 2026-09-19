"""Archive adapter — Task 7.2 (Wave 6).

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R11
Design: §1.2 复用边界, §5.5 Archive
Properties: P23, P24

Adapter contracts for deliverable center and ArchiveOrchestrator.
Governance layer wraps — never replaces — these engines (design §1.2).

The adapters follow the frozen contract shapes from Task 1.5
(adapter_contract_manifest.json) and provide a thin governance integration
layer that:
  - Delegates archival workflow to the real ArchiveOrchestrator
  - Delegates deliverable operations to the real DeliverableService
  - Adds evidence graph snapshot + manifest + offline verification
  - Never duplicates storage, workflow steps, or cloud push logic
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)


# ─────────────────────────────────────────────────────────────────────────────
# Adapter Protocols (shape contracts, not engine duplication)
# ─────────────────────────────────────────────────────────────────────────────


@runtime_checkable
class ArchiveOrchestratorAdapter(Protocol):
    """Adapter protocol for the existing ArchiveOrchestrator.

    Design §1.2: "ArchiveOrchestrator：归档工作流、存储与断点；
    治理层只增加证据图快照、manifest 和离线验证。"

    The governance layer delegates archival workflow operations here and wraps
    them with manifest generation + integrity verification.
    """

    async def orchestrate(
        self,
        project_id: str,
        scope: dict[str, Any],
    ) -> "ArchiveJobResult":
        """Trigger archival orchestration for a project scope.

        Delegates to ArchiveOrchestrator.orchestrate().
        Returns a job result with status and metadata.
        """
        ...

    async def retry(self, job_id: str) -> "ArchiveJobResult":
        """Retry a failed archive job.

        Delegates to ArchiveOrchestrator.retry().
        """
        ...

    async def get_job(self, job_id: str) -> "ArchiveJobResult":
        """Get archive job status.

        Delegates to ArchiveOrchestrator.get_job().
        """
        ...


@runtime_checkable
class DeliverableServiceAdapter(Protocol):
    """Adapter protocol for the existing deliverable center.

    Design §1.2: "deliverable center：交付件版本与固化；
    治理层只做 FormalOutput preflight/finalize gate。"

    The governance layer delegates deliverable operations here and gates them
    through FormalOutput evidence checks.
    """

    async def get_version_chain(
        self, task_id: str
    ) -> list["DeliverableVersion"]:
        """Get deliverable version chain.

        Delegates to DeliverableService.get_version_chain().
        """
        ...

    async def archive_project_deliverables(
        self, project_id: str
    ) -> "DeliverableArchiveResult":
        """Archive all deliverables for a project.

        Delegates to DeliverableService.archive_project_deliverables().
        Called during archive orchestration to freeze deliverable versions.
        """
        ...

    async def confirm_deliverable(
        self, deliverable_id: str
    ) -> bool:
        """Confirm a deliverable (freeze its version).

        Delegates to DeliverableService.confirm_deliverable().
        """
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Data types for adapter results
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ArchiveJobResult:
    """Result from ArchiveOrchestrator operations."""

    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "pending"  # pending | running | completed | failed
    project_id: str = ""
    scope: dict[str, Any] = field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_completed(self) -> bool:
        return self.status == "completed"

    @property
    def is_failed(self) -> bool:
        return self.status == "failed"


@dataclass
class DeliverableVersion:
    """A version entry in the deliverable version chain."""

    version_id: str = ""
    deliverable_id: str = ""
    version_no: int = 1
    content_hash: str = ""
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    confirmed: bool = False
    confirmed_at: datetime | None = None


@dataclass
class DeliverableArchiveResult:
    """Result from archiving project deliverables."""

    success: bool = False
    archived_count: int = 0
    deliverable_ids: list[str] = field(default_factory=list)
    error: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Default (no-op/stub) implementations for testing/offline mode
# ─────────────────────────────────────────────────────────────────────────────


class InMemoryArchiveOrchestratorAdapter:
    """In-memory adapter for testing (no real orchestrator connection).

    Production would delegate to the real ArchiveOrchestrator class.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, ArchiveJobResult] = {}

    async def orchestrate(
        self,
        project_id: str,
        scope: dict[str, Any],
    ) -> ArchiveJobResult:
        job = ArchiveJobResult(
            project_id=project_id,
            scope=scope,
            status="completed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        self._jobs[job.job_id] = job
        return job

    async def retry(self, job_id: str) -> ArchiveJobResult:
        if job_id not in self._jobs:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                "Archive job not found",
            )
        job = self._jobs[job_id]
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        return job

    async def get_job(self, job_id: str) -> ArchiveJobResult:
        if job_id not in self._jobs:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                "Archive job not found",
            )
        return self._jobs[job_id]


class InMemoryDeliverableServiceAdapter:
    """In-memory adapter for testing (no real deliverable center connection).

    Production would delegate to the real DeliverableService class.
    """

    def __init__(self) -> None:
        self._versions: dict[str, list[DeliverableVersion]] = {}
        self._archived: list[str] = []

    async def get_version_chain(
        self, task_id: str
    ) -> list[DeliverableVersion]:
        return self._versions.get(task_id, [])

    async def archive_project_deliverables(
        self, project_id: str
    ) -> DeliverableArchiveResult:
        self._archived.append(project_id)
        return DeliverableArchiveResult(
            success=True,
            archived_count=0,
            deliverable_ids=[],
        )

    async def confirm_deliverable(
        self, deliverable_id: str
    ) -> bool:
        return True


__all__ = [
    "ArchiveOrchestratorAdapter",
    "DeliverableServiceAdapter",
    "ArchiveJobResult",
    "DeliverableVersion",
    "DeliverableArchiveResult",
    "InMemoryArchiveOrchestratorAdapter",
    "InMemoryDeliverableServiceAdapter",
]
