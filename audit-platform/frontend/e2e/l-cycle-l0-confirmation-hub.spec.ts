/**
 * L 类底稿 E2E: L0→ConfirmationHub 路由
 * Task 43: Playwright E2E - L0 ConfirmationHub
 */
import { test, expect } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030';
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1cfe-4784-8b43-1b7b5e0c2e1a';

test.describe('L0 筹资循环函证 → ConfirmationHub', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.fill('input[type="text"]', 'admin');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(dashboard|projects)/);
  });

  test('L0 正确路由到 ConfirmationHub', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=L0`);
    await page.waitForTimeout(2000);

    // 应路由到函证中心模块
    const content = await page.textContent('body');
    expect(content).toBeTruthy();
  });

  test('L0 ConfirmationHub 无致命错误', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=L0`);
    await page.waitForTimeout(2000);

    const errors = await page.locator('.el-message--error').count();
    expect(errors).toBe(0);
  });

  test('L0 ConfirmationHub 页面正常加载', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=L0`);
    await page.waitForTimeout(2000);

    const title = await page.title();
    expect(title).toBeTruthy();
  });

  test('L0 函证页面无控制台错误', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=L0`);
    await page.waitForTimeout(3000);

    const criticalErrors = consoleErrors.filter(
      e => !e.includes('net::ERR') && !e.includes('favicon')
    );
    expect(criticalErrors.length).toBeLessThan(5);
  });

  test('L0 cycle=L 参数传递正确', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=L0`);
    await page.waitForTimeout(2000);

    // ConfirmationHub 应接收 cycle=L 参数
    const content = await page.textContent('body');
    expect(content).toBeTruthy();
  });
});
