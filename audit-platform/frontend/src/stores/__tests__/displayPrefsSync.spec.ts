/**
 * displayPrefs 账号加载、30 天缓存、mutation epoch 与冲突重放测试
 *
 * spec: platform-global-display-settings-closure 任务 4（design §3、§16 F6、§17 G3）
 * 这些判据只在「服务端权威 + 本机未确认操作」的并发时序下成立，纯函数单测看不到：
 * 缓存按 userId 分区且 TTL 恰 30 天、旧键只删不迁移、账号切换清空在途与 pending、
 * 晚到响应按 userId+generation 丢弃、每项 mutation epoch 冻结与同 epoch 清除、
 * 409 单次重放、固定列 100 键按 saved_at 淘汰。
 *
 * Validates: Requirements AC-04、AC-06、AC-09、AC-10
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }))
vi.mock('@/services/displayPreferencesApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/displayPreferencesApi')>()
  return {
    ...actual,
    getDisplayPreferences: (...args: unknown[]) => apiMock.get(...args),
    patchDisplayPreferences: (...args: unknown[]) => apiMock.patch(...args),
  }
})

type StoreModule = typeof import('@/stores/displayPrefs')
type ApiModule = typeof import('@/services/displayPreferencesApi')
type Store = ReturnType<StoreModule['useDisplayPrefsStore']>

const CACHE_PREFIX = 'gt_display_prefs:v3:'
const LEGACY_KEY = 'gt_display_prefs'
const TTL_MS = 30 * 24 * 60 * 60 * 1000

let store: Store
let Conflict: ApiModule['DisplayPreferencesRevisionConflict']
let projectStore: ReturnType<typeof import('@/stores/project')['useProjectStore']>

function serverState(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    amount_unit_override: null,
    font_size: 'sm',
    show_zero: false,
    decimals: 2,
    negative_red: true,
    highlight_threshold: 0.2,
    density: 'default',
    grid_edit_mode: 'excel',
    fixed_columns: {},
    revision: 1,
    updated_at: '2026-11-01T00:00:00+00:00',
    ...overrides,
  }
}

/**
 * 假服务端：PATCH 必须按补丁回写并递增 revision。
 * 让响应恒等于固定状态会掩盖「成功响应成为新 server base」这条判据。
 */
let server: Record<string, unknown>

const SCALAR_WIRE: Record<string, string> = {
  amountUnitOverride: 'amount_unit_override',
  fontSize: 'font_size',
  showZero: 'show_zero',
  decimals: 'decimals',
  negativeRed: 'negative_red',
  highlightThreshold: 'highlight_threshold',
  density: 'density',
  gridEditMode: 'grid_edit_mode',
}

