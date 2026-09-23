/**
 * Task 18 真栈①浏览器层：D4-1 审定表「表格视图 → 在线编辑」，OO 里必须看得见 HTML 的行与金额。
 *
 * spec: d4-html-to-oo-store-contract-alignment · Task 18 · Requirements 5.2 / 5.3
 *
 * ═══ 这条测的就是用户报障本身 ═══
 *
 * 报障原文：「表格视图下是有数据的，但点击到在线编辑、切换到 OO 后，里面是空的。」
 * 真栈形态：HTML 主营段 7 行有真实金额，OO 里 R8:R11 全空、小计 0。
 * 端点层证据已有（`docs/operations/evidence/d4-store-contract-alignment/` §六：主营 21 格 /
 * 其他 16 格 / D4-35 32 格 / D4-13 两键有正文）。本文件补的是**浏览器 + OO canvas** 那一段 ——
 * projection 对了不等于 OO 画布上看得见（materialize 要插行、要写进受管列）。
 *
 * 判据取值方式：**不解析 HTML 表格的列索引**（列序是 UI 细节，会随排版变）。改为
 *   1. 用同一会话的 API 拿 `store-projection` 的两区受管值（它就是 HTML 侧落库内容的投影）；
 *   2. HTML 侧断言这些行的 `label` 在页面上可见（行确实在表格里）；
 *   3. OO 侧断言主营段数据区各行的「本期未审数」列读回的数值集合 ⊇ projection 的那批金额。
 * 三者一致才叫「逐行对齐」。
 *
 * ⚠️ 必须 `--workers=1`（OnlyOffice 8080 单实例，并发 contention 会假失败）。
 */
import { test, expect, type Page, type Request, type Response } from '@playwright/test'
import { writeFileSync, mkdirSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const PROJECT_ID = '0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49'
const WP_ID = 'b3ab3c46-828f-4f48-950e-aee9bbdc923f'
const ENTRY = 'xlsx/gt-d4-operating-revenue'
const SYNC_BASE = `/api/projects/${PROJECT_ID}/workpapers/${WP_ID}/sync/entries/${ENTRY}`
const MANAGED_SHEET_NAME = '营业收入审定表D4-1'
/** 主营段：标题行 7、数据区自 8 起（模板 4 行占位，派生行多于 4 时 materialize 插行）。 */
const FIRST_DATA_ROW_MAIN = 8
/** 「本期未审数」列（`MANAGED_FIELD_SPECS` 里 current_unadjusted 的列标）。 */
const COL_CURRENT_UNADJUSTED = 'B'
const MAIN_TABLE_KEY = 'adjudication_main_rows'
/** D4-1 审定表的模式切换条（`D4TabAdjudication.vue` 用 `.sync-mode-bar`，非 D4-2 的 `.d4-mode-toolbar`）。 */
const MODE_BAR = '.d4-tab-adjudication .sync-mode-bar'

const EVIDENCE_DIR = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../../../docs/operations/evidence/d4-store-contract-alignment',
)

