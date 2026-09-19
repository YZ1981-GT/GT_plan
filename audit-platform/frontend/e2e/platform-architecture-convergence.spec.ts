/**
 * Playwright E2E: platform-architecture-convergence Task 22 (+ gate hardening)
 *
 * Covers: login, unauthorized redirect, deep-link /ai-chat, health/livez/readyz,
 * HTML / confirmation / OnlyOffice representative workpapers, viewport screenshots.
 *
 * Console gate: pageerror + non-resource console must be empty; resource failures
 * must be attributable via response listener. Exempt only ambient OO/favicon and
 * named concurrent `/guidance` WIP (workpaper-guidance-content-closure).
 *
 * Env: backend :9980 + frontend :3030 (start-dev.bat). Skip if not ready — no fake green.
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  partitionConsoleErrors,
  unexplainedResourceFailures,
  type FailedResponse,
} from '../src/__tests__/_helpers/pacNetworkGate'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const BASE_URL = 'http://localhost:3030'
const BACKEND_URL = 'http://127.0.0.1:9980'
const PROJECT_ID = '0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49'
const EVIDENCE_DIR = path.resolve(
  __dirname,
  '../../../.kiro/specs/platform-architecture-convergence/basis/T22-playwright',
)

/** Pre-resolved live ids from `_pac_t22_resolve_wps.py` (re-checked in-test). */
const TARGETS = [
  { wp_code: 'B50-1', wp_id: '68b35347-4e3a-43aa-a91d-c611149df9d2', kind: 'html' },
  { wp_code: 'D0', wp_id: 'f1dcd160-1b0a-4d31-9861-f7de009a6c18', kind: 'confirmation' },
  { wp_code: 'A14-4', wp_id: '342e8635-0a43-4c9a-b656-b1d7c879ef66', kind: 'onlyoffice+html' },
] as const

test.beforeAll(async ({ request }) => {
  test.setTimeout(60_000)
  fs.mkdirSync(EVIDENCE_DIR, { recursive: true })
  try {
    const livez = await request.get(`${BACKEND_URL}/livez`, { timeout: 10_000 })
    expect(livez.status(), 'livez must be 200').toBe(200)
    const health = await request.get(`${BACKEND_URL}/api/health`, { timeout: 15_000 })
    if (health.status() !== 200) {
      test.skip(true, `backend health ${health.status()} — start-dev.bat first`)
    }
  } catch (err) {
    test.skip(true, `backend ${BACKEND_URL} unreachable: ${String(err)}`)
  }
  try {
    const fe = await request.get(BASE_URL, { timeout: 10_000 })
    if (fe.status() >= 500) {
      test.skip(true, `frontend ${BASE_URL} unhealthy`)
    }
  } catch (err) {
    test.skip(true, `frontend ${BASE_URL} unreachable: ${String(err)}`)
  }
})

function attachObservability(page: Page) {
  const consoleMessages: string[] = []
  const failedResponses: FailedResponse[] = []
  page.on('pageerror', (err) => consoleMessages.push(String(err)))
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleMessages.push(msg.text())
  })
  page.on('response', (res) => {
    const status = res.status()
    if (status >= 400) failedResponses.push({ status, url: res.url() })
  })
  return { consoleMessages, failedResponses }
}

function assertConsoleGate(
  label: string,
  consoleMessages: readonly string[],
  failedResponses: readonly FailedResponse[],
) {
  const parts = partitionConsoleErrors(consoleMessages)
  const unexplained = unexplainedResourceFailures(parts.resourceErrors.length, failedResponses)
  fs.writeFileSync(
    path.join(EVIDENCE_DIR, 'console-errors.json'),
    JSON.stringify(
      {
        label,
        parts,
        failedResponses,
        unexplained,
      },
      null,
      2,
    ),
    'utf8',
  )
  expect(parts.pageErrors, `${label}: pageerror must be empty`).toEqual([])
  expect(parts.other, `${label}: non-resource console errors`).toEqual([])
  expect(unexplained, `${label}: first-party / unattributed resource failures`).toEqual([])
}

async function login(page: Page, user = 'admin', pass = 'admin123') {
  const obs = attachObservability(page)
  await page.goto(`${BASE_URL}/login`)
  await page.fill('input[placeholder*="用户名"]', user)
  await page.fill('input[placeholder*="密码"]', pass)
  await page.click('button:has-text("登录")')
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 20000 })
  return obs
}

async function apiLogin(request: APIRequestContext) {
  const resp = await request.post(`${BACKEND_URL}/api/auth/login`, {
    data: { username: 'admin', password: 'admin123' },
  })
  expect(resp.ok(), `login HTTP ${resp.status()}`).toBeTruthy()
  const body = await resp.json()
  const token = body?.data?.access_token || body?.access_token
  expect(token, 'access_token').toBeTruthy()
  return String(token)
}

