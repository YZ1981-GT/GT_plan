/**
 * 公式 E2E 共享辅助函数。
 */
import type { Page, APIRequestContext } from '@playwright/test'
import { expect } from '@playwright/test'
import { defaultCredentials, loadManifest } from './manifest'

const BACKEND = process.env.PLAYWRIGHT_BACKEND_URL || 'http://127.0.0.1:9980'

/** 通过 API 登录并把 token 注入浏览器上下文。返回 auth 对象（含 access_token）。 */
export async function loginAndInstall(
  page: Page,
  request: APIRequestContext,
  overrides?: { username?: string; password?: string },
) {
  const { username, password } = { ...defaultCredentials(), ...overrides }
  const resp = await request.post(`${BACKEND}/api/auth/login`, {
    data: { username, password },
    timeout: 60_000,
  })
  expect(resp.ok(), `登录失败 ${resp.status()} (${username})`).toBeTruthy()
  const body = await resp.json()
  const data = body?.data ?? body
  expect(data?.access_token, '登录响应缺少 access_token').toBeTruthy()

  // 注入浏览器上下文
  await page.addInitScript(
    (auth: any) => {
      sessionStorage.setItem('token', auth.access_token)
      if (auth.refresh_token) sessionStorage.setItem('refreshToken', auth.refresh_token)
      if (auth.user) sessionStorage.setItem('user', JSON.stringify(auth.user))
      localStorage.setItem('token', auth.access_token)
    },
    data,
  )

  // 同时把 token 存到环境变量供纯 API 测试使用
  process.env.FH_E2E_TOKEN = data.access_token

  return data
}

/** 断言健康检查返回 healthy 或 degraded（PG 和 Redis 可用即可）。 */
export async function assertHealthy(request: APIRequestContext) {
  const resp = await request.get(`${BACKEND}/api/health`, { timeout: 30_000 })
  expect(resp.ok(), `/api/health 不可达 (${resp.status()})`).toBeTruthy()
  const body = await resp.json()
  const data = body?.data ?? body
  const status = data?.status
  // healthy = 完全正常，degraded = PG/Redis ok 但有 schema drift 等非阻断问题
  // CI 一次性库上应该是 healthy；共享库可能 degraded
  expect(
    ['healthy', 'degraded'].includes(status),
    `健康检查状态异常: ${status}（只允许 healthy 或 degraded）`,
  ).toBe(true)
  // PG 和 Redis 必须 ok
  const services = data?.services
  if (services) {
    expect(services.postgres, 'PG 不可用').toBe('ok')
    expect(services.redis, 'Redis 不可用').toBe('ok')
  }
}

/** 返回单体项目 id。 */
export function standaloneProjectId(): string {
  return process.env.FH_E2E_STANDALONE_ID || loadManifest().standalone.project_id
}

/** 返回合并项目 id。 */
export function consolProjectId(): string {
  return process.env.FH_E2E_CONSOL_ID || loadManifest().consolidated.project_id
}
