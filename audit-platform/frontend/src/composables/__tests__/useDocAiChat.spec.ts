/**
 * useDocAiChat composable 单元测试
 *
 * 验证：
 * 1. 初始化加载本地缓存
 * 2. fetchHistory 拉取服务端历史并缓存
 * 3. sendMessage SSE streaming 接收
 * 4. 离线时拒绝发送新消息
 * 5. clearHistory 清除本地 + 服务端
 * 6. adoptContent 调用采纳端点
 */

import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { useDocAiChat } from '../useDocAiChat'
import { buildWorkpaperHost } from '../useAiHostContext'

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
  clear: vi.fn(() => { Object.keys(localStorageData).forEach(k => delete localStorageData[k]) }),
  get length() { return Object.keys(localStorageData).length },
  key: vi.fn((i: number) => Object.keys(localStorageData)[i] || null),
}
Object.defineProperty(global, 'localStorage', { value: mockLocalStorage })

// Mock navigator.onLine
let mockOnline = true
Object.defineProperty(navigator, 'onLine', { get: () => mockOnline, configurable: true })

// Task 2 起 composable 只接受一个由宿主 adapter 构造的 AiHostRequest（Req 3.5）。
// ID 必须是合法 UUID —— adapter 会拒绝 'wp-001' / 'proj-123' 这类伪 ID 形态。
const WP_ID = '11111111-1111-4111-8111-111111111111'
const PROJECT_ID = '22222222-2222-4222-8222-222222222222'
const CACHE_KEY = `doc_ai_chat_workpaper_${WP_ID}`

const defaultOptions = {
  host: buildWorkpaperHost({ wpId: WP_ID, projectId: PROJECT_ID, auditYear: 2025 }),
}

