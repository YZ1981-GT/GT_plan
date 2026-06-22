<template>
  <div class="gt-confirmation-entity-verify">
    <!-- Legacy fallback -->
    <template v-if="isLegacyFormat">
      <div class="gt-confirmation-entity-verify__legacy-notice">
        <el-alert
          title="旧格式数据"
          description="当前数据非 entity-verify-v1 格式，以只读网格模式展示"
          type="info"
          show-icon
          :closable="false"
        />
      </div>
      <!-- GtGridSheet readonly fallback would render here -->
    </template>

    <!-- Modern entity-verify-v1 layout -->
    <template v-else>
      <!-- Dashboard -->
      <EntityVerifyDashboard :metrics="progressMetrics" />

      <!-- Fraud Panel (collapsible) -->
      <el-collapse v-model="activePanels" class="gt-confirmation-entity-verify__panels">
        <el-collapse-item name="fraud" title="反舞弊筛查">
          <template #title>
            <span>反舞弊筛查</span>
            <el-badge
              v-if="totalFraudCount > 0"
              :value="totalFraudCount"
              class="gt-confirmation-entity-verify__fraud-badge"
            />
          </template>
          <EntityVerifyFraudPanel
            :row-flags="screeningResult.rowFlags"
            :cross-flags="screeningResult.crossFlags"
            :rows="rows"
          />
          <el-button size="small" type="warning" @click="handleRunScreening">
            一键筛查
          </el-button>
        </el-collapse-item>
      </el-collapse>

      <!-- View switch -->
      <div class="gt-confirmation-entity-verify__view-switch">
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button value="list">列表视图</el-radio-button>
          <el-radio-button value="grid">网格视图</el-radio-button>
        </el-radio-group>
      </div>

      <!-- List view: Master + Detail -->
      <div v-if="viewMode === 'list'" class="gt-confirmation-entity-verify__list-view">
        <div class="gt-confirmation-entity-verify__master">
          <EntityVerifyMaster
            :rows="rows"
            :readonly="readonly"
            :selected-ids="selectedIds"
            @add="handleAdd"
            @delete="handleDelete"
            @save="handleSave"
            @import="handleImport"
            @export="handleExport"
            @row-click="handleRowClick"
            @update:selected-ids="selectedIds = $event"
          />
        </div>
        <div class="gt-confirmation-entity-verify__detail">
          <EntityVerifyDetail
            :row="currentRow"
            :readonly="readonly"
            :dict-data="dictData"
            @update="handleFieldUpdate"
          />
        </div>
      </div>

      <!-- Grid view: FullGrid -->
      <div v-else class="gt-confirmation-entity-verify__grid-view">
        <EntityVerifyMaster
          :rows="rows"
          :readonly="readonly"
          :selected-ids="selectedIds"
          @add="handleAdd"
          @delete="handleDelete"
          @save="handleSave"
          @import="handleImport"
          @export="handleExport"
          @row-click="handleRowClick"
          @update:selected-ids="selectedIds = $event"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import type { EntityVerifyRow } from './entityVerifyTypes'
import { useEntityVerifyData } from './composables/useEntityVerifyData'
import { useFraudFlagDetect, type CrossRowFlag } from './composables/useFraudFlagDetect'
import { useViewMode } from './composables/useViewMode'
import EntityVerifyDashboard from './EntityVerifyDashboard.vue'
import EntityVerifyFraudPanel from './EntityVerifyFraudPanel.vue'
import EntityVerifyMaster from './EntityVerifyMaster.vue'
import EntityVerifyDetail from './EntityVerifyDetail.vue'

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
  return data && data._format !== 'entity-verify-v1'
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
} = useEntityVerifyData({
  htmlData: () => props.htmlData,
  readonly: readonly.value,
})

// ─── Fraud detection ─────────────────────────────────────────────────────────

const { runScreening, deriveRowStatus } = useFraudFlagDetect(rows)

const screeningResult = reactive<{
  rowFlags: Map<string, string[]>
  crossFlags: CrossRowFlag[]
}>({
  rowFlags: new Map(),
  crossFlags: [],
})

const totalFraudCount = computed(() => {
  let count = 0
  for (const flags of screeningResult.rowFlags.values()) {
    count += flags.length
  }
  count += screeningResult.crossFlags.length
  return count
})

function handleRunScreening() {
  const result = runScreening()
  screeningResult.rowFlags = result.rowFlags
  screeningResult.crossFlags = result.crossFlags

  // Update row statuses based on screening
  const crossAffectedIds = new Set(result.crossFlags.flatMap((f) => f.affectedRowIds))
  for (const row of rows.value) {
    const flagCount = result.rowFlags.get(row._row_id!)?.length ?? 0
    const hasCross = crossAffectedIds.has(row._row_id!)
    row.row_status = deriveRowStatus(flagCount, hasCross)
    row.fraud_flags = result.rowFlags.get(row._row_id!) ?? []
  }
}

// ─── View mode ───────────────────────────────────────────────────────────────

const { viewMode } = useViewMode('list')

// ─── UI state ────────────────────────────────────────────────────────────────

const selectedIds = ref<string[]>([])
const currentRow = ref<EntityVerifyRow | null>(null)
const activePanels = ref<string[]>([])

// Dict data stub — in real usage loaded from project dict config
const dictData: Record<string, any[]> = {
  confirmation_account_type: [
    '应收账款', '合同负债', '其他应收款', '预付账款',
    '应付账款', '其他应付款', '短期借款', '长期借款',
    '银行存款', '定期存款', '理财产品', '其他货币资金', '其他',
  ],
}

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
  const payload = buildPayload()
  emit('save', payload)
}

function handleImport() {
  // Stub: open import dialog
  console.info('[EntityVerify] Import triggered')
}

function handleExport() {
  // Stub: export template
  console.info('[EntityVerify] Export template triggered')
}

function handleRowClick(row: EntityVerifyRow) {
  currentRow.value = row
}

function handleFieldUpdate(field: string, value: any) {
  if (!currentRow.value?._row_id) return
  updateField(currentRow.value._row_id, field, value)
}
</script>

<style scoped>
.gt-confirmation-entity-verify {
  padding: 12px;
}

.gt-confirmation-entity-verify__legacy-notice {
  margin-bottom: 16px;
}

.gt-confirmation-entity-verify__panels {
  margin-bottom: 12px;
}

.gt-confirmation-entity-verify__fraud-badge {
  margin-left: 8px;
}

.gt-confirmation-entity-verify__view-switch {
  margin-bottom: 12px;
}

.gt-confirmation-entity-verify__list-view {
  display: grid;
  grid-template-columns: 1fr 400px;
  gap: 12px;
}

.gt-confirmation-entity-verify__grid-view {
  width: 100%;
}

@media (max-width: 1200px) {
  .gt-confirmation-entity-verify__list-view {
    grid-template-columns: 1fr;
  }
}
</style>
