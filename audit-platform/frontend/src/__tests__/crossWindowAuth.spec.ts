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
    const peers = MockBroadcastChannel._channels.get(this.name) ?? new Set()
    for (const peer of peers) {
      if (peer === this) continue
      const ev = { data }
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
