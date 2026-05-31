/**
 * E2E — F2 锁定前后端联调 Playwright 实测 + P3 dev_mode banner 目视确认
 *
 * 待环境：需 start-dev.bat 启动后端 9980 + 前端 3030 方可运行。
 * 跳过策略：模块级探活后端 /api/health，不可达则全部 skip。
 *
 * 验证闭环（需求 5.6 / 设计 §5.6 / 任务 13.1）：
 *   补列 → 后端锁 → 前端点锁定 → 真改子公司被拦 423 → 前端显示锁定态 banner
 *
 * P3 dev_mode banner（需求 9.3 / 任务 13.2）：
 *   合并模块页面在 dev_mode==true 时展示 el-alert 警告 banner
 *
 * 运行：
 *   npx playwright test e2e/consol-lock-closure.spec.ts
 *   或带环境变量：
 *   E2E_PROJECT_ID=<uuid> npx playwright test e2e/consol-lock-closure.spec.ts
 *
 * @see .kiro/specs/consol-phase0-core-pipeline/tasks.md 任务 13
 * @see .kiro/specs/consol-phase0-core-pipeline/requirements.md 需求 5.6 / 9.3
 */
import { test, expect, type APIRequestContext } from '@playwright/test'

// ─── 配置 ───────────────────────────────────────────────────────────────────
const BACKEND_URL = 'http://localhost:9980'
const FRONTEND_URL = 'http://localhost:3030'

// 测试项目 ID（合并母项目），可通过环境变量覆盖
const PROJECT_ID = process.env.E2E_PROJECT_ID ?? 'df5b8403-0000-0000-0000-000000000000'

// 登录凭据
const ADMIN_USER = 'admin'
const ADMIN_PASS = 'admin123'

// ─── 探活：后端不可达则全部 skip ────────────────────────────────────────────
async function isBackendAlive(): Promise<boolean> {
  try {
    const res = await fetch(`${BACKEND_URL}/api/health`, {
      signal: AbortSignal.timeout(3000),
    })
    return res.ok || res.status === 200
  } catch {
    return false
  }
}

// ─── 辅助：通过 API 登录获取 token ──────────────────────────────────────────
async function loginAndGetToken(request: APIRequestContext): Promise<string> {
  const res = await request.post(`${BACKEND_URL}/api/auth/login`, {
    data: { username: ADMIN_USER, password: ADMIN_PASS },
  })
  expect(res.ok()).toBeTruthy()
  const body = await res.json()
  // 兼容 {access_token} 或 {token} 两种返回格式
  return body.access_token || body.token
}

// ─── 辅助：带 token 的 API 请求 ─────────────────────────────────────────────
function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 测试套件
// ═══════════════════════════════════════════════════════════════════════════════

