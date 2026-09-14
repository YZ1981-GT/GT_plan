/**
 * formulaRuntimeContract.ts — 前端公式运行时 API 契约类型
 *
 * 严格对齐后端 `backend/app/schemas/formula_runtime.py` Pydantic 模型。
 * Task 16 (formula-runtime-convergence) 独占新建。
 *
 * 导出：
 * - DraftRefreshRequest / DraftRefreshResponse / RollbackResponse / PresetApplication
 * - parseDraftRefreshResponse(raw): 运行时校验解析
 * - isSuccess / isPartialSuccess / isFailed / isIdempotentHit: 状态分类助手
 */

// ─── Types ─────────────────────────────────────────────────────────────────────

export interface PresetApplication {
  preset_count: number
  presetted_pages: string[]
  pending_pages: string[]
}

export interface DraftRefreshRequest {
  project_id: string
  year: number
  scopes: string[]
  transaction_mode: 'all_or_nothing' | 'partial_success'
  idempotency_key?: string
  confirm_overwrite?: boolean
}

export interface DraftRefreshResponse {
  status: 'success' | 'partial_success' | 'idempotent_hit' | 'failed'
  run_id: string
  transaction_mode: 'all_or_nothing' | 'partial_success'
  affected_count: number
  applied_count: number
  failed_count: number
  skipped_count: number
  scopes: string[]
  idempotent: boolean
  rollback_available: boolean
  warnings: string[]
  failures: string[]
  preset_application: PresetApplication
}

export interface RollbackResponse {
  status: 'rolled_back' | 'failed'
  run_id: string
  restored_count: number
  conflicts: string[]
  error: string | null
}

// ─── Status classification helpers ─────────────────────────────────────────────

const VALID_STATUSES = ['success', 'partial_success', 'idempotent_hit', 'failed'] as const

export function isSuccess(resp: DraftRefreshResponse): boolean {
  return resp.status === 'success'
}

export function isPartialSuccess(resp: DraftRefreshResponse): boolean {
  return resp.status === 'partial_success'
}

export function isFailed(resp: DraftRefreshResponse): boolean {
  return resp.status === 'failed'
}

export function isIdempotentHit(resp: DraftRefreshResponse): boolean {
  return resp.status === 'idempotent_hit'
}

// ─── Runtime parser ────────────────────────────────────────────────────────────

/**
 * 从未知 raw 数据解析为 DraftRefreshResponse，带运行时校验。
 * 容错处理：缺失字段补默认值；status 不合法时抛错。
 */
export function parseDraftRefreshResponse(raw: unknown): DraftRefreshResponse {
  if (!raw || typeof raw !== 'object') {
    throw new Error('parseDraftRefreshResponse: input must be a non-null object')
  }

  const obj = raw as Record<string, unknown>

  // status 必须存在且合法
  const status = obj.status as string
  if (!status || !(VALID_STATUSES as readonly string[]).includes(status)) {
    throw new Error(`parseDraftRefreshResponse: invalid status "${status}"`)
  }

  // run_id 必须存在
  const run_id = typeof obj.run_id === 'string' ? obj.run_id : ''
  if (!run_id) {
    throw new Error('parseDraftRefreshResponse: missing run_id')
  }

  // transaction_mode
  const transaction_mode =
    obj.transaction_mode === 'partial_success' ? 'partial_success' : 'all_or_nothing'

  // Numeric fields — fallback to 0
  const affected_count = typeof obj.affected_count === 'number' ? obj.affected_count : 0
  const applied_count = typeof obj.applied_count === 'number' ? obj.applied_count : 0
  const failed_count = typeof obj.failed_count === 'number' ? obj.failed_count : 0
  const skipped_count = typeof obj.skipped_count === 'number' ? obj.skipped_count : 0

  // Array fields — fallback to []
  const scopes = Array.isArray(obj.scopes) ? (obj.scopes as string[]) : []
  const warnings = Array.isArray(obj.warnings) ? (obj.warnings as string[]) : []
  const failures = Array.isArray(obj.failures) ? (obj.failures as string[]) : []

  // Boolean fields
  const idempotent = obj.idempotent === true
  const rollback_available = obj.rollback_available !== false // default true

  // preset_application — nested object
  const pa = obj.preset_application as Record<string, unknown> | null | undefined
  const preset_application: PresetApplication = {
    preset_count: typeof pa?.preset_count === 'number' ? pa.preset_count : 0,
    presetted_pages: Array.isArray(pa?.presetted_pages) ? (pa.presetted_pages as string[]) : [],
    pending_pages: Array.isArray(pa?.pending_pages) ? (pa.pending_pages as string[]) : [],
  }

  return {
    status: status as DraftRefreshResponse['status'],
    run_id,
    transaction_mode,
    affected_count,
    applied_count,
    failed_count,
    skipped_count,
    scopes,
    idempotent,
    rollback_available,
    warnings,
    failures,
    preset_application,
  }
}
