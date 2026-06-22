<template>
  <div class="gt-confirmation-followup">
    <!-- Legacy fallback -->
    <template v-if="isLegacyFormat">
      <div class="gt-confirmation-followup__legacy-notice">
        <el-alert
          title="旧格式数据"
          description="当前数据非 confirmation-followup-v1 格式，以只读网格模式展示"
          type="info"
          show-icon
          :closable="false"
        />
      </div>
    </template>

    <!-- Modern confirmation-followup-v1 layout -->
    <template v-else>
      <!-- Dashboard -->
      <FollowupDashboard :metrics="progressMetrics" />

      <!-- View switch -->
      <div class="gt-confirmation-followup__view-switch">
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button value="list">列表视图</el-radio-button>
          <el-radio-button value="grid">网格视图</el-radio-button>
        </el-radio-group>
      </div>

      <!-- List view: Master + Detail -->
      <div v-if="viewMode === 'list'" class="gt-confirmation-followup__list-view">
        <div class="gt-confirmation-followup__master">
          <FollowupMaster
            :rows="rows"
            :readonly="readonly"
            :selected-ids="selectedIds"
            :is-dirty="isDirty"
            @add="handleAdd"
            @delete="handleDelete"
            @save="handleSave"
            @import="handleImport"
            @row-click="handleRowClick"
            @update:selected-ids="selectedIds = $event"
          />
        </div>
        <div class="gt-confirmation-followup__detail">
          <FollowupDetail
            :row="currentRow"
            :readonly="readonly"
            @update="handleFieldUpdate"
          >
            <template #memo-preview>
              <FollowupMemoPreview
                :row="currentRow"
                :readonly="readonly"
                @update="handleFieldUpdate"
                @regenerate="handleRegenerate"
              />
            </template>
          </FollowupDetail>
        </div>
      </div>

      <!-- Grid view -->
      <div v-else class="gt-confirmation-followup__grid-view">
        <FollowupMaster
          :rows="rows"
          :readonly="readonly"
          :selected-ids="selectedIds"
          :is-dirty="isDirty"
          @add="handleAdd"
          @delete="handleDelete"
          @save="handleSave"
          @import="handleImport"
          @row-click="handleRowClick"
          @update:selected-ids="selectedIds = $event"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { FollowupRow } from './followupTypes'
import { useFollowupData } from './composables/useFollowupData'
import { useMemoCompose } from './composables/useMemoCompose'
import FollowupDashboard from './FollowupDashboard.vue'
import FollowupMaster from './FollowupMaster.vue'
import FollowupDetail from './FollowupDetail.vue'
import FollowupMemoPreview from './FollowupMemoPreview.vue'

// ─── Props & Emits ────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId?: string
  projectId?: string
  wpCode?: string
  year?: string
  htmlData?: any
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save', payload: any): void
}>()

// ─── Readonly computed ────────────────────────────────────────────────────────

const readonly = computed(() => props.readonly ?? false)

// ─── Legacy format check ──────────────────────────────────────────────────────

const isLegacyFormat = computed(() => {
  const data = props.htmlData
  return data && data._format !== 'confirmation-followup-v1'
})

// ─── Data composable ─────────────────────────────────────────────────────────

const {
  rows,
  isDirty,
  addRow,
  deleteRows,
  updateField,
  importRows,
  progressMetrics,
  buildPayload,
} = useFollowupData({
  htmlData: () => props.htmlData,
  readonly: readonly.value,
})

// ─── Memo compose ────────────────────────────────────────────────────────────

const { applyToRow, regenerate } = useMemoCompose()

// ─── UI state ────────────────────────────────────────────────────────────────

const viewMode = ref<'list' | 'grid'>('list')
const selectedIds = ref<string[]>([])
const currentRow = ref<FollowupRow | null>(null)

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAdd() {
  const newRow = addRow()
  currentRow.value = newRow
}

function handleDelete() {
  deleteRows(selectedIds.value)
  selectedIds.value = []
  if (currentRow.value && !rows.value.find((r) => r._row_id === currentRow.value?._row_id)) {
    currentRow.value = null
  }
}

function handleSave() {
  // Auto-apply memo to all non-overridden rows before saving
  rows.value.forEach((row, idx) => {
    if (!row.memo_overridden) {
      const updated = applyToRow(row)
      rows.value[idx] = { ...row, memo_text: updated.memo_text }
    }
  })
  const payload = buildPayload()
  emit('save', payload)
}

function handleImport() {
  // Stub: open import dialog
  console.info('[FollowupD03] Import triggered')
}

function handleRowClick(row: FollowupRow) {
  currentRow.value = row
}

function handleFieldUpdate(field: string, value: any) {
  if (!currentRow.value?._row_id) return
  updateField(currentRow.value._row_id, field, value)
}

function handleRegenerate() {
  if (!currentRow.value) return
  const regenerated = regenerate(currentRow.value)
  // Apply regenerated fields back
  updateField(currentRow.value._row_id!, 'memo_text', regenerated.memo_text)
  updateField(currentRow.value._row_id!, 'memo_overridden', false)
}
</script>

<style scoped>
.gt-confirmation-followup {
  padding: 12px;
}

.gt-confirmation-followup__legacy-notice {
  margin-bottom: 16px;
}

.gt-confirmation-followup__view-switch {
  margin-bottom: 12px;
}

.gt-confirmation-followup__list-view {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}

.gt-confirmation-followup__grid-view {
  width: 100%;
}

@media (min-width: 1400px) {
  .gt-confirmation-followup__list-view {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
