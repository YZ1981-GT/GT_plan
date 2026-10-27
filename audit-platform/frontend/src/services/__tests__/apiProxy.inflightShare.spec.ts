/**
 * apiProxy GET 在途共享（spec procedure-chain-hardening-and-java-contracts R16）。
 *
 * 原先只有不带 config 的 GET 共享；带 `_silent` / `_dedupe` 这类标志的一律各发一条 ——
 * 编辑器打开时 GtWpRenderer（不静默）与壳的侧栏（静默）同时取 render-config，就是两条。
 * 现在：静默调用方可加入同 URL 的任何在途请求；非静默只加入同类非静默请求（加入静默请求会丢掉错误提示）；
 * 带 params / validateStatus 等真正影响请求的配置仍不共享。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: http }))

import { api } from '../apiProxy'
import { getProject } from '../auditPlatformApi'

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

beforeEach(() => {
  http.get.mockReset()
})

describe('api.get 在途共享', () => {
  it('不带 config：同 URL 并发只发一条（原有行为）', async () => {
    const d = deferred<{ data: unknown }>()
    http.get.mockReturnValue(d.promise)
    const a = api.get('/api/x')
    const b = api.get('/api/x')
    expect(http.get).toHaveBeenCalledTimes(1)
    d.resolve({ data: { v: 1 } })
    expect(await a).toEqual({ v: 1 })
    expect(await b).toEqual({ v: 1 })
  })

  it('静默调用方加入在途的非静默请求：只发一条，拿到同一结果', async () => {
    const d = deferred<{ data: unknown }>()
    http.get.mockReturnValue(d.promise)
    const loud = api.get('/api/workpapers/w1/render-config')
    const quiet = api.get('/api/workpapers/w1/render-config', { _silent: true, _dedupe: false } as any)
    expect(http.get).toHaveBeenCalledTimes(1)
    expect(http.get).toHaveBeenCalledWith('/api/workpapers/w1/render-config', undefined)
    d.resolve({ data: { component_type: 'x' } })
    expect(await quiet).toEqual({ component_type: 'x' })
    expect(await loud).toEqual({ component_type: 'x' })
  })

  it('加入后失败：两边拿到同一个错误（提示由那条非静默请求按原样给出，静默方自行处理）', async () => {
    const d = deferred<{ data: unknown }>()
    http.get.mockReturnValue(d.promise)
    const loud = api.get('/api/p/1')
    const quiet = api.get('/api/p/1', { _silent: true } as any)
    const err = new Error('HTTP 500')
    d.reject(err)
    await expect(loud).rejects.toBe(err)
    await expect(quiet).rejects.toBe(err)
    expect(http.get).toHaveBeenCalledTimes(1)
  })

  it('静默调用方之间也共享', async () => {
    const d = deferred<{ data: unknown }>()
    http.get.mockReturnValue(d.promise)
    const a = api.get('/api/p/2', { _silent: true, _dedupe: false } as any)
    const b = api.get('/api/p/2', { _silent: true } as any)
    expect(http.get).toHaveBeenCalledTimes(1)
    d.resolve({ data: 2 })
    expect(await a).toBe(2)
    expect(await b).toBe(2)
  })

  it('非静默调用方不加入在途的静默请求（否则失败时没有提示）', async () => {
    const d1 = deferred<{ data: unknown }>()
    const d2 = deferred<{ data: unknown }>()
    http.get.mockReturnValueOnce(d1.promise).mockReturnValueOnce(d2.promise)
    const quiet = api.get('/api/p/3', { _silent: true, _dedupe: false } as any)
    const loud = api.get('/api/p/3')
    expect(http.get).toHaveBeenCalledTimes(2)
    expect(http.get.mock.calls[1]).toEqual(['/api/p/3', undefined])
    d1.resolve({ data: 'q' })
    d2.resolve({ data: 'l' })
    expect(await quiet).toBe('q')
    expect(await loud).toBe('l')
  })

  it('非静默的 _dedupe:false 只与同类共享（不加入可被同址请求取消的那一类）', async () => {
    http.get.mockImplementation(() => new Promise(() => {}))
    api.get('/api/p/4')
    api.get('/api/p/4', { _dedupe: false } as any)
    api.get('/api/p/4', { _dedupe: false } as any)
    expect(http.get).toHaveBeenCalledTimes(2)
  })

  it('带 params / validateStatus 等配置不共享（行为不变）', async () => {
    http.get.mockImplementation(() => new Promise(() => {}))
    api.get('/api/p/5', { params: { a: 1 } })
    api.get('/api/p/5', { params: { a: 1 } })
    api.get('/api/p/5', { _silent: true, validateStatus: () => true } as any)
    expect(http.get).toHaveBeenCalledTimes(3)
  })

  it('getProject 经 apiProxy：编辑器打开时 store 与页面同时取项目详情只发一条', async () => {
    const d = deferred<{ data: unknown }>()
    http.get.mockReturnValue(d.promise)
    const a = getProject('p1')
    const b = api.get('/api/projects/p1', { _dedupe: false, _silent: true } as any)
    const c = getProject('p1')
    expect(http.get).toHaveBeenCalledTimes(1)
    d.resolve({ data: { id: 'p1', audit_year: 2025 } })
    expect(await a).toEqual({ id: 'p1', audit_year: 2025 })
    expect(await b).toEqual({ id: 'p1', audit_year: 2025 })
    expect(await c).toEqual({ id: 'p1', audit_year: 2025 })
  })

  it('在途结束后再取：另发一条（只共享在途，不缓存结果）', async () => {
    http.get.mockResolvedValueOnce({ data: 1 }).mockResolvedValueOnce({ data: 2 })
    expect(await api.get('/api/p/6')).toBe(1)
    expect(await api.get('/api/p/6', { _silent: true } as any)).toBe(2)
    expect(http.get).toHaveBeenCalledTimes(2)
  })
})
