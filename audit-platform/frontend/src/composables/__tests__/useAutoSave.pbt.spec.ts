import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as fc from 'fast-check'
import { nextTick, ref } from 'vue'

const mocks = vi.hoisted(() => ({ confirm: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessageBox: { confirm: mocks.confirm } }))
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue')
  return {
    ...actual,
    onMounted: (fn: () => void) => fn(),
    onBeforeUnmount: vi.fn(),
  }
})

import {
  buildDisclosureDraftKey,
  type DraftContext,
  useAutoSave,
} from '../useAutoSave'

const contextArb = fc.record({
  project_id: fc.stringMatching(/^[a-z0-9-]{1,16}$/),
  year: fc.integer({ min: 2000, max: 2100 }),
  section: fc.stringMatching(/^[a-zA-Z0-9._-]{1,20}$/),
})

describe('Feature: advanced-query-disclosure-integration-hardening, Property P10', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    sessionStorage.clear()
    mocks.confirm.mockReset().mockRejectedValue(new Error('cancel'))
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
  })

  it('不同 project/year/section 三元组产生隔离 key', () => {
    fc.assert(fc.property(contextArb, contextArb, (left, right) => {
      fc.pre(JSON.stringify(left) !== JSON.stringify(right))
      expect(buildDisclosureDraftKey(left)).not.toBe(buildDisclosureDraftKey(right))
    }), { numRuns: 40 })
  })

  it('fake timers 切换后只写当前 key，且 clear 不误删旧 key', async () => {
    const context = ref<DraftContext>({ project_id: 'p1', year: 2024, section: 's1' })
    const key = ref(buildDisclosureDraftKey(context.value))
    let value = 'old-context'
    const autosave = useAutoSave(key, () => ({ value }), vi.fn(), {
      interval: 1000,
      context,
    })

    await vi.advanceTimersByTimeAsync(1000)
    const oldStorageKey = `autosave_${key.value}`
    expect(JSON.parse(sessionStorage.getItem(oldStorageKey)!).data.value).toBe('old-context')

    context.value = { project_id: 'p2', year: 2025, section: 's2' }
    key.value = buildDisclosureDraftKey(context.value)
    value = 'new-context'
    await nextTick()
    await vi.advanceTimersByTimeAsync(1000)

    const newStorageKey = `autosave_${key.value}`
    expect(JSON.parse(sessionStorage.getItem(newStorageKey)!).data.value).toBe('new-context')
    autosave.clearDraft()
    expect(sessionStorage.getItem(newStorageKey)).toBeNull()
    expect(sessionStorage.getItem(oldStorageKey)).not.toBeNull()
  })

  it('拒绝上下文不匹配 envelope，且空三元组不写 global', () => {
    const context = ref<DraftContext>({ project_id: 'p1', year: 2024, section: 's1' })
    const key = ref(buildDisclosureDraftKey(context.value))
    const setData = vi.fn()
    const autosave = useAutoSave(key, () => ({ value: 1 }), setData, { context })
    sessionStorage.setItem(`autosave_${key.value}`, JSON.stringify({
      context: { project_id: 'p2', year: 2024, section: 's1' },
      data: { value: 2 }, savedAt: 1, version: 1,
    }))

    expect(autosave.restoreDraft()).toBe(false)
    expect(setData).not.toHaveBeenCalled()
    context.value = { project_id: '', year: 0, section: '' }
    key.value = buildDisclosureDraftKey(context.value)
    expect(autosave.saveDraft()).toBe(false)
    expect(sessionStorage.getItem('autosave_global')).toBeNull()
  })

  it('字符串 key 调用保持 legacy payload 兼容', () => {
    const setData = vi.fn()
    const autosave = useAutoSave('legacy-form', () => ({ value: 7 }), setData)
    expect(autosave.saveDraft()).toBe(true)
    const payload = JSON.parse(sessionStorage.getItem('autosave_legacy-form')!)
    expect(payload).toMatchObject({ data: { value: 7 } })
    expect(payload.context).toBeUndefined()
    expect(autosave.restoreDraft()).toBe(true)
    expect(setData).toHaveBeenCalledWith({ value: 7 })
  })

  it('旧确认晚到不会恢复到新章节', async () => {
    let resolveConfirm!: () => void
    mocks.confirm.mockReturnValue(new Promise<void>((resolve) => { resolveConfirm = resolve }))
    const oldContext: DraftContext = { project_id: 'p1', year: 2024, section: 's1' }
    const context = ref<DraftContext>(oldContext)
    const key = ref(buildDisclosureDraftKey(oldContext))
    sessionStorage.setItem(`autosave_${key.value}`, JSON.stringify({
      context: oldContext,
      data: { value: 'old' }, savedAt: Date.now(), version: 1,
    }))
    const setData = vi.fn()
    useAutoSave(key, () => ({ value: 'current' }), setData, { context })

    context.value = { project_id: 'p1', year: 2024, section: 's2' }
    key.value = buildDisclosureDraftKey(context.value)
    await nextTick()
    resolveConfirm()
    await Promise.resolve()
    await Promise.resolve()

    expect(setData).not.toHaveBeenCalled()
    expect(sessionStorage.getItem(`autosave_${buildDisclosureDraftKey(oldContext)}`)).not.toBeNull()
  })
})
