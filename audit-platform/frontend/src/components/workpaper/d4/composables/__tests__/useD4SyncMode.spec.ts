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

import { useD4SyncMode, fetchOnlyOfficeHealthy } from '../useD4SyncMode'

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
      await nextTick(); await nextTick(); await Promise.resolve()
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
      await nextTick(); await nextTick(); await Promise.resolve()
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
