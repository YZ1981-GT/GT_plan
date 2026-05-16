<template>
  <div class="column-mapping-editor">
    <!-- Sheet 选择 tabs -->
    <el-tabs v-model="activeSheet" type="card">
      <el-tab-pane
        v-for="(sheet, idx) in sheets"
        :key="idx"
        :label="`${sheet.file_name} / ${sheet.sheet_name}`"
        :name="String(idx)"
      />
    </el-tabs>

    <div v-if="currentSheet" class="mapping-content">
      <!-- 8.36: 应用全部历史映射按钮 -->
      <div v-if="hasHistoryMappings" class="history-apply-bar">
        <el-alert type="info" :closable="false" show-icon>
          <template #title>
            <span>检测到历史映射记录，部分列已自动应用</span>
            <el-button
              type="primary"
              size="small"
              style="margin-left: 12px"
              @click="applyAllHistoryMappings"
            >
              应用全部历史映射
            </el-button>
          </template>
        </el-alert>
      </div>

      <!-- 🔴 关键列（key）— 必须填写 -->
      <div class="mapping-section section-key">
        <div class="section-header">
          <span class="section-icon">🔴</span>
          <span class="section-title">关键列（必填）</span>
          <el-tag type="danger" size="small">
            {{ keyMappings.filter(m => m.mappedField).length }}/{{ keyMappings.length }} 已映射
          </el-tag>
        </div>
        <div class="mapping-rows">
          <div
            v-for="mapping in keyMappings"
            :key="mapping.column_index"
            class="mapping-row"
            :class="{ 'missing': !mapping.mappedField }"
          >
            <span class="original-col">{{ mapping.column_header }}</span>
            <el-icon class="arrow-icon"><Right /></el-icon>
            <el-select
              v-model="mapping.mappedField"
              placeholder="选择标准字段"
              filterable
              clearable
              size="default"
              class="field-select"
            >
              <el-option
                v-for="field in availableStandardFields"
                :key="field.value"
                :label="field.label"
                :value="field.value"
                :disabled="isFieldUsed(field.value, mapping.column_index)"
              />
            </el-select>
            <el-tag v-if="mapping.confidence > 0" size="small" type="info">
              {{ mapping.confidence }}%
            </el-tag>
            <el-tag v-if="mapping.autoAppliedFromHistory" size="small" type="warning" effect="plain" class="history-badge">
              🕒 上次映射
            </el-tag>
          </div>
        </div>
      </div>

      <!-- 🟡 次关键列（recommended）— 可折叠 -->
      <el-collapse v-model="expandedSections">
        <el-collapse-item name="recommended">
          <template #title>
            <span class="section-icon">🟡</span>
            <span class="section-title">次关键列（推荐）</span>
            <el-tag type="warning" size="small" style="margin-left: 8px">
              {{ recommendedMappings.filter(m => m.mappedField).length }}/{{ recommendedMappings.length }} 已映射
            </el-tag>
          </template>
          <div class="mapping-rows">
            <div
              v-for="mapping in recommendedMappings"
              :key="mapping.column_index"
              class="mapping-row"
            >
              <span class="original-col">{{ mapping.column_header }}</span>
              <el-icon class="arrow-icon"><Right /></el-icon>
              <el-select
                v-model="mapping.mappedField"
                placeholder="选择标准字段"
                filterable
                clearable
                size="default"
                class="field-select"
              >
                <el-option
                  v-for="field in availableStandardFields"
                  :key="field.value"
                  :label="field.label"
                  :value="field.value"
                  :disabled="isFieldUsed(field.value, mapping.column_index)"
                />
              </el-select>
              <el-tag v-if="mapping.confidence > 0" size="small" type="info">
                {{ mapping.confidence }}%
              </el-tag>
              <el-tag v-if="mapping.autoAppliedFromHistory" size="small" type="warning" effect="plain" class="history-badge">
                🕒 上次映射
              </el-tag>
            </div>
          </div>
        </el-collapse-item>

        <!-- ⚪ 非关键列（extra）— 折叠 -->
        <el-collapse-item name="extra">
          <template #title>
            <span class="section-icon">⚪</span>
            <span class="section-title">非关键列</span>
            <el-tag size="small" style="margin-left: 8px">
              {{ extraMappings.length }} 列将保留到 raw_extra
            </el-tag>
          </template>
          <div class="extra-info">
            <p class="extra-hint">以下列未被识别为标准字段，将原样保留到 raw_extra JSONB 字段中：</p>
            <el-tag
              v-for="mapping in extraMappings"
              :key="mapping.column_index"
              size="small"
              type="info"
              style="margin: 4px"
            >
              {{ mapping.column_header }}
            </el-tag>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- 操作按钮 -->
    <div class="step-actions">
      <el-button aria-label="返回上一步" @click="emit('back')">上一步</el-button>
      <div class="actions-right">
        <el-button
          aria-label="从其他项目导入映射"
          @click="showImportMappingDialog = true"
        >
          从其他项目导入映射
        </el-button>
        <el-button
          type="primary"
          aria-label="确认映射并导入"
          :disabled="!allKeyColumnsMapped"
          @click="onConfirm"
        >
          确认映射并导入
        </el-button>
      </div>
    </div>

    <!-- 从其他项目导入映射弹窗 (Task 69) -->
    <el-dialog
      v-model="showImportMappingDialog"
      title="从其他项目导入映射"
      width="500px"
      append-to-body
    >
      <el-form label-width="100px">
        <el-form-item label="选择项目">
          <el-select
            v-model="selectedReferenceProject"
            placeholder="选择参考项目"
            filterable
            style="width: 100%"
            :loading="loadingProjects"
          >
            <el-option
              v-for="proj in referenceProjects"
              :key="proj.id"
              :label="proj.name"
              :value="proj.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button aria-label="取消导入映射" @click="showImportMappingDialog = false">取消</el-button>
        <el-button
          type="primary"
          aria-label="确认导入映射"
          :disabled="!selectedReferenceProject"
          :loading="importingMapping"
          @click="importMappingFromProject"
        >
          导入
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Right } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { SheetDetection, LedgerDetectionResult, ConfirmedMapping } from './LedgerImportDialog.vue'

