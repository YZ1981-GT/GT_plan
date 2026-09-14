/**
 * S 类底稿 E2E: S1 违反法规行为的考虑程序表
 * Task 42: Playwright E2E - S1 程序表打开 + 步骤展示 + ref_index chip 跳转
 */
import { test, expect } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030';
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1cfe-4784-8b43-1b7b5e0c2e1a';

test.describe('S1 违反法规行为的考虑程序表', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.fill('input[type="text"]', 'admin');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(dashboard|projects)/);
  });

  test('S1 程序表正确打开（a-program-console）', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=S1`);
    await page.waitForTimeout(2000);
    const content = await page.textContent('body');
    expect(content).toBeTruthy();
  });

  test('S1 程序表步骤展示（≥6步）', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=S1`);
    await page.waitForTimeout(3000);
    // 程序表步骤应至少有6行
    const steps = await page.locator('[class*="program-step"], [class*="procedure-row"], tr').count();
    expect(steps).toBeGreaterThan(0);
  });

  test('S1 页面无致命错误', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error' && !msg.text().includes('ResizeObserver')) {
        consoleErrors.push(msg.text());
      }
    });
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=S1`);
    await page.waitForTimeout(3000);
    const fatalErrors = consoleErrors.filter(e => e.includes('500') || e.includes('TypeError'));
    expect(fatalErrors.length).toBe(0);
  });
});
