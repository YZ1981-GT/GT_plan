<template>
  <div ref="containerRef" class="force-graph-container">
    <svg
      ref="svgRef"
      class="force-graph-svg"
      :width="width"
      :height="height"
    >
      <defs>
        <!-- 箭头 marker（每个 severity 一组） -->
        <marker
          v-for="(color, sev) in arrowColors"
          :key="`arrow-${sev}`"
          :id="`arrow-${sev}`"
          viewBox="0 -5 10 10"
          refX="22"
          refY="0"
          markerWidth="8"
          markerHeight="8"
          orient="auto"
        >
          <path d="M0,-5L10,0L0,5" :fill="color" />
        </marker>
      </defs>
      <g ref="rootGroupRef">
        <g class="links" />
        <g class="nodes" />
        <g class="labels" />
      </g>
    </svg>
    <!-- Tooltip -->
    <div
      v-if="tooltip.visible"
      class="force-graph-tooltip"
      :style="{ left: `${tooltip.x}px`, top: `${tooltip.y}px` }"
    >
      <div class="tt-title">{{ tooltip.title }}</div>
      <div v-for="(line, idx) in tooltip.lines" :key="idx" class="tt-line">
        {{ line }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * ForceGraph.vue — D3.js 力导向图核心组件
 *
 * Props: nodes / links / width / height
 * Emits: node-click(node) / node-hover(node|null) / edge-hover(edge|null)
 *
 * Validates: Requirements 2.1, 2.3, 2.4, 2.5, 2.6, 3.1, 3.2, 3.3, 3.5, 4.1, 4.2, 4.3,
 *            5.1, 6.1, 6.2, 8.1, 8.2, 8.3
 */
import { ref, watch, onMounted, onBeforeUnmount, computed, reactive } from 'vue'
import * as d3 from 'd3'
import type { D3Node, D3Link } from '@/composables/usePanoramaGraph'
import {
  cycleColor,
  severityColor,
  severityWidth,
  nodeRadius,
  SEVERITY_COLOR_MAP,
} from './colorMaps'

const props = withDefaults(
  defineProps<{
    nodes: D3Node[]
    links: D3Link[]
    width: number
    height: number
    staleOnly?: boolean
  }>(),
  { width: 1200, height: 800, staleOnly: false },
)

const emit = defineEmits<{
  (e: 'node-click', node: D3Node): void
  (e: 'node-hover', node: D3Node | null): void
  (e: 'edge-hover', edge: D3Link | null): void
}>()

const containerRef = ref<HTMLDivElement | null>(null)
const svgRef = ref<SVGSVGElement | null>(null)
const rootGroupRef = ref<SVGGElement | null>(null)

// 箭头颜色：每个 severity 一种
const arrowColors = computed(() => SEVERITY_COLOR_MAP)

// Tooltip 状态
const tooltip = reactive({
  visible: false,
  x: 0,
  y: 0,
  title: '',
  lines: [] as string[],
})

let simulation: d3.Simulation<D3Node, D3Link> | null = null
let zoomBehavior: d3.ZoomBehavior<SVGSVGElement, unknown> | null = null
let simulationTimeoutId: ReturnType<typeof setTimeout> | null = null
const SIMULATION_TIMEOUT_MS = 5000

// ─── 渲染辅助 ───────────────────────────────────────────────────────────────

function buildSimulation(nodes: D3Node[], links: D3Link[]): void {
  if (!svgRef.value || !rootGroupRef.value) return

  const svg = d3.select(svgRef.value)
  const root = d3.select(rootGroupRef.value)
  const w = props.width
  const h = props.height

  // ── 构造 Force Simulation ────────────────────────────────────────────────
  if (simulation) simulation.stop()
  if (simulationTimeoutId) {
    clearTimeout(simulationTimeoutId)
    simulationTimeoutId = null
  }
  const simStart = performance.now()
  simulation = d3
    .forceSimulation<D3Node>(nodes)
    .force(
      'link',
      d3.forceLink<D3Node, D3Link>(links).id(d => d.id).distance(80).strength(0.3),
    )
    .force('charge', d3.forceManyBody().strength(-300).distanceMax(400))
    .force('center', d3.forceCenter(w / 2, h / 2))
    .force(
      'collision',
      d3.forceCollide<D3Node>().radius(d => nodeRadius(d.degree) + 5),
    )
    .alphaDecay(0.05)
    .velocityDecay(0.5)
    .alphaMin(0.01)
    .on('end', () => {
      const elapsed = performance.now() - simStart
      console.info(`[ForceGraph] simulation stable in ${elapsed.toFixed(0)}ms (${nodes.length} nodes, ${links.length} links)`)
      if (simulationTimeoutId) {
        clearTimeout(simulationTimeoutId)
        simulationTimeoutId = null
      }
    })

  // 5s 超时强制停止保护（design ADR Error Handling）
  simulationTimeoutId = setTimeout(() => {
    if (simulation && simulation.alpha() > 0.001) {
      console.warn(`[ForceGraph] simulation timeout (>${SIMULATION_TIMEOUT_MS}ms), forcing stop. Layout may have minor overlap.`)
      simulation.stop()
    }
    simulationTimeoutId = null
  }, SIMULATION_TIMEOUT_MS)

  // ── 渲染边（含箭头） ─────────────────────────────────────────────────────
  const linkSel = root
    .select<SVGGElement>('g.links')
    .selectAll<SVGLineElement, D3Link>('line')
    .data(links, d => d.id)

  linkSel.exit().remove()

  const linkEnter = linkSel
    .enter()
    .append('line')
    .attr('stroke-opacity', 0.6)
    .on('mouseover', function (_ev, d) {
      const ev = _ev as MouseEvent
      showTooltip(ev, d.ref_id, [
        d.description || '(无描述)',
        `${edgeEndpointId(d.source)} → ${edgeEndpointId(d.target)}`,
        `严重度: ${d.severity}` + (d.category ? ` / 类别: ${d.category}` : ''),
      ])
      emit('edge-hover', d)
    })
    .on('mousemove', _ev => moveTooltip(_ev as MouseEvent))
    .on('mouseout', () => {
      hideTooltip()
      emit('edge-hover', null)
    })

  const linkAll = linkEnter.merge(linkSel)
  linkAll
    .attr('stroke', d => severityColor(d.severity))
    .attr('stroke-width', d => severityWidth(d.severity))
    .attr('marker-end', d => `url(#arrow-${d.severity})`)
    .attr('class', d => (d.is_stale ? 'edge-stale' : null))

  // ── 渲染节点 ─────────────────────────────────────────────────────────────
  const nodeSel = root
    .select<SVGGElement>('g.nodes')
    .selectAll<SVGCircleElement, D3Node>('circle')
    .data(nodes, d => d.id)

  nodeSel.exit().remove()

  const nodeEnter = nodeSel
    .enter()
    .append('circle')
    .attr('cursor', 'pointer')
    .on('click', (_ev, d) => emit('node-click', d))
    .on('mouseover', function (_ev, d) {
      const ev = _ev as MouseEvent
      const lines = [
        `循环: ${d.cycle}`,
        `度数: ${d.degree}`,
        d.is_module ? '类型: 跨模块虚拟节点' : '类型: 底稿节点',
      ]
      if (d.is_stale) lines.push('⚠ 该底稿预填充数据已过期，需重新计算')
      showTooltip(ev, d.label || d.id, lines)
      applyHoverHighlight(d.id)
      emit('node-hover', d)
    })
    .on('mousemove', _ev => moveTooltip(_ev as MouseEvent))
    .on('mouseout', () => {
      hideTooltip()
      clearHoverHighlight()
      emit('node-hover', null)
    })
    .call(buildDragBehavior())

  const nodeAll = nodeEnter.merge(nodeSel)
  nodeAll
    .attr('r', d => nodeRadius(d.degree))
    .attr('fill', d => cycleColor(d.cycle))
    .attr('stroke', d => (d.is_stale ? '#FDD835' : '#fff'))
    .attr('stroke-width', d => (d.is_stale ? 2 : 1))
    .attr('stroke-dasharray', d => (d.is_stale ? '4 2' : null))
    .attr('class', d => (d.is_stale ? 'node-stale' : null))

  // ── 渲染标签 ─────────────────────────────────────────────────────────────
  const labelSel = root
    .select<SVGGElement>('g.labels')
    .selectAll<SVGTextElement, D3Node>('text')
    .data(nodes, d => d.id)

  labelSel.exit().remove()

  const labelEnter = labelSel
    .enter()
    .append('text')
    .attr('font-size', '11px')
    .attr('text-anchor', 'middle')
    .attr('dy', '0.31em')
    .attr('pointer-events', 'none')
    .attr('fill', '#333')
    .attr('paint-order', 'stroke')
    .attr('stroke', '#fff')
    .attr('stroke-width', 3)
    .attr('stroke-linecap', 'round')
    .attr('stroke-linejoin', 'round')

  labelEnter.merge(labelSel).text(d => d.wp_code)

  // ── tick handler ─────────────────────────────────────────────────────────
  simulation.on('tick', () => {
    linkAll
      .attr('x1', d => (d.source as D3Node).x ?? 0)
      .attr('y1', d => (d.source as D3Node).y ?? 0)
      .attr('x2', d => (d.target as D3Node).x ?? 0)
      .attr('y2', d => (d.target as D3Node).y ?? 0)

    nodeAll.attr('cx', d => d.x ?? 0).attr('cy', d => d.y ?? 0)

    root.select<SVGGElement>('g.labels')
      .selectAll<SVGTextElement, D3Node>('text')
      .attr('x', d => d.x ?? 0)
      .attr('y', d => (d.y ?? 0) + nodeRadius(d.degree) + 10)
  })

  // ── Zoom + Pan ───────────────────────────────────────────────────────────
  if (!zoomBehavior) {
    zoomBehavior = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 5])
      .on('zoom', ev => {
        root.attr('transform', ev.transform)
      })
    svg.call(zoomBehavior)
  }
}

