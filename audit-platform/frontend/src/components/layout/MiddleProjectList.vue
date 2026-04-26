<template>
  <div class="gt-project-list">
    <!-- 顶部操作栏 -->
    <div class="gt-list-header">
      <div class="gt-header-left">
        <el-button type="primary" size="small" @click="$router.push('/projects/new')">
          <el-icon><Plus /></el-icon> 新建项目
        </el-button>
        <el-button
          v-if="checkedIds.length > 0"
          type="danger"
          size="small"
          plain
          @click="confirmBatchDelete"
        >
          <el-icon><Delete /></el-icon> 删除选中 ({{ checkedIds.length }})
        </el-button>
      </div>
      <el-input
        v-model="searchText"
        placeholder="搜索项目..."
        size="small"
        clearable
        :prefix-icon="Search"
        style="width: 140px"
      />
    </div>

    <!-- 筛选栏 -->
    <div class="gt-list-filters">
      <el-checkbox
        :model-value="isAllChecked"
        :indeterminate="isIndeterminate"
        size="small"
        @change="toggleSelectAll"
      >全选</el-checkbox>
      <el-select v-model="filterStatus" placeholder="状态" size="small" clearable style="width: 90px">
        <el-option label="已创建" value="created" />
        <el-option label="计划中" value="planning" />
        <el-option label="执行中" value="execution" />
        <el-option label="已完成" value="completion" />
        <el-option label="已归档" value="archived" />
      </el-select>
      <el-select v-model="filterYear" placeholder="年度" size="small" clearable style="width: 80px">
        <el-option v-for="y in yearOptions" :key="y" :label="String(y)" :value="y" />
      </el-select>
    </div>

    <!-- 项目树形列表 -->
    <div class="gt-list-body" v-loading="loading">
      <div v-for="node in filteredTree" :key="node.id">
        <ProjectTreeNode
          :node="node"
          :depth="0"
          :selected-id="selectedId"
          :checked-ids="checkedIds"
          @select="selectProject"
          @toggle-check="toggleCheck"
          @delete="confirmDeleteOne"
          @edit="editProject"
        />
      </div>
      <el-empty v-if="!loading && filteredTree.length === 0" description="暂无项目" :image-size="60" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Search, Delete } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import ProjectTreeNode from './ProjectTreeNode.vue'

interface ProjectItem {
  id: string
  name: string | null
  client_name: string
  status: string
  report_scope: string | null
  parent_project_id: string | null
  consol_level: number
  children?: ProjectItem[]
}

const emit = defineEmits<{ (e: 'select', project: any): void }>()
const router = useRouter()

const loading = ref(false)
const projects = ref<ProjectItem[]>([])
const selectedId = ref<string | null>(null)
const searchText = ref('')
const filterStatus = ref('')
const filterYear = ref<number | null>(null)
const checkedIds = ref<string[]>([])

const currentYear = new Date().getFullYear()
const yearOptions = Array.from({ length: 5 }, (_, i) => currentYear - i)

/** 构建树形结构 */
function buildTree(flat: ProjectItem[]): ProjectItem[] {
  const map = new Map<string, ProjectItem>()
  const roots: ProjectItem[] = []

  for (const p of flat) {
    map.set(p.id, { ...p, children: [] })
  }
  for (const p of flat) {
    const node = map.get(p.id)!
    if (p.parent_project_id && map.has(p.parent_project_id)) {
      map.get(p.parent_project_id)!.children!.push(node)
    } else {
      roots.push(node)
    }
  }
  return roots
}

const filteredTree = computed(() => {
  let filtered = projects.value
  if (filterStatus.value) {
    filtered = filtered.filter(p => p.status === filterStatus.value)
  }
  if (searchText.value) {
    const q = searchText.value.toLowerCase()
    filtered = filtered.filter(p =>
      (p.name || '').toLowerCase().includes(q) ||
      (p.client_name || '').toLowerCase().includes(q)
    )
  }
  return buildTree(filtered)
})

/** 获取所有叶子节点 ID（用于全选） */
function getAllIds(nodes: ProjectItem[]): string[] {
  const ids: string[] = []
  function walk(list: ProjectItem[]) {
    for (const n of list) {
      ids.push(n.id)
      if (n.children?.length) walk(n.children)
    }
  }
  walk(nodes)
  return ids
}

const allVisibleIds = computed(() => getAllIds(filteredTree.value))
const isAllChecked = computed(() => allVisibleIds.value.length > 0 && checkedIds.value.length === allVisibleIds.value.length)
const isIndeterminate = computed(() => checkedIds.value.length > 0 && checkedIds.value.length < allVisibleIds.value.length)

function toggleSelectAll(val: boolean) {
  checkedIds.value = val ? [...allVisibleIds.value] : []
}

function toggleCheck(id: string, checked: boolean) {
  if (checked) {
    if (!checkedIds.value.includes(id)) checkedIds.value.push(id)
  } else {
    checkedIds.value = checkedIds.value.filter(i => i !== id)
  }
}

function selectProject(project: any) {
  selectedId.value = project.id
  localStorage.setItem('gt-last-project-id', project.id)
  emit('select', project)
}

function editProject(project: any) {
  router.push(`/projects/new?projectId=${project.id}`)
}

async function confirmDeleteOne(project: any) {
  try {
    await ElMessageBox.confirm(
      `确定要删除项目「${project.name || project.client_name || '未命名'}」吗？此操作不可恢复。`,
      '删除确认',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning' }
    )
    await api.delete(`/api/projects/${project.id}`)
    ElMessage.success('项目已删除')
    projects.value = projects.value.filter(p => p.id !== project.id)
    checkedIds.value = checkedIds.value.filter(i => i !== project.id)
    if (selectedId.value === project.id) selectedId.value = null
  } catch { /* 用户取消 */ }
}

async function confirmBatchDelete() {
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${checkedIds.value.length} 个项目吗？此操作不可恢复。`,
      '批量删除确认',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning' }
    )
    await api.post('/api/projects/batch-delete', { project_ids: checkedIds.value })
    ElMessage.success(`已删除 ${checkedIds.value.length} 个项目`)
    projects.value = projects.value.filter(p => !checkedIds.value.includes(p.id))
    if (selectedId.value && checkedIds.value.includes(selectedId.value)) selectedId.value = null
    checkedIds.value = []
  } catch { /* 用户取消 */ }
}

async function loadProjects() {
  loading.value = true
  try {
    const data = await api.get('/api/projects')
    projects.value = data ?? []
  } catch { /* ignore */ }
  finally { loading.value = false }
}

onMounted(loadProjects)
</script>

<style scoped>
.gt-project-list { display: flex; flex-direction: column; height: 100%; }
.gt-list-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: var(--gt-space-3);
  border-bottom: 1px solid var(--gt-color-border-light);
  flex-shrink: 0;
}
.gt-header-left { display: flex; gap: var(--gt-space-2); align-items: center; }
.gt-list-filters {
  display: flex; gap: var(--gt-space-2); align-items: center;
  padding: var(--gt-space-2) var(--gt-space-3);
  border-bottom: 1px solid var(--gt-color-border-light);
  flex-shrink: 0;
}
.gt-list-body { flex: 1; overflow-y: auto; padding: var(--gt-space-2); }
</style>
