/**
 * useEditStateMachine.spec.ts — 编辑状态机测试
 * [platform-ui-editing-consistency MVP-5]
 *
 * 验证：
 * - 初始状态为 pristine
 * - 所有状态转换（markDirty/startSave/saveDone/saveFailed/setConflict/setReadonly/setLocked/setArchived/reset）
 * - canEdit 在 readonly/locked/archived/saving 时为 false
 * - 保存失败不清 dirty（回退到 dirty）
 * - 编辑状态单调性：readonly/locked/archived 状态下 markDirty 无效
 */
import { describe, it, expect } from 'vitest'
import { useEditStateMachine } from '@/composables/useEditStateMachine'

describe('useEditStateMachine', () => {
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
    const { state, markDirty, startSave, saveDone } = useEditStateMachine()
    markDirty()
    startSave()
    saveDone()
    expect(state.value).toBe('saved')
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
    const { state, markDirty, setConflict } = useEditStateMachine()
    markDirty()
    setConflict()
    expect(state.value).toBe('conflict')
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
})