function buildDragBehavior(): d3.DragBehavior<SVGCircleElement, D3Node, D3Node | d3.SubjectPosition> {
  return d3
    .drag<SVGCircleElement, D3Node>()
    .on('start', (event, d) => {
      if (!event.active && simulation) simulation.alphaTarget(0.3).restart()
      d.fx = d.x
      d.fy = d.y
    })
    .on('drag', (event, d) => {
      d.fx = event.x
      d.fy = event.y
    })
    .on('end', (event, d) => {
      if (!event.active && simulation) simulation.alphaTarget(0)
      // 拖拽结束后保持固定位置（fx/fy 不清空 → 节点固定）
      d.fx = event.x
      d.fy = event.y
    })
}

function edgeEndpointId(endpoint: string | D3Node): string {
  return typeof endpoint === 'string' ? endpoint : endpoint.id
}

// ─── Hover 高亮：节点+邻居高亮，其余降透明度至 20% ──────────────────────
function applyHoverHighlight(nodeId: string) {
  if (!rootGroupRef.value) return
  const root = d3.select(rootGroupRef.value)
  const neighborIds = new Set<string>([nodeId])
  for (const link of props.links) {
    const src = edgeEndpointId(link.source)
    const tgt = edgeEndpointId(link.target)
    if (src === nodeId) neighborIds.add(tgt)
    if (tgt === nodeId) neighborIds.add(src)
  }
  root.selectAll<SVGCircleElement, D3Node>('g.nodes circle')
    .attr('opacity', d => (neighborIds.has(d.id) ? 1 : 0.2))
  root.selectAll<SVGTextElement, D3Node>('g.labels text')
    .attr('opacity', d => (neighborIds.has(d.id) ? 1 : 0.2))
  root.selectAll<SVGLineElement, D3Link>('g.links line')
    .attr('opacity', d => {
      const src = edgeEndpointId(d.source)
      const tgt = edgeEndpointId(d.target)
      return src === nodeId || tgt === nodeId ? 1 : 0.1
    })
}

