<template>
  <div class="group-structure-tree">
    <div class="tree-toolbar">
      <el-button size="small" @click="handleAddRoot" plain>
        <span class="toolbar-icon">+</span> 添加集团
      </el-button>
      <el-button size="small" @click="refresh" :loading="loading" plain>刷新</el-button>
    </div>

    <el-tree
      ref="treeRef"
      :data="treeData"
      :props="treeProps"
      node-key="id"
      default-expand-all
      :expand-on-click-node="false"
      @node-contextmenu="handleContextMenu"
      @node-click="handleNodeClick"
      class="gt-tree"
    >
      <template #default="{ data }">
        <div class="tree-node-content">
          <span class="node-name">{{ data.companyName }}</span>
          <span class="node-share" v-if="data.shareholding !== null && data.shareholding !== undefined">
            {{ Number(data.shareholding).toFixed(2) }}%
          </span>
          <el-tag
            v-if="data.consolMethod"
            :type="consolMethodTagType(data.consolMethod)"
            size="small"
            class="node-badge"
          >
            {{ consolMethodLabel(data.consolMethod) }}
          </el-tag>
        </div>
      </template>
    </el-tree>

    <!-- Context Menu -->
    <div
      v-if="contextMenu.visible"
      class="context-menu"
      :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }"
      @click.stop
    >
      <div class="context-menu-item" @click="handleAddSubsidiary">
        <span class="menu-icon">+</span> 添加子公司
      </div>
      <div class="context-menu-item" @click="handleEditNode">
        <span class="menu-icon">✎</span> 编辑
      </div>
      <div class="context-menu-item danger" @click="handleDeleteNode">
        <span class="menu-icon">✕</span> 删除
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getCompanyTree, deleteCompany } from '@/services/consolidationApi'
import type { CompanyTreeNode } from '@/services/consolidationApi'

// ─── Props & Emits ───────────────────────────────────────────────────────────
const props = defineProps<{
  projectId: string
  year: number
}>()

const emit = defineEmits<{
  'node-click': [node: CompanyTreeNode]
  'node-add': [parentId: string | null, parentCode: string | null]
  'node-edit': [node: CompanyTreeNode]
  'node-delete': [node: CompanyTreeNode]
}>()

// ─── State ─────────────────────────────────────────────────────────────────
const treeRef = ref()
const loading = ref(false)
const treeData = ref<CompanyTreeNode[]>([])
const contextMenu = reactive({
  visible: false,
  x: 0,
  y: 0,
  currentNode: null as CompanyTreeNode | null,
})

const treeProps = {
  label: 'companyName',
  children: 'children',
}

// ─── Consolidation Method Helpers ──────────────────────────────────────────
function consolMethodLabel(method: string): string {
  const map: Record<string, string> = {
    full: '完全合并',
    proportional: '比例合并',
    equity: '权益法',
    exclude: '排除',
  }
  return map[method] || method
}

function consolMethodTagType(method: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = {
    full: 'primary',
    proportional: 'success',
    equity: 'warning',
    exclude: 'info',
  }
  return map[method] || ''
}

// ─── Data Loading ────────────────────────────────────────────────────────────
async function refresh() {
  loading.value = true
  try {
    const nodes = await getCompanyTree(props.projectId, props.year)
    treeData.value = nodes
  } catch (e) {
    ElMessage.error('加载集团架构失败')
  } finally {
    loading.value = false
  }
}

// ─── Event Handlers ─────────────────────────────────────────────────────────
function handleNodeClick(data: CompanyTreeNode) {
  emit('node-click', data)
}

function handleContextMenu(event: MouseEvent, data: CompanyTreeNode) {
  event.preventDefault()
  contextMenu.currentNode = data
  contextMenu.x = event.clientX
  contextMenu.y = event.clientY
  contextMenu.visible = true
}

function handleAddRoot() {
  emit('node-add', null, null)
}

function handleAddSubsidiary() {
  if (!contextMenu.currentNode) return
  emit('node-add', contextMenu.currentNode.id, contextMenu.currentNode.companyCode)
  contextMenu.visible = false
}

function handleEditNode() {
  if (!contextMenu.currentNode) return
  emit('node-edit', contextMenu.currentNode)
  contextMenu.visible = false
}

async function handleDeleteNode() {
  if (!contextMenu.currentNode) return
  contextMenu.visible = false
  await ElMessageBox.confirm(
    `确认删除「${contextMenu.currentNode.companyName}」？`,
    '删除确认',
    { type: 'warning' },
  )
  try {
    await deleteCompany(contextMenu.currentNode.id, props.projectId)
    emit('node-delete', contextMenu.currentNode)
    await refresh()
    ElMessage.success('删除成功')
  } catch {
    ElMessage.error('删除失败')
  }
}

function handleClickOutside() {
  contextMenu.visible = false
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(() => {
  refresh()
  document.addEventListener('click', handleClickOutside)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleClickOutside)
})

// Expose refresh for parent
defineExpose({ refresh })
</script>

<style scoped>
.group-structure-tree {
  position: relative;
}

.tree-toolbar {
  display: flex;
  gap: var(--gt-space-2);
  margin-bottom: var(--gt-space-3);
}

.toolbar-icon {
  font-weight: 700;
  margin-right: 4px;
}

.gt-tree {
  background: transparent;
  border: 1px solid var(--gt-color-primary);
  border-radius: var(--gt-radius-sm);
  padding: var(--gt-space-3);
}

:deep(.el-tree-node__content) {
  height: 32px;
  border-radius: var(--gt-radius-sm);
}

:deep(.el-tree-node__content:hover) {
  background-color: rgba(75, 45, 119, 0.06);
}

.tree-node-content {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  flex: 1;
}

.node-name {
  font-weight: 500;
  color: var(--gt-color-primary-dark);
}

.node-share {
  font-size: 12px;
  color: #888;
  background: #f0f0f0;
  border-radius: 4px;
  padding: 0 6px;
}

.node-badge {
  font-size: 11px;
}

/* Context Menu */
.context-menu {
  position: fixed;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: var(--gt-radius-sm);
  box-shadow: var(--gt-shadow-md);
  z-index: 9999;
  min-width: 140px;
  overflow: hidden;
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  padding: 8px 14px;
  cursor: pointer;
  font-size: 13px;
  color: var(--gt-color-primary-dark);
  transition: background 0.15s;
}

.context-menu-item:hover {
  background: rgba(75, 45, 119, 0.07);
}

.context-menu-item.danger {
  color: var(--gt-color-coral);
}

.menu-icon {
  font-size: 12px;
  width: 16px;
  text-align: center;
}
</style>
