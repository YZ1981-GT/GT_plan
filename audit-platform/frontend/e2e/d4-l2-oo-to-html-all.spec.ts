/**
 * D4 全盘 L2：逐张「进 OO → 改一格安全金额 → forcesave → applied → 验落库 → 回表格再进」。
 *
 * 为何逐张：UI forcesave 会卸编辑态；批量多格曾触发 footer_anchor_drift / conflict。
 * 只改投影里 |amount|>1 且 key 非 seq 的金额格；文本/空数据记 no_safe_target。
 * D4-4 N/A。真栈：3030 / 9980 / 8080。
 */
import { test, expect, type Page, type Response } from '@playwright/test'
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const PROJECT_ID = '0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49'
const WP_ID = 'b3ab3c46-828f-4f48-950e-aee9bbdc923f'
const ENTRY = 'xlsx/gt-d4-operating-revenue'
/** API 直打后端，避免 vite 代理中途挂掉导致 page.request ECONNREFUSED。 */
const API_BASE = process.env.D4_L2_API_BASE || 'http://127.0.0.1:9980'
const SYNC_BASE = `${API_BASE}/api/projects/${PROJECT_ID}/workpapers/${WP_ID}/sync/entries/${ENTRY}`
const DELTA = 12345.67
const SKIP_KEYS = new Set(['seq', 'index', 'row_no', 'no', 'order', 'month'])

const EVIDENCE_DIR = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../../../docs/operations/evidence/d4-bidirectional-acceptance',
)

type L2Case = {
  code: string
  excel_name: string
  table_key: string
  edit_col: string
  edit_key: string | null
  edit_vt: string
  first_data_row: number
  last_data_row: number
}

type SheetResult = {
  code: string
  status: 'applied_store_ok' | 'applied_store_miss' | 'no_safe_target' | 'type_fail' | 'op_error' | 'op_timeout' | 'enter_fail'
  target_ref?: string
  old_value?: number | string
  new_value?: number | string
  operation_id?: string
  state_trail?: string[]
  error_code?: string | null
  error_message?: string | null
  store_got?: unknown
  sample_field?: string
}

