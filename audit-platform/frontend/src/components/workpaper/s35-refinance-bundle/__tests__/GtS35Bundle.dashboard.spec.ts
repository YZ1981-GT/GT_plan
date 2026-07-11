/**
 * GtS35Bundle.dashboard.spec.ts — 完成进度仪表盘（三色）验证（Task 6.1）
 *
 * Spec: .kiro/specs/s35-refinancing-bundle/  Task 6.1
 * Validates: Requirements 8.1, 8.2, 8.3
 *
 * 覆盖：
 *  - Req 8.1: 通过 completionMap → progressSummary 推导正确计数
 *  - Req 8.2: 仪表盘显示已完成/进行中/未开始数量 + 三色进度条宽度正确
 *  - Req 8.3: completionMap 变化 → 仪表盘实时更新
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// ─── Mocks ───

const mockGet = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: any[]) => mockGet(...args) },
}))

vi.mock('@/services/workpaperApi', () => ({
  getWpIndex: vi.fn(async () => [
    { wp_code: 'S35-1', wp_id: 'wp-s35-1', id: 'idx-1' },
    { wp_code: 'S35-1-1', wp_id: 'wp-s35-1-1', id: 'idx-1-1' },
    { wp_code: 'S35-2', wp_id: 'wp-s35-2', id: 'idx-2' },
    { wp_code: 'S35-2-1', wp_id: 'wp-s35-2-1', id: 'idx-2-1' },
    { wp_code: 'S35-3', wp_id: 'wp-s35-3', id: 'idx-3' },
    { wp_code: 'S35-3-1', wp_id: 'wp-s35-3-1', id: 'idx-3-1' },
    { wp_code: 'S35-4', wp_id: 'wp-s35-4', id: 'idx-4' },
    { wp_code: 'S35-5', wp_id: 'wp-s35-5', id: 'idx-5' },
  ]),
}))

const routeMock = {
  params: { projectId: 'proj-1' },
  query: {} as Record<string, any>,
}
vi.mock('vue-router', () => ({
  useRoute: () => routeMock,
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('../../GtAProgramConsole.vue', () => ({
  __esModule: true,
  default: {
    name: 'GtAProgramConsole',
    props: ['wpId', 'sheetName', 'readonly'],
    template: '<div class="program-console-stub" />',
  },
}))
vi.mock('../GtS35DetailTable.vue', () => ({
  __esModule: true,
  default: {
    name: 'GtS35DetailTable',
    props: ['wpId', 'sheetCode', 'readonly'],
    emits: ['data-changed'],
    template: '<div class="detail-table-stub" />',
  },
}))

import GtS35Bundle from '../GtS35Bundle.vue'

// ─── el-* stubs ───

const stubs = {
  'el-alert': { template: '<div class="el-alert"><slot name="title" /><slot /></div>' },
  'el-tabs': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<div class="el-tabs-stub"><slot /></div>',
  },
  'el-tab-pane': {
    props: ['name', 'label', 'lazy'],
    template: '<div class="el-tab-pane-stub" :data-name="name"><slot /></div>',
  },
  'el-radio-group': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<div class="el-radio-group-stub"><slot /></div>',
  },
  'el-radio-button': {
    props: ['value'],
    template: '<span class="el-radio-button-stub">{{ value }}</span>',
  },
  'el-result': { template: '<div class="el-result-stub"><slot /></div>' },
  'el-icon': { template: '<i class="el-icon-stub" />' },
}

/**
 * 构建 checklist-responses mock：根据 wpCode 返回对应状态
 * - 'completed': 全部有 conclusion
 * - 'in_progress': 部分有 conclusion
 * - 'not_started': 无 conclusion
 */
function buildResponsesMock(statusMap: Record<string, 'completed' | 'in_progress' | 'not_started'>) {
  return (url: string, opts?: any) => {
    if (typeof url === 'string' && url.includes('/checklist-responses')) {
      // Extract wp-id from URL: /api/workpapers/{wp_id}/checklist-responses
      const match = url.match(/\/workpapers\/([^/]+)\/checklist-responses/)
      if (match) {
        const wpId = match[1]
        // Map wp-id back to wpCode
        const wpCode = wpId.replace('wp-', '').toUpperCase().replace(/-/g, (m, offset) => {
          // wp-s35-1 → S35-1
          return '-'
        })
        // Simpler mapping
        const codeMap: Record<string, string> = {
          'wp-s35-1': 'S35-1',
          'wp-s35-2': 'S35-2',
          'wp-s35-3': 'S35-3',
          'wp-s35-4': 'S35-4',
          'wp-s35-5': 'S35-5',
        }
        const code = codeMap[wpId] || ''
        const status = statusMap[code]
        if (status === 'completed') {
          return Promise.resolve([
            { item_id: '1', conclusion: '已完成' },
            { item_id: '2', conclusion: '无异常' },
          ])
        }
        if (status === 'in_progress') {
          return Promise.resolve([
            { item_id: '1', conclusion: '已完成' },
            { item_id: '2', conclusion: null },
          ])
        }
        // not_started
        return Promise.resolve([])
      }
    }
    return Promise.resolve({})
  }
}

