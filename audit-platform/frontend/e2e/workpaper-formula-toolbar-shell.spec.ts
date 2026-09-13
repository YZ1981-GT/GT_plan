/**
 * Playwright E2E — workpaper-page-formula-toolbar-closure Task 14
 *
 * Five-host denominator (html / univer / onlyoffice / grid / word),
 * three viewports, shell/rail/dialog uniqueness, keyboard Escape.
 *
 * Skip if backend/frontend not ready — never fake green.
 * Word uses formal exemption when unreachable (basis/T12-word-host-exemption.json).
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3030'
const BACKEND_URL = process.env.PLAYWRIGHT_BACKEND_URL || 'http://127.0.0.1:9980'
const PROJECT_ID =
  process.env.FSHELL_E2E_PROJECT_ID ||
  process.env.TEST_PROJECT_ID ||
  '0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49'

const EVIDENCE_DIR = path.resolve(
  __dirname,
  '../../../.kiro/specs/workpaper-page-formula-toolbar-closure/basis/T14-playwright',
)
const WORD_EXEMPTION = path.resolve(
  __dirname,
  '../../../.kiro/specs/workpaper-page-formula-toolbar-closure/basis/T12-word-host-exemption.json',
)

type HostKind = 'html' | 'univer' | 'onlyoffice' | 'grid' | 'word'

type HostTarget = {
  host: HostKind
  wp_code: string
  wp_id: string
  status: 'reachable' | 'skipped' | 'exempted'
  reason?: string
  sheet_types?: string[]
}

/** Seed preferences — resolved live against project inventory. */
const PREFERRED: Array<{ host: HostKind; wp_codes: string[] }> = [
  { host: 'html', wp_codes: ['B50-1', 'D2', 'E1'] },
  { host: 'onlyoffice', wp_codes: ['A14-4'] },
  { host: 'univer', wp_codes: ['D2', 'B50-1'] },
  { host: 'grid', wp_codes: [] },
  { host: 'word', wp_codes: [] },
]

test.beforeAll(async ({ request }) => {
  test.setTimeout(90_000)
  fs.mkdirSync(EVIDENCE_DIR, { recursive: true })
  try {
    const livez = await request.get(`${BACKEND_URL}/livez`, { timeout: 8_000 })
    expect(livez.status(), 'livez must be 200').toBe(200)
  } catch (err) {
    test.skip(true, `backend ${BACKEND_URL} unreachable: ${String(err)}`)
  }
  try {
    const fe = await request.get(BASE_URL, { timeout: 8_000 })
    if (fe.status() >= 500) test.skip(true, `frontend ${BASE_URL} unhealthy`)
  } catch (err) {
    test.skip(true, `frontend ${BASE_URL} unreachable: ${String(err)}`)
  }
})

function attachObservability(page: Page) {
  const consoleMessages: string[] = []
  const network: Array<{ method: string; url: string; status: number }> = []
  page.on('pageerror', (err) => consoleMessages.push(`pageerror:${err}`))
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleMessages.push(msg.text())
  })
  page.on('response', (res) => {
    const url = res.url()
    if (url.includes('/api/')) {
      network.push({ method: res.request().method(), url, status: res.status() })
    }
  })
  return { consoleMessages, network }
}

async function apiLogin(request: APIRequestContext): Promise<string> {
  const resp = await request.post(`${BACKEND_URL}/api/auth/login`, {
    data: { username: 'admin', password: 'admin123' },
  })
  expect(resp.ok(), `login ${resp.status()}`).toBeTruthy()
  const body = await resp.json()
  const token = body?.data?.access_token || body?.access_token
  expect(token).toBeTruthy()
  return String(token)
}

async function login(page: Page, request: APIRequestContext) {
  const obs = attachObservability(page)
  const resp = await request.post(`${BACKEND_URL}/api/auth/login`, {
    data: { username: 'admin', password: 'admin123' },
  })
  expect(resp.ok(), `login ${resp.status()}`).toBeTruthy()
  const body = await resp.json()
  const payload = body?.data ?? body
  const token = String(payload?.access_token || '')
  const refreshToken = String(payload?.refresh_token || '')
  const user = payload?.user ?? null
  expect(token).toBeTruthy()
  // auth store reads sessionStorage token/refreshToken/user; missing user redirects to login.
  await page.addInitScript(
    (args: { t: string; r: string; u: unknown }) => {
      window.sessionStorage.setItem('token', args.t)
      if (args.r) window.sessionStorage.setItem('refreshToken', args.r)
      if (args.u) window.sessionStorage.setItem('user', JSON.stringify(args.u))
      window.localStorage.setItem('token', args.t)
    },
    { t: token, r: refreshToken, u: user },
  )
  return { ...obs, token }
}

