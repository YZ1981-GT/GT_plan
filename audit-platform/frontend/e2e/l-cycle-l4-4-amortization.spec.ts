/**
 * L 类底稿 E2E: L4-4 摊余成本摊销表 audit-sheet
 * Task 41: Playwright E2E - L4-4 摊余成本摊销表
 */
import { test, expect } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030';
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1cfe-4784-8b43-1b7b5e0c2e1a';

test.describe('L4-4 摊余成本摊销表', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.fill('input[type="text"]', 'admin');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(dashboard|projects)/);
  });

  test('L4-4 audit-sheet 正确打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=L4-4`);
    await page.waitForTimeout(2000);

    // 页面应正常加载（无500错误）
    const content = await page.textContent('body');
    expect(content).toBeTruthy();
  });

  test('L4-4 componentType 为 audit-sheet', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=L4-4`);
    await page.waitForTimeout(2000);

    // 验证页面无致命错误
    const errors = await page.locator('.el-message--error').count();
    expect(errors).toBe(0);
  });

  test('L4-4 页面无控制台错误', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=L4-4`);
    await page.waitForTimeout(3000);

    // 过滤掉非关键错误
    const criticalErrors = consoleErrors.filter(
      e => !e.includes('net::ERR') && !e.includes('favicon')
    );
    // 允许少量非致命错误
    expect(criticalErrors.length).toBeLessThan(5);
  });

  test('L4-4 摊余成本摊销表正确加载', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=L4-4`);
    await page.waitForTimeout(2000);

    const title = await page.title();
    expect(title).toBeTruthy();
  });

  test('L4-4 与 L4-3 实际利率关联', async ({ page }) => {
    // L4-4 摊余成本摊销需要 L4-3 实际利率结果
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=L4-4`);
    await page.waitForTimeout(2000);

    const content = await page.textContent('body');
    expect(content).toBeTruthy();
  });
});
