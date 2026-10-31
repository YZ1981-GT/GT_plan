/**
 * utils/http 的 GET 共享在途（spec platform-performance-residual-findings-closure R11）。
 *
 * 原去重是「同一 GET 在飞时后发者取消先发者」：同页两个组件取同一地址时先发方静默失败（工时页「预算对比」恒空、
 * 编辑器误报「底稿文件尚未生成」、索引芯片显示「底稿不存在」……）。现在后发者共用先发者那一次请求。
 * 用真实 http（拦截器、信封解包）+ 假适配器（网络层），逐条钉住：共用、各自取消、各自拿结果、新鲜度屏障、身份边界、
 * 白名单外独立发送、失败不缓存。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 't', refreshToken: null, logout: vi.fn(), setTokens: vi.fn() }),
}))
vi.mock('nprogress', () => ({ default: { start: vi.fn(), done: vi.fn(), inc: vi.fn() } }))
vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() } }))
vi.mock('@/composables/useVersionCheck', () => ({ versionBridge: { check: vi.fn(), push: vi.fn() } }))

type Sent = { method: string; url: string; signal?: AbortSignal; release: (data?: unknown, status?: number) => void }

function canceled(): Error {
  return Object.assign(new Error('canceled'), { code: 'ERR_CANCELED', name: 'CanceledError', __CANCEL__: true })
}

let http: typeof import('@/utils/http').default
let shared: typeof import('@/utils/getSingleFlight')
let identity: typeof import('@/services/requestIdentityEpoch')
let sent: Sent[]
let originalAdapter: unknown

/** 每次请求都挂起，直到用例调 release；POST 等写请求立即成功 */
beforeEach(async () => {
  vi.resetModules()
  http = (await import('@/utils/http')).default
  shared = await import('@/utils/getSingleFlight')
  identity = await import('@/services/requestIdentityEpoch')
  sent = []
  originalAdapter = http.defaults.adapter
  http.defaults.adapter = (config: any) => new Promise((resolve, reject) => {
    const method = String(config.method).toUpperCase()
    if (config.signal?.aborted) { reject(canceled()); return }
    const respond = (data: unknown = { code: 200, message: 'success', data: { rows: [1, 2] } }, status = 200) => {
      if (status >= 400) {
        reject(Object.assign(new Error(`HTTP ${status}`), { config, response: { status, data, headers: {}, config }, isAxiosError: true }))
      } else {
        resolve({ data, status, statusText: 'OK', headers: {}, config })
      }
    }
    config.signal?.addEventListener?.('abort', () => reject(canceled()), { once: true })
    sent.push({ method, url: String(config.url), signal: config.signal, release: respond })
    // 写请求默认立即成功；/slow-write 挂着，用来测「写请求还在飞」
    if (method !== 'GET' && !String(config.url).includes('/slow-write')) respond({ code: 200, message: 'success', data: { ok: true } })
  })
})

afterEach(() => {
  http.defaults.adapter = originalAdapter as any
})

const gets = (url: string) => sent.filter((s) => s.method === 'GET' && s.url === url)
const tick = () => new Promise((r) => setTimeout(r, 0))

describe('同一 GET 在飞时共用一次请求', () => {
  it('两个调用方都拿到解包后的数据，只发一次；数据互不串改', async () => {
    const a = http.get('/api/x', { params: { year: 2025 } })
    const b = http.get('/api/x', { params: { year: 2025 } })
    await tick()
    expect(gets('/api/x')).toHaveLength(1)
    gets('/api/x')[0].release()
    const [ra, rb] = await Promise.all([a, b])
    expect(ra.data).toEqual({ rows: [1, 2] })
    expect(rb.data).toEqual({ rows: [1, 2] })
    expect(rb).not.toBe(ra)
    expect(rb.data).not.toBe(ra.data)
    ra.data.rows.push(3)
    expect(rb.data.rows).toEqual([1, 2])
  })

  it('参数乱序视为同一请求；参数 / 返回类型 / 静默标记不同则各发各的', async () => {
    http.get('/api/y', { params: { a: 1, b: [2, 1] } })
    http.get('/api/y', { params: { b: [2, 1], a: 1 } })
    http.get('/api/y', { params: { a: 1, b: [1, 2] } })
    http.get('/api/y', { params: { a: 1, b: [2, 1] }, responseType: 'blob' })
    http.get('/api/y', { params: { a: 1, b: [2, 1] }, _silent: true } as any)
    await tick()
    expect(gets('/api/y')).toHaveLength(4)
  })

  it('A 取消只拒绝 A，B 照常拿结果；底层请求不带任何调用方的 signal', async () => {
    const ca = new AbortController()
    const cb = new AbortController()
    const a = http.get('/api/z', { signal: ca.signal })
    const b = http.get('/api/z', { signal: cb.signal })
    await tick()
    expect(gets('/api/z')).toHaveLength(1)
    const transportSignal = gets('/api/z')[0].signal
    expect(transportSignal).not.toBe(ca.signal)
    expect(transportSignal).not.toBe(cb.signal)
    ca.abort()
    await expect(a).rejects.toMatchObject({ code: 'ERR_CANCELED', name: 'CanceledError' })
    gets('/api/z')[0].release()
    await expect(b).resolves.toMatchObject({ data: { rows: [1, 2] } })
  })

  it('预先取消的调用不发请求', async () => {
    const c = new AbortController()
    c.abort()
    await expect(http.get('/api/pre', { signal: c.signal })).rejects.toMatchObject({ code: 'ERR_CANCELED' })
    expect(gets('/api/pre')).toHaveLength(0)
  })

  it('成功即出在途表：之后再取另发（不缓存结果）', async () => {
    const first = http.get('/api/once')
    await tick()
    gets('/api/once')[0].release()
    await first
    const second = http.get('/api/once')
    await tick()
    expect(gets('/api/once')).toHaveLength(2)
    gets('/api/once')[1].release()
    await expect(second).resolves.toMatchObject({ status: 200 })
  })

  it('失败时共用同一个错误，之后再取另发', async () => {
    const a = http.get('/api/fail', { _silent: true } as any)
    const b = http.get('/api/fail', { _silent: true } as any)
    await tick()
    expect(gets('/api/fail')).toHaveLength(1)
    gets('/api/fail')[0].release({ code: 404, message: '不存在' }, 404)
    const [ea, eb] = await Promise.all([a.catch((e) => e), b.catch((e) => e)])
    expect(ea).toBe(eb)
    expect(ea.response.status).toBe(404)
    http.get('/api/fail', { _silent: true } as any)
    await tick()
    expect(gets('/api/fail')).toHaveLength(2)
  })

  it('ArrayBuffer 后加入者拿复制；Blob 共用', async () => {
    const buf = new Uint8Array([1, 2, 3]).buffer
    const a = http.get('/api/bin', { responseType: 'arraybuffer' })
    const b = http.get('/api/bin', { responseType: 'arraybuffer' })
    await tick()
    gets('/api/bin')[0].release(buf)
    const [ra, rb] = await Promise.all([a, b])
    expect(ra.data).toBe(buf)
    expect(rb.data).not.toBe(buf)
    expect(new Uint8Array(rb.data)).toEqual(new Uint8Array([1, 2, 3]))
  })
})