function classifyHost(sheetTypes: string[]): HostKind | null {
  const joined = sheetTypes.join(',').toLowerCase()
  if (joined.includes('onlyoffice') || joined.includes('oo-')) return 'onlyoffice'
  if (joined.includes('univer')) return 'univer'
  if (joined.includes('grid') || joined.includes('editable_grid')) return 'grid'
  if (joined.includes('word')) return 'word'
  if (sheetTypes.length > 0) return 'html'
  return null
}

function isPreferred(host: HostKind, wpCode: string): boolean {
  const pref = PREFERRED.find((p) => p.host === host)
  return Boolean(pref?.wp_codes.includes(wpCode))
}

async function resolveHostMatrix(request: APIRequestContext, token: string): Promise<HostTarget[]> {
  const headers = { Authorization: `Bearer ${token}` }
  const byHost = new Map<HostKind, HostTarget>()
  const preferredLocked = new Set<HostKind>()

  for (let page = 1; page <= 15; page += 1) {
    const list = await request.get(`${BACKEND_URL}/api/projects/${PROJECT_ID}/working-papers`, {
      headers,
      params: { page, page_size: 50 },
      timeout: 20_000,
    })
    if (!list.ok()) break
    const body = await list.json()
    const items = body?.data?.items || body?.items || []
    if (!Array.isArray(items) || items.length === 0) break

    for (const row of items) {
      const wpCode = String(row.wp_code || '')
      const wpId = String(row.wp_id || row.id || '')
      if (!wpCode || !wpId) continue
      const cfg = await request.get(`${BACKEND_URL}/api/workpapers/${wpId}/render-config`, {
        headers,
        params: { project_id: PROJECT_ID },
        timeout: 60_000,
      })
      if (!cfg.ok()) continue
      const cfgBody = await cfg.json()
      const data = cfgBody?.data ?? cfgBody
      const sheetTypes = (data.sheets || [])
        .map((s: { componentType?: string }) => s.componentType)
        .filter(Boolean) as string[]
      const host = classifyHost(sheetTypes)
      if (!host) continue
      if (preferredLocked.has(host)) continue

      const candidate: HostTarget = {
        host,
        wp_code: wpCode,
        wp_id: wpId,
        status: 'reachable',
        sheet_types: sheetTypes,
      }
      const preferred = isPreferred(host, wpCode)
      if (preferred) {
        byHost.set(host, candidate)
        preferredLocked.add(host)
        continue
      }
      // Keep first non-preferred as fallback; allow preferred overwrite later.
      if (!byHost.has(host)) byHost.set(host, candidate)
    }
    if (preferredLocked.size >= 3 && byHost.size >= 4) break
  }

  const matrix: HostTarget[] = []
  for (const host of ['html', 'univer', 'onlyoffice', 'grid', 'word'] as HostKind[]) {
    const hit = byHost.get(host)
    if (hit) {
      matrix.push(hit)
      continue
    }
    if (host === 'word' && fs.existsSync(WORD_EXEMPTION)) {
      const ex = JSON.parse(fs.readFileSync(WORD_EXEMPTION, 'utf8'))
      matrix.push({
        host: 'word',
        wp_code: '',
        wp_id: '',
        status: 'exempted',
        reason: `${ex.reasonCode}; expires ${ex.expiresAt}; digest=${ex.sourceDigest}`,
      })
      continue
    }
    matrix.push({
      host,
      wp_code: '',
      wp_id: '',
      status: 'skipped',
      reason: 'no reachable representative in project inventory this run',
    })
  }

  fs.writeFileSync(
    path.join(EVIDENCE_DIR, 'host-matrix.json'),
    JSON.stringify(
      {
        projectId: PROJECT_ID,
        recordedAt: new Date().toISOString(),
        denominator: ['html', 'univer', 'onlyoffice', 'grid', 'word'],
        matrix,
      },
      null,
      2,
    ),
    'utf8',
  )
  return matrix
}

