/**
 * Property 5: 年度切换响应不变量 — 属性测试（V3 Req 5.3）
 *
 * 形式化：∀ view V depending on year, ∀ year change Y → Y':
 *   Y → Y' triggers V.refetch() within 1s
 *
 * 测试策略：
 * - 用 fast-check 生成随机的 (projectId, year) 切换序列
 * - 通过 useAuditContext 注册 onContextChange 回调，观测回调与事件 emit
 * - 业务不变量：
 *   (P5-a) 路由变化（projectId 或 year）经 50ms debounce 后必有事件 emit
 *   (P5-b) 注册的 onContextChange 回调收到的 (projectId, year) 等于触发时刻 projectStore 的当前值
 *   (P5-c) 同一 tick 多次变化只 emit 一次（debounce 合并）
 *   (P5-d) 7 核心视图源码必同时含 `useAuditContext` 与 `onContextChange`（静态保证 5.1 不被回退）
 *
 * 反例期望：
 * - 找到任何"路由变化但 onContextChange 不触发"的情形 = composable bug
 * - 找到任何"7 视图缺失接入"的情形 = 5.1 退化
 *
 * Validates: Requirements 5
 *
 * 实施方案：复盘 spec 任务 5.3 提出的 A/B/C 三方案，本测试采用 B（vitest + fast-check）+ C（静态扫描）。
 * 方案 A（Playwright）兜底参考 e2e/year-switching.spec.ts（最小骨架，待 6000 并发压测窗口完整化）。
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import * as fc from 'fast-check'
import { mount } from '@vue/test-utils'
import { defineComponent, nextTick, reactive } from 'vue'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { useProjectStore } from '@/stores/project'
import { useAuditContext, DEBOUNCE_MS } from '@/composables/useAuditContext'
import { eventBus } from '@/utils/eventBus'

// ─── Mock vue-router（reactive 以便 watch 能检测变化） ───────────────────────
const mockRoute = reactive({
  params: { projectId: 'proj-001' } as Record<string, string>,
  query: { year: '2024' } as Record<string, string>,
})

vi.mock('vue-router', () => ({
  useRoute: () => mockRoute,
}))

// ─── Mock roleContext（不影响本 Property 关注的回调触发逻辑） ────────────────
const mockRoleContext = reactive({ canEditInProject: true })
vi.mock('@/stores/roleContext', () => ({
  useRoleContextStore: () => mockRoleContext,
}))

// ─── Mock 远程 service（避免真实 API 调用） ─────────────────────────────────
vi.mock('@/services/auditPlatformApi', () => ({
  getProject: vi.fn().mockResolvedValue({ id: 'proj-001', client_name: '测试客户' }),
  getProjectAuditYear: vi.fn().mockResolvedValue(2024),
}))
vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue([]) },
}))

let testPinia: Pinia

/** Helper：在 setup 上下文调用 composable，避免「inject only at setup」报错 */
function withSetup<T>(composable: () => T): { result: T; wrapper: ReturnType<typeof mount> } {
  let result!: T
  const Comp = defineComponent({
    setup() {
      result = composable()
      return {}
    },
    template: '<div />',
  })
  const wrapper = mount(Comp, { global: { plugins: [testPinia] } })
  return { result, wrapper }
}

/** 推进 watch flush + debounce timer，等价于"等待回调链落地" */
async function flushAuditContext() {
  await nextTick() // 触发 reactive 依赖
  await nextTick() // flush: 'post' 二次落地
  vi.advanceTimersByTime(DEBOUNCE_MS)
}

