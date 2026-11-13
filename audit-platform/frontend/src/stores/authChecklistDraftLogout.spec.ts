import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const authPost = vi.fn()
const broadcastLogout = vi.fn()
let receivedAuthHandlers: { onLogout?: () => void } | undefined

vi.mock('axios', () => ({
  default: { create: vi.fn(() => ({ post: authPost })) },
}))
vi.mock('@/utils/http', () => ({ default: { get: vi.fn() } }))
vi.mock('@/utils/aiChatCacheCleanup', () => ({ clearOnLogout: vi.fn() }))
vi.mock('@/services/requestIdentityEpoch', () => ({ advanceRequestIdentityEpoch: vi.fn() }))
vi.mock('@/utils/crossWindowAuth', () => ({
  broadcastTokenUpdate: vi.fn(),
  broadcastLogout,
  listenAuthEvents: vi.fn((handlers: { onLogout?: () => void }) => {
    receivedAuthHandlers = handlers
  }),
  singleFlightRefresh: async (fn: () => Promise<unknown>) => fn(),
}))

setActivePinia(createPinia())
const { useAuthStore } = await import('./auth')

function clearStorage(): void {
  localStorage.clear()
  sessionStorage.clear()
}

describe('认证登出的底稿草稿边界', () => {
  beforeEach(() => {
    clearStorage()
    setActivePinia(createPinia())
    authPost.mockReset()
    authPost.mockResolvedValue({ data: {} })
    broadcastLogout.mockReset()
  })

  afterEach(clearStorage)

  it('本地 logout 在网络请求前清除所有受管草稿，同时保留无关偏好', async () => {
    const store = useAuthStore()
    store.token = 'access-token'
    store.refreshToken = 'refresh-token'
    store.user = { id: 'user-1' } as any
    sessionStorage.setItem('token', 'access-token')
    sessionStorage.setItem('refreshToken', 'refresh-token')
    sessionStorage.setItem('user', JSON.stringify(store.user))
    localStorage.setItem('strict-cas-draft:user-1:wp-1:G1-a', 'strict')
    localStorage.setItem('g7-main-draft:user-1:wp-1:G7-a', 'g7')
    localStorage.setItem('gt:stocktake-draft:user-1:project-1:wp-1:stocktake_A', 'stocktake')
    localStorage.setItem('gt:h-stocktake-draft:user-1:project-1:wp-1:h_stocktake_A', 'h-stocktake')
    localStorage.setItem('theme', 'dark')

    await store.logout()

    expect(localStorage.getItem('strict-cas-draft:user-1:wp-1:G1-a')).toBeNull()
    expect(localStorage.getItem('g7-main-draft:user-1:wp-1:G7-a')).toBeNull()
    expect(localStorage.getItem('gt:stocktake-draft:user-1:project-1:wp-1:stocktake_A')).toBeNull()
    expect(localStorage.getItem('gt:h-stocktake-draft:user-1:project-1:wp-1:h_stocktake_A')).toBeNull()
    expect(localStorage.getItem('theme')).toBe('dark')
    expect(broadcastLogout).toHaveBeenCalledOnce()
    expect(authPost).toHaveBeenCalledOnce()
  })
})

describe('跨窗口 logout 的草稿边界', () => {
  afterEach(clearStorage)

  it('收到其他窗口 logout 广播时同样清除敏感草稿与会话', async () => {
    await new Promise<void>((resolve) => setTimeout(resolve, 0))
    expect(receivedAuthHandlers?.onLogout).toBeTypeOf('function')
    sessionStorage.setItem('token', 'access-token')
    sessionStorage.setItem('refreshToken', 'refresh-token')
    sessionStorage.setItem('user', JSON.stringify({ id: 'user-1' }))
    localStorage.setItem('g7-sub-draft:user-1:wp-1:G7-8-a', 'g7')
    localStorage.setItem('h10-draft:user-1:wp-1:H10-a', 'h10')
    localStorage.setItem('gt:stocktake-draft:user-1:project-1:wp-1:stocktake_A', 'stocktake')
    localStorage.setItem('theme', 'dark')

    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    receivedAuthHandlers?.onLogout?.()
    consoleError.mockRestore()

    expect(sessionStorage.getItem('token')).toBeNull()
    expect(sessionStorage.getItem('refreshToken')).toBeNull()
    expect(sessionStorage.getItem('user')).toBeNull()
    expect(localStorage.getItem('g7-sub-draft:user-1:wp-1:G7-8-a')).toBeNull()
    expect(localStorage.getItem('h10-draft:user-1:wp-1:H10-a')).toBeNull()
    expect(localStorage.getItem('gt:stocktake-draft:user-1:project-1:wp-1:stocktake_A')).toBeNull()
    expect(localStorage.getItem('theme')).toBe('dark')
  })
})