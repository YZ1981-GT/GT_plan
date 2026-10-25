/**
 * useSSEReconnect · 传输层必须能带鉴权头（真 composable，只替换 createSSE）
 *
 * 缺陷（2026-09-30 实测）：旧实现用原生 `EventSource`，不能带请求头；账表导入进度流
 * `…/ledger-import/jobs/{id}/stream` 走 `require_project_access`（只认 Bearer 头，`?token=` 也 401）
 * ⇒ 每次都连不上，进度全靠 pollFallback 轮询兜底，SSE 从未生效。
 * 平台 LineagePanel 早先踩过同一坑（原生 EventSource 无 token 恒 401），已迁到 fetch 流。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue')
  return { ...actual, onUnmounted: vi.fn() }
})

class FakeConn {
  static all: FakeConn[] = []
  msg: ((d: any, e?: string) => void) | null = null
  err: ((e: any) => void) | null = null
  open: (() => void) | null = null
  drain: ((r: string) => void) | null = null
  closed = false
  constructor(public url: string, public opts: any) { FakeConn.all.push(this) }
  onMessage(h: (d: any, e?: string) => void) { this.msg = h }
  onError(h: (e: any) => void) { this.err = h }
  onOpen(h: () => void) { this.open = h }
  onDraining(h: (r: string) => void) { this.drain = h }
  close() { this.closed = true }
  get isConnected() { return !this.closed }
  get lastEventId() { return undefined }
}
vi.mock('@/utils/sse', () => ({ createSSE: (url: string, opts: any) => new FakeConn(url, opts) }))

import { useSSEReconnect } from '../useSSEReconnect'

const flush = () => new Promise((r) => setTimeout(r, 0))

beforeEach(() => { FakeConn.all = [] })

describe('useSSEReconnect 走 createSSE（fetch 流带 Authorization）', () => {
  it('建连用 createSSE、关掉其内置重试（重连由本 composable 先 poll 再编排）', () => {
    useSSEReconnect({ url: () => '/api/x/stream', onMessage: vi.fn(), pollFallback: vi.fn(async () => 'running' as const) })
    expect(FakeConn.all).toHaveLength(1)
    expect(FakeConn.all[0].url).toBe('/api/x/stream')
    expect(FakeConn.all[0].opts).toEqual({ maxRetries: 0 })
  })

  it('消息原样转交、连接成功置 connected', () => {
    const onMessage = vi.fn()
    const r = useSSEReconnect({ url: '/api/x', onMessage, pollFallback: vi.fn(async () => 'running' as const) })
    FakeConn.all[0].open!()
    FakeConn.all[0].msg!({ phase: 'writing', percent: 40 })
    expect(r.connected.value).toBe(true)
    expect(onMessage).toHaveBeenCalledWith({ phase: 'writing', percent: 40 })
  })

  it('断线：先 poll 真实状态；终态不重连，运行中按退避重连', async () => {
    vi.useFakeTimers()
    try {
      const poll = vi.fn(async () => 'completed' as const)
      useSSEReconnect({ url: '/api/x', onMessage: vi.fn(), pollFallback: poll, backoffMs: 10 })
      FakeConn.all[0].err!(new Error('x'))
      await vi.runAllTimersAsync()
      expect(poll).toHaveBeenCalledTimes(1)
      expect(FakeConn.all).toHaveLength(1)

      FakeConn.all = []
      const running = vi.fn(async () => 'running' as const)
      useSSEReconnect({ url: '/api/y', onMessage: vi.fn(), pollFallback: running, backoffMs: 10 })
      FakeConn.all[0].err!(new Error('x'))
      await vi.advanceTimersByTimeAsync(600)
      expect(FakeConn.all).toHaveLength(2)
      expect(FakeConn.all[0].closed).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })

  it('服务端优雅关闭（server_draining）按断线处理：poll 后重连', async () => {
    const poll = vi.fn(async () => 'completed' as const)
    const onDisconnected = vi.fn()
    useSSEReconnect({ url: '/api/x', onMessage: vi.fn(), pollFallback: poll, onDisconnected })
    FakeConn.all[0].drain!('服务端正在优雅关闭')
    await flush()
    expect(onDisconnected).toHaveBeenCalledTimes(1)
    expect(poll).toHaveBeenCalledTimes(1)
  })

  it('close() 之后旧连接的迟到错误不触发重连', async () => {
    const poll = vi.fn(async () => 'running' as const)
    const r = useSSEReconnect({ url: '/api/x', onMessage: vi.fn(), pollFallback: poll })
    const first = FakeConn.all[0]
    r.close()
    first.err!(new Error('late'))
    await flush()
    expect(poll).not.toHaveBeenCalled()
    expect(first.closed).toBe(true)
  })

  it('源码级：不再使用原生 EventSource', () => {
    const src = readFileSync(resolve(__dirname, '../useSSEReconnect.ts'), 'utf-8')
    expect(src).not.toMatch(/new\s+EventSource\s*\(/)
  })
})
