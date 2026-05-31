<template>
  <!-- C.2.5: 前端版本树可视化 -->
  <el-drawer
    v-model="visible"
    title="章节版本历史"
    direction="rtl"
    size="420px"
  >
    <div class="version-panel">
      <!-- 分支选择 -->
      <div class="version-branches" v-if="branches.length">
        <el-radio-group v-model="selectedBranch" size="small" @change="loadTree">
          <el-radio-button v-for="b in branches" :key="b" :value="b">{{ b }}</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 版本节点列表（时间线） -->
      <el-timeline v-if="nodes.length" style="margin-top: 16px">
        <el-timeline-item
          v-for="node in filteredNodes"
          :key="node.id"
          :timestamp="formatTime(node.created_at)"
          :type="node.branch === 'main' ? 'primary' : 'warning'"
          :hollow="selectedNodes.includes(node.id)"
        >
          <div class="version-node" @click="toggleSelect(node.id)">
            <div class="version-label">{{ node.label }}</div>
            <div class="version-meta">
              <el-tag size="small" type="info">{{ node.branch }}</el-tag>
              <span style="color: #909399; font-size: 11px; margin-left: 6px">{{ node.created_by }}</span>
            </div>
          </div>
        </el-timeline-item>
      </el-timeline>

      <el-empty v-else-if="!loading" description="暂无版本记录" />

      <!-- Diff 对比 -->
      <div v-if="selectedNodes.length === 2" class="version-diff">
        <el-button type="primary" size="small" :loading="diffLoading" @click="computeDiff">
          对比选中的 2 个版本
        </el-button>
        <el-table v-if="diffResult.length" :data="diffResult" size="small" border style="margin-top: 8px">
          <el-table-column prop="key" label="字段" width="120" />
          <el-table-column label="类型" width="70">
            <template #default="{ row }">
              <el-tag :type="row.type === 'add' ? 'success' : row.type === 'remove' ? 'danger' : 'warning'" size="small">
                {{ row.type === 'add' ? '新增' : row.type === 'remove' ? '删除' : '修改' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="value_a" label="版本A" />
          <el-table-column prop="value_b" label="版本B" />
        </el-table>
      </div>

      <!-- Fork 操作 -->
      <div class="version-actions" style="margin-top: 16px">
        <el-button size="small" @click="handleFork">🔀 创建分支</el-button>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'
import { ElMessage, ElMessageBox } from 'element-plus'

interface Props {
  modelValue: boolean
  projectId: string
  year: number
  sectionId: string
}

const props = defineProps<Props>()
const emit = defineEmits<{ 'update:modelValue': [val: boolean] }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const loading = ref(false)
const diffLoading = ref(false)
const nodes = ref<any[]>([])
const branches = ref<string[]>([])
const selectedBranch = ref('main')
const selectedNodes = ref<string[]>([])
const diffResult = ref<any[]>([])

const filteredNodes = computed(() =>
  selectedBranch.value
    ? nodes.value.filter(n => n.branch === selectedBranch.value)
    : nodes.value
)

watch(() => props.sectionId, () => {
  if (visible.value && props.sectionId) loadTree()
})

watch(visible, (v) => {
  if (v && props.sectionId) loadTree()
})

async function loadTree() {
  loading.value = true
  try {
    const resp: any = await api.get(
      `/api/disclosure-notes/${props.projectId}/${props.year}/sections/${props.sectionId}/version-tree`
    )
    nodes.value = resp?.nodes || []
    branches.value = resp?.branches || ['main']
    selectedNodes.value = []
    diffResult.value = []
  } catch {
    nodes.value = []
    branches.value = ['main']
  } finally {
    loading.value = false
  }
}

function toggleSelect(nodeId: string) {
  const idx = selectedNodes.value.indexOf(nodeId)
  if (idx >= 0) {
    selectedNodes.value.splice(idx, 1)
  } else if (selectedNodes.value.length < 2) {
    selectedNodes.value.push(nodeId)
  } else {
    selectedNodes.value = [selectedNodes.value[1], nodeId]
  }
  diffResult.value = []
}

async function computeDiff() {
  if (selectedNodes.value.length !== 2) return
  diffLoading.value = true
  try {
    const resp: any = await api.get(
      `/api/disclosure-notes/${props.projectId}/${props.year}/sections/${props.sectionId}/diff`,
      { params: { node_a: selectedNodes.value[0], node_b: selectedNodes.value[1] } }
    )
    diffResult.value = resp || []
  } catch (e: any) {
    handleApiError(e, '对比')
  } finally {
    diffLoading.value = false
  }
}

async function handleFork() {
  const { value: branchName } = await ElMessageBox.prompt('输入新分支名称', '创建分支', {
    inputPattern: /^[a-zA-Z0-9_-]+$/,
    inputErrorMessage: '仅支持字母、数字、下划线、横线',
  }).catch(() => ({ value: '' }))

  if (!branchName) return

  try {
    await api.post(
      `/api/disclosure-notes/${props.projectId}/${props.year}/sections/${props.sectionId}/fork`,
      { branch_name: branchName }
    )
    ElMessage.success(`分支 "${branchName}" 创建成功`)
    loadTree()
  } catch (e: any) {
    handleApiError(e, '创建')
  }
}

function formatTime(iso: string): string {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.version-panel {
  padding: 0 4px;
}
.version-branches {
  margin-bottom: 12px;
}
.version-node {
  cursor: pointer;
  padding: 4px 0;
}
.version-node:hover {
  background: #f5f7fa;
  border-radius: 4px;
}
.version-label {
  font-weight: 500;
  font-size: 13px;
}
.version-meta {
  margin-top: 4px;
}
.version-diff {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #ebeef5;
}
</style>
