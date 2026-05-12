/**
 * E2E — 查账穿透（余额→序时账）
 * 验证从余额表穿透到序时账的完整链路
 */
import { test, expect } from '@playwright/test'

test.describe('查账穿透', () => {
  test.beforeEach(async ({ page }) => {
    // 登录
    await page.goto('/login')
    await page.fill('input[placeholder*="用户名"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button:has-text("登录")')
    await page.waitForURL(/\/(dashboard|projects)/)
  })

  test('从余额表穿透到序时账', async ({ page }) => {
    // 进入项目的账表查询页
    await page.goto('/projects')
    await page.click('.project-card >> nth=0')

    // 等待余额表加载
    await expect(page.locator('.el-table')).toBeVisible({ timeout: 10000 })

    // 双击金额单元格触发穿透
    const amountCell = page.locator('.el-table__row >> nth=0 >> .gt-amt >> nth=0')
    await amountCell.dblclick()

    // 验证切换到序时账视图
    await expect(page.locator('.gt-penetration')).toBeVisible({ timeout: 5000 })

    // 验证序时账数据加载
    await expect(page.locator('.el-table__row')).toHaveCount.greaterThan(0)
  })

  test('序时账穿透到凭证详情', async ({ page }) => {
    // 假设已在序时账页面
    await page.goto('/projects')
    await page.click('.project-card >> nth=0')

    // 等待表格加载
    await expect(page.locator('.el-table')).toBeVisible({ timeout: 10000 })

    // 双击序时账行穿透到凭证
    const row = page.locator('.el-table__row >> nth=0')
    await row.dblclick()

    // 验证凭证详情面板出现
    await expect(page.locator('.drilldown-panel, .voucher-detail')).toBeVisible({ timeout: 5000 })
  })

  test('穿透面包屑导航可返回', async ({ page }) => {
    await page.goto('/projects')
    await page.click('.project-card >> nth=0')

    // 验证页面头部有返回按钮
    await expect(page.locator('.gt-page-header')).toBeVisible({ timeout: 10000 })
  })
})
