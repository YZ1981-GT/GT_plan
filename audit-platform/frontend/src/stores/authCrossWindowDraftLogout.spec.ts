import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const authPost = vi.fn()

vi.mock('axios', () => ({
  default: { create: vi.fn(() => ({ post: authPost })) },
}))
vi.mock('@/utils/http', () => ({ default: { get: vi.fn() } }))
vi.mock('@/utils/aiChatCacheCleanup', () => ({ clearOnLogout: vi.fn() }))
vi.mock('@/services/requestIdentityEpoch', () => ({ advanceRequestIdentityEpoch: vi.fn() }))
vi.mock('@/utils/clientInstance', () => ({ getClientInstanceId: () => 'self-window' }))
vi.mock('@/utils/cloneable', () => ({ toCloneable: (value: unknown) => value }))

class MockBroadcastChannel {
  static instances: MockBroadcastChannel[] = []
  private listeners = new Set<(event: MessageEvent<any>) => void>()

  constructor(_name: string) {
    MockBroadcastChannel.instances.push(this)
  }

  addEventListener(type: string, listener: (event: MessageEvent<any>) => void): void {
    if (type === 'message') this.listeners.add(listener)
  }

  removeEventListener(type: string, listener: (event: MessageEvent<any>) => void): void {
    if (type === 'message') this.listeners.delete(listener)
  }

  postMessage(_message: unknown): void {}

  emit(message: unknown): void {
    for (const listener of this.listeners) listener({ data: message } as MessageEvent)
  }
}

function clearStorage(): void {
  localStorage.clear()
  sessionStorage.clear()
}

describe('跨窗口 logout 的真实消息链路', () => {
  beforeEach(() => {
    vi.resetModules()
    MockBroadcastChannel.instances = []
    vi.stubGlobal('BroadcastChannel', MockBroadcastChannel)
    clearStorage()
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    clearStorage()
  })

  it('不同 senderId 的 BroadcastChannel logout 会清除会话和敏感草稿', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    try {
      await import('@/stores/auth')
      await new Promise<void>((resolve) => setTimeout(resolve, 0))
      const channel = MockBroadcastChannel.instances[0]
      expect(channel).toBeDefined()

      sessionStorage.setItem('token', 'access-token')
      sessionStorage.setItem('refreshToken', 'refresh-token')
      sessionStorage.setItem('user', JSON.stringify({ id: 'user-1' }))
      localStorage.setItem('g7-equity-method-draft:user-1:wp-1:G7-4-a', 'g7')
      localStorage.setItem('h10-draft:user-1:wp-1:H10-a', 'h10')
      localStorage.setItem('gt:h-stocktake-draft:user-1:project-1:wp-1:h_stocktake_A', 'stocktake')
      localStorage.setItem('theme', 'dark')

      channel.emit({ type: 'logout', senderId: 'another-window' })

      expect(sessionStorage.getItem('token')).toBeNull()
      expect(sessionStorage.getItem('refreshToken')).toBeNull()
      expect(sessionStorage.getItem('user')).toBeNull()
      expect(localStorage.getItem('g7-equity-method-draft:user-1:wp-1:G7-4-a')).toBeNull()
      expect(localStorage.getItem('h10-draft:user-1:wp-1:H10-a')).toBeNull()
      expect(localStorage.getItem('gt:h-stocktake-draft:user-1:project-1:wp-1:h_stocktake_A')).toBeNull()
      expect(localStorage.getItem('theme')).toBe('dark')
    } finally {
      consoleError.mockRestore()
    }
  })
})