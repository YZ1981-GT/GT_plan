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
from app.models.workpaper_lifecycle_models import WorkpaperLifecycleEvent
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
    ProcedureTrimCycleConfirmation,
    ProcedureRowDefinition,
    ProcedureRowTask,
    ProcedureRowTaskHistory,
    ProcedureTrimScheme,
)
from app.models.wp_generation_models import (  # noqa: F401
    WorkpaperGenerationItem,
    WorkpaperGenerationOperation,
)
from app.models.batch_project_models import ProjectBatchImportPlan  # noqa: F401
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
# 附注正文内容模板与原子批量应用审计（迁移 V187）
from app.models.note_content_template_models import (  # noqa: F401
    NoteContentTemplate,
    NoteContentTemplateVersion,
    NoteTextBatchApplication,
)
# 公式推送引擎目标级状态 / 运行记录（迁移 V169）
from app.models.formula_push_models import (  # noqa: F401
    FormulaPushRun,
    FormulaPushState,
)
# 合并推送运行记录 / 合并附注单元格公式（迁移 V172）
from app.models.consol_push_models import (  # noqa: F401
    ConsolNoteFormula,
    ConsolPushRun,
)
# 公式全局设置 / 本项目适配 / 公式模板（迁移 V199）
from app.models.formula_setting_models import (  # noqa: F401
    FormulaPublish,
    FormulaSetting,
    FormulaSyncItem,
    FormulaTemplate,
    FormulaTemplateSubscription,
    FormulaTemplateVersion,
)
# 预审样本存续核对汇总（迁移 V212）
from app.models.audit_phase_models import InterimSurvivalCheck  # noqa: F401
# D5 合并范围用户确认快照（迁移 V183）
from app.models.consol_scope_confirmation_models import (  # noqa: F401
    ConsolScopeConfirmation,
    ConsolScopeConfirmationNode,
)
# 门禁逐项确认留痕（迁移 V217, S2 ADR-CCN-06）
from app.models.gate_acknowledgement_models import GateAcknowledgement  # noqa: F401
# 底稿 HTML ↔ OnlyOffice 双向回写同步域（迁移 V151 的 28 张表）
from app.models.workpaper_sync_models import (  # noqa: F401
    WORKPAPER_SYNC_TABLES,
    WorkpaperArtifact,
    WorkpaperCallbackDelivery,
    WorkpaperCallbackRecoveryCase,
    WorkpaperCallbackRecoveryCaseEvent,
    WorkpaperContentApplication,
    WorkpaperContentApplicationEvent,
    WorkpaperContentRepresentation,
    WorkpaperContentRevisionBackfillLedger,
    WorkpaperContentVersion,
    WorkpaperEntryEvidenceScenario,
    WorkpaperForcesaveRequest,
    WorkpaperOoClientConfirmation,
    WorkpaperOoCloseIntent,
    WorkpaperOoCloseIntentEvent,
    WorkpaperOoParticipant,
    WorkpaperOoRoom,
    WorkpaperPendingMutation,
    WorkpaperRepresentationUpgradeCandidate,
    WorkpaperSyncConflict,
    WorkpaperSyncDefinitionArtifact,
    WorkpaperSyncDefinitionBundle,
    WorkpaperSyncDefinitionNullMarker,
    WorkpaperSyncEntryState,
    WorkpaperSyncOperation,
    WorkpaperSyncOperationContributor,
    WorkpaperSyncOperationEvent,
    WorkpaperSyncScopeIndex,
    WorkpaperSyncTestRun,
)
# V233（platform-global-display-settings-closure 任务 1A）：账号级显示偏好
from app.models.user_display_preferences import UserDisplayPreferences  # noqa: F401

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
    "WorkpaperLifecycleEvent",
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
    # --- 粗裁确认投影 / 两阶段生成 (trim-generation-plan-followup-optimizations / V218、V224) ---
    "ProcedureTrimCycleConfirmation",
    "WorkpaperGenerationOperation",
    "WorkpaperGenerationItem",
    "ProjectBatchImportPlan",
    # --- 底稿可见性隔离 (procedure-delegation-visibility-isolation / V113) ---
    "WorkpaperDelegationHistory",
    "WpAccessSecurityOutbox",
    "WpVisibilityPolicyEpoch",
    "WpVisibilityInvalidationOutbox",
    # --- ACNR Overlay + 失效 durable (acnr-invalidation-overlay-hardening / V122) ---
    "AcnrProjectOverlay",
    "AcnrInvalidationEpoch",
    "AcnrInvalidationOutbox",
    # --- 公式推送引擎 (chain-closure-phase2-formula-push-engine / V169) ---
    "FormulaPushRun",
    "FormulaPushState",
    # --- 显示偏好 (platform-global-display-settings-closure / V233) ---
    "UserDisplayPreferences",
]