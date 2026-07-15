/**
 * 共享测试夹具 — advanced-query-disclosure-integration-hardening spec
 *
 * 提供 sessionStorage mock、fake timers、响应式 DraftContext、
 * manual/provenance/trace cell 构造器和 capability response fixture。
 *
 * Requirements: 8.1–8.5, 9.2, 10.1
 */
import { ref, type Ref } from 'vue'
import { vi } from 'vitest'
import type { DraftContext } from '../../useAutoSave'

// ---------------------------------------------------------------------------
// 1. Mock sessionStorage
// ---------------------------------------------------------------------------

export interface MockSessionStorage {
  getItem: ReturnType<typeof vi.fn>
  setItem: ReturnType<typeof vi.fn>
  removeItem: ReturnType<typeof vi.fn>
  clear: ReturnType<typeof vi.fn>
  key: ReturnType<typeof vi.fn>
  length: number
  _store: Map<string, string>
}

/**
 * 创建一个与 Web Storage API 兼容的 mock sessionStorage。
 * 内部使用 Map 实现，所有方法均为 vi.fn() 可断言。
 */
export function createMockSessionStorage(): MockSessionStorage {
  const store = new Map<string, string>()
  const mock: MockSessionStorage = {
    _store: store,
    length: 0,
    getItem: vi.fn((key: string) => store.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store.set(key, value)
      mock.length = store.size
    }),
    removeItem: vi.fn((key: string) => {
      store.delete(key)
      mock.length = store.size
    }),
    clear: vi.fn(() => {
      store.clear()
      mock.length = 0
    }),
    key: vi.fn((index: number) => {
      const keys = [...store.keys()]
      return keys[index] ?? null
    }),
  }
  return mock
}

// ---------------------------------------------------------------------------
// 2. Fake timers helper
// ---------------------------------------------------------------------------

export interface FakeTimersHelper {
  /** 推进 fake timer 指定毫秒数 */
  advanceByMs: (ms: number) => Promise<void>
  /** 恢复真实 timer（在 afterEach 中调用） */
  restore: () => void
}

/**
 * 激活 vitest fake timers 并返回便捷 helper。
 * 调用方应在 beforeEach 中调用 `useFakeTimers()`，afterEach 中调用 `helper.restore()`。
 */
export function useFakeTimers(): FakeTimersHelper {
  vi.useFakeTimers()
  return {
    advanceByMs: (ms: number) => vi.advanceTimersByTimeAsync(ms),
    restore: () => {
      vi.clearAllTimers()
      vi.useRealTimers()
    },
  }
}

// ---------------------------------------------------------------------------
// 3. Reactive DraftContext
// ---------------------------------------------------------------------------

export interface ReactiveContext {
  project_id: Ref<string>
  year: Ref<number>
  section: Ref<string>
  /** 作为 DraftContext 对象使用（computed 快照） */
  toContext: () => DraftContext
}

/**
 * 创建响应式 project_id/year/section 引用集合，可选覆盖默认值。
 */
export function createReactiveContext(overrides?: Partial<DraftContext>): ReactiveContext {
  const project_id = ref(overrides?.project_id ?? 'test-project-001')
  const year = ref(overrides?.year ?? 2026)
  const section = ref(overrides?.section ?? 'revenue-recognition')

  return {
    project_id,
    year,
    section,
    toContext: () => ({
      project_id: project_id.value,
      year: year.value,
      section: section.value,
    }),
  }
}

// ---------------------------------------------------------------------------
// 4. Cell 构造器 (DisclosureCell 形状)
// ---------------------------------------------------------------------------

export interface DisclosureCell<T = unknown> {
  value: T
  manual?: boolean
  provenance?: Array<Record<string, unknown>>
  trace?: Array<Record<string, unknown>>
  addr_id?: string
}

/**
 * 创建带 manual=true 标记的单元格。
 */
export function createCellWithManual<T>(value: T, manual = true): DisclosureCell<T> {
  return { value, manual }
}

/**
 * 创建带 provenance 数组的单元格。
 */
export function createCellWithProvenance<T>(
  value: T,
  provenance: Array<Record<string, unknown>>,
): DisclosureCell<T> {
  return { value, manual: false, provenance }
}

/**
 * 创建带 trace 数组的单元格。
 */
export function createCellWithTrace<T>(
  value: T,
  trace: Array<Record<string, unknown>>,
): DisclosureCell<T> {
  return { value, manual: false, trace }
}

/**
 * 创建带 addr_id 的单元格。
 */
export function createCellWithAddrId<T>(value: T, addrId: string): DisclosureCell<T> {
  return { value, manual: false, addr_id: addrId }
}

// ---------------------------------------------------------------------------
// 5. Capability response
// ---------------------------------------------------------------------------

export interface CapabilityResponse {
  advanced_query: boolean
  disclosure_writeback: boolean
  historical_upload: boolean
  historical_upload_reason?: string
}

/**
 * 创建 capability API 响应 mock，默认 historical_upload=false。
 */
export function createCapabilityResponse(overrides?: Partial<CapabilityResponse>): CapabilityResponse {
  return {
    advanced_query: true,
    disclosure_writeback: true,
    historical_upload: false,
    historical_upload_reason: '历史 Word/PDF 解析尚未实现',
    ...overrides,
  }
}
