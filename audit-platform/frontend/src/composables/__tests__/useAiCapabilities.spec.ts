/**
 * useAiCapabilities — AI 引擎能力门控守卫（Task 30）
 *
 * Feature: dsh-agent-panel-integration / Task 30
 * Validates: Requirements 10.1, 10.3, 10.4, 10.5, 12.1, 12.2, 12.4
 * Properties: 24 (引擎能力与 UI 一致), 25 (DSH 失败不降级)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'

// Mock http module — factory must not reference outer scope variables
vi.mock('@/utils/http', () => ({
  default: { get: vi.fn() },
}))

import { useAiCapabilities, type CapabilityResponse } from '../useAiCapabilities'
import http from '@/utils/http'

const mockGet = http.get as ReturnType<typeof vi.fn>

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeNativeResponse(): CapabilityResponse {
  return {
    engine: 'native',
    capabilities: {
      streaming: true,
      tools: false,
      subagents: false,
      max_context: 32768,
      structured_output: false,
      local_only: true,
      review_mode: true,
      attachments: true,
    },
    gate_reason: null,
    disabled_reasons: {
      tools: '当前引擎不支持工具调用，切换到 DSH 多步 Agent 后可用。',
      subagents: '当前引擎不支持子 Agent，切换到 DSH 多步 Agent 后可用。',
    },
    health: {
      model: { available: true, endpoint: 'http://localhost:8100', error_code: null, message: '本地模型可用。' },
      embedding: { available: true, endpoint: 'http://localhost:8101', error_code: null, message: '本地 Embedding 服务可用。' },
      ocr: { available: true, endpoint: 'localhost:8200', error_code: null, message: 'OCR 服务已配置。' },
    },
  }
}

function makeDshResponse(): CapabilityResponse {
  return {
    engine: 'dsh',
    capabilities: {
      streaming: true,
      tools: true,
      subagents: true,
      max_context: 32768,
      structured_output: true,
      local_only: true,
      review_mode: true,
      attachments: true,
    },
    gate_reason: null,
    disabled_reasons: {},
    health: {
      model: { available: true, endpoint: 'http://localhost:8100', error_code: null, message: '本地模型可用。' },
      embedding: { available: true, endpoint: 'http://localhost:8101', error_code: null, message: '' },
      ocr: { available: true, endpoint: 'localhost:8200', error_code: null, message: '' },
      mcp: { available: true, endpoint: 'stdio (per-run)', error_code: null, message: 'MCP stdio server 可用。' },
    },
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useAiCapabilities', () => {
  beforeEach(() => {
    mockGet.mockReset()
  })

  describe('Property 24: 引擎能力与 UI 一致', () => {
    it('native 引擎时 toolsEnabled=false, subagentsEnabled=false', async () => {
      mockGet.mockResolvedValueOnce({ data: makeNativeResponse() })

      const { toolsEnabled, subagentsEnabled, loadCapabilities } =
        useAiCapabilities({ autoLoad: false })

      await loadCapabilities()

      expect(toolsEnabled.value).toBe(false)
      expect(subagentsEnabled.value).toBe(false)
    })

    it('native 引擎时提供中文禁用原因', async () => {
      mockGet.mockResolvedValueOnce({ data: makeNativeResponse() })

      const { toolsDisabledReason, subagentsDisabledReason, loadCapabilities } =
        useAiCapabilities({ autoLoad: false })

      await loadCapabilities()

      expect(toolsDisabledReason.value).toContain('工具调用')
      expect(subagentsDisabledReason.value).toContain('子 Agent')
    })

    it('DSH 引擎时 toolsEnabled=true, subagentsEnabled=true', async () => {
      mockGet.mockResolvedValueOnce({ data: makeDshResponse() })

      const { toolsEnabled, subagentsEnabled, loadCapabilities } =
        useAiCapabilities({ autoLoad: false })

      await loadCapabilities()

      expect(toolsEnabled.value).toBe(true)
      expect(subagentsEnabled.value).toBe(true)
    })

    it('DSH 引擎时无禁用原因', async () => {
      mockGet.mockResolvedValueOnce({ data: makeDshResponse() })

      const { toolsDisabledReason, subagentsDisabledReason, loadCapabilities } =
        useAiCapabilities({ autoLoad: false })

      await loadCapabilities()

      expect(toolsDisabledReason.value).toBe('')
      expect(subagentsDisabledReason.value).toBe('')
    })

    it('请求参数不含 engine 字段（客户端不可覆盖）', async () => {
      mockGet.mockResolvedValueOnce({ data: makeNativeResponse() })

      const { loadCapabilities } = useAiCapabilities({ autoLoad: false })
      await loadCapabilities()

      const [url, options] = mockGet.mock.calls[0]
      expect(url).toBe('/api/ai-chat/capabilities')
      // 参数里不应有 engine
      const params = options?.params || {}
      expect(params).not.toHaveProperty('engine')
    })
  })

  describe('fail-closed: 查询失败时禁用危险能力', () => {
    it('网络错误时 tools/subagents 被禁用', async () => {
      mockGet.mockRejectedValueOnce(new Error('network error'))

      const { toolsEnabled, subagentsEnabled, loadCapabilities, error } =
        useAiCapabilities({ autoLoad: false })

      await loadCapabilities()

      expect(toolsEnabled.value).toBe(false)
      expect(subagentsEnabled.value).toBe(false)
      expect(error.value).toBeTruthy()
    })

    it('网络错误时有中文禁用原因', async () => {
      mockGet.mockRejectedValueOnce(new Error('timeout'))

      const { toolsDisabledReason, subagentsDisabledReason, loadCapabilities } =
        useAiCapabilities({ autoLoad: false })

      await loadCapabilities()

      expect(toolsDisabledReason.value).toContain('不可用')
      expect(subagentsDisabledReason.value).toContain('不可用')
    })
  })

  describe('DSH gate reason 传递', () => {
    it('DSH 被门拦下时 gateReason 为中文', async () => {
      const response = makeNativeResponse()
      response.gate_reason = 'DSH 多步 Agent 尚未对当前项目开放，本次使用平台原生引擎。'
      mockGet.mockResolvedValueOnce({ data: response })

      const { dshGateReason, isDsh, loadCapabilities } =
        useAiCapabilities({ autoLoad: false })

      await loadCapabilities()

      expect(isDsh.value).toBe(false)
      expect(dshGateReason.value).toContain('尚未')
    })
  })

  describe('服务健康独立上报', () => {
    it('各服务健康状态独立（Req 12.4）', async () => {
      const response = makeNativeResponse()
      response.health.embedding = {
        available: false,
        endpoint: 'https://api.openai.com',
        error_code: 'local_only_violation',
        message: 'Embedding 路由不合规',
      }
      mockGet.mockResolvedValueOnce({ data: response })

      const { health, allServicesHealthy, loadCapabilities } =
        useAiCapabilities({ autoLoad: false })

      await loadCapabilities()

      expect(health.value.model.available).toBe(true)
      expect(health.value.embedding.available).toBe(false)
      expect(health.value.embedding.error_code).toBe('local_only_violation')
      expect(allServicesHealthy.value).toBe(false)
    })
  })

  describe('checkCapability 辅助', () => {
    it('支持的能力返回空字符串', async () => {
      mockGet.mockResolvedValueOnce({ data: makeNativeResponse() })

      const { checkCapability, loadCapabilities } =
        useAiCapabilities({ autoLoad: false })

      await loadCapabilities()

      expect(checkCapability('streaming')).toBe('')
      expect(checkCapability('attachments')).toBe('')
    })

    it('不支持的能力返回中文原因', async () => {
      mockGet.mockResolvedValueOnce({ data: makeNativeResponse() })

      const { checkCapability, loadCapabilities } =
        useAiCapabilities({ autoLoad: false })

      await loadCapabilities()

      const reason = checkCapability('tools')
      expect(reason.length).toBeGreaterThan(0)
      // 应为中文
      expect(/[\u4e00-\u9fff]/.test(reason)).toBe(true)
    })
  })

  describe('projectId 传递', () => {
    it('传入 projectId 时作为 query param 发送', async () => {
      mockGet.mockResolvedValueOnce({ data: makeNativeResponse() })
      const projectId = 'abc-def-123'

      const { loadCapabilities } =
        useAiCapabilities({ projectId, autoLoad: false })

      await loadCapabilities()

      const [, options] = mockGet.mock.calls[0]
      expect(options?.params?.project_id).toBe(projectId)
    })

    it('支持 Ref<string> 类型的 projectId', async () => {
      mockGet.mockResolvedValueOnce({ data: makeNativeResponse() })
      const projectId = ref('reactive-project-id')

      const { loadCapabilities } =
        useAiCapabilities({ projectId, autoLoad: false })

      await loadCapabilities()

      const [, options] = mockGet.mock.calls[0]
      expect(options?.params?.project_id).toBe('reactive-project-id')
    })
  })
})
