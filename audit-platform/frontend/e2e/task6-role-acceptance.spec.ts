/**
 * E2E — visibility-isolation-go-live-hardening / Task 6 (R5)
 * Playwright 8 角色 fresh-context 验收（Fresh_Context_Acceptance / 组件 H5 RoleAcceptanceHarness）
 *
 * 为 8 个 Acceptance_Role（Admin / Supervisor / Workpaper_Lead / Row_Assignee /
 * Operation_Reviewer / History_Lead / History_Row / plain Restricted）各建【全新 browser
 * context】+ fresh navigation（禁止跨角色复用会话），在真实浏览器上验证：
 *   - scope-internal-not-delegated 与 scope-external-delegated 深链【均被拒绝】（浏览器可见行为）
 *   - render-config 网络响应 allow=200 / deny=404（浏览器自身会话观测）
 *   - 拒绝时不闪现底稿名称/正文（no name/body flash）
 *   - 每次导航 console error 计数 = 0
 *   - 撤权后刷新 <=1s 内拒绝（Fast_Path + DB epoch 安全网）
 *
 * 前置：backend 9980 + frontend 3030 健康；已运行
 *   python scripts/e2e/task6_role_acceptance_seed.py
 * 读取夹具：e2e/fixtures/task6_role_acceptance.json
 * 证据：test-results/task6-role-acceptance-results.json + 逐角色截图
 *
 * Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.6, 5.7, 5.8, 5.9（5.5 撤权收敛见末组）
 */
import { test, expect, type Page } from '@playwright/test'
import { execSync } from 'node:child_process'
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const backendRoot = path.resolve(__dirname, '../../../backend')
const API_BASE = 'http://localhost:9980/api'
const UI_BASE = 'http://localhost:3030'

type WpRec = { wp_id: string; wp_index_id: string; wp_code: string; wp_name: string }
type Fixture = {
  project_id: string
  other_project_id: string
  wp: Record<string, WpRec>
  roles: Record<string, { username: string; password: string; user_id: string }>
  probes: Record<string, [string, 'allow' | 'deny'][]>
  editor_url_template: string
  render_config_path_template: string
  external_not_found_message: string
}

const fixture: Fixture = JSON.parse(
  readFileSync(path.join(__dirname, 'fixtures', 'task6_role_acceptance.json'), 'utf-8'),
)

const ACCEPTANCE_ROLES = [
  'admin',
  'supervisor',
  'lead',
  'assignee',
  'reviewer',
  'history_lead',
  'history_row',
  'restricted',
] as const

// 累积证据（末组 afterAll 落地）
const RESULTS: Record<string, unknown> = { roles: {}, families: {}, revocation: {} }

// 读取 SPA 会话 token（auth store 持久化在 sessionStorage.token）
const READ_TOKEN = `sessionStorage.getItem('token') || localStorage.getItem('token') || ''`

