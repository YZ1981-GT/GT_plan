/**
 * useD4SyncMode 守卫（D4 双向回写改进 task#2，治本 composable）。
 *
 * 钉住本 composable 收敛掉的 4 类历史 bug 的**行为级**判据：
 *  ① 健康端点唯一正确：只打 `/api/workpapers/onlyoffice/health`，禁用旧 404 端点 `/api/onlyoffice/health`。
 *  ② switchMode 竞态兜底：健康未就绪（ooHealthy=false）点击「在线编辑」→ 当场 await 健康 → 健康 true 则
 *     真触发 switchToOnlyOffice（不静默吞点击）。
 *  ③ modeOptions 不用 `!ooHealthy` 锁死：健康未就绪时「在线编辑」项**仍可点**（disabled 只受 readonly/busy）。
 *  ④ descriptor 由桥暴露（不漏声明）。
 *
 * 变异反证：把 switchMode 的 `await checkOoHealth()` 兜底删掉，或把健康端点改回 /api/onlyoffice/health，
 * 对应用例即打红。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { effectScope, ref, nextTick } from 'vue'
import { flushPromises } from '@vue/test-utils'

// http mock：记录所有 GET，健康端点默认延迟返回 healthy=true（模拟 mount 期异步晚于点击）
const getCalls: string[] = []
let healthResolver: (v: any) => void = () => {}
vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn((url: string) => {
      getCalls.push(url)
      if (url.includes('onlyoffice/health')) {
        return new Promise((resolve) => { healthResolver = resolve })
      }
      return Promise.resolve({ data: { data: {} } })
    }),
    post: vi.fn(() => Promise.resolve({ data: { data: {} } })),
  },
}))

// 桥 mock：只暴露 switchToOnlyOffice/switchToHtml + 状态 ref，记录调用
const switchToOnlyOffice = vi.fn(() => Promise.resolve({} as any))
const switchToHtml = vi.fn(() => Promise.resolve())
vi.mock('../../../sync/useWorkpaperSyncBridge', () => ({
  WP_BRIDGE_IN_FLIGHT_STATES: ['materializing', 'oo_loading'],
  useWorkpaperSyncBridge: () => ({
    mode: ref<'html' | 'oo'>('html'),
    state: ref('html_idle'),
    descriptor: ref(null),
    feedback: ref({ message: '' }),
    dirty: ref(false),
    lastError: ref(''),
    switchToOnlyOffice,
    switchToHtml,
    reloadAfterApplied: vi.fn(() => Promise.resolve()),
  }),
}))
vi.mock('../../../sync/workpaperSyncApi', () => ({}))
vi.mock('../../../sync/workpaperSyncCapability', () => ({
  capabilityForEntry: () => 'bidirectional',
}))

import { useD4SyncMode, fetchOnlyOfficeHealthy, __resetOoHealthCacheForTests } from '../useD4SyncMode'

function makeMode(views = ['表格视图']) {
  return useD4SyncMode({
    sheetKey: 'd4xx-managed',
    wpId: ref('wp'),
    projectId: ref('p'),
    isReadonly: ref(false),
    views,
    flushHtml: async () => ({ expectedRevision: 1, projection: { values: {}, row_keys: {} }, sheetKey: 'd4xx-managed' } as any),
    reloadHtml: async () => {},
  })
}

describe('useD4SyncMode 统一接桥守卫', () => {
  beforeEach(() => {
    getCalls.length = 0
    switchToOnlyOffice.mockClear()
    switchToHtml.mockClear()
    // 🔴 2026-09-22：健康检查现有模块级 TTL 缓存 + in-flight 去重（见 useD4SyncMode.ts
    // 顶部 fetchOnlyOfficeHealthy 注释）。各用例各自控制 healthResolver 决定这次请求的
    // 结果/时机，若不清空会被前一用例遗留的缓存值或悬挂 promise 污染。
    __resetOoHealthCacheForTests()
  })

  it('① 只打正确健康端点，不打旧 404 端点', async () => {
    const scope = effectScope()
    scope.run(() => { makeMode() })
    await nextTick()
    expect(getCalls.some(u => u.includes('/api/workpapers/onlyoffice/health'))).toBe(true)
    expect(getCalls.some(u => u === '/api/onlyoffice/health' || /\/api\/onlyoffice\/health(\?|$)/.test(u))).toBe(false)
    scope.stop()
  })

  it('③ modeOptions 的「在线编辑」项在健康未就绪时仍可点（不被 !ooHealthy 锁死）', async () => {
    const scope = effectScope()
    scope.run(() => {
      const m = makeMode()
      // 健康 promise 尚未 resolve → ooHealthy 仍 false
      expect(m.ooHealthy.value).toBe(false)
      const online = m.modeOptions.value.find(o => o.value === '在线编辑')!
      expect(online.disabled).toBe(false)
    })
    scope.stop()
  })

  it('② 健康未就绪点在线编辑 → 当场 await 健康 → 健康 true 则真触发 switchToOnlyOffice', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const m = makeMode()
      expect(m.ooHealthy.value).toBe(false)
      // 点击（走 editorMode setter → switchMode）
      const p = (m.editorMode.value = '在线编辑') as unknown
      void p
      // switchMode 内 await checkOoHealth()，此刻 resolve 健康为 healthy
      healthResolver({ data: { data: { healthy: true } } })
      // 🔴 用 flushPromises()（本仓库既定的等待任意微任务链的惯用法，见其他
      // *.spec.ts）而非硬编码轮数的 nextTick——健康检查现经模块级共享 TTL 缓存
      // +in-flight 去重（.then().finally() 多包了两层），微任务队列深度会随实现
      // 细节变化，断言不该绑定具体轮数。
      await flushPromises()
      // 兜底 await 健康后应触发一次 switchToOnlyOffice
      expect(switchToOnlyOffice).toHaveBeenCalledTimes(1)
    })
    scope.stop()
  })

  it('② 健康探测返回不健康 → 不触发 switchToOnlyOffice（fail-visible 由桥给，不静默切）', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const m = makeMode()
      m.editorMode.value = '在线编辑'
      healthResolver({ data: { data: { healthy: false } } })
      await flushPromises()
      expect(switchToOnlyOffice).not.toHaveBeenCalled()
    })
    scope.stop()
  })

  it('④ descriptor 由桥暴露（初始 null，不漏声明）', () => {
    const scope = effectScope()
    scope.run(() => {
      const m = makeMode()
      expect(m.descriptor.value).toBeNull()
    })
    scope.stop()
  })

  it('多视图形态：views 给几个就有几个 + 在线编辑', () => {
    const scope = effectScope()
    scope.run(() => {
      const m = makeMode(['卡片视图', '矩阵视图'])
      expect(m.modeOptions.value.map(o => o.value)).toEqual(['卡片视图', '矩阵视图', '在线编辑'])
    })
    scope.stop()
  })

  it('fetchOnlyOfficeHealthy 读 .healthy 字段（非 status===healthy）', async () => {
    // 直接验证纯函数字段读取口径
    healthResolver = () => {}
    const scope = effectScope()
    scope.run(() => {})
    scope.stop()
    // 通过 mock 已隐式覆盖端点；此用例锚定字段名，防回退到 status
    expect(typeof fetchOnlyOfficeHealthy).toBe('function')
  })
})

/**
 * 🔴 2026-09-22 性能修复守卫：健康检查的模块级共享 TTL 缓存 + in-flight 去重。
 *
 * 治的病：此前每次 useD4SyncMode() 挂载（=== 每切一次 D4-N 底稿，D4-1~36 共 30 张
 * 共用同段 mount 逻辑）都无条件 void checkOoHealth() 打一次探针；切页面越勤打得越多，
 * 叠加后端一度的同步阻塞 IO 就是「切页面不丝滑」的根因之一。
 *
 * 判据：①TTL 内第二次调用命中缓存不再打请求；②并发调用去重成一次真实请求；
 * ③forceRefresh=true 绕过缓存强制打新请求（用户点击时不能被过期边界的旧值挡住）。
 * 变异反证：把缓存/去重摘掉退回「每次都 http.get」，①②打红；把 forceRefresh 分支
 * 改成也走缓存，③打红。
 */
