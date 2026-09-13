/**
 * G4-0d：D2-2 统一路径真实浏览器取证（§9.6 条件 3–7 的可自动化部分）。
 *
 * 真栈：frontend 3030 / backend 9980 / OnlyOffice 8080。
 * 目标底稿：已有 published representation 的 D2 实例（非最大无 substrate 的旁路底稿）。
 *
 * 断言：
 * 1. 进入 D2-2 并点「在线编辑」后出现 USER_SYNC_PREFIX 请求；
 * 2. 该会话不出现 /d2-sync/*；
 * 3. materialize 响应的 callbackUrl query 含 room-bound 四项 key（值脱敏不落盘）；
 * 4. WorkpaperSyncEditorHost 挂载；若 DocEditor ready 且可 forcesave，则尝试回 HTML；
 * 5. 证据 JSON 写入 kiro evidence（查数据，不只看 exit code）。
 */
import { test, expect, type Page, type Request, type Response } from '@playwright/test'
import { writeFileSync, mkdirSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const PROJECT_ID = '2aa00f57-1df4-4fe8-9840-2d65d0fd8749'
const WP_ID = 'ef7f88e3-09eb-42cc-9f1d-1469fb3e6c88'
const ENTRY = 'xlsx/gt-d2-accounts-receivable'
const USER_SYNC_NEEDLE = `/api/projects/${PROJECT_ID}/workpapers/${WP_ID}/sync/entries/`
const EVIDENCE_DIR = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../../../.kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/g4-0d-host-unified-path',
)

type NetHit = {
  method: string
  url: string
  status?: number
  kind: 'user_sync' | 'd2_sync' | 'other'
}

function classifyUrl(url: string): NetHit['kind'] {
  if (url.includes('/d2-sync/')) return 'd2_sync'
  if (url.includes(USER_SYNC_NEEDLE) || url.includes('/sync/entries/')) return 'user_sync'
  return 'other'
}

function redactCallbackUrl(raw: string): { keys: string[]; redacted: string } {
  try {
    const u = new URL(raw)
    const keys = [...u.searchParams.keys()].sort()
    for (const k of keys) u.searchParams.set(k, '<redacted>')
    return { keys, redacted: `${u.origin}${u.pathname}?${u.searchParams.toString()}` }
  } catch {
    return { keys: [], redacted: '<unparseable>' }
  }
}

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

async function openD2Detail(page: Page): Promise<void> {
  await page.goto(`/projects/${PROJECT_ID}/workpapers/${WP_ID}/edit`, {
    waitUntil: 'domcontentloaded',
  })
  const card = page
    .locator('.gt-b-arch__card')
    .filter({ hasText: /D2-2(?!\d)/ })
    .first()
  await expect(card, 'D2-2 目录卡片应可见').toBeVisible({ timeout: 60_000 })
  await card.scrollIntoViewIfNeeded()
  await card.click()
  await expect(page.locator('.d2-tab-detail, .d2-accounts-receivable').first()).toBeVisible({
    timeout: 60_000,
  })
  await expect(page.locator('.d2-mode-toolbar')).toBeVisible({ timeout: 30_000 })
}

