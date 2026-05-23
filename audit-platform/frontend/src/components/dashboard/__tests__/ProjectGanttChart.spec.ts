/**
 * ProjectGanttChart.spec.ts — Sprint 0 Task 0.1（M-1 多项目甘特图）
 *
 * 测试 ProjectGanttChart.vue 与 projectGanttUtils.ts:
 * - 颜色映射逻辑（按循环字母 D/F/H/.../未知 → other）
 * - 时间区间转换（ISO → timestamp / null / 无效 / end<=start 过滤）
 * - 空数据降级（el-empty）
 * - 事件 emit（点击 → project-click）
 *
 * Validates: Requirements 四 M-1（多项目甘特图）/ design.md ADR-1b
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

// ─── Mock vue-echarts (canvas 不在 jsdom 下可测) ─────────────────────────────
vi.mock('vue-echarts', () => ({
  default: {
    name: 'VChart',
    template: '<div class="v-chart-mock" data-testid="vchart-mock" />',
    props: ['option', 'autoresize'],
    emits: ['click'],
  },
}))

// ─── Mock echarts 子模块 ────────────────────────────────────────────────────
vi.mock('echarts/core', () => ({ use: vi.fn() }))
vi.mock('echarts/charts', () => ({ CustomChart: {} }))
vi.mock('echarts/components', () => ({
  TitleComponent: {},
  TooltipComponent: {},
  GridComponent: {},
  DataZoomComponent: {},
}))
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }))

// ─── 被测对象 ───────────────────────────────────────────────────────────────
import ProjectGanttChart from '../ProjectGanttChart.vue'
import {
  cycleColor,
  cycleLabel,
  toTimestamp,
  buildGanttRows,
  CYCLE_COLOR_MAP,
  type ProjectGanttItem,
} from '../projectGanttUtils'

// 全局 stub：el-empty（jsdom 下不需要真实组件，避免 Vue warn 噪音）
const globalMountConfig = {
  global: {
    stubs: { 'el-empty': true },
  },
}

// ─── 工具：构造测试用例 ────────────────────────────────────────────────────
function makeProject(overrides: Partial<ProjectGanttItem> = {}): ProjectGanttItem {
  return {
    project_id: 'p-001',
    project_name: '测试项目 A',
    start_date: '2025-01-01',
    due_date: '2025-06-30',
    overall_progress: 50,
    primary_cycle: 'D',
    ...overrides,
  }
}

// ────────────────────────────────────────────────────────────────────────────
// 颜色映射逻辑
// ────────────────────────────────────────────────────────────────────────────
describe('projectGanttUtils.cycleColor — 颜色映射', () => {
  it('11 个核心循环都有专属颜色', () => {
    const cycles = ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N']
    cycles.forEach((c) => {
      expect(cycleColor(c)).toBe(CYCLE_COLOR_MAP[c])
      // 确保有效十六进制色
      expect(cycleColor(c)).toMatch(/^#[0-9A-Fa-f]{6}$/)
    })
  })

  it('小写字母大小写不敏感', () => {
    expect(cycleColor('d')).toBe(CYCLE_COLOR_MAP.D)
    expect(cycleColor('h')).toBe(CYCLE_COLOR_MAP.H)
  })

  it('null / undefined / 空字符串 → other 颜色', () => {
    expect(cycleColor(null)).toBe(CYCLE_COLOR_MAP.other)
    expect(cycleColor(undefined)).toBe(CYCLE_COLOR_MAP.other)
    expect(cycleColor('')).toBe(CYCLE_COLOR_MAP.other)
  })

  it('未注册字母 → other 颜色', () => {
    expect(cycleColor('X')).toBe(CYCLE_COLOR_MAP.other)
    expect(cycleColor('Z')).toBe(CYCLE_COLOR_MAP.other)
    expect(cycleColor('AB')).toBe(CYCLE_COLOR_MAP.other)
  })

  it('D 循环 = 蓝色 / F = 绿色 / H = 橙红色（与设计稿一致）', () => {
    expect(cycleColor('D')).toBe('#409EFF')
    expect(cycleColor('F')).toBe('#67C23A')
    expect(cycleColor('H')).toBe('#F56C6C')
  })
})

describe('projectGanttUtils.cycleLabel — 图例标签', () => {
  it('已知循环 → "字母 + 中文名"', () => {
    expect(cycleLabel('D')).toBe('D 销售收入')
    expect(cycleLabel('H')).toBe('H 固定资产')
  })

  it('OTHER 仅返回中文名（不重复"other other"）', () => {
    expect(cycleLabel('other')).toBe('其他')
    expect(cycleLabel('OTHER')).toBe('其他')
  })

  it('未知字母 fallback 到 other 中文名', () => {
    expect(cycleLabel('X')).toBe('X 其他')
  })
})

// ────────────────────────────────────────────────────────────────────────────
// 时间区间转换
// ────────────────────────────────────────────────────────────────────────────
describe('projectGanttUtils.toTimestamp — 时间转换', () => {
  it('合法 ISO 日期 → 数字时间戳', () => {
    const t = toTimestamp('2025-01-01')
    expect(t).toBe(new Date('2025-01-01').getTime())
    expect(typeof t).toBe('number')
  })

  it('null / undefined / 空字符串 → null', () => {
    expect(toTimestamp(null)).toBeNull()
    expect(toTimestamp(undefined)).toBeNull()
    expect(toTimestamp('')).toBeNull()
  })

  it('无效字符串 → null（不抛异常）', () => {
    expect(toTimestamp('not-a-date')).toBeNull()
    expect(toTimestamp('2025-99-99')).toBeNull()
  })
})

describe('projectGanttUtils.buildGanttRows — 数据转换', () => {
  it('过滤掉缺失日期的项', () => {
    const rows = buildGanttRows([
      makeProject({ start_date: null, due_date: '2025-06-30' }),
      makeProject({ start_date: '2025-01-01', due_date: null }),
      makeProject({ start_date: null, due_date: null }),
    ])
    expect(rows).toHaveLength(0)
  })

  it('过滤掉 due_date <= start_date 的项', () => {
    const rows = buildGanttRows([
      makeProject({ start_date: '2025-06-30', due_date: '2025-01-01' }), // 倒置
      makeProject({ start_date: '2025-01-01', due_date: '2025-01-01' }), // 同日
    ])
    expect(rows).toHaveLength(0)
  })

  it('progress 截断到 [0, 100]', () => {
    const rows = buildGanttRows([
      makeProject({ project_id: 'p1', overall_progress: -5 }),
      makeProject({ project_id: 'p2', overall_progress: 150 }),
      makeProject({ project_id: 'p3', overall_progress: 50 }),
    ])
    const byId = Object.fromEntries(rows.map((r) => [r.project_id, r.progress]))
    expect(byId.p1).toBe(0)
    expect(byId.p2).toBe(100)
    expect(byId.p3).toBe(50)
  })

  it('按 start 升序排列并重排 index', () => {
    const rows = buildGanttRows([
      makeProject({ project_id: 'late', start_date: '2025-06-01', due_date: '2025-09-01' }),
      makeProject({ project_id: 'early', start_date: '2025-01-01', due_date: '2025-04-01' }),
      makeProject({ project_id: 'mid', start_date: '2025-03-01', due_date: '2025-07-01' }),
    ])
    expect(rows.map((r) => r.project_id)).toEqual(['early', 'mid', 'late'])
    expect(rows.map((r) => r.index)).toEqual([0, 1, 2])
  })

  it('未知 primary_cycle → cycle="OTHER" + other 颜色', () => {
    const rows = buildGanttRows([makeProject({ primary_cycle: null })])
    expect(rows[0].cycle).toBe('OTHER')
    expect(rows[0].color).toBe(CYCLE_COLOR_MAP.other)
  })

  it('primary_cycle 大小写归一化为大写', () => {
    const rows = buildGanttRows([makeProject({ primary_cycle: 'd' })])
    expect(rows[0].cycle).toBe('D')
    expect(rows[0].color).toBe(CYCLE_COLOR_MAP.D)
  })
})

// ────────────────────────────────────────────────────────────────────────────
// 组件渲染 / 空数据降级 / 事件
// ────────────────────────────────────────────────────────────────────────────
describe('ProjectGanttChart — 组件渲染', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('空数组 → 显示降级 empty 状态，不渲染图表', () => {
    const wrapper = mount(ProjectGanttChart, {
      props: { projects: [] },
      global: { stubs: { 'el-empty': true } },
    })
    expect(wrapper.find('.gt-gantt-empty').exists()).toBe(true)
    expect(wrapper.find('[data-testid="vchart-mock"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="gantt-legend"]').exists()).toBe(false)
  })

  it('全部项目缺失日期 → 同样降级（hasData=false）', () => {
    const wrapper = mount(ProjectGanttChart, {
      props: {
        projects: [
          makeProject({ start_date: null, due_date: null }),
          makeProject({ project_id: 'p2', start_date: '2025-06-01', due_date: '2025-01-01' }),
        ],
      },
      global: { stubs: { 'el-empty': true } },
    })
    expect(wrapper.find('.gt-gantt-empty').exists()).toBe(true)
    expect(wrapper.find('[data-testid="vchart-mock"]').exists()).toBe(false)
  })

  it('有效数据 → 渲染 VChart + 图例', () => {
    const wrapper = mount(ProjectGanttChart, {
      props: {
        projects: [
          makeProject({ project_id: 'p1', primary_cycle: 'D' }),
          makeProject({ project_id: 'p2', project_name: '项目 B', primary_cycle: 'H' }),
        ],
      },
      ...globalMountConfig,
    })
    expect(wrapper.find('[data-testid="vchart-mock"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="gantt-legend"]').exists()).toBe(true)
    // 图例应包含 D / H 两个循环
    const legendText = wrapper.find('[data-testid="gantt-legend"]').text()
    expect(legendText).toContain('D')
    expect(legendText).toContain('H')
  })

  it('option.series[0] 为 custom type 且包含正确数量的数据', () => {
    const wrapper = mount(ProjectGanttChart, {
      props: {
        projects: [
          makeProject({ project_id: 'p1', primary_cycle: 'D' }),
          makeProject({ project_id: 'p2', project_name: '项目 B', primary_cycle: 'F' }),
          makeProject({ project_id: 'p3', start_date: null }), // 应被过滤
        ],
      },
      ...globalMountConfig,
    })
    const chart = wrapper.findComponent({ name: 'VChart' })
    const opt: any = chart.props('option')
    expect(opt.series[0].type).toBe('custom')
    expect(opt.series[0].data).toHaveLength(2)
    // 颜色直接编码到 data.value[5]
    const colors = opt.series[0].data.map((d: any) => d.value[5])
    expect(colors).toContain(CYCLE_COLOR_MAP.D)
    expect(colors).toContain(CYCLE_COLOR_MAP.F)
  })

  it('y 轴 category 数据 = 项目名（按 start 升序）', () => {
    const wrapper = mount(ProjectGanttChart, {
      props: {
        projects: [
          makeProject({
            project_id: 'late',
            project_name: '后开始',
            start_date: '2025-06-01',
            due_date: '2025-09-01',
          }),
          makeProject({
            project_id: 'early',
            project_name: '先开始',
            start_date: '2025-01-01',
            due_date: '2025-04-01',
          }),
        ],
      },
      ...globalMountConfig,
    })
    const chart = wrapper.findComponent({ name: 'VChart' })
    const opt: any = chart.props('option')
    expect(opt.yAxis.data).toEqual(['先开始', '后开始'])
  })

  it('点击 VChart → emit project-click 携带 project_id', async () => {
    const wrapper = mount(ProjectGanttChart, {
      props: {
        projects: [makeProject({ project_id: 'p-clicked' })],
      },
      ...globalMountConfig,
    })
    const chart = wrapper.findComponent({ name: 'VChart' })
    // 模拟 ECharts 点击事件 — params.value[4] = project_id
    await chart.vm.$emit('click', { value: [0, 1, 2, 50, 'p-clicked', '#409EFF'] })
    expect(wrapper.emitted('project-click')).toBeTruthy()
    expect(wrapper.emitted('project-click')![0]).toEqual(['p-clicked'])
  })

  it('点击事件 value 中无 project_id（异常） → 不 emit', async () => {
    const wrapper = mount(ProjectGanttChart, {
      props: {
        projects: [makeProject()],
      },
      ...globalMountConfig,
    })
    const chart = wrapper.findComponent({ name: 'VChart' })
    await chart.vm.$emit('click', { value: [0, 1, 2, 50] }) // 无 [4]
    expect(wrapper.emitted('project-click')).toBeFalsy()
  })

  it('项目数 > 8 启用 dataZoom，否则禁用', () => {
    // ≤8 项
    const small = mount(ProjectGanttChart, {
      props: {
        projects: Array.from({ length: 5 }, (_, i) =>
          makeProject({ project_id: `p${i}`, project_name: `项目${i}` }),
        ),
      },
      ...globalMountConfig,
    })
    const optSmall: any = small.findComponent({ name: 'VChart' }).props('option')
    expect(optSmall.dataZoom).toEqual([])

    // >8 项
    const big = mount(ProjectGanttChart, {
      props: {
        projects: Array.from({ length: 12 }, (_, i) =>
          makeProject({
            project_id: `p${i}`,
            project_name: `项目${i}`,
            // 错开 start_date 避免相同时间
            start_date: `2025-0${1 + (i % 9)}-01`,
            due_date: `2025-12-31`,
          }),
        ),
      },
      ...globalMountConfig,
    })
    const optBig: any = big.findComponent({ name: 'VChart' }).props('option')
    expect(optBig.dataZoom).toHaveLength(1)
    expect(optBig.dataZoom[0].type).toBe('slider')
  })
})