describe('新鲜度与身份边界', () => {
  it('写请求发出后，之前在飞的 GET 不再给新请求共用；旧订阅者照常拿旧结果', async () => {
    const before = http.get('/api/list')
    await tick()
    await http.post('/api/list/item', { name: '新' })
    const after = http.get('/api/list')
    await tick()
    expect(gets('/api/list')).toHaveLength(2)
    gets('/api/list')[0].release({ code: 200, message: 'success', data: ['旧'] })
    gets('/api/list')[1].release({ code: 200, message: 'success', data: ['旧', '新'] })
    expect((await before).data).toEqual(['旧'])
    expect((await after).data).toEqual(['旧', '新'])
  })

  it('写请求一发出（还没回）就推进屏障：随后的同址 GET 不复用写请求之前在飞的那次', async () => {
    http.get('/api/doc')
    await tick()
    const write = http.post('/api/doc/slow-write', { v: 1 })
    await tick()
    expect(sent.filter((s) => s.method === 'POST')).toHaveLength(1) // 写请求已发出、仍在飞
    http.get('/api/doc')
    await tick()
    expect(gets('/api/doc')).toHaveLength(2)
    sent.find((s) => s.method === 'POST')!.release()
    await write
  })

  it('推进屏障（项目事件推送）后新请求另发', async () => {
    http.get('/api/tb')
    await tick()
    shared.advanceGetShareBarrier()
    http.get('/api/tb')
    await tick()
    expect(gets('/api/tb')).toHaveLength(2)
  })

  it('登录身份切换：旧订阅以取消结束，新请求另发', async () => {
    const old = http.get('/api/me')
    await tick()
    identity.advanceRequestIdentityEpoch()
    await expect(old).rejects.toMatchObject({ code: 'ERR_CANCELED' })
    http.get('/api/me')
    await tick()
    expect(gets('/api/me')).toHaveLength(2)
  })
})

describe('白名单外的配置独立发送', () => {
  it.each([
    ['headers', { headers: { 'X-Mode': '1' } }],
    ['timeout', { timeout: 9000 }],
    ['validateStatus', { validateStatus: () => true }],
    ['_dedupe:false', { _dedupe: false }],
    ['URLSearchParams 参数', { params: new URLSearchParams('a=1') }],
  ])('%s：同址两次各发一次、互不取消', async (_label, config) => {
    const url = `/api/independent-${_label}`
    const a = http.get(url, config as any)
    const b = http.get(url, config as any)
    await tick()
    expect(gets(url)).toHaveLength(2)
    gets(url).forEach((s) => s.release())
    await expect(Promise.all([a, b])).resolves.toHaveLength(2)
  })

  it('独立请求同样有身份边界：登出 / 换人后旧请求的结果不交给新身份', async () => {
    const p = http.get('/api/indep-identity', { timeout: 5000 })
    await tick()
    expect(gets('/api/indep-identity')).toHaveLength(1)
    identity.advanceRequestIdentityEpoch()
    await expect(p).rejects.toMatchObject({ code: 'ERR_CANCELED' })
  })

  it('独立请求的调用方 signal 直达底层（原先被去重表换掉，调用方取消不生效）', async () => {
    const c = new AbortController()
    const p = http.get('/api/own-signal', { signal: c.signal, timeout: 5000 })
    await tick()
    expect(gets('/api/own-signal')[0].signal).toBe(c.signal)
    c.abort()
    await expect(p).rejects.toMatchObject({ code: 'ERR_CANCELED' })
  })
})
