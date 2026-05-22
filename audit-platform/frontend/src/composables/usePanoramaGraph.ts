/**
 * usePanoramaGraph — 联动全景图数据 composable
 *
 * 职责：
 * - 拉取 GET /api/projects/{pid}/linkage-panorama/graph-data
 * - 提供 graphData / loading / error 响应式状态
 * - 派生 d3Nodes / d3Links（D3 force simulation 所需格式）
 * - 提供过滤（selectedCycles + showOnlyStale）与搜索能力
 *
 * Validates: Requirements 2.1, 6.3, 7.2, 7.6, 8.5, 9.1
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { api } from '@/services/apiProxy'

// ─── 后端 Pydantic 对齐接口 ─────────────────────────────────────────────────

export interface GraphNode {
  id: string
  wp_code: string
  cycle: string
  label: string
  is_stale: boolean
  degree: number
  is_module: boolean
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  ref_id: string
  severity: string
  category: string
  description: string
  is_stale: boolean
  label: string
}

export interface GraphStatistics {
  node_count: number
  edge_count: number
  stale_node_count: number
  stale_edge_count: number
  blocking_edge_count: number
  severity_distribution: Record<string, number>
  cycle_distribution: Record<string, number>
}

export interface GraphDataResponse {
  nodes: GraphNode[]
  edges: GraphEdge[]
  statistics: GraphStatistics
}

// ─── D3 Simulation 数据接口 ─────────────────────────────────────────────────

export interface D3Node extends GraphNode {
  // D3 simulation 会在 tick 时填充以下字段（可选）
  x?: number
  y?: number
  vx?: number
  vy?: number
  fx?: number | null
  fy?: number | null
}

export interface D3Link {
  id: string
  source: string | D3Node
  target: string | D3Node
  ref_id: string
  severity: string
  category: string
  description: string
  is_stale: boolean
  label: string
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function usePanoramaGraph(projectId: Ref<string>) {
  const graphData = ref<GraphDataResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 过滤状态
  const selectedCycles = ref<string[]>([])  // 空 = 不过滤
  const showOnlyStale = ref(false)

  // ─── 数据加载 ────────────────────────────────────────────────────────────
  async function fetchGraphData(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const result = await api.get<GraphDataResponse>(
        `/api/projects/${projectId.value}/linkage-panorama/graph-data`,
      )
      graphData.value = result
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      error.value = msg
      console.warn('[usePanoramaGraph] fetch failed:', msg)
    } finally {
      loading.value = false
    }
  }

  // ─── D3 数据派生 ─────────────────────────────────────────────────────────
  const d3Nodes: ComputedRef<D3Node[]> = computed(() => {
    if (!graphData.value) return []
    // 浅拷贝以便 D3 写入 x/y/vx/vy 不污染响应式数据
    return graphData.value.nodes.map(n => ({ ...n }))
  })

  const d3Links: ComputedRef<D3Link[]> = computed(() => {
    if (!graphData.value) return []
    return graphData.value.edges.map(e => ({ ...e }))
  })

  const statistics: ComputedRef<GraphStatistics | null> = computed(
    () => graphData.value?.statistics ?? null,
  )

  // ─── 过滤逻辑 ────────────────────────────────────────────────────────────
  const filteredNodes: ComputedRef<D3Node[]> = computed(() => {
    let nodes = d3Nodes.value
    if (selectedCycles.value.length > 0) {
      const cyclesSet = new Set(selectedCycles.value)
      nodes = nodes.filter(n => cyclesSet.has(n.cycle))
    }
    if (showOnlyStale.value) {
      nodes = nodes.filter(n => n.is_stale)
    }
    return nodes
  })

  const filteredLinks: ComputedRef<D3Link[]> = computed(() => {
    const visibleNodeIds = new Set(filteredNodes.value.map(n => n.id))
    return d3Links.value.filter(link => {
      const src = typeof link.source === 'string' ? link.source : link.source.id
      const tgt = typeof link.target === 'string' ? link.target : link.target.id
      const inFilter = visibleNodeIds.has(src) && visibleNodeIds.has(tgt)
      if (!inFilter) return false
      if (showOnlyStale.value && !link.is_stale) return false
      return true
    })
  })

  // ─── 搜索 ───────────────────────────────────────────────────────────────
  function searchNodes(query: string): D3Node[] {
    const q = query.trim().toLowerCase()
    if (!q) return []
    return d3Nodes.value.filter(n => {
      return (
        n.id.toLowerCase().includes(q)
        || n.wp_code.toLowerCase().includes(q)
        || n.label.toLowerCase().includes(q)
      )
    })
  }

  // ─── 循环节点计数（CycleFilter 显示 "D (15)" 用） ───────────────────────
  function getCycleNodeCounts(): Record<string, number> {
    const counts: Record<string, number> = {}
    for (const n of d3Nodes.value) {
      counts[n.cycle] = (counts[n.cycle] ?? 0) + 1
    }
    return counts
  }

  return {
    // 状态
    graphData,
    loading,
    error,
    statistics,
    // D3 数据
    d3Nodes,
    d3Links,
    // 过滤
    selectedCycles,
    showOnlyStale,
    filteredNodes,
    filteredLinks,
    // 行为
    fetchGraphData,
    searchNodes,
    getCycleNodeCounts,
  }
}
