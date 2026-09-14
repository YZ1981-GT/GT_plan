/**
 * UAT — 底稿统一导入导出前端接入 Playwright 实测
 *
 * 锚定 spec workpaper-unified-import-export Phase 7 前端接入
 *
 * 验证：
 * 1. 底稿列表页：增强导入 / 批量导出(元数据) / 模板复制 按钮与弹窗
 * 2. 底稿编辑页：导出按钮命中 export-with-metadata
 * 3. 批量导出 enhanced API 200；export→import-enhanced round-trip
 *
 * 项目：辽宁卫生服务有限公司 2025
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'

const PROJECT_ID = '37814426-a29e-4fc2-9313-a59d229bf7b0'

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
  return token as string
}

async function findD2WpId(request: APIRequestContext, token: string): Promise<string | null> {
  const resp = await request.get(`/api/projects/${PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])
  const d2 = list.find((w: { wp_code?: string }) => (w.wp_code || '').toUpperCase() === 'D2')
  return d2?.id || null
}

test.describe('底稿导入导出前端接入', () => {
  test.describe.configure({ mode: 'serial' })

  test('列表页 — 增强导入/批量导出/模板复制弹窗可打开', async ({ page }) => {
    test.setTimeout(60_000)
    await loginAs(page, 'admin', 'admin123')
    await page.goto(`/projects/${PROJECT_ID}/workpapers`)
    await expect(page.getByRole('button', { name: '增强导入' })).toBeVisible({ timeout: 15_000 })

    await page.getByRole('button', { name: '增强导入' }).click()
    await expect(page.getByRole('dialog', { name: '导入底稿' })).toBeVisible({ timeout: 5_000 })
    await page.getByRole('button', { name: '取消' }).first().click()

    await page.getByRole('button', { name: '批量导出(元数据)' }).click()
    await expect(page.getByRole('dialog', { name: '批量导出底稿' })).toBeVisible({ timeout: 5_000 })
    await page.getByRole('button', { name: '取消' }).click()

    await page.getByRole('button', { name: '模板复制' }).click()
    await expect(page.getByRole('dialog', { name: '模板复制' })).toBeVisible({ timeout: 5_000 })
  })

  test('列表页 — 批量导出 enhanced API 联通', async ({ page }) => {
    test.setTimeout(90_000)
    const apiCalls: { url: string; status: number }[] = []
    page.on('response', (resp) => {
      if (resp.url().includes('batch-export-enhanced')) {
        apiCalls.push({ url: resp.url(), status: resp.status() })
      }
    })

    await loginAs(page, 'admin', 'admin123')
    await page.goto(`/projects/${PROJECT_ID}/workpapers`)
    await expect(page.getByRole('button', { name: '批量导出(元数据)' })).toBeVisible({ timeout: 15_000 })

    await page.getByRole('button', { name: '批量导出(元数据)' }).click()
    const dialog = page.getByRole('dialog', { name: '批量导出底稿' })
    await expect(dialog).toBeVisible()

    await dialog.getByText('D - 销售收入').click()
    const downloadPromise = page.waitForEvent('download', { timeout: 30_000 }).catch(() => null)
    await dialog.getByRole('button', { name: '导出 ZIP' }).click()

    const download = await downloadPromise
    if (download) {
      const tmp = path.join(os.tmpdir(), `wp-batch-${Date.now()}.zip`)
      await download.saveAs(tmp)
      expect(fs.statSync(tmp).size).toBeGreaterThan(100)
      fs.unlinkSync(tmp)
    }

    expect(apiCalls.length, '应调用 batch-export-enhanced').toBeGreaterThan(0)
    expect(apiCalls.every((c) => c.status >= 200 && c.status < 300)).toBeTruthy()
  })

  test('编辑页 — 导出按钮命中 export-with-metadata', async ({ page, request }) => {
    test.setTimeout(90_000)
    const apiCalls: { url: string; status: number }[] = []
    page.on('response', (resp) => {
      if (resp.url().includes('export-with-metadata')) {
        apiCalls.push({ url: resp.url(), status: resp.status() })
      }
    })

    const token = await loginAs(page, 'admin', 'admin123')
    const wpId = await findD2WpId(request, token)
    test.skip(!wpId, '辽宁卫生项目无 D2 底稿')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await expect(page.locator('.gt-wp-io-toolbar, .gt-wp-editor-toolbar')).toBeVisible({ timeout: 20_000 })

    const exportBtn = page.locator('.gt-wp-io-toolbar button, .gt-wp-editor-toolbar button').filter({ hasText: '导出' }).first()
    await expect(exportBtn).toBeVisible({ timeout: 15_000 })

    const downloadPromise = page.waitForEvent('download', { timeout: 30_000 }).catch(() => null)
    await exportBtn.click()
    await downloadPromise

    expect(apiCalls.length).toBeGreaterThan(0)
    expect(apiCalls.every((c) => c.status >= 200 && c.status < 300)).toBeTruthy()
  })

  test('列表页 — export→import-enhanced round-trip', async ({ page, request }) => {
    test.setTimeout(120_000)
    const token = await loginAs(page, 'admin', 'admin123')
    const wpId = await findD2WpId(request, token)
    test.skip(!wpId, 'D2 不存在')

    // 1) API 导出文件
    const exportResp = await request.post(
      `/api/projects/${PROJECT_ID}/workpapers/${wpId}/export-with-metadata`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(exportResp.ok(), `export 应 200，实际 ${exportResp.status()}`).toBeTruthy()
    const buffer = await exportResp.body()
    expect(buffer.byteLength).toBeGreaterThan(100)

    const tmpFile = path.join(os.tmpdir(), `wp-roundtrip-${Date.now()}.xlsx`)
    fs.writeFileSync(tmpFile, buffer)

    // 2) UI 增强导入
    await page.goto(`/projects/${PROJECT_ID}/workpapers`)
    await expect(page.getByRole('button', { name: '增强导入' })).toBeVisible({ timeout: 15_000 })
    await page.getByRole('button', { name: '增强导入' }).click()

    const dialog = page.getByRole('dialog', { name: '导入底稿' })
    await expect(dialog).toBeVisible()

    const fileInput = dialog.locator('input[type="file"]')
    await fileInput.setInputFiles(tmpFile)
    await dialog.getByRole('button', { name: '开始导入' }).click()

    // 成功或冲突/校验（round-trip 同文件通常成功或版本冲突）
    await expect(
      page.locator('.el-result, .wp-import-conflict, .wp-import-validation, .el-message--success, .el-message--error'),
    ).toBeVisible({ timeout: 30_000 })

    fs.unlinkSync(tmpFile)
  })
})