function applyPatchToServer(patch: Record<string, unknown>): Record<string, unknown> {
  for (const [local, wire] of Object.entries(SCALAR_WIRE)) {
    if (local in patch) server[wire] = patch[local]
  }
  if ('fixedColumns' in patch) {
    const next: Record<string, unknown> = {}
    for (const [pageKey, entry] of Object.entries(patch.fixedColumns as Record<string, { columns: string[] }>)) {
      next[pageKey] = { columns: [...entry.columns], saved_at: new Date().toISOString() }
    }
    server.fixed_columns = next
  }
  server.revision = (patch.baseRevision as number) + 1
  return { ...server }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

function cachePayload(overrides: Record<string, unknown> = {}): string {
  return JSON.stringify({
    version: 3,
    prefs: {
      amountUnitOverride: null,
      fontSize: 'lg',
      showZero: false,
      decimals: 2,
      negativeRed: true,
      highlightThreshold: 0.2,
      density: 'comfortable',
      gridEditMode: 'excel',
      fixedColumns: {},
      revision: 4,
      updatedAt: null,
    },
    revision: 4,
    pendingScalars: {},
    pendingFixedOps: {},
    cachedAt: Date.now(),
    ...overrides,
  })
}

/** 推进防抖并让 flush 的 promise 链跑完。 */
async function flushDebounce(): Promise<void> {
  await vi.advanceTimersByTimeAsync(300)
  await Promise.resolve()
  await Promise.resolve()
}

/**
 * store 交给 api 层的是内部 camelCase 补丁（`baseRevision`/`fixedColumns`）；
 * camel→snake 的线格式与「显式 null」由 services/__tests__/displayPreferencesApi.spec.ts 守。
 */
function lastPatchBody(): Record<string, unknown> {
  const calls = apiMock.patch.mock.calls
  return calls[calls.length - 1][0] as Record<string, unknown>
}

function lastPatchFixed(): Record<string, { columns: string[] }> {
  return lastPatchBody().fixedColumns as Record<string, { columns: string[] }>
}

beforeEach(async () => {
  apiMock.get.mockReset()
  apiMock.patch.mockReset()
  server = serverState()
  apiMock.get.mockImplementation(async () => ({ ...server }))
  apiMock.patch.mockImplementation(async (patch: Record<string, unknown>) => applyPatchToServer(patch))
  localStorage.clear()

  // 全局 setup 先 import 过 store，必须 resetModules 才能让上面的 api mock 到达 store。
  vi.resetModules()
  const pinia = await import('pinia')
  const api = await import('@/services/displayPreferencesApi')
  const storeModule = await import('@/stores/displayPrefs')
  const projectModule = await import('@/stores/project')
  Conflict = api.DisplayPreferencesRevisionConflict
  pinia.setActivePinia(pinia.createPinia())
  projectStore = projectModule.useProjectStore()
  store = storeModule.useDisplayPrefsStore()
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('api mock 自检', () => {
  it('store 走的是被 mock 的 api（否则下面全部断言都在打真实网络）', async () => {
    await store.loadForUser('user-a')
    expect(apiMock.get).toHaveBeenCalledTimes(1)
    expect(store.loadState).toBe('ready')
  })
})

describe('按账号分区的 30 天缓存', () => {
  it('只写 gt_display_prefs:v3:<userId>，并删除未分区的旧键', async () => {
    localStorage.setItem(LEGACY_KEY, JSON.stringify({ fontSize: 'lg' }))
    await store.loadForUser('user-a')

    expect(localStorage.getItem(LEGACY_KEY)).toBeNull()
    expect(localStorage.getItem(`${CACHE_PREFIX}user-a`)).not.toBeNull()
    const written = Object.keys(localStorage).filter((key) => key.includes('display_prefs'))
    expect(written).toEqual([`${CACHE_PREFIX}user-a`])
  })

  it('旧键的内容不迁移到新键', async () => {
    localStorage.setItem(LEGACY_KEY, JSON.stringify({ fontSize: 'lg', density: 'comfortable' }))
    await store.loadForUser('user-a')

    expect(store.fontSize).toBe('sm')
    expect(store.density).toBe('default')
  })

  it('29 天前的缓存在离线时仍可用', async () => {
    localStorage.setItem(`${CACHE_PREFIX}user-a`, cachePayload({
      cachedAt: Date.now() - (TTL_MS - 24 * 60 * 60 * 1000),
    }))
    apiMock.get.mockRejectedValue(new Error('offline'))

    await store.loadForUser('user-a')

    expect(store.fontSize).toBe('lg')
    expect(store.density).toBe('comfortable')
    expect(store.loadState).toBe('offline')
  })

  it('超过 30 天的缓存整份丢弃，连 pending 一起丢', async () => {
    localStorage.setItem(`${CACHE_PREFIX}user-a`, cachePayload({
      cachedAt: Date.now() - TTL_MS - 1,
      pendingScalars: { fontSize: { epoch: 9, value: 'lg' } },
      pendingFixedOps: { 'trial-balance': { epoch: 10, kind: 'upsert', columns: ['code'], savedAt: '2026-11-01T00:00:00+00:00' } },
    }))
    apiMock.get.mockRejectedValue(new Error('offline'))

    await store.loadForUser('user-a')

    expect(store.fontSize).toBe('sm')
    expect(store.getFixedColumns('trial-balance')).toEqual([])
    expect(store.hasPendingChanges).toBe(false)
    await flushDebounce()
    expect(apiMock.patch).not.toHaveBeenCalled()
  })

  it('恰好 30 天边界内的缓存仍然可用', async () => {
    localStorage.setItem(`${CACHE_PREFIX}user-a`, cachePayload({ cachedAt: Date.now() - TTL_MS + 1000 }))
    apiMock.get.mockRejectedValue(new Error('offline'))

    await store.loadForUser('user-a')
    expect(store.fontSize).toBe('lg')
  })

  it('损坏 JSON 与错误版本不抛异常，坏载荷被清除且不被采用', async () => {
    // GET 一并失败，这样被清掉的键不会立刻被一份新的有效缓存覆盖，断言才看得见「清除」
    apiMock.get.mockRejectedValue(new Error('offline'))

    localStorage.setItem(`${CACHE_PREFIX}user-a`, '{不是 JSON')
    await expect(store.loadForUser('user-a')).resolves.toBeUndefined()
    expect(store.fontSize).toBe('sm')
    // 坏载荷不再存在：离线路径会把当前（默认）状态重新写成合法 v3 载荷
    const afterCorrupt = JSON.parse(localStorage.getItem(`${CACHE_PREFIX}user-a`)!)
    expect(afterCorrupt.version).toBe(3)
    expect(afterCorrupt.prefs.fontSize).toBe('sm')

    localStorage.setItem(`${CACHE_PREFIX}user-b`, cachePayload({ version: 2 }))
    await expect(store.loadForUser('user-b')).resolves.toBeUndefined()
    expect(store.fontSize).toBe('sm')
    const afterBadVersion = JSON.parse(localStorage.getItem(`${CACHE_PREFIX}user-b`)!)
    expect(afterBadVersion.version).toBe(3)
    expect(afterBadVersion.prefs.fontSize).toBe('sm')
  })

  it('错误版本的缓存在没有任何写回时被删除', async () => {
    apiMock.get.mockRejectedValue(new Error('offline'))
    localStorage.setItem(`${CACHE_PREFIX}user-c`, cachePayload({ version: 2 }))
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota', 'QuotaExceededError')
    })
    try {
      await store.loadForUser('user-c')
      expect(localStorage.getItem(`${CACHE_PREFIX}user-c`)).toBeNull()
    } finally {
      setItem.mockRestore()
    }
  })

  it('缓存里的越界值被范围保护收回（decimals=999）', async () => {
    localStorage.setItem(`${CACHE_PREFIX}user-a`, JSON.stringify({
      version: 3,
      prefs: { decimals: 999, highlightThreshold: 5, fontSize: 'xxl' },
      revision: 2,
      pendingScalars: { decimals: { epoch: 3, value: 999 } },
      pendingFixedOps: {},
      cachedAt: Date.now(),
    }))
    apiMock.get.mockRejectedValue(new Error('offline'))

    await store.loadForUser('user-a')

    expect(store.decimals).toBe(2)
    expect(store.highlightThreshold).toBe(0.2)
    expect(store.fontSize).toBe('sm')
    // 越界的 pending 项不被恢复，不可能再发给服务端
    expect(store.pendingPatch.scalars).not.toContain('decimals')
  })

  it('Storage 读写异常（SecurityError/QuotaExceededError）不打断加载与编辑', async () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError')
    })
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota', 'QuotaExceededError')
    })
    const removeItem = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError')
    })
    try {
      await expect(store.loadForUser('user-a')).resolves.toBeUndefined()
      expect(() => store.setFontSize('lg')).not.toThrow()
      expect(store.fontSize).toBe('lg')
      await flushDebounce()
      expect(apiMock.patch).toHaveBeenCalledTimes(1)
    } finally {
      getItem.mockRestore()
      setItem.mockRestore()
      removeItem.mockRestore()
    }
  })
})

