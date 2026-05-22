<template>
  <div class="linkage-panorama-page">
    <div class="toolbar">
      <div class="toolbar-left">
        <el-icon class="back-icon" @click="goBack"><ArrowLeft /></el-icon>
        <span class="title">联动全景图</span>
        <span class="subtitle">{{ projectName ? `· ${projectName}` : '' }}</span>
      </div>
      <div class="toolbar-center">
        <CycleFilter
          v-if="d3Nodes.length > 0"
          v-model="selectedCycles"
          :counts="cycleCounts"
        />
        <SearchLocator
          v-if="d3Nodes.length > 0"
          :search-fn="searchNodes"
          @locate="handleLocate"
        />
        <el-switch
          v-if="hasStale"
          v-model="showOnlyStale"
          active-text="仅过期"
          inline-prompt
          size="small"
        />
        <span v-if="showOnlyStale && !hasStale" class="stats-no-stale">
          当前无 stale 底稿 ✓
        </span>
        <span v-if="statistics" class="stats-summary">
          {{ filteredNodes.length }}/{{ statistics.node_count }} 节点 ·
          {{ filteredLinks.length }}/{{ statistics.edge_count }} 边
          <span v-if="statistics.stale_node_count > 0" class="stats-stale">
            · ⚠ {{ statistics.stale_node_count }} 底稿过期
          </span>
        </span>
      </div>
      <div class="toolbar-right">
        <el-button :icon="Refresh" size="small" :loading="loading" @click="refresh">刷新</el-button>
        <el-button :icon="Aim" size="small" @click="handleFitToWindow">适应窗口</el-button>
        <el-button :icon="RefreshLeft" size="small" @click="handleResetView">重置视图</el-button>
      </div>
    </div>

    <div ref="graphAreaRef" v-loading="loading" class="graph-area">
      <ForceGraph
        v-if="!loading && !error && d3Nodes.length > 0"
        ref="forceGraphRef"
        :nodes="filteredNodes"
        :links="filteredLinks"
        :width="graphSize.width"
        :height="graphSize.height"
        :stale-only="showOnlyStale"
        @node-click="handleNodeClick"
      />
      <el-empty
        v-if="!loading && error"
        description="加载失败"
      >
        <template #image>
          <el-icon style="font-size: 48px; color: #f56c6c"><Warning /></el-icon>
        </template>
        <div class="empty-msg">{{ error }}</div>
        <el-button type="primary" @click="refresh">重试</el-button>
      </el-empty>
      <el-empty
        v-if="!loading && !error && d3Nodes.length === 0"
        description="无图数据"
      />
      <GraphLegend
        v-if="d3Nodes.length > 0"
        :visible-cycles="visibleCycles"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * LinkagePanoramaView.vue — 联动全景图页面（路由 /projects/:projectId/linkage-panorama）
 *
 * Validates: Requirements 1.1, 1.2, 1.3, 1.5, 5.1, 5.2, 5.3, 5.5
 */
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Refresh, RefreshLeft, Aim, Warning } from '@element-plus/icons-vue'
import ForceGraph from '@/components/panorama/ForceGraph.vue'
import GraphLegend from '@/components/panorama/GraphLegend.vue'
import CycleFilter from '@/components/panorama/CycleFilter.vue'
import SearchLocator from '@/components/panorama/SearchLocator.vue'
import { usePanoramaGraph, type D3Node } from '@/composables/usePanoramaGraph'
import { useNavigationStack } from '@/composables/useNavigationStack'
import { api } from '@/services/apiProxy'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)
const projectName = ref('')

const {
  loading,
  error,
  statistics,
  d3Nodes,
  selectedCycles,
  showOnlyStale,
  filteredNodes,
  filteredLinks,
  fetchGraphData,
  searchNodes,
  getCycleNodeCounts,
} = usePanoramaGraph(projectId)

const cycleCounts = computed(() => getCycleNodeCounts())
const hasStale = computed(() => (statistics.value?.stale_node_count ?? 0) > 0)

const forceGraphRef = ref<InstanceType<typeof ForceGraph> | null>(null)
const graphAreaRef = ref<HTMLDivElement | null>(null)
const graphSize = ref({ width: 1200, height: 800 })

// 当前图中实际出现的 cycles（图例只展示这些）
const visibleCycles = computed(() => {
  const set = new Set<string>()
  for (const n of d3Nodes.value) set.add(n.cycle)
  return Array.from(set)
})

// ─── 项目名称（轻量获取） ───────────────────────────────────────────────────
async function loadProjectName() {
  try {
    const project = await api.get<{ name: string }>(`/api/projects/${projectId.value}`)
    projectName.value = project.name ?? ''
  } catch {
    // 项目名拿不到不致命，静默
  }
}

// ─── 节点点击跳转 ──────────────────────────────────────────────────────────
const navStack = useNavigationStack()

