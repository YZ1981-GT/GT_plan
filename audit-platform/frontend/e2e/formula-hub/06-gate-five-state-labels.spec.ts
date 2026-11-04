/**
 * 浏览器检查 ⑥ — 门禁五态（不能把「没数据」当「通过」）
 *
 * `GET /api/projects/{pid}/qc/vr-heatmap`：D~N 十一个循环，每行与汇总都给五态计数
 * （passed / failed / not_executed / not_applicable / error）。种子项目没有任何四表数据 ⇒ 一条都不能是「通过」，
 * 全部记「未执行」；质控看板的风险热力图按中文标签显示。原用例打不存在的 `/consistency-gate`（404 即通过），
 * 五态集合也写错了（unavailable / warning），界面部分打开交付中心只看标题非空。
 */
import { test, expect } from '@playwright/test'
import { api, apiToken, loginAndInstall, standaloneProjectId } from './helpers'

const FIVE_STATES = ['error', 'failed', 'not_applicable', 'not_executed', 'passed']
const CYCLES = ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N']

test.describe('门禁五态', () => {
  test('空项目：每个循环五态齐全、没有一条「通过」，汇总等于各行之和', async ({ request }) => {
    const token = await apiToken(request)
    const r = await api(request, token, 'GET', `/api/projects/${standaloneProjectId()}/qc/vr-heatmap`)
    expect(r.status).toBe(200)
    expect((r.data.matrix as any[]).map((row) => row.cycle)).toEqual(CYCLES)
    const sum: Record<string, number> = Object.fromEntries(FIVE_STATES.map((s) => [s, 0]))
    for (const row of r.data.matrix as any[]) {
      expect(Object.keys(row.status_counts).sort(), `循环 ${row.cycle}`).toEqual(FIVE_STATES)
      expect(row.status_counts.passed, `循环 ${row.cycle} 没数据却记了通过`).toBe(0)
      for (const s of FIVE_STATES) sum[s] += row.status_counts[s]
    }
    expect(r.data.status_counts).toEqual(sum)
    expect(sum.not_executed, '没数据的检查应记「未执行」').toBeGreaterThan(0)
  })

  test('质控看板风险热力图：显示「未执行（数据缺失）」而不是通过', async ({ page, request }) => {
    await loginAndInstall(page, request)
    await page.goto(`/projects/${standaloneProjectId()}/qc-dashboard`)
    await expect(page).not.toHaveURL(/\/login/)
    await page.getByRole('tab', { name: '风险热力图' }).click()
    await expect(page.getByText('未执行（数据缺失）').first()).toBeVisible({ timeout: 20_000 })
  })
})
