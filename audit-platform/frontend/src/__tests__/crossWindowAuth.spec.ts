/**
 * crossWindowAuth — BroadcastChannel 跨窗口认证同步测试
 *
 * spec: multi-window-ledger-workbench Phase 4 Task 22
 *
 * 测试策略：使用真实 BroadcastChannel（jsdom 环境下需 polyfill）
 * 或在不支持时验证降级行为。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock clientInstance 避免 crypto.randomUUID 在测试环境不可用
vi.mock('@/utils/clientInstance', () => ({
  getClientInstanceId: () => 'test-instance-001',
}))

// jsdom 不支持 BroadcastChannel，手动模拟
class MockBroadcastChannel {
  static _channels = new Map<string, Set<MockBroadcastChannel>>()
  name: string
  onmessage: ((ev: any) => void) | null = null
  private _listeners: Array<(ev: any) => void> = []

  constructor(name: string) {
    this.name = name
    if (!MockBroadcastChannel._channels.has(name)) {
      MockBroadcastChannel._channels.set(name, new Set())
    }
    MockBroadcastChannel._channels.get(name)!.add(this)
  }

  postMessage(data: any) {
    // 与真实 BroadcastChannel 一样先结构化克隆：响应式 Proxy 等不可克隆的载荷在这里抛 DataCloneError
    //（原 mock 直接传引用，测不出会话回执带响应式 user 发不出去的缺陷）
    const cloned = structuredClone(data)
    const peers = MockBroadcastChannel._channels.get(this.name) ?? new Set()
    for (const peer of peers) {
      if (peer === this) continue
      const ev = { data: cloned }
      if (peer.onmessage) peer.onmessage(ev)
      for (const fn of peer._listeners) fn(ev)
    }
  }

  addEventListener(_type: string, fn: (ev: any) => void) {
    this._listeners.push(fn)
  }

  removeEventListener(_type: string, fn: (ev: any) => void) {
    this._listeners = this._listeners.filter(f => f !== fn)
  }

  close() {
    MockBroadcastChannel._channels.get(this.name)?.delete(this)
  }

  static reset() {
    MockBroadcastChannel._channels.clear()
  }
}

// 注入 global
;(globalThis as any).BroadcastChannel = MockBroadcastChannel

beforeEach(() => {
  MockBroadcastChannel.reset()
  vi.resetModules()
})

describe('crossWindowAuth', () => {
  it('broadcastTokenUpdate 广播到其他频道实例', async () => {
    // 动态导入确保每次使用新的模块实例
    const mod = await import('@/utils/crossWindowAuth')

    const receiver = new MockBroadcastChannel('gt-auth')
    const received: any[] = []
    receiver.addEventListener('message', (ev: any) => received.push(ev.data))

    mod.broadcastTokenUpdate('new-access-token', 'new-refresh-token')

    expect(received.length).toBe(1)
    expect(received[0].type).toBe('token-updated')
    expect(received[0].token).toBe('new-access-token')
    expect(received[0].refreshToken).toBe('new-refresh-token')
    expect(received[0].senderId).toBe('test-instance-001')

    receiver.close()
  })

  it('broadcastLogout 广播登出事件', async () => {
    const mod = await import('@/utils/crossWindowAuth')

    const receiver = new MockBroadcastChannel('gt-auth')
    const received: any[] = []
    receiver.addEventListener('message', (ev: any) => received.push(ev.data))

    mod.broadcastLogout()

    expect(received.length).toBe(1)
    expect(received[0].type).toBe('logout')
    expect(received[0].senderId).toBe('test-instance-001')

    receiver.close()
  })

  it('requestSession 超时后返回 null', async () => {
    vi.useFakeTimers()
    const mod = await import('@/utils/crossWindowAuth')

    const promise = mod.requestSession()
    // 快进 2.5 秒（超时 2 秒）
    await vi.advanceTimersByTimeAsync(2500)

    const result = await promise
    expect(result).toBeNull()

    vi.useRealTimers()
  })

  it('新标签页要会话：已登录标签页的 user 是响应式（Pinia state）也能回执', async () => {
    const mod = await import('@/utils/crossWindowAuth')
    const { reactive } = await import('vue')
    const state = reactive({ user: { id: 'u1', username: 'admin', roles: ['admin'] } })
    mod.listenAuthEvents({ onSessionRequest: () => ({ token: 't', refreshToken: 'r', user: state.user }) })

    const otherTab = new MockBroadcastChannel('gt-auth')
    const received: any[] = []
    otherTab.addEventListener('message', (ev: any) => received.push(ev.data))
    otherTab.postMessage({ type: 'session-request', senderId: 'other-tab' })

    expect(received).toEqual([{
      type: 'session-response', token: 't', refreshToken: 'r',
      user: { id: 'u1', username: 'admin', roles: ['admin'] }, senderId: 'test-instance-001',
    }])
    otherTab.close()
  })

  it('新标签页会话接力：已登录标签页回执后才结束，apply 拿到会话', async () => {
    sessionStorage.removeItem('token')
    const mod = await import('@/utils/crossWindowAuth')
    const loggedIn = new MockBroadcastChannel('gt-auth')
    loggedIn.addEventListener('message', (ev: any) => {
      if (ev.data.type === 'session-request') {
        setTimeout(() => loggedIn.postMessage({ type: 'session-response', token: 't', refreshToken: 'r', user: { id: 'u1' }, senderId: 'tab-a' }), 50)
      }
    })
    const applied: any[] = []
    let settled = false
    const handoff = mod.startSessionHandoff((s) => { applied.push(s) })
    void mod.awaitSessionHandoff().then(() => { settled = true })
    await new Promise((r) => setTimeout(r, 10))
    expect(settled).toBe(false) // 回执未到：守卫在等，不会先跳登录页
    await handoff
    expect(settled).toBe(true)
    expect(applied).toEqual([{ token: 't', refreshToken: 'r', user: { id: 'u1' } }])
    loggedIn.close()
  })

  it('本页已有令牌：不要会话，接力立即结束', async () => {
    sessionStorage.setItem('token', 'mine')
    try {
      const mod = await import('@/utils/crossWindowAuth')
      const peer = new MockBroadcastChannel('gt-auth')
      const received: any[] = []
      peer.addEventListener('message', (ev: any) => received.push(ev.data))
      const apply = vi.fn()
      await mod.startSessionHandoff(apply)
      expect(received).toEqual([])
      expect(apply).not.toHaveBeenCalled()
      peer.close()
    } finally {
      sessionStorage.removeItem('token')
    }
  })

  it('singleFlightRefresh 无 Web Locks 时降级直接执行', async () => {
    // jsdom 没有 navigator.locks
    const original = (navigator as any).locks
    delete (navigator as any).locks

    const mod = await import('@/utils/crossWindowAuth')
    const fn = vi.fn().mockResolvedValue('result')

    const result = await mod.singleFlightRefresh(fn)
    expect(fn).toHaveBeenCalledTimes(1)
    expect(result).toBe('result')

    if (original) (navigator as any).locks = original
  })
})