async function login(page: Page): Promise<string> {
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

/** 主营段受管值：`{ rowId: { label, current_unadjusted } }`（取自真实端点，非 mock）。 */
async function fetchMainRegion(page: Page, token: string) {
  const res = await page.request.get(`${SYNC_BASE}/store-projection`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(res.ok(), `store-projection 应 200，实得 ${res.status()}`).toBeTruthy()
  const body = await res.json()
  // 🔴 投影体在 data.projection，不在 data 顶层（早先探针在这里读错层级、误判成 0 格）。
  const projection = body.data?.projection ?? body.projection
  const values: Record<string, { value: unknown }> = projection?.values ?? {}
  const rows: Record<string, { label?: string; amount?: number }> = {}
  for (const [key, field] of Object.entries(values)) {
    if (!key.startsWith(`${MAIN_TABLE_KEY}/`)) continue
    const parts = key.split('/')
    const rowId = parts.slice(1, -1).join('/')
    const col = parts[parts.length - 1]
    rows[rowId] ??= {}
    if (col === 'label') rows[rowId].label = String(field.value ?? '')
    if (col === 'current_unadjusted' && field.value != null) {
      rows[rowId].amount = Number(field.value)
    }
  }
  return rows
}

async function openD4Adjudication(page: Page): Promise<void> {
  await page.goto(`/projects/${PROJECT_ID}/workpapers/${WP_ID}/edit`, {
    waitUntil: 'domcontentloaded',
  })
  const card = page
    .locator('.gt-b-arch__card')
    .filter({ hasText: /D4-1(?!\d)/ })
    .first()
  await expect(card, 'D4-1 目录卡片应可见').toBeVisible({ timeout: 60_000 })
  await card.scrollIntoViewIfNeeded()
  await card.click()
  await expect(page.locator('.d4-tab-adjudication').first()).toBeVisible({ timeout: 60_000 })
  // 🔴 D4-1 的模式切换条 class 是 `.sync-mode-bar`（D4TabAdjudication.vue），
  //    **不是** D4-2 那套 `.d4-mode-toolbar` —— 照抄 g5-1-d4 范式会找不到元素。
  await expect(page.locator(`${MODE_BAR}`)).toBeVisible({ timeout: 30_000 })
}

/** 在 OO canvas 上读主营段数据区若干行的指定列。 */
async function readOoColumn(
  page: Page,
  { column, firstRow, rowCount, wantSheet }:
    { column: string; firstRow: number; rowCount: number; wantSheet: string },
) {
  const sheet = page.frames().find((f) => /spreadsheeteditor\/main\/index\.html/.test(f.url()))
  if (!sheet) return { ok: false as const, reason: 'OO 编辑器 iframe 未找到' }
  return sheet.evaluate(
    ({ col, r0, n, want }: { col: string; r0: number; n: number; want: string }) => {
      const api =
        (window as unknown as { Asc?: { editor?: Record<string, any> } }).Asc?.editor
        || (window as unknown as { editor?: Record<string, any> }).editor
      if (!api) return { ok: false as const, reason: 'no Asc.editor' }
      const out: { ok: true; sheetNames: string[]; activeSheet?: string; cells: Record<string, string | null> } =
        { ok: true, sheetNames: [], cells: {} }
      try {
        const count = api.asc_getWorksheetsCount?.() ?? 0
        for (let i = 0; i < count; i += 1) {
          const ws = api.asc_getWorksheet?.(i)
          const name = (ws && typeof ws.getName === 'function' && ws.getName())
            || (typeof api.asc_getWorksheetName === 'function' && api.asc_getWorksheetName(i))
            || `idx${i}`
          out.sheetNames.push(String(name))
        }
        let want_i = out.sheetNames.findIndex((nm) => nm === want)
        if (want_i < 0) want_i = out.sheetNames.findIndex((nm) => nm.includes('D4-1'))
        if (want_i >= 0) {
          api.asc_showWorksheet?.(want_i)
          out.activeSheet = out.sheetNames[want_i]
        }
      } catch { /* 读不到 sheet 名不致命，下面按当前活动表读 */ }
      for (let r = r0; r < r0 + n; r += 1) {
        const ref = `${col}${r}`
        try {
          api.asc_findCell?.(ref)
          const info = api.asc_getCellInfo?.()
          out.cells[ref] = info && typeof info.asc_getText === 'function' ? info.asc_getText() : null
        } catch {
          out.cells[ref] = null
        }
      }
      return out
    },
    { col: column, r0: firstRow, n: rowCount, want: wantSheet },
  )
}

/** OO 读回的单元格文本 → 数值（去千分符/货币符/空白）。 */
function toNum(text: string | null): number | null {
  if (text == null) return null
  const cleaned = text.replace(/[,\s¥￥]/g, '')
  if (cleaned === '' || cleaned === '-') return null
  const n = Number(cleaned)
  return Number.isFinite(n) ? n : null
}


test.describe('Task 18 真栈①：D4-1 切在线编辑后 OO 里看得见 HTML 的行与金额', () => {
  test.setTimeout(600_000)

  test('D4-1 主营段派生行金额在 OO canvas 上逐值可见（不是空表）', async ({ page }) => {
    const hits: Array<{ url: string; status?: number }> = []
    const consoleErrors: string[] = []
    /** 同步类端点的 4xx/5xx 响应体 —— 没有它，materialize 500 只能看到一个裸状态码。 */
    const syncErrors: Array<{ path: string; status: number; body: string }> = []
    let materializeOk = false

    page.on('request', (req: Request) => {
      if (req.url().includes('/sync/entries/')) hits.push({ url: req.url() })
    })
    page.on('response', (res: Response) => {
      const url = res.url()
      if (!url.includes('/sync/entries/')) return
      const row = hits.find((h) => h.url === url && h.status == null)
      if (row) row.status = res.status()
      if (url.includes('/materialize') && res.status() === 200) materializeOk = true
      if (res.status() >= 400) {
        void res.text().then((text) => {
          syncErrors.push({
            path: url.replace(/^https?:\/\/[^/]+/, ''),
            status: res.status(),
            body: text.slice(0, 1500),
          })
        }).catch(() => { /* 读不到体不致命 */ })
      }
    })
    page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()) })

    const token = await login(page)

    // ── 1. 取 HTML 侧落库内容的投影（真端点）──────────────────────────────────
    const mainRegion = await fetchMainRegion(page, token)
    const derived = Object.entries(mainRegion).filter(
      ([rowId, v]) => rowId.startsWith('xsheet-main-') && v.amount != null && v.amount !== 0,
    )
    test.skip(
      derived.length === 0,
      'D4-1 主营段无非零派生行 —— 该底稿 D4-2 上游为空，本判据无数据可比（不是缺陷）',
    )
    const expectedAmounts = derived.map(([, v]) => Number(v.amount))
    const expectedLabels = derived.map(([, v]) => String(v.label ?? ''))

    // ── 2. HTML 侧：这些行确实在表格里 ───────────────────────────────────────
    await openD4Adjudication(page)
    const mainTable = page.locator('.d4-tab-adjudication .el-table').first()
    await expect(mainTable, '主营段表格应可见').toBeVisible({ timeout: 60_000 })
    const htmlText = await mainTable.innerText()
    const labelsMissingInHtml = expectedLabels.filter((l) => l && !htmlText.includes(l))
    expect(
      labelsMissingInHtml,
      `projection 有这些行但 HTML 表格里看不到（两侧行集不一致）：${labelsMissingInHtml.join(' / ')}`,
    ).toEqual([])

    // ── 3. 切「在线编辑」→ 等 materialize 200 ────────────────────────────────
    const ooItem = page.locator(`${MODE_BAR} .el-segmented__item`).filter({ hasText: '在线编辑' })
    await expect(ooItem, '在线编辑选项应可见').toBeVisible({ timeout: 15_000 })
    await expect(ooItem, '在线编辑不应 disabled').not.toHaveClass(/is-disabled/)
    await ooItem.click()

    try {
      await expect.poll(() => materializeOk, { timeout: 240_000 }).toBeTruthy()
    } catch {
      mkdirSync(EVIDENCE_DIR, { recursive: true })
      writeFileSync(
        resolve(EVIDENCE_DIR, 'task18-browser-materialize-failure.json'),
        JSON.stringify({ captured_at: new Date().toISOString(), hits, syncErrors, consoleErrors }, null, 2),
        'utf-8',
      )
      throw new Error(
        `未见 materialize 200；syncErrors=${JSON.stringify(syncErrors, null, 1).slice(0, 2500)}`,
      )
    }
    expect(
      hits.some((h) => h.url.includes('/store-projection')),
      '切 OO 应打 store-projection',
    ).toBeTruthy()

    await expect(page.locator('[data-testid="wp-sync-host"]')).toBeVisible({ timeout: 120_000 })
    await expect(page.locator('[data-testid="wp-sync-host"]')).toHaveAttribute(
      'data-bridge-state', 'oo_editing', { timeout: 180_000 },
    )
    // OO 画布需要时间把 staged 文档渲染出来（大簿 46 sheet）。
    await page.waitForTimeout(35_000)

    // ── 4. OO 侧：主营段数据区各行「本期未审数」读回 ⊇ projection 的金额 ─────
    const probe = await readOoColumn(page, {
      column: COL_CURRENT_UNADJUSTED,
      firstRow: FIRST_DATA_ROW_MAIN,
      // 数据区行数上限 = 派生行数 + 模板 4 行占位 + 2 行余量（materialize 会插行）。
      rowCount: derived.length + 6,
      wantSheet: MANAGED_SHEET_NAME,
    })

    mkdirSync(EVIDENCE_DIR, { recursive: true })
    writeFileSync(
      resolve(EVIDENCE_DIR, 'task18-browser-oo-visibility.json'),
      JSON.stringify(
        {
          captured_at: new Date().toISOString(),
          project_id: PROJECT_ID,
          wp_id: WP_ID,
          entry: ENTRY,
          managed_sheet: MANAGED_SHEET_NAME,
          derived_rows_from_projection: derived.map(([rowId, v]) => ({
            row_id: rowId, label: v.label, current_unadjusted: v.amount,
          })),
          html_labels_all_visible: labelsMissingInHtml.length === 0,
          materialize_200: materializeOk,
          oo_probe: probe,
          console_errors: consoleErrors.slice(0, 10),
        },
        null, 2,
      ),
      'utf-8',
    )

    expect(probe.ok, `OO canvas 读格失败：${'reason' in probe ? probe.reason : ''}`).toBeTruthy()
    if (!probe.ok) return
    const ooNums = Object.values(probe.cells).map(toNum).filter((n): n is number => n != null)

    // 4a. 决不能是空表（这是报障的原始形态）。
    expect(
      ooNums.length,
      `OO 主营段数据区一个数都读不到 —— 仍是空表（报障形态未修好）。cells=${JSON.stringify(probe.cells)}`,
    ).toBeGreaterThan(0)

    // 4b. 逐值对齐：projection 的每个金额都要能在 OO 读回的数里找到（容差 0.01）。
    const missing = expectedAmounts.filter(
      (want) => !ooNums.some((got) => Math.abs(got - want) <= 0.01),
    )
    expect(
      missing,
      `这些 HTML 侧金额在 OO 主营段读不回：${missing.join(' / ')}；`
      + `OO 读到=${JSON.stringify(ooNums)}；activeSheet=${'activeSheet' in probe ? probe.activeSheet : '?'}`,
    ).toEqual([])
  })
})
