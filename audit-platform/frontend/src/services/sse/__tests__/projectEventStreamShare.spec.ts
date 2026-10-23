// 同一浏览器、同一用户、同一项目的多个标签页共用一条项目事件流（spec writeback-followup-issue-closure R8）。
//
// 真栈根因：HTTP/1.1 下浏览器对同一主机最多 6 条并发连接、所有标签页共享；项目事件流是永不结束的
// 长连接，每个项目页标签各占一条 ⇒ 开到 6 个标签页后任何请求都在浏览器里排队（实测 6 条流在开时
// /api/health 8 s 仍未发出，断开一条后立即返回）。
//
// 这里用两份独立的模块实例模拟两个标签页（vi.resetModules 后各自 import，模块级单例互不相同），
// 共用一份内存版 Web Locks 与 BroadcastChannel —— 浏览器里它们正是跨标签页共享的那两样东西。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const sse = vi.hoisted(() => {
  class Conn {
    static all: Conn[] = []
    closed = false
    messageHandler: ((data: unknown, event?: string) => void) | null = null
    openHandler: (() => void) | null = null
    errorHandler: ((e: unknown) => void) | null = null
    constructor(public url: string, public opts: unknown) {
      Conn.all.push(this)
    }
    onMessage(h: (data: unknown, event?: string) => void) { this.messageHandler = h }
    onOpen(h: () => void) { this.openHandler = h }
    onError(h: (e: unknown) => void) { this.errorHandler = h }
    onDraining() {}
    close() { this.closed = true }
    get isConnected() { return !this.closed }
    get lastEventId() { return undefined }
  }
  return { Conn, user: { id: 'u-1' } }
})

vi.mock('@/utils/sse', () => ({
  createSSE: (url: string, opts: unknown) => new sse.Conn(url, opts),
}))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ userId: sse.user.id }),
}))

// ── 内存版 Web Locks（只实现本模块用到的 ifAvailable / signal / 回调 promise 决定持有时长）
type Waiter = { cb: (lock: unknown) => unknown; resolve: (v: unknown) => void; reject: (e: unknown) => void }

class FakeLocks {
  held = new Set<string>()
  queues = new Map<string, Waiter[]>()

  request(name: string, opts: { ifAvailable?: boolean; signal?: AbortSignal }, cb: (lock: unknown) => unknown) {
    return new Promise((resolve, reject) => {
      if (!this.held.has(name)) {
        this.grant(name, { cb, resolve, reject })
        return
      }
      if (opts.ifAvailable) {
        Promise.resolve().then(() => cb(null)).then(resolve, reject)
        return
      }
      const waiter = { cb, resolve, reject }
      const queue = this.queues.get(name) ?? []
      queue.push(waiter)
      this.queues.set(name, queue)
      opts.signal?.addEventListener('abort', () => {
        const q = this.queues.get(name) ?? []
        const i = q.indexOf(waiter)
        if (i >= 0) q.splice(i, 1)
        reject(new DOMException('aborted', 'AbortError'))
      })
    })
  }

  private grant(name: string, w: Waiter) {
    this.held.add(name)
    Promise.resolve()
      .then(() => w.cb({ name }))
      .then(
        (v) => { this.release(name); w.resolve(v) },
        (e) => { this.release(name); w.reject(e) },
      )
  }

  private release(name: string) {
    this.held.delete(name)
    const next = this.queues.get(name)?.shift()
    if (next) this.grant(name, next)
  }
}

// ── 内存版 BroadcastChannel：同名频道互通、不回给发送者自己（与浏览器语义一致）
class FakeChannel {
  static open: FakeChannel[] = []
  onmessage: ((ev: { data: unknown }) => void) | null = null
  closed = false
  constructor(public name: string) {
    FakeChannel.open.push(this)
  }
  postMessage(data: unknown) {
    for (const other of FakeChannel.open) {
      if (other === this || other.closed || other.name !== this.name) continue
      queueMicrotask(() => other.onmessage?.({ data: structuredClone(data) }))
    }
  }
  close() {
    this.closed = true
    FakeChannel.open = FakeChannel.open.filter((c) => c !== this)
  }
}

type Bus = typeof import('../projectEventStream')

async function openTab(user = 'u-1'): Promise<Bus> {
  vi.resetModules()
  sse.user.id = user
  return import('../projectEventStream')
}

const flush = async () => {
  for (let i = 0; i < 6; i++) await Promise.resolve()
}

const PID = '00000000-0000-0000-0000-000000000001'

beforeEach(() => {
  sse.Conn.all = []
  FakeChannel.open = []
  Object.defineProperty(globalThis.navigator, 'locks', { value: new FakeLocks(), configurable: true })
  vi.stubGlobal('BroadcastChannel', FakeChannel)
})

afterEach(() => {
  vi.unstubAllGlobals()
  delete (globalThis.navigator as unknown as { locks?: unknown }).locks
})