function mountBundle(props: Record<string, any> = {}) {
  return mount(GtS35Bundle, {
    props: { wpId: 'wp-s35', ...props },
    global: {
      stubs,
      directives: { loading: {} },
    },
  })
}

beforeEach(() => {
  mockGet.mockReset()
  routeMock.query = {}
})

// ─── Req 8.2：仪表盘正确渲染三色指标 ───
describe('GtS35Bundle Dashboard — 三色指标渲染（Req 8.2）', () => {
  it('全部未开始 → 已完成0/进行中0/未开始5', async () => {
    mockGet.mockImplementation(buildResponsesMock({
      'S35-1': 'not_started',
      'S35-2': 'not_started',
      'S35-3': 'not_started',
      'S35-4': 'not_started',
      'S35-5': 'not_started',
    }))
    const wrapper = mountBundle()
    await flushPromises()

    const dashboard = wrapper.find('[data-testid="s35-dashboard"]')
    expect(dashboard.exists()).toBe(true)

    // Trigger refreshCompletion to load status data (component doesn't auto-refresh on mount)
    const vm = wrapper.vm as any
    await vm.refreshCompletion()
    await flushPromises()

    expect(vm.progressSummary.completed).toBe(0)
    expect(vm.progressSummary.inProgress).toBe(0)
    expect(vm.progressSummary.notStarted).toBe(5)
  })

  it('2已完成/1进行中/2未开始 → 正确显示数量', async () => {
    mockGet.mockImplementation(buildResponsesMock({
      'S35-1': 'completed',
      'S35-2': 'completed',
      'S35-3': 'in_progress',
      'S35-4': 'not_started',
      'S35-5': 'not_started',
    }))
    const wrapper = mountBundle()
    await flushPromises()

    const vm = wrapper.vm as any
    await vm.refreshCompletion()
    await flushPromises()

    expect(vm.progressSummary.completed).toBe(2)
    expect(vm.progressSummary.inProgress).toBe(1)
    expect(vm.progressSummary.notStarted).toBe(2)

    // 验证 DOM 中显示数字
    const dashText = wrapper.find('[data-testid="s35-dashboard"]').text()
    expect(dashText).toContain('2')
    expect(dashText).toContain('1')
    expect(dashText).toContain('已完成')
    expect(dashText).toContain('进行中')
    expect(dashText).toContain('未开始')
  })

  it('全部已完成 → 已完成5/进行中0/未开始0', async () => {
    mockGet.mockImplementation(buildResponsesMock({
      'S35-1': 'completed',
      'S35-2': 'completed',
      'S35-3': 'completed',
      'S35-4': 'completed',
      'S35-5': 'completed',
    }))
    const wrapper = mountBundle()
    await flushPromises()

    const vm = wrapper.vm as any
    await vm.refreshCompletion()
    await flushPromises()

    expect(vm.progressSummary.completed).toBe(5)
    expect(vm.progressSummary.inProgress).toBe(0)
    expect(vm.progressSummary.notStarted).toBe(0)
  })
})

