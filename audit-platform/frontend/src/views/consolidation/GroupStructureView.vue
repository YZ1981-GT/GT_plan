<template>
  <div class="group-structure-view">
    <!-- Layout: Left tree panel + Right scope table -->
    <div class="view-layout">
      <!-- Left: Group Structure Tree -->
      <div class="left-panel">
        <div class="panel-header">
          <h3>集团架构树</h3>
          <span class="panel-hint">右键节点进行操作</span>
        </div>
        <GroupStructureTree
          ref="treeRef"
          :project-id="projectId"
          :year="year"
          @node-click="onNodeClick"
          @node-add="onNodeAdd"
          @node-edit="onNodeEdit"
          @node-delete="onNodeDelete"
        />
      </div>

      <!-- Right: Consol Scope Table -->
      <div class="right-panel">
        <div class="panel-header">
          <h3>合并范围管理</h3>
        </div>
        <ConsolScopeTable
          :project-id="projectId"
          :year="year"
        />
      </div>
    </div>

    <!-- Company Form Dialog (shared for add/edit) -->
    <CompanyForm
      v-model:visible="formVisible"
      :company="editingCompany"
      :parent-id="editingParentId"
      :parent-code="editingParentCode"
      :project-id="projectId"
      @saved="onFormSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, shallowRef } from 'vue'
import GroupStructureTree from '@/components/consolidation/GroupStructureTree.vue'
import CompanyForm from '@/components/consolidation/CompanyForm.vue'
import ConsolScopeTable from '@/components/consolidation/ConsolScopeTable.vue'
import type { CompanyTreeNode } from '@/services/consolidationApi'

// ─── Props ────────────────────────────────────────────────────────────────────
const props = defineProps<{
  projectId: string
  year: number
}>()

// ─── Tree Ref ────────────────────────────────────────────────────────────────
const treeRef = ref<InstanceType<typeof GroupStructureTree>>()

// ─── Form Dialog State ────────────────────────────────────────────────────────
const formVisible = ref(false)
const editingCompany = ref<CompanyTreeNode | null>(null)
const editingParentId = ref<string | null>(null)
const editingParentCode = ref<string | null>(null)

// ─── Event Handlers ──────────────────────────────────────────────────────────
function onNodeClick(node: CompanyTreeNode) {
  // Could show details in right panel in future
}

function onNodeAdd(parentId: string | null, parentCode: string | null) {
  editingCompany.value = null
  editingParentId.value = parentId
  editingParentCode.value = parentCode
  formVisible.value = true
}

function onNodeEdit(node: CompanyTreeNode) {
  editingCompany.value = node
  editingParentId.value = null
  editingParentCode.value = null
  formVisible.value = true
}

function onNodeDelete(_node: CompanyTreeNode) {
  // Tree will refresh automatically via treeRef.refresh()
}

async function onFormSaved() {
  // Refresh tree after save
  await treeRef.value?.refresh()
}
</script>

<style scoped>
.group-structure-view {
  display: flex;
  flex-direction: column;
}

.view-layout {
  display: grid;
  grid-template-columns: 360px 1fr;
  gap: var(--gt-space-4);
  min-height: 480px;
}

.left-panel,
.right-panel {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-3);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.panel-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--gt-color-primary-dark);
}

.panel-hint {
  font-size: 11px;
  color: #999;
}
</style>
