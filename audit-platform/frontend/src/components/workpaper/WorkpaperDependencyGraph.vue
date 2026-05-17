<template>
  <div class="gt-wp-dep-graph">
    <!-- 顶部工具栏：筛选 + 统计 -->
    <div class="gt-wp-dg-toolbar">
      <div class="gt-wp-dg-stats">
        <span class="gt-wp-dg-stat">
          <strong>{{ stats.totalNodes }}</strong> 节点
        </span>
        <span class="gt-wp-dg-stat">
          <strong>{{ filteredEdges.length }}</strong> 引用 / 共 {{ stats.totalEdges }}
        </span>
      </div>
      <div class="gt-wp-dg-filters">
        <span class="gt-wp-dg-filter-label">循环：</span>
        <el-checkbox
          v-model="showAllCycles"
          @change="onToggleAllCycles"
          size="small"
        >全部</el-checkbox>
        <el-checkbox-group v-model="visibleCycles" size="small" class="gt-wp-dg-cycles">
          <el-checkbox v-for="c in cycleList" :key="c" :value="c" :label="c">
            <span class="gt-wp-dg-cycle-dot" :style="{ background: cycleColor(c) }"></span>
            {{ c }}
          </el-checkbox>
        </el-checkbox-group>
        <el-divider direction="vertical" />
        <span class="gt-wp-dg-filter-label">严重度：</span>
        <el-radio-group v-model="severityFilter" size="small">
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="blocking">阻断</el-radio-button>
          <el-radio-button value="required">必需</el-radio-button>
          <el-radio-button value="warning">警告</el-radio-button>
          <el-radio-button value="recommended">推荐</el-radio-button>
          <el-radio-button value="info">提示</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <!-- 主体：左 SVG / 右图例 -->
    <div class="gt-wp-dg-body">
      <div class="gt-wp-dg-canvas">
        <div v-if="loading" class="gt-wp-dg-loading">加载依赖图...</div>
        <svg
          v-else
          :viewBox="`0 0 ${SVG_SIZE} ${SVG_SIZE}`"
          class="gt-wp-dg-svg"
          @mouseleave="onSvgLeave"
        >
          <!-- 边：先画灰边，再画 hover 关联边覆盖 -->
          <g class="gt-wp-dg-edges">
            <line
              v-for="(e, i) in renderedEdges"
              :key="`edge-${i}`"
              :x1="e.x1"
              :y1="e.y1"
              :x2="e.x2"
              :y2="e.y2"
              :stroke="edgeStroke(e)"
              :stroke-width="edgeWidth(e)"
              :stroke-dasharray="edgeDash(e)"
              :opacity="edgeOpacity(e)"
            />
          </g>

          <!-- 循环弧 -->
          <g class="gt-wp-dg-arcs">
            <path
              v-for="arc in cycleArcs"
              :key="`arc-${arc.cycle}`"
              :d="arc.path"
              fill="none"
              :stroke="cycleColor(arc.cycle)"
              stroke-width="3"
              opacity="0.4"
            />
            <text
              v-for="arc in cycleArcs"
              :key="`label-${arc.cycle}`"
              :x="arc.labelX"
              :y="arc.labelY"
              text-anchor="middle"
              :fill="cycleColor(arc.cycle)"
              font-size="14"
              font-weight="700"
            >
              {{ arc.cycle }}
            </text>
          </g>

          <!-- 节点 -->
          <g class="gt-wp-dg-nodes">
            <g
              v-for="n in renderedNodes"
              :key="`node-${n.id}`"
              class="gt-wp-dg-node"
              :class="{ 'is-hovered': hoveredNode === n.id, 'is-dimmed': hoveredNode && hoveredNode !== n.id && !connectedNodes.has(n.id) }"
              @mouseenter="onNodeHover(n.id, $event)"
              @click="onNodeClick(n.id)"
            >
              <circle
                :cx="n.x"
                :cy="n.y"
                :r="nodeRadius(n.id)"
                :fill="cycleColor(n.cycle)"
                :stroke="hoveredNode === n.id ? 'var(--gt-color-primary-dark)' : 'var(--gt-color-bg-white)'"
                :stroke-width="hoveredNode === n.id ? 2 : 1"
              />
              <text
                :x="n.x"
                :y="n.y + 3"
                text-anchor="middle"
                fill="var(--gt-color-text-inverse)"
                font-size="9"
                font-weight="600"
                pointer-events="none"
              >
                {{ n.id }}
              </text>
            </g>
          </g>
        </svg>

        <!-- Tooltip -->
        <div
          v-if="tooltip.visible"
          class="gt-wp-dg-tooltip"
          :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }"
        >
          <div class="gt-wp-dg-tt-code">{{ tooltip.code }}</div>
          <div class="gt-wp-dg-tt-name">{{ tooltip.name || '—' }}</div>
          <div class="gt-wp-dg-tt-meta">
            上游 {{ tooltip.incoming }} · 下游 {{ tooltip.outgoing }}
          </div>
        </div>
      </div>

      <!-- 右侧图例 -->
      <div class="gt-wp-dg-legend">
        <h4 class="gt-wp-dg-legend-title">循环色谱</h4>
        <ul class="gt-wp-dg-legend-list">
          <li v-for="c in cycleList" :key="c">
            <span class="gt-wp-dg-legend-dot" :style="{ background: cycleColor(c) }"></span>
            <span class="gt-wp-dg-legend-name">{{ c }} {{ cycleNames[c] || '' }}</span>
            <span class="gt-wp-dg-legend-count">{{ cycleNodeCount[c] || 0 }}</span>
          </li>
        </ul>
        <h4 class="gt-wp-dg-legend-title">边样式</h4>
        <ul class="gt-wp-dg-legend-list">
          <li>
            <svg width="40" height="6" style="vertical-align: middle">
              <line x1="0" y1="3" x2="40" y2="3" :stroke="severityColor('blocking')" stroke-width="2.5" />
            </svg>
            <span class="gt-wp-dg-legend-name">阻断（blocking）</span>
          </li>
          <li>
            <svg width="40" height="6" style="vertical-align: middle">
              <line x1="0" y1="3" x2="40" y2="3" :stroke="severityColor('required')" stroke-width="2" />
            </svg>
            <span class="gt-wp-dg-legend-name">必需（required）</span>
          </li>
          <li>
            <svg width="40" height="6" style="vertical-align: middle">
              <line x1="0" y1="3" x2="40" y2="3" :stroke="severityColor('warning')" stroke-width="1.5" stroke-dasharray="4,3" />
            </svg>
            <span class="gt-wp-dg-legend-name">警告（warning）</span>
          </li>
          <li>
            <svg width="40" height="6" style="vertical-align: middle">
              <line x1="0" y1="3" x2="40" y2="3" :stroke="severityColor('recommended')" stroke-width="1.2" stroke-dasharray="6,4" />
            </svg>
            <span class="gt-wp-dg-legend-name">推荐（recommended）</span>
          </li>
          <li>
            <svg width="40" height="6" style="vertical-align: middle">
              <line x1="0" y1="3" x2="40" y2="3" :stroke="severityColor('info')" stroke-width="1" stroke-dasharray="2,2" />
            </svg>
            <span class="gt-wp-dg-legend-name">提示（info）</span>
          </li>
        </ul>
        <p class="gt-wp-dg-legend-tip">
          点击节点：跳转底稿编辑器<br>
          悬停节点：高亮关联边
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import http from '@/utils/http'
import { wpAI } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

