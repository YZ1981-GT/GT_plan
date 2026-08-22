/**
 * D4 确认流门禁 — Property-Based Test
 *
 * **Validates: Requirements 4.1, 4.3**
 * 属性 D4: AI 生成内容回写前必经 AIContentMustBeConfirmedRule（pending 状态）
 *
 * 验证：
 * 1. adoptContent 对任意**服务端签发**的消息 ID 都必须调用 /api/ai-chat/adopt 端点
 * 2. adopt 请求只携带 message_id / host / idempotency_key，**绝不携带正文**
 * 3. AI 内容不会绕过 adopt 端点直接写入文档
 * 4. handleAdopt 只在 API 成功时才 emit adopt 事件（确认流门禁）
 *
 * dsh-agent-panel-integration / Task 2：宿主入参从"四个松散标量"改为由
 * `useAiHostContext` 的宿主 adapter 构造的 `AiHostRequest`。生成器随之改为**按宿主类型
 * 生成合法稳定标识**（底稿/附注/文件夹是 UUID，报表是 report type），
 * 这本身也是一条判据：随机伪 ID 不再可能被 composable 提交出去。
 *
 * dsh-agent-panel-integration / Task 7（Req 8.1/8.6）：正文不再随请求提交 ——
 * 服务端按 message ID 从 `ai_chat_message` 读权威正文。于是消息 ID 生成器从
 * "任意短字符串"改为 **UUID**（服务端签发形态），并新增一条属性：任意本地占位 ID
 * （`ai_…` / `user_…` / `hist_N`）都不得被提交出去。
 */

import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import * as fc from 'fast-check'
import { useDocAiChat } from '../useDocAiChat'
import {
  AI_REPORT_HOST_IDS,
  buildKnowledgeFolderHost,
  buildNoteHost,
  buildReportHost,
  buildWorkpaperHost,
  type AiHostRequest,
} from '../useAiHostContext'

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

const safeContentArb = fc.string({ minLength: 1, maxLength: 100 }).filter(s => s.trim().length > 0)
/**
 * 带**唯一标记前缀**的正文。
 *
 * 🔴 判"请求体里没有正文"不能直接拿随机正文做 substring 比对：单字符正文（如 `,`）
 * 必然出现在任何 JSON 里，判据会假红；带引号的正文又会被 JSON 转义，判据会假绿。
 * 用一个绝不可能出现在合法请求体里的标记前缀，两种假象一起消掉。
 */
const BODY_MARKER = '仅存在于正文中的标记UNIQ7'
const markedContentArb = safeContentArb.map((s) => `${BODY_MARKER}${s}`)
/** 服务端签发的消息 ID 形态（Task 7 起采纳只接受它）。 */
const serverMsgIdArb = fc.uuid()
/** 本地占位 ID 形态（流式刚生成 / 历史回落），采纳必须在发请求前拒绝。 */
const localPlaceholderIdArb = fc.oneof(
  fc.integer({ min: 1, max: 9_999_999 }).map((n) => `ai_${n}`),
  fc.integer({ min: 1, max: 9_999_999 }).map((n) => `user_${n}`),
  fc.integer({ min: 0, max: 99 }).map((n) => `hist_${n}`),
  fc.stringMatching(/^[a-z0-9]{1,20}$/),
)

/**
 * 按宿主类型生成**合法**的 HostContext 请求。
 *
 * 每个宿主用自己的稳定标识形态：workpaper/note/knowledge_folder 是 instance UUID，
 * report 是 report type 字面量（报表实例由 project+year+type 确定，没有 instance UUID）。
 */
const hostArb: fc.Arbitrary<AiHostRequest> = fc.oneof(
  fc.record({ wpId: fc.uuid(), projectId: fc.uuid(), auditYear: fc.integer({ min: 2020, max: 2030 }) })
    .map(buildWorkpaperHost),
  fc.record({ noteId: fc.uuid(), projectId: fc.uuid(), year: fc.integer({ min: 2020, max: 2030 }) })
    .map(buildNoteHost),
  fc.record({
    reportType: fc.constantFrom(...AI_REPORT_HOST_IDS),
    projectId: fc.uuid(),
    year: fc.integer({ min: 2020, max: 2030 }),
  }).map(buildReportHost),
  fc.record({ folderId: fc.uuid(), projectId: fc.uuid() }).map(buildKnowledgeFolderHost),
)

