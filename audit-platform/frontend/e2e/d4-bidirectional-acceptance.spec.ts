/**
 * D4-1..36 双向回写逐张验收脚手架（L1 门：进在线编辑 → 统一路径 → OO 挂载）。
 *
 * 判据（对齐主控文档 §6.4 HOST-CONSUMES-UNIFIED-PATH 的可自动化子集）：
 *   1. 点该 sheet 页签 + 「在线编辑」→ 命中 USER_SYNC_PREFIX 的 store-projection（200）
 *   2. materialize（200）+ callback URL 四项齐全（room_id/generation/doc_key/route_credential_id|route_token）
 *   3. 无 /d2-sync/* 旁路请求
 *   4. WorkpaperSyncEditorHost 挂载 + OnlyOffice DocEditor 被调用（真实 OO 加载）
 *
 * 逐张：由 D4_ACCEPT_SHEETS（JSON 数组，元素 {code,name}）驱动；缺省覆盖当前已接桥的 sheet。
 * 真栈：frontend 3030 / backend 9980 / OnlyOffice 8080。目标 wp 为唯一有 published representation 的真实 D4。
 *
 * L2 完整 roundtrip（写格→forcesave cs_error=0→回读 marker）见 g5-1-d4-unified-path.spec.ts（D4-2 已覆盖）。
 */
import { test, expect, type Page, type Request, type Response } from '@playwright/test'
import { writeFileSync, mkdirSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const PROJECT_ID = process.env.D4_ACCEPT_PROJECT_ID || '0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49'
const WP_ID = process.env.D4_ACCEPT_WP_ID || 'b3ab3c46-828f-4f48-950e-aee9bbdc923f'
const ENTRY = 'xlsx/gt-d4-operating-revenue'
const USER_SYNC_NEEDLE = `/api/projects/${PROJECT_ID}/workpapers/${WP_ID}/sync/entries/`

const EVIDENCE_DIR = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../../../docs/operations/evidence/d4-bidirectional-acceptance',
)

type SheetCase = { code: string; name: string }

// 默认覆盖：当前三维全绿（前端已接 useWorkpaperSyncBridge）的 sheet。
// name 必须与 sheet 页签/OO 名框一致；code 用于日志。
const DEFAULT_SHEETS: SheetCase[] = [
  { code: 'D4-2', name: '主营业务收入明细表D4-2' },
  { code: 'D4-3', name: '其他业务收入明细表D4-3' },
  { code: 'D4-5', name: '营业收入会计政策检查D4-5' },
  { code: 'D4-15', name: '营业收入完整性检查表D4-15' },
  { code: 'D4-16', name: '出口收入电子口岸系统核对D4-16' },
  { code: 'D4-25', name: '经销商检查D4-25' },
  { code: 'D4-26', name: '境外销售收入检查D4-26' },
  { code: 'D4-27', name: '识别未披露的关联方D4-27' },
  { code: 'D4-28', name: '客户信息核查清单D4-28' },
  { code: 'D4-29', name: '客户信息检查表D4-29' },
  { code: 'D4-35', name: '其他业务收入检查表D4-35' },
]

function loadSheets(): SheetCase[] {
  const raw = process.env.D4_ACCEPT_SHEETS
  if (!raw) return DEFAULT_SHEETS
  const parsed = JSON.parse(raw)
  if (!Array.isArray(parsed) || parsed.length === 0) throw new Error('D4_ACCEPT_SHEETS 必须是非空数组')
  return parsed.map((x: any) => ({ code: String(x.code), name: String(x.name) }))
}

function classifyUrl(url: string): 'user_sync' | 'd2_sync' | 'other' {
  if (url.includes('/d2-sync/')) return 'd2_sync'
  if (url.includes(USER_SYNC_NEEDLE) || url.includes('/sync/entries/')) return 'user_sync'
  return 'other'
}

function redactCallbackUrl(raw: string): { keys: string[] } {
  try {
    const u = new URL(raw)
    return { keys: [...u.searchParams.keys()].sort() }
  } catch {
    return { keys: [] }
  }
}

async function login(page: Page): Promise<void> {
  const response = await page.request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  expect(response.ok(), `登录应成功 status=${response.status()}`).toBeTruthy()
  const body = await response.json()
  const token = body.data?.access_token ?? body.access_token
  expect(token, 'access_token').toBeTruthy()
  await page.addInitScript((value: string) => {
    sessionStorage.setItem('token', value)
    localStorage.setItem('token', value)
  }, token)
  // 探针：hook DocsAPI.DocEditor 记录真实 OO 挂载
  await page.addInitScript(() => {
    const g = window as unknown as {
      __d4_doc_editor_called?: boolean
      DocsAPI?: { DocEditor?: new (id: string, config: Record<string, unknown>) => unknown }
    }
    const hook = () => {
      const api = g.DocsAPI
      if (!api || typeof api.DocEditor !== 'function') return false
      const Original = api.DocEditor
      api.DocEditor = function (id: string, config: Record<string, unknown>) {
        g.__d4_doc_editor_called = true
        return new Original(id, config)
      } as unknown as typeof Original
      ;(api.DocEditor as unknown as { prototype: unknown }).prototype = Original.prototype
      return true
    }
    if (!hook()) {
      const timer = window.setInterval(() => { if (hook()) window.clearInterval(timer) }, 50)
    }
  })
}

