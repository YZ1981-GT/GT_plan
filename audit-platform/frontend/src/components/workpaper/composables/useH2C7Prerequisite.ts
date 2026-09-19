/**
 * useH2C7Prerequisite — 监听 C7 控制测试结论，写入 H2A 前置状态
 *
 * 事件源：
 * - control:test-concluded（C 循环标准事件，wpCode=C7）
 * - control:c7-completed（兼容 H1 风格专用事件）
 */
import {
  computed,
  getCurrentInstance,
  onBeforeUnmount,
  type Ref,
  type ComputedRef,
} from 'vue'

export const H2A_C7_PREREQ_KEY = 'H2A-c7-prerequisite'

export interface H2C7PrerequisitePayload {
  wpCode?: string
  conclusion?: string | null
  timestamp?: string
  deviationSummary?: {
    totalControlPoints?: number
    effectiveCount?: number
    deviationAcceptableCount?: number
    ineffectiveCount?: number
    maxDeviationRate?: number
  }
  needsExtendedProcedures?: boolean
}

export interface H2C7PrerequisiteState {
  completed: boolean
  conclusion: string | null
  needsExtended: boolean
  ineffectiveCount: number
  maxDeviationRate: number
  timestamp: string | null
  raw: H2C7PrerequisitePayload | null
}

function _parseState(remark: string | null | undefined, conclusion: string | null | undefined): H2C7PrerequisiteState {
  const empty: H2C7PrerequisiteState = {
    completed: false,
    conclusion: null,
    needsExtended: false,
    ineffectiveCount: 0,
    maxDeviationRate: 0,
    timestamp: null,
    raw: null,
  }
  if (!remark && !conclusion) return empty
  try {
    const raw = remark ? JSON.parse(remark) as H2C7PrerequisitePayload : null
    const conc = (raw?.conclusion ?? conclusion ?? null) as string | null
    const needs =
      raw?.needsExtendedProcedures === true ||
      conc === '控制失效' ||
      (raw?.deviationSummary?.ineffectiveCount ?? 0) > 0
    return {
      completed: conclusion === 'Y' || !!conc || !!raw,
      conclusion: conc,
      needsExtended: needs,
      ineffectiveCount: raw?.deviationSummary?.ineffectiveCount ?? 0,
      maxDeviationRate: raw?.deviationSummary?.maxDeviationRate ?? 0,
      timestamp: raw?.timestamp ?? null,
      raw,
    }
  } catch {
    return {
      ...empty,
      completed: conclusion === 'Y' || !!remark,
      conclusion: conclusion || remark || null,
    }
  }
}

export function useH2C7Prerequisite(options: {
  allResponses: Ref<Map<string, any>>
  onPersist: (itemId: string, value: any, opts?: { conclusion?: string | null }) => void
  isReadonly?: Ref<boolean>
}) {
  const state: ComputedRef<H2C7PrerequisiteState> = computed(() => {
    const item = options.allResponses.value.get(H2A_C7_PREREQ_KEY)
    return _parseState(item?.remark, item?.conclusion)
  })

  function applyPayload(payload: H2C7PrerequisitePayload | undefined | null): void {
    if (!payload) return
    // 仅处理 C7；专用 c7-completed 事件无 wpCode 时也接受
    if (payload.wpCode && payload.wpCode !== 'C7') return

    const needsExtended =
      payload.needsExtendedProcedures === true ||
      payload.conclusion === '控制失效' ||
      (payload.deviationSummary?.ineffectiveCount ?? 0) > 0

    const stored: H2C7PrerequisitePayload = {
      wpCode: 'C7',
      conclusion: payload.conclusion ?? null,
      timestamp: payload.timestamp || new Date().toISOString(),
      deviationSummary: payload.deviationSummary,
      needsExtendedProcedures: needsExtended,
    }

    if (options.isReadonly?.value) {
      const next = new Map(options.allResponses.value)
      next.set(H2A_C7_PREREQ_KEY, {
        item_id: H2A_C7_PREREQ_KEY,
        conclusion: 'Y',
        remark: JSON.stringify(stored),
      })
      options.allResponses.value = next
      return
    }
    options.onPersist(H2A_C7_PREREQ_KEY, stored, { conclusion: 'Y' })
  }

  function onTestConcluded(e: Event): void {
    applyPayload((e as CustomEvent).detail as H2C7PrerequisitePayload)
  }

  function onC7Completed(e: Event): void {
    const detail = (e as CustomEvent).detail as H2C7PrerequisitePayload | undefined
    applyPayload({ ...(detail || {}), wpCode: 'C7' })
  }

  function register(): void {
    window.addEventListener('control:test-concluded', onTestConcluded)
    window.addEventListener('control:c7-completed', onC7Completed)
  }

  function unregister(): void {
    window.removeEventListener('control:test-concluded', onTestConcluded)
    window.removeEventListener('control:c7-completed', onC7Completed)
  }

  // 在组件 setup 中自动注册；单测直接调 applyPayload 时无实例则跳过
  if (getCurrentInstance()) {
    register()
    onBeforeUnmount(unregister)
  }

  return {
    state,
    applyPayload,
    register,
    unregister,
    H2A_C7_PREREQ_KEY,
  }
}
