/**
 * Playwright E2E: audit-evidence-attachment-preview-format-expansion Task 19
 *
 * Real upload → list → preview on Preview_Host (AttachmentManagement) and
 * Drawer_Host (AttachmentTabPanel). Asserts Download_Endpoint only for new
 * families, zero external email hosts, dwg download-only copy.
 *
 * Env: backend :9980 + frontend :3030. Skip if unreachable — no fake green.
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { TEST_PROJECT_ID, findWorkpaper } from './fixtures/ensure-test-project'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const BASE_URL = process.env.APFE_BASE_URL ?? 'http://localhost:3031'
const BACKEND_URL = 'http://127.0.0.1:9980'
const EVIDENCE_DIR = path.resolve(
  __dirname,
  '../../../.kiro/specs/_archive/05-business-features/audit-evidence-attachment-preview-format-expansion/evidence/attachment-preview-format-expansion',
)
const FIXTURE_DIR = path.join(EVIDENCE_DIR, 'browser_fixtures')

const FILES = [
  { name: 'apfe-e2e-sample.zip', file: 'sample.zip', family: 'archive' },
  { name: 'apfe-e2e-sample.eml', file: 'sample.eml', family: 'email' },
  { name: 'apfe-e2e-sample.dxf', file: 'sample.dxf', family: 'drawing' },
  { name: 'apfe-e2e-sample.dwg', file: 'sample.dwg', family: 'cad' },
] as const

async function getToken(request: APIRequestContext): Promise<string | null> {
  try {
    const resp = await request.post(`${BACKEND_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
      timeout: 15_000,
    })
    if (!resp.ok()) return null
    const body = await resp.json()
    return body.data?.access_token ?? body.access_token ?? null
  } catch {
    return null
  }
}

async function uploadFixture(
  request: APIRequestContext,
  token: string,
  projectId: string,
  localName: string,
  uploadName: string,
  bind?: { wpId: string },
): Promise<{ id: string; download_url?: string } | null> {
  const buf = fs.readFileSync(path.join(FIXTURE_DIR, localName))
  const multipart: Record<string, unknown> = {
    file: {
      name: uploadName,
      mimeType: 'application/octet-stream',
      buffer: buf,
    },
  }
  if (bind?.wpId) {
    multipart.reference_id = bind.wpId
    multipart.reference_type = 'working_paper'
  }
  const resp = await request.post(`${BACKEND_URL}/api/projects/${projectId}/attachments/upload`, {
    headers: { Authorization: `Bearer ${token}` },
    multipart: multipart as any,
    timeout: 60_000,
  })
  if (!resp.ok()) {
    console.warn('upload failed', uploadName, resp.status(), await resp.text())
    return null
  }
  const body = await resp.json()
  const att = body.data ?? body
  const id = att.id || att.attachment_id
  if (!id) return null
  return {
    id: String(id),
    download_url: att.download_url || `/api/attachments/${id}/download`,
  }
}

test.describe('APFE Task19 extended preview both hosts', () => {
  test.beforeAll(async ({ request }) => {
    test.setTimeout(60_000)
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true })
    for (const f of FILES) {
      test.skip(
        !fs.existsSync(path.join(FIXTURE_DIR, f.file)),
        `missing fixture ${f.file} — run _write_browser_fixtures.py`,
      )
    }
    try {
      const livez = await request.get(`${BACKEND_URL}/livez`, { timeout: 10_000 })
      expect(livez.status()).toBe(200)
    } catch (err) {
      test.skip(true, `backend unreachable: ${String(err)}`)
    }
    try {
      await request.get(BASE_URL, { timeout: 10_000 })
    } catch (err) {
      test.skip(true, `frontend unreachable: ${String(err)}`)
    }
  })

  test('upload + Preview_Host + Drawer_Host + zero external email', async ({ page, request }) => {
    test.setTimeout(180_000)
    const token = await getToken(request)
    test.skip(!token, 'login failed')

    const uploaded: Record<string, { id: string; download_url?: string }> = {}
    for (const f of FILES) {
      const att = await uploadFixture(request, token!, TEST_PROJECT_ID, f.file, f.name)
      test.skip(!att, `upload failed for ${f.name}`)
      uploaded[f.family] = att!
    }

    const externalHosts = new Set<string>()
    const previewHits: string[] = []
    const downloadHits: string[] = []
    page.on('request', (req) => {
      const url = req.url()
      if (url.includes('/preview') && !url.includes('/preview-pdf')) previewHits.push(url)
      if (url.includes('/download')) downloadHits.push(url)
      try {
        const u = new URL(url)
        if (
          u.hostname &&
          u.hostname !== 'localhost' &&
          u.hostname !== '127.0.0.1' &&
          !u.hostname.endsWith('.local')
        ) {
          externalHosts.add(u.hostname)
        }
      } catch {
        /* ignore */
      }
    })

    const pageErrors: string[] = []
    page.on('pageerror', (err) => {
      const msg = String(err)
      // Email sandbox iframe intentionally omits allow-same-origin; ambient storage access is expected noise.
      if (msg.includes('sandboxed') && msg.includes('sessionStorage')) return
      if (msg.includes('sandboxed') && msg.includes('localStorage')) return
      pageErrors.push(msg)
    })

    await page.addInitScript((t: string) => {
      window.sessionStorage.setItem('token', t)
      window.localStorage.setItem('token', t)
    }, token!)

    // ── Preview_Host: AttachmentManagement ──
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/attachments`, {
      waitUntil: 'domcontentloaded',
      timeout: 60_000,
    })
    await expect(page.getByText(FILES[0].name).first()).toBeVisible({ timeout: 60_000 })

    async function closePreview() {
      try {
        if (page.isClosed()) return
        await page.keyboard.press('Escape').catch(() => undefined)
        await page.locator('.el-dialog__headerbtn').first().click({ timeout: 1500, force: true }).catch(() => undefined)
        await page.locator('.el-dialog').first().waitFor({ state: 'hidden', timeout: 5000 }).catch(() => undefined)
      } catch {
        /* ignore */
      }
    }

    async function openPreviewByName(name: string) {
      await closePreview()
      const row = page.locator('.gt-att-item-name', { hasText: name }).first()
      await expect(row).toBeVisible({ timeout: 30_000 })
      await row.click()
      await expect(page.locator('.el-dialog:visible, [data-testid="extended-format-preview"]:visible').first()).toBeVisible({
        timeout: 30_000,
      })
    }

    await openPreviewByName(FILES[0].name)
    await expect(page.getByTestId('archive-entry-list').first()).toBeVisible({ timeout: 30_000 })

    await openPreviewByName(FILES[1].name)
    await expect(page.getByTestId('email-message-view').first()).toBeVisible({ timeout: 30_000 })

    await openPreviewByName(FILES[2].name)
    await expect(page.getByTestId('dxf-drawing-view').first()).toBeVisible({ timeout: 30_000 })

    await openPreviewByName(FILES[3].name)
    await expect(page.getByText(/DWG 图纸请下载后用 CAD|暂不支持预览|下载文件/).first()).toBeVisible({
      timeout: 15_000,
    })
    await closePreview()

    // ── Drawer_Host: WorkpaperEditor → 面板 → AttachmentTabPanel → AttachmentPreviewDrawer ──
    // Prefer Univer codes first (legacy HTML path used to lack 面板); E1 still valid after hoist.
    const wpCodes = ['A14-4', 'B50-1', 'A26-1', 'F2-1', 'D4', 'B1', 'E1']
    let drawerOk = false
    let drawerDetail = 'no_wp'
    let wpId: string | undefined
    let wpCodeUsed: string | undefined
    for (const code of wpCodes) {
      const wp = await findWorkpaper(request, token!, code, TEST_PROJECT_ID)
      if (wp.exists && wp.wpId) {
        wpId = wp.wpId
        wpCodeUsed = code
        break
      }
    }
    test.skip(!wpId, `no workpaper among ${wpCodes.join(',')}`)

    const drawerZipName = `apfe-e2e-drawer-${Date.now()}.zip`
    const drawerAtt = await uploadFixture(
      request,
      token!,
      TEST_PROJECT_ID,
      FILES[0].file,
      drawerZipName,
      { wpId: wpId! },
    )
    test.skip(!drawerAtt, 'drawer-bound zip upload failed')

    const assoc = await request.post(`${BACKEND_URL}/api/attachments/${drawerAtt!.id}/associate`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { wp_id: wpId, association_type: 'evidence', notes: 'apfe-e2e-drawer' },
      timeout: 30_000,
    })
    drawerDetail = `wp=${wpCodeUsed};assoc_status=${assoc.status()}`

    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers/${wpId}/edit`, {
      waitUntil: 'domcontentloaded',
      timeout: 60_000,
    })
    await page
      .locator('.gt-wp-editor-toolbar, .gt-wp-io-toolbar, canvas, .univer-container')
      .first()
      .waitFor({ timeout: 60_000 })
    await page.locator('.el-loading-mask').first().waitFor({ state: 'detached', timeout: 20_000 }).catch(() => undefined)
    const panelBtn = page.getByRole('button', { name: /面板/ }).first()
    const sidePanel = page.locator('.el-drawer:visible .gt-wp-side-panel').first()
    await expect(panelBtn).toBeVisible({ timeout: 30_000 })
    await expect(panelBtn).toBeEnabled()
    await panelBtn.click()
    const opened = await sidePanel
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    if (!opened) {
      await panelBtn.click()
    }
    await expect(sidePanel).toBeVisible({ timeout: 30_000 })
    // AttachmentTabPanel lives under 追溯关联 → 附件 (lazy nested tabs)
    await page.getByRole('tab', { name: /追溯关联/ }).click({ force: true })
    await page.getByRole('tab', { name: /^附件$/ }).click({ force: true })
    await expect(page.locator('.gt-attach-tab')).toBeVisible({ timeout: 30_000 })
    const zipRow = page.locator('.gt-attach-tab__item', { hasText: drawerZipName })
    await expect(zipRow).toBeVisible({ timeout: 30_000 })
    await zipRow.click({ force: true })
    await expect(page.locator('.el-drawer:visible [data-testid="extended-format-preview"]').first()).toBeVisible({
      timeout: 30_000,
    })
    drawerOk = true
    drawerDetail = `${drawerDetail};drawer_preview_ok`

    const digests = JSON.parse(fs.readFileSync(path.join(FIXTURE_DIR, 'digests.json'), 'utf8'))
    const evidence = {
      spec: 'audit-evidence-attachment-preview-format-expansion',
      task: 19,
      recorded_at: new Date().toISOString(),
      project_id: TEST_PROJECT_ID,
      uploaded: Object.fromEntries(
        Object.entries(uploaded).map(([k, v]) => [k, { id: v.id, download_url: v.download_url }]),
      ),
      drawer_attachment_id: drawerAtt!.id,
      drawer_zip_name: drawerZipName,
      drawer_wp_id: wpId,
      drawer_detail: drawerDetail,
      digests,
      preview_endpoint_hits_for_extended: previewHits.filter((u) =>
        [drawerAtt!.id, ...Object.values(uploaded).map((a) => a.id)].some((id) => u.includes(id)),
      ),
      download_hits: downloadHits.length,
      external_hosts: [...externalHosts],
      page_errors: pageErrors,
      drawer_host_exercised: drawerOk,
      conclusions: {
        preview_host_ok: true,
        drawer_host_ok: drawerOk,
        zero_external_email_hosts: ![...externalHosts].some((h) => h.includes('evil.example')),
        page_errors_zero: pageErrors.length === 0,
      },
    }
    fs.writeFileSync(path.join(EVIDENCE_DIR, 'browser_evidence.json'), JSON.stringify(evidence, null, 2))

    expect(
      evidence.preview_endpoint_hits_for_extended.length,
      'extended formats must not hit Preview_Endpoint',
    ).toBe(0)
    expect(evidence.conclusions.zero_external_email_hosts).toBe(true)
    expect(pageErrors, `uncaught page errors: ${pageErrors.join('; ')}`).toEqual([])
    expect(drawerOk, `Drawer_Host not exercised: ${drawerDetail}`).toBe(true)
  })

  // ── Task19 补强：资源回收(开关5次归零) / JSON trap→logger ERROR / CSP srcdoc / 零外发 ──
  test('resource release x5, JSON trap logger ERROR, email CSP srcdoc & zero external host', async ({
    page,
    request,
  }) => {
    test.setTimeout(180_000)
    const token = await getToken(request)
    test.skip(!token, 'login failed')

    const zipUploadName = `apfe-rr-${Date.now()}.zip`
    const emlUploadName = `apfe-rr-${Date.now()}.eml`
    const zip = await uploadFixture(request, token!, TEST_PROJECT_ID, FILES[0].file, zipUploadName)
    const eml = await uploadFixture(request, token!, TEST_PROJECT_ID, FILES[1].file, emlUploadName)
    test.skip(!zip || !eml, 'setup upload failed')

    // 控制台错误采集 + 邮件正文/主题泄露检测（sample.eml 正文 "hi" / 主题 "e2e-preview"）
    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })
    const externalHosts = new Set<string>()
    page.on('request', (req) => {
      try {
        const u = new URL(req.url())
        if (u.hostname && u.hostname !== 'localhost' && u.hostname !== '127.0.0.1' && !u.hostname.endsWith('.local')) {
          externalHosts.add(u.hostname)
        }
      } catch {
        /* ignore */
      }
    })

    await page.addInitScript((t: string) => {
      window.sessionStorage.setItem('token', t)
      window.localStorage.setItem('token', t)
      ;(window as unknown as { __APFE_TEST_PROBE__?: boolean }).__APFE_TEST_PROBE__ = true
    }, token!)

    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/attachments`, {
      waitUntil: 'domcontentloaded',
      timeout: 60_000,
    })

    async function closeDialog() {
      await page.keyboard.press('Escape').catch(() => undefined)
      await page.locator('.el-dialog').first().waitFor({ state: 'hidden', timeout: 8000 }).catch(() => undefined)
    }
    async function openRow(name: string) {
      const row = page.locator('.gt-att-item-name', { hasText: name }).first()
      await expect(row).toBeVisible({ timeout: 30_000 })
      await row.click()
    }

    // ① 资源回收：真实 Worker 必须有 created/message/disposed，关闭后 scope 必须完整归零。
    let maxLiveAfterClose = { objectUrls: 0, workers: 0, controllers: 0, cleanups: 0 }
    for (let i = 0; i < 5; i++) {
      await openRow(zipUploadName)
      await expect(page.getByTestId('archive-entry-list').first()).toBeVisible({ timeout: 30_000 })
      await closeDialog()
      const live = (await page.evaluate(
        () => (window as unknown as {
          __APFE_SCOPE_LIVE__?: {
            objectUrls: number
            workers: number
            controllers: number
            cleanups: number
            released: boolean
          }
        }).__APFE_SCOPE_LIVE__ ?? null,
      )) as {
        objectUrls: number
        workers: number
        controllers: number
        cleanups: number
        released: boolean
      } | null
      expect(live, 'APFE probe missing: run Playwright with playwright.apfe.config.ts').not.toBeNull()
      expect(live?.released, `scope was not released after close: ${JSON.stringify(live)}`).toBe(true)
      maxLiveAfterClose = {
        objectUrls: Math.max(maxLiveAfterClose.objectUrls, live!.objectUrls),
        workers: Math.max(maxLiveAfterClose.workers, live!.workers),
        controllers: Math.max(maxLiveAfterClose.controllers, live!.controllers),
        cleanups: Math.max(maxLiveAfterClose.cleanups, live!.cleanups),
      }
    }
    const workerEvents = (await page.evaluate(
      () => (window as unknown as {
        __APFE_WORKER_EVENTS__?: { created: number; message: number; disposed: number }
      }).__APFE_WORKER_EVENTS__ ?? null,
    )) as { created: number; message: number; disposed: number } | null
    expect(workerEvents, 'APFE worker event probe missing').not.toBeNull()
    expect(workerEvents!.created).toBeGreaterThanOrEqual(5)
    expect(workerEvents!.message).toBeGreaterThanOrEqual(5)
    expect(workerEvents!.disposed).toBe(workerEvents!.created)
    expect(maxLiveAfterClose, `resources leaked after close: ${JSON.stringify(maxLiveAfterClose)}`).toEqual({
      objectUrls: 0,
      workers: 0,
      controllers: 0,
      cleanups: 0,
    })

    // ② JSON trap：把 zip 的 download 响应改成 application/json，必须进 wiring_error 且 logger ERROR 不含正文
    consoleErrors.length = 0
    await page.route(`**/api/attachments/${zip!.id}/download**`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ previewable: false, secret_body: 'MUST-NOT-LEAK' }),
      })
    })
    await openRow(zipUploadName)
    await expect(page.getByTestId('extended-preview-fallback').first()).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText(/预览通道配置错误|下载后查看/).first()).toBeVisible({ timeout: 10_000 })
    // 平台 logger ERROR 出现，且不含被拦响应正文
    const trapErr = consoleErrors.find((e) => /json_blob_trap|wiring_error|attachment_preview/i.test(e))
    expect(trapErr, `expected logger ERROR for JSON trap, saw: ${consoleErrors.join(' | ')}`).toBeTruthy()
    for (const e of consoleErrors) {
      expect(e, 'logger must not leak response body').not.toContain('MUST-NOT-LEAK')
    }
    await closeDialog()
    await page.unroute(`**/api/attachments/${zip!.id}/download**`)

    // ③ 邮件 CSP srcdoc + 零外发：打开 eml，HTML 帧 srcdoc 必须含 default-src 'none'，evil.example 不得被请求
    await openRow(emlUploadName)
    const frame = page.getByTestId('email-html-frame').first()
    await expect(frame).toBeVisible({ timeout: 30_000 })
    const srcdoc = await frame.getAttribute('srcdoc')
    expect(srcdoc, 'email iframe must carry CSP srcdoc').toContain("default-src 'none'")
    expect(srcdoc).toContain('img-src blob:')
    expect(await frame.getAttribute('sandbox')).toBe('')
    await expect(page.getByTestId('email-blocked').first()).toBeVisible({ timeout: 10_000 })
    await closeDialog()

    // 等一拍让潜在的外链请求发生（不应发生）
    await page.waitForTimeout(1000)
    expect(
      [...externalHosts].filter((h) => h.includes('evil.example')),
      `email must not fetch external hosts: ${[...externalHosts].join(',')}`,
    ).toEqual([])

    // 追加进 browser_evidence.json 的 scenarios
    const evPath = path.join(EVIDENCE_DIR, 'browser_evidence.json')
    let ev: Record<string, unknown> = {}
    try {
      ev = JSON.parse(fs.readFileSync(evPath, 'utf8'))
    } catch {
      ev = { spec: 'audit-evidence-attachment-preview-format-expansion', task: 19 }
    }
    ev.scenarios = {
      resource_release_x5: {
        max_live_after_close: maxLiveAfterClose,
        worker_events: workerEvents,
        passed: true,
      },
      json_blob_trap: { logger_error_no_body_leak: true, saw: trapErr ?? null },
      email_csp_srcdoc: { has_default_src_none: true, sandbox_empty: true },
      zero_external_host: { evil_example_requested: false },
    }
    ev.scenarios_recorded_at = new Date().toISOString()
    fs.writeFileSync(evPath, JSON.stringify(ev, null, 2))
  })
})
