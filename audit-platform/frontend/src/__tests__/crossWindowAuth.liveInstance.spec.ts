/**
 * 跨窗口认证按「当前」窗口编号判断是不是自己发的（spec workpaper-multi-window-lock-gaps R1.4）。
 *
 * 认证监听在启动时就装上；「复制标签页」随后认领到新编号。原先监听记下启动时的旧编号（= 原标签页的编号），
 * 原标签页广播的令牌更新 / 登出都被当成自己发的丢掉。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { instance } = vi.hoisted(() => ({ instance: { id: 'copied-from-tab-a' } }))
vi.mock('@/utils/clientInstance', () => ({ getClientInstanceId: () => instance.id }))

class MockBroadcastChannel {
  static channels = new Map<string, Set<MockBroadcastChannel>>()
  private listeners: Array<(ev: { data: unknown }) => void> = []
  constructor(public name: string) {
    if (!MockBroadcastChannel.channels.has(name)) MockBroadcastChannel.channels.set(name, new Set())
    MockBroadcastChannel.channels.get(name)!.add(this)
  }
  postMessage(data: unknown) {
    const cloned = structuredClone(data)
    for (const peer of MockBroadcastChannel.channels.get(this.name) ?? []) {
      if (peer !== this) peer.listeners.forEach((fn) => fn({ data: cloned }))
    }
  }
  addEventListener(_t: string, fn: (ev: { data: unknown }) => void) { this.listeners.push(fn) }
  removeEventListener(_t: string, fn: (ev: { data: unknown }) => void) { this.listeners = this.listeners.filter((f) => f !== fn) }
  close() { MockBroadcastChannel.channels.get(this.name)?.delete(this) }
}
;(globalThis as any).BroadcastChannel = MockBroadcastChannel

beforeEach(() => {
  MockBroadcastChannel.channels.clear()
  instance.id = 'copied-from-tab-a'
  vi.resetModules()
})

describe('crossWindowAuth：认领换号后', () => {
  it('原标签页（旧编号）发的令牌更新与登出照常收到，自己新编号发的仍忽略', async () => {
    const mod = await import('@/utils/crossWindowAuth')
    const onTokenUpdate = vi.fn()
    const onLogout = vi.fn()
    mod.listenAuthEvents({ onTokenUpdate, onLogout }) // 启动时装上：此刻还是复制来的编号

    instance.id = 'claimed-fresh' // 认领：编号被原标签页占着 ⇒ 换新号

    const tabA = new MockBroadcastChannel('gt-auth')
    tabA.postMessage({ type: 'token-updated', token: 'rotated', refreshToken: 'rotated-r', senderId: 'copied-from-tab-a' })
    tabA.postMessage({ type: 'logout', senderId: 'copied-from-tab-a' })
    tabA.postMessage({ type: 'logout', senderId: 'claimed-fresh' })

    expect(onTokenUpdate).toHaveBeenCalledWith('rotated', 'rotated-r')
    expect(onLogout).toHaveBeenCalledTimes(1)
    tabA.close()
  })

  it('要会话时用当前编号署名，并按当前编号认回执', async () => {
    const mod = await import('@/utils/crossWindowAuth')
    instance.id = 'claimed-fresh'
    const tabA = new MockBroadcastChannel('gt-auth')
    const seen: any[] = []
    tabA.addEventListener('message', (ev: any) => {
      seen.push(ev.data)
      tabA.postMessage({ type: 'session-response', token: 't', refreshToken: 'r', user: null, senderId: 'tab-a' })
    })

    const session = await mod.requestSession()

    expect(seen[0]).toMatchObject({ type: 'session-request', senderId: 'claimed-fresh' })
    expect(session).toEqual({ token: 't', refreshToken: 'r', user: null })
    tabA.close()
  })
})
