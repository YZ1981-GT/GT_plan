/**
 * f-cycle-f1-prepayment.spec.ts — F1 预付账款 E2E
 *
 * 冒烟 + 关键闭环：
 * - F1-7 自动抽凭引擎挂载（科目 1123）
 * - F1-CONF 拟发函清单 → 标记已发函(Y) → 写回 F1-det-rows
 * - F1-5 推送拟调整 → F1-aje-rows 即时落库
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { TEST_PROJECT_ID, findWorkpaper } from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID
const MARKER = `F1-E2E-${Date.now()}`

const DET_ROWS_KEY = 'F1-det-rows'
const LT_ROWS_KEY = 'F1-lt-rows'
const AJE_ROWS_KEY = 'F1-aje-rows'

async function loginAs(page: Page) {
  const resp = await page.request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  const token = body.data?.access_token ?? body.access_token
  await page.addInitScript((t: string) => {
    window.sessionStorage.setItem('token', t)
    window.localStorage.setItem('token', t)
  }, token)
  return token as string
}

async function getToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  return body.data?.access_token ?? body.access_token
}

/** 按 sheet 解析底稿：优先独立 wp_code（F1-7 等），F1-CONF 走主包 Tab */
async function resolveF1SheetWp(
  request: APIRequestContext,
  token: string,
  sheetCode: string,
): Promise<{ wpId: string; viaTab?: boolean } | null> {
  const direct = await findWorkpaper(request, token, sheetCode, PROJECT_ID)
  if (direct.exists && direct.wpId) return { wpId: direct.wpId }

  if (sheetCode === 'F1-CONF') {
    for (const anchor of ['F1', 'F1-1']) {
      const hit = await findWorkpaper(request, token, anchor, PROJECT_ID)
      if (hit.exists && hit.wpId) return { wpId: hit.wpId, viaTab: true }
    }
  }
  return null
}

async function openF1Sheet(page: Page, wpId: string, sheetCode: string, viaTab?: boolean) {
  const needsTab = viaTab || sheetCode === 'F1-CONF'
  await page.goto(f1EditUrl(wpId))
  await page.waitForTimeout(4_000)

  if (needsTab) {
    const tab = page.locator('.gt-wp-renderer__sheet-tabs-inner [role="tab"]').filter({ hasText: /函证|F1-CONF/i })
    await expect(tab.first(), `应存在 ${sheetCode} 页签`).toBeVisible({ timeout: 20_000 })
    await tab.first().click()
    await page.waitForTimeout(2_000)
  }
}

async function checklistItem(
  request: APIRequestContext,
  token: string,
  wpId: string,
  itemId: string,
): Promise<any | undefined> {
  const response = await request.get(`/api/workpapers/${wpId}/checklist-responses`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok()) return undefined
  const body = await response.json()
  const data = body?.data ?? body
  const items = Array.isArray(data) ? data : (data?.items ?? [])
  return items.find((item: any) => item.item_id === itemId)
}

function parseJsonArray(item: any): any[] {
  const raw = item?.remark ?? item?.conclusion
  if (!raw) return []
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

async function putChecklistItems(
  request: APIRequestContext,
  token: string,
  wpId: string,
  items: Array<{ item_id: string; remark?: string | null; conclusion?: string | null }>,
) {
  const resp = await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      project_id: PROJECT_ID,
      items: items.map(i => ({
        item_id: i.item_id,
        remark: i.remark ?? null,
        conclusion: i.conclusion ?? null,
      })),
    },
  })
  expect(resp.ok(), `checklist PUT failed: ${resp.status()} ${await resp.text()}`).toBeTruthy()
}

function f1EditUrl(wpId: string, sheet?: string) {
  const base = `/projects/${PROJECT_ID}/workpapers/${wpId}/edit`
  return sheet ? `${base}?sheet=${encodeURIComponent(sheet)}` : base
}

