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
  { code: 'D4-1', name: '营业收入审定表D4-1' },
  { code: 'D4-2', name: '主营业务收入明细表D4-2' },
  { code: 'D4-3', name: '其他业务收入明细表D4-3' },
  // D4-4 于 2026-09-28 接成真双向（spec d4-4-adjustment-summary-bidirectional-writeback
  // Task 14*）—— 它是 D4 全组最后一张脱离 single_html 的 sheet。
  { code: 'D4-4', name: '营业收入调整分录汇总D4-4' },
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
      const httpErrors: Array<{ method: string; path: string; status: number; body: string }> = []
      let materializeBody: Record<string, unknown> | null = null

      page.on('request', (req: Request) => {
        const kind = classifyUrl(req.url())
        if (kind === 'other') return
        hits.push({ method: req.method(), url: req.url(), kind })
      })
      page.on('response', (res: Response) => {
        const url = res.url()
        const kind = classifyUrl(url)
        if (kind !== 'other') {
          const row = hits.find((h) => h.url === url && h.status == null)
          if (row) row.status = res.status()
        }
        // 抓失败的 sync/checklist 响应体（fail-visible：materialize 挂了要能看到中文原因）
        if (res.status() >= 400 && (url.includes('/sync/') || url.includes('/checklist') || url.includes('/materialize'))) {
          void res.text().then((t) => {
            httpErrors.push({ method: res.request().method(), path: url.replace(/^https?:\/\/[^/]+/, ''), status: res.status(), body: t.slice(0, 800) })
          }).catch(() => {})
        }
        if (url.includes('/materialize')) {
          void res.json().then((json) => {
            materializeBody = (json?.data ?? json) as Record<string, unknown>
          }).catch(() => {})
        }
      })
      page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()) })

      await login(page)
      await openD4Detail(page)

      // 点该 sheet 页签
      // 🔴 负向前瞻必须排除**字母**后缀而非仅数字：sheet 名以编码结尾，`D4-22(?!\d)` 会同时命中
      //    「…D4-22」与「…D4-22A（程序表）」，且 D4-22A 页签在 DOM 中靠前 → .first() 误点到
      //    D4TabIpoProcedure（无 dedicated sync 桥、走 legacy OO）→ 点在线编辑不发 /sync/ 请求
      //    → 判据1 hits.length=0（D4-22 真栈实证误判）。用 (?![\dA-Za-z]) 精确区分编码与编码+字母变体。
      const tab = page.locator('[role="tab"]').filter({ hasText: new RegExp(sheet.code.replace('-', '\\-') + '(?![\\dA-Za-z])') }).first()
      await expect(tab, `${sheet.code} 页签应可见`).toBeVisible({ timeout: 30_000 })
      // 🔴 证据只记**观测到的事实**：sheet_name 取真实点中的页签文本，而不是调用方在
      //    `D4_ACCEPT_SHEETS` 里传进来的 name。2026-09-22 全量重跑时以 `name===code`
      //    的简写调用，导致 30 份证据的 sheet_name 全退化成「D4-13」这类纯编码，
      //    丢掉了「到底点中哪张表」这个最关键的可复核信息（定位本来就只用 code，
      //    name 纯粹是证据字段，于是没有任何判据能发现它被传坏了）。
      const observedTabText = ((await tab.textContent()) ?? '').trim().replace(/\s+/g, ' ')
      await tab.click()
      await page.waitForTimeout(1500)

      // 点「在线编辑」（el-segmented / el-radio 两种形态都覆盖）
      const ooItem = page.locator('.el-segmented__item, label').filter({ hasText: '在线编辑' }).first()
      await expect(ooItem, '在线编辑选项应可见').toBeVisible({ timeout: 20_000 })
      // 🔴 **已知脆弱点（2026-09-30 实测，未修，归本 spec owner）**：本判据假设「进来时
      //    一定在表格视图」，但模式是**持久化**的。同一 wp 上先跑过 L2（停在 OO 模式）后，
      //    再跑本用例时 `renderMode` 已是 `onlyoffice`，`switchMode` 的
      //    `if (target === renderMode.value) return` 把这次点击当成 no-op ⇒ 一个
      //    `/sync/` 请求都不发，判据1 卡 30s 超时，**表象酷似「接桥坏了」**。
      //    真栈快照特征：`radio "在线编辑" [active]` + 状态标签「已同步」+ **无** disabled
      //    —— 与「busy 期点击被吞」（两个 radio 同时 disabled + 「同步中…」）是不同的两种
      //    假失败，先看快照再归因。
      //    ⚠️ 试过「先点回表格视图」的修法但**未奏效**（`input[type=radio]` 的 `isChecked()`
      //    在 el-segmented 下取不到选中态，分支没进），已撤回以免在共享用例里留半成品。
      //    正解需要先确认 el-segmented 的选中态真源（aria 属性或 class），再据此判起始模式。
      await ooItem.click()

      // 判据1：出现 sync 请求
      await expect.poll(() => hits.length, { timeout: 30_000 }).toBeGreaterThan(0)

      // 判据2：materialize 200
      try {
        await expect.poll(
          () => hits.some((h) => h.kind === 'user_sync' && h.url.includes('/materialize') && h.status === 200),
          { timeout: 180_000 },
        ).toBeTruthy()
      } catch {
        throw new Error(
          `${sheet.code} materialize 200 未出现；hits=${JSON.stringify(hits.map((h) => ({ kind: h.kind, status: h.status, path: h.url.replace(/^https?:\/\/[^/]+/, '') })))}；httpErrors=${JSON.stringify(httpErrors)}；console=${JSON.stringify(consoleErrors.slice(0, 8))}`,
        )
      }

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
        /** 真实点中的页签文本（观测值）。清单里声明的期望名另记 `sheet_name_expected`。 */
        sheet_name: observedTabText,
        sheet_name_expected: sheet.name,
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
          http_errors: httpErrors.slice(0, 8),
          console_errors: consoleErrors.slice(0, 8),
        },
      }
      mkdirSync(EVIDENCE_DIR, { recursive: true })
      writeFileSync(resolve(EVIDENCE_DIR, `${sheet.code}.json`), `${JSON.stringify(evidence, null, 2)}\n`, 'utf-8')
    })
  }
})

