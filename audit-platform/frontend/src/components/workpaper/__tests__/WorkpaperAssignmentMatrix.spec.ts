import { describe, test, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import WorkpaperAssignmentMatrix from '../WorkpaperAssignmentMatrix.vue'

const members = [
  { id: 'u1', full_name: '用户一', role: 'auditor' },
  { id: 'u2', full_name: '用户二', role: 'manager' },
]

// D 循环 2 张（u1 编制、u2 复核），E 循环 1 张未委派
const workpapers = [
  { id: 'd1', wp_code: 'D2-1', wp_name: '应收账款', status: 'draft', assigned_to: 'u1', reviewer: 'u2' },
  { id: 'd2', wp_code: 'D3-1', wp_name: '预收账款', status: 'edit_complete', assigned_to: 'u1', reviewer: null },
  { id: 'e1', wp_code: 'E1-1', wp_name: '货币资金', status: 'draft', assigned_to: null, reviewer: null },
]

function mountMatrix(props: Record<string, unknown> = {}) {
  return mount(WorkpaperAssignmentMatrix, {
    // onOpenAssign 作为监听器传入，可靠捕获 emit（直接调用 setup 方法时 wrapper.emitted 不记录）
    props: { projectId: 'p1', workpapers, members, ...props },
    global: {
      // 不渲染表格插槽，聚焦 setup 逻辑（matrixRows/loadStats/onCellClick）
      stubs: {
        'el-select': true, 'el-option': true, 'el-checkbox': true,
        'el-progress': true, 'el-tooltip': true, 'el-segmented': true,
        'el-button': true, 'el-tag': true,
        'el-table': { template: '<div />' },
        'el-table-column': { template: '<div />' },
      },
    },
  })
}

describe('WorkpaperAssignmentMatrix', () => {
  test('编制维度：u1 合计 2、u2 合计 0', () => {
    const wrapper = mountMatrix()
    const vm: any = wrapper.vm
    const rows = vm.matrixRows
    const u1 = rows.find((r: any) => r.member_id === 'u1')
    const u2 = rows.find((r: any) => r.member_id === 'u2')
    expect(u1.total_assigned).toBe(2)
    expect(u2.total_assigned).toBe(0)
    // 未委派：E1-1
    expect(vm.totalSummary.unassigned).toBe(1)
  })

  test('复核维度切换：按 reviewer 统计（u2 合计 1，缺复核 2）', async () => {
    const wrapper = mountMatrix()
    const vm: any = wrapper.vm
    vm.mode = 'reviewer'
    await wrapper.vm.$nextTick()
    const u2 = vm.matrixRows.find((r: any) => r.member_id === 'u2')
    expect(u2.total_assigned).toBe(1) // 仅 D2-1 由 u2 复核
    // 复核维度未分配 = 无 reviewer 的底稿（D3-1 + E1-1）
    expect(vm.totalSummary.unassigned).toBe(2)
  })

  // 说明：open-assign 的正向 emit 由 WorkpaperDelegationMatrix.spec 在 wrapper 层覆盖
  //（InnerMatrix.$emit('open-assign') → 打开弹窗）。此处覆盖组件级的委派权限门控输入。
  test('canAssign 门控：prop=false 时只读、缺省为可委派', () => {
    const ro: any = mountMatrix({ canAssign: false }).vm
    expect(ro.canAssign).toBe(false)
    const rw: any = mountMatrix().vm
    expect(rw.canAssign).toBe(true)
  })

  test('只读态：onCellClick 提前返回不抛错', () => {
    const vm: any = mountMatrix({ canAssign: false }).vm
    const u1 = vm.matrixRows.find((r: any) => r.member_id === 'u1')
    expect(() => vm.onCellClick(u1, 'D')).not.toThrow()
  })

  test('循环筛选：仅显示选中循环列', async () => {
    const wrapper = mountMatrix()
    const vm: any = wrapper.vm
    expect(vm.cycleColumns).toContain('E')
    vm.cycleFilter = ['D']
    await wrapper.vm.$nextTick()
    expect(vm.cycleColumns).toEqual(['D'])
  })

  test('负载均衡：人均/最多/最少与超载判定', () => {
    const wrapper = mountMatrix()
    const vm: any = wrapper.vm
    // u1=2, u2=0 → avg=1, max=2, min=0
    expect(vm.loadStats.avg).toBe(1)
    expect(vm.loadStats.max).toBe(2)
    expect(vm.loadStats.min).toBe(0)
    const u1 = vm.matrixRows.find((r: any) => r.member_id === 'u1')
    // 2 > 1*1.5 → 偏高
    expect(vm.isOverloaded(u1)).toBe(true)
  })
})
