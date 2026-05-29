<!--
  GtAuditFlowGraph.vue — 审计逻辑流程图（4 层横向）

  按 design §11.9 实现：
  - 4 层横向流程图：审计目标 → 识别风险 → 应对程序 → 关联底稿
  - 节点颜色反映状态（绿=完成 / 黄=进行中 / 灰=待执行 / 红=已裁剪）
  - 节点可点击跳转
  - SVG 连线层渲染 edges（轻量实现）

  锚定 spec workpaper-editor-slimdown Task 17.1 + 17.4 + 17.5 + 17.6
  Validates: US-16（程序表流程导航图）
-->

<template>
  <div class="gt-audit-flow-graph" v-show="expanded">
    <div class="gt-audit-flow-graph__container" ref="containerRef">
      <!-- 4 层横向布局 -->
      <div class="gt-flow-layer gt-flow-layer--objectives">
        <div class="gt-flow-layer__title">审计目标</div>
        <div class="gt-flow-layer__nodes">
          <div
            v-for="obj in graph.objectives"
            :key="obj.id"
            :ref="(el) => setNodeRef(obj.id, el as HTMLElement)"
            class="gt-flow-node gt-flow-node--objective"
          >
            {{ obj.name }}
          </div>
        </div>
      </div>

      <div class="gt-flow-layer gt-flow-layer--risks">
        <div class="gt-flow-layer__title">识别风险</div>
        <div class="gt-flow-layer__nodes">
          <div
            v-for="risk in graph.risks"
            :key="risk.id"
            :ref="(el) => setNodeRef(risk.id, el as HTMLElement)"
            class="gt-flow-node gt-flow-node--risk"
            :class="`gt-flow-node--level-${risk.level}`"
            :title="risk.description"
            @click="jumpToRisk(risk)"
          >
            <span class="gt-flow-node__text">{{ truncate(risk.description, 20) }}</span>
          </div>
        </div>
      </div>

      <div class="gt-flow-layer gt-flow-layer--procedures">
        <div class="gt-flow-layer__title">应对程序</div>
        <div class="gt-flow-layer__nodes">
          <div
            v-for="proc in graph.procedures"
            :key="proc.id"
            :ref="(el) => setNodeRef(proc.id, el as HTMLElement)"
            class="gt-flow-node gt-flow-node--procedure"
            :class="`gt-flow-node--status-${proc.status}`"
            @click="scrollToProgram(proc.program_no)"
          >
            <span class="gt-flow-node__no">{{ proc.program_no }}</span>
            <span class="gt-flow-node__text">{{ truncate(proc.category, 12) }}</span>
          </div>
        </div>
      </div>

      <div class="gt-flow-layer gt-flow-layer--workpapers">
        <div class="gt-flow-layer__title">关联底稿</div>
        <div class="gt-flow-layer__nodes">
          <GtIndexChip
            v-for="wp in graph.workpapers"
            :key="wp.wp_code"
            :ref="(el) => setNodeRef(`wp-${wp.wp_code}`, (el as any)?.$el)"
            :value="wp.wp_code"
            :validate="wp.exists"
          />
        </div>
      </div>

      <!-- SVG 连线层 -->
      <svg
        v-if="edgePaths.length > 0"
        class="gt-flow-edges"
        :width="svgWidth"
        :height="svgHeight"
      >
        <path
          v-for="(edge, idx) in edgePaths"
          :key="idx"
          :d="edge.path"
          class="gt-flow-edge"
          :class="`gt-flow-edge--${edge.type}`"
          fill="none"
        />
      </svg>
    </div>

    <!-- 空状态 -->
    <div v-if="isEmpty" class="gt-audit-flow-graph__empty">
      <el-empty description="暂无审计逻辑图数据" :image-size="60" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { api } from '@/services/apiProxy'
import GtIndexChip from './GtIndexChip.vue'

// ─── Props ───
const props = defineProps<{
  wpId: string
  projectId: string
  expanded: boolean
}>()

// ─── Emits ───
const emit = defineEmits<{
  'scroll-to-program': [programNo: number]
}>()

// ─── Types ───
interface AuditObjective {
  id: string
  name: string
}

interface IdentifiedRisk {
  id: string
  description: string
  level: string
  source_wp_code: string
}

interface ProcedureNode {
  id: string
  program_no: number
  category: string
  status: string
  assertions: string[]
}

interface LinkedWorkpaper {
  wp_code: string
  wp_name: string
  status: string
  exists: boolean
}

interface FlowEdge {
  from_id: string
  to_id: string
  type: string
}

interface GraphData {
  objectives: AuditObjective[]
  risks: IdentifiedRisk[]
  procedures: ProcedureNode[]
  workpapers: LinkedWorkpaper[]
  edges: FlowEdge[]
}

interface EdgePath {
  path: string
  type: string
}

// ─── State ───
const router = useRouter()
const route = useRoute()
const containerRef = ref<HTMLElement | null>(null)
const nodeRefs = ref<Record<string, HTMLElement | null>>({})
const graph = ref<GraphData>({
  objectives: [],
  risks: [],
  procedures: [],
  workpapers: [],
  edges: [],
})
const loading = ref(false)
const svgWidth = ref(0)
const svgHeight = ref(0)
const edgePaths = ref<EdgePath[]>([])

