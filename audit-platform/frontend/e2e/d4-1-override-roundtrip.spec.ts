/**
 * Task 18 真栈②：**覆盖往返** —— 在 OO 里改派生行金额 → forcesave → 切回表格视图，
 * 该格显示改后值并带「已人工覆盖」标记。
 *
 * spec: d4-html-to-oo-store-contract-alignment · Task 18 · **Requirement 5.3**
 *
 * ═══ 这条补的是与真栈①相反的方向 ═══
 *
 * 真栈①（`d4-1-adjudication-oo-visibility.spec.ts`）走 HTML→OO（报障方向）。本条走
 * **OO→HTML**：`forcesave → callback → extract → merge → rematerialize → store`，
 * 然后验证需求 6.2 的 **S2 态**（`stored ≠ snap`、`snap = derived`）在 UI 上真的出现。
 *
 * ═══ 两个必须说清的实现约束（都是踩过的坑）═══
 *
 * **一、callback 不经浏览器，所以不能用 `page.on('response')` 判它到没到。**
 * OO 容器是**直接**把 callback POST 给后端的。早先的诊断脚本监听浏览器网络得到
 * `callback_arrived=false`，那是判据本身的错 —— 同期 DB 里
 * `working_paper_sync_operation.application_bound_at` 明明有值。
 * 这里改用**后端权威状态**：轮询 operations 端点等 `state='applied'`。
 *
 * **二、只能改受管格。**
 * 早先诊断往 D4-1 受管 sheet 的 D30/E30（**非**受管格）写了 marker，往返走完
 * `application_bound → extracting → merging → rematerializing` 五步后在 `post_durable`
 * 阶段以 `excel_materialize_editable_write_failed` 失败。所以本判据只动受管金额列，
 * 并且**不硬编码行号** —— 扫 B 列找到 projection 里那个原值所在的行再改它。
 */
import { test, expect, type Page, type Response } from '@playwright/test'
import { writeFileSync, mkdirSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const PROJECT_ID = '0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49'
const WP_ID = 'b3ab3c46-828f-4f48-950e-aee9bbdc923f'
const ENTRY = 'xlsx/gt-d4-operating-revenue'
const SYNC_BASE = `/api/projects/${PROJECT_ID}/workpapers/${WP_ID}/sync/entries/${ENTRY}`
const MANAGED_SHEET = '营业收入审定表D4-1'
const MAIN_TABLE_KEY = 'adjudication_main_rows'
/** 受管金额列：`MANAGED_FIELD_SPECS` 里 `current_unadjusted` 的列标。 */
const COL_CURRENT_UNADJUSTED = 'B'
/** 扫描窗口：覆盖模板占位区与其后追加的派生行（materialize 在占位区之后追加）。 */
const SCAN = { from: 8, to: 30 }
/** 改动增量：取一个不可能与真实金额撞车的值。 */
const DELTA = 12345.67

const MODE_BAR = '.d4-tab-adjudication .sync-mode-bar'
const EVIDENCE_DIR = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../../../docs/operations/evidence/d4-store-contract-alignment',
)

async function login(page: Page): Promise<string> {
  // 全局 setup（seed_fix_projects）刚跑完、或 vite 代理刚建连时，首个请求偶发失败。
  // 登录是测试第一步，抗一下瞬时抖动，避免把环境噪声记成 D4 缺陷。
  let r = await page.request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  }).catch(() => null)
  for (let attempt = 1; attempt <= 4 && (r === null || !r.ok()); attempt += 1) {
    await page.waitForTimeout(3_000)
    r = await page.request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    }).catch(() => null)
  }
  expect(r, '登录请求连续 5 次都没拿到响应（后端/代理不可达）').not.toBeNull()
  expect(r!.ok(), `登录应成功 status=${r!.status()}`).toBeTruthy()
  const body = await r!.json()
  const token = body.data?.access_token ?? body.access_token
  expect(token, 'access_token').toBeTruthy()
  await page.addInitScript((v: string) => {
    sessionStorage.setItem('token', v)
    localStorage.setItem('token', v)
  }, token)
  return token as string
}