interface GraphNode {
  id: string
  cycle: string
  name?: string
}
interface GraphEdge {
  ref_id: string
  source: string
  target: string
  severity: string
  category: string
  description: string
}

const props = defineProps<{
  projectId?: string
}>()

const emit = defineEmits<{
  navigate: [code: string]
}>()

const SVG_SIZE = 800
const CENTER = SVG_SIZE / 2
const RADIUS = 300
const LABEL_RADIUS = 350

const loading = ref(true)
const nodes = ref<GraphNode[]>([])
const edges = ref<GraphEdge[]>([])
const stats = ref({ totalNodes: 0, totalEdges: 0 })

// 14 循环代码（致同体系）
const ALL_CYCLES = ['B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'A', 'S']
const cycleNames: Record<string, string> = {
  A: '完成阶段', B: '风险评估', C: '控制测试',
  D: '收入循环', E: '货币资金', F: '存货', G: '投资',
  H: '固定资产', I: '无形资产', J: '职工薪酬',
  K: '管理费用', L: '债务', M: '权益', N: '税金',
  S: '特定项目',
}

// 配色（不使用 CSS token，因为是分类色谱）
const CYCLE_PALETTE: Record<string, string> = {
  D: '#52b788', // 绿
  E: '#4392f1', // 蓝
  F: '#f08c2e', // 橙
  G: '#9b59b6', // 紫
  H: '#e63946', // 红
  I: '#06b6d4', // 青
  J: '#ec407a', // 粉
  K: '#fbc02d', // 黄
  L: '#8d6e63', // 棕
  M: '#90a4ae', // 灰
  N: '#26a69a', // 蓝绿
  B: '#7e57c2', // 紫罗兰
  C: '#d81b60', // 洋红
  A: '#ff7043', // 三文鱼
  S: '#9ccc65', // 青柠
  REPORT: '#5c6bc0',
  NOTE: '#ab47bc',
  '?': '#bdbdbd',
}

function cycleColor(cycle: string): string {
  return CYCLE_PALETTE[cycle] || '#9e9e9e'
}

function severityColor(severity: string): string {
  if (severity === 'blocking') return '#d32f2f'
  if (severity === 'required') return '#7c5cbf'
  if (severity === 'warning') return '#f57c00'
  if (severity === 'recommended') return '#4392f1'
  if (severity === 'info') return '#9e9e9e'
  return '#9e9e9e'
}

// 筛选状态
const showAllCycles = ref(true)
const visibleCycles = ref<string[]>([...ALL_CYCLES, 'REPORT', 'NOTE'])
const severityFilter = ref<'all' | 'blocking' | 'warning' | 'info' | 'required' | 'recommended'>('all')
const hoveredNode = ref<string | null>(null)

function onToggleAllCycles(val: any) {
  if (val === true || val === 'true') {
    visibleCycles.value = [...ALL_CYCLES, 'REPORT', 'NOTE']
  } else {
    visibleCycles.value = []
  }
}

// 节点圆形分布
const nodePositions = computed<Map<string, { x: number; y: number; cycle: string; name: string }>>(() => {
  const map = new Map<string, { x: number; y: number; cycle: string; name: string }>()
  const filtered = nodes.value.filter(n => visibleCycles.value.includes(n.cycle))

  // 按 cycle 排序，再按 id 排序，使同 cycle 节点相邻
  const sorted = [...filtered].sort((a, b) => {
    const ca = ALL_CYCLES.indexOf(a.cycle)
    const cb = ALL_CYCLES.indexOf(b.cycle)
    if (ca !== cb) return ca - cb
    return a.id.localeCompare(b.id)
  })

  const total = sorted.length || 1
  sorted.forEach((n, i) => {
    const angle = (i / total) * 2 * Math.PI - Math.PI / 2 // 起点为顶部
    const x = CENTER + RADIUS * Math.cos(angle)
    const y = CENTER + RADIUS * Math.sin(angle)
    map.set(n.id, { x, y, cycle: n.cycle, name: n.name || '' })
  })

  return map
})

const renderedNodes = computed(() => {
  const result: Array<{ id: string; x: number; y: number; cycle: string; name: string }> = []
  for (const [id, pos] of nodePositions.value) {
    result.push({ id, ...pos })
  }
  return result
})

// 循环节点计数
const cycleNodeCount = computed<Record<string, number>>(() => {
  const c: Record<string, number> = {}
  for (const n of nodes.value) {
    c[n.cycle] = (c[n.cycle] || 0) + 1
  }
  return c
})

const cycleList = computed(() => {
  return ALL_CYCLES.filter(c => (cycleNodeCount.value[c] || 0) > 0)
})

// 边筛选+渲染
const filteredEdges = computed<GraphEdge[]>(() => {
  return edges.value.filter(e => {
    if (severityFilter.value !== 'all' && e.severity !== severityFilter.value) return false
    if (!nodePositions.value.has(e.source) || !nodePositions.value.has(e.target)) return false
    return true
  })
})

interface RenderedEdge extends GraphEdge {
  x1: number; y1: number; x2: number; y2: number
}

const renderedEdges = computed<RenderedEdge[]>(() => {
  return filteredEdges.value.map(e => {
    const s = nodePositions.value.get(e.source)!
    const t = nodePositions.value.get(e.target)!
    return { ...e, x1: s.x, y1: s.y, x2: t.x, y2: t.y }
  })
})

// 连接节点（hover 高亮用）
const connectedNodes = computed<Set<string>>(() => {
  if (!hoveredNode.value) return new Set()
  const set = new Set<string>([hoveredNode.value])
  for (const e of filteredEdges.value) {
    if (e.source === hoveredNode.value) set.add(e.target)
    else if (e.target === hoveredNode.value) set.add(e.source)
  }
  return set
})

function nodeRadius(id: string): number {
  if (hoveredNode.value === id) return 16
  if (hoveredNode.value && connectedNodes.value.has(id)) return 13
  return 11
}

function edgeStroke(e: RenderedEdge): string {
  if (hoveredNode.value && (e.source === hoveredNode.value || e.target === hoveredNode.value)) {
    return severityColor(e.severity)
  }
  return severityColor(e.severity)
}

function edgeWidth(e: RenderedEdge): number {
  if (hoveredNode.value && (e.source === hoveredNode.value || e.target === hoveredNode.value)) {
    if (e.severity === 'blocking') return 3
    if (e.severity === 'required') return 2.5
    return 2
  }
  if (e.severity === 'blocking') return 2
  if (e.severity === 'required') return 1.8
  return 1
}

function edgeDash(e: RenderedEdge): string {
  if (e.severity === 'warning') return '4,3'
  if (e.severity === 'info') return '2,2'
  if (e.severity === 'recommended') return '6,4'
  return ''
}

function edgeOpacity(e: RenderedEdge): number {
  if (!hoveredNode.value) return 0.5
  if (e.source === hoveredNode.value || e.target === hoveredNode.value) return 1
  return 0.1
}

// 循环弧（外圈 sector）
const cycleArcs = computed(() => {
  // 按已分配位置统计每个 cycle 占据的角度范围
  const ranges: Record<string, { start: number; end: number }> = {}
  const filtered = nodes.value.filter(n => visibleCycles.value.includes(n.cycle))
  const sorted = [...filtered].sort((a, b) => {
    const ca = ALL_CYCLES.indexOf(a.cycle)
    const cb = ALL_CYCLES.indexOf(b.cycle)
    if (ca !== cb) return ca - cb
    return a.id.localeCompare(b.id)
  })
  const total = sorted.length || 1
  sorted.forEach((n, i) => {
    const angle = (i / total) * 2 * Math.PI - Math.PI / 2
    if (!ranges[n.cycle]) ranges[n.cycle] = { start: angle, end: angle }
    ranges[n.cycle].end = angle
  })

  return Object.entries(ranges)
    .filter(([cycle]) => ALL_CYCLES.includes(cycle))
    .map(([cycle, r]) => {
      const arcRadius = RADIUS + 25
      const x1 = CENTER + arcRadius * Math.cos(r.start)
      const y1 = CENTER + arcRadius * Math.sin(r.start)
      const x2 = CENTER + arcRadius * Math.cos(r.end)
      const y2 = CENTER + arcRadius * Math.sin(r.end)
      const largeArc = r.end - r.start > Math.PI ? 1 : 0
      const path = `M ${x1} ${y1} A ${arcRadius} ${arcRadius} 0 ${largeArc} 1 ${x2} ${y2}`
      const midAngle = (r.start + r.end) / 2
      const labelX = CENTER + LABEL_RADIUS * Math.cos(midAngle)
      const labelY = CENTER + LABEL_RADIUS * Math.sin(midAngle)
      return { cycle, path, labelX, labelY }
    })
})

// Tooltip
const tooltip = ref({
  visible: false,
  x: 0,
  y: 0,
  code: '',
  name: '',
  incoming: 0,
  outgoing: 0,
})

function onNodeHover(id: string, ev: MouseEvent) {
  hoveredNode.value = id
  const node = nodePositions.value.get(id)
  if (!node) return
  const rect = (ev.currentTarget as SVGElement).ownerSVGElement?.getBoundingClientRect()
  if (rect) {
    const scaleX = rect.width / SVG_SIZE
    const scaleY = rect.height / SVG_SIZE
    tooltip.value = {
      visible: true,
      x: node.x * scaleX + 12,
      y: node.y * scaleY + 12,
      code: id,
      name: node.name,
      incoming: filteredEdges.value.filter(e => e.target === id).length,
      outgoing: filteredEdges.value.filter(e => e.source === id).length,
    }
  }
}

function onSvgLeave() {
  hoveredNode.value = null
  tooltip.value.visible = false
}

function onNodeClick(id: string) {
  emit('navigate', id)
}

async function loadGraph() {
  loading.value = true
  try {
    const data: any = await http.get(wpAI.dependencyGraph, {
      validateStatus: (s: number) => s < 600,
    }).then(r => r.data)
    nodes.value = data?.nodes || []
    edges.value = data?.edges || []
    stats.value = {
      totalNodes: data?.stats?.total_nodes || nodes.value.length,
      totalEdges: data?.stats?.total_edges || edges.value.length,
    }
  } catch (e: any) {
    handleApiError(e, '加载依赖图')
  } finally {
    loading.value = false
  }
}

// projectId is optional for context only
void props.projectId

onMounted(() => {
  loadGraph()
})
</script>

<style scoped>
.gt-wp-dep-graph {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: var(--gt-space-3);
}

.gt-wp-dg-toolbar {
  background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm);
  padding: var(--gt-space-3);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--gt-space-2);
}

