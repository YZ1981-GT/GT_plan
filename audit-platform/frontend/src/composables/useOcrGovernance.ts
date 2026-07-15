/**
 * useOcrGovernance — OCR 治理 API composable（Task 5.5, Wave 4）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * Requirements: R5, R6, R12, R14
 * Design: §6.2 主要端点 (OCR row)
 *
 * 提供：
 *  - 提交 OCR 任务
 *  - 查询任务详情与时间线
 *  - 重试失败任务
 *  - 获取 OCR 结果
 *  - 添加/查询字段确认
 *  - 执行写回
 *  - 预览映射
 *  - 基于角色的 UI 状态（按钮禁用等）
 */

import { ref, computed, type Ref } from 'vue'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface OcrJob {
  id: string
  project_id: string
  audit_year: number
  attachment_id: string
  attachment_version_id: string
  content_hash: string
  parse_config: Record<string, unknown> | null
  parse_config_version: string | null
  state: OcrJobState
  progress: number
  attempt_count: number
  max_attempts: number
  idempotency_key: string
  error_code: string | null
  error_message: string | null
  created_at: string
  updated_at: string | null
}

export type OcrJobState =
  | 'queued'
  | 'running'
  | 'awaiting_confirmation'
  | 'confirmed'
  | 'written_back'
  | 'failed'

export interface OcrTransition {
  id: string
  from_state: string | null
  to_state: string
  actor_type: string
  error_code: string | null
  error_message: string | null
  created_at: string
}

export interface OcrTimeline {
  job_id: string
  transitions: OcrTransition[]
}

export interface OcrResult {
  id: string
  ocr_job_id: string
  raw_text: string | null
  pages: unknown[] | null
  fields: Record<string, unknown> | null
  confidence: number | null
  engine: string | null
  model_version: string | null
  config_version: string | null
  result_hash: string | null
  created_at: string
}

export interface OcrConfirmation {
  id: string
  field_name: string
  decision: 'accepted' | 'corrected' | 'rejected'
  original_value: string | null
  confirmed_value: string | null
  actor_type: string
  reason: string | null
  created_at: string
}

export interface OcrMapping {
  result_id: string
  mapping: Record<string, string> | null
  all_required_decided: boolean
  ready_for_writeback: boolean
}

export interface WritebackResult {
  writeback_id: string
  status: string
  fields_written: number
  command_root_id: string
}

export interface SubmitJobParams {
  attachment_id: string
  attachment_version_id: string
  content_hash: string
  parse_config?: Record<string, unknown>
  parse_config_version?: string
  max_attempts?: number
}

export interface AddConfirmationParams {
  field_name: string
  decision: 'accepted' | 'corrected' | 'rejected'
  confirmed_value?: string
  reason?: string
}

export interface ExecuteWritebackParams {
  target_type: string
  target_id: string
  target_version?: number
  idempotency_key: string
}

// ─── Role Capability Constants ───────────────────────────────────────────────

/** Roles that can start OCR (ocr.start) */
const OCR_START_ROLES = new Set(['auditor', 'manager', 'partner', 'admin'])
/** Roles that can retry OCR (ocr.retry) */
const OCR_RETRY_ROLES = new Set(['manager', 'partner', 'admin'])
/** Roles that can confirm (ocr.confirm) — human only */
const OCR_CONFIRM_ROLES = new Set(['auditor', 'manager', 'partner', 'admin'])
/** Roles that can writeback (ocr.writeback) — human only */
const OCR_WRITEBACK_ROLES = new Set(['auditor', 'manager', 'partner', 'admin'])

// ─── Composable ──────────────────────────────────────────────────────────────