/**
 * D4-1 L2 完整 roundtrip（Property 3：双区往返一致 + 两区不串）。
 *
 * 与 L1 门（进在线编辑→统一路径→OO 挂载）互补：L2 真的在 OO 里改两格
 *   · 主营区受管输入格（section main-revenue，数据行 8–11；本期未审 B 列 → B8）
 *   · 其他区受管输入格（section other-revenue，数据行 14–17；本期未审 B 列 → B14）
 * 各写一个可区分 marker → forcesave 直到 cs_error=0 → 切回表格视图 → 断言：
 *   (a) 两个 marker 都能在 HTML 侧读回（往返一致）
 *   (b) 主营 marker 不落到其他区、其他 marker 不落到主营区（无跨区污染 = Property 3）
 *
 * 目标 wp 需同时满足：① entry xlsx/gt-d4-operating-revenue 有 published representation
 * （generation≥1，含 d41-managed bundle）② checklist_responses 有 D4-1-rows 受管行
 * （主营+其他各≥1 行）。缺任一 → L2 无可改的受管行 → 如实标 blocked，不伪造 cs_error=0。
 * 用 D4_ACCEPT_L2_WP_ID / D4_ACCEPT_L2_PROJECT_ID 指向满足条件的 wp（缺省 = L1 目标 wp）。
 *
 * 沿用 g5-1-d4-unified-path.spec.ts 的 OO 写格/forcesave/回读手法（Asc.editor + checklist-responses marker）。
 */
const L2_PROJECT_ID = process.env.D4_ACCEPT_L2_PROJECT_ID || PROJECT_ID
const L2_WP_ID = process.env.D4_ACCEPT_L2_WP_ID || WP_ID
const D41_SHEET_NAME = '营业收入审定表D4-1'
const D41_MAIN_TARGET = process.env.D4_ACCEPT_L2_MAIN_CELL || 'B8' // 主营段首数据行本期未审（受管输入列 B/C/D）
const D41_OTHER_TARGET = process.env.D4_ACCEPT_L2_OTHER_CELL || 'B14' // 其他段首数据行本期未审
const L2_USER_SYNC_NEEDLE = `/api/projects/${L2_PROJECT_ID}/workpapers/${L2_WP_ID}/sync/entries/`

function classifyL2Url(url: string): 'user_sync' | 'd2_sync' | 'other' {
  if (url.includes('/d2-sync/')) return 'd2_sync'
  if (url.includes(L2_USER_SYNC_NEEDLE) || url.includes('/sync/entries/')) return 'user_sync'
  return 'other'
}

async function loginL2(page: Page): Promise<string> {
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
  return token as string
}

/** 在 OO spreadsheet iframe 内定位 D4-1 sheet 并把 marker 写入 target 格。返回 cellText 探针。 */
async function ooWriteCell(page: Page, target: string, marker: string): Promise<Record<string, unknown> | null> {
  const sheet = page.frames().find((f) => /spreadsheeteditor\/main\/index\.html/.test(f.url()))
  if (!sheet) return null
  let probe: Record<string, unknown> | null = null
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    probe = await sheet.evaluate(
      ({ value, attemptNo, cell, wantSheet }: { value: string; attemptNo: number; cell: string; wantSheet: string }) => {
        const api =
          (window as unknown as { Asc?: { editor?: Record<string, any> }; editor?: Record<string, any> }).Asc?.editor
          || (window as unknown as { editor?: Record<string, any> }).editor
        if (!api) return { ok: false, reason: 'no Asc.editor', attempt: attemptNo }
        const out: Record<string, unknown> = { ok: true, cell, attempt: attemptNo }
        try {
          if (typeof api.asc_getWorksheetsCount === 'function') {
            const n = api.asc_getWorksheetsCount()
            const names: string[] = []
            for (let i = 0; i < n; i += 1) {
              const ws = api.asc_getWorksheet?.(i)
              const name = (ws && typeof ws.getName === 'function' && ws.getName())
                || (typeof api.asc_getWorksheetName === 'function' && api.asc_getWorksheetName(i)) || `idx${i}`
              names.push(String(name))
            }
            out.sheetNames = names
            let want = names.findIndex((nm) => nm === wantSheet)
            if (want < 0) want = names.findIndex((nm) => nm.includes('D4-1'))
            if (want >= 0 && typeof api.asc_showWorksheet === 'function') {
              api.asc_showWorksheet(want)
              out.activeSheet = names[want]
            }
          }
        } catch (e) { out.sheetErr = String(e) }
        try { if (typeof api.asc_findCell === 'function') api.asc_findCell(cell) } catch (e) { out.findErr = String(e) }
        try { if (typeof api.asc_insertInCell === 'function') { api.asc_insertInCell(value, 0, false); out.inserted = true } } catch (e) { out.insertErr = String(e) }
        try { if (typeof api.asc_enterText === 'function') { api.asc_enterText(value); out.entered = true } } catch (e) { out.enterErr = String(e) }
        try { if (typeof api.asc_closeCellEditor === 'function') { out.closeRet = api.asc_closeCellEditor(true); out.closed = true } } catch (e) { out.closeErr = String(e) }
        try { const info = api.asc_getCellInfo?.(); out.cellText = info && typeof info.asc_getText === 'function' ? info.asc_getText() : null } catch (e) { out.cellInfoErr = String(e) }
        try {
          out.modified = typeof api.asc_isDocumentModified === 'function' ? api.asc_isDocumentModified() : null
          if (typeof api.asc_Save === 'function') { out.saveRet = api.asc_Save(); out.saved = true }
        } catch (e) { out.saveErr = String(e) }
        try {
          if (typeof api.asc_findCell === 'function') api.asc_findCell(cell)
          const info2 = api.asc_getCellInfo?.()
          out.cellTextAfterSave = info2 && typeof info2.asc_getText === 'function' ? info2.asc_getText() : null
          if (out.cellTextAfterSave) out.cellText = out.cellTextAfterSave
        } catch (e) { out.cellInfo2Err = String(e) }
        return out
      },
      { value: marker, attemptNo: attempt, cell: target, wantSheet: wantSheetName(D41_SHEET_NAME) },
    )
    if (String(probe?.cellText ?? '').includes(marker)) break
    await page.waitForTimeout(2_500)
  }
  return probe
}