// ─── Computed ───
const isEmpty = computed(() => {
  return graph.value.procedures.length === 0 && graph.value.risks.length === 0
})

// ─── Methods ───
function setNodeRef(id: string, el: HTMLElement | null) {
  if (el) {
    nodeRefs.value[id] = el
  }
}

function truncate(text: string, maxLen: number): string {
  if (!text) return ''
  return text.length > maxLen ? text.slice(0, maxLen) + '…' : text
}

async function loadGraph() {
  if (!props.wpId) return
  loading.value = true
  try {
    const data = await api.get<GraphData>(`/api/workpapers/${props.wpId}/audit-flow-graph`)
    graph.value = data
    await nextTick()
    computeEdges()
  } catch (e) {
    // 静默失败，显示空状态
    graph.value = { objectives: [], risks: [], procedures: [], workpapers: [], edges: [] }
  } finally {
    loading.value = false
  }
}

function computeEdges() {
  if (!containerRef.value) return

  const containerRect = containerRef.value.getBoundingClientRect()
  svgWidth.value = containerRect.width
  svgHeight.value = containerRect.height

  const paths: EdgePath[] = []

  // 只渲染 risk→procedure 和 procedure→workpaper 的连线（避免过于密集）
  for (const edge of graph.value.edges) {
    if (edge.type === 'objective-risk') continue // 跳过目标→风险（太密集）

    const fromEl = nodeRefs.value[edge.from_id]
    const toEl = nodeRefs.value[edge.to_id]
    if (!fromEl || !toEl) continue

    const fromRect = fromEl.getBoundingClientRect()
    const toRect = toEl.getBoundingClientRect()

    // 计算相对于容器的坐标
    const x1 = fromRect.right - containerRect.left
    const y1 = fromRect.top + fromRect.height / 2 - containerRect.top
    const x2 = toRect.left - containerRect.left
    const y2 = toRect.top + toRect.height / 2 - containerRect.top

    // 贝塞尔曲线
    const midX = (x1 + x2) / 2
    const path = `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`

    paths.push({ path, type: edge.type })
  }

  edgePaths.value = paths
}

function jumpToRisk(risk: IdentifiedRisk) {
  if (risk.source_wp_code) {
    router.push({
      path: `/projects/${props.projectId}/workpapers/${risk.source_wp_code}/edit`,
    })
  }
}

function scrollToProgram(programNo: number) {
  emit('scroll-to-program', programNo)
}

// ─── Lifecycle ───
onMounted(() => {
  if (props.expanded) {
    loadGraph()
  }
})

watch(() => props.expanded, (val) => {
  if (val && graph.value.procedures.length === 0) {
    loadGraph()
  } else if (val) {
    nextTick(() => computeEdges())
  }
})
</script>

<style scoped>
.gt-audit-flow-graph {
  padding: 12px 16px;
  background: var(--el-bg-color-page);
  border-radius: 8px;
  margin-bottom: 12px;
  position: relative;
}

.gt-audit-flow-graph__container {
  display: flex;
  gap: 24px;
  align-items: flex-start;
  position: relative;
  min-height: 120px;
}

.gt-flow-layer {
  flex: 1;
  min-width: 0;
}

.gt-flow-layer__title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
  font-weight: 500;
  text-align: center;
}

.gt-flow-layer__nodes {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: center;
}

.gt-flow-node {
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: center;
  max-width: 140px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.gt-flow-node:hover {
  transform: scale(1.05);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* 目标节点 */
.gt-flow-node--objective {
  background: #e8f4fd;
  border: 1px solid #b3d8fd;
  color: #1677ff;
  cursor: default;
}

/* 风险节点 - 按级别着色 */
.gt-flow-node--risk {
  background: #fff7e6;
  border: 1px solid #ffd591;
  color: #d46b08;
}

.gt-flow-node--level-significant {
  background: #fff1f0;
  border: 1px solid #ffa39e;
  color: #cf1322;
}

.gt-flow-node--level-low {
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  color: #389e0d;
}

/* 程序节点 - 按状态着色 */
.gt-flow-node--procedure {
  display: flex;
  align-items: center;
  gap: 4px;
}

.gt-flow-node--status-completed {
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  color: #389e0d;
}

.gt-flow-node--status-in_progress {
  background: #fffbe6;
  border: 1px solid #ffe58f;
  color: #d48806;
}

.gt-flow-node--status-pending {
  background: #f5f5f5;
  border: 1px solid #d9d9d9;
  color: #8c8c8c;
}

.gt-flow-node--status-not_applicable {
  background: #fff1f0;
  border: 1px solid #ffa39e;
  color: #cf1322;
  text-decoration: line-through;
}

.gt-flow-node__no {
  font-weight: 600;
  min-width: 16px;
}

.gt-flow-node__text {
  overflow: hidden;
  text-overflow: ellipsis;
}

/* SVG 连线 */
.gt-flow-edges {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: none;
  z-index: 0;
}

.gt-flow-edge {
  stroke-width: 1.5;
  opacity: 0.4;
}

.gt-flow-edge--risk-procedure {
  stroke: #faad14;
}

.gt-flow-edge--procedure-workpaper {
  stroke: #1677ff;
}

.gt-flow-edge--objective-risk {
  stroke: #d9d9d9;
}

.gt-audit-flow-graph__empty {
  text-align: center;
  padding: 20px;
}
</style>