.gt-wp-dg-stats {
  display: flex;
  gap: var(--gt-space-3);
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary);
}
.gt-wp-dg-stats strong {
  color: var(--gt-color-primary);
  font-size: var(--gt-font-size-md);
}

.gt-wp-dg-filters {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  flex-wrap: wrap;
}
.gt-wp-dg-filter-label {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
}
.gt-wp-dg-cycles {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.gt-wp-dg-cycle-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 5px;
  margin-right: 4px;
  vertical-align: middle;
}

.gt-wp-dg-body {
  display: flex;
  gap: var(--gt-space-3);
  flex: 1;
  min-height: 0;
}

.gt-wp-dg-canvas {
  flex: 1;
  background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm);
  padding: var(--gt-space-3);
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.gt-wp-dg-svg {
  max-width: 100%;
  max-height: 100%;
  width: 100%;
  height: 100%;
}

.gt-wp-dg-loading {
  font-size: var(--gt-font-size-md);
  color: var(--gt-color-text-tertiary);
  padding: var(--gt-space-5);
}

.gt-wp-dg-node {
  cursor: pointer;
  transition: opacity 0.15s;
}
.gt-wp-dg-node.is-dimmed {
  opacity: 0.2;
}

.gt-wp-dg-edges line {
  transition: opacity 0.15s, stroke-width 0.15s;
}

