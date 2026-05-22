/**
 * useStaleFilter — Phase 7 F13: 联动全景图 stale 过滤器
 *
 * staleOnly ref + filteredNodes/filteredLinks computed
 * staleOnly=true 时：仅显示 is_stale=true 节点 + 一跳邻居 + 相关边
 *
 * Validates: Requirements F13.1, F13.2, F13.4, F13.5
 */

import { ref, computed, type Ref } from 'vue'

export interface D3Node {
  id: string
  is_stale?: boolean
  [key: string]: any
}

export interface D3Link {
  source: string | { id: string }
  target: string | { id: string }
  [key: string]: any
}

function getNodeId(nodeOrId: string | { id: string }): string {
  return typeof nodeOrId === 'string' ? nodeOrId : nodeOrId.id
}

export function useStaleFilter(nodes: Ref<D3Node[]>, links: Ref<D3Link[]>) {
  const staleOnly = ref(false)

  const filteredNodes = computed(() => {
    if (!staleOnly.value) return nodes.value

    // Collect stale node IDs
    const staleIds = new Set(
      nodes.value.filter(n => n.is_stale).map(n => n.id)
    )

    // If no stale nodes, return empty
    if (staleIds.size === 0) return []

    // Collect 1-hop neighbor IDs
    const neighborIds = new Set<string>()
    links.value.forEach(l => {
      const sid = getNodeId(l.source)
      const tid = getNodeId(l.target)
      if (staleIds.has(sid)) neighborIds.add(tid)
      if (staleIds.has(tid)) neighborIds.add(sid)
    })

    // Visible = stale + neighbors
    const visibleIds = new Set([...staleIds, ...neighborIds])
    return nodes.value.filter(n => visibleIds.has(n.id))
  })

  const filteredLinks = computed(() => {
    if (!staleOnly.value) return links.value

    const visibleIds = new Set(filteredNodes.value.map(n => n.id))
    return links.value.filter(l => {
      const sid = getNodeId(l.source)
      const tid = getNodeId(l.target)
      return visibleIds.has(sid) && visibleIds.has(tid)
    })
  })

  return { staleOnly, filteredNodes, filteredLinks }
}
