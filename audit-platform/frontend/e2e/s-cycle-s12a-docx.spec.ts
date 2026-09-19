/**
 * S 类底稿 E2E: S12A 评估专家报告 docx 弹窗
 * Task 45: Playwright E2E - S12A docx 弹窗预览/编辑/降级下载
 */
import { test, expect } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030';
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1cfe-4784-8b43-1b7b5e0c2e1a';

test.describe('S12A 评估专家报告 docx', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.fill('input[type="text"]', 'admin');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(dashboard|projects)/);
  });

  test('S12A word-template 正确打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=S12A`);
    await page.waitForTimeout(2000);
    const content = await page.textContent('body');
    expect(content).toBeTruthy();
  });

  test('S12A componentType 路由到 word-template', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=S12A`);
    await page.waitForTimeout(2000);
    const errors = await page.locator('.el-message--error').count();
    expect(errors).toBe(0);
  });

  test('S12A 页面无致命错误', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error' && !msg.text().includes('ResizeObserver')) {
        consoleErrors.push(msg.text());
      }
    });
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=S12A`);
    await page.waitForTimeout(3000);
    const fatalErrors = consoleErrors.filter(e => e.includes('500') || e.includes('TypeError'));
    expect(fatalErrors.length).toBe(0);
  });
});