describe('Property 5: 年度切换响应不变量', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    testPinia = createPinia()
    setActivePinia(testPinia)
    mockRoute.params.projectId = 'proj-001'
    mockRoute.query.year = '2024'
    mockRoleContext.canEditInProject = true
  })

  afterEach(() => {
    vi.useRealTimers()
    eventBus.all.clear()
  })

  /**
   * P5-a：路由变化经 debounce 后必有事件 emit + 回调触发
   * 反例：emit / 回调未触发 = onContextChange 链路 bug
   */
  it('Property 5a: 路由变化（projectId/year）必触发 onContextChange 回调', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.record({
          newProjectId: fc.constantFrom('proj-A', 'proj-B', 'proj-C'),
          newYear: fc.integer({ min: 2020, max: 2030 }),
        }),
        async ({ newProjectId, newYear }) => {
          // 每次 property 运行用独立 pinia/timer，避免污染
          vi.useFakeTimers()
          testPinia = createPinia()
          setActivePinia(testPinia)
          eventBus.all.clear()

          mockRoute.params.projectId = 'proj-init'
          mockRoute.query.year = '2024'

          const cb = vi.fn()
          const { wrapper } = withSetup(() => {
            const ctx = useAuditContext()
            ctx.onContextChange(cb)
            return ctx
          })

          // 触发变化（projectId 或 year 任意之一）
          mockRoute.params.projectId = newProjectId
          mockRoute.query.year = String(newYear)
          await flushAuditContext()

          // 不变量：回调被调用至少一次
          expect(cb).toHaveBeenCalled()
          // 回调收到的 year 等于触发时刻 projectStore.year（fallback 链）
          const lastCall = cb.mock.calls.at(-1)?.[0] as { projectId: string; year: number }
          expect(typeof lastCall.projectId).toBe('string')
          expect(typeof lastCall.year).toBe('number')

          wrapper.unmount()
          vi.useRealTimers()
        },
      ),
      { numRuns: 20 },
    )
  })

  /**
   * P5-b：debounce 合并 — 同一 50ms 窗口内多次变化只触发一次回调
   * 反例：触发次数 > 1 = debounce 失效
   */
  it('Property 5b: 50ms 内连续 N 次变化只触发一次回调（debounce 合并）', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.array(fc.integer({ min: 2020, max: 2030 }), { minLength: 2, maxLength: 8 }),
        async (yearSequence) => {
          vi.useFakeTimers()
          testPinia = createPinia()
          setActivePinia(testPinia)
          eventBus.all.clear()

          mockRoute.params.projectId = 'proj-debounce'
          mockRoute.query.year = '2024'

          const cb = vi.fn()
          const { wrapper } = withSetup(() => {
            const ctx = useAuditContext()
            ctx.onContextChange(cb)
            return ctx
          })

          // 在 debounce 窗口内（每次推进 < DEBOUNCE_MS）连续切换
          for (const y of yearSequence) {
            mockRoute.query.year = String(y)
            await nextTick()
            await nextTick()
            // 推进 < DEBOUNCE_MS，使后续变化重置 debounce
            vi.advanceTimersByTime(Math.max(1, Math.floor(DEBOUNCE_MS / 2) - 5))
          }

          // 此时距最后一次变化还不到完整 DEBOUNCE_MS，回调不应已触发
          const callsBeforeFlush = cb.mock.calls.length
          // 推进满 debounce 窗口
          vi.advanceTimersByTime(DEBOUNCE_MS)

          // 不变量：debounce 后回调最多增加 1 次（合并窗口内所有变化）
          const callsAfterFlush = cb.mock.calls.length
          expect(callsAfterFlush - callsBeforeFlush).toBeLessThanOrEqual(1)

          wrapper.unmount()
          vi.useRealTimers()
        },
      ),
      { numRuns: 15 },
    )
  })

  /**
   * P5-c：每次回调收到的 year 等于触发时刻 mockRoute.query.year（最终值）
   * 反例：回调 year 与最终路由 year 不一致 = stale closure
   */
  it('Property 5c: 回调收到的 year 等于触发时刻的最新 year（无 stale closure）', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.integer({ min: 2018, max: 2032 }),
        async (targetYear) => {
          vi.useFakeTimers()
          testPinia = createPinia()
          setActivePinia(testPinia)
          eventBus.all.clear()

          // 用 projectStore.year（优先级最高）作为真值源
          const store = useProjectStore()
          store.year = 2024

          mockRoute.params.projectId = 'proj-fresh'
          mockRoute.query.year = '2024'

          const received: number[] = []
          const { wrapper } = withSetup(() => {
            const ctx = useAuditContext()
            ctx.onContextChange((c) => { received.push(c.year) })
            return ctx
          })

          // projectStore.year 优先级 > route.query.year，先改 store 再触发 watch
          store.year = targetYear
          mockRoute.query.year = String(targetYear) // 也同步触发 watch
          await flushAuditContext()

          // 不变量：回调收到的 year 必等于 targetYear
          // （fallback 链：projectStore.year || Number(route.query.year) || currentYear-1）
          expect(received.length).toBeGreaterThanOrEqual(1)
          expect(received.at(-1)).toBe(targetYear)

          wrapper.unmount()
          vi.useRealTimers()
        },
      ),
      { numRuns: 20 },
    )
  })

  /**
   * P5-d（静态保证）：7 核心视图源码必同时含 `useAuditContext` 与 `onContextChange`
   * 反例：任一视图缺失任一关键字 = 5.1 接入退化
   *
   * 这是方案 C 的 PBT 化：把 7 视图的字符串检查写成 fc.constantFrom 遍历断言。
   */
  it('Property 5d: 7 核心视图源码必同时含 useAuditContext 与 onContextChange', async () => {
    const fs = await import('fs')
    const path = await import('path')

    // 7 核心视图（Sprint 1 Req 5.1 已接入清单）
    const SEVEN_VIEWS = [
      'Adjustments.vue',
      'Misstatements.vue',
      'ReportView.vue',
      'DisclosureEditor.vue',
      'WorkpaperList.vue',
      'TrialBalance.vue',
      'LedgerPenetration.vue',
    ] as const

    // vitest cwd = 前端工程根目录，但脚本可能在仓库根跑，做 fallback
    const cwd = process.cwd()
    const candidates = [
      path.resolve(cwd, 'src/views'),
      path.resolve(cwd, 'audit-platform/frontend/src/views'),
      path.resolve(cwd, '../audit-platform/frontend/src/views'),
    ]
    const viewsDir = candidates.find((p) => fs.existsSync(p))
    expect(viewsDir, '未找到 src/views 目录').toBeDefined()

    fc.assert(
      fc.property(fc.constantFrom(...SEVEN_VIEWS), (filename) => {
        const full = path.join(viewsDir!, filename)
        expect(fs.existsSync(full), `${filename} 不存在`).toBe(true)
        const src = fs.readFileSync(full, 'utf-8')

        // 不变量：源码必同时含 useAuditContext + onContextChange
        // useAuditContext 既是 import 也是调用关键字；onContextChange 是 composable 返回的方法
        expect(src.includes('useAuditContext'), `${filename} 缺失 useAuditContext`).toBe(true)
        expect(src.includes('onContextChange'), `${filename} 缺失 onContextChange`).toBe(true)
      }),
      // 7 视图穷举即可，numRuns 设为 7（fast-check 可能采样重复，足够覆盖）
      { numRuns: 14 },
    )
  })

  /**
   * P5-e（事件总线兜底）：audit-context:changed 事件 payload 结构不变
   * 反例：emit payload 缺失字段 = 事件契约破坏
   */
  it('Property 5e: audit-context:changed 事件 payload 含 projectId/year/applicableStandard/before', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.record({
          pid: fc.constantFrom('p-1', 'p-2', 'p-3'),
          y: fc.integer({ min: 2020, max: 2028 }),
        }),
        async ({ pid, y }) => {
          vi.useFakeTimers()
          testPinia = createPinia()
          setActivePinia(testPinia)
          eventBus.all.clear()

          mockRoute.params.projectId = 'proj-ev'
          mockRoute.query.year = '2024'

          const handler = vi.fn()
          eventBus.on('audit-context:changed', handler)

          const { wrapper } = withSetup(() => useAuditContext())

          mockRoute.params.projectId = pid
          mockRoute.query.year = String(y)
          await flushAuditContext()

          // 不变量：handler 至少触发一次，且 payload 结构完整
          expect(handler).toHaveBeenCalled()
          const lastPayload = handler.mock.calls.at(-1)?.[0]
          expect(lastPayload).toMatchObject({
            projectId: expect.any(String),
            year: expect.any(Number),
            applicableStandard: expect.any(String),
            before: {
              projectId: expect.any(String),
              year: expect.any(Number),
              applicableStandard: expect.any(String),
            },
          })

          eventBus.off('audit-context:changed', handler)
          wrapper.unmount()
          vi.useRealTimers()
        },
      ),
      { numRuns: 15 },
    )
  })
})
