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
    AuditCheckSignoff,
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
    FillPreviewSession,
    FinancialReport,
    FinancialReportType,
    NoteStatus,
    NoteValidationResult,
    OpinionType,
    ReportConfig,
    ReportConfigBaseline,
    ReportStatus,
    SourceTemplate,
)
from app.models.workpaper_models import (
    RegionType,
    ReviewCommentStatus,
    ReviewRecord,
    WorkingPaper,
    WorkpaperSheetClassification,
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
from app.models.workpaper_template_version import WorkpaperTemplateVersion
from app.models.project_wp_sheet_override import ProjectWorkpaperSheetOverride
from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.ai_models import AIModelConfig, AIModelType, AIProvider, DocumentType, DocumentScan, DocumentExtracted, DocumentMatch, RecognitionStatus, MatchResult
from app.models.archive_models import ArchiveJob
from app.models.eqcr_models import (
    EqcrDisagreementResolution,
    EqcrOpinion,
    EqcrReviewNote,
    EqcrShadowComputation,
)
from app.models.related_party_models import (
    RelatedPartyRegistry,
    RelatedPartyTransaction,
)
from app.models.independence_models import AnnualIndependenceDeclaration
from app.models.qc_rule_models import QcRuleDefinition
from app.models.enterprise_linkage_models import AdjustmentEditingLock, TbChangeHistory, EventCascadeLog  # noqa: F401
from app.models.v3_refinement_models import AiContentLog, CrossModuleConflict, TimeMachineSnapshot  # noqa: F401
from app.models.account_note_mapping_models import AccountNoteMapping  # noqa: F401
from app.models.consol_cell_comment_models import ConsolCellComment  # noqa: F401
from app.models.consol_worksheet_data_models import ConsolWorksheetData  # noqa: F401
from app.models.consol_note_data_models import ConsolNoteData  # noqa: F401
from app.models.editing_lock_models import EditingLock  # noqa: F401
from app.models.confirmation_models import Confirmation, ConfirmationType, ConfirmationStatus  # noqa: F401
from app.models.account_package_models import AccountPackageProgramStatus  # noqa: F401
from app.models.bad_debt_models import (  # noqa: F401
    BadDebtDetailRow,
    ProvisionMethod,
    PROVISION_METHOD_LABELS,
)
from app.models.wp_export_models import (  # noqa: F401
    WpExportSnapshot,
    WpVersionArchive,
)
from app.models.procedure_models import (  # noqa: F401
    ProcedureInstance,
    ProcedureOperationPreview,
    ProcedureRowDefinition,
    ProcedureRowTask,
    ProcedureRowTaskHistory,
    ProcedureTrimScheme,
)
from app.models.wp_visibility_models import (  # noqa: F401
    WorkpaperDelegationHistory,
    WpAccessSecurityOutbox,
    WpVisibilityInvalidationOutbox,
    WpVisibilityPolicyEpoch,
)
from app.models.acnr_overlay_model import AcnrProjectOverlay  # noqa: F401
from app.models.acnr_invalidation_model import (  # noqa: F401
    AcnrInvalidationEpoch,
    AcnrInvalidationOutbox,
)

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
    "AuditCheckSignoff",
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
    "ReportConfigBaseline",
    "FinancialReport",
    "CfsAdjustment",
    "DisclosureNote",
    "AuditReport",
    "AuditReportTemplate",
    "ExportTask",
    "NoteValidationResult",
    "FillPreviewSession",
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
    "WorkpaperSheetClassification",
    "WorkpaperTemplateVersion",
    "ProjectWorkpaperSheetOverride",
    # --- archive models ---
    "ArchiveJob",
    # --- EQCR models (R5) ---
    "EqcrOpinion",
    "EqcrReviewNote",
    "EqcrShadowComputation",
    "EqcrDisagreementResolution",
    # --- related party models (R5) ---
    "RelatedPartyRegistry",
    "RelatedPartyTransaction",
    # --- independence declaration (R5) ---
    "AnnualIndependenceDeclaration",
    # --- QC rule definitions (R6) ---
    "QcRuleDefinition",
    # --- V3 收官增强 (V017) ---
    "AiContentLog",
    "CrossModuleConflict",
    "TimeMachineSnapshot",
    # --- 懒建表入 D6 (V040/V041) ---
    "AccountNoteMapping",
    "ConsolCellComment",
    "ConsolWorksheetData",
    "ConsolNoteData",
    # --- 通用编辑锁 (V057) ---
    "EditingLock",
    # --- 函证管理 (V058) ---
    "Confirmation",
    "ConfirmationType",
    "ConfirmationStatus",
    # --- 科目工作包程序状态 (V063) ---
    "AccountPackageProgramStatus",
    # --- 坏账准备明细表嵌套子表 D2-3 (V070) ---
    "BadDebtDetailRow",
    "ProvisionMethod",
    "PROVISION_METHOD_LABELS",
    # --- 底稿导出快照与版本归档 (V071) ---
    "WpExportSnapshot",
    "WpVersionArchive",
    # --- 审计程序裁剪/委派 (Phase9) + V105 程序行任务模型 ---
    "ProcedureInstance",
    "ProcedureTrimScheme",
    "ProcedureRowDefinition",
    "ProcedureRowTask",
    "ProcedureRowTaskHistory",
    "ProcedureOperationPreview",
    # --- 底稿可见性隔离 (procedure-delegation-visibility-isolation / V113) ---
    "WorkpaperDelegationHistory",
    "WpAccessSecurityOutbox",
    "WpVisibilityPolicyEpoch",
    "WpVisibilityInvalidationOutbox",
    # --- ACNR Overlay + 失效 durable (acnr-invalidation-overlay-hardening / V122) ---
    "AcnrProjectOverlay",
    "AcnrInvalidationEpoch",
    "AcnrInvalidationOutbox",
]