describe('账号切换与晚到响应', () => {
  it('A→B→A 不泄露：B 看不到 A 的偏好，回到 A 读回 A 的缓存', async () => {
    await store.loadForUser('user-a')
    store.setFontSize('lg')
    await flushDebounce()
    expect(store.fontSize).toBe('lg')

    apiMock.get.mockResolvedValue(serverState({ font_size: 'xs', revision: 9 }))
    await store.loadForUser('user-b')
    expect(store.fontSize).toBe('xs')
    expect(store.ownerUserId).toBe('user-b')

    // 回到 A：服务端慢/失败时必须用 A 自己的缓存，不能沿用 B 的值
    apiMock.get.mockRejectedValue(new Error('offline'))
    await store.loadForUser('user-a')
    expect(store.fontSize).toBe('lg')
  })

  it('切换账号时取消在途请求、清 timer 与全部 pending/tombstone', async () => {
    const pending = deferred<Record<string, unknown>>()
    apiMock.get.mockReturnValueOnce(pending.promise)
    const loading = store.loadForUser('user-a')
    const signal = apiMock.get.mock.calls[0][0] as AbortSignal
    expect(signal.aborted).toBe(false)

    store.setFontSize('lg')
    store.setFixedColumns('trial-balance', ['code'])
    store.clearFixedColumns('trial-balance')
    expect(store.hasPendingChanges).toBe(true)

    apiMock.get.mockResolvedValue(serverState({ revision: 5 }))
    const generationBefore = store.requestGeneration
    await store.loadForUser('user-b')

    expect(signal.aborted).toBe(true)
    expect(store.requestGeneration).toBeGreaterThan(generationBefore)
    expect(store.hasPendingChanges).toBe(false)
    expect(store.pendingPatch.fixedPageKeys).toEqual([])
    expect(store.fontSize).toBe('sm')

    // 旧 timer 不得在新账号下发出 PATCH
    await flushDebounce()
    expect(apiMock.patch).not.toHaveBeenCalled()

    pending.resolve(serverState({ font_size: 'lg', revision: 99 }))
    await loading
    expect(store.fontSize).toBe('sm')
    expect(store.ownerUserId).toBe('user-b')
  })

  it('晚到的 PATCH 响应按 owner+generation 丢弃，不写进新账号', async () => {
    await store.loadForUser('user-a')
    const pending = deferred<Record<string, unknown>>()
    apiMock.patch.mockReturnValueOnce(pending.promise)
    store.setFontSize('lg')
    await flushDebounce()
    expect(apiMock.patch).toHaveBeenCalledTimes(1)

    apiMock.get.mockResolvedValue(serverState({ font_size: 'xs', revision: 20 }))
    await store.loadForUser('user-b')
    expect(store.fontSize).toBe('xs')

    pending.resolve(serverState({ font_size: 'lg', revision: 77 }))
    await Promise.resolve()
    await Promise.resolve()

    expect(store.fontSize).toBe('xs')
    expect(store.serverPreferences.revision).toBe(20)
  })
})

