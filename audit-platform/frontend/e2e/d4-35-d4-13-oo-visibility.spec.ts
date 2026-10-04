/**
 * Task 18 真栈①浏览器层（续）：D4-35 动态行表 + D4-13 静态受管区在 OO canvas 上逐值可见。
 *
 * spec: d4-html-to-oo-store-contract-alignment · Task 18 · Requirements 5.2
 *
 * ═══ 为什么要单独补这两张 ═══
 *
 * `d4-1-adjudication-oo-visibility.spec.ts` 只覆盖了 D4-1 审定表（动态行 + 插行 + 合计链）。
 * D4-35 / D4-13 走的是**另外两条引擎路径**，端点层证据（evidence §六：D4-35 32 格 /
 * D4-13 两键有正文）不能替代画布层：
 *
 * * **D4-35**「其他业务收入检查表」= dict store（`D4-35-data`，行身份 `id`）→ 16 列动态行表。
 *   修复前 `D4-35-data` 既不在 `STORE_ITEM_IDS` 也不在 `STORE_ITEM_IDS_D45_FIXED`，
 *   端点装配 **0 格** ⇒ 切 OO 恒空。
 * * **D4-13**「营业收入账面金额与ERP系统核对记录」= `BindingKind.static_region`，
 *   两段自由文本锚死 A6 / A16，**不建 Excel Table、不注 UUID 列、不插行**。
 *   它是三条引擎路径里唯一的静态区，动态行那套判据一条都覆盖不到它。
 *
 * ═══ 判据取值方式 ═══
 *
 * 与 D4-1 同规矩：**不解析 HTML 列索引**，改为拿 `store-projection`（HTML 侧落库内容的投影）
 * 与 OO canvas 读回值做比对。
 *
 * * D4-35 **不硬编码首数据行** —— 扫一段行窗口，断言 projection 的每个值都能在窗口里读到，
 *   并把实际命中的行号写进证据（materialize 可能插行，锚死行号会让判据变脆且掩盖真实几何）。
 * * D4-13 **既精确读 A6/A16 断言**（静态区就该锚死），**又扫 A1:A20 作为诊断**，
 *   这样万一值落偏了，证据里能直接看出偏到哪一行，而不是只得到一句「不相等」。
 * * D4-13 **比值不比键数**：端点层「两个键都在」早就绿了，真正没被证明的是
 *   「那两段中文正文真的出现在画布上」。
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

/** D4-35：`phase5_d4_other_check_sheet.MANAGED_SHEET_D435` / `ROWS_TABLE_KEY_D435`。 */
const SHEET_D435 = '其他业务收入检查表D4-35'
const TABLE_D435 = 'other_revenue_check_rows'
/**
 * 扫描窗口：必须覆盖到「模板占位区末尾之后 + 真实行数 + 余量」。
 *
 * D4-35 模板几何（`phase5_d4_other_check_sheet`）：表头 13/14 两行，数据区占位 15..25。
 * materialize 的语义是**保留模板占位行、把真实派生行追加在占位区之后**（与 D4-1 一致 ——
 * D4-1 首数据行 8、模板 4 行占位，实测 `insert_at=12`）。所以真实行落在 26 起，
 * 窗口若只开到 25 或 26 会把第二行切掉，看起来像「漏行缺陷」，实际是判据自己短视。
 * 首版正是踩了这个坑（窗口 3..26，第 1 行命中 26、第 2 行判定 missing）。
 */
const SCAN_ROWS_D435 = { from: 3, to: 45 }
/** 挑三列做跨类型对照：文本 / 金额 / 短码（`MANAGED_FIELD_SPECS_D435` 的 C/F/B 列）。 */
const PROBE_COLS_D435 = [
  { field: 'content', column: 'C', kind: 'text' as const },
  { field: 'amount', column: 'F', kind: 'number' as const },
  { field: 'voucher_no', column: 'B', kind: 'text' as const },
]

