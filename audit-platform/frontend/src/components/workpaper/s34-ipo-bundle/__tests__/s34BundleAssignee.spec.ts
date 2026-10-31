/**
 * s34BundleAssignee.spec.ts — P2.3 bundle tab 委派负责人展示测试
 *
 * Feature: s-cycle-linkage-trimming-and-component-wiring, P2.3
 *
 * 2026-10-31 勘误：生产的 buildWpIdMap 已拆成「仅 wp_id 映射」，
 * 负责人映射改由 shared/bundleAssignee 的 buildBundleAssigneeMap 承担。
 * 原测试还按旧的 { wpIdMap, assigneeMap } 返回形状解构，因此运行时拿到
 * undefined；这与两个 shared 源文件未入库是同一次重构的两个独立交付缺口。
 */
import { describe, expect, it } from 'vitest'
import { buildWpIdMap } from '../../composables/useS34BundleState'
import { buildBundleAssigneeMap } from '../../shared/bundleAssignee'

describe('P2.3 wpIdMap / assigneeMap 提取', () => {
  const ITEMS = [
    {
      id: 'idx-1',
      wp_code: 'S34-2',
      wp_id: 'wp-s34-2',
      assigned_to: 'staff-aaa-111',
      assigned_to_name: '张三',
    },
    { id: 'idx-2', wp_code: 'S34-3', wp_id: 'wp-s34-3', assigned_to: null },
    { id: 'idx-3', wp_code: 'S34-16', wp_id: 'wp-s34-16', assigned_to: 'staff-bbb-222' },
    { id: 'idx-4', wp_code: 'S34-4', wp_id: 'wp-s34-4' }, // assigned_to 完全缺失
    { id: 'idx-5', wp_code: 'D4', wp_id: 'wp-d4', assigned_to: 'staff-ccc-333' }, // 非 S34
    { id: 'idx-6', wp_code: 'S34-25', wp_id: null, assigned_to: 'staff-ddd-444' }, // 无 wp_id
  ]

  it('wpIdMap 只含有 wp_id 的 S34-* 条目', () => {
    const wpIdMap = buildWpIdMap(ITEMS)
    expect(Object.keys(wpIdMap).sort()).toEqual(['S34-16', 'S34-2', 'S34-3', 'S34-4'])
    expect(wpIdMap['S34-2']).toBe('wp-s34-2')
  })

  it('assigneeMap 只含有 assigned_to 且有 wp_id 的 S34-* 条目', () => {
    const assigneeMap = buildBundleAssigneeMap(ITEMS)
    expect(Object.keys(assigneeMap).sort()).toEqual(['S34-16', 'S34-2'])
    expect(assigneeMap['S34-2']).toEqual({ staffId: 'staff-aaa-111', displayName: '张三' })
    expect(assigneeMap['S34-16']).toEqual({ staffId: 'staff-bbb-222', displayName: 'staff-bb' })
  })

  it('assigned_to 为 null 或缺失时不进 assigneeMap', () => {
    const assigneeMap = buildBundleAssigneeMap(ITEMS)
    expect(assigneeMap['S34-3']).toBeUndefined()
    expect(assigneeMap['S34-4']).toBeUndefined()
  })

  it('非 S34 条目或没有 wp_id 的条目不进任一映射', () => {
    const wpIdMap = buildWpIdMap(ITEMS)
    const assigneeMap = buildBundleAssigneeMap(ITEMS)
    expect(wpIdMap['D4']).toBeUndefined()
    expect(assigneeMap['D4']).toBeUndefined()
    expect(wpIdMap['S34-25']).toBeUndefined()
    expect(assigneeMap['S34-25']).toBeUndefined()
  })

  it('空输入返回两个空映射', () => {
    expect(buildWpIdMap([])).toEqual({})
    expect(buildBundleAssigneeMap([])).toEqual({})
  })
})

describe('P2.3 负责人显示名解析逻辑', () => {
  it('姓名优先于用户名和 ID', () => {
    const map = buildBundleAssigneeMap([{
      id: 'idx',
      wp_id: 'wp',
      wp_code: 'S34-2',
      assigned_to: 'staff-aaa-111',
      assigned_to_name: '张三',
      assigned_to_username: 'zhangsan',
    }])
    expect(map['S34-2']?.displayName).toBe('张三')
  })

  it('姓名为空时使用用户名', () => {
    const map = buildBundleAssigneeMap([{
      id: 'idx',
      wp_id: 'wp',
      wp_code: 'S34-2',
      assigned_to: 'staff-aaa-111',
      assigned_to_name: ' ',
      assigned_to_username: 'zhangsan',
    }])
    expect(map['S34-2']?.displayName).toBe('zhangsan')
  })

  it('姓名和用户名都缺失时回退 ID 前八位', () => {
    const map = buildBundleAssigneeMap([{
      id: 'idx',
      wp_id: 'wp',
      wp_code: 'S34-2',
      assigned_to: 'abcdef12-3456-7890',
    }])
    expect(map['S34-2']?.displayName).toBe('abcdef12')
  })
})