function handleNodeClick(node: D3Node) {
  // 跳转前推入栈，支持 Backspace 返回全景图
  navStack.push({
    source_view: route.fullPath,
  })

  if (node.is_module) {
    // 跨模块虚拟节点：按 module 名称跳转对应视图
    // 注意：cross_wp_references.json 中 __module__D4 / __module__H1 等其实是底稿引用
    // 而非真实模块，先按 wp_code 模式尝试，找不到再走 module 路由
    const moduleName = node.label
    const businessWpPattern = /^[A-N]\d+/i
    if (businessWpPattern.test(moduleName)) {
      // 这是底稿 wp_code 误命名为 module（如 __module__D4）→ 跳到底稿列表搜索
      router
        .push({
          name: 'WorkpaperList',
          params: { projectId: projectId.value },
          query: { wp_code: moduleName },
        })
        .catch(() => ElMessage.warning('该底稿尚未创建'))
      return
    }
    const moduleRouteMap: Record<string, { name: string; needProjectId: boolean }> = {
      trial_balance: { name: 'TrialBalance', needProjectId: true },
      adjustments: { name: 'Adjustments', needProjectId: true },
      misstatements: { name: 'Misstatements', needProjectId: true },
      disclosure_notes: { name: 'DisclosureNotes', needProjectId: true },
      audit_report: { name: 'AuditReport', needProjectId: true },
      financial_report: { name: 'Reports', needProjectId: true },
      consolidation: { name: 'ConsolidationHub', needProjectId: false },
      audit_plan: { name: 'PartnerProjectDashboard', needProjectId: true },
    }
    const target = moduleRouteMap[moduleName]
    if (!target) {
      ElMessage.info(`模块 ${moduleName} 暂无对应视图`)
      return
    }
    const params = target.needProjectId ? { projectId: projectId.value } : {}
    router.push({ name: target.name, params }).catch(() => {
      ElMessage.warning(`跳转到 ${target.name} 失败`)
    })
    return
  }

  if (node.cycle === 'report') {
    router.push({ name: 'Reports', params: { projectId: projectId.value } }).catch(() => {})
    return
  }
  if (node.cycle === 'note') {
    router.push({ name: 'DisclosureNotes', params: { projectId: projectId.value } }).catch(() => {})
    return
  }

  // 业务底稿节点：跳转到 WorkpaperList 并用 query.wp_code 触发预选/筛选
  router
    .push({
      name: 'WorkpaperList',
      params: { projectId: projectId.value },
      query: { wp_code: node.wp_code },
    })
    .catch(() => {
      ElMessage.warning('该底稿尚未创建')
    })
}

// ─── 工具栏行为 ────────────────────────────────────────────────────────────
async function refresh() {
  await fetchGraphData()
}

function handleResetView() {
  forceGraphRef.value?.resetView()
}

function handleFitToWindow() {
  forceGraphRef.value?.fitToWindow()
}

function handleLocate(nodeId: string) {
  forceGraphRef.value?.locateNode(nodeId)
}

function goBack() {
  router.back()
}

// ─── 响应式尺寸 ────────────────────────────────────────────────────────────
function updateSize() {
  if (graphAreaRef.value) {
    const rect = graphAreaRef.value.getBoundingClientRect()
    graphSize.value = {
      width: Math.max(rect.width, 600),
      height: Math.max(rect.height, 400),
    }
  }
}

let resizeObserver: ResizeObserver | null = null

onMounted(async () => {
  // Phase 7 F13: URL query persistence for stale_only
  if (route.query.stale_only === '1') {
    showOnlyStale.value = true
  }

  await loadProjectName()
  await fetchGraphData()
  await nextTick()
  updateSize()
  if (window.ResizeObserver && graphAreaRef.value) {
    resizeObserver = new ResizeObserver(() => updateSize())
    resizeObserver.observe(graphAreaRef.value)
  } else {
    window.addEventListener('resize', updateSize)
  }
})

onBeforeUnmount(() => {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  } else {
    window.removeEventListener('resize', updateSize)
  }
})

// Phase 7 F13: Persist stale_only to URL query
watch(showOnlyStale, (val) => {
  const query = { ...route.query }
  if (val) {
    query.stale_only = '1'
  } else {
    delete query.stale_only
  }
  router.replace({ query }).catch(() => {})
})
</script>

<style scoped>
.linkage-panorama-page {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: calc(100vh - 60px);
  overflow: hidden;
  background: #fff;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
  padding: 0 16px;
  border-bottom: 1px solid #e0e0e0;
  background: #fff;
  flex-shrink: 0;
}

.toolbar-left,
.toolbar-center,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.back-icon {
  cursor: pointer;
  font-size: 18px;
  color: #555;
}

.back-icon:hover {
  color: #1976D2;
}

.title {
  font-size: 15px;
  font-weight: 600;
  color: #222;
}

.subtitle {
  font-size: 13px;
  color: #888;
}

.stats-summary {
  font-size: 12px;
  color: #555;
  background: #f5f5f5;
  padding: 4px 10px;
  border-radius: 12px;
}

.stats-stale {
  color: #d32f2f;
  font-weight: 500;
}

.graph-area {
  flex: 1;
  position: relative;
  overflow: hidden;
  background: #fafafa;
}

.empty-msg {
  margin: 8px 0;
  color: #888;
  font-size: 12px;
}
</style>
