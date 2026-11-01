import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const progress = vi.hoisted(() => ({
  start: vi.fn(),
  done: vi.fn(),
  inc: vi.fn(),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 't', refreshToken: null, logout: vi.fn() }),
}))
vi.mock('nprogress', () => ({ default: progress }))
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(() => ({ close: vi.fn() })) },
}))
vi.mock('@/composables/useVersionCheck', () => ({
  versionBridge: { check: vi.fn(), push: vi.fn() },
}))

let http: typeof import('@/utils/http').default
let originalAdapter: unknown

function response(config: any, data: unknown = { code: 200, data: { ok: true } }) {
  return { data, status: 200, statusText: 'OK', headers: {}, config }
}

function failure(config: any, status: number) {
  return Object.assign(new Error(`HTTP ${status}`), {
    config,
    response: { status, data: { detail: '失败' }, headers: {}, config },
    isAxiosError: true,
  })
}

beforeEach(async () => {
  vi.resetModules()
  progress.start.mockReset()
  progress.done.mockReset()
  progress.inc.mockReset()
  http = (await import('@/utils/http')).default
  originalAdapter = http.defaults.adapter
})

afterEach(() => {
  vi.useRealTimers()
  http.defaults.adapter = originalAdapter as any
})

describe('后台请求与全局进度条', () => {
  it('background 成功请求不启动或结束 NProgress', async () => {
    http.defaults.adapter = async (config: any) => response(config)
    await http.get('/api/background', { _background: true } as any)
    expect(progress.start).not.toHaveBeenCalled()
    expect(progress.inc).not.toHaveBeenCalled()
    expect(progress.done).not.toHaveBeenCalled()
  })

  it('background 完成不会减掉仍在飞的前台请求', async () => {
    let release!: () => void
    const gate = new Promise<void>((resolve) => { release = resolve })
    http.defaults.adapter = async (config: any) => {
      if (config.url === '/api/foreground') await gate
      return response(config)
    }

    const foreground = http.get('/api/foreground')
    await Promise.resolve()
    await http.get('/api/background', { _background: true } as any)
    expect(progress.start).toHaveBeenCalledTimes(1)
    expect(progress.done).not.toHaveBeenCalled()

    release()
    await foreground
    expect(progress.done).toHaveBeenCalledTimes(1)
  })

  it('silent 与 background 正交，silent 前台请求仍显示进度', async () => {
    http.defaults.adapter = async (config: any) => response(config)
    await http.get('/api/silent', { _silent: true } as any)
    expect(progress.start).toHaveBeenCalledTimes(1)
    expect(progress.done).toHaveBeenCalledTimes(1)
  })
})

describe('5xx 重试安全门', () => {
  it('纯策略只放行幂等读、幂等键或显式安全写', async () => {
    const { shouldRetry5xx } = await import('@/utils/http')
    expect(shouldRetry5xx({ method: 'get' }, 503)).toBe(true)
    expect(shouldRetry5xx({ method: 'post' }, 503)).toBe(false)
    expect(shouldRetry5xx({ method: 'post', headers: { 'Idempotency-Key': 'op-1' } }, 503)).toBe(true)
    expect(shouldRetry5xx({ method: 'delete', _retrySafe: true } as any, 500)).toBe(true)
    expect(shouldRetry5xx({ method: 'get' }, 504)).toBe(false)
    expect(shouldRetry5xx({ method: 'get' }, 501)).toBe(false)
  })

  it('无幂等键 POST 遇 503 只发送一次', async () => {
    let calls = 0
    http.defaults.adapter = async (config: any) => {
      calls += 1
      throw failure(config, 503)
    }
    await expect(http.post('/api/write', { value: 1 })).rejects.toBeTruthy()
    expect(calls).toBe(1)
  })

  it('带幂等键 POST 遇 503 后可重试且正文逐字相同', async () => {
    vi.useFakeTimers()
    const bodies: unknown[] = []
    http.defaults.adapter = async (config: any) => {
      bodies.push(config.data)
      if (bodies.length === 1) throw failure(config, 503)
      return response(config)
    }
    const pending = http.post('/api/idempotent', { value: 1 }, {
      headers: { 'Idempotency-Key': 'op-1' },
    })
    await vi.advanceTimersByTimeAsync(1000)
    await expect(pending).resolves.toBeTruthy()
    expect(bodies).toHaveLength(2)
    expect(bodies[1]).toBe(bodies[0])
  })
})

describe('大 JSON 正文只序列化一次且完整指纹去重', () => {
  it('同一对象只调用一次 toJSON，adapter 收到可复用 JSON 字符串', async () => {
    let serializations = 0
    const payload = {
      value: 'x'.repeat(1024 * 1024),
      toJSON() {
        serializations += 1
        return { value: this.value }
      },
    }
    let sent: unknown
    http.defaults.adapter = async (config: any) => {
      sent = config.data
      return response(config)
    }

    await http.post('/api/large', payload)
    expect(serializations).toBe(1)
    expect(typeof sent).toBe('string')
    expect(JSON.parse(sent as string)).toEqual({ value: payload.value })
  })

  it('自定义 transformRequest 保持原语义，不被预序列化', async () => {
    const transform = vi.fn((data: any) => JSON.stringify({ wrapped: data.value }))
    let sent: unknown
    http.defaults.adapter = async (config: any) => {
      sent = config.data
      return response(config)
    }

    await http.post('/api/custom-transform', { value: 7 }, {
      transformRequest: transform,
      headers: { 'Content-Type': 'application/json' },
    })

    expect(transform).toHaveBeenCalledTimes(1)
    expect(sent).toBe('{"wrapped":7}')
  })

  it('前 100 字符和长度相同但尾部不同的并发正文不会互相误杀', async () => {
    let release!: () => void
    const gate = new Promise<void>((resolve) => { release = resolve })
    const started: string[] = []
    http.defaults.adapter = async (config: any) => {
      started.push(config.data)
      await gate
      return response(config)
    }
    const prefix = 'x'.repeat(200)
    const first = http.post('/api/collision', { payload: `${prefix}A` })
    const second = http.post('/api/collision', { payload: `${prefix}B` })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(started).toHaveLength(2)
    release()
    await Promise.all([first, second])
  })
})