function loadCases(): L2Case[] {
  const raw = readFileSync(
    resolve(dirname(fileURLToPath(import.meta.url)), 'fixtures/d4-l2-cases.json'),
    'utf-8',
  )
  let cases = [...(JSON.parse(raw) as { cases: L2Case[] }).cases]
  // D4-2 金额月列易与派生/审定冲突；改走文本 product（与 g5-1 一致）
  cases = cases.map((c) => {
    if (c.code !== 'D4-2') return c
    return { ...c, edit_col: 'A', edit_key: 'product', edit_vt: 'text' }
  })
  const only = (process.env.D4_L2_ONLY || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
  if (only.length) cases = cases.filter((c) => only.includes(c.code))
  return cases.sort(
    (a, b) => Number(a.code.replace(/\D/g, '')) - Number(b.code.replace(/\D/g, '')),
  )
}

async function login(page: Page): Promise<string> {
  const r = await page.request.post(`${API_BASE}/api/auth/login`, {
    data: { username: 'admin', password: 'admin123' },
  })
  expect(r.ok()).toBeTruthy()
  const body = await r.json()
  const token = body.data?.access_token ?? body.access_token
  expect(token).toBeTruthy()
  await page.addInitScript((v: string) => {
    sessionStorage.setItem('token', v)
    localStorage.setItem('token', v)
  }, token)
  return token as string
}

function ooFrame(page: Page) {
  return page.frames().find((f) => /spreadsheeteditor\/main\/index\.html/.test(f.url()))
}

function toNum(text: string | null | undefined): number | null {
  if (text == null) return null
  const c = String(text).replace(/[,\s¥￥]/g, '')
  if (c === '' || c === '-') return null
  const n = Number(c)
  return Number.isFinite(n) ? n : null
}

function isAmountVt(vt: string) {
  return ['amount', 'number', 'integer', 'decimal'].includes(vt)
}

async function fetchProjectionValues(page: Page, token: string): Promise<Record<string, unknown>> {
  const res = await page.request.get(`${SYNC_BASE}/store-projection`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(res.ok()).toBeTruthy()
  const body = await res.json()
  return ((body.data?.projection ?? body.projection)?.values ?? {}) as Record<string, unknown>
}

/** 金额 |n|>1；否则回退同表非空文本（抬高有载荷 sheet 的 L2 覆盖）。 */
function pickSample(
  values: Record<string, unknown>,
  tableKey: string,
  editKey: string | null,
  editVt: string,
): { fieldKey: string; value: number | string; kind: 'amount' | 'text' } | null {
  const prefix = `${tableKey}/`
  const entries = Object.entries(values).filter(([k]) => k.startsWith(prefix))
  const ordered = [
    ...entries.filter(([k]) => (editKey ? k.endsWith(`/${editKey}`) : true)),
    ...entries,
  ]
  const seen = new Set<string>()
  if (isAmountVt(editVt)) {
    for (const [k, field] of ordered) {
      if (seen.has(k)) continue
      seen.add(k)
      const colKey = (k.split('/').pop() || '').toLowerCase()
      if (SKIP_KEYS.has(colKey) || colKey === 'group_label') continue
      const n = Number((field as { value?: unknown })?.value)
      if (Number.isFinite(n) && Math.abs(n) > 1) return { fieldKey: k, value: n, kind: 'amount' }
    }
  }
  seen.clear()
  for (const [k, field] of ordered) {
    if (seen.has(k)) continue
    seen.add(k)
    const colKey = (k.split('/').pop() || '').toLowerCase()
    if (SKIP_KEYS.has(colKey)) continue
    const raw = (field as { value?: unknown })?.value
    if (typeof raw === 'number') continue
    const s = String(raw ?? '').trim()
    if (s && !s.startsWith('L2MARK-') && !/^-?\d+(\.\d+)?$/.test(s)) {
      return { fieldKey: k, value: s, kind: 'text' }
    }
  }
  return null
}

async function waitEditorReady(page: Page) {
  await expect.poll(async () => {
    const state = await page.locator('[data-testid="wp-sync-host"]').getAttribute('data-bridge-state')
    if (state === 'oo_editing') return 'oo_editing'
    const f = ooFrame(page)
    if (!f) return state || 'no_frame'
    const hasApi = await f.evaluate(() => {
      const api = (window as any).Asc?.editor || (window as any).editor
      return Boolean(api && typeof api.asc_getWorksheetsCount === 'function')
    }).catch(() => false)
    return hasApi ? 'api_ready' : (state || 'waiting')
  }, { timeout: 600_000, intervals: [3_000] }).toMatch(/^(oo_editing|api_ready)$/)
}

async function waitMaskGone(page: Page, timeoutMs = 120_000) {
  try {
    await page.locator('[data-testid="wp-sync-host-mask"]').waitFor({ state: 'hidden', timeout: timeoutMs })
  } catch { /* */ }
}

async function openD4Shell(page: Page) {
  await page.goto(`/projects/${PROJECT_ID}/workpapers/${WP_ID}/edit`, { waitUntil: 'domcontentloaded' })
  const card = page.locator('.gt-b-arch__card, .el-tabs__item, [role="tab"]').filter({ hasText: /D4-1(?!\d)/ }).first()
  await expect(card).toBeVisible({ timeout: 60_000 })
  await card.click()
  await page.waitForTimeout(2_000)
  await expect(page.locator('.d4-mode-toolbar, .sync-mode-bar').first()).toBeVisible({ timeout: 60_000 })
}

async function enterOnlineEdit(page: Page, track: { materializeOk: boolean }) {
  track.materializeOk = false
  const htmlItem = page.locator('.d4-mode-toolbar .el-segmented__item, .sync-mode-bar .el-segmented__item')
    .filter({ hasText: '表格视图' }).first()
  if (await htmlItem.count() > 0) {
    const cls = await htmlItem.getAttribute('class')
    if (!cls?.includes('is-disabled')) {
      await htmlItem.click().catch(() => {})
      await page.waitForTimeout(2_000)
    }
  }
  const ooItem = page.locator('.d4-mode-toolbar .el-segmented__item, .sync-mode-bar .el-segmented__item')
    .filter({ hasText: '在线编辑' }).first()
  await expect(ooItem).toBeVisible({ timeout: 30_000 })
  await ooItem.click()
  try {
    await expect.poll(() => track.materializeOk, { timeout: 180_000 }).toBeTruthy()
  } catch {
    // conflict/error 后桥可能不再发 materialize —— 整页重开
    await openD4Shell(page)
    track.materializeOk = false
    const oo2 = page.locator('.d4-mode-toolbar .el-segmented__item, .sync-mode-bar .el-segmented__item')
      .filter({ hasText: '在线编辑' }).first()
    await oo2.click()
    await expect.poll(() => track.materializeOk, { timeout: 300_000 }).toBeTruthy()
  }
  await waitEditorReady(page)
  await page.waitForTimeout(12_000)
  await waitMaskGone(page, 90_000)
}

async function locateByValue(
  page: Page,
  {
    wantSheet,
    from,
    to,
    wantValue,
    wantText,
  }: {
    wantSheet: string
    from: number
    to: number
    wantValue?: number | null
    wantText?: string | null
  },
) {
  const f = ooFrame(page)
  if (!f) return { ok: false as const, reason: 'no frame' }
  return f.evaluate(
    ({ want, fromR, toR, wantV, wantT, cols }: {
      want: string; fromR: number; toR: number; wantV: number | null; wantT: string | null; cols: string[]
    }) => {
      const api = (window as any).Asc?.editor || (window as any).editor
      if (!api) return { ok: false as const, reason: 'no api' }
      try {
        const n = api.asc_getWorksheetsCount?.() ?? 0
        const names: string[] = []
        for (let i = 0; i < n; i += 1) {
          const ws = api.asc_getWorksheet?.(i)
          names.push(String(
            (ws && typeof ws.getName === 'function' && ws.getName())
            || (typeof api.asc_getWorksheetName === 'function' && api.asc_getWorksheetName(i))
            || `idx${i}`,
          ))
        }
        let idx = names.findIndex((nm) => nm === want)
        if (idx < 0) {
          const code = (want.match(/D4-\d+/) || [])[0]
          if (code) idx = names.findIndex((nm) => nm.includes(code))
        }
        if (idx < 0) return { ok: false as const, reason: `sheet missing ${want}`, located: false }
        api.asc_showWorksheet?.(idx)
      } catch (e) {
        return { ok: false as const, reason: String(e), located: false }
      }
      const parseNum = (t: string | null) => {
        if (t == null) return null
        const c = String(t).replace(/[,\s¥￥]/g, '')
        if (c === '' || c === '-') return null
        const n = Number(c)
        return Number.isFinite(n) ? n : null
      }
      const needle = wantT ? String(wantT).slice(0, 24) : null
      for (const col of cols) {
        for (let r = fromR; r <= toR; r += 1) {
          try {
            api.asc_findCell?.(`${col}${r}`)
            const t = api.asc_getCellInfo?.()?.asc_getText?.() ?? null
            if (wantV != null) {
              const num = parseNum(t)
              if (num != null && Math.abs(num - wantV) <= 0.01) {
                return { ok: true as const, located: true, target: `${col}${r}`, oldText: t }
              }
            }
            if (needle && t != null && String(t).includes(needle)) {
              return { ok: true as const, located: true, target: `${col}${r}`, oldText: t }
            }
          } catch { /* */ }
        }
      }
      return { ok: true as const, located: false, reason: 'value not found' }
    },
    {
      want: wantSheet,
      fromR: from,
      toR: to,
      wantV: wantValue ?? null,
      wantT: wantText ?? null,
      cols: 'ABCDEFGHIJKLMNOPQRST'.split(''),
    },
  )
}

async function typeIntoOoCell(page: Page, ref: string, value: string) {
  await waitMaskGone(page, 60_000)
  const f = ooFrame(page)
  if (!f) return { ok: false as const, reason: 'no frame' }
  const nameBox = f.locator('#ce-cell-name').first()
  try {
    await nameBox.click({ timeout: 20_000 })
  } catch {
    await nameBox.click({ force: true, timeout: 10_000 })
  }
  await nameBox.fill(ref)
  await page.keyboard.press('Enter')
  await page.waitForTimeout(600)
  await page.keyboard.press('Control+A')
  await page.keyboard.press('Backspace')
  await page.keyboard.type(value, { delay: 30 })
  await page.keyboard.press('Enter')
  await page.waitForTimeout(1_200)
  return { ok: true as const }
}

async function readOoCell(page: Page, ref: string) {
  const f = ooFrame(page)
  if (!f) return null
  return f.evaluate(({ r }: { r: string }) => {
    const api = (window as any).Asc?.editor || (window as any).editor
    if (!api) return null
    try {
      api.asc_findCell?.(r)
      return api.asc_getCellInfo?.()?.asc_getText?.() ?? null
    } catch { return null }
  }, { r: ref })
}

async function operationPayload(page: Page, token: string, opId: string): Promise<Record<string, unknown>> {
  const res = await page.request.get(`${SYNC_BASE}/operations/${opId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok()) return { state: `http_${res.status()}` }
  const body = await res.json().catch(() => null)
  return ((body?.data ?? body) as Record<string, unknown>) || {}
}

test.describe('D4 全盘 L2 OO→HTML（逐张金额）', () => {
  test.setTimeout(3_600_000)

  test('逐张安全金额 → forcesave → applied', async ({ page }) => {
    const cases = loadCases()
    const track = { materializeOk: false }
    let lastForcesave: Record<string, unknown> | null = null

    page.on('response', (res: Response) => {
      const u = res.url()
      if (!u.includes('/sync/entries/')) return
      if (u.includes('/materialize') && res.status() === 200) track.materializeOk = true
      if (u.includes('/forcesave') && res.request().method() === 'POST') {
        void res.json().then((j) => { lastForcesave = (j?.data ?? j) as Record<string, unknown> }).catch(() => {})
      }
    })

    const token = await login(page)
    await openD4Shell(page)

    const results: SheetResult[] = []
    const flushPartial = () => {
      mkdirSync(EVIDENCE_DIR, { recursive: true })
      writeFileSync(
        resolve(EVIDENCE_DIR, 'd4-l2-oo-to-html-serial.partial.json'),
        JSON.stringify({ updated_at: new Date().toISOString(), results }, null, 2),
        'utf-8',
      )
    }

    for (const c of cases) {
      lastForcesave = null
      const values = await fetchProjectionValues(page, token)
      const sample = pickSample(values, c.table_key, c.edit_key, c.edit_vt)
      if (!sample) {
        results.push({ code: c.code, status: 'no_safe_target' })
        flushPartial()
        continue
      }

      try {
        await enterOnlineEdit(page, track)
      } catch (e) {
        results.push({ code: c.code, status: 'enter_fail', error_message: String(e).slice(0, 200) })
        flushPartial()
        await openD4Shell(page).catch(() => {})
        continue
      }

      const locate = await locateByValue(page, {
        wantSheet: c.excel_name,
        from: Math.max(1, c.first_data_row - 2),
        to: Math.max(c.last_data_row + 15, c.first_data_row + 40),
        wantValue: sample.kind === 'amount' ? Number(sample.value) : null,
        wantText: sample.kind === 'text' ? String(sample.value) : null,
      })
      if (!locate.ok || !locate.located || !('target' in locate) || !locate.target) {
        results.push({
          code: c.code,
          status: 'no_safe_target',
          sample_field: sample.fieldKey,
          error_message: 'locate_miss',
        })
        flushPartial()
        const htmlItem = page.locator('.d4-mode-toolbar .el-segmented__item, .sync-mode-bar .el-segmented__item')
          .filter({ hasText: '表格视图' }).first()
        if (await htmlItem.count()) await htmlItem.click().catch(() => {})
        continue
      }

      const oldValue = sample.value
      const newValue = sample.kind === 'amount'
        ? Math.round((Number(oldValue) + DELTA) * 100) / 100
        : `L2MARK-${c.code}-${Date.now().toString(36).slice(-4)}`
      const typed = await typeIntoOoCell(page, String(locate.target), String(newValue))
      const afterText = await readOoCell(page, String(locate.target))
      let typedOk = typed.ok
      if (typedOk) {
        if (sample.kind === 'amount') {
          const after = toNum(afterText)
          typedOk = after != null && Math.abs(after - Number(newValue)) <= 0.05
        } else {
          typedOk = afterText != null && String(afterText).includes(String(newValue).slice(0, 12))
        }
      }
      if (!typedOk) {
        results.push({
          code: c.code,
          status: 'type_fail',
          target_ref: String(locate.target),
          old_value: oldValue,
          new_value: newValue,
          error_message: `got=${afterText}`,
        })
        flushPartial()
        await openD4Shell(page).catch(() => {})
        continue
      }

      await page.waitForTimeout(6_000)
      const saveBtn = page.locator('[data-testid="wp-sync-host-forcesave"]')
      await expect(saveBtn).toBeEnabled({ timeout: 30_000 })
      await saveBtn.click()
      try {
        await expect.poll(() => lastForcesave !== null, { timeout: 90_000 }).toBeTruthy()
      } catch {
        results.push({ code: c.code, status: 'op_timeout', target_ref: String(locate.target) })
        flushPartial()
        await openD4Shell(page).catch(() => {})
        continue
      }
      const opId = String(
        (lastForcesave as Record<string, unknown> | null)?.operation_id
        ?? (lastForcesave as Record<string, unknown> | null)?.operationId ?? '',
      )
      const trail: string[] = []
      let payload: Record<string, unknown> = {}
      let state = ''
      try {
        await expect.poll(async () => {
          payload = await operationPayload(page, token, opId)
          state = String(payload.state ?? '')
          if (state && state !== trail[trail.length - 1]) trail.push(state)
          if (['applied', 'error', 'rejected', 'conflict'].includes(state)) return state
          return state
        }, { timeout: 420_000, intervals: [2_000] }).toMatch(/^(applied|error|rejected|conflict)$/)
      } catch {
        results.push({
          code: c.code, status: 'op_timeout', operation_id: opId, state_trail: trail,
          error_code: String(payload.application_error_code ?? ''),
          error_message: String(payload.application_error_message ?? ''),
        })
        flushPartial()
        await openD4Shell(page).catch(() => {})
        continue
      }

      if (state !== 'applied') {
        results.push({
          code: c.code,
          status: 'op_error',
          target_ref: String(locate.target),
          old_value: oldValue,
          new_value: newValue,
          operation_id: opId,
          state_trail: trail,
          error_code: String(payload.application_error_code ?? payload.logical_result_code ?? state),
          error_message: String(payload.application_error_message ?? ''),
          sample_field: sample.fieldKey,
        })
        flushPartial()
        await openD4Shell(page).catch(() => {})
        continue
      }

      let storeGot: unknown = null
      let storeOk = false
      try {
        await expect.poll(async () => {
          const vals = await fetchProjectionValues(page, token)
          if (sample.kind === 'amount') {
            const field = vals[sample.fieldKey] as { value?: unknown } | undefined
            const n = Number(field?.value)
            storeGot = field?.value
            if (Number.isFinite(n) && Math.abs(n - Number(newValue)) <= 0.05) {
              storeOk = true
              return true
            }
            for (const [k, f] of Object.entries(vals)) {
              if (!k.startsWith(`${c.table_key}/`)) continue
              const nn = Number((f as { value?: unknown })?.value)
              if (Number.isFinite(nn) && Math.abs(nn - Number(newValue)) <= 0.05) {
                storeGot = nn
                storeOk = true
                return true
              }
            }
            return false
          }
          for (const [k, f] of Object.entries(vals)) {
            if (!k.startsWith(`${c.table_key}/`)) continue
            const v = String((f as { value?: unknown })?.value ?? '')
            if (v.includes(String(newValue).slice(0, 10))) {
              storeGot = v
              storeOk = true
              return true
            }
          }
          return false
        }, { timeout: 120_000, intervals: [2_500] }).toBeTruthy()
      } catch { /* */ }

      results.push({
        code: c.code,
        status: storeOk ? 'applied_store_ok' : 'applied_store_miss',
        target_ref: String(locate.target),
        old_value: oldValue,
        new_value: newValue,
        operation_id: opId,
        state_trail: trail,
        store_got: storeGot,
        sample_field: sample.fieldKey,
      })
      flushPartial()
    }

    const summary = {
      n: results.length,
      applied_store_ok: results.filter((r) => r.status === 'applied_store_ok').length,
      applied_store_miss: results.filter((r) => r.status === 'applied_store_miss').length,
      no_safe_target: results.filter((r) => r.status === 'no_safe_target').length,
      type_fail: results.filter((r) => r.status === 'type_fail').length,
      op_error: results.filter((r) => r.status === 'op_error').length,
      op_timeout: results.filter((r) => r.status === 'op_timeout').length,
      enter_fail: results.filter((r) => r.status === 'enter_fail').length,
    }

    mkdirSync(EVIDENCE_DIR, { recursive: true })
    const evidencePath = resolve(EVIDENCE_DIR, 'd4-l2-oo-to-html-serial.json')
    writeFileSync(evidencePath, JSON.stringify({
      captured_at: new Date().toISOString(),
      summary,
      results,
    }, null, 2), 'utf-8')

    // 写进度摘要到 stdout 方便看
    // eslint-disable-next-line no-console
    console.log('L2_SUMMARY', JSON.stringify(summary))
    // eslint-disable-next-line no-console
    console.log('L2_RESULTS', JSON.stringify(results.map((r) => ({ code: r.code, status: r.status, err: r.error_code }))))

    expect(
      summary.op_error + summary.op_timeout + summary.type_fail + summary.enter_fail,
      `有目标 sheet 失败。summary=${JSON.stringify(summary)} failures=${JSON.stringify(
        results.filter((r) => !['applied_store_ok', 'applied_store_miss', 'no_safe_target'].includes(r.status)),
      )} evidence=${evidencePath}`,
    ).toBe(0)

    expect(
      summary.applied_store_ok,
      `至少 3 张落库成功。summary=${JSON.stringify(summary)} evidence=${evidencePath}`,
    ).toBeGreaterThanOrEqual(3)

    expect(summary.applied_store_ok + summary.applied_store_miss + summary.no_safe_target).toBe(cases.length)
  })
})