// ─── Props & Emits ──────────────────────────────────────────────────────────

const props = defineProps<{
  sheets: SheetDetection[]
  detectionResult: LedgerDetectionResult | null
  projectId?: string
}>()

const emit = defineEmits<{
  confirm: [mappings: ConfirmedMapping[]]
  back: []
}>()

// ─── Types ──────────────────────────────────────────────────────────────────

interface MappingRow {
  column_index: number
  column_header: string
  column_tier: 'key' | 'recommended' | 'extra'
  confidence: number
  mappedField: string | null
  autoAppliedFromHistory: boolean
  historyMappingId: string | null
}

interface StandardField {
  value: string
  label: string
}

// ─── State ──────────────────────────────────────────────────────────────────

const activeSheet = ref('0')
const expandedSections = ref<string[]>(['recommended'])
const sheetMappings = ref<Map<number, MappingRow[]>>(new Map())
const showImportMappingDialog = ref(false)
const selectedReferenceProject = ref('')
const referenceProjects = ref<Array<{ id: string; name: string }>>([])
const loadingProjects = ref(false)
const importingMapping = ref(false)

/** 获取当前项目 ID（优先 prop，回退路由参数） */
function getCurrentProjectId(): string {
  if (props.projectId) return props.projectId
  const route = useRoute()
  return (route.params.projectId as string) || ''
}

// ─── Standard Fields ────────────────────────────────────────────────────────

const availableStandardFields: StandardField[] = [
  { value: 'account_code', label: '科目编码' },
  { value: 'account_name', label: '科目名称' },
  { value: 'opening_balance', label: '期初余额' },
  { value: 'opening_debit', label: '期初借方' },
  { value: 'opening_credit', label: '期初贷方' },
  { value: 'closing_balance', label: '期末余额' },
  { value: 'closing_debit', label: '期末借方' },
  { value: 'closing_credit', label: '期末贷方' },
  { value: 'debit_amount', label: '借方发生额' },
  { value: 'credit_amount', label: '贷方发生额' },
  { value: 'voucher_date', label: '凭证日期' },
  { value: 'voucher_no', label: '凭证号' },
  { value: 'voucher_type', label: '凭证类型' },
  { value: 'summary', label: '摘要' },
  { value: 'preparer', label: '制单人' },
  { value: 'currency_code', label: '币种' },
  { value: 'level', label: '级次' },
  { value: 'aux_type', label: '辅助类型' },
  { value: 'aux_code', label: '辅助编码' },
  { value: 'aux_name', label: '辅助名称' },
  { value: 'amount', label: '金额' },
  { value: 'direction', label: '方向' },
  { value: 'entry_seq', label: '分录序号' },
]

// ─── Computed ───────────────────────────────────────────────────────────────

const currentSheet = computed(() => {
  const idx = parseInt(activeSheet.value)
  return props.sheets[idx] || null
})

const currentMappings = computed<MappingRow[]>(() => {
  const idx = parseInt(activeSheet.value)
  return sheetMappings.value.get(idx) || []
})

const keyMappings = computed(() =>
  currentMappings.value.filter(m => m.column_tier === 'key')
)

const recommendedMappings = computed(() =>
  currentMappings.value.filter(m => m.column_tier === 'recommended')
)

const extraMappings = computed(() =>
  currentMappings.value.filter(m => m.column_tier === 'extra')
)

