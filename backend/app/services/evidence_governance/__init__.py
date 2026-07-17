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
    backfill_runner,
    command_audit,
    contracts,
    facade,
    frozen_contracts,
    migration_allocation,
    migration_phases,
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
from .archive_adapter import (
    ArchiveJobResult,
    ArchiveOrchestratorAdapter,
    DeliverableArchiveResult,
    DeliverableServiceAdapter,
    DeliverableVersion,
    InMemoryArchiveOrchestratorAdapter,
    InMemoryDeliverableServiceAdapter,
)
from .offline_manifest_verifier import (
    DifferenceType,
    OfflineManifestVerifier,
    OfflineVerificationResult,
    VerificationDifference,
    VerificationStatus,
    serialize_sealed_package,
)
from .observability import (
    ALERT_ERROR,
    ALERT_INFO,
    ALERT_TYPES,
    ALERT_WARNING,
    METRIC_DOMAINS,
    METRIC_OUTCOMES,
    AlertEvent,
    EvidenceGovernanceMetrics,
    get_evidence_metrics,
    reset_evidence_metrics,
)
from .audit_retention import (
    DEFAULT_RETENTION_DAYS,
    RetentionStatus,
    assert_audit_mutable,
    evaluate_retention,
    is_within_retention,
)
from .retention_legal_hold_service import (
    FrozenClosure,
    HoldActivationResult,
    NewEdgeResult,
    PurgeConditions,
    PurgeDecision,
    PurgeResult,
    RetentionLegalHoldService,
    compute_new_edge_additions,
    evaluate_purge_conditions,
    freeze_hold_closure,
    split_node_key,
    subject_has_purge_capability,
)
from .migration_phases import (
    PHASES as MIGRATION_PHASES,
    PHASE_M0_DARK_READ,
    PHASE_M1_BACKFILL,
    PHASE_M2_DUAL_WRITE,
    PHASE_M3_CUTOVER,
    PHASE_M4_RETIREMENT,
    CutoverPreconditions,
    PhaseBehavior,
    RetirementPreconditions,
    RollbackPlan,
    can_advance,
    evaluate_cutover_preconditions,
    evaluate_retirement_preconditions,
    phase_behavior,
    production_rollback_plan,
)
from .backfill_runner import (
    BACKFILL_MIGRATION_VERSION,
    BackfillAggregate,
    BackfillReport,
    EvidenceBackfillRunner,
    build_backfill_aggregates,
    build_batch_key,
    compute_input_hash,
)
from .quality_snapshot import (
    AGING_BUCKET_KEYS,
    BLOCKING_ISSUE_CODES,
    QualitySnapshotResult,
    build_snapshot_input_hash,
    compute_quality_snapshot,
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
    "migration_phases",
    "backfill_runner",
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
    # archive adapter (Task 7.2)
    "ArchiveOrchestratorAdapter",
    "DeliverableServiceAdapter",
    "ArchiveJobResult",
    "DeliverableVersion",
    "DeliverableArchiveResult",
    "InMemoryArchiveOrchestratorAdapter",
    "InMemoryDeliverableServiceAdapter",
    # offline manifest verifier (Task 7.2)
    "OfflineManifestVerifier",
    "OfflineVerificationResult",
    "VerificationDifference",
    "VerificationStatus",
    "DifferenceType",
    "serialize_sealed_package",
    # retention & legal hold (Task 7.3)
    "RetentionLegalHoldService",
    "FrozenClosure",
    "freeze_hold_closure",
    "compute_new_edge_additions",
    "PurgeConditions",
    "PurgeDecision",
    "evaluate_purge_conditions",
    "subject_has_purge_capability",
    "split_node_key",
    "HoldActivationResult",
    "NewEdgeResult",
    "PurgeResult",
    # observability — metrics/trace/alerting (Task 7.4)
    "EvidenceGovernanceMetrics",
    "AlertEvent",
    "get_evidence_metrics",
    "reset_evidence_metrics",
    "METRIC_DOMAINS",
    "METRIC_OUTCOMES",
    "ALERT_TYPES",
    "ALERT_INFO",
    "ALERT_WARNING",
    "ALERT_ERROR",
    # audit retention (Task 7.4)
    "RetentionStatus",
    "is_within_retention",
    "evaluate_retention",
    "assert_audit_mutable",
    "DEFAULT_RETENTION_DAYS",
    # M0–M4 migration phases (Task 8.1)
    "MIGRATION_PHASES",
    "PHASE_M0_DARK_READ",
    "PHASE_M1_BACKFILL",
    "PHASE_M2_DUAL_WRITE",
    "PHASE_M3_CUTOVER",
    "PHASE_M4_RETIREMENT",
    "PhaseBehavior",
    "CutoverPreconditions",
    "RetirementPreconditions",
    "RollbackPlan",
    "can_advance",
    "phase_behavior",
    "evaluate_cutover_preconditions",
    "evaluate_retirement_preconditions",
    "production_rollback_plan",
    # M1 checkpoint backfill (Task 8.1)
    "EvidenceBackfillRunner",
    "BackfillAggregate",
    "BackfillReport",
    "build_backfill_aggregates",
    "build_batch_key",
    "compute_input_hash",
    "BACKFILL_MIGRATION_VERSION",
    # quality snapshot recompute (Task 9.6 — P30)
    "compute_quality_snapshot",
    "build_snapshot_input_hash",
    "QualitySnapshotResult",
    "AGING_BUCKET_KEYS",
    "BLOCKING_ISSUE_CODES",
]
