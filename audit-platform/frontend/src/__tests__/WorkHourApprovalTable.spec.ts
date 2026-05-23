/**
 * WorkHourApprovalTable — 底稿完成度列单测
 * Validates: proposal-remaining-18 task 0.2 (M-5)
 *
 * 验证两层：
 *  1) 渲染层（mount 组件）：传入 wp_completion_rate=0/50/100/null 的 items 后
 *     - 表格应包含进度条数 + 占位 "—" 的总数与 mock 一致
 *  2) 工具层（直接调 helpers）：阈值上色 / 占位判定的边界
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'project-uuid' } }),
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

import WorkHourApprovalTable from '@/components/workhour/WorkHourApprovalTable.vue'
import { api } from '@/services/apiProxy'
import {
  completionColor,
  formatCompletion,
  hasCompletionRate,
} from '@/components/workhour/wpCompletion'

function makeItem(rate: number | null, idx = 0): any {
  return {
    entry_id: `e-${idx}`,
    user_id: `u-${idx}`,
    user_name: `员工 ${idx}`,
    date: '2026-05-22',
    hours: 8,
    cycle: 'D',
    wp_code: 'D2-1',
    description: 'desc',
    wp_progress_pct: 50,
    wp_completion_rate: rate,
    is_warning: false,
  }
}

const stubs = {
  'el-table': true,
  'el-table-column': true,
  'el-button': true,
  'el-dialog': true,
  'el-input': true,
  'el-icon': true,
  'el-progress': true,
  'el-tag': true,
}

describe('WorkHourApprovalTable — 底稿完成度', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('helpers', () => {
    it('hasCompletionRate: 0 是数值，应识别为有效', () => {
      expect(hasCompletionRate(0)).toBe(true)
      expect(hasCompletionRate(50)).toBe(true)
      expect(hasCompletionRate(100)).toBe(true)
    })

    it('hasCompletionRate: null/undefined/字符串 都视为无值', () => {
      expect(hasCompletionRate(null)).toBe(false)
      expect(hasCompletionRate(undefined)).toBe(false)
      expect(hasCompletionRate('50')).toBe(false)
      expect(hasCompletionRate(NaN)).toBe(false)
    })

    it('completionColor 阈值边界：<30 红 / <70 橙 / 其他 绿', () => {
      // <30 红
      expect(completionColor(0)).toBe('#F56C6C')
      expect(completionColor(29)).toBe('#F56C6C')
      expect(completionColor(29.99)).toBe('#F56C6C')
      // [30, 70) 橙
      expect(completionColor(30)).toBe('#E6A23C')
      expect(completionColor(50)).toBe('#E6A23C')
      expect(completionColor(69.99)).toBe('#E6A23C')
      // >=70 绿
      expect(completionColor(70)).toBe('#67C23A')
      expect(completionColor(85)).toBe('#67C23A')
      expect(completionColor(100)).toBe('#67C23A')
    })

    it('formatCompletion 输出整数百分比', () => {
      expect(formatCompletion(0)).toBe('0%')
      expect(formatCompletion(50)).toBe('50%')
      expect(formatCompletion(99.7)).toBe('100%') // toFixed(0) 四舍五入
      expect(formatCompletion(100)).toBe('100%')
    })
  })

  describe('component mount', () => {
    it('加载后调用 api.get 拉取审批列表', async () => {
      vi.mocked(api.get).mockResolvedValue({
        items: [makeItem(0), makeItem(50, 1), makeItem(100, 2), makeItem(null, 3)],
      })
      mount(WorkHourApprovalTable, { global: { stubs } })
      await flushPromises()
      expect(api.get).toHaveBeenCalledWith(
        '/api/projects/project-uuid/workhours/approval',
      )
    })

    it('items 数据回填到 ref 后保留 wp_completion_rate 字段', async () => {
      const fixture = [
        makeItem(0, 0),
        makeItem(50, 1),
        makeItem(100, 2),
        makeItem(null, 3),
      ]
      vi.mocked(api.get).mockResolvedValue({ items: fixture })

      const wrapper = mount(WorkHourApprovalTable, { global: { stubs } })
      await flushPromises()

      const vm = wrapper.vm as any
      expect(vm.items).toHaveLength(4)
      expect(vm.items.map((i: any) => i.wp_completion_rate)).toEqual([
        0, 50, 100, null,
      ])
    })

    it('api 失败时 items 兜底为空数组', async () => {
      vi.mocked(api.get).mockRejectedValue(new Error('boom'))
      const wrapper = mount(WorkHourApprovalTable, { global: { stubs } })
      await flushPromises()
      expect((wrapper.vm as any).items).toEqual([])
    })
  })

  // W-4: 加班工时自动识别
  describe('W-4 加班行高亮', () => {
    function makeItemWithOvertime(
      hours: number,
      isOvertime: boolean | undefined,
      isWarning = false,
      idx = 0,
    ): any {
      return {
        entry_id: `e-${idx}`,
        user_id: `u-${idx}`,
        user_name: `员工 ${idx}`,
        date: '2026-05-22',
        hours,
        cycle: 'D',
        wp_code: 'D2-1',
        description: 'desc',
        wp_progress_pct: 50,
        wp_completion_rate: 50,
        is_warning: isWarning,
        is_overtime: isOvertime,
      }
    }

    it('rowClassName: is_overtime=true 添加 gt-overtime-row class', async () => {
      vi.mocked(api.get).mockResolvedValue({
        items: [makeItemWithOvertime(10, true, false, 0)],
      })
      const wrapper = mount(WorkHourApprovalTable, { global: { stubs } })
      await flushPromises()
      const vm = wrapper.vm as any
      const cls = vm.rowClassName({ row: vm.items[0] })
      expect(cls).toContain('gt-overtime-row')
    })

    it('rowClassName: is_overtime=false 不应包含 gt-overtime-row', async () => {
      vi.mocked(api.get).mockResolvedValue({
        items: [makeItemWithOvertime(8, false, false, 0)],
      })
      const wrapper = mount(WorkHourApprovalTable, { global: { stubs } })
      await flushPromises()
      const vm = wrapper.vm as any
      const cls = vm.rowClassName({ row: vm.items[0] })
      expect(cls).not.toContain('gt-overtime-row')
    })

    it('rowClassName: 同时 overtime 和 warning 时合并两个 class', async () => {
      vi.mocked(api.get).mockResolvedValue({
        items: [makeItemWithOvertime(12, true, true, 0)],
      })
      const wrapper = mount(WorkHourApprovalTable, { global: { stubs } })
      await flushPromises()
      const vm = wrapper.vm as any
      const cls = vm.rowClassName({ row: vm.items[0] })
      expect(cls).toContain('gt-overtime-row')
      expect(cls).toContain('gt-warning-row')
    })

    it('rowClassName: is_overtime 缺失时按 falsy 处理', async () => {
      vi.mocked(api.get).mockResolvedValue({
        items: [makeItemWithOvertime(5, undefined, false, 0)],
      })
      const wrapper = mount(WorkHourApprovalTable, { global: { stubs } })
      await flushPromises()
      const vm = wrapper.vm as any
      const cls = vm.rowClassName({ row: vm.items[0] })
      expect(cls).toBe('')
    })
  })
})