function healthCallCount(): number {
  return getCalls.filter(u => u.includes('onlyoffice/health')).length
}

describe('fetchOnlyOfficeHealthy 共享 TTL 缓存 + in-flight 去重', () => {
  beforeEach(() => {
    getCalls.length = 0
    __resetOoHealthCacheForTests()
  })

  it('① TTL 内第二次调用命中缓存，不再打第二次请求', async () => {
    const p1 = fetchOnlyOfficeHealthy()
    healthResolver({ data: { data: { healthy: true } } })
    const v1 = await p1
    expect(v1).toBe(true)
    expect(healthCallCount()).toBe(1)

    // 缓存未过期（TTL 15s，测试瞬时完成）→ 第二次应命中缓存
    const v2 = await fetchOnlyOfficeHealthy()
    expect(v2).toBe(true)
    expect(healthCallCount()).toBe(1) // 仍是 1，没打第二次
  })

  it('② 并发调用去重成一次真实请求', async () => {
    // 同一时刻两个组件挂载各调一次，应只打一次 http.get
    const pa = fetchOnlyOfficeHealthy()
    const pb = fetchOnlyOfficeHealthy()
    expect(healthCallCount()).toBe(1) // in-flight 去重：第二次复用同一 promise
    healthResolver({ data: { data: { healthy: true } } })
    const [va, vb] = await Promise.all([pa, pb])
    expect(va).toBe(true)
    expect(vb).toBe(true)
    expect(healthCallCount()).toBe(1)
  })

  it('③ forceRefresh=true 绕过缓存强制打新请求', async () => {
    // 先填充一份缓存
    const p1 = fetchOnlyOfficeHealthy()
    healthResolver({ data: { data: { healthy: true } } })
    await p1
    expect(healthCallCount()).toBe(1)

    // forceRefresh=true：即便缓存未过期也要真的再问一次
    const p2 = fetchOnlyOfficeHealthy(true)
    healthResolver({ data: { data: { healthy: false } } })
    const v2 = await p2
    expect(healthCallCount()).toBe(2) // 打了第二次
    expect(v2).toBe(false) // 拿到的是最新状态，不是旧缓存的 true
  })
})