test.describe('G4-0d D2-2 unified host path', () => {
  test.setTimeout(600_000)

  test('在线编辑走 USER_SYNC_PREFIX 且不打 /d2-sync/*', async ({ page }) => {
    const hits: NetHit[] = []
    const consoleErrors: string[] = []
    let materializeBody: Record<string, unknown> | null = null
    let forcesaveBody: Record<string, unknown> | null = null

    page.on('request', (req: Request) => {
      const url = req.url()
      const kind = classifyUrl(url)
      if (kind === 'other') return
      hits.push({ method: req.method(), url, kind })
    })
    page.on('response', (res: Response) => {
      const url = res.url()
      const kind = classifyUrl(url)
      if (kind === 'other') return
      const row = hits.find((h) => h.url === url && h.status == null)
      if (row) row.status = res.status()
      // 不在 response 钩子里 await json（会拖死测试收尾）；仅对关键响应 fire-and-forget
      if (url.includes('/materialize') || url.includes('/forcesave')) {
        void res
          .json()
          .then((json) => {
            const body = (json?.data ?? json) as Record<string, unknown>
            if (url.includes('/materialize')) {
              materializeBody = res.ok()
                ? body
                : { _http_status: res.status(), ...(typeof json === 'object' && json ? json : {}) }
            } else {
              forcesaveBody = res.ok()
                ? body
                : { _http_status: res.status(), ...(typeof json === 'object' && json ? json : {}) }
            }
          })
          .catch(() => {
            /* ignore */
          })
      }
    })

    const token = await login(page)
    // DocsAPI 入参探测（只记布尔；验证 readonly Proxy 深拷贝修复是否生效）
    await page.addInitScript(() => {
      const g = window as unknown as {
        __g4_0d_doc_editor_probe?: {
          called: boolean
          has_root_token: boolean
          document_mutable: boolean
        }
        DocsAPI?: { DocEditor?: new (id: string, config: Record<string, unknown>) => unknown }
      }
      const hook = () => {
        const api = g.DocsAPI
        if (!api || typeof api.DocEditor !== 'function') return false
        const Original = api.DocEditor
        api.DocEditor = function (id: string, config: Record<string, unknown>) {
          const doc = config?.document as Record<string, unknown> | undefined
          let documentMutable = false
          if (doc && typeof doc === 'object') {
            try {
              const marker = '__g4_probe_write__'
              doc[marker] = true
              documentMutable = doc[marker] === true
              delete doc[marker]
            } catch {
              documentMutable = false
            }
          }
          g.__g4_0d_doc_editor_probe = {
            called: true,
            has_root_token: typeof config?.token === 'string' && String(config.token).includes('.'),
            document_mutable: documentMutable,
          }
          return new Original(id, config)
        } as unknown as typeof Original
        ;(api.DocEditor as unknown as { prototype: unknown }).prototype = Original.prototype
        return true
      }
      if (!hook()) {
        const timer = window.setInterval(() => {
          if (hook()) window.clearInterval(timer)
        }, 50)
      }
    })
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })
    await openD2Detail(page)

    // Element Plus segmented：真实 input[type=radio] 是 hidden；点可见的 item label
    const ooItem = page
      .locator('.d2-mode-toolbar .el-segmented__item')
      .filter({ hasText: '在线编辑' })
    await expect(ooItem, '在线编辑选项应可见').toBeVisible({ timeout: 15_000 })
    await expect(ooItem, '在线编辑不应 disabled').not.toHaveClass(/is-disabled/)
    await ooItem.click()

    // 先等任意 sync 请求，便于失败时区分「没点上」与「点上但失败」
    try {
      await expect.poll(() => hits.length, { timeout: 30_000 }).toBeGreaterThan(0)
    } catch (err) {
      throw new Error(
        `点「在线编辑」后 30s 内无 sync 请求；console=${JSON.stringify(consoleErrors.slice(0, 8))}；toolbar=${await page.locator('.d2-mode-toolbar').innerText().catch(() => '<missing>')}`,
      )
    }

    // 等 store-projection → pending → materialize 链路（大表可达 40s+）
    try {
      await expect
        .poll(
          () =>
            hits.some(
              (h) => h.kind === 'user_sync' && h.url.includes('/materialize') && h.status === 200,
            ),
          { timeout: 180_000 },
        )
        .toBeTruthy()
    } catch {
      throw new Error(
        `应出现 materialize 200；hits=${JSON.stringify(
          hits.map((h) => ({
            kind: h.kind,
            status: h.status,
            url: h.url.replace(/^https?:\/\/[^/]+/, ''),
          })),
        )}；materializeBody=${JSON.stringify(materializeBody)?.slice(0, 800)}；console=${JSON.stringify(consoleErrors.slice(0, 8))}`,
      )
    }

    const userSync = hits.filter((h) => h.kind === 'user_sync')
    const d2Sync = hits.filter((h) => h.kind === 'd2_sync')
    expect(userSync.length, '应有 USER_SYNC_PREFIX 请求').toBeGreaterThan(0)
    expect(
      userSync.some((h) => h.url.includes('/store-projection')),
      '应打 store-projection',
    ).toBeTruthy()
    expect(
      userSync.some((h) => h.url.includes('/pending-mutations')),
      '应打 pending-mutations',
    ).toBeTruthy()
    expect(d2Sync, '该会话不得出现 /d2-sync/*').toEqual([])

    await expect
      .poll(() => materializeBody !== null, { timeout: 15_000 })
      .toBeTruthy()
    expect(materializeBody, '应捕获 materialize 响应体').toBeTruthy()
    const cfg =
      (materializeBody?.onlyoffice_config as Record<string, unknown> | undefined) ??
      (materializeBody?.onlyofficeConfig as Record<string, unknown> | undefined)
    const editorConfig = (cfg?.editorConfig ?? cfg?.editor_config) as
      | Record<string, unknown>
      | undefined
    const callbackUrl = String(editorConfig?.callbackUrl ?? editorConfig?.callback_url ?? '')
    const { keys: callbackKeys, redacted } = redactCallbackUrl(callbackUrl)
    for (const key of ['room_id', 'generation', 'doc_key', 'route_credential_id', 'route_token']) {
      expect(callbackKeys, `callbackUrl 应含 ${key}`).toContain(key)
    }

    // 宿主 DOM
    await expect(page.locator('[data-testid="wp-sync-host"]')).toBeVisible({ timeout: 60_000 })

    // 尽力 forcesave（先 confirm；再尝试在 OO iframe 内改一格，否则 CS error=4 无 callback）
    const saveBtn = page.locator('[data-testid="wp-sync-host-forcesave"]')
    let forcesaveClicked = false
    let confirmHit = false
    let ooCellDirtyAttempted = false
    let dirtyBeforeForcesave = false
    let ooCellEditProbe: Record<string, unknown> | null = null
    let confirmForcesaveError: string | null = null
    let htmlDomRoundtrip: {
      attempted: boolean
      marker: string | null
      switched_to_html: boolean
      marker_visible: boolean
      store_mirrored?: boolean
      dom_probe?: Record<string, unknown>
      dom_error?: string
    } = {
      attempted: false,
      marker: null,
      switched_to_html: false,
      marker_visible: false,
    }
    try {
      await expect
        .poll(
          () => hits.some((h) => h.url.includes('/confirm-descriptor') && h.status === 200),
          { timeout: 180_000 },
        )
        .toBeTruthy()
      confirmHit = true

      // 等 mask 消失（confirm → oo_editing）再改格
      await expect(page.locator('[data-testid="wp-sync-host-mask"]')).toHaveCount(0, {
        timeout: 30_000,
      })
      await expect(page.locator('[data-testid="wp-sync-host"]')).toHaveAttribute(
        'data-bridge-state',
        'oo_editing',
        { timeout: 30_000 },
      )
      // DocServer 注册晚于 confirm：过短会 CS error=1 doc_not_online
      await page.waitForTimeout(35_000)

      // OO Community 无 createConnector：用 Asc.editor 写受管格 B25（customer_name）。
      // Z99 只能造 CS dirty，不会进 HTML store —— §9.6 条件 6 要求 DOM 可见回读。
      let writtenMarker: string | null = null
      try {
        const marker = `g4h${Date.now().toString().slice(-6)}`
        writtenMarker = marker
        const sheet = page.frames().find((f) => /spreadsheeteditor\/main\/index\.html/.test(f.url()))
        if (sheet) {
          let cellEdit: Record<string, unknown> | null = null
          for (let attempt = 1; attempt <= 3; attempt += 1) {
            cellEdit = await sheet.evaluate(
              ({ value, attemptNo }: { value: string; attemptNo: number }) => {
                const api =
                  (window as unknown as { Asc?: { editor?: Record<string, any> }; editor?: Record<string, any> })
                    .Asc?.editor || (window as unknown as { editor?: Record<string, any> }).editor
                if (!api) return { ok: false, reason: 'no Asc.editor', attempt: attemptNo }
                const out: Record<string, unknown> = {
                  ok: true,
                  target: 'B25',
                  attempt: attemptNo,
                  hasInsert: typeof api.asc_insertInCell,
                  hasEnter: typeof api.asc_enterText,
                  hasPaste: typeof api.asc_PasteData,
                  hasFind: typeof api.asc_findCell,
                }
                // 必须精确切到受管 sheet，避免 /明细|D2-2/ 误匹配其它表
                try {
                  if (typeof api.asc_getWorksheetsCount === 'function') {
                    const n = api.asc_getWorksheetsCount()
                    const names: string[] = []
                    for (let i = 0; i < n; i += 1) {
                      const ws = api.asc_getWorksheet?.(i)
                      const name =
                        (ws && typeof ws.getName === 'function' && ws.getName()) ||
                        (typeof api.asc_getWorksheetName === 'function' &&
                          api.asc_getWorksheetName(i)) ||
                        `idx${i}`
                      names.push(String(name))
                    }
                    out.sheetNames = names
                    let want = names.findIndex((nm) => nm === '明细表D2-2')
                    if (want < 0) want = names.findIndex((nm) => /明细表D2-2/.test(nm))
                    if (want >= 0 && typeof api.asc_showWorksheet === 'function') {
                      api.asc_showWorksheet(want)
                      out.activeSheet = names[want]
                    }
                  }
                } catch (e) {
                  out.sheetErr = String(e)
                }
                try {
                  if (typeof api.asc_findCell === 'function') api.asc_findCell('B25')
                } catch (e) {
                  out.findErr = String(e)
                }
                try {
                  if (typeof api.asc_insertInCell === 'function') {
                    api.asc_insertInCell(value, 0, false)
                    out.inserted = true
                  }
                } catch (e) {
                  out.insertErr = String(e)
                }
                try {
                  if (typeof api.asc_enterText === 'function') {
                    api.asc_enterText(value)
                    out.entered = true
                  }
                } catch (e) {
                  out.enterErr = String(e)
                }
                try {
                  if (typeof api.asc_PasteData === 'function') {
                    api.asc_PasteData(1, value)
                    out.pasted = true
                  }
                } catch (e) {
                  out.pasteErr = String(e)
                }
                // 🔴 未 close 时 getCellInfo 可能只读到编辑缓冲，forcesave 文件仍是空格
                try {
                  if (typeof api.asc_closeCellEditor === 'function') {
                    out.closeRet = api.asc_closeCellEditor(true)
                    out.closed = true
                  }
                } catch (e) {
                  out.closeErr = String(e)
                }
                try {
                  const info = api.asc_getCellInfo?.()
                  out.cellText =
                    info && typeof info.asc_getText === 'function' ? info.asc_getText() : null
                } catch (e) {
                  out.cellInfoErr = String(e)
                }
                try {
                  out.modified =
                    typeof api.asc_isDocumentModified === 'function'
                      ? api.asc_isDocumentModified()
                      : null
                  if (typeof api.asc_Save === 'function') {
                    out.saveRet = api.asc_Save()
                    out.saved = true
                  }
                } catch (e) {
                  out.saveErr = String(e)
                }
                // 再读一次：确认落进文档模型（而非仅公式栏缓冲）
                try {
                  if (typeof api.asc_findCell === 'function') api.asc_findCell('B25')
                  const info2 = api.asc_getCellInfo?.()
                  out.cellTextAfterSave =
                    info2 && typeof info2.asc_getText === 'function' ? info2.asc_getText() : null
                  if (out.cellTextAfterSave) out.cellText = out.cellTextAfterSave
                } catch (e) {
                  out.cellInfo2Err = String(e)
                }
                return out
              },
              { value: marker, attemptNo: attempt },
            )
            ooCellEditProbe = cellEdit
            const textOk = String(cellEdit?.cellText ?? '').includes(marker)
            if (textOk) break
            await page.waitForTimeout(2_500)
          }
          ooCellDirtyAttempted = Boolean(
            cellEdit &&
              String((cellEdit as { cellText?: string }).cellText ?? '').includes(marker),
          )
          // 写入 + asc_Save 后稍等协同推送到达 DocServer
          await page.waitForTimeout(5000)
          try {
            await expect(page.locator('[data-testid="wp-sync-host"]')).toHaveAttribute(
              'data-dirty',
              '1',
              { timeout: 8_000 },
            )
          } catch {
            /* CS error 才是权威；UI dirty 仅作参考 */
          }
        }
      } catch {
        ooCellDirtyAttempted = false
        writtenMarker = writtenMarker // keep marker for evidence even if write failed
      }

      await expect(saveBtn).toBeEnabled({ timeout: 30_000 })
      dirtyBeforeForcesave =
        (await page.locator('[data-testid="wp-sync-host"]').getAttribute('data-dirty')) === '1'
      if (dirtyBeforeForcesave) ooCellDirtyAttempted = true

      // CS error=1 doc_not_online：DocServer 协同注册晚于 confirm，最多重试 3 次
      for (let fsAttempt = 1; fsAttempt <= 3; fsAttempt += 1) {
        const forcesaveWait = page.waitForResponse(
          (r) => r.url().includes('/forcesave') && r.request().method() === 'POST',
          { timeout: 60_000 },
        )
        await expect(saveBtn).toBeEnabled({ timeout: 30_000 })
        await saveBtn.click()
        forcesaveClicked = true
        try {
          const fsRes = await forcesaveWait
          const fsJson = await fsRes.json().catch(() => null)
          const body = ((fsJson as { data?: unknown } | null)?.data ?? fsJson) as
            | Record<string, unknown>
            | null
          forcesaveBody = fsRes.ok()
            ? body
            : {
                _http_status: fsRes.status(),
                ...(typeof fsJson === 'object' && fsJson ? (fsJson as Record<string, unknown>) : {}),
              }
        } catch {
          /* 下方仍记 hits */
        }
        const cs = forcesaveBody && 'cs_error' in forcesaveBody ? Number(forcesaveBody.cs_error) : null
        if (cs === 0) break
        if (cs === 1 && fsAttempt < 3) {
          await page.waitForTimeout(15_000)
          continue
        }
        break
      }
      await expect
        .poll(() => hits.some((h) => h.url.includes('/forcesave')), { timeout: 5_000 })
        .toBeTruthy()
      try {
        await expect
          .poll(
            () =>
              hits.some((h) => h.url.includes('/onlyoffice-callback')) ||
              hits.some((h) => h.url.includes('/forcesave') && (h.status === 202 || h.status === 422)),
            { timeout: 90_000 },
          )
          .toBeTruthy()
      } catch {
        /* 证据阶段记录即可 */
      }
      // §9.6 条件 6：CS0 后桥应轮询至 applied → reloadHtml；再断言 DOM
      const csOk =
        forcesaveBody &&
        'cs_error' in forcesaveBody &&
        Number(forcesaveBody.cs_error) === 0
      htmlDomRoundtrip = {
        attempted: Boolean(writtenMarker) && Boolean(csOk),
        marker: writtenMarker,
        switched_to_html: false,
        marker_visible: false,
        store_mirrored: false,
      }
      if (writtenMarker && csOk) {
        const trackedOpId =
          forcesaveBody && typeof forcesaveBody.operation_id === 'string'
            ? String(forcesaveBody.operation_id)
            : forcesaveBody && typeof forcesaveBody.operationId === 'string'
              ? String(forcesaveBody.operationId)
              : null
        try {
          // 先跟本次 forcesave 的 operation 到 applied（避免被并行二次 forcesave 带跑）
          if (trackedOpId) {
            await expect
              .poll(
                async () => {
                  const res = await page.request.get(
                    `/api/projects/${PROJECT_ID}/workpapers/${WP_ID}/sync/entries/${ENTRY}/operations/${trackedOpId}`,
                    { headers: { Authorization: `Bearer ${token}` } },
                  )
                  if (!res.ok()) return `http_${res.status()}`
                  const body = await res.json().catch(() => null)
                  const data = (body?.data ?? body) as Record<string, unknown> | null
                  return String(data?.state ?? data?.operation_state ?? '')
                },
                { timeout: 240_000 },
              )
              .toBe('applied')
          }

          // 再等 store 镜像（比等桥状态更硬）：checklist 出现 marker 即 apply+mirror 完成
          await expect
            .poll(
              async () => {
                const res = await page.request.get(
                  `/api/workpapers/${WP_ID}/checklist-responses`,
                  { headers: { Authorization: `Bearer ${token}` } },
                )
                if (!res.ok()) return false
                const body = await res.json().catch(() => null)
                const text = JSON.stringify(body ?? {})
                return text.includes(writtenMarker)
              },
              { timeout: 120_000 },
            )
            .toBeTruthy()
          htmlDomRoundtrip.store_mirrored = true

          try {
            await expect
              .poll(
                async () => {
                  const st =
                    (await page.locator('[data-testid="wp-sync-host"]').getAttribute(
                      'data-bridge-state',
                    )) ?? ''
                  if (st === 'html_idle' || st === 'applied') return true
                  if ((await page.locator('[data-testid="wp-sync-host"]').count()) === 0) return true
                  return false
                },
                { timeout: 60_000 },
              )
              .toBeTruthy()
          } catch {
            /* 桥未自动切回时走下方催点 / 整页重开 */
          }

          // 同会话桥可能卸下宿主但未 loadAll：整页重开从 checklist 真源渲染
          await page.goto(`/projects/${PROJECT_ID}/workpapers/${WP_ID}/edit`, {
            waitUntil: 'domcontentloaded',
          })
          await openD2Detail(page)

          await expect(page.locator('.d2-tab-detail')).toBeVisible({ timeout: 120_000 })
          await expect(page.locator('[data-testid="wp-sync-host"]')).toHaveCount(0, {
            timeout: 60_000,
          })
          htmlDomRoundtrip.switched_to_html = true
          // 大表虚拟滚动默认 browseMode=true（span 文本）；先填搜索缩小行集。
          // 🔴 勿只靠 input[value]/innerText：Vue 受控 el-input 常不写 value 属性，
          //    且 input.value 不进 body.innerText —— 这是此前 marker_visible 假失败根因。
          const search = page.locator('.d2-tab-detail .toolbar-right .el-input__inner').first()
          await expect(search, '客户名称搜索框应可见').toBeVisible({ timeout: 30_000 })
          await search.click()
          await search.fill('')
          await search.fill(writtenMarker)
          await expect(search).toHaveValue(writtenMarker)
          await page.waitForTimeout(800)

          const browseToggle = page.locator('.d2-tab-detail').getByRole('button', {
            name: /切换表格编辑|切换虚拟速览/,
          })
          // 优先留在虚拟速览（cellRenderer 把 customerName 渲成可见文本）
          if ((await browseToggle.count()) > 0) {
            const label = await browseToggle.first().innerText()
            if (/切换虚拟速览/.test(label)) {
              await browseToggle.first().click()
              await page.waitForTimeout(400)
            }
          }

          const byExactText = page.locator('.d2-tab-detail').getByText(writtenMarker, {
            exact: true,
          })
          await expect
            .poll(
              async () => {
                const textCount = await byExactText.count()
                const inputProp = await page.evaluate((m) => {
                  const root = document.querySelector('.d2-tab-detail')
                  if (!root) return 0
                  const inputs = root.querySelectorAll('input, textarea')
                  let n = 0
                  for (const el of inputs) {
                    const v = (el as HTMLInputElement).value || ''
                    // 排除工具栏搜索框自身
                    if (v === m && !el.closest('.toolbar-right')) n += 1
                  }
                  return n
                }, writtenMarker)
                const virtualText = await page.evaluate((m) => {
                  const root = document.querySelector('.d2-tab-detail .virtual-table, .d2-tab-detail')
                  return root?.textContent?.includes(m) ? 1 : 0
                }, writtenMarker)
                return textCount + inputProp + virtualText
              },
              { timeout: 60_000 },
            )
            .toBeGreaterThan(0)
          htmlDomRoundtrip.marker_visible = true
          htmlDomRoundtrip.dom_probe = {
            by_exact_text: await byExactText.count(),
            input_prop_hits: await page.evaluate((m) => {
              const root = document.querySelector('.d2-tab-detail')
              if (!root) return 0
              let n = 0
              for (const el of root.querySelectorAll('input, textarea')) {
                const v = (el as HTMLInputElement).value || ''
                if (v === m && !el.closest('.toolbar-right')) n += 1
              }
              return n
            }, writtenMarker),
            virtual_text_has: await page.evaluate(
              (m) =>
                document
                  .querySelector('.d2-tab-detail .virtual-table, .d2-tab-detail')
                  ?.textContent?.includes(m) ?? false,
              writtenMarker,
            ),
            search_value: await search.inputValue().catch(() => ''),
            tracked_operation_id: trackedOpId,
          }
        } catch (err) {
          htmlDomRoundtrip.marker_visible = false
          htmlDomRoundtrip.dom_error = String(err).slice(0, 500)
        }
      }
    } catch (err) {
      // confirm/forcesave 失败写入证据，但末尾硬断言会打红（不得网络门假绿）
      confirmForcesaveError = String(err).slice(0, 500)
    }

    const tokenProbe = await page.evaluate(() => {
      const status = document.querySelector('[data-testid="wp-sync-host-status"]')?.textContent ?? ''
      const err = document.querySelector('[data-testid="wp-sync-host-error"]')?.textContent ?? ''
      const probe = (window as unknown as { __g4_0d_doc_editor_probe?: Record<string, unknown> })
        .__g4_0d_doc_editor_probe
      return {
        status: status.slice(0, 200),
        err: err.slice(0, 200),
        doc_editor_called: Boolean(probe?.called),
        doc_editor_has_root_token: Boolean(probe?.has_root_token),
        doc_editor_document_mutable: Boolean(probe?.document_mutable),
      }
    })

    const hostStatus = tokenProbe.status
    const hostError = tokenProbe.err

    // materialize 体是否带 JWT（只记布尔，不落盘 token 值）
    const cfgForProbe =
      (materializeBody?.onlyoffice_config as Record<string, unknown> | undefined) ??
      (materializeBody?.onlyofficeConfig as Record<string, unknown> | undefined) ??
      {}
    const materializeHasJwtToken =
      typeof cfgForProbe.token === 'string' && String(cfgForProbe.token).includes('.')

    const evidence = {
      script: 'e2e/g4-0d-d2-unified-path.spec.ts',
      captured_at: new Date().toISOString(),
      scope: { project_id: PROJECT_ID, wp_id: WP_ID, entry_id: ENTRY },
      predicates: {
        user_sync_requests: userSync.map((h) => ({
          method: h.method,
          path: h.url.replace(/^https?:\/\/[^/]+/, ''),
          status: h.status ?? null,
        })),
        forcesave_hits: hits
          .filter((h) => h.url.includes('/forcesave'))
          .map((h) => ({
            method: h.method,
            path: h.url.replace(/^https?:\/\/[^/]+/, ''),
            status: h.status ?? null,
          })),
        d2_sync_hits: d2Sync.length,
        callback_url_keys: callbackKeys,
        callback_url_redacted: redacted,
        host_mounted: true,
        confirm_descriptor_200: confirmHit,
        forcesave_clicked: forcesaveClicked,
        oo_cell_dirty_attempted: ooCellDirtyAttempted,
        host_dirty_before_forcesave: dirtyBeforeForcesave,
        forcesave_dispatch_error:
          forcesaveBody && 'dispatch_error' in forcesaveBody
            ? forcesaveBody.dispatch_error ?? null
            : null,
        forcesave_cs_error:
          forcesaveBody && 'cs_error' in forcesaveBody ? forcesaveBody.cs_error ?? null : null,
        forcesave_cs_outcome:
          forcesaveBody && 'cs_outcome' in forcesaveBody ? forcesaveBody.cs_outcome ?? null : null,
        forcesave_callback_expected:
          forcesaveBody && 'callback_expected' in forcesaveBody
            ? forcesaveBody.callback_expected ?? null
            : null,
        forcesave_http_status:
          forcesaveBody && '_http_status' in forcesaveBody
            ? forcesaveBody._http_status ?? null
            : hits.find((h) => h.url.includes('/forcesave'))?.status ?? null,
        forcesave_error_code: (() => {
          if (!forcesaveBody) return null
          const msg = forcesaveBody.message
          if (msg && typeof msg === 'object' && msg !== null && 'error_code' in msg) {
            return (msg as { error_code?: unknown }).error_code ?? null
          }
          return forcesaveBody.error_code ?? forcesaveBody.detail ?? null
        })(),
        forcesave_body_keys: forcesaveBody ? Object.keys(forcesaveBody).slice(0, 20) : null,
        materialize_room_id: materializeBody?.room_id ?? materializeBody?.roomId ?? null,
        materialize_has_jwt_token: materializeHasJwtToken,
        doc_editor_called: tokenProbe.doc_editor_called,
        doc_editor_has_root_token: tokenProbe.doc_editor_has_root_token,
        doc_editor_document_mutable: tokenProbe.doc_editor_document_mutable,
        host_status: hostStatus.slice(0, 200),
        host_error: hostError.slice(0, 400),
        confirm_forcesave_error: confirmForcesaveError,
        html_dom_roundtrip: htmlDomRoundtrip,
        oo_write_target: 'B25',
        oo_cell_edit_probe: ooCellEditProbe,
      },
      notes: [
        'token/JWT/route_credential 值已脱敏',
        'OO 写格：Asc.editor 写受管 B25(customer_name)；权威判据是 forcesave 响应 cs_error（0=有变更，4=no_changes）',
        'application applied / revision+1 由同目录 DB 核查脚本补齐',
        '§9.6 条件 6：切回结构化视图后 DOM 应出现 marker（getByDisplayValue / virtual text / input.value，排除搜索框）',
        'DocEditor document 必须是可变纯对象（readonly Proxy 会导致 document.token 赋值被吞 → -20）',
      ],
      auth_probe: { has_token: Boolean(token) },
    }

    mkdirSync(EVIDENCE_DIR, { recursive: true })
    writeFileSync(
      resolve(EVIDENCE_DIR, 'network-and-callback.json'),
      `${JSON.stringify(evidence, null, 2)}\n`,
      'utf-8',
    )

    // §9.6：confirm → CS0 → store 镜像 → DOM 可见，缺一不可（不得网络门假绿）
    expect(confirmHit, `confirm-descriptor 200 必达；err=${confirmForcesaveError ?? ''}`).toBe(
      true,
    )
    expect(
      evidence.predicates.forcesave_cs_error,
      `forcesave cs_error 应为 0；err=${confirmForcesaveError ?? ''}`,
    ).toBe(0)
    expect(
      evidence.predicates.html_dom_roundtrip.store_mirrored,
      `CS0 后 checklist 应含 marker；dom_error=${evidence.predicates.html_dom_roundtrip.dom_error ?? ''}`,
    ).toBe(true)
    expect(
      evidence.predicates.html_dom_roundtrip.marker_visible,
      `CS0 后 HTML DOM 应可见 marker；probe=${JSON.stringify(evidence.predicates.html_dom_roundtrip.dom_probe ?? {})}`,
    ).toBe(true)
  })
})