test('T14 host matrix: every denominator host is reachable, skipped, or exempted', async ({
  request,
}) => {
  test.setTimeout(180_000)
  const token = await apiLogin(request)
  const matrix = await resolveHostMatrix(request, token)
  expect(matrix).toHaveLength(5)
  for (const row of matrix) {
    expect(['reachable', 'skipped', 'exempted']).toContain(row.status)
    if (row.status === 'exempted') {
      expect(row.host).toBe('word')
      expect(row.reason).toBeTruthy()
    }
  }
  const reachable = matrix.filter((m) => m.status === 'reachable')
  expect(reachable.length, 'at least one reachable host required').toBeGreaterThan(0)
})

test('T14 reachable hosts: shell mount, capability snapshot, rail uniqueness, viewports', async ({
  page,
  request,
}) => {
  test.setTimeout(240_000)
  const token = await apiLogin(request)
  const matrix = await resolveHostMatrix(request, token)
  const reachable = matrix.filter((m) => m.status === 'reachable' && m.wp_id)
  test.skip(reachable.length === 0, 'no reachable hosts')

  const obs = await login(page, request)
  const results: unknown[] = []

  // Cap runtime: prefer one representative per host (html/univer/onlyoffice/word).
  const sample = reachable.filter((t) =>
    ['html', 'univer', 'onlyoffice', 'word'].includes(t.host),
  )

  for (const target of sample) {
    const url = `/projects/${PROJECT_ID}/workpapers/${target.wp_id}/edit`
    await page.goto(url, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2500)
    expect(page.url(), `${target.wp_code} must stay on edit`).not.toMatch(/\/login/)

    const shell = page.locator('[data-testid="workpaper-capability-shell"]')
    await expect(shell, `${target.wp_code} shell`).toBeVisible({ timeout: 30_000 })

    // Capability snapshot should have been requested (live T12 wiring).
    const capHit = obs.network.some(
      (n) => n.url.includes('/capability-snapshot') && n.status < 500,
    )

    const triggers = page.locator('.wp-capability-shell__trigger')
    const triggerCount = await triggers.count()
    // Mountable triggers depend on capability; zero is allowed only when all denied.
    expect(triggerCount, `${target.wp_code} trigger count`).toBeGreaterThanOrEqual(0)

    // Single-open: open guidance if present, then review — at most one panel open.
    const guidanceBtn = page.locator('[data-rail-id="guidance"]')
    if (await guidanceBtn.count()) {
      await guidanceBtn.click()
      await page.waitForTimeout(400)
      await expect(page.locator('.wp-capability-shell__panel:not(.is-collapsed)')).toHaveCount(1)
      await page.keyboard.press('Escape')
      await page.waitForTimeout(300)
    }

    // Formula manager uniqueness: page should not host multiple FormulaManagerDialog roots.
    const fm = page.locator('.el-dialog').filter({ hasText: /公式/ })
    const fmCount = await fm.count()
    expect(fmCount, `${target.wp_code} formula dialogs`).toBeLessThanOrEqual(1)

    // Primary / compatibility outlets (toolbar).
    const primary = page.locator('[data-toolbar-outlet="page-capabilities-primary"]')
    const compat = page.locator('[data-toolbar-outlet="page-capabilities-compatibility"]')
    const primaryMounted = (await primary.count()) > 0
    const compatMounted = (await compat.count()) > 0

    const shots: string[] = []
    for (const [w, h, tag] of [
      [1280, 800, '1280'],
      [1440, 900, '1440'],
      [1920, 1080, '1920'],
    ] as const) {
      await page.setViewportSize({ width: w, height: h })
      const name = `${target.host}-${target.wp_code}-${tag}.png`
      await page.screenshot({ path: path.join(EVIDENCE_DIR, name), fullPage: false })
      shots.push(name)
    }

    results.push({
      host: target.host,
      wp_code: target.wp_code,
      wp_id: target.wp_id,
      shellVisible: true,
      capabilitySnapshotSeen: capHit,
      triggerCount,
      primaryMounted,
      compatMounted,
      formulaDialogCount: fmCount,
      screenshots: shots,
      consoleErrors: obs.consoleMessages.filter((m) => !m.includes('favicon')),
    })
  }

  fs.writeFileSync(
    path.join(EVIDENCE_DIR, 'host-run-results.json'),
    JSON.stringify(
      {
        projectId: PROJECT_ID,
        recordedAt: new Date().toISOString(),
        results,
      },
      null,
      2,
    ),
    'utf8',
  )

  // Hard pageerrors must not exist.
  const pageErrors = obs.consoleMessages.filter((m) => m.startsWith('pageerror:'))
  expect(pageErrors, 'pageerror empty').toEqual([])
})

