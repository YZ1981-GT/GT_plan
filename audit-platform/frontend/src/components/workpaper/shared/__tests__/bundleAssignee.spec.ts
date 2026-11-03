import { describe, expect, it } from 'vitest'
import { buildBundleAssigneeMap } from '../bundleAssignee'

/**
 * 四个 S bundle 共用同一映射器，但每个 state composable 都是独立导入边。
 * 2026-10-31 曾发生「四个已提交调用方都指向未提交模块」而脏工作树假绿，
 * 所以不能只让 S34 的单一夹具代表其余三条前缀。
 */
describe('buildBundleAssigneeMap — S32/S33/S34/S35 共享契约', () => {
  it('逐个保留四个 bundle 的已分配底稿，并按姓名、用户名、ID 回退显示', () => {
    const result = buildBundleAssigneeMap([
      { id: 'idx-32', wp_id: 'wp-32', wp_code: 'S32-1', assigned_to: 'user-32', assigned_to_name: '张三' },
      { id: 'idx-33', wp_id: 'wp-33', wp_code: 'S33-2', assigned_to: 'user-33', assigned_to_name: ' ', assigned_to_username: 'lisi' },
      { id: 'idx-34', wp_id: 'wp-34', wp_code: 'S34-3', assigned_to: 'abcdef34-0000' },
      { id: 'idx-35', wp_id: 'wp-35', wp_code: 'S35-4', assigned_to: 'user-35', assigned_to_name: '王五' },
    ])

    expect(Object.keys(result).sort()).toEqual(['S32-1', 'S33-2', 'S34-3', 'S35-4'])
    expect(result['S32-1']).toEqual({ staffId: 'user-32', displayName: '张三' })
    expect(result['S33-2']).toEqual({ staffId: 'user-33', displayName: 'lisi' })
    expect(result['S34-3']).toEqual({ staffId: 'abcdef34-0000', displayName: 'abcdef34' })
    expect(result['S35-4']).toEqual({ staffId: 'user-35', displayName: '王五' })
  })

  it('子表码可携带负责人，但非 S32–S35、无 wp_id 或无负责人必须排除', () => {
    const result = buildBundleAssigneeMap([
      { id: 'child', wp_id: 'wp-child', wp_code: 'S35-4-1', assigned_to: 'child-user' },
      { id: 'other', wp_id: 'wp-other', wp_code: 'S36-1', assigned_to: 'other-user' },
      { id: 'no-wp', wp_id: null, wp_code: 'S32-2', assigned_to: 'no-wp-user' },
      { id: 'no-user', wp_id: 'wp-no-user', wp_code: 'S33-3', assigned_to: null },
    ])

    expect(result).toEqual({
      'S35-4-1': { staffId: 'child-user', displayName: 'child-us' },
    })
  })
})