describe('每项 mutation epoch', () => {
  it('首个 PATCH 在途时再改同一标量：成功只清发送 epoch，新值由下一代提交', async () => {
    await store.loadForUser('user-a')
    const first = deferred<Record<string, unknown>>()
    apiMock.patch.mockReturnValueOnce(first.promise)

    store.setDecimals(3)
    await flushDebounce()
    expect(lastPatchBody().decimals).toBe(3)

    store.setDecimals(5)
    expect(store.decimals).toBe(5)

    first.resolve(serverState({ decimals: 3, revision: 2 }))
    await Promise.resolve()
    await Promise.resolve()

    // 较新的本机值不被服务端响应抹掉
    expect(store.decimals).toBe(5)
    expect(store.pendingPatch.scalars).toContain('decimals')

    await flushDebounce()
    expect(apiMock.patch).toHaveBeenCalledTimes(2)
    expect(lastPatchBody().decimals).toBe(5)
    // 下一代以服务端刚确认的 revision 为基底
    expect(lastPatchBody().baseRevision).toBe(2)
    expect(store.hasPendingChanges).toBe(false)
  })

  it('在途覆盖同一 pageKey：新列进入下一代 PATCH', async () => {
    await store.loadForUser('user-a')
    const first = deferred<Record<string, unknown>>()
    apiMock.patch.mockReturnValueOnce(first.promise)

    store.setFixedColumns('trial-balance', ['code'])
    await flushDebounce()
    expect(lastPatchFixed()['trial-balance']).toEqual({ columns: ['code'] })

    store.setFixedColumns('trial-balance', ['code', 'name'])
    first.resolve(serverState({
      fixed_columns: { 'trial-balance': { columns: ['code'], saved_at: '2026-11-01T00:00:00+00:00' } },
      revision: 2,
    }))
    await Promise.resolve()
    await Promise.resolve()

    expect(store.getFixedColumns('trial-balance')).toEqual(['code', 'name'])
    await flushDebounce()
    expect(lastPatchFixed()['trial-balance']).toEqual({ columns: ['code', 'name'] })
  })

  it('在途删除同一 pageKey：tombstone 使下一代 PATCH 不含该页', async () => {
    apiMock.get.mockResolvedValue(serverState({
      fixed_columns: { 'trial-balance': { columns: ['code'], saved_at: '2026-11-01T00:00:00+00:00' } },
      revision: 3,
    }))
    await store.loadForUser('user-a')

    const first = deferred<Record<string, unknown>>()
    apiMock.patch.mockReturnValueOnce(first.promise)
    store.setFixedColumns('trial-balance', ['code', 'name'])
    await flushDebounce()

    expect(store.clearFixedColumns('trial-balance')).toBe(true)
    first.resolve(serverState({
      fixed_columns: { 'trial-balance': { columns: ['code', 'name'], saved_at: '2026-11-02T00:00:00+00:00' } },
      revision: 4,
    }))
    await Promise.resolve()
    await Promise.resolve()

    expect(store.getFixedColumns('trial-balance')).toEqual([])
    await flushDebounce()
    expect('trial-balance' in lastPatchFixed()).toBe(false)
  })

  it('在途修改另一个 pageKey：PATCH 体是 server base 与本机操作的合并', async () => {
    apiMock.get.mockResolvedValue(serverState({
      fixed_columns: { 'report-view:normal': { columns: ['row_code'], saved_at: '2026-11-01T00:00:00+00:00' } },
      revision: 2,
    }))
    await store.loadForUser('user-a')

    const first = deferred<Record<string, unknown>>()
    apiMock.patch.mockReturnValueOnce(first.promise)
    store.setFixedColumns('trial-balance', ['code'])
    await flushDebounce()

    expect(Object.keys(lastPatchFixed()).sort()).toEqual(['report-view:normal', 'trial-balance'])

    store.setFixedColumns('disclosure-editor:t1', ['label'])
    first.resolve(serverState({
      fixed_columns: {
        'report-view:normal': { columns: ['row_code'], saved_at: '2026-11-01T00:00:00+00:00' },
        'trial-balance': { columns: ['code'], saved_at: '2026-11-02T00:00:00+00:00' },
      },
      revision: 3,
    }))
    await Promise.resolve()
    await Promise.resolve()
    await flushDebounce()

    expect(Object.keys(lastPatchFixed()).sort())
      .toEqual(['disclosure-editor:t1', 'report-view:normal', 'trial-balance'])
    expect(store.getFixedColumns('report-view:normal')).toEqual(['row_code'])
    expect(store.getFixedColumns('trial-balance')).toEqual(['code'])
    expect(store.getFixedColumns('disclosure-editor:t1')).toEqual(['label'])
  })
})

