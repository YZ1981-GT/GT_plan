/**
 * E2E — 现金流量表支持底稿 A5-1 ~ A5-4
 *
 * Validates: cash-flow-support-workpaper spec Task 9
 *
 * A5-1: 现金流量表审计底稿
 * A5-2: 承诺事项底稿
 * A5-3: 或有事项底稿
 * A5-4: 终止经营底稿
 *
 * NOTE: data-blocked — 依赖真实项目底稿数据，无数据时 test.skip
 */
import { test, expect } from '@playwright/test'
import {
  ensureTestProject,
  findWorkpaper,
  TEST_PROJECT_ID,
} from './fixtures/ensure-test-project'

test.describe('A5 现金流量表支持底稿 E2E', () => {
  let token: string

  test.beforeAll(async ({ request }) => {
    const fixture = await ensureTestProject(request)
    test.skip(!fixture.ready, fixture.reason || '测试环境未就绪')
    token = fixture.token
  })

  test.beforeEach(async ({ page }) => {
    // 注入 token 到 sessionStorage/localStorage
    await page.addInitScript((t: string) => {
      window.sessionStorage.setItem('token', t)
      window.localStorage.setItem('token', t)
    }, token)
  })

  test('A5-1 现金流量表审计底稿能打开 (route not 404)', async ({ page, request }) => {
    const wp = await findWorkpaper(request, token, 'A5-1')
    test.skip(!wp.exists, '项目内无 A5-1 底稿，跳过')

    const response = await page.goto(
      `/projects/${TEST_PROJECT_ID}/workpapers/${wp.wpId}/edit`,
    )
    expect(response?.status()).not.toBe(404)

    // 等待渲染器或 Univer 加载
    await page.waitForSelector(
      '.gt-wp-renderer, .univer-container, [data-testid="workpaper-content"]',
      { timeout: 20_000 },
    )
  })

  test('A5-2 承诺事项底稿能打开', async ({ page, request }) => {
    const wp = await findWorkpaper(request, token, 'A5-2')
    test.skip(!wp.exists, '项目内无 A5-2 底稿，跳过')

    const response = await page.goto(
      `/projects/${TEST_PROJECT_ID}/workpapers/${wp.wpId}/edit`,
    )
    expect(response?.status()).not.toBe(404)

    await page.waitForSelector(
      '.gt-wp-renderer, .univer-container, [data-testid="workpaper-content"]',
      { timeout: 20_000 },
    )

    // 验证页面内容包含承诺事项相关文字或组件
    await page.waitForTimeout(3_000)
    const body = await page.textContent('body')
    const hasContent =
      body?.includes('承诺') ||
      body?.includes('事项') ||
      (await page.locator('.univer-container, .gt-wp-renderer').count()) > 0
    expect(hasContent).toBeTruthy()
  })

  test('A5-3 或有事项底稿能打开', async ({ page, request }) => {
    const wp = await findWorkpaper(request, token, 'A5-3')
    test.skip(!wp.exists, '项目内无 A5-3 底稿，跳过')

    const response = await page.goto(
      `/projects/${TEST_PROJECT_ID}/workpapers/${wp.wpId}/edit`,
    )
    expect(response?.status()).not.toBe(404)

    await page.waitForSelector(
      '.gt-wp-renderer, .gt-contingent-liability, .univer-container, [data-testid="workpaper-content"]',
      { timeout: 20_000 },
    )

    await page.waitForTimeout(3_000)
    const body = await page.textContent('body')
    const hasContent =
      body?.includes('或有事项') ||
      body?.includes('可能性') ||
      body?.includes('预计负债') ||
      (await page.locator('.gt-contingent-liability, .univer-container').count()) > 0
    expect(hasContent).toBeTruthy()
  })

  test('A5-4 终止经营底稿能打开', async ({ page, request }) => {
    const wp = await findWorkpaper(request, token, 'A5-4')
    test.skip(!wp.exists, '项目内无 A5-4 底稿，跳过')

    const response = await page.goto(
      `/projects/${TEST_PROJECT_ID}/workpapers/${wp.wpId}/edit`,
    )
    expect(response?.status()).not.toBe(404)

    await page.waitForSelector(
      '.gt-wp-renderer, .gt-discontinued-ops, .univer-container, [data-testid="workpaper-content"]',
      { timeout: 20_000 },
    )

    await page.waitForTimeout(3_000)
    const body = await page.textContent('body')
    const hasContent =
      body?.includes('终止经营') ||
      body?.includes('持续经营') ||
      body?.includes('净利润') ||
      (await page.locator('.gt-discontinued-ops, .univer-container').count()) > 0
    expect(hasContent).toBeTruthy()
  })
})
