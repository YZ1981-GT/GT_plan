/**
 * 公式 E2E 共享辅助函数。
 *
 * spec formula-management-repair-closure R7：用例只调真实存在的接口与页面，断言具体状态码与业务值；
 * 种子缺数据的用例显式 `test.skip(条件, 原因)`，不再「404 就 return / 不是 500 就算过」。
 */
import type { Page, APIRequestContext } from '@playwright/test'
import { expect, test } from '@playwright/test'
import { defaultCredentials, loadManifest } from './manifest'

export const BACKEND = process.env.PLAYWRIGHT_BACKEND_URL || 'http://127.0.0.1:9980'

async function login(request: APIRequestContext, overrides?: { username?: string; password?: string }) {
  const { username, password } = { ...defaultCredentials(), ...overrides }
  const resp = await request.post(`${BACKEND}/api/auth/login`, { data: { username, password }, timeout: 60_000 })
  expect(resp.ok(), `登录失败 ${resp.status()} (${username})`).toBeTruthy()
  const body = await resp.json()
  const data = body?.data ?? body
  expect(data?.access_token, '登录响应缺少 access_token').toBeTruthy()
  return data
}

/** 通过 API 登录并把 token 注入浏览器上下文。返回 auth 对象（含 access_token）。 */
export async function loginAndInstall(
  page: Page,
  request: APIRequestContext,
  overrides?: { username?: string; password?: string },
) {
  const data = await login(request, overrides)
  await page.addInitScript(
    (auth: any) => {
      sessionStorage.setItem('token', auth.access_token)
      if (auth.refresh_token) sessionStorage.setItem('refreshToken', auth.refresh_token)
      if (auth.user) sessionStorage.setItem('user', JSON.stringify(auth.user))
    },
    data,
  )
  process.env.FH_E2E_TOKEN = data.access_token
  return data
}

/** 纯接口用例：登录拿 token（不碰浏览器）。 */
export async function apiToken(request: APIRequestContext): Promise<string> {
  return (await login(request)).access_token as string
}

export interface ApiResult<T = any> {
  status: number
  /** 2xx 时：响应信封里的 data（无信封则整个响应体） */
  data: T
  /** 非 2xx 时：平台错误信封的 message（HTTPException 的 detail 原样放在这里，可能是字符串或对象） */
  error: any
}

/** 带 token 调后端；统一拆信封（成功 `{code, message, data}`，失败 `{code, message: detail}`）。 */
export async function api<T = any>(
  request: APIRequestContext, token: string, method: 'GET' | 'POST' | 'PUT' | 'DELETE', path: string,
  opts: { data?: unknown; params?: Record<string, string | number | boolean> } = {},
): Promise<ApiResult<T>> {
  const resp = await request.fetch(`${BACKEND}${path}`, {
    method, data: opts.data as any, params: opts.params, timeout: 60_000,
    headers: { Authorization: `Bearer ${token}` },
  })
  const text = await resp.text()
  let body: any = null
  try { body = text ? JSON.parse(text) : null } catch { body = text }
  const ok = resp.ok()
  return { status: resp.status(), data: ok ? (body?.data ?? body) : (null as any), error: ok ? null : (body?.message ?? body?.detail ?? body) }
}

/** 本次运行的唯一后缀：同一库上重跑不会撞上一次留下的公式位 */
export function runTag(): string {
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

/**
 * 会写公式数据的用例，开头先确认后端连的是只有 E2E 种子项目的一次性库。
 *
 * 全局发布（作用范围 `*`）会改库里所有项目的有效公式；照 global-setup 注释里的本地做法
 * （`seed --allow-shared` + `SKIP_FORMULA_SEED=1`）跑到共享库上，就会改真实项目。
 * 本地看到非 E2E 项目 ⇒ 显式跳过并写明原因；CI 用的是一次性库，看到了说明环境错了 ⇒ 直接失败。
 */
export async function requireIsolatedDb(request: APIRequestContext, token: string) {
  const r = await api<any[]>(request, token, 'GET', '/api/projects')
  expect(r.status, JSON.stringify(r.error)).toBe(200)
  const others = (r.data || []).filter((p) => !String(p?.name || p?.client_name || '').startsWith('【E2E】'))
  const sample = others[0]?.name || others[0]?.client_name || ''
  const reason = `库里有 ${others.length} 个非 E2E 项目（如「${sample}」）：本用例会写公式数据，只在一次性库上跑`
  if (others.length && process.env.CI) throw new Error(reason)
  test.skip(others.length > 0, reason)
}

/** 断言健康检查返回 healthy 或 degraded（PG 和 Redis 可用即可）。 */
export async function assertHealthy(request: APIRequestContext) {
  const resp = await request.get(`${BACKEND}/api/health`, { timeout: 30_000 })
  expect(resp.ok(), `/api/health 不可达 (${resp.status()})`).toBeTruthy()
  const body = await resp.json()
  const data = body?.data ?? body
  const status = data?.status
  // healthy = 完全正常，degraded = PG/Redis ok 但有 schema drift 等非阻断问题
  expect(
    ['healthy', 'degraded'].includes(status),
    `健康检查状态异常: ${status}（只允许 healthy 或 degraded）`,
  ).toBe(true)
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

/** 种子年度 */
export function seedYear(): number {
  return Number(process.env.FH_E2E_YEAR || loadManifest().year || 2025)
}
