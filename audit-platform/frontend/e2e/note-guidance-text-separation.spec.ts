/**
 * UAT — 附注 guidance_text 提示条 + Word 导出不含指引
 *
 * Feature: note-guidance-text-separation, Task 11.1
 *
 * 门禁：需显式开启 RUN_GUIDANCE_E2E=1 且 start-dev.bat 已启动。
 *   set RUN_GUIDANCE_E2E=1 && npx playwright test e2e/note-guidance-text-separation.spec.ts
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import mammoth from 'mammoth'

const _env = ((globalThis as any).process?.env ?? {}) as Record<string, string | undefined>
const RUN_GUIDANCE_E2E = _env.RUN_GUIDANCE_E2E === '1'

const PROJECTS = [
  { id: '37814426-a29e-4fc2-9313-a59d229bf7b0', label: '辽宁卫生' },
  { id: '5942c12e-65fb-4187-ace3-79d45a90cb53', label: '和平药房' },
]
const YEAR = Number(_env.GUIDANCE_E2E_YEAR || '2025')
const BACKEND = _env.GUIDANCE_E2E_BACKEND || 'http://localhost:9980'

async function loginAs(page: Page) {
  const resp = await page.request.post(`${BACKEND}/api/auth/login`, {
    data: { username: 'admin', password: 'admin123' },
  })
  if (!resp.ok()) {
    test.skip(true, `登录失败 ${resp.status()} — 请确认后端已启动`)
  }
  const body = await resp.json()
  const payload = body.data ?? body
  const token = payload.access_token
  const refreshToken = payload.refresh_token ?? ''
  const user = payload.user ?? null
  // auth store 用 sessionStorage 读 token/refreshToken/user（见 stores/auth.ts）；
  // 仅塞 token 不够——路由守卫读 user，缺失会被重定向登录页导致超时。
  await page.addInitScript(
    (args: { t: string; r: string; u: unknown }) => {
      window.sessionStorage.setItem('token', args.t)
      if (args.r) window.sessionStorage.setItem('refreshToken', args.r)
      if (args.u) window.sessionStorage.setItem('user', JSON.stringify(args.u))
      // 兼容仍读 localStorage.token 的旧路径（collaboration store / webVitals）
      window.localStorage.setItem('token', args.t)
    },
    { t: token, r: refreshToken, u: user },
  )
  return token as string
}

async function findNoteWithGuidance(request: APIRequestContext, token: string, projectId: string) {
  const treeResp = await request.get(
    `${BACKEND}/api/disclosure-notes/${projectId}/${YEAR}`,
    { headers: { Authorization: `Bearer ${token}` } },
  )
  if (!treeResp.ok()) return null
  const treeBody = await treeResp.json()
  const nodes = treeBody.data?.nodes ?? treeBody.nodes ?? treeBody.data ?? []

  async function walk(items: any[]): Promise<{ note_section: string; guidance_text: string } | null> {
    for (const n of items) {
      if (n.note_section) {
        const detailResp = await request.get(
          `${BACKEND}/api/disclosure-notes/${projectId}/${YEAR}/${encodeURIComponent(n.note_section)}`,
          { headers: { Authorization: `Bearer ${token}` } },
        )
        if (detailResp.ok()) {
          const detail = await detailResp.json()
          const data = detail.data ?? detail
          if (data.guidance_text?.trim()) {
            return { note_section: n.note_section, guidance_text: data.guidance_text }
          }
        }
      }
      if (n.children?.length) {
        const found = await walk(n.children)
        if (found) return found
      }
    }
    return null
  }
  return walk(nodes)
}

test.describe('note-guidance-text-separation E2E', () => {
  test.skip(!RUN_GUIDANCE_E2E, '需 RUN_GUIDANCE_E2E=1')

  for (const proj of PROJECTS) {
    test(`${proj.label}: 编辑器展示 GT 紫提示条且 Word 不含 guidance`, async ({ page, request }) => {
      test.setTimeout(120_000)  // 树叶遍历可能较多，放宽超时
      const token = await loginAs(page)
      const hit = await findNoteWithGuidance(request, token, proj.id)
      test.skip(!hit, `${proj.label} 无 guidance_text 章节 — 请先跑 preview/execute 拆分`)

      await page.goto(`/projects/${proj.id}/disclosure-notes?year=${YEAR}`)
      // 注：不能用 waitForLoadState('networkidle') —— 应用有 SSE 协作长连接，
      // networkidle 永不触发会超时。改等附注树节点出现。
      await page.waitForLoadState('domcontentloaded')
      // 树节点用 treeitem role（非 .el-tree-node__label）；等树渲染
      await page.getByRole('treeitem').first().waitFor({ state: 'visible', timeout: 15000 })

      // note_section → 树叶节点文本无可靠 1:1 映射（树叶可能是去前缀短标题）。
      // 已知该项目存在 guidance 章节（findNoteWithGuidance 命中），策略：
      // 逐个展开顶层 treeitem 并点击叶子，直到 .gt-guidance-bar 出现。
      const bar = page.locator('.gt-guidance-bar')
      let barFound = false
      const topItems = page.getByRole('treeitem')
      const topCount = await topItems.count()
      for (let i = 0; i < topCount && !barFound; i++) {
        const item = topItems.nth(i)
        try {
          await item.click({ timeout: 3000 })
          await page.waitForTimeout(400)
        } catch { continue }
        // 点击后可能展开出叶子；点当前所有可见 treeitem 的叶子文本
        if (await bar.isVisible().catch(() => false)) { barFound = true; break }
      }
      // 若顶层点击未直接命中，遍历全部（含展开后的）叶子节点
      if (!barFound) {
        const all = page.getByRole('treeitem')
        const n = await all.count()
        for (let i = 0; i < n && !barFound; i++) {
          try {
            await all.nth(i).click({ timeout: 2000 })
            await page.waitForTimeout(300)
          } catch { continue }
          if (await bar.isVisible().catch(() => false)) barFound = true
        }
      }

      await expect(bar, '未找到 GT 紫指引提示条').toBeVisible({ timeout: 10000 })

      const exportResp = await request.post(
        `${BACKEND}/api/disclosure-notes/${proj.id}/${YEAR}/export-word`,
        {
          headers: { Authorization: `Bearer ${token}` },
          data: { skip_empty: true, template_type: 'soe' },
        },
      )
      expect(exportResp.ok(), `Word 导出失败 ${exportResp.status()}`).toBeTruthy()
      const buf = Buffer.from(await exportResp.body())
      const { value: docText } = await mammoth.extractRawText({ buffer: buf })
      expect(docText).not.toContain(hit!.guidance_text.trim())
    })
  }
})
