/**
 * E2E — 登录 happy path
 * 验证用户可以成功登录并跳转到首页
 */
import { test, expect } from '@playwright/test'

test.describe('登录流程', () => {
  test('使用正确凭据登录成功', async ({ page }) => {
    await page.goto('/login')

    // 填写登录表单
    await page.fill('input[placeholder*="用户名"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')

    // 点击登录按钮
    await page.click('button:has-text("登录")')

    // 验证跳转到首页
    await expect(page).toHaveURL(/\/(dashboard|projects)/)

    // 验证顶栏显示用户信息
    await expect(page.locator('.gt-topbar')).toBeVisible()
  })

  test('使用错误密码显示错误提示', async ({ page }) => {
    await page.goto('/login')

    await page.fill('input[placeholder*="用户名"]', 'admin')
    await page.fill('input[type="password"]', 'wrong-password')
    await page.click('button:has-text("登录")')

    // 验证显示错误消息
    await expect(page.locator('.el-message--error')).toBeVisible()
  })

  test('未登录访问受保护页面重定向到登录', async ({ page }) => {
    await page.goto('/projects')
    await expect(page).toHaveURL(/\/login/)
  })
})