function clearHoverHighlight() {
  if (!rootGroupRef.value) return
  const root = d3.select(rootGroupRef.value)
  root.selectAll('g.nodes circle').attr('opacity', 1)
  root.selectAll('g.labels text').attr('opacity', 1)
  root.selectAll('g.links line').attr('opacity', 0.6)
}

// ─── Tooltip 帮助函数 ──────────────────────────────────────────────────────
function showTooltip(event: MouseEvent, title: string, lines: string[]) {
  const rect = containerRef.value?.getBoundingClientRect()
  const offsetX = rect ? event.clientX - rect.left + 12 : event.offsetX + 12
  const offsetY = rect ? event.clientY - rect.top + 12 : event.offsetY + 12
  tooltip.x = offsetX
  tooltip.y = offsetY
  tooltip.title = title
  tooltip.lines = lines
  tooltip.visible = true
}

function moveTooltip(event: MouseEvent) {
  if (!tooltip.visible) return
  const rect = containerRef.value?.getBoundingClientRect()
  tooltip.x = (rect ? event.clientX - rect.left : event.offsetX) + 12
  tooltip.y = (rect ? event.clientY - rect.top : event.offsetY) + 12
}

function hideTooltip() {
  tooltip.visible = false
}

// ─── 暴露给父组件的命令 ─────────────────────────────────────────────────────

function resetView() {
  if (svgRef.value && zoomBehavior) {
    d3.select<SVGSVGElement, unknown>(svgRef.value)
      .transition()
      .duration(300)
      .call(zoomBehavior.transform, d3.zoomIdentity)
  }
}