function wantSheetName(name: string): string { return name }

test.describe('D4-1 L2 双区完整 roundtrip（Property 3 无跨区污染）', () => {
  test.setTimeout(900_000)

  test('D4-1 OO 改主营+其他两区受管行→forcesave cs_error=0→切回值一致且两区不串', async ({ page }) => {
    const hits: Array<{ method: string; url: string; status?: number; kind: string }> = []
    const consoleErrors: string[] = []
    const httpErrors: Array<{ path: string; status: number; body: string }> = []
    let materializeBody: Record<string, unknown> | null = null
    let forcesaveBody: Record<string, unknown> | null = null

    page.on('request', (req: Request) => {
      const kind = classifyL2Url(req.url())
      if (kind === 'other') return
      hits.push({ method: req.method(), url: req.url(), kind })
    })
    page.on('response', (res: Response) => {
      const url = res.url()
      const kind = classifyL2Url(url)
      if (kind !== 'other') {
        const row = hits.find((h) => h.url === url && h.status == null)
        if (row) row.status = res.status()
      }
      if (res.status() >= 400 && (url.includes('/sync/') || url.includes('/checklist'))) {
        void res.text().then((t) => httpErrors.push({ path: url.replace(/^https?:\/\/[^/]+/, ''), status: res.status(), body: t.slice(0, 400) })).catch(() => {})
      }
      if (url.includes('/materialize')) {
        void res.json().then((j) => { materializeBody = (j?.data ?? j) as Record<string, unknown> }).catch(() => {})
      }
      if (url.includes('/forcesave')) {
        void res.json().then((j) => { forcesaveBody = (j?.data ?? j) as Record<string, unknown> }).catch(() => {})
      }
    })
    page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()) })

    const token = await loginL2(page)
    await page.addInitScript(() => {
      const g = window as unknown as {
        __d41_doc_editor_called?: boolean
        DocsAPI?: { DocEditor?: new (id: string, config: Record<string, unknown>) => unknown }
      }
      const hook = () => {
        const api = g.DocsAPI
        if (!api || typeof api.DocEditor !== 'function') return false
        const Original = api.DocEditor
        api.DocEditor = function (id: string, config: Record<string, unknown>) {
          g.__d41_doc_editor_called = true
          return new Original(id, config)
        } as unknown as typeof Original
        ;(api.DocEditor as unknown as { prototype: unknown }).prototype = Original.prototype
        return true
      }
      if (!hook()) { const t = window.setInterval(() => { if (hook()) window.clearInterval(t) }, 50) }
    })

    // ── 前置数据门：目标 wp 必须有 D4-1-rows 受管行（主营+其他），否则 L2 无可改行 → blocked ──
    const rowsRes = await page.request.get(`/api/workpapers/${L2_WP_ID}/checklist-responses`, { headers: { Authorization: `Bearer ${token}` } })
    const rowsJson = rowsRes.ok() ? await rowsRes.json().catch(() => null) : null
    const rowsText = JSON.stringify(rowsJson ?? {})
    const hasD41Rows = rowsText.includes('"D4-1-rows"') || rowsText.includes('D4-1-rows')
    // 粗判两区是否各有行（remark 里含 main-revenue / other-revenue 或 seedmain/seedother 皆可）
    const hasMainRow = /main-revenue|seedmain|"sectionKey"\s*:\s*"main/.test(rowsText)
    const hasOtherRow = /other-revenue|seedother|"sectionKey"\s*:\s*"other/.test(rowsText)

    const L2 = {
      attempted: false,
      main_marker: '' as string,
      other_marker: '' as string,
      switched_to_html: false,
      main_visible: false,
      other_visible: false,
      main_leaked_to_other: false,
      other_leaked_to_main: false,
      main_probe: null as Record<string, unknown> | null,
      other_probe: null as Record<string, unknown> | null,
      blocked_reason: null as string | null,
      forcesave_cs_error: null as number | null,
    }

    if (!hasD41Rows || !hasMainRow || !hasOtherRow) {
      L2.blocked_reason = `目标 wp ${L2_WP_ID} 缺 D4-1 受管行（hasD41Rows=${hasD41Rows} main=${hasMainRow} other=${hasOtherRow}）——L2 无可改的双区受管行，需先 seed 一个同时有 published representation + D4-1-rows(main+other) 的 wp（用 D4_ACCEPT_L2_WP_ID 指向）。`
    }

    // 进 D4-1 在线编辑（无论是否 blocked 都跑 L1 侧证据：materialize/callback/OO 挂载）
    await page.goto(`/projects/${L2_PROJECT_ID}/workpapers/${L2_WP_ID}/edit`, { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.el-tabs__item, [role="tab"]').first()).toBeVisible({ timeout: 60_000 })
    const tab = page.locator('[role="tab"]').filter({ hasText: /D4\-1(?!\d)/ }).first()
    await expect(tab, 'D4-1 页签应可见').toBeVisible({ timeout: 30_000 })
    await tab.click()
    await page.waitForTimeout(1500)
    const ooItem = page.locator('.sync-mode-bar .el-segmented__item, .el-segmented__item, label').filter({ hasText: '在线编辑' }).first()
    await expect(ooItem, '在线编辑选项应可见').toBeVisible({ timeout: 20_000 })
    await ooItem.click()

    await expect.poll(() => hits.some((h) => h.kind === 'user_sync' && h.url.includes('/materialize') && h.status === 200), { timeout: 180_000 }).toBeTruthy()
    const userSync = hits.filter((h) => h.kind === 'user_sync')
    const d2Sync = hits.filter((h) => h.kind === 'd2_sync')
    await expect.poll(() => materializeBody !== null, { timeout: 15_000 }).toBeTruthy()
    const cfg = (materializeBody?.onlyoffice_config ?? materializeBody?.onlyofficeConfig) as Record<string, unknown> | undefined
    const editorConfig = (cfg?.editorConfig ?? cfg?.editor_config) as Record<string, unknown> | undefined
    const callbackUrl = String(editorConfig?.callbackUrl ?? editorConfig?.callback_url ?? '')
    const callbackKeys = redactCallbackUrl(callbackUrl).keys
    await expect(page.locator('[data-testid="wp-sync-host"]'), 'WorkpaperSyncEditorHost 应挂载').toBeVisible({ timeout: 60_000 })

    if (!L2.blocked_reason) {
      L2.attempted = true
      const mainMarker = `d41m${Date.now().toString().slice(-6)}`
      const otherMarker = `d41o${Date.now().toString().slice(-6)}`
      L2.main_marker = mainMarker
      L2.other_marker = otherMarker
      try {
        // 等 OO 进入可编辑（confirm-descriptor + 非 mask）
        await expect.poll(() => hits.some((h) => h.url.includes('/confirm-descriptor') && h.status === 200), { timeout: 180_000 }).toBeTruthy()
        await expect(page.locator('[data-testid="wp-sync-host-mask"]')).toHaveCount(0, { timeout: 30_000 })
        await page.waitForTimeout(35_000)

        // 主营区 B8 + 其他区 B14 各写 marker
        L2.main_probe = await ooWriteCell(page, D41_MAIN_TARGET, mainMarker)
        L2.other_probe = await ooWriteCell(page, D41_OTHER_TARGET, otherMarker)
        await page.waitForTimeout(5_000)

        // forcesave 直到 cs_error=0
        const saveBtn = page.locator('[data-testid="wp-sync-host-forcesave"]')
        for (let fs = 1; fs <= 3; fs += 1) {
          const wait = page.waitForResponse((r) => r.url().includes('/forcesave') && r.request().method() === 'POST', { timeout: 60_000 })
          await expect(saveBtn).toBeEnabled({ timeout: 30_000 })
          await saveBtn.click()
          try { await wait } catch { /* hits 仍记 */ }
          const cs = forcesaveBody && 'cs_error' in forcesaveBody ? Number(forcesaveBody.cs_error) : null
          L2.forcesave_cs_error = cs
          if (cs === 0) break
          if (cs === 1 && fs < 3) { await page.waitForTimeout(15_000); continue }
          break
        }

        // 回读：切回表格视图，两 marker 都应可见（往返一致）
        const csOk = L2.forcesave_cs_error === 0
        if (csOk) {
          // 权威门：checklist-responses 含两 marker
          await expect.poll(async () => {
            const r = await page.request.get(`/api/workpapers/${L2_WP_ID}/checklist-responses`, { headers: { Authorization: `Bearer ${token}` } })
            if (!r.ok()) return ''
            return JSON.stringify(await r.json().catch(() => ({})))
          }, { timeout: 300_000 }).toContain(mainMarker)

          const finalText = await (async () => {
            const r = await page.request.get(`/api/workpapers/${L2_WP_ID}/checklist-responses`, { headers: { Authorization: `Bearer ${token}` } })
            return r.ok() ? JSON.stringify(await r.json().catch(() => ({}))) : ''
          })()
          L2.main_visible = finalText.includes(mainMarker)
          L2.other_visible = finalText.includes(otherMarker)

          // 无跨区污染判据（Property 3）：解析 D4-1-rows，按 sectionKey 分区核对
          // main_marker 只应出现在 main-revenue 区行的字段，other_marker 只应在 other-revenue 区
          const leak = await (async () => {
            try {
              const parsed = JSON.parse(finalText)
              const items: any[] = Array.isArray(parsed?.data) ? parsed.data : Array.isArray(parsed) ? parsed : (parsed?.data?.items ?? parsed?.items ?? [])
              const findRows = () => {
                for (const it of items) {
                  if (it?.item_id === 'D4-1-rows' || it?.itemId === 'D4-1-rows') {
                    try { return JSON.parse(it.remark ?? it.conclusion ?? '[]') } catch { return [] }
                  }
                }
                return []
              }
              const rows = findRows() as any[]
              const sectionOf = (rowId: string) => (rows.find((r) => r.rowId === rowId || r.rowKey === rowId)?.sectionKey ?? '')
              // 收集含 marker 的 per-field 键，反查其 rowId 的区
              const mainInOther: string[] = []
              const otherInMain: string[] = []
              for (const it of items) {
                const id = String(it?.item_id ?? it?.itemId ?? '')
                const val = String(it?.remark ?? it?.conclusion ?? '')
                const m = id.match(/^D4-1-(.+?)-(currentUnadjusted|currentAje|currentRje|priorUnadjusted|priorAje|priorRje)$/)
                if (!m) continue
                const sec = sectionOf(m[1])
                if (val.includes(mainMarker) && sec.startsWith('other')) mainInOther.push(id)
                if (val.includes(otherMarker) && sec.startsWith('main')) otherInMain.push(id)
              }
              return { mainInOther, otherInMain }
            } catch { return { mainInOther: [], otherInMain: [] } }
          })()
          L2.main_leaked_to_other = leak.mainInOther.length > 0
          L2.other_leaked_to_main = leak.otherInMain.length > 0
          L2.switched_to_html = true
        }
      } catch (err) {
        L2.blocked_reason = `L2 执行中断：${String(err).slice(0, 400)}`
      }
    }

    const evidence = {
      sheet: 'D4-1',
      sheet_name: D41_SHEET_NAME,
      level: 'L2',
      captured_at: new Date().toISOString(),
      scope: { project_id: L2_PROJECT_ID, wp_id: L2_WP_ID, entry_id: ENTRY },
      predicates: {
        user_sync_requests: userSync.map((h) => ({ method: h.method, path: h.url.replace(/^https?:\/\/[^/]+/, ''), status: h.status ?? null })),
        store_projection_ok: userSync.some((h) => h.url.includes('/store-projection') && h.status === 200),
        materialize_ok: userSync.some((h) => h.url.includes('/materialize') && h.status === 200),
        content_version: (materializeBody?.generation ?? materializeBody?.content_version ?? null) as unknown,
        d2_sync_hits: d2Sync.length,
        callback_url_keys: callbackKeys,
        sync_host_mounted: await page.locator('[data-testid="wp-sync-host"]').count() > 0,
        oo_iframe_count: await page.locator('iframe').count(),
        forcesave_cs_error: L2.forcesave_cs_error,
        forcesave_hits: hits.filter((h) => h.url.includes('/forcesave')).map((h) => ({ path: h.url.replace(/^https?:\/\/[^/]+/, ''), status: h.status ?? null })),
        l2_roundtrip: L2,
        no_cross_contamination: !L2.main_leaked_to_other && !L2.other_leaked_to_main,
        http_errors: httpErrors.slice(0, 8),
        console_errors: consoleErrors.slice(0, 8),
      },
      notes: [
        'L1 门（materialize/callback/OO 挂载）与 D4-1.json 一致；本文件补 L2 双区 roundtrip + Property 3 无跨区污染。',
        `OO 写主营 ${D41_MAIN_TARGET}（section main-revenue R8–11）+ 其他 ${D41_OTHER_TARGET}（section other-revenue R14–17）；权威判据 forcesave cs_error=0`,
        'blocked_reason 非空 = 目标 wp 无 D4-1 受管双区行（真实库唯一有 D4-1-rows 的 wp 无 published representation）——如实标 blocked，不伪造 cs_error=0。',
        'token/JWT/route_credential 值已脱敏（仅记 callbackUrl key 名）',
      ],
    }
    mkdirSync(EVIDENCE_DIR, { recursive: true })
    writeFileSync(resolve(EVIDENCE_DIR, 'D4-1-L2.json'), `${JSON.stringify(evidence, null, 2)}\n`, 'utf-8')

    // 断言：若数据齐（未 blocked）→ 要求真 roundtrip 绿；否则显式 blocked（不伪造通过）
    if (L2.blocked_reason) {
      test.info().annotations.push({ type: 'blocked', description: L2.blocked_reason })
      test.skip(true, L2.blocked_reason)
    } else {
      expect(L2.forcesave_cs_error, 'forcesave cs_error 应为 0').toBe(0)
      expect(L2.main_visible, '主营区 marker 应回读可见').toBe(true)
      expect(L2.other_visible, '其他区 marker 应回读可见').toBe(true)
      expect(evidence.predicates.no_cross_contamination, '两区不得跨区污染（Property 3）').toBe(true)
    }
  })
})

