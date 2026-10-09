import { test as base, expect, type Page } from '@playwright/test'
import { installSyntheticNoteRoutes } from './fixtures/consol-note-runtime-routes'

type SyntheticRoutes = Awaited<ReturnType<typeof installSyntheticNoteRoutes>>
const test = base.extend<{ synthetic: SyntheticRoutes }>({
  synthetic: [async ({ context }, use) => {
    const synthetic = await installSyntheticNoteRoutes(context)
    try { await use(synthetic) } finally { synthetic.releaseAll() }
  }, { auto: true }],
})
const normalTable = (page: Page) => page.locator('.gt-note-content .el-table').first()
const snapshot = (page: Page) => page.evaluate(() => (window as any).__cp04NoteFixture.snapshot())
const writes = (routes: SyntheticRoutes) => routes.requests.filter((r) => r.method !== 'GET')

async function openFixture(page: Page) {
  await page.goto('/e2e/fixtures/consol-note-runtime.html')
  await expect(normalTable(page).locator('tbody tr').first()).toContainText('合成国企业务')
}
async function editAmount(page: Page, value: string) {
  const table = normalTable(page)
  if (!await table.locator('thead input[type="checkbox"]').count()) await page.getByRole('button', { name: '编辑' }).first().click()
  const first = table.locator('tbody tr').first()
  await first.locator('td').nth(2).locator('.gt-note-cell-text').click()
  await first.locator('input:not([type="checkbox"])').fill(value)
  await page.locator('.gt-note-section-title').first().click()
  await expect.poll(async () => (await snapshot(page)).dirty).toBe(true)
}

test('real headers and fullscreen retain distinct amount leaves on both template families', async ({ page, synthetic }, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await openFixture(page)
  for (const [standard, width] of [['soe', 11], ['listed', 6]] as const) {
    if (standard === 'listed') await page.getByTestId('fixture-listed').click()
    const table = normalTable(page)
    await expect(table.locator('thead tr')).toHaveCount(3)
    const first = table.locator('tbody tr').first()
    await expect(first.locator('td')).toHaveCount(width)
    for (let c = 1; c < width; c++) await expect(first.locator('td').nth(c)).toHaveText(String(c * 101))
    await expect(first).toContainText(standard === 'listed' ? '合成上市业务' : '合成国企业务')
    await page.getByRole('button', { name: '全屏', exact: true }).click()
    const fullscreen = page.locator('.gt-fullscreen')
    await expect(fullscreen).toBeVisible()
    await expect(fullscreen.locator('thead tr')).toHaveCount(3)
    const fullscreenRow = fullscreen.locator('tbody tr').first()
    await expect(fullscreenRow.locator('td')).toHaveCount(width)
    await page.screenshot({ path: testInfo.outputPath(`headers-${standard}.png`), fullPage: true })
    const finalLeaf = fullscreenRow.locator('td').nth(width - 1)
    await finalLeaf.scrollIntoViewIfNeeded()
    const bounds = await finalLeaf.evaluate((cell) => {
      const rect = cell.getBoundingClientRect()
      return { left: rect.left, right: rect.right, width: innerWidth }
    })
    expect(bounds.left).toBeGreaterThanOrEqual(0)
    expect(bounds.right).toBeLessThanOrEqual(bounds.width)
    await expect(finalLeaf).toHaveText(String((width - 1) * 101))
    await page.screenshot({ path: testInfo.outputPath(`headers-${standard}-last-leaf.png`), fullPage: true })
    await page.keyboard.press('Escape')
    await expect(fullscreen).toHaveCount(0)
  }
  expect(writes(synthetic)).toEqual([])
  expect(synthetic.blocked).toEqual([])
  expect(errors).toEqual([])
})

test('dirty cancellation keeps the old object and explicit acceptance switches without saving', async ({ page, synthetic }) => {
  await openFixture(page)
  await editAmount(page, '909')
  await page.getByTestId('fixture-listed').click()
  const decision = page.getByRole('dialog', { name: '切换附注' })
  await expect(decision).toBeVisible()
  await expect(normalTable(page)).toHaveCount(0)
  await decision.getByRole('button', { name: '继续编辑' }).click()
  await expect.poll(async () => (await snapshot(page)).variant).toBe('soe')
  await expect(normalTable(page).locator('tbody tr').first()).toContainText('909')
  expect((await snapshot(page)).dirty).toBe(true)
  await page.getByTestId('fixture-listed').click()
  await decision.getByRole('button', { name: '放弃修改并切换' }).click()
  await expect(normalTable(page).locator('tbody tr').first()).toContainText('合成上市业务')
  expect((await snapshot(page)).dirty).toBe(false)
  expect(writes(synthetic)).toEqual([])
  expect(synthetic.blocked).toEqual([])
})

test('pending detail and old save cannot revive or clear the new template state', async ({ page, synthetic }) => {
  await openFixture(page)
  const detail = synthetic.delayNext('/listed/五-5-2')
  await page.getByTestId('fixture-listed').click()
  await expect.poll(() => detail.reached).toBe(true)
  await expect(normalTable(page)).toHaveCount(0)
  expect(await page.evaluate(() => (window as any).__cp04NoteFixture.save())).toBe(false)
  await page.getByTestId('fixture-soe').click()
  await expect(normalTable(page).locator('tbody tr').first()).toContainText('合成国企业务')
  detail.release()
  await editAmount(page, '808')
  const saving = synthetic.delayNext('/data/', 'PUT')
  await page.getByRole('button', { name: '💾', exact: true }).click()
  await expect.poll(() => saving.reached).toBe(true)
  const saveRequest = writes(synthetic)[0]
  expect(saveRequest.body.data.template_variant).toBe('soe')
  expect(saveRequest.path).toContain('cp04-offline-project/2025/五-5-2')
  await page.getByTestId('fixture-listed').click()
  await page.getByRole('dialog', { name: '切换附注' }).getByRole('button', { name: '放弃修改并切换' }).click()
  await expect(normalTable(page).locator('tbody tr').first()).toContainText('合成上市业务')
  await editAmount(page, '707')
  saving.release()
  await expect(normalTable(page).locator('tbody tr').first()).toContainText('707')
  expect((await snapshot(page)).dirty).toBe(true)
  expect((await snapshot(page)).context.variant).toBe('listed')
  expect(writes(synthetic)).toHaveLength(1)
  expect(synthetic.blocked).toEqual([])
})

test('route firewall rejects real writes and side-effecting reads', async ({ page, synthetic }) => {
  await openFixture(page)
  const results = await page.evaluate(async () => {
    const requests = [
      ['/api/consol-note-sections/breakdown/real-project/2025/五-5-2', 'GET'],
      ['/api/consol-note-formulas?template_type=unknown', 'GET'],
      ['/api/consol-note-sections/data/real-project/2025/五-5-2', 'PUT'],
      ['/api/consolidation/real-project/2025/refresh-all', 'POST'],
    ]
    return Promise.all(requests.map(async ([url, method]) => {
      try { await fetch(url, { method }); return false } catch { return true }
    }))
  })
  expect(results).toEqual([true, true, true, true])
  expect(synthetic.blocked).toHaveLength(4)
})
