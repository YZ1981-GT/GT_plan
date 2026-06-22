<template>
  <div class="gt-confirmation-summary">
    <!-- 旧格式降级：检测 htmlData 无 _format 时显示只读 GtGridSheet -->
    <template v-if="!isNewFormat">
      <div class="gt-confirmation-summary__legacy-notice">
        <el-alert type="info" :closable="false" show-icon>
          此底稿使用旧格式，仅支持只读查看。如需编辑请联系管理员升级格式。
        </el-alert>
      </div>
      <!-- Fallback: 使用 GtGridSheet 只读渲染 -->
      <GtGridSheet :html-data="htmlDataRef" :readonly="true" />
    </template>

    <!-- 新格式：完整 confirmation-v1 组件 -->
    <template v-else>
      <!-- 看板区 -->
      <el-collapse v-model="expandedSections">
        <el-collapse-item title="函证情况统计" name="dashboard">
          <ConfirmationDashboard :metrics="data.dashboardMetrics.value" :coverage="data.coverageMetrics.value" />
        </el-collapse-item>

        <!-- 科目 Tab -->
        <ConfirmationTabs :tabs="data.accountTabs.value" :active-tab="data.activeTab.value" @update:active-tab="data.activeTab.value = $event" />

        <!-- 视图切换按钮 -->
        <div class="gt-confirmation-summary__view-switch">
          <el-radio-group v-model="viewMode.viewMode.value" size="small">
            <el-radio-button value="list">列表视图</el-radio-button>
            <el-radio-button value="grid">完整表格</el-radio-button>
          </el-radio-group>
        </div>

        <!-- 列表视图 -->
        <template v-if="viewMode.viewMode.value === 'list'">
          <ConfirmationMaster
            :rows="data.filteredRows.value"
            :readonly="readonly"
            :selected-ids="selectedIds"
            @update:selected-ids="selectedIds = $event"
            @add="handleAdd"
            @delete="handleDelete"
            @save="handleSave"
            @row-click="handleRowClick"
          />
          <ConfirmationDetail
            :row="currentRow"
            :readonly="readonly"
            :dict-data="dictData"
            @update="handleFieldUpdate"
          />
        </template>

        <!-- 完整表格视图 -->
        <template v-else>
          <ConfirmationFullGrid
            :rows="data.filteredRows.value"
            :readonly="readonly"
            @update="handleGridUpdate"
          />
        </template>

        <!-- 辅助区（默认折叠） -->
        <el-collapse-item title="样本选择" name="sampling">
          <ConfirmationSampling :data="data.sampling.value" :readonly="readonly" :dict-data="dictData" @update="handleSamplingUpdate" />
        </el-collapse-item>

        <el-collapse-item title="审计说明" name="notes">
          <ConfirmationNotes :data="data.notes.value" :readonly="readonly" @update="handleNotesUpdate" />
        </el-collapse-item>

        <el-collapse-item title="审计结论" name="conclusion">
          <ConfirmationConclusion :data="data.conclusion.value" :readonly="readonly" @update="handleConclusionUpdate" />
        </el-collapse-item>
      </el-collapse>
    </template>

    <!-- 右键菜单 -->
    <ConfirmationContextMenu
      :visible="contextMenu.visible"
      :x="contextMenu.x"
      :y="contextMenu.y"
      :readonly="readonly"
      @update:visible="contextMenu.visible = $event"
      @action="handleContextAction"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent } from 'vue'
import { useConfirmationData } from './composables/useConfirmationData'
import { useViewMode } from './composables/useViewMode'
import type { ConfirmationRow } from './confirmationTypes'

import ConfirmationDashboard from './ConfirmationDashboard.vue'
import ConfirmationTabs from './ConfirmationTabs.vue'
import ConfirmationMaster from './ConfirmationMaster.vue'
import ConfirmationDetail from './ConfirmationDetail.vue'
import ConfirmationFullGrid from './ConfirmationFullGrid.vue'
import ConfirmationSampling from './ConfirmationSampling.vue'
import ConfirmationNotes from './ConfirmationNotes.vue'
import ConfirmationConclusion from './ConfirmationConclusion.vue'
import ConfirmationContextMenu from './ConfirmationContextMenu.vue'

// GtGridSheet for legacy fallback
const GtGridSheet = defineAsyncComponent(() => import('../GtGridSheet.vue'))

const props = defineProps<{
  htmlData: any
  readonly: boolean
  wpId?: string
  projectId?: string
  wpCode?: string
  year?: string
}>()

const emit = defineEmits<{
  (e: 'save', payload: any): void
}>()

// ─── 格式检测 ────────────────────────────────────────────────────────────────

const htmlDataRef = computed(() => props.htmlData)
const isNewFormat = computed(() => props.htmlData?._format === 'confirmation-v1')

// ─── 数据核心 ────────────────────────────────────────────────────────────────

const data = useConfirmationData({
  htmlData: () => props.htmlData,
  readonly: props.readonly,
})

const viewMode = useViewMode()

// ─── UI 状态 ──────────────────────────────────────────────────────────────────

const selectedIds = ref<string[]>([])
const currentRow = ref<ConfirmationRow | null>(null)
const contextMenu = ref({ visible: false, x: 0, y: 0 })

/** 默认展开：看板+列表可见，辅助区折叠 */
const expandedSections = ref<string[]>(['dashboard'])

// TODO: dictData 从 useDictStore 获取（暂用空）
const dictData = ref<Record<string, any[]>>({})

// ─── 事件处理 ────────────────────────────────────────────────────────────────

function handleAdd() {
  data.addRow()
}

function handleDelete() {
  data.deleteRows(selectedIds.value)
  selectedIds.value = []
}

function handleSave() {
  const payload = data.buildPayload()
  emit('save', payload)
}

function handleRowClick(row: ConfirmationRow) {
  currentRow.value = row
}

function handleFieldUpdate(field: string, value: any) {
  if (!currentRow.value?._row_id) return
  data.updateField(currentRow.value._row_id, field, value)
}

function handleGridUpdate(rowId: string, field: string, value: any) {
  data.updateField(rowId, field, value)
}

function handleSamplingUpdate(field: string, value: any) {
  ;(data.sampling.value as any)[field] = value
}

function handleNotesUpdate(field: string, value: any) {
  ;(data.notes.value as any)[field] = value
}

function handleConclusionUpdate(field: string, value: any) {
  ;(data.conclusion.value as any)[field] = value
}

function handleContextAction(action: string) {
  // Context menu actions - to be wired with row context
  console.log('[GtConfirmationSummary] context action:', action)
}
</script>

<style scoped>
.gt-confirmation-summary {
  padding: 8px 0;
}

.gt-confirmation-summary__legacy-notice {
  margin-bottom: 12px;
}

.gt-confirmation-summary__view-switch {
  display: flex;
  justify-content: flex-end;
  margin: 8px 0;
}
</style>