export function useOcrGovernance(
  projectId: Ref<string> | string,
  year: Ref<number> | number,
  userRole: Ref<string> | string,
) {
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Reactively resolve refs
  const _pid = computed(() => (typeof projectId === 'string' ? projectId : projectId.value))
  const _year = computed(() => (typeof year === 'number' ? year : year.value))
  const _role = computed(() => (typeof userRole === 'string' ? userRole : userRole.value))

  const basePath = computed(
    () => `/api/projects/${_pid.value}/years/${_year.value}/evidence/ocr`
  )

  // ─── Capability Computed ─────────────────────────────────────────────

  const canStartOcr = computed(() => OCR_START_ROLES.has(_role.value))
  const canRetryOcr = computed(() => OCR_RETRY_ROLES.has(_role.value))
  const canConfirmOcr = computed(() => OCR_CONFIRM_ROLES.has(_role.value))
  const canWritebackOcr = computed(() => OCR_WRITEBACK_ROLES.has(_role.value))

  // ─── API Methods ─────────────────────────────────────────────────────

  async function submitJob(params: SubmitJobParams): Promise<{ job: OcrJob; created: boolean } | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.post(`${basePath.value}/jobs`, params)
      return res.data?.data ?? res.data
    } catch (e: any) {
      error.value = e?.response?.data?.message || e?.message || '提交 OCR 任务失败'
      return null
    } finally {
      loading.value = false
    }
  }

  async function getJob(jobId: string): Promise<OcrJob | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(`${basePath.value}/jobs/${jobId}`)
      return res.data?.data ?? res.data
    } catch (e: any) {
      error.value = e?.response?.data?.message || e?.message || '获取任务详情失败'
      return null
    } finally {
      loading.value = false
    }
  }

  async function retryJob(jobId: string): Promise<{ job: OcrJob } | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.post(`${basePath.value}/jobs/${jobId}/retry`)
      return res.data?.data ?? res.data
    } catch (e: any) {
      error.value = e?.response?.data?.message || e?.message || '重试任务失败'
      return null
    } finally {
      loading.value = false
    }
  }

  async function getTimeline(jobId: string): Promise<OcrTimeline | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(`${basePath.value}/jobs/${jobId}/timeline`)
      return res.data?.data ?? res.data
    } catch (e: any) {
      error.value = e?.response?.data?.message || e?.message || '获取时间线失败'
      return null
    } finally {
      loading.value = false
    }
  }

  async function getResult(jobId: string, resultId: string): Promise<OcrResult | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(`${basePath.value}/jobs/${jobId}/results/${resultId}`)
      return res.data?.data ?? res.data
    } catch (e: any) {
      error.value = e?.response?.data?.message || e?.message || '获取 OCR 结果失败'
      return null
    } finally {
      loading.value = false
    }
  }

  async function addConfirmation(
    jobId: string,
    resultId: string,
    params: AddConfirmationParams,
  ): Promise<OcrConfirmation | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.put(
        `${basePath.value}/jobs/${jobId}/results/${resultId}/confirmations`,
        params,
      )
      return res.data?.data ?? res.data
    } catch (e: any) {
      error.value = e?.response?.data?.message || e?.message || '添加确认失败'
      return null
    } finally {
      loading.value = false
    }
  }

  async function listConfirmations(
    jobId: string,
    resultId: string,
  ): Promise<{ confirmations: OcrConfirmation[] } | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(
        `${basePath.value}/jobs/${jobId}/results/${resultId}/confirmations`,
      )
      return res.data?.data ?? res.data
    } catch (e: any) {
      error.value = e?.response?.data?.message || e?.message || '获取确认列表失败'
      return null
    } finally {
      loading.value = false
    }
  }

  async function executeWriteback(
    jobId: string,
    resultId: string,
    params: ExecuteWritebackParams,
  ): Promise<WritebackResult | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.post(
        `${basePath.value}/jobs/${jobId}/results/${resultId}/writeback`,
        { target_type: params.target_type, target_id: params.target_id, target_version: params.target_version },
        { headers: { 'Idempotency-Key': params.idempotency_key } },
      )
      return res.data?.data ?? res.data
    } catch (e: any) {
      if (e?.response?.status === 409) {
        error.value = '版本冲突，目标已被修改'
      } else {
        error.value = e?.response?.data?.message || e?.message || '执行写回失败'
      }
      return null
    } finally {
      loading.value = false
    }
  }

  async function previewMapping(jobId: string, resultId: string): Promise<OcrMapping | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(
        `${basePath.value}/jobs/${jobId}/results/${resultId}/mapping`,
      )
      return res.data?.data ?? res.data
    } catch (e: any) {
      error.value = e?.response?.data?.message || e?.message || '获取映射预览失败'
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    // State
    loading,
    error,

    // Capability computed
    canStartOcr,
    canRetryOcr,
    canConfirmOcr,
    canWritebackOcr,

    // Methods
    submitJob,
    getJob,
    retryJob,
    getTimeline,
    getResult,
    addConfirmation,
    listConfirmations,
    executeWriteback,
    previewMapping,
  }
}