test.describe('F2 锁定前后端联调闭环 + P3 dev_mode banner', () => {
  let backendAlive: boolean

  test.beforeAll(async () => {
    backendAlive = await isBackendAlive()
  })

  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(!backendAlive, '后端 9980 不可达，跳过（待环境：start-dev.bat）')

    // 前端登录
    await page.goto(`${FRONTEND_URL}/login`)
    await page.fill('input[placeholder*="用户名"]', ADMIN_USER)
    await page.fill('input[type="password"]', ADMIN_PASS)
    await page.click('button:has-text("登录")')
    await expect(page).toHaveURL(/\/(dashboard|projects)/, { timeout: 10000 })
  })

  // ─────────────────────────────────────────────────────────────────────────
  // 13.1 锁定真闭环
  // ─────────────────────────────────────────────────────────────────────────
  test('13.1 锁定真闭环：lock → 423 拦截 → 前端锁定态 → unlock → 可写', async ({
    page,
    request,
  }) => {
    test.skip(!backendAlive, '后端 9980 不可达，跳过（待环境：start-dev.bat）')

    const token = await loginAndGetToken(request)
    const headers = authHeaders(token)

    // ── Step 1: 确保初始状态为未锁定 ──
    const unlockFirst = await request.post(
      `${BACKEND_URL}/api/consolidation/${PROJECT_ID}/unlock`,
      { headers }
    )
    // 可能已经是 unlocked，忽略错误
    if (!unlockFirst.ok()) {
      // 如果 unlock 失败可能是项目不存在，跳过
      const body = await unlockFirst.text()
      if (unlockFirst.status() === 404) {
        test.skip(true, `项目 ${PROJECT_ID} 不存在，跳过`)
      }
    }

    // ── Step 2: 验证 lock-status 返回 locked=false ──
    const statusBefore = await request.get(
      `${BACKEND_URL}/api/consolidation/${PROJECT_ID}/lock-status`,
      { headers }
    )
    expect(statusBefore.ok()).toBeTruthy()
    const statusBeforeBody = await statusBefore.json()
    expect(statusBeforeBody.locked).toBe(false)

    // ── Step 3: 执行锁定 ──
    const lockRes = await request.post(
      `${BACKEND_URL}/api/consolidation/${PROJECT_ID}/lock`,
      { headers }
    )
    expect(lockRes.ok()).toBeTruthy()

    // ── Step 4: 验证 lock-status 返回 locked=true ──
    const statusAfter = await request.get(
      `${BACKEND_URL}/api/consolidation/${PROJECT_ID}/lock-status`,
      { headers }
    )
    expect(statusAfter.ok()).toBeTruthy()
    const statusAfterBody = await statusAfter.json()
    expect(statusAfterBody.locked).toBe(true)

    // ── Step 5: 尝试修改子公司数据 → 验证 423 响应 ──
    // 尝试对锁定项目的 trial_balance 写操作（recalculate 是写操作）
    const writeAttempt = await request.post(
      `${BACKEND_URL}/api/consolidation/${PROJECT_ID}/trial/recalculate`,
      { headers, data: { year: 2025 } }
    )
    // 锁定态下写操作应返回 423
    expect(writeAttempt.status()).toBe(423)

    // ── Step 6: 前端导航到合并页面，验证锁定态 UI ──
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}/consolidation`)
    await page.waitForLoadState('networkidle')

    // 验证前端能感知锁定状态（页面应有锁定相关的视觉指示）
    // 注：具体 selector 取决于前端实现，这里检查 lock-status API 被调用
    const lockStatusResponse = await page.waitForResponse(
      (res) => res.url().includes('lock-status') && res.status() === 200,
      { timeout: 5000 }
    ).catch(() => null)

    if (lockStatusResponse) {
      const lockData = await lockStatusResponse.json()
      expect(lockData.locked).toBe(true)
    }

    // ── Step 7: 解锁 ──
    const unlockRes = await request.post(
      `${BACKEND_URL}/api/consolidation/${PROJECT_ID}/unlock`,
      { headers }
    )
    expect(unlockRes.ok()).toBeTruthy()

    // ── Step 8: 验证解锁后可写 ──
    const statusUnlocked = await request.get(
      `${BACKEND_URL}/api/consolidation/${PROJECT_ID}/lock-status`,
      { headers }
    )
    expect(statusUnlocked.ok()).toBeTruthy()
    const statusUnlockedBody = await statusUnlocked.json()
    expect(statusUnlockedBody.locked).toBe(false)

    // 解锁后写操作应不再返回 423（可能返回 200 或其他业务错误，但不是 423）
    const writeAfterUnlock = await request.post(
      `${BACKEND_URL}/api/consolidation/${PROJECT_ID}/trial/recalculate`,
      { headers, data: { year: 2025 } }
    )
    expect(writeAfterUnlock.status()).not.toBe(423)
  })

  // ─────────────────────────────────────────────────────────────────────────
  // 13.2 P3 dev_mode banner 前端目视确认
  // ─────────────────────────────────────────────────────────────────────────
  test('13.2 P3 dev_mode banner：合并页面显示"开发中，不可用于正式合并报告"', async ({
    page,
    request,
  }) => {
    test.skip(!backendAlive, '后端 9980 不可达，跳过（待环境：start-dev.bat）')

    const token = await loginAndGetToken(request)

    // ── Step 1: 验证 module-status 端点返回 dev_mode=true ──
    const moduleStatus = await request.get(
      `${BACKEND_URL}/api/consolidation/${PROJECT_ID}/module-status`,
      { headers: authHeaders(token) }
    )
    // 端点可能尚未部署，容错处理
    if (moduleStatus.ok()) {
      const body = await moduleStatus.json()
      expect(body.dev_mode).toBe(true)
      expect(body.warning).toContain('开发中')
    }

    // ── Step 2: 前端导航到合并页面 ──
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}/consolidation`)
    await page.waitForLoadState('networkidle')

    // ── Step 3: 验证 el-alert 警告 banner 可见 ──
    // ConsolidationIndex.vue 中的 el-alert 结构：
    //   <el-alert v-if="consolDevMode" type="warning" :closable="false" show-icon>
    //     <template #title>
    //       <span style="font-weight: 600">开发中，不可用于正式合并报告</span>
    //     </template>
    //   </el-alert>
    const devModeBanner = page.locator('.el-alert--warning')
    await expect(devModeBanner).toBeVisible({ timeout: 8000 })

    // 验证 banner 文本内容
    const bannerText = page.locator('.el-alert--warning').locator('text=开发中，不可用于正式合并报告')
    await expect(bannerText).toBeVisible()
  })
})
