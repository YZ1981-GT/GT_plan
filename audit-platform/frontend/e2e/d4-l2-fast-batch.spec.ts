/**
 * D4 L2 快速批：进一次 OO → 改多张安全格 → 一次 forcesave → applied。
 * 避免逐张 rematerialize（单张 3–7 分钟）。
 *
 * env: D4_L2_ONLY=逗号分隔 code（缺省=已灌种子的 19 张）
 */
import { test, expect, type Page, type Response } from '@playwright/test'
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const PROJECT_ID = '0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49'
const WP_ID = 'b3ab3c46-828f-4f48-950e-aee9bbdc923f'
const ENTRY = 'xlsx/gt-d4-operating-revenue'
const API_BASE = process.env.D4_L2_API_BASE || 'http://127.0.0.1:9980'
const SYNC_BASE = `${API_BASE}/api/projects/${PROJECT_ID}/workpapers/${WP_ID}/sync/entries/${ENTRY}`
const DELTA = 12345.67
const SKIP_KEYS = new Set(['seq', 'index', 'row_no', 'no', 'order', 'month', 'group_label'])
const DEFAULT_ONLY = 'D4-6,D4-7,D4-8,D4-9,D4-11,D4-12,D4-14,D4-15,D4-16,D4-17,D4-18,D4-19,D4-20,D4-21,D4-23,D4-24,D4-33,D4-34,D4-36'

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

function loadCases(): L2Case[] {
  const raw = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), 'fixtures/d4-l2-cases.json'), 'utf-8')
  let cases = [...(JSON.parse(raw) as { cases: L2Case[] }).cases]
  const only = (process.env.D4_L2_ONLY || DEFAULT_ONLY).split(',').map((s) => s.trim()).filter(Boolean)
  cases = cases.filter((c) => only.includes(c.code))
  return cases.sort((a, b) => Number(a.code.replace(/\D/g, '')) - Number(b.code.replace(/\D/g, '')))
}

function ooFrame(page: Page) {
  return page.frames().find((f) => /spreadsheeteditor\/main\/index\.html/.test(f.url()))
}

function toNum(t: string | null | undefined): number | null {
  if (t == null) return null
  const c = String(t).replace(/[,\s¥￥]/g, '')
  if (!c || c === '-') return null
  const n = Number(c)
  return Number.isFinite(n) ? n : null
}

