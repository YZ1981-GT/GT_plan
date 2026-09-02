/**
 * 本文件由 `backend/scripts/gen/generate_workpaper_sync_frontend_contract.py` 生成，请勿手工编辑。
 *
 * 真源：`backend/app/routers/wp_sync_router.py`（路由模板 + Idempotency-Key 必填集）、
 * `backend/app/services/workpaper_sync/models.py`（状态机封闭域与 terminal 集）、
 * `EditorLaunchDescriptor.confirm_payload()`（confirm 逐项回传清单）、
 * `MATERIALIZE_REJECTION_STATUS`（error_code → HTTP 状态码）。
 *
 * spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 31
 */

export const WP_SYNC_CONTRACT_DIGEST = "ca3b003aeaad2f154677a9f9e499fd66e306c5ff49882c169ccc720fa0056c5b"

/**
 * 用户端统一前缀模板。`{entry_id}` 是**多段**值（186 条 entry_id 全部含 `/`，最深四段），
 * 路由用 Starlette 的 `:path` 转换器接收；拼 URL 时不得 percent-encode 其中的 `/`。
 */
export const WP_SYNC_USER_PREFIX_TEMPLATE = "/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}"

export interface WorkpaperSyncRouteSpec {
  readonly endpoint: string
  readonly method: 'GET' | 'POST'
  readonly suffix: string
  readonly idempotencyKey: 'required' | 'optional' | 'absent'
}

/** 后端**真实**路由表（一路由一方法）。前端只能从这里取路径，不得再拼字面量。 */
export const WP_SYNC_ROUTES = [
  {
    "endpoint": "claim_recovery_case",
    "idempotencyKey": "required",
    "method": "POST",
    "suffix": "/recovery-cases/{case_id}/claim"
  },
  {
    "endpoint": "confirm_descriptor",
    "idempotencyKey": "required",
    "method": "POST",
    "suffix": "/rooms/{room_id}/confirm-descriptor"
  },
  {
    "endpoint": "create_close_intent",
    "idempotencyKey": "required",
    "method": "POST",
    "suffix": "/rooms/{room_id}/close-intents"
  },
  {
    "endpoint": "create_pending_mutation",
    "idempotencyKey": "required",
    "method": "POST",
    "suffix": "/pending-mutations"
  },
  {
    "endpoint": "download_recovery_artifact",
    "idempotencyKey": "absent",
    "method": "GET",
    "suffix": "/recovery-cases/{case_id}/download"
  },
  {
    "endpoint": "get_operation",
    "idempotencyKey": "absent",
    "method": "GET",
    "suffix": "/operations/{operation_id}"
  },
  {
    "endpoint": "get_operation_conflicts",
    "idempotencyKey": "absent",
    "method": "GET",
    "suffix": "/operations/{operation_id}/conflicts"
  },
  {
    "endpoint": "get_operation_timeline",
    "idempotencyKey": "absent",
    "method": "GET",
    "suffix": "/operations/{operation_id}/timeline"
  },
  {
    "endpoint": "get_recovery_case_timeline",
    "idempotencyKey": "absent",
    "method": "GET",
    "suffix": "/recovery-cases/{case_id}/timeline"
  },
  {
    "endpoint": "list_recovery_cases",
    "idempotencyKey": "absent",
    "method": "GET",
    "suffix": "/recovery-cases"
  },
  {
    "endpoint": "materialize",
    "idempotencyKey": "required",
    "method": "POST",
    "suffix": "/materialize"
  },
  {
    "endpoint": "request_forcesave",
    "idempotencyKey": "required",
    "method": "POST",
    "suffix": "/rooms/{room_id}/forcesave"
  },
  {
    "endpoint": "resolve_conflicts",
    "idempotencyKey": "required",
    "method": "POST",
    "suffix": "/operations/{operation_id}/resolve"
  },
  {
    "endpoint": "retry_operation",
    "idempotencyKey": "absent",
    "method": "POST",
    "suffix": "/operations/{operation_id}/retry"
  },
  {
    "endpoint": "rollback_version",
    "idempotencyKey": "absent",
    "method": "POST",
    "suffix": "/versions/{version_id}/rollback"
  },
  {
    "endpoint": "terminate_recovery_download_only",
    "idempotencyKey": "absent",
    "method": "POST",
    "suffix": "/recovery-cases/{case_id}/download-only"
  }
] as const satisfies readonly WorkpaperSyncRouteSpec[]

/** 服务端**强制**携带 `Idempotency-Key` 的端点（缺 key 时复合幂等键最后一项恒空）。 */
export const WP_SYNC_IDEMPOTENT_ENDPOINTS = [
  "claim_recovery_case",
  "confirm_descriptor",
  "create_close_intent",
  "create_pending_mutation",
  "materialize",
  "request_forcesave",
  "resolve_conflicts"
] as const

