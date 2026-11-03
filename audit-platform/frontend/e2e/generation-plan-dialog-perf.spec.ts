/**
 * 生成计划弹窗明细性能裁决（spec trim-generation-plan-followup-optimizations R6）。
 *
 * 全 mock：只打开 e2e/perf-harness 夹具页（Vite 开发服务提供），模板集 / 生成计划接口由页面路由应答，不连后端与数据库。
 * 夹具：B 循环 141（发布硬门）/ 250 / 500 / 1025 项 × 「单组」「每项一组」，桌面 1440×900 与窄屏 390×844 分开报告。
 * 每档：冷态 5 次（每次新开页面后的首次展开）+ 热态 20 次（同页收起再展开），量 click→两帧 RAF、>50ms Long Task、
 * DOM 节点数，展开后 120 帧滚动的平均 FPS 与 p95 帧时长；每次都断言真实渲染项数 = N、展开明细只有 1 个（不空跑）。
 * 141 档硬门（requirements 6.3）：展开 p95 ≤ 200ms、max ≤ 300ms、无 >100ms Long Task、平均滚动 ≥ 30 FPS、p95 帧 ≤ 33.3ms。
 * 压力档（GT_PERF_STRESS=1 才跑）只输出曲线。结果写 test-results/perf/generation-plan-dialog-<GT_PERF_ROUND>.json。
 *
 * 运行：node node_modules/@playwright/test/cli.js test --config=playwright.perf.config.ts（workers=1、retries=0）
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test, type Page } from '@playwright/test'

const BASE = process.env.GT_PERF_BASE_URL || 'http://127.0.0.1:3030'
const HARNESS = `${BASE}/e2e/perf-harness/generation-plan-dialog.html`
const ROUND = process.env.GT_PERF_ROUND || 'adhoc'
const TIERS = process.env.GT_PERF_STRESS === '1' ? [141, 250, 500, 1025] : [141]
const SHAPES = ['single', 'per-item'] as const
const VIEWPORTS = { desktop: { width: 1440, height: 900 }, narrow: { width: 390, height: 844 } } as const
const COLD_SAMPLES = 5
const WARM_SAMPLES = 20
const SCROLL_FRAMES = 120
const GATE = { p95: 200, max: 300, longTask: 100, fps: 30, frameP95: 33.3 }
const CYCLE_LABEL = 'B 初步业务'
const OUT_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'test-results', 'perf')
const PLAN_API = 'GET /api/projects/00000000-0000-4000-8000-0000000000aa/procedure-scope/generation-plan'
// 打开弹窗只读：原先先 POST /api/template-sets/seed（spec trim-followup-residual-findings-closure R2 去掉）
const EXPECTED_API = new Set(['GET /api/template-sets', PLAN_API])

type Shape = (typeof SHAPES)[number]
const STATES = ['to_create', 'to_create', 'to_create', 'existing', 'trimmed', 'in_recycle', 'category_excluded'] as const

function counts(items: Array<{ state: string }>) {
  const n = (s: string) => items.filter((it) => it.state === s).length
  return { total: items.length, to_create: n('to_create'), existing: n('existing'), in_recycle: n('in_recycle'),
    trimmed: n('trimmed'), category_excluded: n('category_excluded') }
}

function cycleOf(cycle: string, n: number, shape: Shape, confirmed: boolean) {
  const programs = shape === 'single'
    ? [{ code: `${cycle}1`, name: '了解被审计单位及其环境', status: 'execute', skip_reason: null, origin: 'catalog' }]
    : Array.from({ length: n }, (_, i) => ({ code: `${cycle}${i + 1}`, name: `程序 ${i + 1}`,
      status: i % 9 === 0 ? 'skip' : 'execute', skip_reason: null, origin: 'catalog' }))
  const items = Array.from({ length: n }, (_, i) => ({
    wp_code: `${cycle}${String(i + 1).padStart(4, '0')}`,
    wp_name: `底稿 ${i + 1} 名称（用于测量换行与省略的较长文字）`,
    state: STATES[i % STATES.length],
    decided_by: shape === 'single' ? `${cycle}1` : `${cycle}${i + 1}`,
    follows_children: false, category_applicable: true, category_reason: null, category_conflict: false,
  }))
  return { cycle, trim_state: confirmed ? 'confirmed' : 'unconfirmed', confirmed_at: confirmed ? '2026-10-28T08:00:00Z' : null,
    confirmed_by: confirmed ? '性能夹具' : null, counts: counts(items), programs, items }
}

function buildPlan(n: number, shape: Shape) {
  const cycles = [cycleOf('B', n, shape, true), cycleOf('D', 3, 'single', false), cycleOf('E', 3, 'single', true)]
  return { template_set: { id: 'set-std', set_name: '标准年审', code_count: n + 6 }, business_category: { code: 'C', defaulted: false },
    totals: counts(cycles.flatMap((c) => c.items)), cycles }
}

async function mockApi(page: Page, plan: unknown, calls: string[]): Promise<void> {
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const { pathname } = new URL(request.url())
    calls.push(`${request.method()} ${pathname}`)
    let data: unknown = null
    if (pathname === '/api/template-sets') {
      data = [{ id: 'set-std', set_name: '标准年审', template_codes: [], applicable_audit_type: null,
        applicable_standard: null, description: null }]
    } else if (pathname.endsWith('/procedure-scope/generation-plan')) {
      data = plan
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 200, message: 'success', data }) })
  })
}

async function openHarness(page: Page, plan: unknown, calls: string[]): Promise<void> {
  await page.addInitScript(() => {
    const w = window as unknown as {
      __longTasks: Array<{ start: number; duration: number }>
      __expandTiming: { t0: number; ms: number } | null
    }
    w.__longTasks = []
    w.__expandTiming = null
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) w.__longTasks.push({ start: entry.startTime, duration: entry.duration })
    }).observe({ type: 'longtask', buffered: true })
    // 捕获阶段先于按钮自己的处理函数：此时登记的两帧 RAF 一定落在 Vue 本次刷新之后
    document.addEventListener('click', (event) => {
      const target = event.target as Element | null
      if (!target?.closest?.('button[aria-label^="展开"][aria-label$="明细"]')) return
      const t0 = event.timeStamp
      requestAnimationFrame(() => requestAnimationFrame(() => {
        w.__expandTiming = { t0, ms: performance.now() - t0 }
      }))
    }, true)
  })
  await mockApi(page, plan, calls)
  await page.goto(HARNESS)
  await page.getByRole('button', { name: `展开${CYCLE_LABEL}明细` }).waitFor({ state: 'visible', timeout: 30_000 })
  await page.waitForTimeout(300) // 让打开弹窗的过渡与首屏布局结束，不算进展开
}

interface ExpandSample { ms: number; longTaskMax: number; items: number; details: number; domNodes: number }

async function expandOnce(page: Page): Promise<ExpandSample> {
  // 🔴 不能在 page.evaluate 里 button.click()：CDP 求值里的同步工作不计入 Long Task（自检实测抓不到 140ms 忙等），
  //    展开时 Vue 的同步渲染会整段漏测。改走真实输入：Playwright 点击 → 浏览器派发事件任务；捕获阶段监听记下事件
  //    创建时刻（event.timeStamp），两帧 RAF 后算「点击 → 两帧」。
  await page.evaluate(() => {
    const w = window as unknown as { __expandTiming: { t0: number; ms: number } | null }
    w.__expandTiming = null
  })
  await page.getByRole('button', { name: `展开${CYCLE_LABEL}明细` }).click()
  await page.waitForFunction(() => (window as unknown as { __expandTiming: unknown }).__expandTiming !== null)
  await page.waitForTimeout(150)
  return page.evaluate(() => {
    const w = window as unknown as {
      __expandTiming: { t0: number; ms: number }
      __longTasks: Array<{ start: number; duration: number }>
    }
    const { t0, ms } = w.__expandTiming
    const overlapping = w.__longTasks.filter((t) => t.start + t.duration >= t0 && t.start <= t0 + ms + 150)
    return {
      ms,
      longTaskMax: Math.max(0, ...overlapping.map((t) => t.duration)),
      items: document.querySelectorAll('.gt-gen-plan__detail .gt-gen-plan__item').length,
      details: document.querySelectorAll('.gt-gen-plan__detail').length,
      domNodes: document.getElementsByTagName('*').length,
    }
  })
}

async function collapse(page: Page): Promise<void> {
  await page.getByRole('button', { name: `收起${CYCLE_LABEL}明细` }).click()
  await expect(page.locator('.gt-gen-plan__detail')).toHaveCount(0)
  await page.waitForTimeout(50)
}

async function scrollFrames(page: Page): Promise<{ fps: number; frameP95: number; frames: number }> {
  return page.evaluate(async (count) => {
    const list = document.querySelector<HTMLElement>('.gt-gen-plan__list')
    if (!list) throw new Error('找不到列表')
    list.scrollTop = 0
    const room = Math.max(1, list.scrollHeight - list.clientHeight)
    const deltas: number[] = []
    await new Promise<void>((resolve) => {
      let last = 0
      let i = 0
      const step = (ts: number) => {
        if (last) deltas.push(ts - last)
        last = ts
        list.scrollTop = Math.round((room * (i % count)) / count)
        if (++i <= count) requestAnimationFrame(step)
        else resolve()
      }
      requestAnimationFrame(step)
    })
    const sorted = [...deltas].sort((a, b) => a - b)
    const mean = deltas.reduce((a, b) => a + b, 0) / deltas.length
    return { fps: 1000 / mean, frameP95: sorted[Math.min(sorted.length - 1, Math.ceil(sorted.length * 0.95) - 1)], frames: deltas.length }
  }, SCROLL_FRAMES)
}

function stats(values: number[]) {
  const sorted = [...values].sort((a, b) => a - b)
  const at = (q: number) => sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * q) - 1))]
  return { n: values.length, median: at(0.5), p95: at(0.95), max: sorted[sorted.length - 1] }
}

// 不用 serial：某一档超门不能让后面的档跳过不测（workers=1 已保证按顺序执行、结果写在同一个文件里）
const results: Record<string, unknown>[] = []

test('自检：同一测量路径能抓到点击处理里 >100ms 的 Long Task 和计时（门不是空转）', async ({ page }) => {
  const calls: string[] = []
  await openHarness(page, buildPlan(3, 'single'), calls)
  // 一个和真实展开按钮同名规则的按钮，处理函数里忙等 140ms：走与 expandOnce 相同的真实点击 + 捕获监听
  await page.evaluate(() => {
    const button = document.createElement('button')
    button.setAttribute('aria-label', '展开自检明细')
    button.textContent = '自检'
    button.addEventListener('click', () => { const t0 = performance.now(); while (performance.now() - t0 < 140) { /* 忙等 */ } })
    // 放进弹窗内容里（弹窗遮罩盖住 body 上的其他元素，真实点击会被遮罩拦下）
    document.querySelector('.gt-gen-plan__toolbar')!.appendChild(button)
    ;(window as unknown as { __expandTiming: unknown }).__expandTiming = null
  })
  await page.getByRole('button', { name: '展开自检明细' }).click()
  await page.waitForFunction(() => (window as unknown as { __expandTiming: unknown }).__expandTiming !== null)
  const timing = await page.evaluate(() => (window as unknown as { __expandTiming: { ms: number } }).__expandTiming)
  expect(timing.ms, '点击 → 两帧计时包含处理函数的忙等').toBeGreaterThanOrEqual(140)
  await expect.poll(() => page.evaluate(() =>
    (window as unknown as { __longTasks: Array<{ duration: number }> }).__longTasks.some((t) => t.duration > 100)),
  ).toBe(true)
})

