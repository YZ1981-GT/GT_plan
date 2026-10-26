/**
 * useAcnr 按项目订阅与失效隔离（D9 / T27 / 需求 11.1~11.4）
 *
 * 签名改 `useAcnr(projectId?: MaybeRefOrGetter<string|null|undefined>)` 后：
 *  - 在 effect scope（组件 setup / Pinia setup store）内 → 订阅当前项目；A→B 切换时先取消 A
 *    再建 B；同项目多处只有一个总线订阅（本层按 projectId 引用计数复用）；scope 释放后归零。
 *  - 在普通函数里调用（无 effect scope）→ 不订阅（无从释放）。
 *  - 失效隔离：A 收到 `acnr:invalidate`（仅 project_id）只清 A 的 resolve 缓存，B 仍命中；
 *    携带新 catalog_version 才清目录级缓存。
 *
 * 守卫以 stub `subscribeProjectEvent` 计数按项目的订阅建立/取消。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { effectScope, ref, nextTick, watch } from 'vue'

const PID_A = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
const PID_B = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'

// ─── Mock http ────────────────────────────────────────────────────────────────
const mockGet = vi.fn()
vi.mock('@/utils/http', () => ({
  default: { get: (...args: any[]) => mockGet(...args) },
}))

// ─── Stub 项目事件总线：按 projectId 计数订阅建立/取消 ─────────────────────────
// 每 (projectId) 一个活跃订阅句柄；记录 open/close 次数与当前活跃计数。
interface SubStat {
  opened: number
  closed: number
  active: number
  handler: ((data: unknown, event: string) => void) | null
  onReconnect?: () => void
}
const subStats = new Map<string, SubStat>()

function _stat(pid: string): SubStat {
  let s = subStats.get(pid)
  if (!s) {
    s = { opened: 0, closed: 0, active: 0, handler: null }
    subStats.set(pid, s)
  }
  return s
}

const subscribeProjectEvent = vi.fn(
  (projectId: string, _eventName: string, handler: any, options: any = {}) => {
    if (!projectId) return { close() {} }
    const s = _stat(projectId)
    s.opened++
    s.active++
    s.handler = handler
    s.onReconnect = options?.onReconnect
    let closed = false
    return {
      close() {
        if (closed) return
        closed = true
        s.closed++
        s.active--
      },
    }
  },
)

vi.mock('@/services/sse/projectEventStream', () => ({
  subscribeProjectEvent: (...args: any[]) => subscribeProjectEvent(...(args as [any, any, any, any])),
  isProjectStreamDegraded: () => false,
}))

async function loadModule() {
  return await import('../useAcnr')
}

describe('useAcnr — 按项目订阅（D9 T27，需求 11.1/11.4）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    subStats.clear()
    vi.resetModules()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('effect scope 内带项目 → 订阅该项目（一次）', async () => {
    const { useAcnr } = await loadModule()
    const scope = effectScope()
    scope.run(() => {
      useAcnr(PID_A)
    })
    await nextTick()
    expect(_stat(PID_A).opened).toBe(1)
    expect(_stat(PID_A).active).toBe(1)
    scope.stop()
  })

  it('A→B 切换：取消 A、建立 B（watch 随项目切订阅）', async () => {
    const { useAcnr } = await loadModule()
    const pid = ref<string>(PID_A)
    const scope = effectScope()
    scope.run(() => {
      useAcnr(() => pid.value)
    })
    await nextTick()
    expect(_stat(PID_A).active).toBe(1)
    expect(_stat(PID_B).active).toBe(0)

    pid.value = PID_B
    await nextTick()
    // A 取消、B 建立
    expect(_stat(PID_A).active).toBe(0)
    expect(_stat(PID_A).closed).toBe(1)
    expect(_stat(PID_B).active).toBe(1)
    expect(_stat(PID_B).opened).toBe(1)
    scope.stop()
  })

  it('同项目多处调用 → 只建一个总线订阅（subscribeInvalidation 按项目引用计数复用）', async () => {
    // useAcnr 内部走 subscribeInvalidation(pid)，后者按 projectId 引用计数复用同一总线订阅：
    // 同 scope 内两处 useAcnr(同项目) 只向总线订阅一次（opened=1，active=1）；两处的 cleanup
    // 把 refCount 2→1→0，最后一处释放时才真正 close 总线订阅。
    const { useAcnr } = await loadModule()
    const scope = effectScope()
    scope.run(() => {
      useAcnr(PID_A)
      useAcnr(PID_A)
    })
    await nextTick()
    expect(_stat(PID_A).opened).toBe(1)
    expect(_stat(PID_A).active).toBe(1)
    scope.stop()
    // 两处 onScopeDispose 都触发 subscribeInvalidation 的 cleanup：refCount 归 0 → 总线订阅 close 一次
    expect(_stat(PID_A).active).toBe(0)
    expect(_stat(PID_A).closed).toBe(1)
  })

  it('scope 释放后订阅归零（onScopeDispose）', async () => {
    const { useAcnr } = await loadModule()
    const scope = effectScope()
    scope.run(() => {
      useAcnr(PID_A)
    })
    await nextTick()
    expect(_stat(PID_A).active).toBe(1)
    scope.stop()
    expect(_stat(PID_A).active).toBe(0)
    expect(_stat(PID_A).closed).toBe(1)
  })

  it('普通函数内调用（无 effect scope）→ 不订阅', async () => {
    const { useAcnr } = await loadModule()
    // 直接在 describe 回调里调用（无活跃 effect scope）
    useAcnr(PID_A)
    await nextTick()
    expect(subscribeProjectEvent).not.toHaveBeenCalled()
    expect(_stat(PID_A).active).toBe(0)
  })

  it('空项目（空串/undefined）不建连接', async () => {
    const { useAcnr } = await loadModule()
    const scope = effectScope()
    scope.run(() => {
      useAcnr('')
      useAcnr(undefined)
      useAcnr(() => null)
    })
    await nextTick()
    // subscribeInvalidation('') 在 useAcnr 内被调但本层对空值直接 no-op，不触达总线 stub
    expect(subscribeProjectEvent).not.toHaveBeenCalled()
    scope.stop()
  })

  it('store 式：getter 随 _projectId 切换时同步切订阅', async () => {
    // 模拟 addressRegistry store：useAcnr(() => _projectId.value)，store 在 effect scope 内。
    const { useAcnr } = await loadModule()
    const _projectId = ref('')
    const scope = effectScope()
    scope.run(() => {
      useAcnr(() => _projectId.value)
    })
    await nextTick()
    // 初始空 → 未订阅
    expect(subscribeProjectEvent).not.toHaveBeenCalled()
    // refresh 绑定项目 A
    _projectId.value = PID_A
    await nextTick()
    expect(_stat(PID_A).active).toBe(1)
    // 切到项目 B
    _projectId.value = PID_B
    await nextTick()
    expect(_stat(PID_A).active).toBe(0)
    expect(_stat(PID_B).active).toBe(1)
    scope.stop()
    expect(_stat(PID_B).active).toBe(0)
  })

  // ─── 失效隔离（D9 T28，需求 11.3/11.5） ────────────────────────────────────
  it('A 收到项目级失效只清 A 的 resolve 缓存，B 仍命中', async () => {
    const { useAcnr, getCacheEpoch } = await loadModule()
    const scope = effectScope()
    let acnr!: ReturnType<typeof useAcnr>
    scope.run(() => {
      acnr = useAcnr(PID_A)
      // 同时订阅 B 以便拿到 B 的 handler
      useAcnr(PID_B)
    })
    await nextTick()

    mockGet.mockResolvedValue({ data: { found: true, addr_id: 'D2/D2-2/E100' } })
    await acnr.resolveIndex('cell:D2-2!E100', PID_A)
    await acnr.resolveIndex('cell:D3-2!E100', PID_B)
    const callsAfterSeed = mockGet.mock.calls.length
    const epochBefore = getCacheEpoch()

    // 触发 A 的项目级失效（仅 project_id，无 catalog_version）
    _stat(PID_A).handler?.({ project_id: PID_A }, 'acnr:invalidate')

    // epoch 未变（不 bump 全局目录）
    expect(getCacheEpoch()).toBe(epochBefore)
    // B 仍命中
    await acnr.resolveIndex('cell:D3-2!E100', PID_B)
    expect(mockGet.mock.calls.length).toBe(callsAfterSeed)
    // A 已清 → 重新请求
    await acnr.resolveIndex('cell:D2-2!E100', PID_A)
    expect(mockGet.mock.calls.length).toBe(callsAfterSeed + 1)
    scope.stop()
  })

  it('携带新 catalog_version → 清目录级缓存 + bump epoch', async () => {
    const { useAcnr, getCacheEpoch } = await loadModule()
    const scope = effectScope()
    let acnr!: ReturnType<typeof useAcnr>
    scope.run(() => {
      acnr = useAcnr(PID_A)
    })
    await nextTick()

    mockGet.mockResolvedValue({ data: [{ addr_id: 'D2/D2-2', sheet_code: 'D2-2' }] })
    await acnr.listSheets('D')
    const callsAfterSeed = mockGet.mock.calls.length
    const epochBefore = getCacheEpoch()

    _stat(PID_A).handler?.(
      { project_id: PID_A, catalog_version: 'v-new-2026' },
      'acnr:invalidate',
    )

    expect(getCacheEpoch()).toBe(epochBefore + 1)
    await acnr.listSheets('D')
    expect(mockGet.mock.calls.length).toBe(callsAfterSeed + 1)
    scope.stop()
  })
})

// watch 导入仅为确保 vue 的 watch 在 mock 环境下可用（本文件直接依赖 useAcnr 内部 watch）。
void watch
