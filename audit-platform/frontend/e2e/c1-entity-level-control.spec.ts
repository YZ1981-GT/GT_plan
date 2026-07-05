/**
 * c1-entity-level-control.spec.ts — C1 企业层面控制测试专属组件 E2E 实测
 *
 * Spec: .kiro/specs/c1-entity-level-control/  Task 6.2
 * Validates: Requirements 2.3, 3.1, 4.3, 8.1
 *
 * 打开 C1 → 九段折叠切换 → 适用性裁剪（标记不适用 + 理由）→ C1-4-4 过程记录
 * 样本填写（借贷勾稽实时重算）→ 只读模式说明。
 *
 * 依赖真实 dev 环境（backend 9980 + frontend 3030）。
 * 项目动态发现：查任一「未软删 + 含 C1 底稿 + render-config 命中 c1-entity-level-control」
 * 的项目（默认 e2e fixture 37814426 已软删，故不硬编码）。
 *
 * 说明（Req 8.1 只读）：WorkpaperEditor 的 HTML 渲染器路由未向 GtWpRenderer 透传
 * readonly（editor 未绑定 :readonly），故只读禁编辑无法经真实编辑器路由触达。
 * 只读行为由 vitest 组件/属性测试覆盖：
 *   - GtC1EntityControl.spec.ts（Task 4.2 readonly 用例）
 *   - useC1ControlProperties.pbt.spec.ts（Property 6: readonly 禁编辑）
 * 本 e2e 覆盖真实应用可触达的三条交互链路。
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'

async function getToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  return body.data?.access_token ?? body.access_token ?? ''
}

async function injectToken(page: Page, token: string) {
  await page.addInitScript((t: string) => {
    window.sessionStorage.setItem('token', t)
    window.localStorage.setItem('token', t)
  }, token)
}

interface C1Target {
  projectId: string
  wpId: string
}

/**
 * 发现一个可用的 C1 底稿：项目未软删 + 含 wp_code=C1 + render-config 各 sheet
 * 命中 componentType=c1-entity-level-control。找不到返回 null（测试 skip）。
 */
async function discoverC1(request: APIRequestContext, token: string): Promise<C1Target | null> {
  const headers = { Authorization: `Bearer ${token}` }
  const projResp = await request.get('/api/projects', { headers })
  if (projResp.status() !== 200) return null
  const projBody = await projResp.json()
  const projects: any[] = projBody?.data?.items || projBody?.data || projBody?.items || []
  for (const p of projects) {
    if (p.is_deleted) continue
    const pid = p.id
    if (!pid) continue
    const wpResp = await request.get(`/api/projects/${pid}/working-papers`, { headers })
    if (wpResp.status() !== 200) continue
    const wpBody = await wpResp.json()
    const list: any[] = wpBody?.data?.items || wpBody?.data || wpBody?.items || []
    const c1 = list.find((w) => w.wp_code === 'C1')
    if (!c1?.id) continue
    // 确认 render-config 命中专属组件
    const rc = await request.get(`/api/workpapers/${c1.id}/render-config`, { headers })
    if (rc.status() !== 200) continue
    const rcBody = await rc.json()
    const d = rcBody?.data ?? rcBody
    const sheets: any[] = d?.sheets || []
    const hit = sheets.some((s) => s.componentType === 'c1-entity-level-control')
    if (hit) return { projectId: pid, wpId: c1.id }
  }
  return null
}

let target: C1Target | null = null

test.beforeAll(async ({ request }) => {
  const token = await getToken(request)
  if (!token) return
  target = await discoverC1(request, token)
})

async function openC1(page: Page, request: APIRequestContext) {
  const token = await getToken(request)
  await injectToken(page, token)
  await page.goto(`/projects/${target!.projectId}/workpapers/${target!.wpId}/edit`)
  // 等待专属组件挂载
  await page.waitForSelector('.c1-entity-control', { timeout: 20_000 })
  // 无渲染配置失败
  await expect(page.locator('body')).not.toContainText('加载渲染配置失败')
}

