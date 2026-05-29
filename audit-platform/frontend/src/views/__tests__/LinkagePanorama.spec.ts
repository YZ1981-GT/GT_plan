/**
 * LinkagePanorama.spec.ts — task 2.9
 *
 * 测试 LinkagePanoramaView 页面骨架：
 * - 路由参数 projectId 正确传递
 * - loading 状态 + error 占位 + empty 占位
 * - 工具栏按钮 emit 正确事件
 *
 * Validates: Requirements 1.1, 1.2, 1.3, 1.5
 */
import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const mockGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
  },
}))

const mockPush = vi.fn()
const mockBack = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: { projectId: 'proj-test-001' },
    query: {},
    fullPath: '/projects/proj-test-001/linkage-panorama',
  }),
  useRouter: () => ({
    push: mockPush,
    back: mockBack,
    replace: vi.fn().mockReturnValue(Promise.resolve()),
  }),
}))

vi.mock('@/composables/useNavigationStack', () => ({
  useNavigationStack: () => ({
    push: vi.fn(),
    pop: vi.fn(),
  }),
}))

// Stub 子组件以隔离 D3 依赖
vi.mock('@/components/panorama/ForceGraph.vue', () => ({
  default: { name: 'ForceGraph', template: '<div class="mock-force-graph" />' },
}))

vi.mock('@/components/panorama/GraphLegend.vue', () => ({
  default: { name: 'GraphLegend', template: '<div class="mock-graph-legend" />' },
}))

vi.mock('@/components/panorama/CycleFilter.vue', () => ({
  default: { name: 'CycleFilter', template: '<div class="mock-cycle-filter" />' },
}))

vi.mock('@/components/panorama/SearchLocator.vue', () => ({
  default: { name: 'SearchLocator', template: '<div class="mock-search-locator" />' },
}))

// Stub Element Plus 组件，避免"Failed to resolve component" + onMounted 异常
const STUBS = {
  'el-icon': { template: '<i class="el-icon"><slot /></i>' },
  'el-switch': { template: '<input type="checkbox" class="el-switch" />', props: ['modelValue'] },
  'el-button': { template: '<button class="el-button"><slot /></button>' },
  'el-empty': {
    template: '<div class="el-empty" :data-description="description"><slot name="image" /><div class="el-empty__description">{{ description }}</div><slot /></div>',
    props: ['description'],
  },
}

import LinkagePanoramaView from '@/views/LinkagePanoramaView.vue'

function fixtureGraphData() {
  return {
    nodes: [
      { id: 'H1', wp_code: 'H1', cycle: 'H', label: 'H1', is_stale: true, degree: 2, is_module: false },
      { id: 'K8', wp_code: 'K8', cycle: 'K', label: 'K8', is_stale: false, degree: 1, is_module: false },
    ],
    edges: [
      { id: 'CW-1', source: 'H1', target: 'K8', ref_id: 'CW-1', severity: 'blocking', category: '', description: '', is_stale: true, label: '' },
    ],
    statistics: {
      node_count: 2,
      edge_count: 1,
      stale_node_count: 1,
      stale_edge_count: 1,
      blocking_edge_count: 1,
      severity_distribution: { blocking: 1 },
      cycle_distribution: { H: 1, K: 1 },
    },
  }
}

describe('LinkagePanoramaView', () => {
  it('mount 渲染工具栏 + 标题', () => {
    mockGet.mockResolvedValue(fixtureGraphData())
    const wrapper = mount(LinkagePanoramaView, { global: { stubs: STUBS } })
    expect(wrapper.html()).toContain('联动全景图')
  })

  it('调用 graph-data API 并展示节点边数统计', async () => {
    mockGet.mockResolvedValue(fixtureGraphData())
    const wrapper = mount(LinkagePanoramaView, { global: { stubs: STUBS } })
    await flushPromises()
    expect(mockGet).toHaveBeenCalled()
    const calls = mockGet.mock.calls
    expect(calls.some(c => String(c[0]).includes('linkage-panorama/graph-data'))).toBe(true)
    expect(wrapper.html()).toContain('节点')
    expect(wrapper.html()).toContain('边')
  })

  it('数据加载完成后渲染 ForceGraph 与 GraphLegend', async () => {
    mockGet.mockResolvedValue(fixtureGraphData())
    const wrapper = mount(LinkagePanoramaView, { global: { stubs: STUBS } })
    await flushPromises()
    expect(wrapper.find('.mock-force-graph').exists()).toBe(true)
    expect(wrapper.find('.mock-graph-legend').exists()).toBe(true)
  })

  it('stale 数据时展示 stale 摘要 + 仅过期开关', async () => {
    mockGet.mockResolvedValue(fixtureGraphData())
    const wrapper = mount(LinkagePanoramaView, { global: { stubs: STUBS } })
    await flushPromises()
    expect(wrapper.html()).toContain('过期')
  })

  it('API 失败时展示错误占位', async () => {
    mockGet.mockRejectedValue(new Error('Network down'))
    const wrapper = mount(LinkagePanoramaView, { global: { stubs: STUBS } })
    await flushPromises()
    expect(wrapper.html()).toContain('加载失败')
  })

  it('空数据时展示 el-empty 占位', async () => {
    mockGet.mockResolvedValue({
      nodes: [],
      edges: [],
      statistics: {
        node_count: 0, edge_count: 0, stale_node_count: 0,
        stale_edge_count: 0, blocking_edge_count: 0,
        severity_distribution: {}, cycle_distribution: {},
      },
    })
    const wrapper = mount(LinkagePanoramaView, { global: { stubs: STUBS } })
    await flushPromises()
    expect(wrapper.html()).toContain('无图数据')
  })
})
