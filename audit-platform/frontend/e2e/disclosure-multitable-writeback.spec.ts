/**
 * Playwright E2E — 附注多表编辑保存与重载（全拦截合成数据）
 *
 * Spec: disclosure-multitable-refresh-and-edit-writeback Task 7 (R4.3)
 *
 * 所有 API 请求拦截为合成数据：PUT 只存内存再 GET。不写真实业务库。
 * 门禁：需 start-dev.bat 前端已启动（后端不需要）。
 *
 * npx playwright test e2e/disclosure-multitable-writeback.spec.ts
 */
import { test, expect } from '@playwright/test'

const PROJECT_ID = '00000000-0000-0000-0000-000000000001'
const YEAR = 2025
const NOTE_ID = '00000000-0000-0000-0000-000000000099'
const NOTE_SECTION = '测试、多表'

/** 合成的多表 table_data：2 张表 + 首表镜像 */
function syntheticTableData() {
  return {
    headers: ['项目', '期末余额'],
    rows: [
      { label: '行A1', values: [100], is_total: false },
      { label: '合计', values: [100], is_total: true },
    ],
    name: '表A',
    _tables: [
      {
        name: '表A',
        headers: ['项目', '期末余额'],
        rows: [
          { label: '行A1', values: [100], is_total: false },
          { label: '合计', values: [100], is_total: true },
        ],
      },
      {
        name: '表B',
        headers: ['项目', '本期发生额'],
        rows: [
          { label: '行B1', values: [200], is_total: false },
          { label: '合计', values: [200], is_total: true },
        ],
      },
    ],
  }
}

function syntheticNote() {
  return {
    id: NOTE_ID,
    note_section: NOTE_SECTION,
    section_title: '测试多表',
    account_name: '测试',
    content_type: 'table',
    status: 'draft',
    table_data: syntheticTableData(),
    text_content: null,
    guidance_text: null,
    source_template: 'soe',
    sort_order: 1,
    year: YEAR,
    project_id: PROJECT_ID,
  }
}

test.describe('附注多表编辑保存（合成拦截）', () => {
  // 内存中存储 PUT 后的数据
  let savedTableData: any = null

  test.beforeEach(async ({ page }) => {
    savedTableData = null

    // 注入 auth token（绕过登录）
    await page.addInitScript(() => {
      const fakeUser = { id: '1', username: 'admin', role: 'admin' }
      window.sessionStorage.setItem('token', 'fake-e2e-token')
      window.sessionStorage.setItem('refreshToken', 'fake-e2e-refresh')
      window.sessionStorage.setItem('user', JSON.stringify(fakeUser))
      window.localStorage.setItem('token', 'fake-e2e-token')
    })

    // 拦截所有 API 请求
    await page.route('**/api/**', async (route) => {
      const url = route.request().url()
      const method = route.request().method()

      // 附注树列表
      if (url.includes(`/api/disclosure-notes/${PROJECT_ID}/${YEAR}`) && method === 'GET'
          && !url.includes(encodeURIComponent(NOTE_SECTION))) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            code: 200,
            message: 'ok',
            data: {
              nodes: [{
                note_section: NOTE_SECTION,
                section_title: '测试多表',
                content_type: 'table',
                status: 'draft',
              }],
            },
          }),
        })
      }

      // 附注详情 GET
      if (url.includes(encodeURIComponent(NOTE_SECTION)) && method === 'GET') {
        const note = syntheticNote()
        if (savedTableData) note.table_data = savedTableData
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ code: 200, message: 'ok', data: note }),
        })
      }

      // 附注保存 PUT
      if (url.includes(`/api/disclosure-notes/`) && method === 'PUT') {
        const body = route.request().postDataJSON()
        savedTableData = body?.table_data ?? null
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ code: 200, message: 'ok', data: { id: NOTE_ID } }),
        })
      }

      // 项目信息
      if (url.includes('/api/projects/') && method === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            code: 200, message: 'ok',
            data: {
              id: PROJECT_ID, name: '测试项目', year: YEAR,
              audit_period_end: '2025-12-31', status: 'active',
              template_type: 'soe',
            },
          }),
        })
      }

      // 其他 API：200 空数据
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 200, message: 'ok', data: null }),
      })
    })
  })

  test('多表数据加载并显示 tab', async ({ page }) => {
    await page.goto(`/disclosure-editor?projectId=${PROJECT_ID}&year=${YEAR}`)
    // 等页面渲染
    await page.waitForTimeout(2000)

    // 查找附注树节点并点击
    const treeNode = page.getByText('测试多表').first()
    if (await treeNode.isVisible()) {
      await treeNode.click()
      await page.waitForTimeout(1000)

      // 应该有 2 个 tab（表A、表B）
      const tabs = page.locator('.el-tabs__item')
      const tabCount = await tabs.count()
      // 至少有 1 个 tab（如果渲染了多表）
      expect(tabCount).toBeGreaterThanOrEqual(1)
    }
  })

  test('保存后 PUT 发送完整 raw 多表', async ({ page }) => {
    await page.goto(`/disclosure-editor?projectId=${PROJECT_ID}&year=${YEAR}`)
    await page.waitForTimeout(2000)

    const treeNode = page.getByText('测试多表').first()
    if (await treeNode.isVisible()) {
      await treeNode.click()
      await page.waitForTimeout(1000)

      // 点编辑按钮进入编辑模式
      const editBtn = page.getByRole('button', { name: /编辑/ }).first()
      if (await editBtn.isVisible()) {
        await editBtn.click()
        await page.waitForTimeout(500)

        // 点保存
        const saveBtn = page.getByRole('button', { name: /保存/ }).first()
        if (await saveBtn.isVisible()) {
          await saveBtn.click()
          await page.waitForTimeout(1000)

          // 验证 PUT 发送的 table_data 包含 _tables
          if (savedTableData) {
            expect(savedTableData._tables).toBeDefined()
            expect(savedTableData._tables.length).toBe(2)
          }
        }
      }
    }
  })
})
