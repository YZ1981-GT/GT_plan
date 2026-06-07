/**
 * useEditStateMachine.spec.ts — 编辑状态机测试
 * [platform-ui-editing-consistency P0-5]
 *
 * 验证：
 * - 初始状态为 pristine
 * - 所有状态转换（markDirty/startSave/saveDone/saveFailed/setConflict/setReadonly/setLocked/setArchived/reset）
 * - canEdit 在 readonly/locked/archived/saving 时为 false
 * - 保存失败不清 dirty（回退到 dirty）
 * - 编辑状态单调性：readonly/locked/archived 状态下 markDirty 无效
 * - shouldBlockLeave: dirty/saving 时返回 true
 * - statusText 中文文案
 * - savedResetDelay 自动回归
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useEditStateMachine } from '@/composables/useEditStateMachine'

// Mock vue's onBeforeUnmount to be a no-op in test
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue')
  return {
    ...actual,
    onBeforeUnmount: vi.fn(),
  }
})

describe('useEditStateMachine', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('初始状态为 pristine', () => {
    const { state, isDirty, isSaving, canEdit } = useEditStateMachine()
    expect(state.value).toBe('pristine')
    expect(isDirty.value).toBe(false)
    expect(isSaving.value).toBe(false)
    expect(canEdit.value).toBe(true)
  })

  it('支持自定义初始状态', () => {
    const { state } = useEditStateMachine('readonly')
    expect(state.value).toBe('readonly')
  })

  // --- 正常编辑流程 ---
  it('pristine → markDirty → dirty', () => {
    const { state, markDirty, isDirty } = useEditStateMachine()
    markDirty()
    expect(state.value).toBe('dirty')
    expect(isDirty.value).toBe(true)
  })

  it('dirty → startSave → saving', () => {
    const { state, markDirty, startSave, isSaving } = useEditStateMachine()
    markDirty()
    startSave()
    expect(state.value).toBe('saving')
    expect(isSaving.value).toBe(true)
  })

  it('saving → saveDone → saved', () => {
    const { state, markDirty, startSave, saveDone, isSaved } = useEditStateMachine()
    markDirty()
    startSave()
    saveDone()
    expect(state.value).toBe('saved')
    expect(isSaved.value).toBe(true)
  })

  // --- 保存失败回退 ---
  it('saving → saveFailed → dirty（不清 dirty）', () => {
    const { state, markDirty, startSave, saveFailed, isDirty } = useEditStateMachine()
    markDirty()
    startSave()
    saveFailed()
    expect(state.value).toBe('dirty')
    expect(isDirty.value).toBe(true)
  })

  // --- canEdit 计算 ---
  it('canEdit: readonly → false', () => {
    const { canEdit, setReadonly } = useEditStateMachine()
    setReadonly()
    expect(canEdit.value).toBe(false)
  })

  it('canEdit: locked → false', () => {
    const { canEdit, setLocked } = useEditStateMachine()
    setLocked()
    expect(canEdit.value).toBe(false)
  })

  it('canEdit: archived → false', () => {
    const { canEdit, setArchived } = useEditStateMachine()
    setArchived()
    expect(canEdit.value).toBe(false)
  })

  it('canEdit: saving → false', () => {
    const { canEdit, markDirty, startSave } = useEditStateMachine()
    markDirty()
    startSave()
    expect(canEdit.value).toBe(false)
  })

  // --- 编辑状态单调性：不可编辑状态下 markDirty 无效 ---
  it('readonly 下 markDirty 无效', () => {
    const { state, setReadonly, markDirty } = useEditStateMachine()
    setReadonly()
    markDirty()
    expect(state.value).toBe('readonly')
  })

  it('locked 下 markDirty 无效', () => {
    const { state, setLocked, markDirty } = useEditStateMachine()
    setLocked()
    markDirty()
    expect(state.value).toBe('locked')
  })

  it('archived 下 markDirty 无效', () => {
    const { state, setArchived, markDirty } = useEditStateMachine()
    setArchived()
    markDirty()
    expect(state.value).toBe('archived')
  })

  // --- setConflict ---
  it('任意状态 → setConflict → conflict', () => {
    const { state, markDirty, setConflict, isConflict } = useEditStateMachine()
    markDirty()
    setConflict()
    expect(state.value).toBe('conflict')
    expect(isConflict.value).toBe(true)
  })

  // --- reset ---
  it('reset → pristine', () => {
    const { state, markDirty, startSave, reset } = useEditStateMachine()
    markDirty()
    startSave()
    reset()
    expect(state.value).toBe('pristine')
  })

  // --- startSave 只在 dirty 时生效 ---
  it('pristine 下 startSave 无效', () => {
    const { state, startSave } = useEditStateMachine()
    startSave()
    expect(state.value).toBe('pristine')
  })

  it('saved 下 startSave 无效', () => {
    const { state, markDirty, startSave, saveDone } = useEditStateMachine()
    markDirty()
    startSave()
    saveDone()
    startSave()
    expect(state.value).toBe('saved')
  })

  // --- shouldBlockLeave ---
  it('dirty 时 shouldBlockLeave 返回 true', () => {
    const { markDirty, shouldBlockLeave } = useEditStateMachine()
    markDirty()
    expect(shouldBlockLeave()).toBe(true)
  })

  it('saving 时 shouldBlockLeave 返回 true', () => {
    const { markDirty, startSave, shouldBlockLeave } = useEditStateMachine()
    markDirty()
    startSave()
    expect(shouldBlockLeave()).toBe(true)
  })

  it('pristine 时 shouldBlockLeave 返回 false', () => {
    const { shouldBlockLeave } = useEditStateMachine()
    expect(shouldBlockLeave()).toBe(false)
  })

  it('saved 时 shouldBlockLeave 返回 false', () => {
    const { markDirty, startSave, saveDone, shouldBlockLeave } = useEditStateMachine()
    markDirty()
    startSave()
    saveDone()
    expect(shouldBlockLeave()).toBe(false)
  })

  // --- statusText ---
  it('statusText 对应正确的中文文案', () => {
    const fsm = useEditStateMachine()
    expect(fsm.statusText.value).toBe('')

    fsm.markDirty()
    expect(fsm.statusText.value).toBe('有未保存的修改')

    fsm.startSave()
    expect(fsm.statusText.value).toBe('保存中…')

    fsm.saveDone()
    expect(fsm.statusText.value).toBe('已保存')

    fsm.setConflict()
    expect(fsm.statusText.value).toBe('数据冲突，请刷新')

    fsm.setReadonly()
    expect(fsm.statusText.value).toBe('只读')

    fsm.setLocked()
    expect(fsm.statusText.value).toBe('已锁定')

    fsm.setArchived()
    expect(fsm.statusText.value).toBe('已归档')
  })

  // --- isReadonly computed ---
  it('isReadonly: readonly/locked/archived 为 true', () => {
    const fsm1 = useEditStateMachine('readonly')
    expect(fsm1.isReadonly.value).toBe(true)

    const fsm2 = useEditStateMachine('locked')
    expect(fsm2.isReadonly.value).toBe(true)

    const fsm3 = useEditStateMachine('archived')
    expect(fsm3.isReadonly.value).toBe(true)
  })

  it('isReadonly: dirty/saving/saved 为 false', () => {
    const fsm = useEditStateMachine('dirty')
    expect(fsm.isReadonly.value).toBe(false)
  })

  // --- savedResetDelay ---
  it('saved 后 savedResetDelay 自动回归 pristine', () => {
    const { state, markDirty, startSave, saveDone } = useEditStateMachine('pristine', {
      savedResetDelay: 1000,
    })
    markDirty()
    startSave()
    saveDone()
    expect(state.value).toBe('saved')

    vi.advanceTimersByTime(999)
    expect(state.value).toBe('saved')

    vi.advanceTimersByTime(1)
    expect(state.value).toBe('pristine')
  })

  it('savedResetDelay=0 时不自动回归', () => {
    const { state, markDirty, startSave, saveDone } = useEditStateMachine('pristine', {
      savedResetDelay: 0,
    })
    markDirty()
    startSave()
    saveDone()
    expect(state.value).toBe('saved')

    vi.advanceTimersByTime(10000)
    expect(state.value).toBe('saved')
  })

  it('saved 后再次 markDirty 取消自动回归 timer', () => {
    const { state, markDirty, startSave, saveDone } = useEditStateMachine('pristine', {
      savedResetDelay: 2000,
    })
    markDirty()
    startSave()
    saveDone()
    expect(state.value).toBe('saved')

    // 在 timer 触发前再次标记 dirty
    vi.advanceTimersByTime(500)
    markDirty()
    expect(state.value).toBe('dirty')

    // 原 timer 到期不应回到 pristine
    vi.advanceTimersByTime(2000)
    expect(state.value).toBe('dirty')
  })

  // --- getLeaveMessage ---
  it('getLeaveMessage 返回默认文案', () => {
    const { getLeaveMessage } = useEditStateMachine()
    expect(getLeaveMessage()).toBe('页面有未保存的修改，确定离开吗？')
  })

  it('getLeaveMessage 返回自定义文案', () => {
    const { getLeaveMessage } = useEditStateMachine('pristine', {
      leaveMessage: '自定义提示',
    })
    expect(getLeaveMessage()).toBe('自定义提示')
  })
})