describe('同用户同项目：多个标签页只建一条连接', () => {
  it('第二个标签页跟随，事件经领导转发到两边', async () => {
    const tabA = await openTab()
    const seenA: unknown[] = []
    tabA.subscribeProjectEvent(PID, 'workpaper.content.updated', (d) => seenA.push(d))
    await flush()
    const tabB = await openTab()
    const seenB: unknown[] = []
    tabB.subscribeProjectEvent(PID, 'workpaper.content.updated', (d) => seenB.push(d))
    await flush()

    expect(sse.Conn.all).toHaveLength(1)
    const leaderConn = sse.Conn.all[0]
    leaderConn.openHandler?.()
    leaderConn.messageHandler?.({ revision: 7 }, 'workpaper.content.updated')
    await flush()
    expect(seenA).toEqual([{ revision: 7 }])
    expect(seenB).toEqual([{ revision: 7 }])
  })

  it('领导标签页退订后，排队的标签页接手建连，连上后两边都按断线重连恢复', async () => {
    const tabA = await openTab()
    const subA = tabA.subscribeProjectEvent(PID, 'e', () => {})
    await flush()
    const tabB = await openTab()
    const reconnectB = vi.fn()
    const seenB: unknown[] = []
    tabB.subscribeProjectEvent(PID, 'e', (d) => seenB.push(d), { onReconnect: reconnectB })
    await flush()
    sse.Conn.all[0].openHandler?.()

    subA.close()
    await flush()
    expect(sse.Conn.all[0].closed).toBe(true)
    expect(sse.Conn.all).toHaveLength(2)
    const takeoverConn = sse.Conn.all[1]
    expect(reconnectB).not.toHaveBeenCalled()
    takeoverConn.openHandler?.()
    // 接手期间可能漏事件：首次连上即按断线重连通知（消费者据此清缓存 / 重拉）
    expect(reconnectB).toHaveBeenCalledTimes(1)
    takeoverConn.messageHandler?.('x', 'e')
    expect(seenB).toEqual(['x'])
  })

  it('领导断线重连 / 降级都同步到跟随的标签页', async () => {
    const tabA = await openTab()
    tabA.subscribeProjectEvent(PID, 'e', () => {})
    await flush()
    const tabB = await openTab()
    const reconnectB = vi.fn()
    const degradedB = vi.fn()
    tabB.subscribeProjectEvent(PID, 'e', () => {}, { onReconnect: reconnectB, onDegraded: degradedB })
    await flush()
    const conn = sse.Conn.all[0]
    conn.openHandler?.()
    conn.openHandler?.() // 第二次 open = 断线后重连成功
    await flush()
    expect(reconnectB).toHaveBeenCalledTimes(1)
    for (let i = 0; i < 6; i++) conn.errorHandler?.(new Error('down'))
    await flush()
    expect(degradedB).toHaveBeenCalledTimes(1)
    expect(tabB.isProjectStreamDegraded(PID)).toBe(true)
  })

  it('只在跟随时排队：跟随标签页先退订 ⇒ 不再接手，也不建连接', async () => {
    const tabA = await openTab()
    const subA = tabA.subscribeProjectEvent(PID, 'e', () => {})
    await flush()
    const tabB = await openTab()
    const subB = tabB.subscribeProjectEvent(PID, 'e', () => {})
    await flush()
    subB.close()
    subA.close()
    await flush()
    expect(sse.Conn.all).toHaveLength(1)
  })
})

describe('不共用的情形', () => {
  it('不同用户各建一条（事件不得跨用户转发）', async () => {
    const tabA = await openTab('u-1')
    tabA.subscribeProjectEvent(PID, 'e', () => {})
    await flush()
    const tabB = await openTab('u-2')
    const seenB: unknown[] = []
    tabB.subscribeProjectEvent(PID, 'e', (d) => seenB.push(d))
    await flush()
    expect(sse.Conn.all).toHaveLength(2)
    sse.Conn.all[0].messageHandler?.('only-for-u1', 'e')
    await flush()
    expect(seenB).toEqual([])
  })

  it('浏览器不支持 Web Locks ⇒ 退回每个标签页各自一条', async () => {
    delete (globalThis.navigator as unknown as { locks?: unknown }).locks
    const tabA = await openTab()
    tabA.subscribeProjectEvent(PID, 'e', () => {})
    const tabB = await openTab()
    tabB.subscribeProjectEvent(PID, 'e', () => {})
    await flush()
    expect(sse.Conn.all).toHaveLength(2)
  })

  it('拿不到用户 id ⇒ 不共用', async () => {
    const tabA = await openTab('')
    tabA.subscribeProjectEvent(PID, 'e', () => {})
    const tabB = await openTab('')
    tabB.subscribeProjectEvent(PID, 'e', () => {})
    await flush()
    expect(sse.Conn.all).toHaveLength(2)
  })
})