test.describe('C1 企业层面控制测试专属组件 E2E（Task 6.2）', () => {
  // 三条链路对同一 C1 底稿读写，串行执行避免共享后端数据竞态
  test.describe.configure({ mode: 'serial' })

  test('6.2.1 — 打开 C1 → 九段分组程序中控台渲染 + 折叠切换（Req 2.3）', async ({ page, request }) => {
    test.setTimeout(60_000)
    test.skip(!target, '未发现可用 C1 底稿（项目未软删 + render-config 命中 c1-entity-level-control）')

    const pageErrors: string[] = []
    page.on('pageerror', (e) => pageErrors.push(e.message))

    await openC1(page, request)

    // 程序模式 + 九段折叠面板
    await expect(page.locator('.c1-program')).toBeVisible()
    const items = page.locator('.c1-section-nav .el-collapse-item')
    await expect(items).toHaveCount(9)

    // 九段标题齐全（源模板九段，Phase0 实测）
    const titles = await page.locator('.c1-sec-title').allInnerTexts()
    const joined = titles.join(' ')
    for (const t of ['控制环境', '风险评估', '监督', '监控业务单元', '信息与沟通', '财务报告', '对业务层面控制的影响', '年终程序', '关联方相关内容']) {
      expect(joined, `九段应含「${t}」`).toContain(t)
    }

    // 各段有完成进度条 + 适用性开关
    await expect(page.locator('.c1-sec-progress')).toHaveCount(9)
    await expect(page.locator('.c1-sec-applicable .el-switch')).toHaveCount(9)

    // 折叠切换：点击首段标题切换展开态（el-collapse header 可点）
    const firstHeader = page.locator('.c1-section-nav .el-collapse-item .el-collapse-item__header').first()
    const before = await firstHeader.getAttribute('class')
    await firstHeader.click()
    await page.waitForTimeout(400)
    const after = await firstHeader.getAttribute('class')
    expect(before !== after, '点击段标题应切换展开/收起态').toBeTruthy()

    // 全链路不崩
    expect(pageErrors, `页面异常:\n${pageErrors.join('\n')}`).toHaveLength(0)
  })

  test('6.2.2 — 适用性裁剪：标记不适用需填理由 → 段呈现裁剪态（Req 3.1）', async ({ page, request }) => {
    test.setTimeout(60_000)
    test.skip(!target, '未发现可用 C1 底稿')

    await openC1(page, request)

    // 选末段（关联方相关内容）的适用性开关
    const lastSwitch = page.locator('.c1-section-nav .el-collapse-item').last().locator('.c1-sec-applicable .el-switch')
    // 自愈：若上次运行已裁剪（开关 off），先恢复为适用（切 on 不弹框），确保本次点击是「适用→不适用」触发理由 prompt
    if (!(await lastSwitch.evaluate((el) => el.classList.contains('is-checked')))) {
      await lastSwitch.click()
      await page.waitForTimeout(500)
    }
    // 点击 → 适用转不适用 → 弹出理由 prompt
    await lastSwitch.click()

    // ElMessageBox prompt 出现（标记不适用 + 必填理由）
    const box = page.locator('.el-message-box')
    await expect(box).toBeVisible({ timeout: 5_000 })
    await expect(box.locator('.el-message-box__title')).toContainText('标记不适用')
    await expect(box).toContainText('不适用')

    // 填理由 + 确定
    await box.locator('input, textarea').first().fill('本项目无关联方交易')
    await box.locator('.el-message-box__btns button.el-button--primary').click()

    // 段呈现裁剪态 + 理由回显（Req 3.3 不参与进度统计）
    const lastItem = page.locator('.c1-section-nav .el-collapse-item').last()
    await expect(lastItem.locator('.c1-sec-trimmed')).toBeVisible({ timeout: 5_000 })
    await expect(lastItem.locator('.c1-sec-trimmed')).toContainText('本段已标记「不适用」')
    await expect(lastItem.locator('.c1-sec-trimmed')).toContainText('本项目无关联方交易')

    // 刷新后仍保持裁剪态（即时保存到 checklist-responses，Req 3.4）
    await page.reload()
    await page.waitForSelector('.c1-entity-control', { timeout: 20_000 })
    const lastItem2 = page.locator('.c1-section-nav .el-collapse-item').last()
    await expect(lastItem2.locator('.c1-sec-trimmed')).toContainText('本项目无关联方交易', { timeout: 10_000 })
  })

  test('6.2.3 — C1-4-4 过程记录样本填写 → 借贷勾稽实时重算（Req 4.3）', async ({ page, request }) => {
    test.setTimeout(60_000)
    test.skip(!target, '未发现可用 C1 底稿')

    await openC1(page, request)

    // 切换到 C1-4-4 sheet（会计分录人工授权测试样本表）
    await page.locator('.gt-wp-renderer__tab-name', { hasText: 'C1-4-4' }).first().click()
    await expect(page.locator('.c1-process-sample')).toBeVisible({ timeout: 10_000 })
    await expect(page.locator('.c1-sample-table')).toBeVisible()

    // 数据行（含借方输入的 tr，排除空占位行）
    const dataRows = page.locator('.c1-sample-table tbody tr', {
      has: page.locator('input[placeholder="借方"]'),
    })
    // 自愈：清空历史样本行（上次运行遗留），确保勾稽合计断言确定性
    let guard = 0
    while ((await dataRows.count()) > 0 && guard < 30) {
      await page.locator('.c1-sample-table tbody tr').first().getByRole('button', { name: '删除' }).click()
      await page.waitForTimeout(150)
      guard++
    }
    await expect(dataRows).toHaveCount(0)

    // 新增两行样本
    const addBtn = page.getByRole('button', { name: /新增样本行/ })
    await addBtn.click()
    await addBtn.click()
    const rows = dataRows
    await expect(rows).toHaveCount(2)

    // 行0 借方 250、行1 贷方 250（借方镜像贷方勾稽，Phase0 §4）
    await rows.nth(0).locator('input[placeholder="借方"]').fill('250')
    await rows.nth(1).locator('input[placeholder="贷方"]').fill('250')

    // tfoot 借贷勾稽只读派生：Σ借方=Σ贷方 → 借贷平衡（Req 4.4 实时重算）
    const foot = page.locator('.c1-sample-foot')
    await expect(foot).toBeVisible()
    await expect(foot).toContainText('借贷平衡')
    await expect(foot).toContainText('250.00')

    // 改行1贷方 → 借贷不平（重算方向可逆）
    await rows.nth(1).locator('input[placeholder="贷方"]').fill('100')
    await expect(foot).toContainText('借贷不平')
  })
})
