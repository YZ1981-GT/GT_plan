/**
 * ForceGraph stale filter property tests + unit tests
 * **Validates: Requirements F13.2**
 *
 * Property 7: stale 过滤幂等性 — filter(filter(graph)) == filter(graph)
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { ref } from 'vue'
import { useStaleFilter, type D3Node, type D3Link } from '@/composables/useStaleFilter'

/**
 * Helper: apply stale filter to a graph and return filtered nodes/links.
 * Simulates the composable logic with staleOnly=true.
 */
function applyStaleFilter(nodes: D3Node[], links: D3Link[]): { nodes: D3Node[]; links: D3Link[] } {
  const nodesRef = ref(nodes)
  const linksRef = ref(links)
  const { staleOnly, filteredNodes, filteredLinks } = useStaleFilter(nodesRef, linksRef)
  staleOnly.value = true
  return {
    nodes: filteredNodes.value,
    links: filteredLinks.value,
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Generators
// ═══════════════════════════════════════════════════════════════════════════════

const nodeArb = fc.record({
  id: fc.string({ minLength: 1, maxLength: 8 }),
  is_stale: fc.boolean(),
})

const graphArb = fc.array(nodeArb, { minLength: 1, maxLength: 20 }).chain((rawNodes) => {
  // Deduplicate by id
  const seen = new Set<string>()
  const nodes: D3Node[] = []
  for (const n of rawNodes) {
    if (!seen.has(n.id)) {
      seen.add(n.id)
      nodes.push(n)
    }
  }
  if (nodes.length === 0) {
    nodes.push({ id: 'fallback', is_stale: true })
  }

  const nodeIds = nodes.map((n) => n.id)

  // Generate links between existing nodes
  const linkArb = fc.record({
    source: fc.constantFrom(...nodeIds),
    target: fc.constantFrom(...nodeIds),
  })

  return fc.array(linkArb, { minLength: 0, maxLength: 30 }).map((links) => ({
    nodes,
    links: links.filter((l) => l.source !== l.target), // no self-loops
  }))
})

// ═══════════════════════════════════════════════════════════════════════════════
// PBT-P7: stale 过滤幂等性
// **Validates: Requirements F13.2**
// ═══════════════════════════════════════════════════════════════════════════════

describe('useStaleFilter — Property Tests (P7: stale filter idempotence)', () => {
  it('P7: filter(filter(graph)) == filter(graph) — idempotence', () => {
    fc.assert(
      fc.property(graphArb, ({ nodes, links }) => {
        // First application
        const first = applyStaleFilter(nodes, links)

        // Second application on already-filtered result
        const second = applyStaleFilter(first.nodes, first.links)

        // Idempotence: second application produces same result
        const firstNodeIds = first.nodes.map((n) => n.id).sort()
        const secondNodeIds = second.nodes.map((n) => n.id).sort()

        expect(secondNodeIds).toEqual(firstNodeIds)

        // Compare links by source-target pairs
        const linkKey = (l: D3Link) => {
          const s = typeof l.source === 'string' ? l.source : l.source.id
          const t = typeof l.target === 'string' ? l.target : l.target.id
          return `${s}->${t}`
        }
        const firstLinkKeys = first.links.map(linkKey).sort()
        const secondLinkKeys = second.links.map(linkKey).sort()

        expect(secondLinkKeys).toEqual(firstLinkKeys)
      }),
      { numRuns: 30 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Unit Tests — stale filter behavior
// ═══════════════════════════════════════════════════════════════════════════════

describe('useStaleFilter — Unit Tests', () => {
  it('staleOnly=false returns all nodes and links', () => {
    const nodes = ref<D3Node[]>([
      { id: 'A', is_stale: true },
      { id: 'B', is_stale: false },
      { id: 'C', is_stale: false },
    ])
    const links = ref<D3Link[]>([
      { source: 'A', target: 'B' },
      { source: 'B', target: 'C' },
    ])
    const { staleOnly, filteredNodes, filteredLinks } = useStaleFilter(nodes, links)
    staleOnly.value = false

    expect(filteredNodes.value).toHaveLength(3)
    expect(filteredLinks.value).toHaveLength(2)
  })

  it('staleOnly=true includes stale nodes + 1-hop neighbors', () => {
    const nodes = ref<D3Node[]>([
      { id: 'A', is_stale: true },
      { id: 'B', is_stale: false },
      { id: 'C', is_stale: false },
      { id: 'D', is_stale: false },
    ])
    const links = ref<D3Link[]>([
      { source: 'A', target: 'B' },
      { source: 'B', target: 'C' },
      { source: 'C', target: 'D' },
    ])
    const { staleOnly, filteredNodes, filteredLinks } = useStaleFilter(nodes, links)
    staleOnly.value = true

    // A is stale, B is 1-hop neighbor. C and D are not included.
    const ids = filteredNodes.value.map((n) => n.id).sort()
    expect(ids).toEqual(['A', 'B'])

    // Only link A->B is included (both endpoints visible)
    expect(filteredLinks.value).toHaveLength(1)
  })

  it('no stale nodes → empty result', () => {
    const nodes = ref<D3Node[]>([
      { id: 'A', is_stale: false },
      { id: 'B', is_stale: false },
    ])
    const links = ref<D3Link[]>([{ source: 'A', target: 'B' }])
    const { staleOnly, filteredNodes, filteredLinks } = useStaleFilter(nodes, links)
    staleOnly.value = true

    expect(filteredNodes.value).toHaveLength(0)
    expect(filteredLinks.value).toHaveLength(0)
  })

  it('handles object-style source/target in links', () => {
    const nodes = ref<D3Node[]>([
      { id: 'X', is_stale: true },
      { id: 'Y', is_stale: false },
    ])
    const links = ref<D3Link[]>([{ source: { id: 'X' }, target: { id: 'Y' } }])
    const { staleOnly, filteredNodes, filteredLinks } = useStaleFilter(nodes, links)
    staleOnly.value = true

    const ids = filteredNodes.value.map((n) => n.id).sort()
    expect(ids).toEqual(['X', 'Y'])
    expect(filteredLinks.value).toHaveLength(1)
  })
})
