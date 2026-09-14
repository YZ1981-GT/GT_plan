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
  'F2-29', // 检查类 bundle：含 F2-29~35
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

type WpListItem = { id?: string; wp_id?: string; wp_code?: string }

/**
 * 验证特定 wp_code 的底稿存在。
 * API page_size 上限 100，需分页；条目主键多为 wp_id（兼容 id）。
 */
export async function findWorkpaper(
  request: APIRequestContext,
  token: string,
  wpCode: string,
  projectId: string = TEST_PROJECT_ID,
): Promise<{ exists: boolean; wpId?: string }> {
  try {
    for (let page = 1; page <= 30; page += 1) {
      const resp = await request.get(`${projectBaseApi(projectId)}/working-papers`, {
        headers: { Authorization: `Bearer ${token}` },
        params: { page, page_size: 100 },
      })
      if (!resp.ok()) return { exists: false }
      const body = await resp.json()
      const list = parseWorkingPaperList(body)
      const wp = list.find((w) => w.wp_code === wpCode)
      if (wp) {
        const wpId = wp.wp_id || wp.id
        return wpId ? { exists: true, wpId } : { exists: false }
      }
      if (list.length < 100) break
    }
    return { exists: false }
  } catch {
    return { exists: false }
  }
}

/** 解析 working-papers 列表（兼容 data 为 array 或 { items }；主键 wp_id | id） */
export function parseWorkingPaperList(body: unknown): WpListItem[] {
  if (!body || typeof body !== 'object') return []
  const b = body as Record<string, unknown>
  const data = b.data
  if (Array.isArray(data)) return data as WpListItem[]
  if (data && typeof data === 'object' && Array.isArray((data as { items?: unknown }).items)) {
    return (data as { items: WpListItem[] }).items
  }
  if (Array.isArray(b.items)) return b.items as WpListItem[]
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
  await page.getByRole('tab').first().waitFor({ state: 'visible', timeout: 20_000 })
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
  throw new Error(`未找到 sheet Tab: ${wpCode}`)
}

/** 切换到「底稿目录」Tab */
export async function clickWorkpaperDirectoryTab(page: import('@playwright/test').Page) {
  const tab = page.getByRole('tab').filter({ hasText: /底稿目录/ })
  if (await tab.count()) {
    await tab.first().click({ timeout: 15_000 })
    await page.waitForTimeout(2_500)
  }
}

/** 底稿目录页点击索引 Chip 跳转（G*-dir 清单 或 b-index 底稿架构卡片） */
export async function clickDirectoryIndexChip(
  page: import('@playwright/test').Page,
  cycle: 'g12' | 'g13' | 'g14',
  code: string,
) {
  const dirRoot = page.locator(`[data-testid="${cycle}-directory"]`)
  if (await dirRoot.count()) {
    await dirRoot.first().waitFor({ state: 'visible', timeout: 20_000 })
    const chipByTestId = dirRoot.locator(`[data-testid="${cycle}-dir-chip-${code}"]`)
    const chip = (await chipByTestId.count())
      ? chipByTestId
      : dirRoot.locator('.gt-index-chip').filter({ hasText: code })
    await chip.first().click({ timeout: 15_000 })
    await page.waitForTimeout(2_500)
    return
  }

  const chip = page.locator(`[data-testid="${cycle}-dir-chip-${code}"]`)
  if (await chip.count()) {
    await chip.first().click({ timeout: 15_000 })
  } else {
    const archCard = page
      .locator('.gt-b-arch__card:visible')
      .filter({ has: page.locator('.gt-index-chip').filter({ hasText: code }) })
    if (await archCard.count()) {
      await archCard.first().click({ timeout: 15_000 })
    } else {
      const fallback = page.locator(`.${cycle}-dir .gt-index-chip`).filter({ hasText: code })
      await fallback.first().click({ timeout: 15_000 })
    }
  }
  await page.waitForTimeout(2_500)
}

/** 附注披露 sheet Tab（上市公司 / 国企） */
export async function clickDisclosureSheetTab(
  page: import('@playwright/test').Page,
  variant: 'listed' | 'soe',
) {
  const variantHint = variant === 'listed' ? /上市/ : /国企/
  const tab = page.getByRole('tab').filter({ hasText: /附注/ }).filter({ hasText: variantHint })
  await tab.first().click({ timeout: 15_000 })
  await page.waitForTimeout(2_500)
}

/** 断言附注披露表 tbody 行数（含合计行） */
export async function expectDisclosureTableRows(
  page: import('@playwright/test').Page,
  testId: string,
  expectedCount: number,
) {
  const { expect } = await import('@playwright/test')
  const rows = page.locator(`[data-testid="${testId}"] tbody tr`)
  await expect(rows).toHaveCount(expectedCount, { timeout: 15_000 })
}

/** 断言明细表可见列头（当前 Tab） */
export async function expectDetailColumnHeaders(
  page: import('@playwright/test').Page,
  testId: string,
  headers: string[],
) {
  const { expect } = await import('@playwright/test')
  const table = page.locator(`[data-testid="${testId}"]`)
  for (const h of headers) {
    await expect(table.locator('th').filter({ hasText: h }).first()).toBeVisible({ timeout: 10_000 })
  }
}

/** 切换 G13/G14 明细表 segmented Tab */
export async function clickDetailSegmentTab(
  page: import('@playwright/test').Page,
  testId: 'g13-detail-tab' | 'g14-detail-tab',
  label: string | RegExp,
) {
  const seg = page.locator(`[data-testid="${testId}"]`)
  const item = typeof label === 'string'
    ? seg.getByText(label, { exact: true })
    : seg.locator('.el-segmented__item').filter({ hasText: label })
  await item.first().click({ timeout: 10_000 })
  await page.waitForTimeout(800)
}