/** D4-13：`phase5_d4_erp_check_sheet` 的 `MANAGED_SHEET_D413` / `FIXED_FIELD_SPECS_D413`。 */
const SHEET_D413 = '营业收入账面金额与ERP系统核对记录D4-13'
const TABLE_D413 = 'd413_erp_check_fixed'
const CELLS_D413: ReadonlyArray<{ field: string; ref: string }> = [
  { field: 'process', ref: 'A6' },
  { field: 'conclusion', ref: 'A16' },
]
const SCAN_COL_D413 = { column: 'A', from: 1, to: 20 }

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

/** 取整份 projection 的 `values`（真实端点，非 mock）。投影体在 `data.projection`。 */
async function fetchProjectionValues(page: Page, token: string): Promise<Record<string, unknown>> {
  const res = await page.request.get(`${SYNC_BASE}/store-projection`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(res.ok(), `store-projection 应 200，实得 ${res.status()}`).toBeTruthy()
  const body = await res.json()
  const projection = body.data?.projection ?? body.projection
  const values: Record<string, { value?: unknown }> = projection?.values ?? {}
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(values)) out[k] = v?.value
  return out
}

/**
 * 在 OO canvas 上切到指定 sheet 并按 ref 列表读文本。
 *
 * `fallbackMatch` 用于 sheet 名在簿里被改过的情况（只按 `includes` 兜一次，
 * 不做模糊猜测 —— 猜错 sheet 会让判据在错误的表上「通过」）。
 */