// ─── Req 8.2：进度条宽度正确 ───
describe('GtS35Bundle Dashboard — 进度条段宽度正确（Req 8.2）', () => {
  it('2/1/2 → 绿色40%/黄色20%/灰色40%', async () => {
    mockGet.mockImplementation(buildResponsesMock({
      'S35-1': 'completed',
      'S35-2': 'completed',
      'S35-3': 'in_progress',
      'S35-4': 'not_started',
      'S35-5': 'not_started',
    }))
    const wrapper = mountBundle()
    await flushPromises()

    const vm = wrapper.vm as any
    await vm.refreshCompletion()
    await flushPromises()

    const bar = wrapper.find('[data-testid="s35-dashboard-bar"]')
    expect(bar.exists()).toBe(true)

    const segments = bar.findAll('.dashboard-bar__segment')
    expect(segments.length).toBe(3)

    // 绿色（完成）= 2/5 = 40%
    const successSeg = bar.find('.dashboard-bar__segment--success')
    expect(successSeg.attributes('style')).toContain('width: 40%')

    // 黄色（进行中）= 1/5 = 20%
    const warningSeg = bar.find('.dashboard-bar__segment--warning')
    expect(warningSeg.attributes('style')).toContain('width: 20%')

    // 灰色（未开始）= 2/5 = 40%
    const infoSeg = bar.find('.dashboard-bar__segment--info')
    expect(infoSeg.attributes('style')).toContain('width: 40%')
  })

  it('全部未开始 → 绿0%/黄0%/灰100%', async () => {
    mockGet.mockImplementation(buildResponsesMock({
      'S35-1': 'not_started',
      'S35-2': 'not_started',
      'S35-3': 'not_started',
      'S35-4': 'not_started',
      'S35-5': 'not_started',
    }))
    const wrapper = mountBundle()
    await flushPromises()

    const vm = wrapper.vm as any
    await vm.refreshCompletion()
    await flushPromises()

    const bar = wrapper.find('[data-testid="s35-dashboard-bar"]')
    const successSeg = bar.find('.dashboard-bar__segment--success')
    const warningSeg = bar.find('.dashboard-bar__segment--warning')
    const infoSeg = bar.find('.dashboard-bar__segment--info')

    expect(successSeg.attributes('style')).toContain('width: 0%')
    expect(warningSeg.attributes('style')).toContain('width: 0%')
    expect(infoSeg.attributes('style')).toContain('width: 100%')
  })

  it('全部已完成 → 绿100%/黄0%/灰0%', async () => {
    mockGet.mockImplementation(buildResponsesMock({
      'S35-1': 'completed',
      'S35-2': 'completed',
      'S35-3': 'completed',
      'S35-4': 'completed',
      'S35-5': 'completed',
    }))
    const wrapper = mountBundle()
    await flushPromises()

    const vm = wrapper.vm as any
    await vm.refreshCompletion()
    await flushPromises()

    const bar = wrapper.find('[data-testid="s35-dashboard-bar"]')
    const successSeg = bar.find('.dashboard-bar__segment--success')
    const warningSeg = bar.find('.dashboard-bar__segment--warning')
    const infoSeg = bar.find('.dashboard-bar__segment--info')

    expect(successSeg.attributes('style')).toContain('width: 100%')
    expect(warningSeg.attributes('style')).toContain('width: 0%')
    expect(infoSeg.attributes('style')).toContain('width: 0%')
  })
})

// ─── Req 8.3：仪表盘实时更新 ───
describe('GtS35Bundle Dashboard — 实时更新（Req 8.3）', () => {
  it('refreshCompletion 后仪表盘数据更新', async () => {
    // 初始全未开始
    mockGet.mockImplementation(buildResponsesMock({
      'S35-1': 'not_started',
      'S35-2': 'not_started',
      'S35-3': 'not_started',
      'S35-4': 'not_started',
      'S35-5': 'not_started',
    }))
    const wrapper = mountBundle()
    await flushPromises()

    const vm = wrapper.vm as any
    expect(vm.progressSummary.completed).toBe(0)
    expect(vm.progressSummary.notStarted).toBe(5)

    // 模拟 S35-1 完成后刷新
    mockGet.mockImplementation((url: string) => {
      if (typeof url === 'string' && url.includes('/checklist-responses')) {
        if (url.includes('wp-s35-1')) {
          return Promise.resolve([
            { item_id: '1', conclusion: '已完成' },
            { item_id: '2', conclusion: '无异常' },
          ])
        }
        return Promise.resolve([])
      }
      return Promise.resolve({})
    })

    await vm.refreshCompletion('S35-1')
    await flushPromises()

    // 仪表盘应更新：1 已完成 / 4 未开始
    expect(vm.progressSummary.completed).toBe(1)
    expect(vm.progressSummary.notStarted).toBe(4)
  })

  it('data-testid="s35-dashboard" 位于 el-tabs 之前', async () => {
    mockGet.mockImplementation(buildResponsesMock({
      'S35-1': 'not_started',
      'S35-2': 'not_started',
      'S35-3': 'not_started',
      'S35-4': 'not_started',
      'S35-5': 'not_started',
    }))
    const wrapper = mountBundle()
    await flushPromises()

    // Dashboard 在 tabs 之前（DOM 顺序验证）
    const html = wrapper.html()
    const dashboardPos = html.indexOf('data-testid="s35-dashboard"')
    const tabsPos = html.indexOf('el-tabs-stub')
    expect(dashboardPos).toBeGreaterThan(-1)
    expect(tabsPos).toBeGreaterThan(-1)
    expect(dashboardPos).toBeLessThan(tabsPos)
  })
})
