/**
 * Task 4 — `_dedupe:false` 保留调用方 signal，同 URL 双请求互不取消
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    token: 't',
    refreshToken: null,
    logout: vi.fn(),
    setTokens: vi.fn(),
  }),
}))

vi.mock('nprogress', () => ({
  default: { start: vi.fn(), done: vi.fn(), inc: vi.fn() },
}))

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
}))

vi.mock('@/composables/useVersionCheck', () => ({
  versionBridge: { check: vi.fn() },
}))

type AdapterConfig = {
  url?: string
  signal?: AbortSignal
  _dedupe?: boolean
  _silent?: boolean
  method?: string
}

describe('http _dedupe:false contract', () => {
  let http: typeof import('@/utils/http').default
  let started: AdapterConfig[]
  let originalAdapter: any

  beforeEach(async () => {
    vi.resetModules()
    http = (await import('@/utils/http')).default
    started = []
    originalAdapter = http.defaults.adapter
    http.defaults.adapter = async (config: any) => {
      if (config.signal?.aborted) {
        const err: any = new Error('canceled')
        err.code = 'ERR_CANCELED'
        err.name = 'CanceledError'
        throw err
      }
      started.push({
        url: config.url,
        signal: config.signal,
        _dedupe: config._dedupe,
        method: config.method,
      })
      await new Promise((r) => setTimeout(r, 20))
      if (config.signal?.aborted) {
        const err: any = new Error('canceled')
        err.code = 'ERR_CANCELED'
        err.name = 'CanceledError'
        throw err
      }
      return {
        data: new Blob(['ok']),
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }
  })

  afterEach(() => {
    if (http) http.defaults.adapter = originalAdapter
  })

  it('预先 aborted signal 不发请求（_dedupe:false）', async () => {
    const ac = new AbortController()
    ac.abort()
    await expect(
      http.get('/api/attachments/x/download', {
        responseType: 'blob',
        _silent: true,
        _dedupe: false,
        signal: ac.signal,
      } as any),
    ).rejects.toMatchObject({ code: 'ERR_CANCELED' })
    expect(started.length).toBe(0)
  })

  it('同 URL 两个 _dedupe:false 均成功；取消一个不影响另一个', async () => {
    const a = new AbortController()
    const b = new AbortController()
    const p1 = http.get('/api/attachments/same/download', {
      responseType: 'blob',
      _silent: true,
      _dedupe: false,
      signal: a.signal,
    } as any)
    const p2 = http.get('/api/attachments/same/download', {
      responseType: 'blob',
      _silent: true,
      _dedupe: false,
      signal: b.signal,
    } as any)
    await new Promise((r) => setTimeout(r, 5))
    expect(started.length).toBe(2)
    expect(started[0].signal).toBe(a.signal)
    expect(started[1].signal).toBe(b.signal)
    a.abort()
    await expect(p1).rejects.toMatchObject({ code: 'ERR_CANCELED' })
    const r2 = await p2
    expect(r2.status).toBe(200)
  })

  it('未传 _dedupe 的存量 GET 仍取消先发请求', async () => {
    const p1 = http.get('/api/attachments/dedupe/preview', {
      responseType: 'blob',
      _silent: true,
    } as any)
    await new Promise((r) => setTimeout(r, 5))
    const p2 = http.get('/api/attachments/dedupe/preview', {
      responseType: 'blob',
      _silent: true,
    } as any)
    await expect(p1).rejects.toMatchObject({ code: 'ERR_CANCELED' })
    const r2 = await p2
    expect(r2.status).toBe(200)
  })
})
