/**
 * g-cycle-g12-g13-g14-index-navigation.spec.ts — G12/G13/G14 目录 Chip 跳转 E2E
 */
import { test, expect, type Page } from '@playwright/test'
import {
  TEST_PROJECT_ID,
  findWorkpaper,
  clickWorkpaperDirectoryTab,
  clickWorkpaperSheetTab,
  clickDirectoryIndexChip,
} from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID

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
}

const ADJ_NAV_CASES = [
  {
    wpSearch: 'G12',
    cycle: 'g12' as const,
    dirTestId: 'g12-directory',
    chipCode: 'G12-1',
    bodyHint: /审定|净敞口/,
  },
  {
    wpSearch: 'G13',
    cycle: 'g13' as const,
    dirTestId: 'g13-directory',
    chipCode: 'G13-1',
    bodyHint: /审定|公允价值/,
  },
  {
    wpSearch: 'G14',
    cycle: 'g14' as const,
    dirTestId: 'g14-directory',
    chipCode: 'G14-1',
    bodyHint: /审定|信用减值/,
  },
]

const DETAIL_NAV_CASES = [
  { wpSearch: 'G12', cycle: 'g12' as const, chipCode: 'G12-2', bodyHint: /套期关系|无效/ },
  { wpSearch: 'G13', cycle: 'g13' as const, chipCode: 'G13-2', bodyHint: /明细|公允价值|FV/ },
  { wpSearch: 'G14', cycle: 'g14' as const, chipCode: 'G14-2', bodyHint: /明细|减值|ECL/ },
]

test.describe('G12/G13/G14 目录跳转 — 审定表', () => {
  for (const c of ADJ_NAV_CASES) {
    test(`${c.wpSearch} 目录 Chip → ${c.chipCode}`, async ({ page, request }) => {
      test.setTimeout(90_000)
      await loginAs(page)

      const loginResp = await request.post('/api/auth/login', {
        data: { username: 'admin', password: 'admin123' },
      })
      const token = (await loginResp.json()).data?.access_token

      const wpResult = await findWorkpaper(request, token, c.wpSearch, PROJECT_ID)
      test.skip(!wpResult.exists, `${c.wpSearch} 底稿不存在`)

      await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
      await page.waitForTimeout(4_000)

      await clickWorkpaperDirectoryTab(page)
      await expect(page.locator(`[data-testid="${c.dirTestId}"]`)).toBeVisible({ timeout: 15_000 })
      await expect(page.locator('[data-testid="g-cycle-b-index-extras"]')).toBeVisible({ timeout: 10_000 })

      await clickDirectoryIndexChip(page, c.cycle, c.chipCode)

      const content = await page.textContent('body')
      expect(content).toMatch(c.bodyHint)
      await expect(page.locator('[data-testid="g-cycle-guide-strip"]')).toBeVisible({ timeout: 10_000 })
    })
  }
})

test.describe('G12/G13/G14 目录跳转 — 明细表', () => {
  for (const c of DETAIL_NAV_CASES) {
    test(`${c.wpSearch} 目录 Chip → ${c.chipCode}`, async ({ page, request }) => {
      test.setTimeout(90_000)
      await loginAs(page)

      const loginResp = await request.post('/api/auth/login', {
        data: { username: 'admin', password: 'admin123' },
      })
      const token = (await loginResp.json()).data?.access_token

      const wpResult = await findWorkpaper(request, token, c.wpSearch, PROJECT_ID)
      test.skip(!wpResult.exists, `${c.wpSearch} 底稿不存在`)

      await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
      await page.waitForTimeout(4_000)

      await clickWorkpaperDirectoryTab(page)
      await clickDirectoryIndexChip(page, c.cycle, c.chipCode)

      const content = await page.textContent('body')
      expect(content).toMatch(c.bodyHint)
    })
  }
})

test.describe('G12 审定表交叉验证栏', () => {
  test('G12-1 显示 guide strip 与交叉验证栏', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)

    const loginResp = await request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    })
    const token = (await loginResp.json()).data?.access_token

    const wpResult = await findWorkpaper(request, token, 'G12', PROJECT_ID)
    test.skip(!wpResult.exists, 'G12 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G12-1')
    await page.waitForTimeout(2_500)

    await expect(page.locator('[data-testid="g12-adjudication"]')).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('[data-testid="g-cycle-guide-strip"]')).toBeVisible()
    const crossBar = page.locator(
      '[data-testid="g12-adj-hedge-cross-bar"], [data-testid="g12-adj-hedge-cross-ok"], [data-testid="g12-adj-hedge-cross-pending"], [data-testid="g12-adj-fv-cross-bar"], [data-testid="g12-adj-fv-cross-ok"]',
    )
    await expect(crossBar.first()).toBeVisible({ timeout: 10_000 })
  })
})

test.describe('G13/G14 审定表交叉验证栏', () => {
  test('G13-1 显示 detail 交叉栏 testid', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)

    const loginResp = await request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    })
    const token = (await loginResp.json()).data?.access_token

    const wpResult = await findWorkpaper(request, token, 'G13', PROJECT_ID)
    test.skip(!wpResult.exists, 'G13 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G13-1')
    await page.waitForTimeout(2_500)

    await expect(page.locator('[data-testid="g13-adjudication"]')).toBeVisible({ timeout: 15_000 })
    const crossBar = page.locator(
      '[data-testid="g13-adj-detail-cross-bar"], [data-testid="g13-adj-detail-cross-ok"], [data-testid="g13-adj-detail-cross-pending"]',
    )
    await expect(crossBar.first()).toBeVisible({ timeout: 10_000 })
  })

  test('G14-1 显示 detail 交叉栏 testid', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)

    const loginResp = await request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    })
    const token = (await loginResp.json()).data?.access_token

    const wpResult = await findWorkpaper(request, token, 'G14', PROJECT_ID)
    test.skip(!wpResult.exists, 'G14 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G14-1')
    await page.waitForTimeout(2_500)

    await expect(page.locator('[data-testid="g14-adjudication"]')).toBeVisible({ timeout: 15_000 })
    const crossBar = page.locator(
      '[data-testid="g14-adj-detail-cross-bar"], [data-testid="g14-adj-detail-cross-ok"], [data-testid="g14-adj-detail-cross-pending"]',
    )
    await expect(crossBar.first()).toBeVisible({ timeout: 10_000 })
  })
})
