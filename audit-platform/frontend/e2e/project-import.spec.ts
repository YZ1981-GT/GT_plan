/**
 * E2E — 创建项目 + 导入账套
 * 验证项目创建和账套导入的完整流程
 */
import { test, expect } from '@playwright/test'

test.describe('创建项目 + 导入账套', () => {
  test.beforeEach(async ({ page }) => {
    // 登录
    await page.goto('/login')
    await page.fill('input[placeholder*="用户名"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button:has-text("登录")')
    await page.waitForURL(/\/(dashboard|projects)/)
  })

  test('创建新项目', async ({ page }) => {
    await page.goto('/projects')

    // 点击新建项目按钮
    await page.click('button:has-text("新建项目")')

    // 填写项目信息
    await page.fill('input[placeholder*="项目名称"]', 'E2E测试项目')
    await page.fill('input[placeholder*="客户名称"]', '测试客户有限公司')

    // 提交
    await page.click('button:has-text("确定")')

    // 验证项目创建成功
    await expect(page.locator('text=E2E测试项目')).toBeVisible()
  })

  test('导入账套数据', async ({ page }) => {
    // 进入项目的账表查询页
    await page.goto('/projects')
    await page.click('.project-card >> nth=0')

    // 点击导入按钮
    await page.click('button:has-text("导入")')

    // 验证导入对话框出现
    await expect(page.locator('.el-dialog:has-text("导入")')).toBeVisible()

    // 上传文件（使用 fixture）
    const fileInput = page.locator('input[type="file"]')
    await fileInput.setInputFiles('./e2e/fixtures/sample-balance.xlsx')

    // 等待识别完成
    await expect(page.locator('text=识别完成')).toBeVisible({ timeout: 30000 })

    // 确认提交
    await page.click('button:has-text("提交导入")')

    // 验证导入进度显示
    await expect(page.locator('.import-progress')).toBeVisible({ timeout: 10000 })
  })
})