test.afterAll(() => {
  if (!results.length) return
  mkdirSync(OUT_DIR, { recursive: true })
  writeFileSync(resolve(OUT_DIR, `generation-plan-dialog-${ROUND}.json`),
    JSON.stringify({ round: ROUND, at: new Date().toISOString(), gate: GATE, results }, null, 2), 'utf-8')
})

for (const [viewportName, viewport] of Object.entries(VIEWPORTS)) {
  for (const n of TIERS) {
    for (const shape of SHAPES) {
      test(`${viewportName} ${n} 项 ${shape}`, async ({ browser }) => {
        test.skip(test.info().config.workers !== 1, '性能裁决只在 workers=1 下有效：用 playwright.perf.config.ts 运行')
        test.setTimeout(10 * 60_000)
        const plan = buildPlan(n, shape)
        const context = await browser.newContext({ viewport, deviceScaleFactor: 1, serviceWorkers: 'block' })
        const calls: string[] = []
        const cold: ExpandSample[] = []
        const warm: ExpandSample[] = []
        let scroll = { fps: 0, frameP95: 0, frames: 0 }
        try {
          for (let i = 0; i < COLD_SAMPLES; i++) {
            const page = await context.newPage()
            await openHarness(page, plan, calls)
            cold.push(await expandOnce(page))
            if (i === COLD_SAMPLES - 1) {
              scroll = await scrollFrames(page)
              for (let j = 0; j < WARM_SAMPLES; j++) {
                await collapse(page)
                warm.push(await expandOnce(page))
              }
            }
            await page.close()
          }
        } finally {
          await context.close()
        }
        for (const sample of [...cold, ...warm]) {
          expect(sample.items, '真实渲染的明细项数必须等于夹具项数（不空跑）').toBe(n)
          expect(sample.details, '一次只展开一个循环').toBe(1)
        }
        expect(new Set(calls.filter((c) => !EXPECTED_API.has(c))), '夹具只应调用模板集与生成计划接口').toEqual(new Set())
        expect(calls.filter((c) => !c.startsWith('GET ')), '打开弹窗不发写请求').toEqual([])
        expect(calls).toContain(PLAN_API)
        expect(scroll.frames).toBe(SCROLL_FRAMES)
        const all = [...cold, ...warm]
        const entry = {
          viewport: viewportName, items: n, shape,
          cold: stats(cold.map((s) => s.ms)), warm: stats(warm.map((s) => s.ms)), all: stats(all.map((s) => s.ms)),
          longTaskMax: Math.max(...all.map((s) => s.longTaskMax)), domNodes: Math.max(...all.map((s) => s.domNodes)),
          scroll,
        }
        results.push(entry)
        await test.info().attach('perf.json', { body: JSON.stringify(entry, null, 2), contentType: 'application/json' })
        if (n === 141) {
          expect.soft(entry.all.p95, '141 项展开 p95').toBeLessThanOrEqual(GATE.p95)
          expect.soft(entry.all.max, '141 项展开 max').toBeLessThanOrEqual(GATE.max)
          expect.soft(entry.longTaskMax, '141 项展开期间最长 Long Task').toBeLessThanOrEqual(GATE.longTask)
          expect.soft(scroll.fps, '141 项展开后平均滚动 FPS').toBeGreaterThanOrEqual(GATE.fps)
          expect.soft(scroll.frameP95, '141 项展开后滚动 p95 帧时长').toBeLessThanOrEqual(GATE.frameP95)
        }
      })
    }
  }
}