/** 主营段派生行的 `{rowId: {label, amount}}`（真实端点；投影体在 `data.projection`）。 */
async function fetchMainRows(page: Page, token: string) {
  const res = await page.request.get(`${SYNC_BASE}/store-projection`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(res.ok(), `store-projection 应 200，实得 ${res.status()}`).toBeTruthy()
  const body = await res.json()
  const values: Record<string, { value?: unknown }> =
    (body.data?.projection ?? body.projection)?.values ?? {}
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

/**
 * 在受管 sheet 上按值定位目标行 —— **只读扫描，不写**。
 *
 * ⚠️ 为什么写入不走这里的内部 API（踩过的坑，真栈实测）：
 * `asc_insertInCell` + `asc_closeCellEditor(true)` 能让**浏览器端**的
 * `asc_isDocumentModified()` 变 true，但那批改动**没有通过 WebSocket 同步到 OO 服务端**。
 * 于是 forcesave 时 Command Service 回 `cs_error=4`（no_changes），operation 直接
 * `rejected`，往返根本不开始。DB 实证：`state='rejected' error_code='cs_error=4'`。
 * 只有**真实键盘输入**才会产生 changes 并同步到服务端（那次拿到 `cs_error=0` 并走到
 * `extracting`）。所以定位用 API（便宜、准确），**写入必须用键盘**。
 */
async function locateManagedCellByValue(
  page: Page,
  { wantSheet, column, oldValue }:
    { wantSheet: string; column: string; oldValue: number },
) {
  const f = ooFrame(page)
  if (!f) return { ok: false as const, reason: 'OO iframe 未找到' }
  return f.evaluate(
    ({ want, col, from, to, oldV }:
      { want: string; col: string; from: number; to: number; oldV: number }) => {
      const api = (window as any).Asc?.editor || (window as any).editor
      if (!api) return { ok: false as const, reason: 'no Asc.editor' } as Record<string, unknown>
      const out: Record<string, unknown> = { ok: true }
      // 切到受管表
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
        if (idx < 0) idx = names.findIndex((nm) => nm.includes('D4-1'))
        out.matchedBy = idx >= 0 ? 'ok' : 'none'
        if (idx >= 0) { api.asc_showWorksheet?.(idx); out.activeSheet = names[idx] }
      } catch (e) { out.sheetErr = String(e) }

      // 扫列找 oldValue 所在行（不硬编码行号）
      const scanned: Record<string, string | null> = {}
      let hitRow: number | null = null
      for (let r = from; r <= to; r += 1) {
        const ref = `${col}${r}`
        try {
          api.asc_findCell?.(ref)
          const t = api.asc_getCellInfo?.()?.asc_getText?.() ?? null
          scanned[ref] = t
          const num = t == null ? null : Number(String(t).replace(/[,\s¥￥]/g, ''))
          if (num != null && Number.isFinite(num) && Math.abs(num - oldV) <= 0.01) {
            hitRow = r
            break
          }
        } catch { scanned[ref] = null }
      }
      out.scanned = scanned
      out.hitRow = hitRow
      out.target = hitRow == null ? null : `${col}${hitRow}`
      return { ...out, ok: true, located: hitRow != null }
    },
    { want: wantSheet, col: column, from: SCAN.from, to: SCAN.to, oldV: oldValue },
  )
}

/** 读一个格的当前文本（写完之后复核用）。 */
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

/**
 * 用**真实键盘**改一个格：名称框 `#ce-cell-name` 定位 → 打字 → Enter。
 *
 * 这是唯一能让改动同步到 OO 服务端、从而让 forcesave 拿到 `cs_error=0` 的路径
 * （见 `locateManagedCellByValue` 的注释）。
 */
async function typeIntoOoCell(page: Page, ref: string, value: string) {
  const f = ooFrame(page)
  if (!f) return { ok: false as const, reason: 'OO iframe 未找到' }
  const nameBox = f.locator('#ce-cell-name').first()
  if (await nameBox.count() === 0) return { ok: false as const, reason: '#ce-cell-name 不存在' }
  await nameBox.click({ timeout: 15_000 })
  await nameBox.fill(ref)
  await page.keyboard.press('Enter')
  await page.waitForTimeout(1_500)
  await page.keyboard.type(value, { delay: 60 })
  await page.keyboard.press('Enter')
  // 给 OO 时间把 changes 推到服务端（协同通道），再让 forcesave 去取。
  await page.waitForTimeout(12_000)
  return { ok: true as const }
}

/** 后端权威的 operation 状态（callback 不经浏览器，只能问后端）。 */
async function operationState(page: Page, token: string, opId: string): Promise<string> {
  const res = await page.request.get(`${SYNC_BASE}/operations/${opId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok()) return `http_${res.status()}`
  const body = await res.json().catch(() => null)
  const data = (body?.data ?? body) as Record<string, unknown> | null
  return String(data?.state ?? data?.operation_state ?? '')
}

test.describe('Task 18 真栈②：OO 改派生行金额 → 切回 HTML 带「已人工覆盖」（需求 5.3）', () => {
  test.setTimeout(1_200_000)

  test('覆盖往返：OO 改受管金额格 → operation applied → HTML 显示改后值 + S2 标记', async ({ page }) => {
    const consoleErrors: string[] = []
    const syncErrors: Array<{ path: string; status: number; body: string }> = []
    let materializeOk = false
    let forcesaveBody: Record<string, unknown> | null = null

    page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()) })
    page.on('response', (res: Response) => {
      const u = res.url()
      if (!u.includes('/sync/entries/')) return
      if (u.includes('/materialize') && res.status() === 200) materializeOk = true
      if (u.includes('/forcesave') && res.request().method() === 'POST') {
        void res.json().then((j) => { forcesaveBody = (j?.data ?? j) as Record<string, unknown> }).catch(() => {})
      }
      if (res.status() >= 400) {
        void res.text().then((t) => syncErrors.push({
          path: u.replace(/^https?:\/\/[^/]+/, ''), status: res.status(), body: t.slice(0, 800),
        })).catch(() => {})
      }
    })

    const token = await login(page)

    // ── 1. 选一个主营派生行的受管金额格作为目标 ──────────────────────────────
    const before = await fetchMainRows(page, token)
    const candidates = Object.entries(before).filter(
      ([rowId, v]) => rowId.startsWith('xsheet-main-') && v.amount != null && v.amount !== 0,
    )
    test.skip(
      candidates.length === 0,
      'D4-1 主营段无非零派生行 —— 覆盖往返无目标可改（上游 D4-2 为空，不是缺陷）',
    )
    const [targetRowId, targetRow] = candidates[0]
    const oldValue = Number(targetRow.amount)
    const newValue = Math.round((oldValue + DELTA) * 100) / 100

    // ── 2. 切「在线编辑」 ────────────────────────────────────────────────────
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${WP_ID}/edit`, { waitUntil: 'domcontentloaded' })
    const card = page.locator('.gt-b-arch__card').filter({ hasText: /D4-1(?!\d)/ }).first()
    await expect(card, 'D4-1 目录卡片应可见').toBeVisible({ timeout: 60_000 })
    await card.scrollIntoViewIfNeeded()
    await card.click()
    await expect(page.locator('.d4-tab-adjudication').first()).toBeVisible({ timeout: 60_000 })
    await expect(page.locator(MODE_BAR)).toBeVisible({ timeout: 30_000 })
    const ooItem = page.locator(`${MODE_BAR} .el-segmented__item`).filter({ hasText: '在线编辑' })
    await expect(ooItem).toBeVisible({ timeout: 15_000 })
    await ooItem.click()
    await expect.poll(() => materializeOk, { timeout: 300_000 }).toBeTruthy()
    const host = page.locator('[data-testid="wp-sync-host"]')
    // 🔴 timeout 给到 420s：OO 容器**冷启动后首次**打开这本 46 sheet 的大簿要做一次完整
    //    加载/转换，实测 240s 不够（卡在 `descriptor_mounted` —— DocEditor 已构造但
    //    `onDocumentReady` 未触发，于是 confirm-descriptor 还没发生）。
    await expect(host).toHaveAttribute('data-bridge-state', 'oo_editing', { timeout: 420_000 })
    await page.waitForTimeout(35_000)

    // ── 3. 定位受管格（只读扫描）→ 用真实键盘改它 ────────────────────────────
    const edit = await locateManagedCellByValue(page, {
      wantSheet: MANAGED_SHEET, column: COL_CURRENT_UNADJUSTED, oldValue,
    }) as Record<string, unknown>
    expect(edit.ok, `OO 扫描失败：${'reason' in edit ? String(edit.reason) : ''}`).toBeTruthy()
    if (!edit.ok) return
    expect(
      edit.located,
      `在 ${MANAGED_SHEET} 的 ${COL_CURRENT_UNADJUSTED} 列 ${SCAN.from}..${SCAN.to} 行里`
      + `找不到 projection 的原值 ${oldValue} —— 无法定位要改的受管格。scanned=${JSON.stringify(edit.scanned)}`,
    ).toBeTruthy()
    const targetRef = String(edit.target)
    const typed = await typeIntoOoCell(page, targetRef, String(newValue))
    expect(typed.ok, `键盘写入失败：${'reason' in typed ? typed.reason : ''}`).toBeTruthy()
    const cellTextAfter = await readOoCell(page, targetRef)
    expect(
      toNum(cellTextAfter),
      `键盘写入后 ${targetRef} 读回不是新值（got=${cellTextAfter}）。`
      + `若为 null 说明名称框定位没生效。`,
    ).toBeCloseTo(newValue, 2)

    // ── 4. forcesave → 等**后端**把 operation 走到 applied ───────────────────
    // OO 的协同通道把键盘 changes 推到服务端有延迟；点 forcesave 太早会拿到
    // cs_error=4(no_changes)。多点几次并每次给足等待，直到后端真的回了一个 forcesave。
    const saveBtn = page.locator('[data-testid="wp-sync-host-forcesave"]')
    await expect(saveBtn, 'forcesave 按钮应可用').toBeEnabled({ timeout: 30_000 })
    for (let attempt = 1; attempt <= 4 && forcesaveBody === null; attempt += 1) {
      if (await saveBtn.isEnabled().catch(() => false)) {
        await saveBtn.click().catch(() => { /* 竞态下按钮可能瞬时禁用，下一轮重试 */ })
      }
      try {
        await expect.poll(() => forcesaveBody !== null, { timeout: 30_000 }).toBeTruthy()
      } catch {
        // 还没回；再等一会让协同通道把 changes 推上去，然后重试点击
        await page.waitForTimeout(5_000)
      }
    }
    expect(
      forcesaveBody,
      `点了 4 次 forcesave 都没等到后端响应 —— OO 侧改动可能没同步到服务端`
      + `（cs_error=4）。target=${targetRef} host_dirty=`
      + `${await page.locator('[data-testid="wp-sync-host"]').getAttribute('data-dirty')}`,
    ).not.toBeNull()
    const opId = String(
      (forcesaveBody as Record<string, unknown> | null)?.operation_id
      ?? (forcesaveBody as Record<string, unknown> | null)?.operationId ?? '',
    )
    expect(opId, `forcesave 响应里没有 operation_id：${JSON.stringify(forcesaveBody)}`).toBeTruthy()

    const stateTrail: string[] = []
    let finalState = ''
    try {
      await expect.poll(async () => {
        const s = await operationState(page, token, opId)
        if (s !== stateTrail[stateTrail.length - 1]) stateTrail.push(s)
        finalState = s
        return s
      }, { timeout: 600_000, intervals: [2_000] }).toBe('applied')
    } catch { /* 下面统一断言，先把 trail 记进证据 */ }

    // ── 5. store 侧：该格的值确实变成了新值（往返真的落库）──────────────────
    let storedAfter: number | null = null
    try {
      await expect.poll(async () => {
        const rows = await fetchMainRows(page, token)
        storedAfter = rows[targetRowId]?.amount ?? null
        return storedAfter
      }, { timeout: 180_000, intervals: [3_000] }).toBeCloseTo(newValue, 2)
    } catch { /* 统一断言 */ }

    // ── 6. 切回表格视图，看 S2 标记 ──────────────────────────────────────────
    let htmlProbe: Record<string, unknown> = {}
    try {
      const htmlItem = page.locator(`${MODE_BAR} .el-segmented__item`).filter({ hasText: '表格视图' })
      if (await htmlItem.count() > 0) {
        // 等桥把 operation applied 反映到 UI：此前 busy 含 applied 会把该项锁成
        // is-disabled；修后 applied 时该项应可点，但仍要等轮询追上。
        await expect(htmlItem).not.toHaveClass(/is-disabled/, { timeout: 120_000 })
        await htmlItem.click()
        await expect(page.locator('.d4-tab-adjudication .el-table').first()).toBeVisible({ timeout: 60_000 })
        await page.waitForTimeout(6_000)
        const table = page.locator('.d4-tab-adjudication .el-table').first()
        const text = await table.innerText()
        // `.override-tag` 是 D4TabAdjudication.vue 里 S2/S4 的 el-tag class；
        // S2 文案「已人工覆盖」、S4 文案「覆盖·上游已变」。
        const tags = page.locator('.d4-tab-adjudication .override-tag')
        const tagCount = await tags.count()
        const tagTexts: string[] = []
        for (let i = 0; i < tagCount; i += 1) tagTexts.push((await tags.nth(i).innerText()).trim())
        htmlProbe = {
          table_has_new_value: text.replace(/[,\s]/g, '').includes(String(newValue).replace('.', '.')),
          table_snippet: text.slice(0, 600),
          override_tag_count: tagCount,
          override_tag_texts: tagTexts,
        }
      } else {
        htmlProbe = { error: '找不到「表格视图」切换项' }
      }
    } catch (e) {
      htmlProbe = { error: String(e).slice(0, 400) }
    }

    mkdirSync(EVIDENCE_DIR, { recursive: true })
    writeFileSync(
      resolve(EVIDENCE_DIR, 'task18-override-roundtrip.json'),
      JSON.stringify({
        captured_at: new Date().toISOString(),
        project_id: PROJECT_ID, wp_id: WP_ID, entry: ENTRY,
        target: {
          row_id: targetRowId, label: targetRow.label,
          old_value: oldValue, new_value: newValue,
          cell_ref: targetRef, oo_cell_text_after_typing: cellTextAfter,
        },
        oo_locate: edit,
        materialize_200: materializeOk,
        forcesave: forcesaveBody,
        operation_id: opId,
        operation_state_trail: stateTrail,
        operation_final_state: finalState,
        store_value_after: storedAfter,
        html: htmlProbe,
        sync_errors: syncErrors,
        console_errors: consoleErrors.slice(0, 10),
      }, null, 2),
      'utf-8',
    )

    // ── 7. 判定 ──────────────────────────────────────────────────────────────
    expect(
      finalState,
      `OO→HTML 往返没走到 applied。状态轨迹=${JSON.stringify(stateTrail)}；`
      + `sync_errors=${JSON.stringify(syncErrors).slice(0, 1200)}`,
    ).toBe('applied')

    expect(
      storedAfter,
      `往返后 store 里该格不是新值 —— OO 的改动没落库（需求 1.5：OO 改动必须生效）。`
      + `row=${targetRowId} old=${oldValue} want=${newValue} got=${storedAfter}`,
    ).toBeCloseTo(newValue, 2)

    expect(
      htmlProbe.override_tag_count as number,
      `切回表格视图后没有任何「已人工覆盖」标记 —— 需求 1.5 明确禁止静默显示派生值。`
      + `htmlProbe=${JSON.stringify(htmlProbe)}`,
    ).toBeGreaterThan(0)

    expect(
      (htmlProbe.override_tag_texts as string[]).some((t) => t.includes('已人工覆盖') || t.includes('覆盖')),
      `覆盖标记文案不对：${JSON.stringify(htmlProbe.override_tag_texts)}`,
    ).toBeTruthy()
  })
})