describe('useDocAiChat', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.keys(localStorageData).forEach(k => delete localStorageData[k])
    mockOnline = true
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({ messages: [] }) })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('初始化时从 localStorage 加载缓存', () => {
    const cachedMessages = [
      { id: '1', role: 'user', text: '测试问题' },
      { id: '2', role: 'assistant', text: '测试回答' },
    ]
    localStorageData[CACHE_KEY] = JSON.stringify(cachedMessages)

    const { messages } = useDocAiChat(defaultOptions)
    expect(messages.value).toEqual(cachedMessages)
  })

  it('初始化时 localStorage 为空则 messages 为空', () => {
    const { messages } = useDocAiChat(defaultOptions)
    expect(messages.value).toEqual([])
  })

  it('fetchHistory 拉取服务端历史并更新 messages（真实信封 {code,message,data}）', async () => {
    const serverMessages = [
      { role: 'user', content: '服务端问题', citations: [] },
      { role: 'assistant', content: '服务端回答', citations: [{ source_type: 'knowledge_doc', source_id: 'kd-1', source_name: '文件1' }] },
    ]
    // 后端 ResponseWrapperMiddleware 会把 2xx 响应包装成 {code,message,data}
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ code: 200, message: 'success', data: { messages: serverMessages, total: 2 } }),
    })

    const { messages, fetchHistory } = useDocAiChat(defaultOptions)
    await fetchHistory()

    expect(messages.value).toHaveLength(2)
    expect(messages.value[0].role).toBe('user')
    expect(messages.value[0].text).toBe('服务端问题')
    expect(messages.value[1].role).toBe('assistant')
    expect(messages.value[1].text).toBe('服务端回答')
    expect(messages.value[1].citations).toHaveLength(1)

    // 验证缓存已保存
    expect(mockLocalStorage.setItem).toHaveBeenCalledWith(
      CACHE_KEY,
      expect.any(String),
    )
  })

  it('fetchHistory 网络失败时静默（使用本地缓存）', async () => {
    const cachedMessages = [{ id: '1', role: 'user', text: '缓存问题' }]
    localStorageData[CACHE_KEY] = JSON.stringify(cachedMessages)

    mockFetch.mockRejectedValueOnce(new Error('Network error'))

    const { messages, fetchHistory } = useDocAiChat(defaultOptions)
    await fetchHistory()

    // 保持本地缓存数据
    expect(messages.value).toEqual(cachedMessages)
  })

  it('sendMessage 发送消息并处理 SSE streaming', async () => {
    // 模拟 SSE 流式响应
    const sseData = [
      'data: {"type":"content","data":"你好"}\n',
      'data: {"type":"content","data":"，世界"}\n',
      'data: {"type":"citations","data":[{"source_type":"knowledge_doc","source_id":"kd-1","source_name":"测试"}]}\n',
      'data: [DONE]\n',
    ].join('\n')

    const encoder = new TextEncoder()
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(sseData))
        controller.close()
      },
    })

    mockFetch.mockResolvedValueOnce({
      ok: true,
      body: stream,
    })

    const { messages, loading, sendMessage } = useDocAiChat(defaultOptions)
    await sendMessage('测试问题')

    // 用户消息 + AI 回复
    expect(messages.value).toHaveLength(2)
    expect(messages.value[0].role).toBe('user')
    expect(messages.value[0].text).toBe('测试问题')
    expect(messages.value[1].role).toBe('assistant')
    expect(messages.value[1].text).toBe('你好，世界')
    expect(messages.value[1].citations).toHaveLength(1)
    expect(loading.value).toBe(false)
  })

  it('离线时拒绝发送新消息', async () => {
    mockOnline = false

    const { messages, sendMessage, isOnline } = useDocAiChat(defaultOptions)
    // 手动设置离线状态（因为 composable 初始化时读取 navigator.onLine）
    isOnline.value = false

    await sendMessage('离线测试')

    expect(messages.value).toHaveLength(1)
    expect(messages.value[0].role).toBe('assistant')
    expect(messages.value[0].text).toContain('离线状态')
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('sendMessage 网络错误时显示错误消息', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'))

    const { messages, sendMessage } = useDocAiChat(defaultOptions)
    await sendMessage('测试')

    expect(messages.value).toHaveLength(2)
    expect(messages.value[1].role).toBe('assistant')
    expect(messages.value[1].text).toContain('AI 服务暂不可用')
  })

  it('sendMessage 空消息不发送', async () => {
    const { messages, sendMessage } = useDocAiChat(defaultOptions)
    await sendMessage('')
    await sendMessage('   ')

    expect(messages.value).toHaveLength(0)
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('clearHistory 清除本地和服务端历史', async () => {
    localStorageData[CACHE_KEY] = JSON.stringify([
      { id: '1', role: 'user', text: '旧消息' },
    ])

    mockFetch.mockResolvedValueOnce({ ok: true })

    const { messages, clearHistory } = useDocAiChat(defaultOptions)
    expect(messages.value).toHaveLength(1)

    await clearHistory()

    expect(messages.value).toHaveLength(0)
    expect(mockLocalStorage.removeItem).toHaveBeenCalledWith(CACHE_KEY)
    expect(mockFetch).toHaveBeenCalledWith(
      // 宿主有项目绑定 → 带 project_id 断言（无绑定时 hostQueryString 返回空串）
      `/api/ai-chat/doc/workpaper/${WP_ID}/history?project_id=${PROJECT_ID}`,
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  // Task 7（dsh-agent-panel-integration Req 8.1/8.6）：采纳只提交服务端 message ID +
  // 宿主 + 幂等键，**不提交正文**。服务端按 ID 读库取权威正文。
  const SERVER_MESSAGE_ID = '3f2504e0-4f89-41d3-9a0c-0305e82c3301'

  it('fetchHistory 保留服务端 message_id，历史消息因此可采纳', async () => {
    // 后端 history 每条带 `message_id`（Task 3 的真实元数据）。旧实现读的是不存在的
    // `m.id` ⇒ 恒回落 `hist_N` 占位 ID ⇒ 任何历史消息都过不了采纳的服务端 ID 检查。
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        data: {
          messages: [
            { message_id: SERVER_MESSAGE_ID, role: 'assistant', content: '历史回复' },
          ],
        },
      }),
    })

    const { messages, fetchHistory, adoptContent } = useDocAiChat(defaultOptions)
    await fetchHistory()

    expect(messages.value[0].id).toBe(SERVER_MESSAGE_ID)

    // 端到端：该 ID 能真的走到 adopt 请求（不是被占位 ID 检查挡下）
    mockFetch.mockResolvedValueOnce({ ok: true })
    const result = await adoptContent(SERVER_MESSAGE_ID)
    expect(result.success).toBe(true)
    expect(mockFetch).toHaveBeenLastCalledWith(
      '/api/ai-chat/adopt',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('adoptContent 提交服务端 message ID + 幂等键，且不提交正文', async () => {
    localStorageData[CACHE_KEY] = JSON.stringify([
      { id: SERVER_MESSAGE_ID, role: 'assistant', text: 'AI 建议内容', citations: [] },
    ])

    mockFetch.mockResolvedValueOnce({ ok: true })

    const { adoptContent } = useDocAiChat(defaultOptions)
    const result = await adoptContent(SERVER_MESSAGE_ID)

    expect(result.success).toBe(true)
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/ai-chat/adopt',
      expect.objectContaining({ method: 'POST' }),
    )
    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.message_id).toBe(SERVER_MESSAGE_ID)
    expect(body.host).toEqual({
      type: 'workpaper',
      id: WP_ID,
      project_id: PROJECT_ID,
      year: 2025,
    })
    expect(body.idempotency_key).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[089ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    )
    // 🔴 正文不得出现在请求体的任何位置（旧实现发的是 content: msg.text）
    expect(body).not.toHaveProperty('content')
    expect(JSON.stringify(body)).not.toContain('AI 建议内容')
  })

  it('adoptContent 对本地占位 ID 直接拒绝，不发注定失败的请求', async () => {
    localStorageData[CACHE_KEY] = JSON.stringify([
      { id: 'ai_1712345678', role: 'assistant', text: '流式刚生成的回复', citations: [] },
    ])

    const { adoptContent } = useDocAiChat(defaultOptions)
    const result = await adoptContent('ai_1712345678')

    expect(result.success).toBe(false)
    expect(result.code).toBe('message_id_not_server_issued')
    expect(result.message).toContain('服务端消息编号')
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('adoptContent 服务端返回失败时带出 typed code 与中文原因', async () => {
    localStorageData[CACHE_KEY] = JSON.stringify([
      { id: SERVER_MESSAGE_ID, role: 'assistant', text: 'AI 建议内容', citations: [] },
    ])
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 503,
      json: async () => ({
        detail: { code: 'adopt_log_failed', message: '采纳未生效：请稍后重试' },
      }),
    })

    const { adoptContent } = useDocAiChat(defaultOptions)
    const result = await adoptContent(SERVER_MESSAGE_ID)

    expect(result.success).toBe(false)
    expect(result.code).toBe('adopt_log_failed')
    expect(result.message).toContain('采纳未生效')
  })

  it('adoptContent 消息不存在时返回失败', async () => {
    const { adoptContent } = useDocAiChat(defaultOptions)
    const result = await adoptContent('non-existent')

    expect(result.success).toBe(false)
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('sendMessage 传递 extraScopes', async () => {
    const encoder = new TextEncoder()
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('data: {"type":"content","data":"回复"}\n\ndata: [DONE]\n'))
        controller.close()
      },
    })

    mockFetch.mockResolvedValueOnce({ ok: true, body: stream })

    const { sendMessage } = useDocAiChat(defaultOptions)
    await sendMessage('问题', ['scope-1', 'scope-2'])

    expect(mockFetch).toHaveBeenCalledWith(
      `/api/ai-chat/doc/workpaper/${WP_ID}`,
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"extra_scopes":["scope-1","scope-2"]'),
      }),
    )
  })
})
