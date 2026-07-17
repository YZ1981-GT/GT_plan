"""底稿可见性隔离 · 服务层（procedure-delegation-visibility-isolation）

Task 3 组件 C3（Role/Mapping）：

- ``VisibilityRole`` / ``VisibilityContext``：唯一角色分类结果契约（frozen）。
- ``VisibilityRoleClassifier``：唯一角色分类入口（Admin/Supervisor/Restricted）。
- ``StaffUserMappingService``：写事务用严格 staff↔user 双向映射校验。

Task 4 组件 C4（ProcedureWpResolver + server-side sheet binding catalog）：

- ``ProcedureWpResolver`` / ``ProcedureBindingSources`` / ``WpBindingResolution`` /
  ``BindingRejectReason``：标准/自定义 procedure 多来源唯一一致解析为 ``wp_index_id``，
  零/多/冲突 fail-closed（记 ``binding_conflict``），纯读不改业务数据。
- ``SheetBindingCatalog`` / ``SheetResolution`` / ``SheetResolveReason``：在已确定
  project+wp_index+version 内把 checklist item / render sheet / ProcedureRowTask 映射到
  稳定 ``sheet_key``；无法唯一映射即拒绝，不退化整稿授权。

Task 5 组件 C5（VisibilityQuery）：

- ``AccessGrant``：独立访问授权项（access_kind/identity/allowed_sheet_keys/readonly）。
- ``VisibilityGrantSet``：``wp_index_id → grants`` 去重可见集。
- ``VisibilityQueryService``：单次 UNION ALL 产生 lead/assignee/reviewer/lead_history/row_history，
  Admin 显式 admin grant、Supervisor 显式 supervisor_scope grant；Non_Admin 与 scope_cycles 相交，
  空集不回退循环级；history 只读不可变快照（staff/task 重绑不改历史归属）。
- ``REGISTERED_ACCESS_KINDS`` / ``ALL_PAGES``：已登记 access_kind 集合与整稿页面哨兵。

Task 7 组件 C12（DelegationTransaction）：

- ``DelegationTransactionService``：两层委派/转派/清空、scope expansion 与 policy epoch/
  invalidation outbox 的同事务原子编排（只 flush，router 提交）；两层互不覆盖、无 last-write-wins。
- ``LeadDelegationRequest`` / ``RowDelegationRequest`` / ``DelegationResult``：委派请求与结果契约。
- ``DelegationError`` / ``DelegationRejectReason``：fail-closed 拒绝（调用方回滚事务）。

后续任务（C6 ActionMatrix、C8 Wp_Bound_Gate 等）在同一 package 内扩展，
不重复声明此处已冻结的契约。
"""

from __future__ import annotations

from app.services.wp_visibility.contracts import (
    ALL_PAGE_ACCESS_KINDS,
    ALL_PAGES,
    READONLY_ACCESS_KINDS,
    REGISTERED_ACCESS_KINDS,
    AccessGrant,
    ResourceRef,
    VisibilityContext,
    VisibilityRole,
    WpAccessContext,
    WpBoundRequest,
    build_access_grant,
)
from app.services.wp_visibility.procedure_wp_resolver import (
    BindingRejectReason,
    ProcedureBindingSources,
    ProcedureWpResolver,
    WpBindingResolution,
)
from app.services.wp_visibility.role_classifier import VisibilityRoleClassifier
from app.services.wp_visibility.sheet_binding_catalog import (
    SheetBindingCatalog,
    SheetResolution,
    SheetResolveReason,
)
from app.services.wp_visibility.staff_user_mapping import (
    MappingRejectReason,
    StaffMappingResolution,
    StaffUserMappingService,
)
from app.services.wp_visibility.visibility_query import (
    ALL_PAGES,
    REGISTERED_ACCESS_KINDS,
    AccessGrant,
    VisibilityGrantSet,
    VisibilityQueryService,
)
from app.services.wp_visibility.delegation_transaction import (
    DelegationError,
    DelegationRejectReason,
    DelegationResult,
    DelegationTransactionService,
    LeadDelegationRequest,
    RowDelegationRequest,
)
from app.services.wp_visibility.action_matrix import (
    ActionMatrix,
    MatrixEntry,
    MatrixKey,
)
from app.services.wp_visibility.denial import (
    EXTERNAL_NOT_FOUND_DETAIL,
    DenialError,
    DenialReason,
    DenialResponder,
    ExternalNotFound,
    RateLimited,
)
from app.services.wp_visibility.wp_bound_gate import (
    NullRateLimiter,
    RateLimitDecision,
    RateLimiter,
    resolve_wp_binding_and_access,
)
from app.services.wp_visibility.editor_security import (
    JWT_LIFETIME_CONFIG_ID,
    REQUIRED_EDITOR_CLAIMS,
    EditorTokenResult,
    compute_user_can_write,
    frozen_jwt_lifetime_seconds,
    sign_editor_token,
    validate_editor_token,
    verify_callback_preconditions,
)
from app.services.wp_visibility.workpaper_list_query import (
    DEFAULT_PAGE_SIZE,
    LEGACY_STATUS_MAPPING,
    MAX_PAGE_SIZE,
    REGISTERED_SORTS,
    InvalidListParams,
    ListParams,
    WorkpaperListFilters,
    WorkpaperListQueryService,
)
from app.services.wp_visibility.epoch_cache import (
    EPOCH_INVALIDATE_CHANNEL_PREFIX,
    EpochUnavailable,
    PersistentEpochCache,
    get_epoch_cache,
    invalidation_channel,
    reset_epoch_cache,
)
from app.services.wp_visibility.rate_limit_profile import (
    TARGET_CONCURRENCY,
    CapacityReport,
    MeasurementModeRateLimiter,
    PerformanceProfile,
    RateLimitProfile,
    RateLimitProfileError,
    freeze_rate_limit_profile,
    get_default_rate_limiter,
    measurement_only_profile,
    reset_default_rate_limiter,
)
from app.services.wp_visibility.perf_metrics import (
    VisibilityMetrics,
    get_metrics,
    measure,
    percentile,
    reset_metrics,
)
from app.services.wp_visibility.invalidation_dispatcher import (
    InvalidationDispatcher,
    handle_invalidation_message,
    run_invalidation_subscriber,
)

