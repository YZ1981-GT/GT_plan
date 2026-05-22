/**
 * usePanoramaGraph.spec.ts — task 2.9
 *
 * 测试 usePanoramaGraph composable：
 * - fetchGraphData 调用 API + 更新 graphData ref
 * - loading / error 状态切换
 * - d3Nodes / d3Links 派生
 * - 过滤逻辑（selectedCycles + showOnlyStale）
 * - 搜索逻辑（searchNodes 按 wp_code/label 模糊匹配）
 * - getCycleNodeCounts 统计正确
 *
 * Validates: Requirements 2.1, 6.3, 7.2, 7.6, 8.5
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'

const mockGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
  },
}))

import { usePanoramaGraph, type GraphDataResponse } from '../usePanoramaGraph'

function fixtureResponse(): GraphDataResponse {
  return {
    nodes: [
      { id: 'H1', wp_code: 'H1', cycle: 'H', label: 'H1 固定资产', is_stale: true, degree: 3, is_module: false },
      { id: 'K8', wp_code: 'K8', cycle: 'K', label: 'K8 销售费用', is_stale: false, degree: 2, is_module: false },
      { id: 'D2', wp_code: 'D2', cycle: 'D', label: 'D2 收入', is_stale: false, degree: 1, is_module: false },
      { id: '__module__trial_balance', wp_code: 'trial_balance', cycle: 'module', label: 'trial_balance', is_stale: false, degree: 1, is_module: true },
    ],
    edges: [
      { id: 'CW-1', source: 'H1', target: 'K8', ref_id: 'CW-1', severity: 'blocking', category: 'depreciation', description: '折旧分摊', is_stale: true, label: '' },
      { id: 'CW-2', source: 'D2', target: 'K8', ref_id: 'CW-2', severity: 'warning', category: '', description: '', is_stale: false, label: '' },
      { id: 'CW-3', source: 'H1', target: '__module__trial_balance', ref_id: 'CW-3', severity: 'recommended', category: 'cross_module', description: '', is_stale: true, label: '' },
    ],
    statistics: {
      node_count: 4,
      edge_count: 3,
      stale_node_count: 1,
      stale_edge_count: 2,
      blocking_edge_count: 1,
      severity_distribution: { blocking: 1, warning: 1, recommended: 1 },
      cycle_distribution: { H: 1, K: 1, D: 1, module: 1 },
    },
  }
}

beforeEach(() => {
  mockGet.mockReset()
})

describe('usePanoramaGraph', () => {
  it('fetchGraphData 调用 API 并更新 graphData', async () => {
    mockGet.mockResolvedValue(fixtureResponse())
    const projectId = ref('proj-001')
    const { fetchGraphData, graphData, loading, error } = usePanoramaGraph(projectId)

    expect(loading.value).toBe(false)
    const promise = fetchGraphData()
    expect(loading.value).toBe(true)
    await promise

    expect(loading.value).toBe(false)
    expect(error.value).toBeNull()
    expect(graphData.value).not.toBeNull()
    expect(graphData.value!.nodes).toHaveLength(4)
    expect(graphData.value!.edges).toHaveLength(3)
    expect(mockGet).toHaveBeenCalledWith('/api/projects/proj-001/linkage-panorama/graph-data')
  })

  it('API 失败时设置 error 字段', async () => {
    mockGet.mockRejectedValue(new Error('Network error'))
    const projectId = ref('proj-001')
    const { fetchGraphData, error, graphData } = usePanoramaGraph(projectId)
    await fetchGraphData()
    expect(error.value).toContain('Network error')
    expect(graphData.value).toBeNull()
  })

  it('d3Nodes / d3Links 是 graphData 的浅拷贝', async () => {
    mockGet.mockResolvedValue(fixtureResponse())
    const projectId = ref('proj-001')
    const { fetchGraphData, d3Nodes, d3Links, graphData } = usePanoramaGraph(projectId)
    await fetchGraphData()
    expect(d3Nodes.value).toHaveLength(4)
    expect(d3Links.value).toHaveLength(3)
    // 浅拷贝：修改 d3Nodes 不影响 graphData.nodes
    d3Nodes.value[0].id = 'modified'
    expect(graphData.value!.nodes[0].id).toBe('H1')
  })

  it('selectedCycles 过滤后只保留所选循环节点', async () => {
    mockGet.mockResolvedValue(fixtureResponse())
    const projectId = ref('proj-001')
    const { fetchGraphData, filteredNodes, selectedCycles } = usePanoramaGraph(projectId)
    await fetchGraphData()
    expect(filteredNodes.value).toHaveLength(4)
    selectedCycles.value = ['H', 'K']
    await nextTick()
    expect(filteredNodes.value.map(n => n.id).sort()).toEqual(['H1', 'K8'])
  })

  it('selectedCycles 过滤后边只保留两端都可见的', async () => {
    mockGet.mockResolvedValue(fixtureResponse())
    const projectId = ref('proj-001')
    const { fetchGraphData, filteredLinks, selectedCycles } = usePanoramaGraph(projectId)
    await fetchGraphData()
    selectedCycles.value = ['H', 'K']
    await nextTick()
    // CW-1 (H1→K8) 保留 / CW-2 (D2→K8) 因 D 不在过滤集 / CW-3 (H1→module) 因 module 不在过滤集
    expect(filteredLinks.value.map(l => l.id)).toEqual(['CW-1'])
  })

  it('showOnlyStale 仅保留 stale 节点和边', async () => {
    mockGet.mockResolvedValue(fixtureResponse())
    const projectId = ref('proj-001')
    const { fetchGraphData, filteredNodes, filteredLinks, showOnlyStale } = usePanoramaGraph(projectId)
    await fetchGraphData()
    showOnlyStale.value = true
    await nextTick()
    expect(filteredNodes.value.map(n => n.id)).toEqual(['H1'])
    // 边 CW-1 stale 但 K8 已被节点过滤掉 → 也应过滤
    // 真实场景下用户期望"过滤后边端必须可见"，filteredLinks 已严格执行
    expect(filteredLinks.value).toEqual([])
  })

  it('searchNodes 按 wp_code 模糊匹配', async () => {
    mockGet.mockResolvedValue(fixtureResponse())
    const projectId = ref('proj-001')
    const { fetchGraphData, searchNodes } = usePanoramaGraph(projectId)
    await fetchGraphData()
    expect(searchNodes('H1').map(n => n.id)).toEqual(['H1'])
    expect(searchNodes('h')).toHaveLength(1)
    // label 模糊匹配
    expect(searchNodes('销售费用').map(n => n.id)).toEqual(['K8'])
    // 空 query 返回空
    expect(searchNodes('')).toEqual([])
    // 无匹配返回空
    expect(searchNodes('zzz_no_match')).toEqual([])
  })

  it('getCycleNodeCounts 返回每个循环的节点数', async () => {
    mockGet.mockResolvedValue(fixtureResponse())
    const projectId = ref('proj-001')
    const { fetchGraphData, getCycleNodeCounts } = usePanoramaGraph(projectId)
    await fetchGraphData()
    const counts = getCycleNodeCounts()
    expect(counts).toEqual({ H: 1, K: 1, D: 1, module: 1 })
  })
})
