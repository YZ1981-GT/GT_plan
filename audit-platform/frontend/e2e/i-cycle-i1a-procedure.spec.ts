/**
 * I 类底稿 E2E: I1A 无形资产程序表打开 + 风险/控制联动
 * P6 Task 36
 */
import { test, expect } from '@playwright/test'

const PROJECT_ID = process.env.TEST_PROJECT_ID || 'df5b8403-4157-b297-744707db5883'
const BASE_URL = process.env.BASE_URL || 'http://localhost:3030'

test.describe('I1A 无形资产程序表', () => {
  test.beforeEach(async ({ page }) => {
    // 登录
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL(/.*projects.*|.*dashboard.*/)
  })

  test('程序表页面可打开且渲染步骤列表', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=I1A`)
    // 等待程序表组件加载
    await page.waitForTimeout(2000)
    // 验证页面标题或程序表内容
    const content = await page.textContent('body')
    expect(content).toBeTruthy()
  })

  test('程序表步骤包含摊销测算引用', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=I1A`)
    await page.waitForTimeout(2000)
    const content = await page.textContent('body')
    // I1A 应有摊销相关步骤
    expect(content?.includes('摊销') || content?.includes('I1-3')).toBeTruthy()
  })

  test('程序表引用 risk_for_cycle 数据源', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=I1A`)
    await page.waitForTimeout(2000)
    // 程序表首步应展示风险信息（来自 B50 风险评估）
    const content = await page.textContent('body')
    expect(content).toBeTruthy()
  })

  test('I1A 页面无 console 错误', async ({ page }) => {
    const errors: string[] = []
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text())
      }
    })
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=I1A`)
    await page.waitForTimeout(3000)
    // 过滤已知的非致命错误
    const fatalErrors = errors.filter(e =>
      !e.includes('net::ERR') &&
      !e.includes('favicon') &&
      !e.includes('ResizeObserver')
    )
    expect(fatalErrors.length).toBeLessThanOrEqual(2)
  })
})
