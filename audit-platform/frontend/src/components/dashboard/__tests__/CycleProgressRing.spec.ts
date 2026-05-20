/**
 * CycleProgressRing.spec.ts — Sprint 2 Task 4.3
 *
 * 测试 CycleProgressRing.vue 组件:
 * - 11 环渲染
 * - 颜色映射（< 50% 红色 / 50-99% 橙色 / 100% 绿色）
 * - 点击跳转到对应循环底稿列表
 *
 * Validates: Requirements 2.1, 2.3, 2.4, 2.5, 2.6
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import type { CycleProgressItem } from '@/composables/useDashboardData'

// ─── Mock vue-router ─────────────────────────────────────────────────────────

const mockPush = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ params: { projectId: 'proj-001' } }),
}))

// ─── Mock vue-echarts (ECharts renders to canvas, not testable in jsdom) ─────

vi.mock('vue-echarts', () => ({
  default: {
    name: 'VChart',
    template: '<div class="v-chart-mock" />',
    props: ['option', 'autoresize'],
  },
}))

// ─── Mock echarts/core ───────────────────────────────────────────────────────

vi.mock('echarts/core', () => ({ use: vi.fn() }))
vi.mock('echarts/charts', () => ({ PieChart: {} }))
vi.mock('echarts/components', () => ({ TooltipComponent: {} }))
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }))

// ─── Import component under test ────────────────────────────────────────────

import CycleProgressRing from '../CycleProgressRing.vue'

// ─── Test Fixtures ───────────────────────────────────────────────────────────

function create11Cycles(): CycleProgressItem[] {
  const cycles = ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N']
  const names = ['销售收入', '货币资金', '采购存货', '投资', '固定资产', '无形资产', '职工薪酬', '管理费用', '筹资', '权益', '税费']
  return cycles.map((c, i) => ({
    cycle: c,
    cycle_name: names[i],
    total_procedures: 20,
    completed_procedures: 10,
    trimmed_procedures: 0,
    progress_rate: 50,
  }))
}

function mountComponent(cycleProgress: CycleProgressItem[] = create11Cycles()) {
  return mount(CycleProgressRing, {
    props: { cycleProgress },
  })
}

// ─── Tests ───────────────────────────────────────────────────────────────────

beforeEach(() => {
  mockPush.mockReset()
})

describe('CycleProgressRing — 11 环渲染', () => {
  it('渲染 11 个循环环形图项', () => {
    const wrapper = mountComponent()
    const items = wrapper.findAll('.cycle-ring-item')
    expect(items).toHaveLength(11)
  })

  it('每个环形图项包含 VChart 组件', () => {
    const wrapper = mountComponent()
    const charts = wrapper.findAll('.v-chart-mock')
    expect(charts).toHaveLength(11)
  })

  it('每个环形图项显示循环名称标签', () => {
    const wrapper = mountComponent()
    const labels = wrapper.findAll('.cycle-ring-label')
    expect(labels).toHaveLength(11)
    expect(labels[0].text()).toBe('销售收入')
    expect(labels[10].text()).toBe('税费')
  })

  it('传入空数组时不渲染任何环形图', () => {
    const wrapper = mountComponent([])
    const items = wrapper.findAll('.cycle-ring-item')
    expect(items).toHaveLength(0)
  })
})

describe('CycleProgressRing — 颜色映射', () => {
  it('progress_rate < 50 → 红色 (#F56C6C)', () => {
    const cycles: CycleProgressItem[] = [{
      cycle: 'D', cycle_name: '销售收入',
      total_procedures: 20, completed_procedures: 5, trimmed_procedures: 0,
      progress_rate: 25,
    }]
    const wrapper = mountComponent(cycles)
    const chart = wrapper.findComponent({ name: 'VChart' })
    const option = chart.props('option')
    // 已完成部分颜色应为红色
    expect(option.series[0].data[0].itemStyle.color).toBe('#F56C6C')
    // 中心标签颜色也应为红色
    expect(option.series[0].label.color).toBe('#F56C6C')
  })

  it('progress_rate = 0 → 红色', () => {
    const cycles: CycleProgressItem[] = [{
      cycle: 'E', cycle_name: '货币资金',
      total_procedures: 10, completed_procedures: 0, trimmed_procedures: 0,
      progress_rate: 0,
    }]
    const wrapper = mountComponent(cycles)
    const chart = wrapper.findComponent({ name: 'VChart' })
    const option = chart.props('option')
    expect(option.series[0].data[0].itemStyle.color).toBe('#F56C6C')
  })

  it('progress_rate = 50 → 橙色 (#E6A23C)', () => {
    const cycles: CycleProgressItem[] = [{
      cycle: 'F', cycle_name: '采购存货',
      total_procedures: 20, completed_procedures: 10, trimmed_procedures: 0,
      progress_rate: 50,
    }]
    const wrapper = mountComponent(cycles)
    const chart = wrapper.findComponent({ name: 'VChart' })
    const option = chart.props('option')
    expect(option.series[0].data[0].itemStyle.color).toBe('#E6A23C')
  })

  it('progress_rate = 75 → 橙色', () => {
    const cycles: CycleProgressItem[] = [{
      cycle: 'G', cycle_name: '投资',
      total_procedures: 20, completed_procedures: 15, trimmed_procedures: 0,
      progress_rate: 75,
    }]
    const wrapper = mountComponent(cycles)
    const chart = wrapper.findComponent({ name: 'VChart' })
    const option = chart.props('option')
    expect(option.series[0].data[0].itemStyle.color).toBe('#E6A23C')
  })

  it('progress_rate = 100 → 绿色 (#67C23A)', () => {
    const cycles: CycleProgressItem[] = [{
      cycle: 'H', cycle_name: '固定资产',
      total_procedures: 20, completed_procedures: 20, trimmed_procedures: 0,
      progress_rate: 100,
    }]
    const wrapper = mountComponent(cycles)
    const chart = wrapper.findComponent({ name: 'VChart' })
    const option = chart.props('option')
    expect(option.series[0].data[0].itemStyle.color).toBe('#67C23A')
  })

  it('progress_rate = 99 → 橙色（非绿色）', () => {
    const cycles: CycleProgressItem[] = [{
      cycle: 'I', cycle_name: '无形资产',
      total_procedures: 100, completed_procedures: 99, trimmed_procedures: 0,
      progress_rate: 99,
    }]
    const wrapper = mountComponent(cycles)
    const chart = wrapper.findComponent({ name: 'VChart' })
    const option = chart.props('option')
    expect(option.series[0].data[0].itemStyle.color).toBe('#E6A23C')
  })

  it('progress_rate = 49 → 红色（非橙色）', () => {
    const cycles: CycleProgressItem[] = [{
      cycle: 'J', cycle_name: '职工薪酬',
      total_procedures: 100, completed_procedures: 49, trimmed_procedures: 0,
      progress_rate: 49,
    }]
    const wrapper = mountComponent(cycles)
    const chart = wrapper.findComponent({ name: 'VChart' })
    const option = chart.props('option')
    expect(option.series[0].data[0].itemStyle.color).toBe('#F56C6C')
  })
})

describe('CycleProgressRing — 点击跳转', () => {
  it('点击环形图项跳转到对应循环底稿列表', async () => {
    const wrapper = mountComponent()
    const items = wrapper.findAll('.cycle-ring-item')

    await items[0].trigger('click')

    expect(mockPush).toHaveBeenCalledWith({
      name: 'WorkpaperList',
      params: { projectId: 'proj-001' },
      query: { cycle: 'D' },
    })
  })

  it('点击不同循环传递正确的 cycle 参数', async () => {
    const wrapper = mountComponent()
    const items = wrapper.findAll('.cycle-ring-item')

    await items[4].trigger('click')

    expect(mockPush).toHaveBeenCalledWith({
      name: 'WorkpaperList',
      params: { projectId: 'proj-001' },
      query: { cycle: 'H' },
    })
  })

  it('点击最后一个循环（N）跳转正确', async () => {
    const wrapper = mountComponent()
    const items = wrapper.findAll('.cycle-ring-item')

    await items[10].trigger('click')

    expect(mockPush).toHaveBeenCalledWith({
      name: 'WorkpaperList',
      params: { projectId: 'proj-001' },
      query: { cycle: 'N' },
    })
  })
})
