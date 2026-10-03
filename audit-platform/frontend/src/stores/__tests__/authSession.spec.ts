/**
 * auth store · 令牌刷新与登出
 *
 * 2026-09-30 Playwright 实测：登录约 2 小时（access token 到期）后页面**无限整页重载**（137 轮，每轮 12 个 401 +
 * 一次 /api/auth/refresh 401）。两处根因，缺一不成环：
 *
 * 1. `refreshAccessToken` 未解 `{code, message, data}` 信封（`authHttp` 不经 http.ts 拦截器、不自动解包）
 *    ⇒ 把 "undefined" 存成 token、丢掉后端已轮换出的新 refresh_token（旧的随即被拉黑）⇒ 刷新从未成功过；
 * 2. `logout` 把本地清理放在 await 登出请求之后，而 http.ts 调它**不 await**、随即 `location.href = '/login'`
 *    ⇒ 页面卸载、清理永不执行 ⇒ 新页面仍「已登录」⇒ 路由守卫把 /login 重定向回首页 ⇒ 401 ⇒ 循环。
 *
 * 本文件钉 store 自身语义；与 http.ts 组合后的整条链见 `utils/__tests__/httpTokenRefresh.spec.ts`。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const mocks = vi.hoisted(() => ({ post: vi.fn() }))

vi.mock('axios', () => {
  const instance = {
    post: mocks.post,
    get: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  }
  return { default: { ...instance, create: vi.fn(() => instance) } }
})
vi.mock('@/utils/http', () => ({ default: { get: vi.fn() } }))

import { useAuthStore } from '@/stores/auth'

const SESSION_KEYS = ['token', 'refreshToken', 'user'] as const

function seedSession(token = 'old-access', refresh = 'old-refresh'): void {
  sessionStorage.setItem('token', token)
  sessionStorage.setItem('refreshToken', refresh)
  sessionStorage.setItem('user', JSON.stringify({ id: 'u1', username: 'admin', role: 'admin' }))
}

beforeEach(() => {
  sessionStorage.clear()
  localStorage.clear()
  mocks.post.mockReset()
  setActivePinia(createPinia())
})

describe('refreshAccessToken', () => {
  it('解信封：存新 access_token 与轮换后的新 refresh_token（真实后端响应形态）', async () => {
    seedSession()
    mocks.post.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: { access_token: 'new-access', refresh_token: 'new-refresh', token_type: 'bearer' } },
    })
    const store = useAuthStore()
    await store.refreshAccessToken()
    expect(mocks.post).toHaveBeenCalledWith('/api/auth/refresh', { refresh_token: 'old-refresh' })
    expect([store.token, store.refreshToken]).toEqual(['new-access', 'new-refresh'])
    expect([sessionStorage.getItem('token'), sessionStorage.getItem('refreshToken')]).toEqual(['new-access', 'new-refresh'])
  })

  it('平铺响应（无信封）同样可用', async () => {
    seedSession()
    mocks.post.mockResolvedValueOnce({ data: { access_token: 'a2', refresh_token: 'r2' } })
    const store = useAuthStore()
    await store.refreshAccessToken()
    expect([store.token, store.refreshToken]).toEqual(['a2', 'r2'])
  })

  it('响应缺 access_token ⇒ 抛错，且不把 "undefined" 写成 token', async () => {
    seedSession()
    mocks.post.mockResolvedValueOnce({ data: { code: 200, message: 'success', data: {} } })
    const store = useAuthStore()
    await expect(store.refreshAccessToken()).rejects.toThrow('刷新令牌响应缺少 access_token')
    expect(store.token).toBe('old-access')
    expect(sessionStorage.getItem('token')).toBe('old-access')
  })
})

describe('logout', () => {
  it('本地会话在首个 await 之前清空（调用方不 await 即整页跳转时也生效）', () => {
    seedSession('t', 'r')
    mocks.post.mockReturnValueOnce(new Promise(() => {})) // 页面卸载中断请求：永不返回
    const store = useAuthStore()
    void store.logout()
    expect([store.token, store.refreshToken, store.user]).toEqual([null, null, null])
    expect(SESSION_KEYS.map((k) => sessionStorage.getItem(k))).toEqual([null, null, null])
    expect(store.isAuthenticated).toBe(false)
    // 登出请求仍携带清空前的凭据（先取值再清）
    expect(mocks.post).toHaveBeenCalledWith(
      '/api/auth/logout', { refresh_token: 'r' }, { headers: { Authorization: 'Bearer t' } },
    )
  })

  it('服务端登出失败也完成本地登出且不抛错', async () => {
    seedSession()
    mocks.post.mockRejectedValueOnce(new Error('network'))
    const store = useAuthStore()
    await expect(store.logout()).resolves.toBeUndefined()
    expect(store.isAuthenticated).toBe(false)
    expect(SESSION_KEYS.map((k) => sessionStorage.getItem(k))).toEqual([null, null, null])
  })
})
