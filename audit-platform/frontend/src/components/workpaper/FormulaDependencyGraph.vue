<script setup lang="ts">
/**
 * 公式管理依赖图视图 — 有向图+stale 高亮+编制顺序建议
 * Sprint 11 Task 11.12
 */
import { ref, onMounted, computed } from 'vue'
import { api } from '@/services/apiProxy'

interface GraphNode {
  id: string
  wp_code: string
  wp_name: string
  is_stale: boolean
  order?: number
}

interface GraphEdge {
  source: string
  target: string
  formula_type: string
}

const props = defineProps<{ projectId: string }>()

const nodes = ref<GraphNode[]>([])
const edges = ref<GraphEdge[]>([])
const loading = ref(false)
const selectedNode = ref<GraphNode | null>(null)

const suggestedOrder = computed(() => {
  // Topological sort suggestion based on edges
  return nodes.value
    .filter(n => n.order !== undefined)
    .sort((a, b) => (a.order || 0) - (b.order || 0))
})

async function loadGraph() {
  loading.value = true
  try {
    const data = await api.get(`/api/projects/${props.projectId}/workpapers/formula-dependencies`)
    const res = data as any
    nodes.value = res.nodes || []
    edges.value = res.edges || []
  } catch {
    // Use empty graph
  } finally {
    loading.value = false
  }
}

function selectNode(node: GraphNode) {
  selectedNode.value = node
}

function nodeClass(node: GraphNode) {
  return {
    'graph-node': true,
    'stale': node.is_stale,
    'selected': selectedNode.value?.id === node.id,
  }
}

onMounted(loadGraph)
</script>

<template>
  <div class="formula-dependency-graph" v-loading="loading">
    <div class="graph-header">
      <span class="title">公式依赖图</span>
      <el-tag v-if="nodes.some(n => n.is_stale)" type="warning" size="small">
        {{ nodes.filter(n => n.is_stale).length }} 个底稿需要更新
      </el-tag>
    </div>

    <!-- 简化的节点列表视图（完整实现需要 D3/ECharts 有向图） -->
    <div class="graph-container">
      <div class="nodes-panel">
        <div
          v-for="node in nodes"
          :key="node.id"
          :class="nodeClass(node)"
          @click="selectNode(node)"
        >
          <span class="node-code">{{ node.wp_code }}</span>
          <span class="node-name">{{ node.wp_name }}</span>
          <el-tag v-if="node.is_stale" type="warning" size="small">stale</el-tag>
        </div>
        <div v-if="nodes.length === 0" class="empty-tip">暂无公式依赖关系</div>
      </div>

      <!-- 编制顺序建议 -->
      <div v-if="suggestedOrder.length > 0" class="order-panel">
        <div class="order-title">建议编制顺序</div>
        <ol class="order-list">
          <li v-for="node in suggestedOrder" :key="node.id">
            {{ node.wp_code }} - {{ node.wp_name }}
          </li>
        </ol>
      </div>
    </div>

    <!-- 选中节点详情 -->
    <div v-if="selectedNode" class="node-detail">
      <h4>{{ selectedNode.wp_code }} - {{ selectedNode.wp_name }}</h4>
      <div class="edges-list">
        <div v-for="edge in edges.filter(e => e.source === selectedNode!.id)" :key="edge.target">
          依赖 → {{ nodes.find(n => n.id === edge.target)?.wp_code || edge.target }}
          <el-tag size="small">{{ edge.formula_type }}</el-tag>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.formula-dependency-graph { padding: 12px; }
.graph-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.title { font-weight: 600; font-size: 14px; }
.graph-container { display: flex; gap: 16px; }
.nodes-panel { flex: 1; }
.graph-node { padding: 8px 12px; border: 1px solid #e4e7ed; border-radius: 4px; margin-bottom: 4px; cursor: pointer; display: flex; align-items: center; gap: 8px; }
.graph-node:hover { border-color: #4b2d77; }
.graph-node.stale { background: #fdf6ec; border-color: #e6a23c; }
.graph-node.selected { border-color: #4b2d77; background: #f8f7fc; }
.node-code { font-weight: 600; font-size: 12px; }
.node-name { font-size: 13px; color: #606266; }
.order-panel { width: 200px; padding: 8px; background: #f5f7fa; border-radius: 4px; }
.order-title { font-size: 12px; font-weight: 600; margin-bottom: 8px; }
.order-list { font-size: 12px; padding-left: 16px; }
.node-detail { margin-top: 12px; padding: 8px; background: #f5f7fa; border-radius: 4px; }
.node-detail h4 { margin: 0 0 8px; font-size: 13px; }
.edges-list { font-size: 12px; }
.empty-tip { text-align: center; padding: 24px; color: #909399; }
</style>