test.describe('F1 预付账款冒烟', () => {
  test('F1-1 审定表页面可加载', async ({ page, request }) => {
    test.setTimeout(60_000)
    await loginAs(page)
    const token = await getToken(request)

    const wpResult = await findWorkpaper(request, token, 'F1', PROJECT_ID)
    test.skip(!wpResult.exists, 'F1 底稿不存在')

    await page.goto(f1EditUrl(wpResult.wpId!))
    await page.waitForTimeout(6_000)

    const content = await page.textContent('body')
    expect(content).toMatch(/预付账款|F1-1|审定|底稿目录/)
  })

  test('F1-2 明细表可打开且含列设置', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)

    const wpResult = await findWorkpaper(request, token, 'F1-2', PROJECT_ID)
    test.skip(!wpResult.exists, 'F1-2 底稿不存在')

    await page.goto(f1EditUrl(wpResult.wpId!))
    await page.waitForTimeout(8_000)

    const content = await page.textContent('body')
    expect(content).toMatch(/预付|明细|债权人/)
    const colBtn = page.getByRole('button', { name: /列设置/ })
    if (await colBtn.count()) {
      await colBtn.first().click()
      await expect(page.getByText(/核心列|全部列|审定/)).toBeVisible({ timeout: 5_000 })
    }
  })
})