/** descriptor 必备字段（缺任一项都不得挂载 DocEditor）。 */
export const WP_SYNC_DESCRIPTOR_FIELDS = [
  "operation_id",
  "room_id",
  "participant_id",
  "doc_key",
  "generation",
  "server_applied_revision",
  "client_confirmed_base_revision",
  "content_version_id",
  "representation_id",
  "representation_generation",
  "artifact_sha256",
  "write_fence_epoch",
  "authority_model",
  "authority_model_definition_sha256",
  "definition_bundle_id",
  "definition_bundle_sha256",
  "definition_bundle_slots",
  "document_type",
  "mode",
  "onlyoffice_config"
] as const

/** `onDocumentReady` 之后 confirm-descriptor 必须**逐项**回传的 identity。 */
export const WP_SYNC_DESCRIPTOR_CONFIRM_KEYS = [
  "artifact_sha256",
  "authority_model_definition_sha256",
  "content_revision",
  "definition_bundle_id",
  "definition_bundle_sha256",
  "doc_key",
  "generation",
  "participant_id",
  "representation_id",
  "write_fence_epoch"
] as const

export const WP_SYNC_OPERATION_STATES = [
  "created",
  "command_pending",
  "accepted",
  "waiting_application",
  "application_bound",
  "duplicate",
  "extracting",
  "merging",
  "conflict",
  "rematerializing",
  "applying",
  "applied",
  "refresh_required",
  "error",
  "rejected",
  "superseded",
  "authorization_stale"
] as const
export type WorkpaperSyncOperationState = (typeof WP_SYNC_OPERATION_STATES)[number]

/** 封闭域只作类型约束（运行时由派生逻辑保证），故不发数组常量。 */
export type WorkpaperSyncOperationShape = "pre_correlation" | "primary" | "duplicate"

export const WP_SYNC_ROOM_STATES = [
  "opening",
  "active",
  "close_barrier",
  "closing",
  "refresh_required",
  "superseded",
  "closed",
  "recovery_required"
] as const
export type WorkpaperSyncRoomState = (typeof WP_SYNC_ROOM_STATES)[number]

export const WP_SYNC_RECOVERY_CASE_STATES = [
  "unclaimed",
  "claiming",
  "application_created",
  "download_only",
  "quarantined",
  "expired"
] as const
export type WorkpaperSyncRecoveryCaseState = (typeof WP_SYNC_RECOVERY_CASE_STATES)[number]

export const WP_SYNC_RECOVERY_REASONS = [
  "missing_request",
  "ambiguous_close",
  "crash_close",
  "stale_candidate"
] as const
export type WorkpaperSyncRecoveryReason = (typeof WP_SYNC_RECOVERY_REASONS)[number]

export const WP_SYNC_AUTHORITY_MODELS = [
  "projection_contract",
  "custom_authoritative_ooxml",
  "opaque_single_onlyoffice"
] as const
export type WorkpaperSyncAuthorityModel = (typeof WP_SYNC_AUTHORITY_MODELS)[number]

/**
 * operation 的 terminal 状态（出边为空）。前端用它判「还要不要继续等」。
 * `error` **不在**其中 —— 它可重试（AC 5.8）。
 */
export const WP_SYNC_OPERATION_TERMINAL_STATES = [
  "applied",
  "authorization_stale",
  "duplicate",
  "refresh_required",
  "rejected",
  "superseded"
] as const

/**
 * 服务端 `error_code` → HTTP 状态码的**唯一**映射（`classify_materialize_rejection`）。
 * 未登记的 error_code 一律 fail visible，不得兜底成 4xx。
 */
export const WP_SYNC_REJECTION_STATUS: Readonly<Record<string, number>> = {
  "definition_bundle_not_approved": 422,
  "definition_upgrade_changed_revision": 422,
  "entry_not_materializable": 422,
  "flush_advanced_content_revision": 500,
  "launch_descriptor_incomplete": 422,
  "launch_descriptor_stale_identity": 409,
  "launch_descriptor_substrate_stale": 409,
  "materialize_authorization_denied": 403,
  "materialize_idempotency_key_mismatch": 409,
  "materialize_not_single_commit": 500,
  "materialize_revision_delta_mismatch": 500,
  "materialize_revision_target_mismatch": 500,
  "materialize_scope_not_visible": 404,
  "materialize_substrate_not_published": 422,
  "pending_mutation_token_expired": 409,
  "pending_mutation_token_payload_mismatch": 409,
  "pending_mutation_token_required": 409,
  "pending_mutation_token_revision_mismatch": 409,
  "pending_mutation_token_scope_mismatch": 409,
  "pending_mutation_token_signature_invalid": 409,
  "pending_mutation_token_state_invalid": 409,
  "per_entry_contract_required": 422,
  "representation_still_candidate": 422
} as const
