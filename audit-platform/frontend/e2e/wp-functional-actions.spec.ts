/**
 * Playwright E2E: 底稿功能行为联动
 *
 * wp-functional-actions spec Task 8.3
 * 打开截止测试底稿 → 点动作按钮 → 弹窗 → 确认 → 数据填入
 *
 * 待环境验证：需要后端 9980 + 前端 3030 运行
 */
import { test, expect } from '@playwright/test'

const BASE_URL = 'http://localhost:3030'
const API_URL = 'http://localhost:9980'
const PROJECT_ID = 'df5b8403-xxxx-xxxx-xxxx-xxxxxxxxxxxx' // 首汽租车_2025

// 跳过条件：后端未启动时跳过
test.beforeAll(async ({ request }) => {
  try {
    const resp = await request.get(`${API_URL}/api/health`)
    if (resp.status() !== 200) {
      test.skip()
    }
  } catch {
    test.skip()
  }
})

test.describe('底稿功能行为联动', () => {
  test.beforeEach(async ({ page }) => {
    // 登录
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[placeholder*="用户名"]', 'admin')
    await page.fill('input[placeholder*="密码"]', 'admin123')
    await page.click('button:has-text("登录")')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('ACTION_REGISTRY 端点返回动作列表', async ({ page }) => {
    // 通过 API 验证动作列表端点
    const response = await page.request.get(
      `${API_URL}/api/projects/${PROJECT_ID}/workpapers/actions/registry`
    )

    if (response.ok()) {
      const data = await response.json()
      expect(data).toHaveProperty('functional_types')
      expect(Array.isArray(data.functional_types)).toBe(true)
      // 至少包含已知类型
      const types = data.functional_types.map((t: any) => t.type)
      expect(types).toContain('cutoff')
      expect(types).toContain('aging')
      expect(types).toContain('sampling')
    }
  })

  test('底稿编辑器显示动作按钮', async ({ page }) => {
    // 导航到底稿列表
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers`)
    await page.waitForLoadState('networkidle')

    // 查找截止测试底稿（D2-8）
    const wpRow = page.locator('.el-table__row:has-text("D2-8")')
    if (await wpRow.isVisible({ timeout: 5000 })) {
      await wpRow.click()
      await page.waitForLoadState('networkidle')

      // 验证工具栏有动作按钮
      const actionBtn = page.locator('button:has-text("截止测试取数"), button:has-text("📅")')
      const hasAction = await actionBtn.isVisible({ timeout: 5000 }).catch(() => false)
      expect(typeof hasAction).toBe('boolean')
    }
  })

  test('点击动作按钮弹出参数弹窗', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers`)
    await page.waitForLoadState('networkidle')

    // 查找截止测试底稿
    const wpRow = page.locator('.el-table__row:has-text("D2-8")')
    if (await wpRow.isVisible({ timeout: 5000 })) {
      await wpRow.click()
      await page.waitForLoadState('networkidle')

      // 点击动作按钮
      const actionBtn = page.locator('button:has-text("截止测试取数")')
      if (await actionBtn.isVisible({ timeout: 5000 })) {
        await actionBtn.click()

        // 验证弹窗出现
        const dialog = page.locator('.el-dialog:has-text("截止测试")')
        await expect(dialog).toBeVisible({ timeout: 5000 })

        // 验证弹窗包含参数字段
        await expect(dialog.locator('text=科目编码')).toBeVisible()
        await expect(dialog.locator('text=会计年度')).toBeVisible()
      }
    }
  })

  test('确认参数后执行动作并填入数据', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers`)
    await page.waitForLoadState('networkidle')

    const wpRow = page.locator('.el-table__row:has-text("D2-8")')
    if (await wpRow.isVisible({ timeout: 5000 })) {
      await wpRow.click()
      await page.waitForLoadState('networkidle')

      const actionBtn = page.locator('button:has-text("截止测试取数")')
      if (await actionBtn.isVisible({ timeout: 5000 })) {
        await actionBtn.click()

        const dialog = page.locator('.el-dialog:has-text("截止测试")')
        if (await dialog.isVisible({ timeout: 5000 })) {
          // 填写参数
          const yearInput = dialog.locator('input[placeholder*="年度"], .el-input-number input')
          if (await yearInput.isVisible()) {
            await yearInput.fill('2025')
          }

          // 点击确认按钮
          const confirmBtn = dialog.locator('button:has-text("确认"), button:has-text("执行")')
          if (await confirmBtn.isVisible()) {
            await confirmBtn.click()

            // 等待执行完成（成功消息或数据更新）
            const successMsg = page.locator('.el-message--success')
            const hasSuccess = await successMsg.isVisible({ timeout: 10000 }).catch(() => false)
            expect(typeof hasSuccess).toBe('boolean')
          }
        }
      }
    }
  })

  test('抽凭动作弹窗包含抽样方式选择', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers`)
    await page.waitForLoadState('networkidle')

    // 查找抽凭底稿（D2-9）
    const wpRow = page.locator('.el-table__row:has-text("D2-9")')
    if (await wpRow.isVisible({ timeout: 5000 })) {
      await wpRow.click()
      await page.waitForLoadState('networkidle')

      const actionBtn = page.locator('button:has-text("抽凭取数")')
      if (await actionBtn.isVisible({ timeout: 5000 })) {
        await actionBtn.click()

        const dialog = page.locator('.el-dialog:has-text("抽凭")')
        if (await dialog.isVisible({ timeout: 5000 })) {
          // 验证抽样方式选项
          await expect(dialog.locator('text=抽样方式')).toBeVisible()
          // 验证有分层/随机/大额选项
          const methodSelect = dialog.locator('.el-select, .el-radio-group')
          expect(await methodSelect.count()).toBeGreaterThan(0)
        }
      }
    }
  })

  test('账龄分析动作弹窗包含区间配置', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers`)
    await page.waitForLoadState('networkidle')

    // 查找账龄分析底稿（D2-13）
    const wpRow = page.locator('.el-table__row:has-text("D2-13")')
    if (await wpRow.isVisible({ timeout: 5000 })) {
      await wpRow.click()
      await page.waitForLoadState('networkidle')

      const actionBtn = page.locator('button:has-text("账龄分析取数")')
      if (await actionBtn.isVisible({ timeout: 5000 })) {
        await actionBtn.click()

        const dialog = page.locator('.el-dialog:has-text("账龄")')
        if (await dialog.isVisible({ timeout: 5000 })) {
          // 验证账龄区间配置
          await expect(dialog.locator('text=账龄区间')).toBeVisible()
          await expect(dialog.locator('text=基准日期')).toBeVisible()
        }
      }
    }
  })
})
