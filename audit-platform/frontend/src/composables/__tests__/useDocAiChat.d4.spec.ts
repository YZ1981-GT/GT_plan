/**
 * D4 确认流门禁 — Property-Based Test
 *
 * **Validates: Requirements 4.1, 4.3**
 * 属性 D4: AI 生成内容回写前必经 AIContentMustBeConfirmedRule（pending 状态）
 *
 * 验证：
 * 1. adoptContent 对任意有效消息都必须调用 /api/ai-chat/adopt 端点
 * 2. adopt 端点调用时必须携带 doc_type/doc_id/project_id/content/message_id
 * 3. AI 内容不会绕过 adopt 端点直接写入文档
 * 4. handleAdopt 只在 API 成功时才 emit adopt 事件（确认流门禁）
 */

import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import * as fc from 'fast-check'
import { useDocAiChat } from '../useDocAiChat'

// Mock auth store
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    token: 'test-token',
    user: { id: 'user-1' },
  }),
}))

// Mock fetch
const mockFetch = vi.fn()
global.fetch = mockFetch

// Mock localStorage
const localStorageData: Record<string, string> = {}
const mockLocalStorage = {
  getItem: vi.fn((key: string) => localStorageData[key] || null),
  setItem: vi.fn((key: string, value: string) => { localStorageData[key] = value }),
  removeItem: vi.fn((key: string) => { delete localStorageData[key] }),
  clear: vi.fn(),
  get length() { return Object.keys(localStorageData).length },
  key: vi.fn((i: number) => Object.keys(localStorageData)[i] || null),
}
Object.defineProperty(global, 'localStorage', { value: mockLocalStorage })

// 使用安全的 ID 生成策略（避免特殊字符干扰 cache key）
const safeIdArb = fc.stringMatching(/^[a-z0-9]{1,20}$/)
const safeContentArb = fc.string({ minLength: 1, maxLength: 100 }).filter(s => s.trim().length > 0)

describe('D4 确认流门禁 — PBT', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.keys(localStorageData).forEach(k => delete localStorageData[k])
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({ messages: [] }) })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('D4: adoptContent 对任意有效消息必调用 /api/ai-chat/adopt 端点', async () => {
    /**
     * **Validates: Requirements 4.1**
     * 属性 D4: 对任意 docType/docId/projectId 组合和任意消息内容，
     * adoptContent 必须发起 POST /api/ai-chat/adopt 请求，
     * 确保 AI 内容走确认流而非直接写入。
     */
    await fc.assert(
      fc.asyncProperty(
        fc.constantFrom('workpaper', 'note', 'report', 'knowledge_folder'),
        safeIdArb,
        safeIdArb,
        fc.integer({ min: 2020, max: 2030 }),
        safeContentArb,
        safeIdArb,
        async (docType, docId, projectId, year, content, messageId) => {
          // 清理状态
          Object.keys(localStorageData).forEach(k => delete localStorageData[k])
          mockFetch.mockReset()
          mockFetch.mockResolvedValue({ ok: true })

          // 预设消息到本地缓存
          const cacheKey = `doc_ai_chat_${docType}_${docId}`
          localStorageData[cacheKey] = JSON.stringify([
            { id: messageId, role: 'assistant', text: content, citations: [] },
          ])

          const { adoptContent } = useDocAiChat({ docType, docId, projectId, year })
          const result = await adoptContent(messageId)

          // D4 核心断言：必须调用 adopt 端点
          expect(mockFetch).toHaveBeenCalledWith(
            '/api/ai-chat/adopt',
            expect.objectContaining({ method: 'POST' }),
          )

          // D4 核心断言：请求体包含必要字段
          const callArgs = mockFetch.mock.calls[0]
          const body = JSON.parse(callArgs[1].body)
          expect(body.doc_type).toBe(docType)
          expect(body.doc_id).toBe(docId)
          expect(body.project_id).toBe(projectId)
          expect(body.content).toBe(content)
          expect(body.message_id).toBe(messageId)

          // D4 核心断言：返回成功
          expect(result.success).toBe(true)
        },
      ),
      { numRuns: 15 },
    )
  })

  it('D4: adoptContent 不存在的消息不会调用 adopt 端点（不会误写）', async () => {
    /**
     * **Validates: Requirements 4.3**
     * 属性 D4: 对不存在的 messageId，adoptContent 不发起请求，
     * 确保不会误将无效内容写入确认流。
     */
    await fc.assert(
      fc.asyncProperty(
        fc.constantFrom('workpaper', 'note', 'report', 'knowledge_folder'),
        safeIdArb,
        safeIdArb,
        async (docType, docId, messageId) => {
          // 清理状态
          Object.keys(localStorageData).forEach(k => delete localStorageData[k])
          mockFetch.mockReset()
          mockFetch.mockResolvedValue({ ok: true })

          // 空消息列表 — messageId 不存在
          const cacheKey = `doc_ai_chat_${docType}_${docId}`
          localStorageData[cacheKey] = JSON.stringify([
            { id: 'other_msg_id_xyz', role: 'assistant', text: 'some text', citations: [] },
          ])

          const { adoptContent } = useDocAiChat({
            docType,
            docId,
            projectId: 'proj1',
            year: 2025,
          })

          // 使用一个保证不存在的 messageId
          const nonExistentId = `nonexistent_${messageId}_${Date.now()}`
          const result = await adoptContent(nonExistentId)

          // D4: 不存在的消息不应调用 API
          expect(mockFetch).not.toHaveBeenCalled()
          expect(result.success).toBe(false)
        },
      ),
      { numRuns: 15 },
    )
  })

  it('D4: adopt 端点失败时 adoptContent 返回 failure（不会假装成功）', async () => {
    /**
     * **Validates: Requirements 4.1, 4.3**
     * 属性 D4: 当 adopt 端点返回非 ok 状态时，adoptContent 返回 { success: false }，
     * 确保确认流失败时不会误认为内容已被接受。
     */
    await fc.assert(
      fc.asyncProperty(
        fc.constantFrom('workpaper', 'note', 'report', 'knowledge_folder'),
        safeIdArb,
        safeContentArb,
        fc.constantFrom(400, 401, 403, 500, 502, 503),
        async (docType, docId, content, statusCode) => {
          // 清理状态
          Object.keys(localStorageData).forEach(k => delete localStorageData[k])
          mockFetch.mockReset()
          mockFetch.mockResolvedValue({ ok: false, status: statusCode })

          const msgId = 'msg_fail_test'
          const cacheKey = `doc_ai_chat_${docType}_${docId}`
          localStorageData[cacheKey] = JSON.stringify([
            { id: msgId, role: 'assistant', text: content, citations: [] },
          ])

          const { adoptContent } = useDocAiChat({
            docType,
            docId,
            projectId: 'proj1',
            year: 2025,
          })
          const result = await adoptContent(msgId)

          // D4: 端点失败时必须返回 failure
          expect(result.success).toBe(false)
        },
      ),
      { numRuns: 12 },
    )
  })
})