function fitToWindow() {
  if (!svgRef.value || !zoomBehavior || props.nodes.length === 0) return
  // 计算节点 bounding box
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const n of props.nodes) {
    if (n.x === undefined || n.y === undefined) continue
    minX = Math.min(minX, n.x); minY = Math.min(minY, n.y)
    maxX = Math.max(maxX, n.x); maxY = Math.max(maxY, n.y)
  }
  if (!isFinite(minX)) return
  const padding = 50
  const w = props.width
  const h = props.height
  const dx = maxX - minX + padding * 2
  const dy = maxY - minY + padding * 2
  const scale = Math.min(w / dx, h / dy, 5)
  const tx = (w - scale * (minX + maxX)) / 2
  const ty = (h - scale * (minY + maxY)) / 2
  d3.select<SVGSVGElement, unknown>(svgRef.value)
    .transition()
    .duration(500)
    .call(zoomBehavior.transform, d3.zoomIdentity.translate(tx, ty).scale(scale))
}

function locateNode(nodeId: string) {
  const node = props.nodes.find(n => n.id === nodeId)
  if (!node || !svgRef.value || !zoomBehavior) return
  if (node.x === undefined || node.y === undefined) return
  const scale = 2
  const tx = props.width / 2 - scale * node.x
  const ty = props.height / 2 - scale * node.y
  d3.select<SVGSVGElement, unknown>(svgRef.value)
    .transition()
    .duration(500)
    .call(zoomBehavior.transform, d3.zoomIdentity.translate(tx, ty).scale(scale))
}

defineExpose({ resetView, fitToWindow, locateNode })

// ─── 生命周期 ──────────────────────────────────────────────────────────────
onMounted(() => {
  buildSimulation(props.nodes, props.links)
})

watch(
  () => [props.nodes, props.links],
  () => {
    buildSimulation(props.nodes, props.links)
  },
  { deep: false },
)

// ═══ Phase 7 F13: staleOnly 过滤 — 平滑过渡 ═══
watch(
  () => props.staleOnly,
  (staleOnly) => {
    if (!svgRef.value) return
    const svg = d3.select(svgRef.value)

    if (!staleOnly) {
      // Show all nodes/links with full opacity
      svg.selectAll('.nodes circle').transition().duration(300).attr('opacity', 1)
      svg.selectAll('.links line').transition().duration(300).attr('opacity', 1)
      svg.selectAll('.labels text').transition().duration(300).attr('opacity', 1)
      return
    }

    // Fade out non-stale nodes (keep stale + 1-hop neighbors)
    const staleIds = new Set(
      props.nodes.filter(n => n.is_stale).map(n => n.id)
    )
    const neighborIds = new Set<string>()
    props.links.forEach(l => {
      const sid = typeof l.source === 'string' ? l.source : (l.source as any).id
      const tid = typeof l.target === 'string' ? l.target : (l.target as any).id
      if (staleIds.has(sid)) neighborIds.add(tid)
      if (staleIds.has(tid)) neighborIds.add(sid)
    })
    const visibleIds = new Set([...staleIds, ...neighborIds])

    svg.selectAll('.nodes circle')
      .transition().duration(300)
      .attr('opacity', (d: any) => visibleIds.has(d.id) ? 1 : 0.1)

    svg.selectAll('.links line')
      .transition().duration(300)
      .attr('opacity', (d: any) => {
        const sid = typeof d.source === 'string' ? d.source : d.source?.id
        const tid = typeof d.target === 'string' ? d.target : d.target?.id
        return visibleIds.has(sid) && visibleIds.has(tid) ? 1 : 0.05
      })

    svg.selectAll('.labels text')
      .transition().duration(300)
      .attr('opacity', (d: any) => visibleIds.has(d.id) ? 1 : 0.1)
  },
)

onBeforeUnmount(() => {
  if (simulationTimeoutId) {
    clearTimeout(simulationTimeoutId)
    simulationTimeoutId = null
  }
  if (simulation) {
    simulation.stop()
    simulation = null
  }
})
</script>

<style scoped>
.force-graph-container {
  position: relative;
  width: 100%;
  height: 100%;
  background: #fafafa;
}

.force-graph-svg {
  display: block;
  width: 100%;
  height: 100%;
  cursor: grab;
}

.force-graph-svg:active {
  cursor: grabbing;
}

.force-graph-tooltip {
  position: absolute;
  pointer-events: none;
  background: rgba(33, 33, 33, 0.92);
  color: #fff;
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.5;
  max-width: 320px;
  z-index: 10;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.force-graph-tooltip .tt-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.force-graph-tooltip .tt-line {
  font-size: 11px;
  opacity: 0.92;
}

/* Stale 边闪烁 + 加粗 */
:deep(.edge-stale) {
  animation: stale-pulse 0.8s ease-in-out infinite alternate;
}

@keyframes stale-pulse {
  from {
    opacity: 0.45;
  }
  to {
    opacity: 1;
  }
}
</style>