async function readOoCells(
  page: Page,
  { refs, wantSheet, fallbackMatch }: { refs: string[]; wantSheet: string; fallbackMatch: string },
) {
  const sheet = page.frames().find((f) => /spreadsheeteditor\/main\/index\.html/.test(f.url()))
  if (!sheet) return { ok: false as const, reason: 'OO 编辑器 iframe 未找到' }
  return sheet.evaluate(
    ({ list, want, fallback }: { list: string[]; want: string; fallback: string }) => {
      const api =
        (window as unknown as { Asc?: { editor?: Record<string, any> } }).Asc?.editor
        || (window as unknown as { editor?: Record<string, any> }).editor
      if (!api) return { ok: false as const, reason: 'no Asc.editor' }
      const out: {
        ok: true
        sheetNames: string[]
        activeSheet?: string
        matchedBy?: 'exact' | 'fallback' | 'none'
        cells: Record<string, string | null>
      } = { ok: true, sheetNames: [], cells: {} }
      try {
        const count = api.asc_getWorksheetsCount?.() ?? 0
        for (let i = 0; i < count; i += 1) {
          const ws = api.asc_getWorksheet?.(i)
          const name = (ws && typeof ws.getName === 'function' && ws.getName())
            || (typeof api.asc_getWorksheetName === 'function' && api.asc_getWorksheetName(i))
            || `idx${i}`
          out.sheetNames.push(String(name))
        }
        let idx = out.sheetNames.findIndex((nm) => nm === want)
        out.matchedBy = idx >= 0 ? 'exact' : 'none'
        if (idx < 0) {
          idx = out.sheetNames.findIndex((nm) => nm.includes(fallback))
          if (idx >= 0) out.matchedBy = 'fallback'
        }
        if (idx >= 0) {
          api.asc_showWorksheet?.(idx)
          out.activeSheet = out.sheetNames[idx]
        }
      } catch { /* 读不到 sheet 名不致命：下面按当前活动表读，activeSheet 会留空供诊断 */ }
      for (const ref of list) {
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
    { list: refs, want: wantSheet, fallback: fallbackMatch },
  )
}

/** OO 读回文本 → 数值（去千分符/货币符/空白）。 */
function toNum(text: string | null | undefined): number | null {
  if (text == null) return null
  const cleaned = String(text).replace(/[,\s¥￥]/g, '')
  if (cleaned === '' || cleaned === '-') return null
  const n = Number(cleaned)
  return Number.isFinite(n) ? n : null
}

/** 文本比对归一化：OO 会把全角括号/空白渲染得略有差异，比对时收敛掉空白。 */
function normText(text: string | null | undefined): string {
  return text == null ? '' : String(text).replace(/\s+/g, '')
}

function refsFor(column: string, from: number, to: number): string[] {
  const out: string[] = []
  for (let r = from; r <= to; r += 1) out.push(`${column}${r}`)
  return out
}

test.describe('Task 18 真栈①续：D4-35 动态行表 / D4-13 静态受管区在 OO 画布上可见', () => {
  test.setTimeout(900_000)

  test('D4-35 的行值与 D4-13 的两段正文在 OO canvas 上逐值可见', async ({ page }) => {
    const hits: Array<{ url: string; status?: number }> = []
    const consoleErrors: string[] = []
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
    const values = await fetchProjectionValues(page, token)

    // ── 1. 从真实 projection 抽期望值 ────────────────────────────────────────
    // D4-35：`other_revenue_check_rows/<rowId>/<field>`
    const rowIds435 = [...new Set(
      Object.keys(values)
        .filter((k) => k.startsWith(`${TABLE_D435}/`))
        .map((k) => k.split('/').slice(1, -1).join('/')),
    )].sort()
    const expect435 = rowIds435.map((rowId) => ({
      rowId,
      fields: PROBE_COLS_D435.map((c) => ({
        ...c, value: values[`${TABLE_D435}/${rowId}/${c.field}`],
      })).filter((f) => f.value != null && String(f.value) !== ''),
    })).filter((r) => r.fields.length > 0)

    // D4-13：两键定值
    const expect413 = CELLS_D413.map((c) => ({
      ...c, value: values[`${TABLE_D413}/${c.field}`],
    })).filter((c) => c.value != null && String(c.value) !== '')

    test.skip(
      expect435.length === 0 && expect413.length === 0,
      'D4-35 与 D4-13 在 store 里都没有值 —— 本判据无数据可比（需先跑探针种子写入）',
    )

    // ── 2. 切「在线编辑」（与 D4-1 同一个 entry，一次 materialize 覆盖整册）──
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${WP_ID}/edit`, {
      waitUntil: 'domcontentloaded',
    })
    const card = page.locator('.gt-b-arch__card').filter({ hasText: /D4-1(?!\d)/ }).first()
    await expect(card, 'D4-1 目录卡片应可见').toBeVisible({ timeout: 60_000 })
    await card.scrollIntoViewIfNeeded()
    await card.click()
    await expect(page.locator('.d4-tab-adjudication').first()).toBeVisible({ timeout: 60_000 })
    await expect(page.locator(MODE_BAR)).toBeVisible({ timeout: 30_000 })

    const ooItem = page.locator(`${MODE_BAR} .el-segmented__item`).filter({ hasText: '在线编辑' })
    await expect(ooItem, '在线编辑选项应可见').toBeVisible({ timeout: 15_000 })
    await expect(ooItem, '在线编辑不应 disabled').not.toHaveClass(/is-disabled/)
    await ooItem.click()

    try {
      await expect.poll(() => materializeOk, { timeout: 300_000 }).toBeTruthy()
    } catch {
      mkdirSync(EVIDENCE_DIR, { recursive: true })
      writeFileSync(
        resolve(EVIDENCE_DIR, 'task18-browser-d435-d413-materialize-failure.json'),
        JSON.stringify({ captured_at: new Date().toISOString(), hits, syncErrors, consoleErrors }, null, 2),
        'utf-8',
      )
      throw new Error(
        `未见 materialize 200；syncErrors=${JSON.stringify(syncErrors, null, 1).slice(0, 2500)}`,
      )
    }

    const host = page.locator('[data-testid="wp-sync-host"]')
    await expect(host).toBeVisible({ timeout: 120_000 })
    await expect(host).toHaveAttribute('data-bridge-state', 'oo_editing', { timeout: 240_000 })
    // OO 画布需要时间把 staged 文档渲染出来（大簿 46 sheet）。
    await page.waitForTimeout(35_000)

    // ── 3. 读 D4-35：三列 × 行窗口（不锚死首数据行）────────────────────────
    const refs435 = PROBE_COLS_D435.flatMap(
      (c) => refsFor(c.column, SCAN_ROWS_D435.from, SCAN_ROWS_D435.to),
    )
    const probe435 = await readOoCells(page, {
      refs: refs435, wantSheet: SHEET_D435, fallbackMatch: 'D4-35',
    })

    // ── 4. 读 D4-13：精确 A6/A16 + 扫 A 列做诊断 ─────────────────────────────
    const refs413 = [...new Set([
      ...CELLS_D413.map((c) => c.ref),
      ...refsFor(SCAN_COL_D413.column, SCAN_COL_D413.from, SCAN_COL_D413.to),
    ])]
    const probe413 = await readOoCells(page, {
      refs: refs413, wantSheet: SHEET_D413, fallbackMatch: 'D4-13',
    })

    // ── 5. 判定 ──────────────────────────────────────────────────────────────
    /** 在 sheet 的某列窗口里找一个值，返回命中行号（用于证据里落下真实几何）。 */
    function locate(
      cells: Record<string, string | null>,
      col: string,
      want: unknown,
      kind: 'text' | 'number',
    ): number | null {
      for (let r = SCAN_ROWS_D435.from; r <= SCAN_ROWS_D435.to; r += 1) {
        const got = cells[`${col}${r}`]
        if (kind === 'number') {
          const a = toNum(got)
          const b = Number(want)
          if (a != null && Number.isFinite(b) && Math.abs(a - b) <= 0.01) return r
        } else if (normText(got) !== '' && normText(got) === normText(String(want))) {
          return r
        }
      }
      return null
    }

    const found435 = probe435.ok
      ? expect435.map((row) => ({
        row_id: row.rowId,
        fields: row.fields.map((f) => ({
          field: f.field,
          column: f.column,
          want: f.value,
          hit_row: locate(probe435.cells, f.column, f.value, f.kind),
        })),
      }))
      : []
    const missing435 = found435.flatMap(
      (r) => r.fields.filter((f) => f.hit_row == null).map((f) => `${r.row_id}/${f.field}=${String(f.want)}`),
    )

    const found413 = probe413.ok
      ? expect413.map((c) => ({
        field: c.field,
        ref: c.ref,
        want: c.value,
        got: probe413.cells[c.ref] ?? null,
        equal: normText(probe413.cells[c.ref]) === normText(String(c.value)),
      }))
      : []
    const missing413 = found413.filter((c) => !c.equal)
    /** 值落偏了落到哪一行 —— 断言失败时直接从证据看出几何漂移方向。 */
    const stray413 = probe413.ok
      ? expect413.flatMap((c) => Object.entries(probe413.cells)
        .filter(([ref, got]) => ref !== c.ref && normText(got) === normText(String(c.value)))
        .map(([ref]) => ({ field: c.field, expected_ref: c.ref, actually_at: ref })))
      : []

    mkdirSync(EVIDENCE_DIR, { recursive: true })
    writeFileSync(
      resolve(EVIDENCE_DIR, 'task18-browser-d435-d413-visibility.json'),
      JSON.stringify(
        {
          captured_at: new Date().toISOString(),
          project_id: PROJECT_ID,
          wp_id: WP_ID,
          entry: ENTRY,
          materialize_200: materializeOk,
          d4_35: {
            managed_sheet: SHEET_D435,
            table_key: TABLE_D435,
            row_ids: rowIds435,
            scan_window: SCAN_ROWS_D435,
            oo_matched_by: probe435.ok ? probe435.matchedBy : null,
            oo_active_sheet: probe435.ok ? probe435.activeSheet : null,
            expected_vs_found: found435,
            missing: missing435,
          },
          d4_13: {
            managed_sheet: SHEET_D413,
            table_key: TABLE_D413,
            oo_matched_by: probe413.ok ? probe413.matchedBy : null,
            oo_active_sheet: probe413.ok ? probe413.activeSheet : null,
            expected_vs_found: found413,
            missing: missing413,
            stray_hits: stray413,
            column_scan: probe413.ok
              ? Object.fromEntries(
                Object.entries(probe413.cells).filter(([, v]) => normText(v) !== ''),
              )
              : null,
          },
          console_errors: consoleErrors.slice(0, 10),
        },
        null, 2,
      ),
      'utf-8',
    )

    expect(probe435.ok, `D4-35 读格失败：${'reason' in probe435 ? probe435.reason : ''}`).toBeTruthy()
    expect(probe413.ok, `D4-13 读格失败：${'reason' in probe413 ? probe413.reason : ''}`).toBeTruthy()
    if (!probe435.ok || !probe413.ok) return

    // 5a. 切对了表 —— 切错表上「读到空」会被误当成缺陷，必须先钉住这一步。
    expect(
      probe435.matchedBy,
      `OO 簿里找不到 D4-35 受管表；sheetNames=${JSON.stringify(probe435.sheetNames)}`,
    ).not.toBe('none')
    expect(
      probe413.matchedBy,
      `OO 簿里找不到 D4-13 受管表；sheetNames=${JSON.stringify(probe413.sheetNames)}`,
    ).not.toBe('none')

    // 5b. D4-35：决不能是空表（修复前端点 0 格，画布必然全空）。
    const nonEmpty435 = Object.values(probe435.cells).filter((v) => normText(v) !== '').length
    expect(
      nonEmpty435,
      `D4-35 扫描窗口内一个非空格都没有 —— 仍是空表。activeSheet=${probe435.activeSheet}`,
    ).toBeGreaterThan(0)

    // 5c. D4-35：projection 每个值都要在画布上读到（文本等值 / 金额容差 0.01）。
    expect(
      missing435,
      `这些 D4-35 的 HTML 侧值在 OO 画布上读不回：${missing435.join(' / ')}；`
      + `activeSheet=${probe435.activeSheet}`,
    ).toEqual([])

    // 5e. 几何：同一 store 行的各列必须落在**同一个 Excel 行**上。
    //     光比「值出现过」抓不到列错位/行错配 —— 三个值各自散在不同行也能让 5c 通过。
    const rowSkew = found435
      .map((r) => ({ row_id: r.row_id, rows: [...new Set(r.fields.map((f) => f.hit_row))] }))
      .filter((r) => r.rows.length > 1)
    expect(
      rowSkew,
      `同一 store 行的多个字段落在了不同 Excel 行（列错位/行错配）：${JSON.stringify(rowSkew)}`,
    ).toEqual([])

    // 5f. 几何：不同 store 行必须占不同 Excel 行（两行被写进同一行 = 覆盖丢数据）。
    const occupied = found435.map((r) => r.fields[0]?.hit_row).filter((n): n is number => n != null)
    expect(
      new Set(occupied).size,
      `${found435.length} 个 store 行只占了 ${new Set(occupied).size} 个 Excel 行 —— 存在互相覆盖。`
      + `命中行号=${JSON.stringify(found435.map((r) => ({ [r.row_id]: r.fields[0]?.hit_row })))}`,
    ).toBe(occupied.length)

    // 5d. D4-13：比值不比键数 —— 两段正文必须精确落在 A6 / A16（静态区不插行）。
    expect(
      missing413.map((c) => `${c.field}@${c.ref} want=${String(c.want)} got=${String(c.got)}`),
      `D4-13 静态受管区两段正文没落在锚点上；`
      + `若 stray_hits 非空说明只是几何漂移而非内容丢失：${JSON.stringify(stray413)}`,
    ).toEqual([])
  })
})