.gt-wp-dg-tooltip {
  position: absolute;
  background: var(--gt-color-bg-white);
  border: 1px solid var(--gt-color-border);
  border-radius: var(--gt-radius-sm);
  padding: var(--gt-space-2);
  pointer-events: none;
  box-shadow: var(--gt-shadow-md);
  font-size: var(--gt-font-size-xs);
  min-width: 120px;
  z-index: 10;
}
.gt-wp-dg-tt-code {
  font-weight: 700;
  color: var(--gt-color-primary);
  font-size: var(--gt-font-size-sm);
}
.gt-wp-dg-tt-name {
  color: var(--gt-color-text-primary);
  margin: 2px 0;
}
.gt-wp-dg-tt-meta {
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-xs);
}

.gt-wp-dg-legend {
  width: 240px;
  min-width: 240px;
  background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm);
  padding: var(--gt-space-3);
  overflow-y: auto;
}
.gt-wp-dg-legend-title {
  margin: 0 0 var(--gt-space-2);
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-primary);
  font-weight: 600;
}
.gt-wp-dg-legend-list {
  list-style: none;
  padding: 0;
  margin: 0 0 var(--gt-space-3);
}
.gt-wp-dg-legend-list li {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--gt-font-size-xs);
  padding: 3px 0;
  color: var(--gt-color-text-secondary);
}
.gt-wp-dg-legend-dot {
  width: 12px;
  height: 12px;
  border-radius: 6px;
  flex-shrink: 0;
}
.gt-wp-dg-legend-name {
  flex: 1;
  color: var(--gt-color-text-primary);
}
.gt-wp-dg-legend-count {
  color: var(--gt-color-text-tertiary);
}
.gt-wp-dg-legend-tip {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
  margin: 0;
  line-height: 1.6;
}
</style>
