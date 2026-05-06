<template>
  <div class="task-tree-view">
    <!-- 顶部筛选栏 -->
    <div class="tree-toolbar">
      <el-select v-model="filters.root_level" placeholder="节点层级" clearable size="small" style="width:120px">
        <el-option label="单位" value="unit" />
        <el-option label="科目" value="account" />
        <el-option label="底稿" value="workpaper" />
        <el-option label="证据" value="evidence" />
      </el-select>
      <el-select v-model="filters.status" placeholder="状态" clearable size="small" style="width:120px">
        <el-option label="待处理" value="pending" />
        <el-option label="进行中" value="in_progress" />
        <el-option label="已阻断" value="blocked" />
        <el-option label="已完成" value="done" />
      </el-select>
      <el-button size="small" @click="loadData">刷新</el-button>
      <el-button size="small" type="primary" @click="loadStats">统计</el-button>
    </div>

    <div class="tree-content">
      <!-- 左栏：任务树 -->
      <div class="tree-left">
        <el-tree
          :data="treeData"
          :props="{ label: 'label', children: 'children' }"
          node-key="id"
          default-expand-all
          highlight-current
          @node-click="handleNodeClick"
        >
          <template #default="{ node: _node, data }">
            <span class="tree-node">
              <span class="node-status" :class="data.status">●</span>
              <span class="node-label">{{ data.label }}</span>
              <el-tag v-if="data.status === 'blocked'" type="danger" size="small">阻断</el-tag>
              <el-tag v-else-if="data.status === 'done'" type="success" size="small">完成</el-tag>
            </span>
          </template>
        </el-tree>
      </div>

      <!-- 右栏：节点详情 -->
      <div class="tree-right" v-if="selectedNode">
        <h4>{{ selectedNode.label }}</h4>
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="层级">{{ selectedNode.node_level }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="(statusTagType(selectedNode.status)) || undefined" size="small">{{ selectedNode.status }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="负责人">{{ selectedNode.assignee_id || '未分配' }}</el-descriptions-item>
          <el-descriptions-item label="截止时间">{{ selectedNode.due_at || '无' }}</el-descriptions-item>
        </el-descriptions>

        <div class="node-actions" style="margin-top:12px">
          <el-button size="small" @click="transitTo('in_progress')" :disabled="selectedNode.status !== 'pending'">开始</el-button>
          <el-button size="small" type="success" @click="transitTo('done')" :disabled="selectedNode.status !== 'in_progress'">完成</el-button>
          <el-button size="small" type="warning" @click="transitTo('blocked')" :disabled="selectedNode.status !== 'in_progress'">阻断</el-button>
          <el-button size="small" @click="transitTo('in_progress')" :disabled="selectedNode.status !== 'blocked'">解除阻断</el-button>
        </div>
      </div>
    </div>

    <!-- 统计弹窗 -->
    <el-dialog v-model="showStats" title="任务统计" width="500px" append-to-body>
      <el-table :data="statsRows" border size="small">
        <el-table-column prop="level" label="层级" width="100" />
        <el-table-column prop="pending" label="待处理" />
        <el-table-column prop="in_progress" label="进行中" />
        <el-table-column prop="blocked" label="阻断" />
        <el-table-column prop="done" label="完成" />
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listTaskTree, getTreeStats, transitNodeStatus, type TaskNode } from '@/services/governanceApi'

const route = useRoute()
const projectId = route.params.projectId as string

const filters = reactive({ root_level: '', status: '' })
const treeData = ref<any[]>([])
const selectedNode = ref<any>(null)
const showStats = ref(false)
const statsRows = ref<any[]>([])

interface TreeItem {
  id: string
  label: string
  node_level: string
  status: string
  assignee_id?: string
  due_at?: string
  children?: TreeItem[]
}

async function loadData() {
  try {
    const result = await listTaskTree({
      project_id: projectId,
      root_level: filters.root_level || undefined,
      status: filters.status || undefined,
      page_size: 200,
    })
    treeData.value = (result.items || []).map((n: TaskNode) => ({
      id: n.id,
      label: `[${n.node_level}] ${n.ref_id?.substring(0, 8)}`,
      node_level: n.node_level,
      status: n.status,
      assignee_id: n.assignee_id,
      due_at: n.due_at,
      children: [],
    }))
  } catch (e: any) {
    ElMessage.error(e.message || '加载任务树失败')
  }
}

function handleNodeClick(data: TreeItem) {
  selectedNode.value = data
}

function statusTagType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  if (status === 'blocked') return 'danger'
  if (status === 'done') return 'success'
  if (status === 'in_progress') return 'primary'
  return 'info'
}

async function transitTo(nextStatus: string) {
  if (!selectedNode.value) return
  try {
    await transitNodeStatus(selectedNode.value.id, nextStatus, 'current_user_id')
    ElMessage.success(`状态已更新为 ${nextStatus}`)
    selectedNode.value.status = nextStatus
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail?.message || '状态更新失败')
  }
}

async function loadStats() {
  try {
    const stats = await getTreeStats(projectId)
    statsRows.value = Object.entries(stats).map(([level, counts]: [string, any]) => ({
      level,
      pending: counts.pending || 0,
      in_progress: counts.in_progress || 0,
      blocked: counts.blocked || 0,
      done: counts.done || 0,
    }))
    showStats.value = true
  } catch (e: any) {
    ElMessage.error('加载统计失败')
  }
}

onMounted(loadData)
</script>

<style scoped>
.task-tree-view { padding: 16px; }
.tree-toolbar { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; }
.tree-content { display: flex; gap: 16px; }
.tree-left { flex: 1; min-width: 300px; border: 1px solid #eee; border-radius: 8px; padding: 12px; max-height: 600px; overflow-y: auto; }
.tree-right { width: 360px; border: 1px solid #eee; border-radius: 8px; padding: 16px; }
.tree-node { display: flex; align-items: center; gap: 6px; }
.node-status { font-size: 10px; }
.node-status.pending { color: #999; }
.node-status.in_progress { color: var(--el-color-primary); }
.node-status.blocked { color: var(--el-color-danger); }
.node-status.done { color: var(--el-color-success); }
</style>
