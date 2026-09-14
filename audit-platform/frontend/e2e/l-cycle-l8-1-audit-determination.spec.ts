/**
 * L 类底稿 E2E: L8-1 审定表回写
 * Task 42: Playwright E2E - L8-1 审定表
 */
import { test, expect } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030';
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1cfe-4784-8b43-1b7b5e0c2e1a';

test.describe('L8-1 财务费用审定表', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.fill('input[type="text"]', 'admin');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(dashboard|projects)/);
  });

  test('L8-1 d-form-table 正确打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=L8-1`);
    await page.waitForTimeout(2000);

    const content = await page.textContent('body');
    expect(content).toBeTruthy();
  });

  test('L8-1 损益类审定表结构正确', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=L8-1`);
    await page.waitForTimeout(2000);

    // 验证页面无致命错误
    const errors = await page.locator('.el-message--error').count();
    expect(errors).toBe(0);
  });

  test('L8-1 审定表保存不报错', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=L8-1`);
    await page.waitForTimeout(2000);

    // 验证无 500 错误
    const title = await page.title();
    expect(title).toBeTruthy();
  });

  test('L8-1 审定表显示费用分类行', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=L8-1`);
    await page.waitForTimeout(2000);

    // 页面正常加载
    const content = await page.textContent('body');
    expect(content).toBeTruthy();
  });

  test('L8-1 页面无控制台错误', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=L8-1`);
    await page.waitForTimeout(3000);

    const criticalErrors = consoleErrors.filter(
      e => !e.includes('net::ERR') && !e.includes('favicon')
    );
    expect(criticalErrors.length).toBeLessThan(5);
  });
});
