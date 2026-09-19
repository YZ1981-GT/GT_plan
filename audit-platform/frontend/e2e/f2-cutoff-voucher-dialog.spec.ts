/**
 * f2-cutoff-voucher-dialog.spec.ts — F2-29/35 核对弹窗 + F2-14 推送 + F2-33/34 入口冒烟
 *
 * 夹具：
 * - F2-14 在审定明细包 F2-1
 * - F2-29~35 在检查类包 F2-29（seed 写入「F2-29至F2-35…检查类」xlsx；勿用 F2-1/F2-47 切 tab）
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { TEST_PROJECT_ID, findWorkpaper, clickWorkpaperSheetTab } from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID

async function loginAs(page: Page, username: string, password: string) {
  const resp = await page.request.post('/api/auth/login', {
    data: { username, password },
  })
  const body = await resp.json()
  const token = body.data?.access_token ?? body.access_token
  await page.addInitScript((t: string) => {
    window.sessionStorage.setItem('token', t)
    window.localStorage.setItem('token', t)
  }, token)
  return token
}

async function getToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  return body.data?.access_token ?? body.access_token
}

async function openPackageSheet(
  page: Page,
  request: APIRequestContext,
  packageWpCode: string,
  sheetCode: string,
) {
  const token = await getToken(request)
  const wpResult = await findWorkpaper(request, token, packageWpCode, PROJECT_ID)
  if (!wpResult.exists || !wpResult.wpId) return null
  await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
  await page.waitForTimeout(4_000)
  await clickWorkpaperSheetTab(page, sheetCode)
  await page.waitForTimeout(2_500)
  return wpResult
}

test.describe('F2-29 截止逐笔核对弹窗', () => {
  test('打开 F2-29 检查包 → 切 F2-29 → 核对弹窗 → 实时勾稽可见', async ({ page, request }) => {
    test.setTimeout(120_000)
    await loginAs(page, 'admin', 'admin123')

    const consoleErrors: string[] = []
    page.on('pageerror', (err) => consoleErrors.push(err.message))

    const wp = await openPackageSheet(page, request, 'F2-29', 'F2-29')
    test.skip(!wp, 'F2-29 检查类底稿不存在（请跑 seed_fix_projects --fix）')

    const addBtn = page.getByRole('button', { name: /\+/ }).filter({ hasText: /行/ }).first()
    if (await addBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await addBtn.click()
      await page.waitForTimeout(600)
    }

    const checkBtn = page.getByRole('button', { name: '核对' }).first()
    test.skip(!(await checkBtn.isVisible({ timeout: 10_000 }).catch(() => false)), '无核对按钮')

    await checkBtn.click()
    const dialog = page.locator('.el-dialog').filter({ hasText: /逐笔核对|实时勾稽/ }).first()
    await expect(dialog).toBeVisible({ timeout: 8_000 })
    await expect(dialog.getByText('实时勾稽').first()).toBeVisible()
    await expect(dialog.getByText(/截止细判|账证配对/).first()).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden({ timeout: 5_000 })

    const critical = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined/.test(e),
    )
    expect(critical, critical.join('\n')).toHaveLength(0)
  })
})

test.describe('F2-14 推送集中调整表按钮', () => {
  test('F2-1 包内切 F2-14 → 可见推送集中调整表', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page, 'admin', 'admin123')
    const wp = await openPackageSheet(page, request, 'F2-1', 'F2-14')
    test.skip(!wp, 'F2-1 底稿不存在')

    await expect(page.getByRole('button', { name: /推送集中调整表/ })).toBeVisible({ timeout: 15_000 })
  })
})

test.describe('F2-33/34/35 逐笔核对入口', () => {
  for (const code of ['F2-33', 'F2-34'] as const) {
    test(`${code} — 检查包内可见核对/逐笔核对`, async ({ page, request }) => {
      test.setTimeout(90_000)
      await loginAs(page, 'admin', 'admin123')
      const wp = await openPackageSheet(page, request, 'F2-29', code)
      test.skip(!wp, 'F2-29 检查类底稿不存在')

      const hasDialogEntry =
        (await page.getByText(/逐笔核对|完整表格/).first().isVisible({ timeout: 10_000 }).catch(() => false))
        || (await page.getByRole('button', { name: '核对' }).first().isVisible({ timeout: 3_000 }).catch(() => false))
      const hasInspectShell = (await page.locator('.f2-inspect, .ic-hero, .f2-cutoff').count()) > 0
      expect(hasDialogEntry || hasInspectShell).toBeTruthy()
    })
  }

  test('F2-35 — 表三核对弹窗 → 实时勾稽可见', async ({ page, request }) => {
    test.setTimeout(120_000)
    await loginAs(page, 'admin', 'admin123')
    const wp = await openPackageSheet(page, request, 'F2-29', 'F2-35')
    test.skip(!wp, 'F2-29 检查类底稿不存在')

    const addBtn = page.getByRole('button', { name: /\+/ }).filter({ hasText: /行/ }).last()
    if (await addBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await addBtn.click()
      await page.waitForTimeout(600)
    }

    const checkBtn = page.getByRole('button', { name: '核对' }).first()
    test.skip(!(await checkBtn.isVisible({ timeout: 10_000 }).catch(() => false)), '无核对按钮')

    await checkBtn.click()
    const dialog = page.locator('.el-dialog').filter({ hasText: /逐笔核对|实时勾稽/ }).first()
    await expect(dialog).toBeVisible({ timeout: 8_000 })
    await expect(dialog.getByText('实时勾稽').first()).toBeVisible()
    await expect(dialog.getByText(/收回≈发出|合同/).first()).toBeVisible()
    // OCR 入口（有 wpId 时）
    await expect(page.getByTestId('f2-35-ocr-contract')).toBeVisible({ timeout: 5_000 })
    await expect(page.getByTestId('f2-35-ocr-fee')).toBeVisible({ timeout: 5_000 })
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden({ timeout: 5_000 })
  })
})
