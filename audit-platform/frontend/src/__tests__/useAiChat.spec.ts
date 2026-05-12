/**
 * useAiChat composable 单测
 * 验证消息发送/流式解析/清除逻辑
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { computed, nextTick } from 'vue'

// Mock auth store
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token-123' }),
}))

// Mock lifecycle hooks
vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return {
    ...actual as any,
    onMounted: (fn: Function) => fn(),
    onUnmounted: vi.fn(),
  }
})

import { useAiChat } from '@/composables/useAiChat'

describe('useAiChat', () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockFetch = vi.fn()
    global.fetch = mockFetch
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('sends message and adds user message to history', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      body: null,
      json: async () => ({ answer: 'Hello from AI' }),
    })

    const { messages, send } = useAiChat({
      endpoint: '/api/ai/chat',
      streaming: false,
    })

    await send('你好')
    expect(messages.value.length).toBe(2)
    expect(messages.value[0].role).toBe('user')
    expect(messages.value[0].text).toBe('你好')
    expect(messages.value[1].role).toBe('assistant')
    expect(messages.value[1].text).toBe('Hello from AI')
  })

  it('does not send empty messages', async () => {
    const { messages, send } = useAiChat({ endpoint: '/api/ai/chat' })
    await send('   ')
    expect(messages.value.length).toBe(0)
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('includes context in request body', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      body: null,
      json: async () => ({ answer: 'ok' }),
    })

    const context = computed(() => ({ project_id: 'p1', wp_id: 'w1' }))
    const { send } = useAiChat({
      endpoint: '/api/ai/chat',
      context,
      streaming: false,
    })

    await send('test')
    const [url, opts] = mockFetch.mock.calls[0]
    const body = JSON.parse(opts.body)
    expect(body.project_id).toBe('p1')
    expect(body.wp_id).toBe('w1')
    expect(body.message).toBe('test')
  })

  it('handles HTTP error gracefully', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      headers: new Headers(),
    })

    const { messages, send } = useAiChat({ endpoint: '/api/ai/chat', streaming: false })
    await send('test')
    expect(messages.value.length).toBe(2)
    expect(messages.value[1].text).toContain('暂不可用')
  })

  it('clear() resets messages', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      body: null,
      json: async () => ({ answer: 'hi' }),
    })

    const { messages, send, clear } = useAiChat({ endpoint: '/api/ai/chat', streaming: false })
    await send('hello')
    expect(messages.value.length).toBe(2)

    clear()
    expect(messages.value.length).toBe(0)
  })

  it('sets loading state during request', async () => {
    let resolvePromise: Function
    mockFetch.mockReturnValue(new Promise(r => { resolvePromise = r }))

    const { loading, send } = useAiChat({ endpoint: '/api/ai/chat', streaming: false })
    expect(loading.value).toBe(false)

    const sendPromise = send('test')
    await nextTick()
    expect(loading.value).toBe(true)

    resolvePromise!({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      body: null,
      json: async () => ({ answer: 'done' }),
    })
    await sendPromise
    expect(loading.value).toBe(false)
  })
})