test('probes: livez/readyz/health.startup present and desensitized', async ({ request }) => {
  const livez = await request.get(`${BACKEND_URL}/livez`)
  expect(livez.status()).toBe(200)

  const readyz = await request.get(`${BACKEND_URL}/readyz`)
  expect([200, 503]).toContain(readyz.status())
  fs.writeFileSync(
    path.join(EVIDENCE_DIR, 'readyz.json'),
    JSON.stringify(await readyz.json(), null, 2),
    'utf8',
  )

  const health = await request.get(`${BACKEND_URL}/api/health`)
  expect(health.status()).toBe(200)
  const payload = await health.json()
  const data = payload?.data ?? payload
  expect(data.startup, 'health.startup report').toBeTruthy()
  expect(data.startup.status).toBeTruthy()
  const blob = JSON.stringify(data.startup)
  expect(blob).not.toMatch(/password|secret|Bearer /i)
  fs.writeFileSync(
    path.join(EVIDENCE_DIR, 'health-startup.json'),
    JSON.stringify(data.startup, null, 2),
    'utf8',
  )
})

test('unauthorized deep link redirects to login with redirect query', async ({ page }) => {
  await page.goto(`${BASE_URL}/projects`)
  await page.waitForURL(/\/login/, { timeout: 15000 })
  expect(page.url()).toContain('/login')
  expect(page.url()).toMatch(/redirect=/)
})

test('login + /ai-chat deep link is a registered non-catch-all route', async ({ page }) => {
  const obs = await login(page)
  await page.goto(`${BASE_URL}/ai-chat`)
  await page.waitForURL(/\/ai-chat/, { timeout: 15000 })
  const body = await page.locator('body').innerText()
  expect(body).not.toMatch(/404|页面不存在|Not Found/i)
  for (const [w, h, name] of [
    [1280, 800, 'ai-chat-1280.png'],
    [1440, 900, 'ai-chat-1440.png'],
    [1920, 1080, 'ai-chat-1920.png'],
  ] as const) {
    await page.setViewportSize({ width: w, height: h })
    await page.screenshot({ path: path.join(EVIDENCE_DIR, name), fullPage: false })
  }
  assertConsoleGate('ai-chat', obs.consoleMessages, obs.failedResponses)
})

test('HTML / confirmation / OO representatives: render-config + DOM mount', async ({
  page,
  request,
}) => {
  const token = await apiLogin(request)
  const headers = { Authorization: `Bearer ${token}` }

  for (const target of TARGETS) {
    const cfg = await request.get(
      `${BACKEND_URL}/api/workpapers/${target.wp_id}/render-config`,
      { headers, params: { project_id: PROJECT_ID } },
    )
    expect(cfg.ok(), `${target.wp_code} render-config ${cfg.status()}`).toBeTruthy()
    const cfgBody = await cfg.json()
    const cfgData = cfgBody?.data ?? cfgBody
    expect(Array.isArray(cfgData.decision_trace), `${target.wp_code} decision_trace`).toBe(true)
    expect(cfgData.decision_trace.length).toBeGreaterThan(0)
    fs.writeFileSync(
      path.join(EVIDENCE_DIR, `render-config-${target.wp_code}.json`),
      JSON.stringify(
        {
          wp_code: target.wp_code,
          wp_id: target.wp_id,
          project_id: PROJECT_ID,
          kind: target.kind,
          decision_trace_len: cfgData.decision_trace.length,
          sheet_types: (cfgData.sheets || []).map((s: { componentType?: string }) => s.componentType),
        },
        null,
        2,
      ),
      'utf8',
    )
  }

  const obs = await login(page)
  await page.setViewportSize({ width: 1440, height: 900 })

  for (const target of TARGETS) {
    const url = `${BASE_URL}/projects/${PROJECT_ID}/workpapers/${target.wp_id}/edit`
    await page.goto(url)
    await page.waitForTimeout(3000)
    const host = page.locator(
      [
        '.gt-wp-renderer',
        '[data-component-type]',
        '.sheet-tab',
        '.confirmation-summary',
        'iframe',
        '.univer-container',
        '.wp-editor-shell',
        '.workpaper-editor',
      ].join(', '),
    )
    await expect(host.first(), `${target.wp_code} (${target.kind}) mount host`).toBeVisible({
      timeout: 45000,
    })
    await page.screenshot({
      path: path.join(EVIDENCE_DIR, `wp-${target.wp_code}-1440.png`),
      fullPage: false,
    })
  }

  assertConsoleGate('wp-mount', obs.consoleMessages, obs.failedResponses)
})
