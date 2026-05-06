"""SQLAlchemy 数据模型包"""

from app.models.base import (
    AuditMixin,
    Base,
    PermissionLevel,
    ProjectStatus,
    ProjectType,
    ProjectUserRole,
    SoftDeleteMixin,
    TimestampMixin,
    UserRole,
)
from app.models.core import (
    Log,
    Notification,
    Project,
    ProjectUser,
    User,
)
from app.models.audit_platform_models import (
    AccountCategory,
    AccountChart,
    AccountDirection,
    AccountMapping,
    AccountSource,
    Adjustment,
    AdjustmentType,
    ImportBatch,
    ImportStatus,
    MappingType,
    Materiality,
    ReviewStatus,
    TbAuxBalance,
    TbAuxLedger,
    TbBalance,
    TbLedger,
    TrialBalance,
)
from app.models.dataset_models import (
    ActivationRecord,
    ActivationType,
    ArtifactStatus,
    DatasetStatus,
    ImportArtifact,
    ImportEventConsumption,
    ImportEventOutbox,
    ImportJob,
    JobStatus,
    LedgerDataset,
    OutboxStatus,
)
from app.models.report_models import (
    AuditReport,
    AuditReportTemplate,
    CashFlowCategory,
    CfsAdjustment,
    CompanyType,
    ContentType,
    DisclosureNote,
    ExportTask,
    ExportTaskStatus,
    ExportTaskType,
    FinancialReport,
    FinancialReportType,
    NoteStatus,
    NoteValidationResult,
    OpinionType,
    ReportConfig,
    ReportStatus,
    SourceTemplate,
)
from app.models.workpaper_models import (
    RegionType,
    ReviewCommentStatus,
    ReviewRecord,
    WorkingPaper,
    WpCrossRef,
    WpFileStatus,
    WpIndex,
    WpQcResult,
    WpSourceType,
    WpStatus,
    WpTemplate,
    WpTemplateMeta,
    WpTemplateSet,
    WpTemplateStatus,
)
from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.ai_models import AIModelConfig, AIModelType, AIProvider, DocumentType, DocumentScan, DocumentExtracted, DocumentMatch, RecognitionStatus, MatchResult
from app.models.archive_models import ArchiveJob
from app.models.audit_log_models import AuditLogEntry
from app.models.handover_models import HandoverRecord, HandoverReasonCode, HandoverScope
from app.models.independence_models import IndependenceDeclaration
from app.models.rotation_models import PartnerRotationOverride

__all__ = [
    # --- base ---
    "Base",
    "SoftDeleteMixin",
    "TimestampMixin",
    "AuditMixin",
    "UserRole",
    "ProjectType",
    "ProjectStatus",
    "ProjectUserRole",
    "PermissionLevel",
    # --- core ---
    "User",
    "Project",
    "ProjectUser",
    "Log",
    "Notification",
    # --- audit platform enums ---
    "AccountDirection",
    "AccountCategory",
    "AccountSource",
    "MappingType",
    "AdjustmentType",
    "ReviewStatus",
    "ImportStatus",
    "DatasetStatus",
    "JobStatus",
    "ArtifactStatus",
    "ActivationType",
    "OutboxStatus",
    # --- audit platform models ---
    "AccountChart",
    "AccountMapping",
    "TbBalance",
    "TbLedger",
    "TbAuxBalance",
    "TbAuxLedger",
    "Adjustment",
    "TrialBalance",
    "Materiality",
    "ImportBatch",
    "LedgerDataset",
    "ImportJob",
    "ImportArtifact",
    "ImportEventOutbox",
    "ImportEventConsumption",
    "ActivationRecord",
    # --- report enums ---
    "FinancialReportType",
    "CashFlowCategory",
    "ContentType",
    "SourceTemplate",
    "NoteStatus",
    "OpinionType",
    "CompanyType",
    "ReportStatus",
    "ExportTaskType",
    "ExportTaskStatus",
    # --- report models ---
    "ReportConfig",
    "FinancialReport",
    "CfsAdjustment",
    "DisclosureNote",
    "AuditReport",
    "AuditReportTemplate",
    "ExportTask",
    "NoteValidationResult",
    # --- attachment models ---
    "Attachment",
    "AttachmentWorkingPaper",
    # --- ai enums/models ---
    "AIModelType",
    "AIProvider",
    "AIModelConfig",
    # --- workpaper enums ---
    "WpTemplateStatus",
    "RegionType",
    "WpStatus",
    "WpSourceType",
    "WpFileStatus",
    "ReviewCommentStatus",
    # --- workpaper models ---
    "WpTemplate",
    "WpTemplateMeta",
    "WpTemplateSet",
    "WpIndex",
    "WorkingPaper",
    "WpCrossRef",
    "WpQcResult",
    "ReviewRecord",
    # --- archive models ---
    "ArchiveJob",
    # --- audit log models ---
    "AuditLogEntry",
    # --- handover models ---
    "HandoverRecord",
    "HandoverReasonCode",
    "HandoverScope",
    # --- independence models ---
    "IndependenceDeclaration",
    # --- rotation models ---
    "PartnerRotationOverride",
]