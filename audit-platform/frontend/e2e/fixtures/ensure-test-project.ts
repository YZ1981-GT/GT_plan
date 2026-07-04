/**
 * ensure-test-project.ts — E2E Fixture: 确保测试项目存在
 *
 * 项目 ID 优先级：环境变量 → backend/data/e2e_fix_projects.json → FIX-B 默认 UUID
 */
import { type APIRequestContext } from '@playwright/test'
import * as fs from 'node:fs'
import * as path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

/** FIX-B 历史默认（本地 PG 可能与 seed 解析结果不同，manifest 优先） */
export const DEFAULT_FIX_B_PROJECT_ID = '37814426-a29e-4fc2-9313-a59d229bf7b0'

type E2eManifest = {
  env?: Record<string, string>
}

function loadE2eManifest(): E2eManifest | null {
  const manifestPath = path.resolve(__dirname, '../../../../backend/data/e2e_fix_projects.json')
  try {
    if (!fs.existsSync(manifestPath)) return null
    return JSON.parse(fs.readFileSync(manifestPath, 'utf-8')) as E2eManifest
  } catch {
    return null
  }
}

const MANIFEST = loadE2eManifest()

export type FixtureKind = 'FIX-A' | 'FIX-B' | 'FIX-INT' | 'FIX-RP' | 'FIX-F'

/** F2 HTML E2E 所需底稿（与 backend/scripts/e2e/seed_fix_projects.py 对齐） */
export const F2_E2E_WP_CODES = [
  'F2-1',
  'F2-21', 'F2-22', 'F2-23', 'F2-24', 'F2-25', 'F2-26',
  'F2-47', 'F2-55', 'F2-70',
] as const

const ENV_KEYS: Record<FixtureKind, string> = {
  'FIX-A': 'TEST_PROJECT_ID_FIX_A',
  'FIX-B': 'TEST_PROJECT_ID_FIX_B',
  'FIX-INT': 'TEST_PROJECT_ID_FIX_INT',
  'FIX-RP': 'TEST_PROJECT_ID_FIX_RP',
  'FIX-F': 'TEST_PROJECT_ID_FIX_F',
}

function manifestEnv(key: string): string | undefined {
  const v = MANIFEST?.env?.[key]
  return v && v.trim() ? v.trim() : undefined
}

/** 通用 TEST_PROJECT_ID；未设 env 时读 seed manifest */
export const TEST_PROJECT_ID =
  process.env.TEST_PROJECT_ID ||
  manifestEnv('TEST_PROJECT_ID') ||
  process.env.TEST_PROJECT_ID_FIX_B ||
  manifestEnv('TEST_PROJECT_ID_FIX_B') ||
  DEFAULT_FIX_B_PROJECT_ID

export function resolveFixtureProjectId(kind: FixtureKind): string {
  const key = ENV_KEYS[kind]
  const fromEnv = process.env[key] || manifestEnv(key)
  if (fromEnv) return fromEnv
  if (kind === 'FIX-B' || kind === 'FIX-F') return TEST_PROJECT_ID
  return ''
}
export function projectBaseApi(projectId: string): string {
  return `/api/projects/${projectId}`
}

/** @deprecated 使用 projectBaseApi(TEST_PROJECT_ID) */
export const TEST_BASE_API = projectBaseApi(TEST_PROJECT_ID)

export interface TestFixture {
  ready: boolean
  token: string
  projectId: string
  fixture?: FixtureKind
  reason?: string
}

async function login(request: APIRequestContext): Promise<{ ok: boolean; token: string; reason?: string }> {
  try {
    const resp = await request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    })
    if (resp.status() !== 200) {
      return { ok: false, token: '', reason: '后端不可达或 admin 账号不存在' }
    }
    const body = await resp.json()
    const token = body.data?.access_token ?? body.access_token ?? ''
    if (!token) {
      return { ok: false, token: '', reason: '登录成功但未返回 token' }
    }
    return { ok: true, token }
  } catch (e) {
    return { ok: false, token: '', reason: `登录失败: ${e}` }
  }
}

/**
 * 获取 auth token + 验证项目存在
 */