test.describe('F1 关键闭环', () => {
  test('F1-7 展开自动抽凭区 → 抽凭引擎可见（1123）', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const resolved = await resolveF1SheetWp(request, token, 'F1-7')
    test.skip(!resolved, 'F1-7 底稿不存在')

    await openF1Sheet(page, resolved!.wpId, 'F1-7', resolved!.viaTab)
    await expect(page.locator('.f1-comprehensive-check')).toBeVisible({ timeout: 30_000 })

    await expect(page.getByRole('button', { name: '标注跨期疑点' })).toBeVisible()
    await page.getByRole('button', { name: '+ 添加样本' }).first().click()
    await expect(page.getByRole('button', { name: '单据核对' }).first()).toBeVisible({ timeout: 10_000 })

    const collapseTitle = page.getByText(/自动抽凭.*1123/)
    await expect(collapseTitle).toBeVisible()
    await collapseTitle.click()

    await expect(page.locator('.gt-voucher-sampling-engine')).toBeVisible({ timeout: 20_000 })
    await expect(page.getByText(/笔数覆盖率|金额覆盖率/).first()).toBeVisible()
  })

  test('F1-CONF 标记已发函写回 F1-det-rows', async ({ page, request }) => {
    test.setTimeout(120_000)
    await loginAs(page)
    const token = await getToken(request)

    const f12 = await findWorkpaper(request, token, 'F1-2', PROJECT_ID)
    const f1 = await findWorkpaper(request, token, 'F1', PROJECT_ID)
    const f11 = await findWorkpaper(request, token, 'F1-1', PROJECT_ID)
    const resolvedWpId = f12.wpId || f1.wpId || f11.wpId
    test.skip(!resolvedWpId, 'F1 函证程序底稿不可达')
    const wpId = resolvedWpId!

    const beforeDet = await checklistItem(request, token, wpId, DET_ROWS_KEY)
    const beforeRows = parseJsonArray(beforeDet)

    const seedRows = [
      ...beforeRows.filter((r: any) => !String(r.customerName || '').includes('F1-E2E-')),
      {
        rowId: `row-${MARKER}-a`,
        customerName: `${MARKER}-甲`,
        endAudited: 1200,
        isConfirmed: '',
        relationType: '',
      },
      {
        rowId: `row-${MARKER}-b`,
        customerName: `${MARKER}-乙`,
        endAudited: 800,
        isConfirmed: 'Y',
        relationType: '',
      },
    ]

    await putChecklistItems(request, token, wpId, [
      { item_id: DET_ROWS_KEY, remark: JSON.stringify(seedRows) },
    ])

    await expect.poll(async () => {
      const item = await checklistItem(request, token, wpId, DET_ROWS_KEY)
      return parseJsonArray(item).some((r: any) => r.customerName === `${MARKER}-甲`)
    }, { timeout: 10_000 }).toBe(true)

    await openF1Sheet(page, wpId, 'F1-CONF', true)
    await expect(page.locator('.f1-confirmation-procedure')).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText(`${MARKER}-甲`)).toBeVisible({ timeout: 15_000 })

    const row = page.locator('.el-table__body tr').filter({ hasText: `${MARKER}-甲` }).first()
    await row.locator('.el-checkbox').click()
    await page.getByRole('button', { name: /标记已发函/ }).click()

    await expect.poll(async () => {
      const item = await checklistItem(request, token, wpId, DET_ROWS_KEY)
      const rows = parseJsonArray(item)
      const hit = rows.find((r: any) => r.rowId === `row-${MARKER}-a`)
      return hit?.isConfirmed === 'Y'
    }, { timeout: 15_000 }).toBe(true)

    // 清理
    await putChecklistItems(request, token, wpId, [
      { item_id: DET_ROWS_KEY, remark: JSON.stringify(beforeRows) },
    ])
  })

  test('F1-5 推送拟调整至 F1-3（saveImmediate）', async ({ page, request }) => {
    test.setTimeout(120_000)
    await loginAs(page)
    const token = await getToken(request)
    const resolved = await resolveF1SheetWp(request, token, 'F1-5')
    test.skip(!resolved, 'F1-5 底稿不存在')

    const wpId = resolved!.wpId
    const beforeLt = await checklistItem(request, token, wpId, LT_ROWS_KEY)
    const beforeAje = await checklistItem(request, token, wpId, AJE_ROWS_KEY)
    const beforeLtRows = parseJsonArray(beforeLt)
    const beforeAjeRows = parseJsonArray(beforeAje)

    const ltSeed = [
      ...beforeLtRows.filter((r: any) => !String(r.customerName || '').includes('F1-E2E-')),
      {
        rowId: `lt-${MARKER}`,
        customerName: `${MARKER}-减值户`,
        endBalance: 1000,
        badDebtProvision: 200,
        transferToOtherReceivable: 'N',
        auditedBalance: 800,
        aging: '2-3年',
        reason: 'E2E测试',
      },
      {
        rowId: `lt-${MARKER}-rje`,
        customerName: `${MARKER}-重分类户`,
        endBalance: 500,
        badDebtProvision: 0,
        transferToOtherReceivable: 'Y',
        auditedBalance: 500,
        aging: '1-2年',
        reason: 'E2E重分类',
      },
    ]

    await putChecklistItems(request, token, wpId, [
      { item_id: LT_ROWS_KEY, remark: JSON.stringify(ltSeed) },
      { item_id: AJE_ROWS_KEY, remark: JSON.stringify(beforeAjeRows) },
    ])

    await openF1Sheet(page, wpId, 'F1-5', resolved!.viaTab)
    await expect(page.locator('.f1-long-term')).toBeVisible({ timeout: 30_000 })
    await expect(page.getByRole('button', { name: /推送拟调整至 F1-3/ })).toBeEnabled({ timeout: 10_000 })

    await page.getByRole('button', { name: /推送拟调整至 F1-3/ }).click()
    await expect(page.getByText(/已向 F1-3 追加/)).toBeVisible({ timeout: 10_000 })

    await expect.poll(async () => {
      const item = await checklistItem(request, token, wpId, AJE_ROWS_KEY)
      const rows = parseJsonArray(item)
      return rows.filter((r: any) => String(r.description || '').includes(MARKER)).length
    }, { timeout: 15_000 }).toBeGreaterThanOrEqual(2)

    // 幂等：再次点击不应重复追加
    await page.getByRole('button', { name: /推送拟调整至 F1-3/ }).click()
    await expect(page.getByText(/无新增拟调整/)).toBeVisible({ timeout: 8_000 })

    // 清理
    await putChecklistItems(request, token, wpId, [
      { item_id: LT_ROWS_KEY, remark: JSON.stringify(beforeLtRows) },
      { item_id: AJE_ROWS_KEY, remark: JSON.stringify(beforeAjeRows) },
    ])
  })
})