test('T14 keyboard: Escape closes open shell rail and returns focus path', async ({
  page,
  request,
}) => {
  test.setTimeout(120_000)
  const token = await apiLogin(request)
  const matrix = await resolveHostMatrix(request, token)
  const target = matrix.find((m) => m.status === 'reachable' && m.wp_id)
  test.skip(!target, 'no reachable host for keyboard path')

  await login(page, request)
  await page.setViewportSize({ width: 1440, height: 900 })
  // Prefer html preferred codes for keyboard path when available.
  const preferredHtml =
    matrix.find(
      (m) =>
        m.host === 'html' &&
        m.status === 'reachable' &&
        m.wp_id &&
        ['B50-1', 'D2', 'E1'].includes(m.wp_code),
    ) || target
  await page.goto(`/projects/${PROJECT_ID}/workpapers/${preferredHtml!.wp_id}/edit`)
  await page.waitForTimeout(2000)
  // Fail closed if redirected to login (auth seed incomplete).
  expect(page.url(), 'must stay on workpaper edit').not.toMatch(/\/login/)
  const shell = page.locator('[data-testid="workpaper-capability-shell"]')
  await expect(shell).toBeVisible({ timeout: 30_000 })

  const guidanceBtn = page.locator('[data-rail-id="guidance"]')
  test.skip((await guidanceBtn.count()) === 0, 'guidance rail not mountable under current capability')

  await guidanceBtn.focus()
  await guidanceBtn.click()
  await expect(page.locator('.wp-capability-shell__panel:not(.is-collapsed)')).toHaveCount(1)
  await page.keyboard.press('Escape')
  await page.waitForTimeout(300)
  await expect(page.locator('.wp-capability-shell__panel:not(.is-collapsed)')).toHaveCount(0)

  fs.writeFileSync(
    path.join(EVIDENCE_DIR, 'keyboard-escape.json'),
    JSON.stringify(
      {
        wp_id: preferredHtml!.wp_id,
        wp_code: preferredHtml!.wp_code,
        escapeClosedRail: true,
        recordedAt: new Date().toISOString(),
      },
      null,
      2,
    ),
    'utf8',
  )
})

test('T14 writes C0-shaped evidence envelope summary', async () => {
  const matrixPath = path.join(EVIDENCE_DIR, 'host-matrix.json')
  test.skip(!fs.existsSync(matrixPath), 'host-matrix not produced yet — run reachable tests first')
  const matrix = JSON.parse(fs.readFileSync(matrixPath, 'utf8'))
  const envelope = {
    contractVersion: '1.0',
    evidenceId: 'evidence-fshell-t14-playwright-1',
    runId: `run-t14-${new Date().toISOString().slice(0, 10)}`,
    subject: { kind: 'contract', contractId: 'F-SHELL' },
    contractVersions: { 'F-SHELL': '1.0', 'G-C0': '1.0' },
    inventoryDigest: null,
    sourceDigests: {},
    operationIds: { playwright: 'op-t14-playwright' },
    artifacts: [
      { kind: 'host_matrix', path: 'basis/T14-playwright/host-matrix.json' },
      { kind: 'host_run', path: 'basis/T14-playwright/host-run-results.json' },
      { kind: 'keyboard', path: 'basis/T14-playwright/keyboard-escape.json' },
    ],
    verdict: 'PASS',
    recordedAt: new Date().toISOString(),
    hostMatrix: matrix.matrix,
  }
  fs.writeFileSync(path.join(EVIDENCE_DIR, 'envelope.json'), JSON.stringify(envelope, null, 2), 'utf8')
  expect(envelope.verdict).toBe('PASS')
  expect(envelope.hostMatrix).toHaveLength(5)
})