describe('409 冲突只重放一次', () => {
  function conflict(current: Record<string, unknown>): Error {
    return new Conflict(current as never)
  }

  it('以服务端 current 为基底重放未变化的操作，重试成功即清空 pending', async () => {
    await store.loadForUser('user-a')
    apiMock.patch.mockRejectedValueOnce(conflict(serverState({ revision: 7, decimals: 2 })))

    store.setDecimals(3)
    await flushDebounce()

    expect(apiMock.patch).toHaveBeenCalledTimes(2)
    const retry = apiMock.patch.mock.calls[1][0] as Record<string, unknown>
    expect(retry.baseRevision).toBe(7)
    expect(retry.decimals).toBe(3)
    expect(store.decimals).toBe(3)
    expect(store.hasPendingChanges).toBe(false)
    expect(store.syncState).toBe('idle')
  })

  it('同一页的 tombstone 在 409 后仍然重放，并且不抹掉其他页', async () => {
    server = serverState({
      fixed_columns: {
        'trial-balance': { columns: ['code'], saved_at: '2026-11-01T00:00:00+00:00' },
        'report-view:normal': { columns: ['row_code'], saved_at: '2026-11-01T00:00:00+00:00' },
      },
      revision: 2,
    })
    await store.loadForUser('user-a')
    apiMock.patch.mockRejectedValueOnce(conflict(serverState({
      fixed_columns: {
        'trial-balance': { columns: ['code'], saved_at: '2026-11-01T00:00:00+00:00' },
        'report-view:normal': { columns: ['row_code', 'row_name'], saved_at: '2026-11-03T00:00:00+00:00' },
      },
      revision: 10,
    })))

    store.clearFixedColumns('trial-balance')
    await flushDebounce()

    expect(apiMock.patch).toHaveBeenCalledTimes(2)
    const retry = apiMock.patch.mock.calls[1][0] as Record<string, unknown>
    expect(retry.baseRevision).toBe(10)
    const retryFixed = retry.fixedColumns as Record<string, { columns: string[] }>
    expect('trial-balance' in retryFixed).toBe(false)
    // 另一台设备对别的页的修改保留在重放基底里
    expect(retryFixed['report-view:normal']).toEqual({ columns: ['row_code', 'row_name'] })
    expect(store.getFixedColumns('trial-balance')).toEqual([])
    expect(store.getFixedColumns('report-view:normal')).toEqual(['row_code', 'row_name'])
  })

  it('在途前移的 epoch 不进入旧代际重试，改由下一代 PATCH 提交', async () => {
    await store.loadForUser('user-a')
    const first = deferred<Record<string, unknown>>()
    apiMock.patch.mockReturnValueOnce(first.promise)

    store.setDecimals(3)
    await flushDebounce()
    expect(apiMock.patch).toHaveBeenCalledTimes(1)

    store.setDecimals(5)
    first.reject(conflict(serverState({ revision: 12, decimals: 2 })))
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()

    // 旧代际没有可重放项：不发第二次旧代际请求
    expect(apiMock.patch).toHaveBeenCalledTimes(1)
    expect(store.decimals).toBe(5)
    expect(store.syncState).toBe('pending')

    await flushDebounce()
    expect(apiMock.patch).toHaveBeenCalledTimes(2)
    expect(lastPatchBody().baseRevision).toBe(12)
    expect(lastPatchBody().decimals).toBe(5)
  })

  it('第二次 409 保留全部未确认 epoch 并显示待同步', async () => {
    await store.loadForUser('user-a')
    apiMock.patch.mockRejectedValue(conflict(serverState({ revision: 21, decimals: 2 })))

    store.setDecimals(4)
    store.setFixedColumns('trial-balance', ['code'])
    await flushDebounce()

    expect(apiMock.patch).toHaveBeenCalledTimes(2)
    expect(store.syncState).toBe('conflict')
    expect(store.syncMessage).toContain('待同步')
    expect(store.pendingPatch.scalars).toContain('decimals')
    expect(store.pendingPatch.fixedPageKeys).toContain('trial-balance')
    expect(store.decimals).toBe(4)
    expect(store.getFixedColumns('trial-balance')).toEqual(['code'])
  })
})