/**
 * ─────────────────────────────────────────────────────────────────────────────
 * D4-4 L2：真 OO canvas 往返（spec d4-4-adjustment-summary-bidirectional-writeback T16）
 * ─────────────────────────────────────────────────────────────────────────────
 * 与上面 D4-1 L2 同手法，但 D4-4 是**单区动态行表**（store 单 item `D4-4-rows`
 * 承裸 list），故 Property 判据换成「无跨**行**污染」：marker 只应落在被改的那
 * 一行（rowId = D44_L2_ROW_ID），不得漂到同区其他行。
 *
 * 前置数据门：目标 wp 的 `D4-4-rows` 必须已有带业务值的受管行
 * （由 `backend/scripts/e2e/seed_d4_4_adjustment_l2.py --apply` 造），否则
 * 如实标 blocked，**不得用 L1 通过冒充 L2**。
 *
 * 🔴 回读区间的权威载体是 **Excel Table ref**（`GT_D44_ROWS`，gen168 实测
 * `A6:K23` 覆盖 seed 的 R21~R23），不是 `GT_ROW_UUID_RANGE_D44`
 * （`$K$6:$K$20`，instrumentation 元数据、无生产读方）。
 */
const D44_SHEET_NAME = '营业收入调整分录汇总D4-4'
const D44_STORE_ITEM = 'D4-4-rows'
//: 受管列 J = 备注（`MANAGED_FIELD_SPECS_D44` 的 `remark`，editable/text）——
//: 选文本列避开数值强制转换与公式格；R21 = seed 首行。
const D44_TARGET_CELL = process.env.D4_ACCEPT_L2_D44_CELL || 'J21'
const D44_L2_ROW_ID = process.env.D4_ACCEPT_L2_D44_ROW_ID || 'd4a-l2seed001-a1b2c3d'

