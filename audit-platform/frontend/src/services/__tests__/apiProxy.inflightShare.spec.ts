/**
 * apiProxy GET single-flight.
 *
 * A shared producer is allowed only for equivalent, low-risk GET semantics.
 * Every caller gets a distinct subscription: aborting caller A cannot cancel B.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: http }))

import { api, resetApiProxyInflightForTests } from '../apiProxy'
import { advanceGetShareBarrier } from '@/utils/getSingleFlight'
import {
  advanceRequestIdentityEpoch,
  requestIdentityEpoch,
  resetRequestIdentityEpochForTests,
} from '../requestIdentityEpoch'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

beforeEach(() => {
  http.get.mockReset()
  resetApiProxyInflightForTests()
  resetRequestIdentityEpochForTests()
})

describe('api.get 安全 single-flight', () => {
  it('递归乱序 params 的同一安全请求只发一个 producer，producer 关闭底层取消式去重', async () => {
    const d = deferred<{ data: unknown }>()
    http.get.mockReturnValue(d.promise)
    const a = api.get('/api/query', { params: { z: [2, 1], nested: { b: 2, a: 1 } } })
    const b = api.get('/api/query', { params: { nested: { a: 1, b: 2 }, z: [2, 1] } })
    expect(http.get).toHaveBeenCalledTimes(1)
    expect(http.get).toHaveBeenCalledWith('/api/query', {
      params: { z: [2, 1], nested: { b: 2, a: 1 } }, _dedupe: false,
    })
    d.resolve({ data: { rows: [1] } })
    await expect(a).resolves.toEqual({ rows: [1] })
    await expect(b).resolves.toEqual({ rows: [1] })
  })

  it('数组顺序、responseType 和 silent 语义不同都不得复用 producer', async () => {
    http.get.mockImplementation(() => new Promise(() => {}))
    api.get('/api/x', { params: { codes: ['A', 'B'] } })
    api.get('/api/x', { params: { codes: ['B', 'A'] } })
    api.get('/api/x', { responseType: 'blob' })
    api.get('/api/x', { _silent: true })
    expect(http.get).toHaveBeenCalledTimes(4)
  })

  it('显式 _dedupe:false 与高风险 config 都独立发送，且不落入底层取消式去重', () => {
    http.get.mockImplementation(() => new Promise(() => {}))
    const risky = [
      { _dedupe: false },
      { headers: { 'X-Mode': 'one' } },
      { timeout: 9000 },
      { validateStatus: () => true },
      { adapter: () => Promise.resolve({}) },
      { paramsSerializer: () => 'x=1' },
      { transformResponse: [(v: unknown) => v] },
    ]
    for (const config of risky) api.get('/api/risky', config as any)
    expect(http.get).toHaveBeenCalledTimes(risky.length)
    expect(http.get.mock.calls.every(([, config]) => config._dedupe === false)).toBe(true)
  })

  it('Date、URLSearchParams、函数和循环 params 不猜等价性，全部独立发送', () => {
    http.get.mockImplementation(() => new Promise(() => {}))
    const cyclic: any = { a: 1 }; cyclic.self = cyclic
    for (const params of [new Date(), new URLSearchParams('a=1'), { fn: () => 1 }, cyclic]) {
      api.get('/api/unsafe-params', { params } as any)
    }
    expect(http.get).toHaveBeenCalledTimes(4)
  })
})

describe('api.get 独立订阅取消与身份边界', () => {
  it('同 flight 中 A 取消只拒绝 A，B 正常得到 producer 结果；producer 不带任一订阅者 signal', async () => {
    const d = deferred<{ data: unknown }>()
    http.get.mockReturnValue(d.promise)
    const a = new AbortController()
    const b = new AbortController()
    const first = api.get('/api/shared', { params: { project: 'p1' }, signal: a.signal })
    const second = api.get('/api/shared', { params: { project: 'p1' }, signal: b.signal })
    expect(http.get).toHaveBeenCalledTimes(1)
    expect(http.get.mock.calls[0][1]).toEqual({ params: { project: 'p1' }, _dedupe: false })
    a.abort()
    await expect(first).rejects.toMatchObject({ code: 'ERR_CANCELED', name: 'CanceledError' })
    d.resolve({ data: { ok: true } })
    await expect(second).resolves.toEqual({ ok: true })
  })

  it('预先取消的安全订阅不创建 producer', async () => {
    const controller = new AbortController()
    controller.abort()
    await expect(api.get('/api/pre-aborted', { signal: controller.signal })).rejects.toMatchObject({
      code: 'ERR_CANCELED', name: 'CanceledError',
    })
    expect(http.get).not.toHaveBeenCalled()
  })

  it('身份代际推进后同 URL 创建新 producer，旧订阅不能回传旧身份数据', async () => {
    const old = deferred<{ data: unknown }>()
    const fresh = deferred<{ data: unknown }>()
    http.get.mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise)
    const oldSubscriber = api.get('/api/projects/p1', { params: { year: 2025 } })
    expect(requestIdentityEpoch()).toBe(0)
    advanceRequestIdentityEpoch()
    const newSubscriber = api.get('/api/projects/p1', { params: { year: 2025 } })
    expect(http.get).toHaveBeenCalledTimes(2)
    old.resolve({ data: { owner: 'old-user' } })
    fresh.resolve({ data: { owner: 'new-user' } })
    await expect(oldSubscriber).rejects.toMatchObject({ code: 'ERR_CANCELED' })
    await expect(newSubscriber).resolves.toEqual({ owner: 'new-user' })
  })

  it('后加入者拿深拷贝：一方改数据不影响另一方（R11）', async () => {
    const d = deferred<{ data: unknown }>()
    http.get.mockReturnValue(d.promise)
    const a = api.get('/api/copy')
    const b = api.get('/api/copy')
    d.resolve({ data: { rows: [{ v: 1 }] } })
    const [ra, rb] = await Promise.all([a, b])
    expect(rb).toEqual(ra)
    expect(rb).not.toBe(ra)
    ra.rows[0].v = 99
    expect(rb.rows[0].v).toBe(1)
  })

  it('新鲜度屏障推进后（写请求 / 项目事件）同址新请求另起 producer，旧订阅照常拿旧结果（R11）', async () => {
    const old = deferred<{ data: unknown }>()
    const fresh = deferred<{ data: unknown }>()
    http.get.mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise)
    const before = api.get('/api/list')
    advanceGetShareBarrier()
    const after = api.get('/api/list')
    expect(http.get).toHaveBeenCalledTimes(2)
    old.resolve({ data: ['旧'] })
    fresh.resolve({ data: ['旧', '新'] })
    await expect(before).resolves.toEqual(['旧'])
    await expect(after).resolves.toEqual(['旧', '新'])
  })

  it('producer 成功、失败后都移出在途表，不会缓存结果', async () => {
    http.get.mockResolvedValueOnce({ data: 1 }).mockResolvedValueOnce({ data: 2 })
    await expect(api.get('/api/once')).resolves.toBe(1)
    await expect(api.get('/api/once')).resolves.toBe(2)
    const d = deferred<{ data: unknown }>()
    http.get.mockReturnValueOnce(d.promise)
    const failed = api.get('/api/failure')
    const error = new Error('HTTP 500')
    d.reject(error)
    await expect(failed).rejects.toBe(error)
    http.get.mockResolvedValueOnce({ data: 'after-error' })
    await expect(api.get('/api/failure')).resolves.toBe('after-error')
  })
})
