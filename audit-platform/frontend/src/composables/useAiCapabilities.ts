/**
 * useAiCapabilities — AI 引擎能力查询与 UI 禁用门控（Task 30）
 *
 * 前端据 /api/ai-chat/capabilities 禁用不支持的入口并显示中文原因（Req 10.4）。
 * 不手写第二份能力常量 —— 单一真源在服务端 CAPABILITIES_BY_ENGINE。
 *
 * Feature: dsh-agent-panel-integration / Task 30
 * Validates: Requirements 10.1, 10.3, 10.4, 10.5, 10.6, 12.1, 12.2, 12.4
 * Properties: 24 (引擎能力与 UI 一致), 25 (DSH 失败不降级), 26 (Effective Cordis 受控)
 */

import { ref, computed, type Ref } from 'vue'
import http from '@/utils/http'

// ---------------------------------------------------------------------------
// Types (从服务端 capability_endpoint.py 投影)
// ---------------------------------------------------------------------------

/** 引擎能力 manifest（与后端 EngineCapabilities 对应） */
export interface EngineCapabilities {
  streaming: boolean
  tools: boolean
  subagents: boolean
  max_context: number
  structured_output: boolean
  local_only: boolean
  review_mode: boolean
  attachments: boolean
}

/** 单个服务健康状态 */
export interface ServiceHealth {
  available: boolean
  endpoint: string
  error_code: string | null
  message: string
}

/** GET /api/ai-chat/capabilities 完整响应 */
export interface CapabilityResponse {
  engine: string
  capabilities: EngineCapabilities
  gate_reason: string | null
  disabled_reasons: Record<string, string>
  health: Record<string, ServiceHealth>
}

// ---------------------------------------------------------------------------
// Safe defaults (fail-closed: 全部 false → 入口禁用)
// ---------------------------------------------------------------------------

const SAFE_DEFAULTS: EngineCapabilities = {
  streaming: true,
  tools: false,
  subagents: false,
  max_context: 32768,
  structured_output: false,
  local_only: true,
  review_mode: false,
  attachments: false,
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export interface UseAiCapabilitiesOptions {
  /** 可选项目 ID（精确判断 DSH allowlist） */
  projectId?: string | Ref<string | undefined>
  /** 是否组件挂载时自动加载 */
  autoLoad?: boolean
}

export function useAiCapabilities(options: UseAiCapabilitiesOptions = {}) {
  const capabilities = ref<EngineCapabilities>({ ...SAFE_DEFAULTS })
  const engine = ref<string>('native')
  const gateReason = ref<string | null>(null)
  const disabledReasons = ref<Record<string, string>>({})
  const health = ref<Record<string, ServiceHealth>>({})
  const loading = ref(false)
  const error = ref<string | null>(null)

  // ---------------------------------------------------------------------------
  // Computed: 能力门控
  // ---------------------------------------------------------------------------

  /** 工具调用是否可用 */
  const toolsEnabled = computed(() => capabilities.value.tools)

  /** 工具禁用时的中文原因 */
  const toolsDisabledReason = computed(() =>
    disabledReasons.value.tools || ''
  )

  /** 子 Agent 是否可用 */
  const subagentsEnabled = computed(() => capabilities.value.subagents)

  /** 子 Agent 禁用时的中文原因 */
  const subagentsDisabledReason = computed(() =>
    disabledReasons.value.subagents || ''
  )

  /** 复核模式是否可用 */
  const reviewModeEnabled = computed(() => capabilities.value.review_mode)

  /** 附件功能是否可用 */
  const attachmentsEnabled = computed(() => capabilities.value.attachments)

  /** 是否使用 DSH 引擎 */
  const isDsh = computed(() => engine.value === 'dsh')

  /** DSH 被门拦下的中文原因（前端展示用） */
  const dshGateReason = computed(() => gateReason.value || '')

  /** 所有服务是否健康 */
  const allServicesHealthy = computed(() =>
    Object.values(health.value).every((h) => h.available)
  )

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  async function loadCapabilities(): Promise<CapabilityResponse | null> {
    loading.value = true
    error.value = null

    try {
      const projectId = options.projectId
        ? (typeof options.projectId === 'object' && 'value' in options.projectId
            ? options.projectId.value
            : options.projectId)
        : undefined

      const params: Record<string, string> = {}
      if (projectId) params.project_id = projectId

      const response = await http.get<CapabilityResponse>(
        '/api/ai-chat/capabilities',
        { params, _silent: true } as any,
      )

      const data = (response as any)?.data ?? response

      if (data && typeof data === 'object') {
        capabilities.value = data.capabilities || { ...SAFE_DEFAULTS }
        engine.value = data.engine || 'native'
        gateReason.value = data.gate_reason || null
        disabledReasons.value = data.disabled_reasons || {}
        health.value = data.health || {}
        return data as CapabilityResponse
      }

      return null
    } catch (e: any) {
      error.value = e?.message || '能力查询失败'
      // fail-closed: 保持 safe defaults（tools/subagents 禁用）
      capabilities.value = { ...SAFE_DEFAULTS }
      disabledReasons.value = {
        tools: '能力查询失败，工具调用暂时不可用。',
        subagents: '能力查询失败，子 Agent 暂时不可用。',
      }
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 检查指定能力是否可用。
   * 不可用时返回中文原因，可用时返回空字符串。
   */
  function checkCapability(field: keyof EngineCapabilities): string {
    const val = capabilities.value[field]
    if (val === true || (typeof val === 'number' && val > 0)) return ''
    return disabledReasons.value[field] || `${field} 不可用`
  }

  // 自动加载
  if (options.autoLoad !== false) {
    loadCapabilities()
  }

  return {
    // State
    capabilities,
    engine,
    gateReason,
    disabledReasons,
    health,
    loading,
    error,
    // Computed gates
    toolsEnabled,
    toolsDisabledReason,
    subagentsEnabled,
    subagentsDisabledReason,
    reviewModeEnabled,
    attachmentsEnabled,
    isDsh,
    dshGateReason,
    allServicesHealthy,
    // Actions
    loadCapabilities,
    checkCapability,
  }
}