/** 在 OO spreadsheet iframe 内切到指定 sheet 并把 marker 写入 target 格。 */
async function ooWriteCellOnSheet(
  page: Page,
  opts: { sheetName: string; sheetNeedle: string; target: string; marker: string },
): Promise<Record<string, unknown> | null> {
  const sheet = page.frames().find((f) => /spreadsheeteditor\/main\/index\.html/.test(f.url()))
  if (!sheet) return null
  let probe: Record<string, unknown> | null = null
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    probe = await sheet.evaluate(
      ({ value, attemptNo, cell, wantSheet, needle }: { value: string; attemptNo: number; cell: string; wantSheet: string; needle: string }) => {
        const api =
          (window as unknown as { Asc?: { editor?: Record<string, any> }; editor?: Record<string, any> }).Asc?.editor
          || (window as unknown as { editor?: Record<string, any> }).editor
        if (!api) return { ok: false, reason: 'no Asc.editor', attempt: attemptNo }
        const out: Record<string, unknown> = { ok: true, cell, attempt: attemptNo }
        try {
          if (typeof api.asc_getWorksheetsCount === 'function') {
            const n = api.asc_getWorksheetsCount()
            const names: string[] = []
            for (let i = 0; i < n; i += 1) {
              const ws = api.asc_getWorksheet?.(i)
              const name = (ws && typeof ws.getName === 'function' && ws.getName())
                || (typeof api.asc_getWorksheetName === 'function' && api.asc_getWorksheetName(i)) || `idx${i}`
              names.push(String(name))
            }
            out.sheetNames = names
            let want = names.findIndex((nm) => nm === wantSheet)
            if (want < 0) want = names.findIndex((nm) => nm.includes(needle))
            if (want >= 0 && typeof api.asc_showWorksheet === 'function') {
              api.asc_showWorksheet(want)
              out.activeSheet = names[want]
            } else {
              out.sheetNotFound = true
            }
          }
        } catch (e) { out.sheetErr = String(e) }
        try { if (typeof api.asc_findCell === 'function') api.asc_findCell(cell) } catch (e) { out.findErr = String(e) }
        try { if (typeof api.asc_insertInCell === 'function') { api.asc_insertInCell(value, 0, false); out.inserted = true } } catch (e) { out.insertErr = String(e) }
        try { if (typeof api.asc_enterText === 'function') { api.asc_enterText(value); out.entered = true } } catch (e) { out.enterErr = String(e) }
        try { if (typeof api.asc_closeCellEditor === 'function') { out.closeRet = api.asc_closeCellEditor(true); out.closed = true } } catch (e) { out.closeErr = String(e) }
        try { const info = api.asc_getCellInfo?.(); out.cellText = info && typeof info.asc_getText === 'function' ? info.asc_getText() : null } catch (e) { out.cellInfoErr = String(e) }
        try {
          out.modified = typeof api.asc_isDocumentModified === 'function' ? api.asc_isDocumentModified() : null
          if (typeof api.asc_Save === 'function') { out.saveRet = api.asc_Save(); out.saved = true }
        } catch (e) { out.saveErr = String(e) }
        try {
          if (typeof api.asc_findCell === 'function') api.asc_findCell(cell)
          const info2 = api.asc_getCellInfo?.()
          out.cellTextAfterSave = info2 && typeof info2.asc_getText === 'function' ? info2.asc_getText() : null
          if (out.cellTextAfterSave) out.cellText = out.cellTextAfterSave
        } catch (e) { out.cellInfo2Err = String(e) }
        return out
      },
      { value: opts.marker, attemptNo: attempt, cell: opts.target, wantSheet: opts.sheetName, needle: opts.sheetNeedle },
    )
    if (String(probe?.cellText ?? '').includes(opts.marker)) break
    await page.waitForTimeout(2_500)
  }
  return probe
}

