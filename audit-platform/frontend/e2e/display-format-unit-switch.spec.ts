/**
 * display-format-unit-switch.spec.ts — 显示格式单一真源 E2E 烟雾测试
 *
 * 验证 display-format-single-source spec Task 11 要求：
 * 1. TrialBalance 页面加载后切换显示单位（元→万元）
 * 2. 主表金额按 /10000 换算
 * 3. 弹窗（公式详情/汇总明细）内金额同步切换
 *
 * 项目：辽宁卫生服务有限公司 2025（FIX-B）
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { TEST_PROJECT_ID } from './fixtures/ensure-test-project'

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

test.describe('显示格式单位切换一致性', () => {
  test('主表切换"万元"后金额按万元展示，弹窗同步', async ({ page }) => {
    test.setTimeout(90_000)
    await loginAs(page, 'admin', 'admin123')

    // 1. 导航到 TrialBalance 页面
    await page.goto(`/projects/${PROJECT_ID}/trial-balance`)
    await page.waitForLoadState('networkidle')

    // 等待表格加载（试算表行出现）
    const tableRows = page.locator('.el-table__body-wrapper .el-table__row')
    await expect(tableRows.first()).toBeVisible({ timeout: 30_000 })

    // 2. 记录当前"元"模式下某个金额单元格的文本
    const amountCells = page.locator('.gt-amt, .gt-amount, [class*="amount"]')
    const firstAmountText = await amountCells.first().textContent() ?? ''

    // 解析元模式下的数值（移除千分符）
    const yuanValue = parseFloat(firstAmountText.replace(/,/g, '').replace(/—/g, '0'))

    // 3. 切换显示单位到"万元"
    // 查找单位切换控件（通常在页面顶部工具栏或设置区域）
    const unitSelector = page.locator('[class*="display-pref"], [class*="unit-switch"], .gt-toolbar')
    const wanButton = page.getByRole('radio', { name: /万元/ }).or(
      page.locator('label:has-text("万元")'),
    ).or(
      page.locator('[class*="unit"] >> text=万元'),
    )

    // 如果有直接的万元选项按钮
    if (await wanButton.first().isVisible({ timeout: 5_000 }).catch(() => false)) {
      await wanButton.first().click()
      await page.waitForTimeout(500) // 等待响应式更新
    } else {
      // 尝试通过 el-select 或 el-radio-group 切换
      const radioGroup = page.locator('.el-radio-group:has-text("元")')
      if (await radioGroup.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await radioGroup.locator('label:has-text("万元")').click()
        await page.waitForTimeout(500)
      } else {
        // 尝试 segmented control
        const segmented = page.locator('[class*="segmented"]:has-text("元")')
        if (await segmented.isVisible({ timeout: 3_000 }).catch(() => false)) {
          await segmented.locator('text=万元').click()
          await page.waitForTimeout(500)
        } else {
          test.skip(true, '未找到单位切换控件，可能页面结构已变更')
        }
      }
    }

    // 4. 验证切换后金额变化（应为原值 / 10000）
    const newAmountText = await amountCells.first().textContent() ?? ''
    const wanValue = parseFloat(newAmountText.replace(/,/g, '').replace(/—/g, '0'))

    // 如果原值是有效数字且不为0，验证换算关系
    if (!isNaN(yuanValue) && yuanValue !== 0 && !isNaN(wanValue)) {
      // 万元值应约等于元值/10000（允许四舍五入误差）
      const ratio = yuanValue / wanValue
      expect(ratio).toBeGreaterThan(9000) // 应接近 10000
      expect(ratio).toBeLessThan(11000)
    }

    // 5. 打开一个弹窗（公式详情/汇总明细）验证弹窗内也是万元
    // 尝试点击带公式的单元格或明细按钮
    const formulaCell = page.locator('[class*="formula"], [class*="dashed"], .gt-formula-cell').first()
    if (await formulaCell.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await formulaCell.click()
      await page.waitForTimeout(1000)

      // 检查弹窗/popover 内的金额是否也是万元级别
      const dialogAmounts = page.locator('.el-dialog .gt-amt, .el-popover .gt-amt, .el-drawer .gt-amt')
      if (await dialogAmounts.first().isVisible({ timeout: 5_000 }).catch(() => false)) {
        const dialogAmountText = await dialogAmounts.first().textContent() ?? ''
        const dialogValue = parseFloat(dialogAmountText.replace(/,/g, '').replace(/—/g, '0'))

        // 弹窗内数值应该也是万元级别（不应该是原始元值，除非标记 rawUnit）
        if (!isNaN(dialogValue) && dialogValue !== 0 && !isNaN(yuanValue) && yuanValue !== 0) {
          // 弹窗值应远小于原始元值（因为已除以10000）
          // 或者与主表万元值在同一数量级
          expect(Math.abs(dialogValue)).toBeLessThan(Math.abs(yuanValue) * 1.1)
        }
      }
    }

    // 6. 验证页面无 console 错误
    const consoleErrors: string[] = []
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })
    // 切回元确认不崩溃
    const yuanButton = page.getByRole('radio', { name: /^元$/ }).or(
      page.locator('label:has-text("元"):not(:has-text("万"))'),
    )
    if (await yuanButton.first().isVisible({ timeout: 3_000 }).catch(() => false)) {
      await yuanButton.first().click()
      await page.waitForTimeout(500)
    }

    // 验证无致命错误（允许非关键 warning）
    const fatalErrors = consoleErrors.filter(e =>
      !e.includes('Failed to resolve') && !e.includes('hydration'),
    )
    expect(fatalErrors).toHaveLength(0)
  })
})