function seedCache(host: AiHostRequest, messages: unknown[]): void {
  const ref = host.host!
  localStorageData[`doc_ai_chat_${ref.type}_${ref.id}`] = JSON.stringify(messages)
}

describe('D4 确认流门禁 — PBT', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.keys(localStorageData).forEach(k => delete localStorageData[k])
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({ messages: [] }) })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('D4: adoptContent 对任意服务端消息 ID 必调用 adopt 端点且不提交正文', async () => {
    /**
     * **Validates: Requirements 4.1**
     * 属性 D4: 对任意宿主组合和任意服务端消息 ID，adoptContent 必须发起
     * POST /api/ai-chat/adopt 请求（确保走确认流），且请求体里**不含正文**
     * （Task 7 / Req 8.1：正文由服务端按 ID 读库，客户端无权提供）。
     */
    await fc.assert(
      fc.asyncProperty(
        hostArb,
        markedContentArb,
        serverMsgIdArb,
        async (host, content, messageId) => {
          // 清理状态
          Object.keys(localStorageData).forEach(k => delete localStorageData[k])
          mockFetch.mockReset()
          mockFetch.mockResolvedValue({ ok: true })

          expect(host.available).toBe(true)
          seedCache(host, [{ id: messageId, role: 'assistant', text: content, citations: [] }])

          const { adoptContent } = useDocAiChat({ host })
          const result = await adoptContent(messageId)

          // D4 核心断言：必须调用 adopt 端点
          expect(mockFetch).toHaveBeenCalledWith(
            '/api/ai-chat/adopt',
            expect.objectContaining({ method: 'POST' }),
          )

          // D4 核心断言：只提交 ID / 宿主 / 幂等键；宿主标识是服务端可反查的稳定 ID
          const callArgs = mockFetch.mock.calls[0]
          const body = JSON.parse(callArgs[1].body)
          expect(Object.keys(body).sort()).toEqual(['host', 'idempotency_key', 'message_id'])
          expect(body.message_id).toBe(messageId)
          expect(body.host.type).toBe(host.host!.type)
          expect(body.host.id).toBe(host.host!.id)
          expect(body.host.project_id).toBe(host.host!.projectId)
          expect(body.idempotency_key).toMatch(
            /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[089ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
          )
          // Req 3.5：项目 ID 绝不出现在文档 ID 位置
          expect(body.host.id).not.toBe(body.host.project_id)
          // Req 8.1：正文绝不出现在请求体的任何位置
          expect(body).not.toHaveProperty('content')
          expect(content).toContain(BODY_MARKER)
          expect(JSON.stringify(body)).not.toContain(BODY_MARKER)

          // D4 核心断言：返回成功
          expect(result.success).toBe(true)
        },
      ),
      { numRuns: 15 },
    )
  })

  it('D4: 本地占位 ID 一律在发请求前被拒（不能拿伪 ID 换取确认流记录）', async () => {
    /**
     * **Validates: Requirements 4.1**
     * Task 7 / Req 8.1：采纳只能引用服务端签发的 message ID。流式刚生成的
     * `ai_…` 与历史回落的 `hist_N` 都不是服务端 ID，必须在发请求前拒绝并给出中文原因。
     */
    await fc.assert(
      fc.asyncProperty(
        hostArb,
        safeContentArb,
        localPlaceholderIdArb,
        async (host, content, placeholderId) => {
          Object.keys(localStorageData).forEach(k => delete localStorageData[k])
          mockFetch.mockReset()
          mockFetch.mockResolvedValue({ ok: true })

          seedCache(host, [
            { id: placeholderId, role: 'assistant', text: content, citations: [] },
          ])

          const { adoptContent } = useDocAiChat({ host })
          const result = await adoptContent(placeholderId)

          expect(result.success).toBe(false)
          expect(result.code).toBe('message_id_not_server_issued')
          expect(mockFetch).not.toHaveBeenCalled()
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
        hostArb,
        serverMsgIdArb,
        async (host, messageId) => {
          // 清理状态
          Object.keys(localStorageData).forEach(k => delete localStorageData[k])
          mockFetch.mockReset()
          mockFetch.mockResolvedValue({ ok: true })

          // 缓存里放的是另一条消息（形态合法的服务端 ID，但不是要采纳的那条）
          seedCache(host, [
            { id: messageId, role: 'assistant', text: 'some text', citations: [] },
          ])

          const { adoptContent } = useDocAiChat({ host })

          // 使用一个保证不在缓存里的**合法形态**服务端 ID：
          // 这样"被拒"的原因只能是"消息不存在"，而不是"ID 形态不合法"。
          const absentId = '00000000-0000-4000-8000-0000000000ff'
          expect(absentId).not.toBe(messageId)
          const result = await adoptContent(absentId)

          // D4: 不存在的消息不应调用 API
          expect(mockFetch).not.toHaveBeenCalled()
          expect(result.success).toBe(false)
          expect(result.code).toBe('message_not_found')
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
        hostArb,
        safeContentArb,
        fc.constantFrom(400, 401, 403, 500, 502, 503),
        async (host, content, statusCode) => {
          // 清理状态
          Object.keys(localStorageData).forEach(k => delete localStorageData[k])
          mockFetch.mockReset()
          mockFetch.mockResolvedValue({
            ok: false,
            status: statusCode,
            json: async () => ({
              detail: { code: 'adopt_log_failed', message: '采纳未生效' },
            }),
          })

          const msgId = '11111111-2222-4333-8444-555555555555'
          seedCache(host, [{ id: msgId, role: 'assistant', text: content, citations: [] }])

          const { adoptContent } = useDocAiChat({ host })
          const result = await adoptContent(msgId)

          // D4: 端点失败时必须返回 failure，并带出可执行原因（Req 8.5）
          expect(result.success).toBe(false)
          expect(result.code).toBe('adopt_log_failed')
        },
      ),
      { numRuns: 12 },
    )
  })

  it('D4: 宿主不可用时 adoptContent 不调用 adopt 端点（Task 2 / Req 3.4）', async () => {
    /**
     * **Validates: Requirements 4.3**
     * 宿主未解析（未选定资源 / 无项目上下文）时，即使本地有消息也不得发起采纳请求 ——
     * 否则会发出 doc_id='' / project_id='' 的必然失败调用。
     */
    await fc.assert(
      fc.asyncProperty(
        fc.oneof(
          fc.constant(buildReportHost({ reportType: 'cross_check', projectId: fc.sample(fc.uuid(), 1)[0] })),
          fc.constant(buildWorkpaperHost({ wpId: '', projectId: fc.sample(fc.uuid(), 1)[0] })),
          fc.constant(buildNoteHost({ projectId: '' })),
        ),
        safeContentArb,
        async (host, content) => {
          Object.keys(localStorageData).forEach(k => delete localStorageData[k])
          mockFetch.mockReset()
          mockFetch.mockResolvedValue({ ok: true })

          expect(host.available).toBe(false)
          // 缓存键在宿主未解析时是 unresolved sentinel。消息 ID 用**合法服务端形态**，
          // 这样"不发请求"的原因只能是宿主不可用，而不是 ID 形态被提前拦下。
          const msgId = '22222222-3333-4444-8555-666666666666'
          localStorageData['doc_ai_chat_unresolved'] = JSON.stringify([
            { id: msgId, role: 'assistant', text: content, citations: [] },
          ])

          const { adoptContent } = useDocAiChat({ host })
          const result = await adoptContent(msgId)

          expect(result.success).toBe(false)
          expect(result.code).toBe('host_unavailable')
          expect(mockFetch).not.toHaveBeenCalled()
        },
      ),
      { numRuns: 10 },
    )
  })
})
