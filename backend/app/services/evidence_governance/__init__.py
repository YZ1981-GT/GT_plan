"""Evidence Governance 治理编排层（strangler facade）。

本包是 `attachment-ocr-ai-evidence-governance-hardening` spec 的新增治理层根。
它 **只允许委托** 以下八项既有引擎，禁止复制、分叉或影子实现：

    AttachmentService / UnifiedOCRService / KnowledgeIndexService /
    AiContentLog(Service) / ACNR(resolver+events) / StalePropagationEngine /
    DeliverableService(deliverable center) / ArchiveOrchestrator

冻结契约见 ``frozen_contracts``（API/幂等键/expected-version/错误码/ActorContext/
canonical JSON+hash）；引擎 adapter contract 与禁止分叉清单见
``backend/data/evidence_governance/adapter_contract_manifest.json``，
由 ``backend/scripts/check/check_evidence_no_fork.py`` 在 CI 强制。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 1.5 (Wave 0 — 冻结 P0 契约与既有引擎边界)
Requirements: R1, R5, R7, R8, R9, R11, R12, R15
"""

from __future__ import annotations

from . import (
    command_audit,
    contracts,
    facade,
    frozen_contracts,
    migration_allocation,
    outbox,
    role_capability_contract,
    typed_adapters,
)
from .capability_guard import CapabilityGuard
from .command_audit import CommandAuditService
from .facade import (
    CommandRequest,
    CommandResult,
    CommandTxn,
    EvidenceGovernanceFacade,
    OutboxEvent,
)
from .outbox import InboxService, OutboxService
from .scope_guard import (
    ObjectScope,
    ProjectYearScopeGuard,
)
from .secure_attachment_gateway import (
    DEFAULT_MAX_FILENAME_LENGTH,
    UPLOAD_OUTCOME_PENDING,
    UPLOAD_OUTCOMES,
    UPLOAD_TERMINAL_OUTCOMES,
    AttachmentReadResult,
    LocalByteReader,
    ReadPlan,
    SecureAttachmentGateway,
    StorageBoundaryResolver,
    UploadAttemptRecord,
    sanitize_upload_filename,
)
from .version_manager import (
    AttachmentVersionManager,
    ImpactEntry,
    ImpactReport,
    LegacyAttachmentResolver,
    LegacyRouteFacade,
    ReplaceResult,
    sanitize_attachment_response,
    sanitize_file_path_response,
)
from .typed_adapters import (
    SUPPORTED_EVIDENCE_TYPES,
    EvidenceAdapter,
    LocatorInfo,
    ResolvedTarget,
    get_adapter,
    list_adapters,
)
from .evidence_ref_service import (
    CreateEvidenceRefRequest,
    EvidenceRefResult,
    EvidenceRefService,
)
from .ocr_governance import OCRGovernanceOrchestrator
from .ocr_retry_service import OCRRetryService
from .ocr_confirmation_service import OCRConfirmationService
from .evidence_ref_query_service import (
    CursorPage,
    DeactivateRefResult,
    DependencyPage,
    DependencyRow,
    EvidenceRefQueryService,
    EvidenceRefRow,
    ImpactNode,
    ImpactResult,
)
from .citation_snapshot_service import (
    CitationLocateResult,
    CitationSnapshot,
    CitationSnapshotService,
    CitationStatus,
    CitationValidationEntry,
    CitationValidationResult,
    RetrievalCandidate,
)
from .ai_evidence_gate import (
    AI_ENTRY_REGISTRY,
    AIEvidenceGate,
    AiContentRegistration,
    AiLifecycleStatus,
    AiServiceStatus,
    GateBlockReason,
    GateCheckResult,
    GateCheckStatus,
    compute_coverage_gap,
)

__all__ = [
    # modules
    "frozen_contracts",
    "contracts",
    "role_capability_contract",
    "migration_allocation",
    "command_audit",
    "outbox",
    "facade",
    "typed_adapters",
    # facade + guards
    "EvidenceGovernanceFacade",
    "CommandRequest",
    "CommandResult",
    "CommandTxn",
    "OutboxEvent",
    "ProjectYearScopeGuard",
    "ObjectScope",
    "CapabilityGuard",
    "CommandAuditService",
    "OutboxService",
    "InboxService",
    # secure attachment gateway (Task 3.2)
    "SecureAttachmentGateway",
    "UploadAttemptRecord",
    "sanitize_upload_filename",
    "UPLOAD_OUTCOME_PENDING",
    "UPLOAD_TERMINAL_OUTCOMES",
    "UPLOAD_OUTCOMES",
    "DEFAULT_MAX_FILENAME_LENGTH",
    # secure read chain (Task 3.4)
    "StorageBoundaryResolver",
    "ReadPlan",
    "LocalByteReader",
    "AttachmentReadResult",
    # version manager (Task 3.5)
    "AttachmentVersionManager",
    "ImpactEntry",
    "ImpactReport",
    "LegacyAttachmentResolver",
    "LegacyRouteFacade",
    "ReplaceResult",
    "sanitize_attachment_response",
    "sanitize_file_path_response",
    # typed adapters (Task 4.1)
    "EvidenceAdapter",
    "ResolvedTarget",
    "LocatorInfo",
    "SUPPORTED_EVIDENCE_TYPES",
    "get_adapter",
    "list_adapters",
    # evidence ref service (Task 4.2)
    "EvidenceRefService",
    "CreateEvidenceRefRequest",
    "EvidenceRefResult",
    # OCR governance (Task 5.1)
    "OCRGovernanceOrchestrator",
    # OCR retry service (Task 5.2)
    "OCRRetryService",
    # OCR confirmation service (Task 5.3)
    "OCRConfirmationService",
    # evidence ref query service (Task 4.3)
    "EvidenceRefQueryService",
    "EvidenceRefRow",
    "CursorPage",
    "DependencyRow",
    "DependencyPage",
    "ImpactNode",
    "ImpactResult",
    "DeactivateRefResult",
    # citation snapshot service (Task 6.1)
    "CitationSnapshotService",
    "CitationSnapshot",
    "CitationLocateResult",
    "CitationValidationResult",
    "CitationValidationEntry",
    "CitationStatus",
    "RetrievalCandidate",
    # AI evidence gate (Task 6.2)
    "AIEvidenceGate",
    "AiContentRegistration",
    "AiLifecycleStatus",
    "AiServiceStatus",
    "GateBlockReason",
    "GateCheckResult",
    "GateCheckStatus",
    "AI_ENTRY_REGISTRY",
    "compute_coverage_gap",
]