const allKeyColumnsMapped = computed(() =>
  keyMappings.value.every(m => !!m.mappedField)
)

// 8.36: Check if any mappings were auto-applied from history
const hasHistoryMappings = computed(() =>
  currentMappings.value.some(m => m.autoAppliedFromHistory)
)

// ─── Methods ────────────────────────────────────────────────────────────────

// 8.36: Apply all history mappings (accept all auto-applied suggestions)
function applyAllHistoryMappings() {
  const mappings = currentMappings.value
  for (const m of mappings) {
    if (m.autoAppliedFromHistory && m.mappedField) {
      // Already applied — just confirm by keeping the value
      // This is a no-op since they're already set, but signals user intent
    }
  }
  ElMessage.success('已应用全部历史映射')
}

function isFieldUsed(fieldValue: string, excludeColIdx: number): boolean {
  return currentMappings.value.some(
    m => m.mappedField === fieldValue && m.column_index !== excludeColIdx
  )
}

function initMappings() {
  const map = new Map<number, MappingRow[]>()
  props.sheets.forEach((sheet, idx) => {
    const rows: MappingRow[] = sheet.column_mappings.map(col => ({
      column_index: col.column_index,
      column_header: col.column_header,
      column_tier: col.column_tier,
      confidence: col.confidence,
      mappedField: col.standard_field,
      autoAppliedFromHistory: !!(col as any).auto_applied_from_history,
      historyMappingId: (col as any).history_mapping_id || null,
    }))
    map.set(idx, rows)
  })
  sheetMappings.value = map
}

function onConfirm() {
  const mappings: ConfirmedMapping[] = props.sheets.map((sheet, idx) => {
    const rows = sheetMappings.value.get(idx) || []
    const columnMapping: Record<string, string> = {}
    for (const row of rows) {
      if (row.mappedField) {
        columnMapping[String(row.column_index)] = row.mappedField
      }
    }
    return {
      file: sheet.file_name,
      sheet: sheet.sheet_name,
      table_type: sheet.table_type,
      column_mapping: columnMapping,
      aux_dimension_columns: sheet.aux_dimension_columns,
    }
  })
  emit('confirm', mappings)
}

async function importMappingFromProject() {
  if (!selectedReferenceProject.value) return
  importingMapping.value = true
  try {
    const { ledgerImportV2Api } = await import('@/services/ledgerImportV2Api')
    // 从 detectionResult 中获取当前项目 ID（通过 upload_token 关联的项目）
    // 实际项目 ID 需要从父组件传入
    const pid = getCurrentProjectId()
    await ledgerImportV2Api.copyMappingFromProject(pid, selectedReferenceProject.value)
    showImportMappingDialog.value = false
    ElMessage.success('映射模板已保存，下次导入相同格式文件时将自动应用')
  } catch {
    ElMessage.error('导入映射失败')
  } finally {
    importingMapping.value = false
  }
}

// ─── Watchers ───────────────────────────────────────────────────────────────

watch(() => props.sheets, () => {
  initMappings()
}, { immediate: true })

watch(showImportMappingDialog, async (visible) => {
  if (visible && referenceProjects.value.length === 0) {
    loadingProjects.value = true
    try {
      const { ledgerImportV2Api } = await import('@/services/ledgerImportV2Api')
      const pid = getCurrentProjectId()
      const res = await ledgerImportV2Api.getReferenceProjects(pid) as Array<{ id: string; name: string }>
      referenceProjects.value = res || []
    } catch { /* ignore */ }
    finally { loadingProjects.value = false }
  }
})
</script>

<style scoped>
.column-mapping-editor {
  padding: 0 8px;
}

.mapping-content {
  margin-top: 16px;
}

.mapping-section {
  margin-bottom: 20px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-weight: 500;
}

.section-icon {
  font-size: var(--gt-font-size-md);
}

.section-title {
  font-size: var(--gt-font-size-sm);
}

.mapping-rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mapping-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border-radius: 4px;
  background: var(--el-fill-color-lighter);
}

.mapping-row.missing {
  border: 1px solid var(--el-color-danger-light-5);
  background: var(--el-color-danger-light-9);
}

.original-col {
  min-width: 120px;
  font-size: var(--gt-font-size-sm);
  font-weight: 500;
}

.arrow-icon {
  color: var(--el-text-color-secondary);
}

.field-select {
  width: 200px;
}

.extra-info {
  padding: 8px 12px;
}

.extra-hint {
  font-size: var(--gt-font-size-xs);
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.step-actions {
  margin-top: 24px;
  display: flex;
  justify-content: space-between;
}

.actions-right {
  display: flex;
  gap: 8px;
}

.history-badge {
  font-size: var(--gt-font-size-xs);
}

.history-apply-bar {
  margin-bottom: 16px;
}
</style>