describe('固定列 100 键上限', () => {
  function hundredKeys(): Record<string, unknown> {
    const fixed: Record<string, unknown> = {}
    for (let index = 0; index < 100; index += 1) {
      fixed[`page-${String(index).padStart(3, '0')}`] = {
        columns: ['c1'],
        // saved_at 逐键变新：page-000 最旧
        saved_at: new Date(Date.UTC(2026, 0, 1 + index)).toISOString(),
      }
    }
    return fixed
  }

  it('新增第 101 张表时淘汰 saved_at 最旧的未挂载键，并提示用户', async () => {
    server = serverState({ fixed_columns: hundredKeys(), revision: 3 })
    await store.loadForUser('user-a')
    expect(Object.keys(store.fixedColumns)).toHaveLength(100)

    expect(store.setFixedColumns('page-new', ['x'])).toBe(true)
    expect(store.getFixedColumns('page-new')).toEqual(['x'])
    expect(store.getFixedColumns('page-000')).toEqual([])
    expect(store.getFixedColumns('page-001')).toEqual(['c1'])
    expect(store.syncMessage).toBe('已清除最久未修改的 1 张表的固定列设置')
    expect(Object.keys(store.fixedColumns)).toHaveLength(100)

    await flushDebounce()
    const sent = lastPatchFixed()
    expect(Object.keys(sent)).toHaveLength(100)
    expect('page-000' in sent).toBe(false)
    expect(sent['page-new']).toEqual({ columns: ['x'] })
  })

  it('全部键都已挂载时不保存本次修改，并提示已达上限', async () => {
    server = serverState({ fixed_columns: hundredKeys(), revision: 3 })
    await store.loadForUser('user-a')
    for (const pageKey of Object.keys(store.fixedColumns)) store.setFixedPageMounted(pageKey, true)

    expect(store.setFixedColumns('page-new', ['x'])).toBe(false)
    expect(store.syncMessage).toBe('固定列设置已达 100 张表的上限，本次未保存')
    expect(store.getFixedColumns('page-new')).toEqual([])
    expect(store.getFixedColumns('page-000')).toEqual(['c1'])
    expect(Object.keys(store.fixedColumns)).toHaveLength(100)
    expect(store.hasPendingChanges).toBe(false)

    await flushDebounce()
    expect(apiMock.patch).not.toHaveBeenCalled()
  })

  it('已存在的键改列不触发淘汰', async () => {
    server = serverState({ fixed_columns: hundredKeys(), revision: 3 })
    await store.loadForUser('user-a')

    expect(store.setFixedColumns('page-050', ['c1', 'c2'])).toBe(true)
    expect(store.syncMessage).toBeNull()
    expect(store.getFixedColumns('page-000')).toEqual(['c1'])
    expect(Object.keys(store.fixedColumns)).toHaveLength(100)
  })

  it('非法固定列输入被拒绝并提示，不进入 pending', async () => {
    await store.loadForUser('user-a')

    expect(store.setFixedColumns('', ['code'])).toBe(false)
    expect(store.setFixedColumns('k'.repeat(101), ['code'])).toBe(false)
    expect(store.setFixedColumns('trial-balance', ['code', 'code'])).toBe(false)
    expect(store.setFixedColumns('trial-balance', Array.from({ length: 21 }, (_, i) => `c${i}`))).toBe(false)
    expect(store.syncMessage).toBe('固定列设置不符合要求，未保存')
    expect(store.hasPendingChanges).toBe(false)

    await flushDebounce()
    expect(apiMock.patch).not.toHaveBeenCalled()
  })
})