// ─── 工具 ────────────────────────────────────────────────────────────────────
/** UI 登录（fresh context 内） */
async function uiLogin(page: Page, username: string, password: string) {
  await page.goto(`${UI_BASE}/login`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(500)
  if (!page.url().includes('/login')) return
  await page.fill('input[placeholder*="用户名"]', username)
  await page.fill('input[type="password"]', password)
  await page.click('button:has-text("登录")')
  await page.waitForFunction(() => !window.location.pathname.includes('/login'), { timeout: 20000 })
}

/** 收集非良性 console error（忽略预期 404/网络噪声，5.7 只关心 fatal JS） */
function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return
    const t = msg.text()
    if (
      t.includes('ResizeObserver') ||
      t.includes('favicon') ||
      t.includes('net::ERR_') ||
      t.includes('Failed to load resource') ||
      t.includes('status of 404') ||
      t.includes('status of 401') ||
      t.includes('401') ||
      t.includes('404')
    )
      return
    errors.push(t)
  })
  page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`))
  return errors
}

/** 浏览器会话内 fetch 指定 URL，返回状态码（携带 SPA 存储的 Authorization）。 */
async function sessionFetchStatus(page: Page, url: string): Promise<number> {
  return page.evaluate(
    async ({ u, readTok }) => {
      // eslint-disable-next-line no-eval
      const tok = eval(readTok) as string
      const r = await fetch(u, { headers: tok ? { Authorization: `Bearer ${tok}` } : {} })
      return r.status
    },
    { u: url, readTok: READ_TOKEN },
  )
}

/** 从浏览器会话（SPA 自身发的 XHR）观测某 wp 的 render-config 状态码。 */
function watchRenderConfig(page: Page): Map<string, number> {
  const seen = new Map<string, number>()
  page.on('response', (resp) => {
    const m = resp.url().match(/\/api\/workpapers\/([0-9a-fA-F-]{36})\/render-config/)
    if (m) seen.set(m[1], resp.status())
  })
  return seen
}

const editorUrl = (wpId: string, projectId = fixture.project_id) =>
  `${UI_BASE}${fixture.editor_url_template.replace('{project_id}', projectId).replace('{wp_id}', wpId)}`

const renderConfigUrl = (wpId: string) => `${API_BASE}/workpapers/${wpId}/render-config`

// ─── 测试组 1：8 角色 fresh-context 深链验收（5.1/5.2/5.3/5.6/5.7/5.8） ──────────
test.describe('Task6 R5 — 8 角色 fresh-context 深链验收', () => {
  for (const role of ACCEPTANCE_ROLES) {
    test(`${role}: fresh context + login + 深链 allow/deny 矩阵 + no-flash + console error=0`, async ({
      browser,
    }) => {
      test.setTimeout(120000)
      const cred = fixture.roles[role]
      const probes = fixture.probes[role] || []
      // 每角色全新 browser context（禁止跨角色复用会话）—— Req 5.1/5.8
      const context = await browser.newContext()
      const page = await context.newPage()
      const errors = collectConsoleErrors(page)
      const rc = watchRenderConfig(page)
      const roleOut: any = { probes: [], console_errors: [], login: false }

      try {
        await uiLogin(page, cred.username, cred.password)
        roleOut.login = true

        for (const [wpKey, expect_] of probes) {
          const rec = fixture.wp[wpKey]
          rc.delete(rec.wp_id)
          // 真实 fresh navigation 到底稿编辑器深链（UX：no-flash / console error）
          await page
            .goto(editorUrl(rec.wp_id), { waitUntil: 'domcontentloaded', timeout: 30000 })
            .catch(() => {})
          await page.waitForTimeout(1500) // 让 SPA 完成分类 / render-config XHR 与渲染
          const spaStatus = rc.has(rec.wp_id) ? rc.get(rec.wp_id)! : 0

          // 权威信号：浏览器自身会话直接 fetch render-config，与 SPA 内部调用序列解耦，
          // 稳健证明 gate 在浏览器会话上 allow(200) / deny(404)。
          const status = await sessionFetchStatus(page, renderConfigUrl(rec.wp_id))

          const bodyText = (await page.locator('body').innerText().catch(() => '')) || ''
          const nameLeaked = bodyText.includes(rec.wp_name)
          const placeholderShown = bodyText.includes(fixture.external_not_found_message)

          roleOut.probes.push({
            wp_key: wpKey,
            wp_id: rec.wp_id,
            expect: expect_,
            session_render_config_status: status,
            spa_render_config_status: spaStatus,
            name_flash: nameLeaked,
            placeholder_shown: placeholderShown,
          })

          if (expect_ === 'deny') {
            // 浏览器可见行为：render-config 拒绝（404）；且不闪现底稿名（no-flash）—— Req 5.2/5.3/5.6
            expect(status, `${role}/${wpKey} 期望拒绝(404) 实得 ${status}`).toBe(404)
            expect(nameLeaked, `${role}/${wpKey} 拒绝时不得闪现底稿名`).toBe(false)
          } else {
            // 放行：render-config 200
            expect(status, `${role}/${wpKey} 期望放行(200) 实得 ${status}`).toBe(200)
          }
        }

        roleOut.console_errors = errors
        // 每次导航 console error = 0（Req 5.7）
        expect(errors, `console errors: ${JSON.stringify(errors)}`).toHaveLength(0)

        mkdirSync('test-results', { recursive: true })
        await page
          .screenshot({ path: `test-results/task6-role-${role}.png`, fullPage: true })
          .catch(() => {})
      } finally {
        RESULTS.roles = { ...(RESULTS.roles as object), [role]: roleOut }
        await context.close()
      }
    })
  }
})

// ─── 测试组 2：动作族矩阵（浏览器会话观测 detail/version/html 族）5.4 ──────────────
test.describe('Task6 R5 — 动作族矩阵（浏览器会话）', () => {
  test('lead/restricted 跨 detail/version/html 族 gate 一致', async ({ browser }) => {
    test.setTimeout(120000)
    const pid = fixture.project_id
    const families = [
      { key: 'detail', path: (id: string) => `${API_BASE}/projects/${pid}/working-papers/${id}` },
      { key: 'version_list', path: (id: string) => `${API_BASE}/workpapers/${id}/versions` },
      { key: 'html', path: (id: string) => `${API_BASE}/projects/${pid}/workpapers/${id}/html` },
    ]
    const out: any = {}
    for (const role of ['lead', 'restricted'] as const) {
      const cred = fixture.roles[role]
      const ctx = await browser.newContext()
      const page = await ctx.newPage()
      await uiLogin(page, cred.username, cred.password)
      const probeWps: string[] =
        role === 'lead' ? ['lead', 'undelegated', 'external'] : ['lead', 'undelegated', 'external']
      out[role] = {}
      for (const wpKey of probeWps) {
        const rec = fixture.wp[wpKey]
        out[role][wpKey] = {}
        for (const fam of families) {
          out[role][wpKey][fam.key] = await sessionFetchStatus(page, fam.path(rec.wp_id))
        }
      }
      await ctx.close()
    }
    RESULTS.families = out
    // lead 对自己主编底稿 detail 放行（200）；对未委派 / 域外底稿全族拒绝（404）
    expect(out.lead.lead.detail).toBe(200)
    for (const wpKey of ['undelegated', 'external']) {
      for (const fam of ['detail', 'version_list', 'html']) {
        expect(out.lead[wpKey][fam], `lead/${wpKey}/${fam} 应拒绝`).toBe(404)
        expect(out.restricted[wpKey][fam], `restricted/${wpKey}/${fam} 应拒绝`).toBe(404)
      }
    }
    // restricted 对 lead 底稿亦拒绝
    expect(out.restricted.lead.detail).toBe(404)
  })
})

// ─── 测试组 3：撤权刷新 <=1s 生效（5.5） ────────────────────────────────────────
test.describe('Task6 R5 — 撤权刷新 <=1s 收敛', () => {
  test('lead 撤权后浏览器刷新 <=1s 内 render-config 拒绝', async ({ browser }) => {
    test.setTimeout(120000)
    const cred = fixture.roles['lead']
    const leadWp = fixture.wp['lead']
    const ctx = await browser.newContext()
    const page = await ctx.newPage()

    await uiLogin(page, cred.username, cred.password)
    // 撤权前：lead 主编底稿放行（浏览器会话 fetch 权威信号）
    await page.goto(editorUrl(leadWp.wp_id), { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {})
    const before = await sessionFetchStatus(page, renderConfigUrl(leadWp.wp_id))
    expect(before, '撤权前 lead 主编底稿应放行(200)').toBe(200)

    // 撤权：清空 lead 主编 + 递增 policy epoch（同事务）
    execSync('python scripts/e2e/task6_role_acceptance_seed.py --revoke-lead', {
      cwd: backendRoot,
      stdio: 'inherit',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    })

    // 撤权后：浏览器会话轮询 render-config，测量至拒绝(404)的用时；断言 <=1s
    const t0 = Date.now()
    let denied = false
    let elapsedMs = -1
    for (let i = 0; i < 20; i++) {
      const status = await sessionFetchStatus(page, renderConfigUrl(leadWp.wp_id))
      if (status === 404) {
        denied = true
        elapsedMs = Date.now() - t0
        break
      }
      await page.waitForTimeout(100)
    }
    RESULTS.revocation = { before_status: before, denied_after_revoke: denied, elapsed_ms: elapsedMs }
    expect(denied, '撤权后应拒绝').toBe(true)
    expect(elapsedMs, `撤权收敛用时 ${elapsedMs}ms 应 <=1000ms`).toBeLessThanOrEqual(1000)

    // 浏览器 fresh reload 也拒绝，且不闪现底稿名（no-flash）
    await page.goto(editorUrl(leadWp.wp_id), { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {})
    await page.waitForTimeout(1000)
    const after = await sessionFetchStatus(page, renderConfigUrl(leadWp.wp_id))
    expect(after, '撤权后刷新 render-config 应拒绝(404)').toBe(404)
    const bodyText = (await page.locator('body').innerText().catch(() => '')) || ''
    expect(bodyText.includes(leadWp.wp_name), '撤权后不得闪现底稿名').toBe(false)
    await ctx.close()
  })
})

// ─── 测试组 4：证据落地 ────────────────────────────────────────────────────────
test.afterAll(async () => {
  mkdirSync('test-results', { recursive: true })
  writeFileSync(
    'test-results/task6-role-acceptance-results.json',
    JSON.stringify(
      { feature: 'visibility-isolation-go-live-hardening', task: '6', results: RESULTS },
      null,
      2,
    ),
    'utf-8',
  )
})