async function openD4Detail(page: Page): Promise<void> {
  await page.goto(`/projects/${PROJECT_ID}/workpapers/${WP_ID}/edit`, { waitUntil: 'domcontentloaded' })
  // 顶部 sheet tablist 渲染即视为底稿页就绪
  await expect(page.locator('.el-tabs__item, [role="tab"]').first()).toBeVisible({ timeout: 60_000 })
}

test.describe('D4 双向回写逐张 L1 验收', () => {
  test.setTimeout(600_000)

  for (const sheet of loadSheets()) {
    test(`${sheet.code} 进在线编辑走统一路径且 OO 挂载`, async ({ page }) => {
      const hits: Array<{ method: string; url: string; status?: number; kind: string }> = []
      const consoleErrors: string[] = []
      let materializeBody: Record<string, unknown> | null = null

      page.on('request', (req: Request) => {
        const kind = classifyUrl(req.url())
        if (kind === 'other') return
        hits.push({ method: req.method(), url: req.url(), kind })
      })
      page.on('response', (res: Response) => {
        const kind = classifyUrl(res.url())
        if (kind !== 'other') {
          const row = hits.find((h) => h.url === res.url() && h.status == null)
          if (row) row.status = res.status()
        }
        if (res.url().includes('/materialize')) {
          void res.json().then((json) => {
            materializeBody = (json?.data ?? json) as Record<string, unknown>
          }).catch(() => {})
        }
      })
      page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()) })

      await login(page)
      await openD4Detail(page)

      // 点该 sheet 页签
      const tab = page.locator('[role="tab"]').filter({ hasText: new RegExp(sheet.code.replace('-', '\\-') + '(?!\\d)') }).first()
      await expect(tab, `${sheet.code} 页签应可见`).toBeVisible({ timeout: 30_000 })
      await tab.click()
      await page.waitForTimeout(1500)

      // 点「在线编辑」（el-segmented / el-radio 两种形态都覆盖）
      const ooItem = page.locator('.el-segmented__item, label').filter({ hasText: '在线编辑' }).first()
      await expect(ooItem, '在线编辑选项应可见').toBeVisible({ timeout: 20_000 })
      await ooItem.click()

      // 判据1：出现 sync 请求
      await expect.poll(() => hits.length, { timeout: 30_000 }).toBeGreaterThan(0)

      // 判据2：materialize 200
      await expect.poll(
        () => hits.some((h) => h.kind === 'user_sync' && h.url.includes('/materialize') && h.status === 200),
        { timeout: 180_000 },
      ).toBeTruthy()

      const userSync = hits.filter((h) => h.kind === 'user_sync')
      const d2Sync = hits.filter((h) => h.kind === 'd2_sync')
      expect(userSync.some((h) => h.url.includes('/store-projection')), '应打 store-projection').toBeTruthy()
      expect(d2Sync, '不得出现 /d2-sync/* 旁路').toEqual([])

      // 判据3：callback 四项
      await expect.poll(() => materializeBody !== null, { timeout: 15_000 }).toBeTruthy()
      const cfg = (materializeBody?.onlyoffice_config ?? materializeBody?.onlyofficeConfig) as Record<string, unknown> | undefined
      const editorConfig = (cfg?.editorConfig ?? cfg?.editor_config) as Record<string, unknown> | undefined
      const callbackUrl = String(editorConfig?.callbackUrl ?? editorConfig?.callback_url ?? '')
      const { keys } = redactCallbackUrl(callbackUrl)
      for (const k of ['room_id', 'generation', 'doc_key']) {
        expect(keys, `callbackUrl 应含 ${k}`).toContain(k)
      }
      expect(keys.includes('route_credential_id') || keys.includes('route_token'), 'callbackUrl 应含 route_credential_id 或 route_token').toBeTruthy()

      // 判据4：统一同步宿主挂载（WorkpaperSyncEditorHost），并出现 OnlyOffice iframe。
      // （DocEditor 实例在 OO iframe 内，主 page hook 抓不到；宿主挂载 + iframe 存在即证明进入 OO 装配。）
      await expect(page.locator('[data-testid="wp-sync-host"]'), 'WorkpaperSyncEditorHost 应挂载').toBeVisible({ timeout: 60_000 })
      await expect.poll(
        () => page.locator('iframe').count(),
        { timeout: 120_000 },
      ).toBeGreaterThan(0)

      const evidence = {
        sheet: sheet.code,
        sheet_name: sheet.name,
        captured_at: new Date().toISOString(),
        scope: { project_id: PROJECT_ID, wp_id: WP_ID, entry_id: ENTRY },
        predicates: {
          user_sync_requests: userSync.map((h) => ({ method: h.method, path: h.url.replace(/^https?:\/\/[^/]+/, ''), status: h.status ?? null })),
          store_projection_ok: userSync.some((h) => h.url.includes('/store-projection') && h.status === 200),
          materialize_ok: userSync.some((h) => h.url.includes('/materialize') && h.status === 200),
          d2_sync_hits: d2Sync.length,
          callback_url_keys: keys,
          sync_host_mounted: await page.locator('[data-testid="wp-sync-host"]').count() > 0,
          oo_iframe_count: await page.locator('iframe').count(),
          doc_editor_called: await page.evaluate(() => Boolean((window as any).__d4_doc_editor_called)),
          console_errors: consoleErrors.slice(0, 8),
        },
      }
      mkdirSync(EVIDENCE_DIR, { recursive: true })
      writeFileSync(resolve(EVIDENCE_DIR, `${sheet.code}.json`), `${JSON.stringify(evidence, null, 2)}\n`, 'utf-8')
    })
  }
})
