/**
 * http.ts × auth store · 401 → 刷新令牌 → 重放原请求（真拦截器 + 真 store，只替换网络层）
 *
 * 复现 2026-09-30 实测的「登录约 2 小时后无限整页重载」整条链（根因见 `stores/__tests__/authSession.spec.ts`）：
 * - 刷新成功：必须用**新** token 重放原请求并拿到解包后的业务数据（修复前重放带 `Bearer undefined` ⇒ 再 401 ⇒ 登出）；
 * - 刷新失败：跳转 /login 时本地会话必须**已经**清空（修复前登出请求被页面卸载中断、清理不执行 ⇒ 守卫弹回首页 ⇒ 循环）。
 *
 * 网络层替换方式：`axios.create()` 在创建时合并 `axios.defaults` ⇒ 先改 defaults.adapter 再动态 import，
 * http.ts 的 `http` 与 auth store 的 `authHttp` 两个实例都走同一个假适配器。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('nprogress', () => ({ default: { start: vi.fn(), done: vi.fn(), inc: vi.fn() } }))
vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() } }))
vi.mock('@/composables/useVersionCheck', () => ({ versionBridge: { check: vi.fn(), push: vi.fn() } }))

const PROBE = '/api/probe'
let calls: string[] = []
let location: { href: string }

async function setup() {
  vi.resetModules()
  const axiosMod = await import('axios')
  const axios = axiosMod.default
  const { AxiosError } = axiosMod
  const envelope = (config: any, data: unknown) => ({
    data: { code: 200, message: 'success', data }, status: 200, statusText: 'OK', headers: {}, config,
  })
  const unauthorized = (config: any): never => {
    const response = { data: { code: 401, message: '无效的认证凭据' }, status: 401, statusText: 'Unauthorized', headers: {}, config }
    throw new AxiosError('Request failed with status code 401', 'ERR_BAD_REQUEST', config, null, response as any)
  }
  axios.defaults.adapter = async (config: any) => {
    const auth = config.headers?.get?.('Authorization') ?? config.headers?.Authorization
    calls.push(`${String(config.method).toUpperCase()} ${config.url}${auth ? ` ${auth}` : ''}`)
    if (config.url === '/api/auth/refresh') {
      if (JSON.parse(config.data).refresh_token === 'valid-refresh') {
        return envelope(config, { access_token: 'new-access', refresh_token: 'new-refresh', token_type: 'bearer' })
      }
      return unauthorized(config)
    }
    if (config.url === '/api/auth/logout') return new Promise(() => {}) // 整页跳转会中断它：永不返回
    if (config.url === PROBE && auth === 'Bearer new-access') return envelope(config, { ok: true })
    return unauthorized(config)
  }
  const { createPinia, setActivePinia } = await import('pinia')
  setActivePinia(createPinia())
  const http = (await import('@/utils/http')).default
  const { useAuthStore } = await import('@/stores/auth')
  return { http, store: useAuthStore() }
}

beforeEach(() => {
  calls = []
  sessionStorage.clear()
  localStorage.clear()
  location = { href: 'http://localhost/projects' }
  vi.stubGlobal('location', location)
})

describe('401 → 刷新令牌', () => {
  it('刷新成功：用新 token 重放原请求并返回解包后的数据，会话更新为新令牌对', async () => {
    sessionStorage.setItem('token', 'expired-access')
    sessionStorage.setItem('refreshToken', 'valid-refresh')
    const { http, store } = await setup()
    const res = await http.get(PROBE)
    expect(res.data).toEqual({ ok: true })
    expect(calls).toEqual([
      `GET ${PROBE} Bearer expired-access`,
      'POST /api/auth/refresh',
      `GET ${PROBE} Bearer new-access`,
    ])
    expect([store.token, store.refreshToken]).toEqual(['new-access', 'new-refresh'])
    expect(location.href).toBe('http://localhost/projects')
  })

  it('刷新失败：跳转 /login 时本地会话已清空（新页面不会被守卫弹回首页）', async () => {
    sessionStorage.setItem('token', 'expired-access')
    sessionStorage.setItem('refreshToken', 'revoked-refresh')
    const { http, store } = await setup()
    await expect(http.get(PROBE)).rejects.toMatchObject({ response: { status: 401 } })
    expect(location.href).toBe('/login')
    expect(['token', 'refreshToken', 'user'].map((k) => sessionStorage.getItem(k))).toEqual([null, null, null])
    expect(store.isAuthenticated).toBe(false)
    expect(calls.slice(0, 2)).toEqual([`GET ${PROBE} Bearer expired-access`, 'POST /api/auth/refresh'])
  })
})