__all__ = [
    # C3 · Role/Mapping（Task 3）
    "VisibilityRole",
    "VisibilityContext",
    "VisibilityRoleClassifier",
    "StaffUserMappingService",
    "StaffMappingResolution",
    "MappingRejectReason",
    # C4 · ProcedureWpResolver + sheet binding catalog（Task 4）
    "ProcedureWpResolver",
    "ProcedureBindingSources",
    "WpBindingResolution",
    "BindingRejectReason",
    "SheetBindingCatalog",
    "SheetResolution",
    "SheetResolveReason",
    # C5 · VisibilityQuery（Task 5）
    "VisibilityQueryService",
    "VisibilityGrantSet",
    "AccessGrant",
    "REGISTERED_ACCESS_KINDS",
    "ALL_PAGES",
    # C12 · DelegationTransaction（Task 7）
    "DelegationTransactionService",
    "LeadDelegationRequest",
    "RowDelegationRequest",
    "DelegationResult",
    "DelegationError",
    "DelegationRejectReason",
    # C6 · ActionMatrix（Task 6）
    "ActionMatrix",
    "MatrixKey",
    "MatrixEntry",
    # C7 · DenialResponder + SecurityAuditOutbox（Task 6）
    "DenialResponder",
    "DenialReason",
    "DenialError",
    "ExternalNotFound",
    "RateLimited",
    "EXTERNAL_NOT_FOUND_DETAIL",
    # C8 · Wp_Bound_Gate（Task 6）
    "resolve_wp_binding_and_access",
    "RateLimiter",
    "RateLimitDecision",
    "NullRateLimiter",
    # C2 · gate contracts（Task 6）
    "ResourceRef",
    "WpBoundRequest",
    "WpAccessContext",
    # C11 · EditorSecurity（Task 11）
    "validate_editor_token",
    "sign_editor_token",
    "compute_user_can_write",
    "verify_callback_preconditions",
    "frozen_jwt_lifetime_seconds",
    "EditorTokenResult",
    "REQUIRED_EDITOR_CLAIMS",
    "JWT_LIFETIME_CONFIG_ID",
    # C13 · List/Views（Task 8）
    "WorkpaperListQueryService",
    "WorkpaperListFilters",
    "ListParams",
    "InvalidListParams",
    "REGISTERED_SORTS",
    "MAX_PAGE_SIZE",
    "DEFAULT_PAGE_SIZE",
    "LEGACY_STATUS_MAPPING",
    # C15 · Cache/Rate/Perf（Task 13）
    "PersistentEpochCache",
    "EpochUnavailable",
    "get_epoch_cache",
    "reset_epoch_cache",
    "invalidation_channel",
    "EPOCH_INVALIDATE_CHANNEL_PREFIX",
    "PerformanceProfile",
    "CapacityReport",
    "RateLimitProfile",
    "RateLimitProfileError",
    "MeasurementModeRateLimiter",
    "measurement_only_profile",
    "freeze_rate_limit_profile",
    "get_default_rate_limiter",
    "reset_default_rate_limiter",
    "TARGET_CONCURRENCY",
    "VisibilityMetrics",
    "get_metrics",
    "reset_metrics",
    "percentile",
    "measure",
    "InvalidationDispatcher",
    "run_invalidation_subscriber",
    "handle_invalidation_message",
]
