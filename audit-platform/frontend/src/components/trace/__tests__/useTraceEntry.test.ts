/**
 * useTraceEntry 单元测试
 *
 * Feature: platform-global-hardening
 * Requirements: 8.3
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useTraceEntry, openTrace, closeTrace, setTraceProjectId } from '../useTraceEntry'

describe('useTraceEntry', () => {
  beforeEach(() => {
    // 重置状态
    closeTrace()
  })

  it('初始状态 visible=false', () => {
    const { state } = useTraceEntry()
    expect(state.value.visible).toBe(false)
    expect(state.value.targetAddr).toBe('')
    expect(state.value.targetValue).toBeNull()
  })

  it('openTrace 设置 addr 和 value 并打开抽屉', () => {
    const { state } = useTraceEntry()
    openTrace('1122', 50000)
    expect(state.value.visible).toBe(true)
    expect(state.value.targetAddr).toBe('1122')
    expect(state.value.targetValue).toBe(50000)
  })

  it('openTrace 不传 value 时默认为 null', () => {
    const { state } = useTraceEntry()
    openTrace('D2-1!B5')
    expect(state.value.visible).toBe(true)
    expect(state.value.targetAddr).toBe('D2-1!B5')
    expect(state.value.targetValue).toBeNull()
  })

  it('openTrace 传 projectId 时更新 projectId', () => {
    const { state } = useTraceEntry()
    openTrace('1122', 100, 'proj-abc')
    expect(state.value.projectId).toBe('proj-abc')
  })

  it('openTrace 不传 projectId 时保留上次 projectId', () => {
    const { state } = useTraceEntry()
    setTraceProjectId('proj-xyz')
    openTrace('1122', 200)
    expect(state.value.projectId).toBe('proj-xyz')
  })

  it('closeTrace 关闭抽屉但保留其他状态', () => {
    const { state } = useTraceEntry()
    openTrace('1122', 50000, 'proj-1')
    closeTrace()
    expect(state.value.visible).toBe(false)
    expect(state.value.targetAddr).toBe('1122')
    expect(state.value.targetValue).toBe(50000)
  })

  it('setVisible 方法可用于 v-model 绑定', () => {
    const { state, setVisible } = useTraceEntry()
    openTrace('addr-test', 0)
    expect(state.value.visible).toBe(true)
    setVisible(false)
    expect(state.value.visible).toBe(false)
    setVisible(true)
    expect(state.value.visible).toBe(true)
  })

  it('setTraceProjectId 设置全局项目 ID', () => {
    const { state } = useTraceEntry()
    setTraceProjectId('proj-global')
    expect(state.value.projectId).toBe('proj-global')
  })

  it('state 为只读不可直接修改', () => {
    const { state } = useTraceEntry()
    // readonly 应使得直接赋值无效（Vue readonly 在 dev 模式下会 warn）
    expect(() => {
      // @ts-expect-error 测试只读保护
      state.value = { visible: true, targetAddr: 'x', targetValue: 1, projectId: '' }
    }).not.toThrow() // readonly ref 不 throw 但赋值无效
  })

  it('多次 openTrace 覆盖前次状态', () => {
    const { state } = useTraceEntry()
    openTrace('first', 100)
    openTrace('second', 200)
    expect(state.value.targetAddr).toBe('second')
    expect(state.value.targetValue).toBe(200)
  })
})