export async function ensureTestProject(
  request: APIRequestContext,
  projectId: string = TEST_PROJECT_ID,
): Promise<TestFixture> {
  const loginResult = await login(request)
  if (!loginResult.ok) {
    return {
      ready: false,
      token: '',
      projectId,
      reason: loginResult.reason,
    }
  }

  const token = loginResult.token

  try {
    const projResp = await request.get(`/api/projects/${projectId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (projResp.status() === 404) {
      return {
        ready: false,
        token,
        projectId,
        reason:
          `测试项目 ${projectId} 不存在。请先运行 backend/scripts/e2e/seed_fix_projects.py --fix`,
      }
    }
  } catch {
    return { ready: false, token, projectId, reason: '项目查询失败' }
  }

  return { ready: true, token, projectId }
}

/**
 * 按 e2e-matrix 夹具类型解析项目 ID 并校验存在
 */
export async function ensureFixtureProject(
  request: APIRequestContext,
  kind: FixtureKind,
): Promise<TestFixture> {
  const projectId = resolveFixtureProjectId(kind)
  if (!projectId) {
    return {
      ready: false,
      token: '',
      projectId: '',
      fixture: kind,
      reason: `未设置 ${ENV_KEYS[kind]}。请运行 seed_fix_projects.py --fix 并 export 对应 env`,
    }
  }
  const base = await ensureTestProject(request, projectId)
  return { ...base, fixture: kind }
}

/**
 * 验证特定 wp_code 的底稿存在
 */
export async function findWorkpaper(
  request: APIRequestContext,
  token: string,
  wpCode: string,
  projectId: string = TEST_PROJECT_ID,
): Promise<{ exists: boolean; wpId?: string }> {
  try {
    const resp = await request.get(`${projectBaseApi(projectId)}/working-papers`, {
      headers: { Authorization: `Bearer ${token}` },
      params: { page_size: 500 },
    })
    const body = await resp.json()
    const list = parseWorkingPaperList(body)
    const wp = list.find((w: { wp_code?: string }) => w.wp_code === wpCode)
    return wp ? { exists: true, wpId: wp.id } : { exists: false }
  } catch {
    return { exists: false }
  }
}

/** 解析 working-papers 列表（兼容 data 为 array 或 { items }） */
export function parseWorkingPaperList(body: unknown): Array<{ id: string; wp_code?: string }> {
  if (!body || typeof body !== 'object') return []
  const b = body as Record<string, unknown>
  const data = b.data
  if (Array.isArray(data)) return data as Array<{ id: string; wp_code?: string }>
  if (data && typeof data === 'object' && Array.isArray((data as { items?: unknown }).items)) {
    return (data as { items: Array<{ id: string; wp_code?: string }> }).items
  }
  if (Array.isArray(b.items)) return b.items as Array<{ id: string; wp_code?: string }>
  return []
}

/** render-config 正确路径（非 /projects/.../working-papers/...） */
export function renderConfigApiUrl(wpId: string, sheetName?: string): string {
  const base = `/api/workpapers/${wpId}/render-config`
  return sheetName ? `${base}?sheet_name=${encodeURIComponent(sheetName)}` : base
}

export function sheetComponentTypes(rcData: Record<string, unknown>): string[] {
  const sheets = (rcData.sheets as Array<{ componentType?: string; component_type?: string }>) ?? []
  return sheets.map((s) => s.componentType ?? s.component_type).filter(Boolean) as string[]
}

export async function fetchRenderConfig(
  request: APIRequestContext,
  token: string,
  wpId: string,
): Promise<Record<string, unknown>> {
  const resp = await request.get(renderConfigApiUrl(wpId), {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (resp.status() !== 200) {
    throw new Error(`render-config ${resp.status()}: ${await resp.text()}`)
  }
  const body = await resp.json()
  return (body?.data ?? body) as Record<string, unknown>
}

export async function expectHtmlDualModeOrContent(
  page: import('@playwright/test').Page,
  bodyHint: RegExp,
) {
  const { expect } = await import('@playwright/test')
  const segmented = page.locator('.el-segmented')
  let hasSeg = false
  try {
    await expect(segmented.first()).toBeVisible({ timeout: 20_000 })
    hasSeg = true
  } catch {
    hasSeg = false
  }
  const bodyText = (await page.textContent('body')) || ''
  expect(hasSeg || bodyHint.test(bodyText), `应显示 HTML 双模式或页面含 ${bodyHint}`).toBeTruthy()
}
/** 多 sheet 底稿默认打开「底稿目录」Tab，需切换到含 wpCode 的 HTML sheet（排除 F2-21A 等父码 Tab） */
export async function clickWorkpaperSheetTab(page: import('@playwright/test').Page, wpCode: string) {
  const fallbacks: Record<string, string[]> = {
    'F2-1': ['F2-1', 'F2-8', 'F2-3'],
  }
  const labels = fallbacks[wpCode] ?? [wpCode]
  for (const label of labels) {
    const exact = label.match(/^F2-\d+$/)
      ? new RegExp(`${label.replace('-', '\\-')}(?!\\d)`)
      : label
    let tab =
      typeof exact === 'string'
        ? page.getByRole('tab').filter({ hasText: exact })
        : page.getByRole('tab', { name: exact })
    if (label.match(/^F2-\d+$/)) {
      tab = tab.filter({ hasNotText: `${label}A` })
    }
    if (await tab.count()) {
      await tab.first().click({ timeout: 15_000 })
      await page.waitForTimeout(2_500)
      return
    }
  }
}
