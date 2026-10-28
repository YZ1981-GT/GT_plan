/**
 * s34BundleAssignee.spec.ts — P2.3 bundle tab 委派负责人展示测试
 *
 * Feature: s-cycle-linkage-trimming-and-component-wiring, P2.3
 *
 * 验证：
 * 1. buildWpIdMap 同时提取 wpIdMap 和 assigneeMap
 * 2. 有 assigned_to 的 tab 显示负责人名字
 * 3. 无 assigned_to 的 tab 不显示负责人
 * 4. assigned_to 有值但 staff name 找不到时回退 id 前 8 位
 */
import { describe, expect, it } from 'vitest'
import { buildWpIdMap } from '../../composables/useS34BundleState'

describe('P2.3 buildWpIdMap — assigneeMap 提取', () => {
  const ITEMS = [
    { id: 'idx-1', wp_code: 'S34-2', wp_id: 'wp-s34-2', assigned_to: 'staff-aaa-111' },
    { id: 'idx-2', wp_code: 'S34-3', wp_id: 'wp-s34-3', assigned_to: null },
    { id: 'idx-3', wp_code: 'S34-16', wp_id: 'wp-s34-16', assigned_to: 'staff-bbb-222' },
    { id: 'idx-4', wp_code: 'S34-4', wp_id: 'wp-s34-4' },  // assigned_to 完全缺失
    { id: 'idx-5', wp_code: 'D4', wp_id: 'wp-d4', assigned_to: 'staff-ccc-333' },  // 非 S34
    { id: 'idx-6', wp_code: 'S34-25', wp_id: null, assigned_to: 'staff-ddd-444' },  // 无 wp_id
  ]

  it('wpIdMap 只含有 wp_id 的 S34-* 条目', () => {
    const { wpIdMap } = buildWpIdMap(ITEMS)
    expect(Object.keys(wpIdMap).sort()).toEqual(['S34-16', 'S34-2', 'S34-3', 'S34-4'])
    expect(wpIdMap['S34-2']).toBe('wp-s34-2')
  })

  it('assigneeMap 只含有 assigned_to 且有 wp_id 的 S34-* 条目', () => {
    const { assigneeMap } = buildWpIdMap(ITEMS)
    expect(Object.keys(assigneeMap).sort()).toEqual(['S34-16', 'S34-2'])
    expect(assigneeMap['S34-2']).toBe('staff-aaa-111')
    expect(assigneeMap['S34-16']).toBe('staff-bbb-222')
  })

  it('assigned_to 为 null 的不进 assigneeMap', () => {
    const { assigneeMap } = buildWpIdMap(ITEMS)
    expect(assigneeMap['S34-3']).toBeUndefined()
  })

  it('assigned_to 缺失（undefined）的不进 assigneeMap', () => {
    const { assigneeMap } = buildWpIdMap(ITEMS)
    expect(assigneeMap['S34-4']).toBeUndefined()
  })

  it('非 S34 条目不进任何 map', () => {
    const { wpIdMap, assigneeMap } = buildWpIdMap(ITEMS)
    expect(wpIdMap['D4']).toBeUndefined()
    expect(assigneeMap['D4']).toBeUndefined()
  })

  it('wp_id 为 null 的条目不进任何 map（即使有 assigned_to）', () => {
    const { wpIdMap, assigneeMap } = buildWpIdMap(ITEMS)
    expect(wpIdMap['S34-25']).toBeUndefined()
    expect(assigneeMap['S34-25']).toBeUndefined()
  })

  it('空输入返回两个空 map', () => {
    const { wpIdMap, assigneeMap } = buildWpIdMap([])
    expect(wpIdMap).toEqual({})
    expect(assigneeMap).toEqual({})
  })
})

describe('P2.3 负责人显示名解析逻辑', () => {
  /**
   * 等价于 GtS34Bundle.vue 中 tabAssigneeName 的纯函数版本。
   * 实际组件里这个函数读 ref，这里用纯函数测逻辑。
   */
  function resolveAssigneeName(
    staffId: string | undefined,
    staffNameMap: Record<string, string>,
  ): string {
    if (!staffId) return ''
    return staffNameMap[staffId] || staffId.slice(0, 8)
  }

  it('有 staff name 时返回 staff name', () => {
    expect(resolveAssigneeName('staff-aaa-111', { 'staff-aaa-111': '张三' })).toBe('张三')
  })

  it('无 assigned_to（undefined）时返回空字符串', () => {
    expect(resolveAssigneeName(undefined, { 'staff-aaa-111': '张三' })).toBe('')
  })

  it('有 assigned_to 但 staffNameMap 找不到时回退 id 前 8 位', () => {
    expect(resolveAssigneeName('abcdef12-3456-7890', {})).toBe('abcdef12')
  })

  it('staffNameMap 里 staff_name 为空字符串时也回退 id 前 8 位', () => {
    // staff_name 空串 = 假值，回退
    expect(resolveAssigneeName('staff-xxx', { 'staff-xxx': '' })).toBe('staff-xx')
  })
})