function isAmount(vt: string) {
  return ['amount', 'number', 'integer', 'decimal'].includes(vt)
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

async function fetchValues(page: Page, token: string) {
  const res = await page.request.get(`${SYNC_BASE}/store-projection`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(res.ok()).toBeTruthy()
  const body = await res.json()
  return ((body.data?.projection ?? body.projection)?.values ?? {}) as Record<string, unknown>
}

function pickSample(values: Record<string, unknown>, tableKey: string, editKey: string | null, editVt: string) {
  const entries = Object.entries(values).filter(([k]) => k.startsWith(`${tableKey}/`))
  const ordered = [
    ...entries.filter(([k]) => (editKey ? k.endsWith(`/${editKey}`) : true)),
    ...entries,
  ]
  const seen = new Set<string>()
  if (isAmount(editVt)) {
    for (const [k, field] of ordered) {
      if (seen.has(k)) continue
      seen.add(k)
      const col = (k.split('/').pop() || '').toLowerCase()
      if (SKIP_KEYS.has(col)) continue
      const n = Number((field as { value?: unknown })?.value)
      if (Number.isFinite(n) && Math.abs(n) > 1) return { fieldKey: k, value: n, kind: 'amount' as const }
    }
  }
  seen.clear()
  for (const [k, field] of ordered) {
    if (seen.has(k)) continue
    seen.add(k)
    const col = (k.split('/').pop() || '').toLowerCase()
    if (SKIP_KEYS.has(col)) continue
    const raw = (field as { value?: unknown })?.value
    if (typeof raw === 'number') continue
    const s = String(raw ?? '').trim()
    if (s && !s.startsWith('L2MARK-') && !/^-?\d+(\.\d+)?$/.test(s)) {
      return { fieldKey: k, value: s, kind: 'text' as const }
    }
  }
  return null
}

async function waitReady(page: Page) {
  await expect.poll(async () => {
    const state = await page.locator('[data-testid="wp-sync-host"]').getAttribute('data-bridge-state')
    const f = ooFrame(page)
    if (!f) return state || 'no_frame'
    const info = await f.evaluate(() => {
      const api = (window as any).Asc?.editor || (window as any).editor
      if (!api) return { ok: false, n: 0 }
      let n = 0
      try { n = Number(api.asc_getWorksheetsCount?.() ?? 0) } catch { n = 0 }
      return { ok: n > 0, n }
    }).catch(() => ({ ok: false, n: 0 }))
    if (info.ok) return 'ok'
    return `${state || 'wait'}:sheets=${info.n}`
  }, { timeout: 420_000, intervals: [2_000] }).toBe('ok')
  // 冷启后 worksheet API 偶发仍抖一下
  await page.waitForTimeout(5_000)
}

async function locate(page: Page, wantSheet: string, from: number, to: number, wantV: number | null, wantT: string | null) {
  const f = ooFrame(page)
  if (!f) return { ok: false as const, reason: 'no frame' }
  return f.evaluate(({ want, fromR, toR, wantV: wv, wantT: wt, cols }) => {
    const api = (window as any).Asc?.editor || (window as any).editor
    if (!api) return { ok: false as const, reason: 'no api' }
    let n = 0
    try { n = Number(api.asc_getWorksheetsCount?.() ?? 0) } catch (e) {
      return { ok: false as const, reason: `sheetsCount: ${String(e)}`, located: false }
    }
    if (n <= 0) return { ok: false as const, reason: 'sheets=0', located: false }
    const names: string[] = []
    for (let i = 0; i < n; i += 1) {
      try {
        const ws = api.asc_getWorksheet?.(i)
        names.push(String((ws && ws.getName?.()) || api.asc_getWorksheetName?.(i) || `i${i}`))
      } catch {
        names.push(`i${i}`)
      }
    }
    let idx = names.findIndex((nm) => nm === want)
    if (idx < 0) {
      const code = (want.match(/D4-\d+/) || [])[0]
      if (code) idx = names.findIndex((nm) => nm.includes(code))
    }
    if (idx < 0) return { ok: false as const, reason: `no sheet ${want}`, located: false }
    try { api.asc_showWorksheet?.(idx) } catch (e) {
      return { ok: false as const, reason: `show: ${String(e)}`, located: false }
    }
    const parse = (t: string | null) => {
      if (t == null) return null
      const c = String(t).replace(/[,\s¥￥]/g, '')
      if (!c || c === '-') return null
      const num = Number(c)
      return Number.isFinite(num) ? num : null
    }
    const needle = wt ? String(wt).slice(0, 24) : null
    for (const col of cols) {
      for (let r = fromR; r <= toR; r += 1) {
        try {
          api.asc_findCell?.(`${col}${r}`)
          const t = api.asc_getCellInfo?.()?.asc_getText?.() ?? null
          if (wv != null) {
            const num = parse(t)
            if (num != null && Math.abs(num - wv) <= 0.01) return { ok: true as const, located: true, target: `${col}${r}`, oldText: t }
          }
          if (needle && t && String(t).includes(needle)) return { ok: true as const, located: true, target: `${col}${r}`, oldText: t }
        } catch { /* */ }
      }
    }
    return { ok: true as const, located: false }
  }, { want: wantSheet, fromR: from, toR: to, wantV, wantT, cols: 'ABCDEFGHIJKLMNOPQRST'.split('') })
}

async function typeCell(page: Page, ref: string, value: string) {
  const f = ooFrame(page)!
  const box = f.locator('#ce-cell-name').first()
  try { await box.click({ timeout: 10_000 }) } catch { await box.click({ force: true }) }
  await box.fill(ref)
  await page.keyboard.press('Enter')
  await page.waitForTimeout(400)
  await page.keyboard.press('Control+A')
  await page.keyboard.press('Backspace')
  await page.keyboard.type(value, { delay: 20 })
  await page.keyboard.press('Enter')
  await page.waitForTimeout(600)
}

async function opState(page: Page, token: string, opId: string) {
  const res = await page.request.get(`${SYNC_BASE}/operations/${opId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok()) return { state: `http_${res.status()}` }
  const body = await res.json()
  return (body?.data ?? body) as Record<string, unknown>
}

test.describe('D4 L2 fast batch', () => {
  test.setTimeout(900_000)

  test('一次进 OO 改多张 → 一次 forcesave', async ({ page }) => {
    const cases = loadCases()
    expect(cases.length).toBeGreaterThan(0)

    let materializeOk = false
    let forcesaveBody: Record<string, unknown> | null = null
    page.on('response', (res: Response) => {
      const u = res.url()
      if (u.includes('/materialize') && res.status() === 200) materializeOk = true
      if (u.includes('/forcesave') && res.request().method() === 'POST') {
        void res.json().then((j) => { forcesaveBody = (j?.data ?? j) as Record<string, unknown> }).catch(() => {})
      }
    })

    const token = await login(page)
    const before = await fetchValues(page, token)

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${WP_ID}/edit`, { waitUntil: 'domcontentloaded' })
    const card = page.locator('.gt-b-arch__card, .el-tabs__item, [role="tab"]').filter({ hasText: /D4-1(?!\d)/ }).first()
    await expect(card).toBeVisible({ timeout: 60_000 })
    await card.click()
    await page.waitForTimeout(1_500)
    const ooItem = page.locator('.d4-mode-toolbar .el-segmented__item, .sync-mode-bar .el-segmented__item')
      .filter({ hasText: '在线编辑' }).first()
    await expect(ooItem).toBeVisible({ timeout: 30_000 })
    await ooItem.click()
    await expect.poll(() => materializeOk, { timeout: 180_000 }).toBeTruthy()
    await waitReady(page)
    await page.waitForTimeout(8_000)
    try {
      await page.locator('[data-testid="wp-sync-host-mask"]').waitFor({ state: 'hidden', timeout: 60_000 })
    } catch { /* */ }

    const plans: Array<{
      code: string
      table_key: string
      target: string
      new_value: number | string
      kind: 'amount' | 'text'
      fieldKey: string
      ok: boolean
      reason?: string
    }> = []

    for (const c of cases) {
      const sample = pickSample(before, c.table_key, c.edit_key, c.edit_vt)
      if (!sample) {
        plans.push({ code: c.code, table_key: c.table_key, target: '', new_value: '', kind: 'amount', fieldKey: '', ok: false, reason: 'no_sample' })
        continue
      }
      const hit = await locate(
        page,
        c.excel_name,
        Math.max(1, c.first_data_row - 2),
        Math.max(c.last_data_row + 20, c.first_data_row + 40),
        sample.kind === 'amount' ? Number(sample.value) : null,
        sample.kind === 'text' ? String(sample.value) : null,
      )
      if (!hit.ok || !hit.located || !hit.target) {
        plans.push({ code: c.code, table_key: c.table_key, target: '', new_value: '', kind: sample.kind, fieldKey: sample.fieldKey, ok: false, reason: 'locate_miss' })
        continue
      }
      const newValue = sample.kind === 'amount'
        ? Math.round((Number(sample.value) + DELTA) * 100) / 100
        : `L2MARK-${c.code}-${Date.now().toString(36).slice(-3)}`
      await typeCell(page, String(hit.target), String(newValue))
      plans.push({
        code: c.code,
        table_key: c.table_key,
        target: String(hit.target),
        new_value: newValue,
        kind: sample.kind,
        fieldKey: sample.fieldKey,
        ok: true,
      })
    }

    const typed = plans.filter((p) => p.ok)
    expect(typed.length, `typed=${typed.length} plans=${JSON.stringify(plans)}`).toBeGreaterThanOrEqual(
      Math.min(1, cases.length),
    )
    expect(typed.length, `至少改到一半目标；typed=${typed.length} plans=${JSON.stringify(plans)}`).toBeGreaterThanOrEqual(
      Math.ceil(cases.length / 2),
    )

    await page.waitForTimeout(6_000)
    const saveBtn = page.locator('[data-testid="wp-sync-host-forcesave"]')
    await expect(saveBtn).toBeEnabled({ timeout: 30_000 })
    await saveBtn.click()
    await expect.poll(() => forcesaveBody !== null, { timeout: 90_000 }).toBeTruthy()
    const opId = String((forcesaveBody as any)?.operation_id || (forcesaveBody as any)?.operationId || '')
    expect(opId).toBeTruthy()

    const trail: string[] = []
    let payload: Record<string, unknown> = {}
    let state = ''
    await expect.poll(async () => {
      payload = await opState(page, token, opId)
      state = String(payload.state ?? '')
      if (state && state !== trail[trail.length - 1]) trail.push(state)
      return state
    }, { timeout: 420_000, intervals: [2_000] }).toMatch(/^(applied|error|rejected|conflict)$/)

    const after = state === 'applied' ? await fetchValues(page, token) : {}
    const storeChecks = typed.map((p) => {
      let ok = false
      let got: unknown = null
      if (p.kind === 'amount') {
        for (const [k, f] of Object.entries(after)) {
          if (!k.startsWith(`${p.table_key}/`)) continue
          const n = Number((f as { value?: unknown })?.value)
          if (Number.isFinite(n) && Math.abs(n - Number(p.new_value)) <= 0.05) {
            ok = true
            got = n
            break
          }
        }
      } else {
        for (const [k, f] of Object.entries(after)) {
          if (!k.startsWith(`${p.table_key}/`)) continue
          const v = String((f as { value?: unknown })?.value ?? '')
          if (v.includes(String(p.new_value).slice(0, 10))) {
            ok = true
            got = v
            break
          }
        }
      }
      return { code: p.code, ok, got, want: p.new_value }
    })

    mkdirSync(EVIDENCE_DIR, { recursive: true })
    const path = resolve(EVIDENCE_DIR, 'd4-l2-fast-batch.json')
    writeFileSync(path, JSON.stringify({
      captured_at: new Date().toISOString(),
      n_cases: cases.length,
      n_typed: typed.length,
      plans,
      operation_id: opId,
      trail,
      state,
      error: payload.application_error_code ?? payload.error_code ?? null,
      store_ok: storeChecks.filter((s) => s.ok).length,
      storeChecks,
    }, null, 2), 'utf-8')

    // eslint-disable-next-line no-console
    console.log('FAST_L2', JSON.stringify({
      typed: typed.length,
      state,
      store_ok: storeChecks.filter((s) => s.ok).length,
      fails: plans.filter((p) => !p.ok).map((p) => `${p.code}:${p.reason}`),
    }))

    expect(state, `trail=${trail} err=${payload.application_error_code}`).toBe('applied')
    expect(storeChecks.filter((s) => s.ok).length).toBeGreaterThanOrEqual(Math.min(1, typed.length))
  })
})