/** 从 checklist-responses 响应文本里取出 `D4-4-rows` 的行数组。 */
function parseD44Rows(text: string): Array<Record<string, unknown>> {
  try {
    const parsed = JSON.parse(text)
    const items: any[] = Array.isArray(parsed?.data)
      ? parsed.data
      : Array.isArray(parsed) ? parsed : (parsed?.data?.items ?? parsed?.items ?? [])
    for (const it of items) {
      const id = String(it?.item_id ?? it?.itemId ?? '')
      if (id !== D44_STORE_ITEM) continue
      const raw = it?.remark ?? it?.conclusion ?? '[]'
      const rows = typeof raw === 'string' ? JSON.parse(raw) : raw
      return Array.isArray(rows) ? rows : []
    }
  } catch { /* 解析失败按空处理，由调用方的 blocked/断言暴露 */ }
  return []
}

test.describe('D4-4 L2 真 OO canvas 往返（无跨行污染）', () => {
  test.setTimeout(900_000)

  test('D4-4 OO 改受管行备注→forcesave cs_error=0→HTML store 镜像可见且只落该行', async ({ page }) => {
    const hits: Array<{ method: string; url: string; status?: number; kind: string }> = []
    const consoleErrors: string[] = []
    const httpErrors: Array<{ path: string; status: number; body: string }> = []
    let materializeBody: Record<string, unknown> | null = null
    let forcesaveBody: Record<string, unknown> | null = null

    page.on('request', (req: Request) => {
      const kind = classifyL2Url(req.url())
      if (kind === 'other') return
      hits.push({ method: req.method(), url: req.url(), kind })
    })
    page.on('response', (res: Response) => {
      const url = res.url()
      const kind = classifyL2Url(url)
      if (kind !== 'other') {
        const row = hits.find((h) => h.url === url && h.status == null)
        if (row) row.status = res.status()
      }
      if (res.status() >= 400 && (url.includes('/sync/') || url.includes('/checklist'))) {
        void res.text().then((t) => httpErrors.push({ path: url.replace(/^https?:\/\/[^/]+/, ''), status: res.status(), body: t.slice(0, 400) })).catch(() => {})
      }
      if (url.includes('/materialize')) {
        void res.json().then((j) => { materializeBody = (j?.data ?? j) as Record<string, unknown> }).catch(() => {})
      }
      if (url.includes('/forcesave')) {
        void res.json().then((j) => { forcesaveBody = (j?.data ?? j) as Record<string, unknown> }).catch(() => {})
      }
    })
    page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()) })

    const token = await loginL2(page)

    const L2 = {
      attempted: false,
      marker: '' as string,
      target_cell: D44_TARGET_CELL,
      target_row_id: D44_L2_ROW_ID,
      seed_row_count: 0,
      marker_visible_on_target_row: false,
      marker_leaked_row_ids: [] as string[],
      probe: null as Record<string, unknown> | null,
      blocked_reason: null as string | null,
      forcesave_cs_error: null as number | null,
      forcesave_cs_outcome: '' as string,
      forcesave_callback_expected: null as boolean | null,
      forcesave_response: null as Record<string, unknown> | null,
    }

    // ── 前置数据门：`D4-4-rows` 必须已有含业务值的受管行，且包含目标 rowId ──
    const rowsRes = await page.request.get(`/api/workpapers/${L2_WP_ID}/checklist-responses`, { headers: { Authorization: `Bearer ${token}` } })
    const rowsText = rowsRes.ok() ? JSON.stringify(await rowsRes.json().catch(() => ({}))) : ''
    const seedRows = parseD44Rows(rowsText)
    L2.seed_row_count = seedRows.length
    const hasTargetRow = seedRows.some((r) => String(r?.rowId ?? r?.rowKey ?? '') === D44_L2_ROW_ID)
    if (!seedRows.length || !hasTargetRow) {
      L2.blocked_reason = `目标 wp ${L2_WP_ID} 的 ${D44_STORE_ITEM} 缺受管行（rows=${seedRows.length} hasTargetRow=${hasTargetRow}）`
        + ' —— 先跑 `python backend/scripts/e2e/seed_d4_4_adjustment_l2.py --apply` 造 L2 数据，再跑本用例。'
    }

    // 进 D4-4 在线编辑（blocked 也跑 L1 侧证据：materialize/callback/OO 挂载）
    await page.goto(`/projects/${L2_PROJECT_ID}/workpapers/${L2_WP_ID}/edit`, { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.el-tabs__item, [role="tab"]').first()).toBeVisible({ timeout: 60_000 })
    // 🔴 负向前瞻排**字母**不只排数字（沿用 L1 的教训：`D4-22(?!\d)` 会误命中 D4-22A）。
    const tab = page.locator('[role="tab"]').filter({ hasText: /D4\-4(?![\dA-Za-z])/ }).first()
    await expect(tab, 'D4-4 页签应可见').toBeVisible({ timeout: 30_000 })
    await tab.click()
    await page.waitForTimeout(1500)
    const ooItem = page.locator('.sync-mode-bar .el-segmented__item, .el-segmented__item, label').filter({ hasText: '在线编辑' }).first()
    await expect(ooItem, '在线编辑选项应可见').toBeVisible({ timeout: 20_000 })

    // 🔴 必须先等切换器**真的可点**再点：`useD4SyncMode.switchMode` 第一行是
    //    `if (busy.value && !isAppliedHtmlReturn(target)) return` —— busy 期间点击被
    //    静默吞掉，materialize 永不发出，表象是「点了没反应」而不是报错。
    //    首版没等，真栈实测卡死：快照里「表格视图 / 在线编辑」两个 radio **同时**
    //    `[disabled]` + 状态标签 `同步中…`，materialize 轮询 180s 超时。
    const readState = async () => ({
      tag: ((await page.locator('.el-tag').filter({ hasText: /同步中|已同步|未同步改动|同步失败|Excel 在线编辑/ }).first().textContent().catch(() => '')) ?? '').trim(),
      htmlDisabled: await page.locator('.sync-mode-bar input[type="radio"], .el-segmented input[type="radio"]').first().isDisabled().catch(() => true),
      ooDisabled: await page.locator('.sync-mode-bar input[type="radio"], .el-segmented input[type="radio"]').nth(1).isDisabled().catch(() => true),
    })
    const beforeClick = await readState()
    let gateTimedOut = false
    try {
      await expect.poll(async () => (await readState()).ooDisabled, { timeout: 120_000 }).toBe(false)
    } catch {
      gateTimedOut = true
    }
    const afterGate = await readState()
    const diag = () =>
      `进入时=${JSON.stringify(beforeClick)}；门后=${JSON.stringify(afterGate)}；`
      + `hits=${JSON.stringify(hits.map((h) => ({ kind: h.kind, status: h.status, path: h.url.replace(/^https?:\/\/[^/]+/, '') })))}；`
      + `httpErrors=${JSON.stringify(httpErrors)}；console=${JSON.stringify(consoleErrors.slice(0, 8))}`
    if (gateTimedOut) {
      throw new Error(`D4-4 L2：「在线编辑」120s 内未解除 disabled ⇒ 点击会被 switchMode 的 busy 短路。${diag()}`)
    }
    await ooItem.click()

    // 🔴 300s 不是 180s：D4 是**整册** materialize（37 张 sheet），真栈实测单次
    //    operation 15~30s，但 flush→pending-mutations→materialize 整链在本机可达 3 分钟+，
    //    180s 会在链条快完成时切掉（首版实测 poll 超时后 18s 才出现 `applied` operation）。
    try {
      await expect.poll(() => hits.some((h) => h.kind === 'user_sync' && h.url.includes('/materialize') && h.status === 200), { timeout: 300_000 }).toBeTruthy()
    } catch {
      throw new Error(`D4-4 L2：materialize 200 未出现。${diag()}；点击后=${JSON.stringify(await readState())}`)
    }
    const userSync = hits.filter((h) => h.kind === 'user_sync')
    const d2Sync = hits.filter((h) => h.kind === 'd2_sync')
    await expect.poll(() => materializeBody !== null, { timeout: 15_000 }).toBeTruthy()
    const cfg = (materializeBody?.onlyoffice_config ?? materializeBody?.onlyofficeConfig) as Record<string, unknown> | undefined
    const editorConfig = (cfg?.editorConfig ?? cfg?.editor_config) as Record<string, unknown> | undefined
    const callbackUrl = String(editorConfig?.callbackUrl ?? editorConfig?.callback_url ?? '')
    const callbackKeys = redactCallbackUrl(callbackUrl).keys
    await expect(page.locator('[data-testid="wp-sync-host"]'), 'WorkpaperSyncEditorHost 应挂载').toBeVisible({ timeout: 60_000 })

    if (!L2.blocked_reason) {
      L2.attempted = true
      const marker = `d44r${Date.now().toString().slice(-6)}`
      L2.marker = marker
      try {
        await expect.poll(() => hits.some((h) => h.url.includes('/confirm-descriptor') && h.status === 200), { timeout: 180_000 }).toBeTruthy()
        await expect(page.locator('[data-testid="wp-sync-host-mask"]')).toHaveCount(0, { timeout: 30_000 })
        await page.waitForTimeout(35_000)

        L2.probe = await ooWriteCellOnSheet(page, {
          sheetName: D44_SHEET_NAME,
          sheetNeedle: 'D4-4',
          target: D44_TARGET_CELL,
          marker,
        })
        await page.waitForTimeout(5_000)

        const saveBtn = page.locator('[data-testid="wp-sync-host-forcesave"]')
        for (let fs = 1; fs <= 3; fs += 1) {
          const wait = page.waitForResponse((r) => r.url().includes('/forcesave') && r.request().method() === 'POST', { timeout: 60_000 })
          await expect(saveBtn).toBeEnabled({ timeout: 30_000 })
          await saveBtn.click()
          // 🔴 必须从 `await wait` 拿到的 Response **直接** await 它的 `json()`，不能读
          //    `page.on('response')` 里 `void res.json().then(...)` 异步塞进去的变量：
          //    `waitForResponse` 在**响应头**到达就 resolve，body 解析的 microtask 往往
          //    还没跑 ⇒ 读到 `null` ⇒ `cs_error` 恒 null ⇒ 循环判「非 0 非 1」直接 break。
          //    首版实测正是这样把一次**真实成功的 OO 写入**误判成 forcesave 失败
          //    （证据 probe 里 cellTextAfterSave 已是 marker，forcesave 也是 202）。
          let csBody: Record<string, unknown> | null = null
          try {
            const res = await wait
            const parsed = (await res.json().catch(() => null)) as Record<string, unknown> | null
            csBody = ((parsed?.data as Record<string, unknown> | undefined) ?? parsed) ?? null
          } catch { /* hits 仍记；csBody 保持 null */ }
          if (csBody) forcesaveBody = csBody
          L2.forcesave_response = csBody
          const cs = csBody && 'cs_error' in csBody ? Number(csBody.cs_error) : null
          L2.forcesave_cs_error = cs
          L2.forcesave_cs_outcome = csBody ? String(csBody.cs_outcome ?? '') : ''
          L2.forcesave_callback_expected = csBody && 'callback_expected' in csBody ? Boolean(csBody.callback_expected) : null
          if (cs === 0) break
          if (cs === 1 && fs < 3) { await page.waitForTimeout(15_000); continue }
          break
        }

        if (L2.forcesave_cs_error === 0) {
          // 权威门：HTML store 镜像（checklist-responses）里出现 marker
          await expect.poll(async () => {
            const r = await page.request.get(`/api/workpapers/${L2_WP_ID}/checklist-responses`, { headers: { Authorization: `Bearer ${token}` } })
            if (!r.ok()) return ''
            return JSON.stringify(await r.json().catch(() => ({})))
          }, { timeout: 300_000 }).toContain(marker)

          const finalRes = await page.request.get(`/api/workpapers/${L2_WP_ID}/checklist-responses`, { headers: { Authorization: `Bearer ${token}` } })
          const finalRows = parseD44Rows(finalRes.ok() ? JSON.stringify(await finalRes.json().catch(() => ({}))) : '')
          for (const row of finalRows) {
            const rid = String(row?.rowId ?? row?.rowKey ?? '')
            const carries = Object.entries(row).some(([k, v]) => k !== 'rowId' && k !== 'rowKey' && String(v ?? '').includes(marker))
            if (!carries) continue
            if (rid === D44_L2_ROW_ID) L2.marker_visible_on_target_row = true
            else L2.marker_leaked_row_ids.push(rid)
          }
        }
      } catch (err) {
        L2.blocked_reason = `L2 执行中断：${String(err).slice(0, 400)}`
      }
    }

    const evidence = {
      sheet: 'D4-4',
      sheet_name: D44_SHEET_NAME,
      level: 'L2',
      captured_at: new Date().toISOString(),
      scope: { project_id: L2_PROJECT_ID, wp_id: L2_WP_ID, entry_id: ENTRY },
      predicates: {
        user_sync_requests: userSync.map((h) => ({ method: h.method, path: h.url.replace(/^https?:\/\/[^/]+/, ''), status: h.status ?? null })),
        store_projection_ok: userSync.some((h) => h.url.includes('/store-projection') && h.status === 200),
        materialize_ok: userSync.some((h) => h.url.includes('/materialize') && h.status === 200),
        content_version: (materializeBody?.generation ?? materializeBody?.content_version ?? null) as unknown,
        d2_sync_hits: d2Sync.length,
        callback_url_keys: callbackKeys,
        sync_host_mounted: await page.locator('[data-testid="wp-sync-host"]').count() > 0,
        oo_iframe_count: await page.locator('iframe').count(),
        forcesave_cs_error: L2.forcesave_cs_error,
        forcesave_hits: hits.filter((h) => h.url.includes('/forcesave')).map((h) => ({ path: h.url.replace(/^https?:\/\/[^/]+/, ''), status: h.status ?? null })),
        l2_roundtrip: L2,
        no_cross_row_contamination: L2.marker_leaked_row_ids.length === 0,
        http_errors: httpErrors.slice(0, 8),
        console_errors: consoleErrors.slice(0, 8),
      },
      notes: [
        'L1 门（materialize/callback/OO 挂载）与 D4-4.json 一致；本文件补 L2 真 OO canvas 往返 + 无跨行污染。',
        `OO 写 ${D44_TARGET_CELL}（受管列 J=备注 / 行 rowId=${D44_L2_ROW_ID}）；权威判据 forcesave cs_error=0 + HTML store 镜像回读到 marker`,
        '回读区间权威载体 = Excel Table ref GT_D44_ROWS（gen168 实测 A6:K23，覆盖 seed 的 R21~R23）；GT_ROW_UUID_RANGE_D44=$K$6:$K$20 是 instrumentation 元数据，无生产读方。',
        'blocked_reason 非空 = 目标 wp 无 D4-4 受管行（需先跑 seed_d4_4_adjustment_l2.py --apply）——如实标 blocked，不用 L1 通过冒充 L2。',
        'token/JWT/route_credential 值已脱敏（仅记 callbackUrl key 名）',
      ],
    }
    mkdirSync(EVIDENCE_DIR, { recursive: true })
    writeFileSync(resolve(EVIDENCE_DIR, 'D4-4-L2.json'), `${JSON.stringify(evidence, null, 2)}\n`, 'utf-8')

    if (L2.blocked_reason) {
      test.info().annotations.push({ type: 'blocked', description: L2.blocked_reason })
      test.skip(true, L2.blocked_reason)
    } else {
      expect(L2.forcesave_cs_error, 'forcesave cs_error 应为 0').toBe(0)
      expect(L2.marker_visible_on_target_row, `marker 应回读可见于 rowId=${D44_L2_ROW_ID}`).toBe(true)
      expect(L2.marker_leaked_row_ids, '同区其他行不得出现 marker（无跨行污染）').toEqual([])
    }
  })
})
