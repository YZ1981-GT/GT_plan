/**
 * Playwright E2E — A18-2 与监管层沟通函
 *
 * Spec: .kiro/specs/a18-2-regulatory-communication/
 * Task: 5.2
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || '005a6f2d-cecd-4e30-bcbd-9fb01236c194'
const SHOULD_RUN = process.env.RUN_A182_E2E === '1'

test.describe('A18-2 与监管层沟通函', () => {
  test.skip(!SHOULD_RUN, '跳过 E2E（需设置 RUN_A182_E2E=1）')

  test('加载 → 选监管机构 → 设置适用性 → 填内容 → 双签 → 保存 → 刷新验证', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpapers`)
    await page.waitForLoadState('networkidle')

    // Navigate to A18-2
    await page.getByText('A18-2').first().click()
    await page.waitForTimeout(1000)

    // Verify structured view loads
    const content = page.locator('.gt-a182__content')
    await expect(content).toBeVisible({ timeout: 10000 })

    // 1. Select authority (recipient)
    const select = page.locator('.gt-a182__recipient .el-select')
    await select.click()
    await page.getByText('中国证券监督管理委员会').click()

    // 2. Set matter1 applicability = Y
    const matter1Radio = page.locator('.gt-a182__matter').first().locator('.el-radio-group')
    await matter1Radio.locator('text=适用').first().click()

    // 3. Fill matter1 content textarea
    const textarea = page.locator('.gt-a182__matter').first().locator('textarea')
    await expect(textarea).toBeVisible()
    await textarea.fill('审计过程中发现管理层舞弊迹象')

    // 4. Set matter2 applicability = NA (verify textarea hidden)
    const matter2Radio = page.locator('.gt-a182__matter').nth(1).locator('.el-radio-group')
    await matter2Radio.locator('text=不涉及').click()
    const matter2Textarea = page.locator('.gt-a182__matter').nth(1).locator('textarea')
    await expect(matter2Textarea).not.toBeVisible()

    // 5. Dual-sign: fill CPA1 and CPA2
    const issuanceFields = page.locator('.gt-a182__issuance input:not([disabled])')
    await issuanceFields.nth(0).fill('张三')
    await issuanceFields.nth(1).fill('李四')

    // 6. Wait for debounce save
    await page.waitForTimeout(3000)
    await expect(page.locator('.gt-a182__save-status')).toContainText('已保存')

    // 7. Reload and verify persistence
    await page.reload()
    await page.waitForLoadState('networkidle')
    await page.getByText('A18-2').first().click()
    await page.waitForTimeout(1000)

    await expect(page.locator('.gt-a182__content')).toBeVisible({ timeout: 10000 })

    // Verify matter1 textarea still shows content
    const reloadedTextarea = page.locator('.gt-a182__matter').first().locator('textarea')
    await expect(reloadedTextarea).toHaveValue('审计过程中发现管理层舞弊迹象')

    // Verify CPA fields persisted
    const reloadedIssuance = page.locator('.gt-a182__issuance input:not([disabled])')
    await expect(reloadedIssuance.nth(0)).toHaveValue('张三')
    await expect(reloadedIssuance.nth(1)).toHaveValue('李四')
  })
})