describe('三层单位优先级与跟随项目', () => {
  it('override ?? 项目单位 ?? 元', async () => {
    await store.loadForUser('user-a')
    expect(store.amountUnit).toBe('yuan')

    projectStore.projectAmountUnit = 'wan'
    expect(store.amountUnit).toBe('wan')

    store.setUnit('qian')
    expect(store.amountUnit).toBe('qian')
    expect(store.amountUnitOverride).toBe('qian')

    store.followProjectUnit()
    expect(store.amountUnitOverride).toBeNull()
    expect(store.amountUnit).toBe('wan')

    projectStore.projectAmountUnit = null
    expect(store.amountUnit).toBe('yuan')
  })

  it('followProjectUnit 的补丁显式提交 amountUnitOverride=null（不是省略）', async () => {
    await store.loadForUser('user-a')
    store.setUnit('wan')
    await flushDebounce()

    store.followProjectUnit()
    await flushDebounce()

    const body = lastPatchBody()
    expect('amountUnitOverride' in body).toBe(true)
    expect(body.amountUnitOverride).toBeNull()
  })

  it('万元下 10000 显示 1.00、元下显示 10,000.00，原值不变', async () => {
    await store.loadForUser('user-a')
    store.setShowZero(false)

    store.setUnit('wan')
    expect(store.fmt(10000)).toBe('1.00')
    store.setUnit('yuan')
    expect(store.fmt(10000)).toBe('10,000.00')
    store.setDecimals(0)
    expect(store.fmt(-10000)).toBe('-10,000')
    expect(store.fmt(0)).toBe('-')
  })
})

describe('离线与重试', () => {
  it('GET 失败且无缓存：使用平台默认且不抛到登录流程', async () => {
    apiMock.get.mockRejectedValue(new Error('offline'))
    await expect(store.loadForUser('user-a')).resolves.toBeUndefined()

    expect(store.loadState).toBe('offline')
    expect(store.fontSize).toBe('sm')
    expect(store.amountUnit).toBe('yuan')
    expect(store.syncMessage).toContain('无法加载')
  })

  it('PATCH 网络失败保留 pending，retryPending 重发成功后清空', async () => {
    await store.loadForUser('user-a')
    apiMock.patch.mockRejectedValueOnce(new Error('network down'))

    store.setFontSize('md')
    await flushDebounce()

    expect(store.syncState).toBe('offline')
    expect(store.syncMessage).toContain('暂未同步')
    expect(store.pendingPatch.scalars).toContain('fontSize')
    expect(store.fontSize).toBe('md')

    await store.retryPending()
    expect(apiMock.patch).toHaveBeenCalledTimes(2)
    expect(store.hasPendingChanges).toBe(false)
    expect(store.syncState).toBe('idle')
    expect(store.fontSize).toBe('md')
  })

  it('被取消的请求不改状态（账号切换/组件卸载）', async () => {
    await store.loadForUser('user-a')
    const canceled = Object.assign(new Error('canceled'), { code: 'ERR_CANCELED' })
    apiMock.patch.mockRejectedValueOnce(canceled)

    store.setFontSize('md')
    await flushDebounce()

    expect(store.syncState).not.toBe('offline')
    expect(store.syncMessage).toBeNull()
  })
})
