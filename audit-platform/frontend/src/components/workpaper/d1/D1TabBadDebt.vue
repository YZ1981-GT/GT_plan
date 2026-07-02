<script setup lang="ts">
/**
 * D1TabBadDebt.vue — 坏账准备D1-4 HTML渲染
 *
 * Spec: .kiro/specs/d1-adjudication-table/
 * Task: 11.1
 *
 * 渲染 el-table：项目|期初未审|期初AJE|期初RJE|期初审定|本期计提|本期收回|本期转回|本期核销|本期其他|期末未审|期末AJE|期末RJE|期末审定
 * 固定行结构：按单项计提（可展开子行）+ 按组合计提（可展开子行）+ 小计
 * ECL差异警告（小计行旁黄色 el-alert）
 */
import { ref, inject, toRef, computed, onMounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useD1BadDebt, type BadDebtRow } from '../composables/useD1BadDebt'
import type { ChecklistResponse } from '../composables/useD1FormData'
import GtOnlyOfficeSheet from '../GtOnlyOfficeSheet.vue'
import http from '@/utils/http'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
  sheetName?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// ─── Dual Mode (HTML ↔ OnlyOffice) ──────────────────────────────────────────

const editorMode = ref<'html' | 'oo'>('html')
const ooHealthy = ref(true)
const modeOptions = computed(() => [
  { label: '结构化视图', value: 'html' },
  { label: '在线编辑', value: 'oo', disabled: !ooHealthy.value },
])

const ooSheetName = computed(() => props.sheetName || '坏账准备D1-4')

onMounted(async () => {
  try {
    const health = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    ooHealthy.value = health.data?.data?.healthy ?? health.data?.healthy ?? false
  } catch { ooHealthy.value = false }
})

// ─── ECL Test Total (from allResponses or default 0) ─────────────────────────

const eclTestTotal = ref(0)

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  individualRows,
  portfolioRows,
  subtotalRow,
  eclWarning,
  addSubRow,
  removeSubRow,
  updateCell,
} = useD1BadDebt({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: async (items) => {
    try {
      await http.post(`/api/workpapers/${props.wpId}/checklist-responses/batch`, { items })
    } catch { ElMessage.warning('保存失败，请重试') }
  },
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  eclTestTotal,
})

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  if (val < 0) return `<span class="negative-amount">(${displayPrefs.fmtAmount(Math.abs(val))})</span>`
  return displayPrefs.fmtAmount(val)
}

// ─── Table Data ──────────────────────────────────────────────────────────────

const tableData = computed<BadDebtRow[]>(() => {
  return [
    ...individualRows.value,
    ...portfolioRows.value,
    subtotalRow.value,
  ]
})

// ─── Table Helpers ───────────────────────────────────────────────────────────

function getRowClass({ row }: { row: BadDebtRow }): string {
  if (row.rowId === 'subtotal') return 'is-summary'
  if (!row.isSubRow) return 'is-parent-row'
  return 'is-sub-row'
}

function isComputedField(field: string): boolean {
  return ['priorAudited', 'currentUnadjusted', 'currentAudited'].includes(field)
}

function isCellEditable(row: BadDebtRow, field: string): boolean {
  if (props.isReadonly) return false
  if (row.rowId === 'subtotal') return false
  if (isComputedField(field)) return false
  return true
}

function isParentRow(row: BadDebtRow): boolean {
  return !row.isSubRow && row.rowId !== 'subtotal'
}

// ─── Import/Export ───────────────────────────────────────────────────────────

const SHEET_CODE = 'D1-4'

async function exportTemplate() {
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d1/export-template`,
      null,
      { params: { sheet: SHEET_CODE }, responseType: 'blob' }
    )
    const blob = new Blob([res.data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${SHEET_CODE}_模板.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error('导出模板失败') }
}

async function exportData() {
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d1/export-data`,
      null,
      { params: { sheet: SHEET_CODE }, responseType: 'blob' }
    )
    const blob = new Blob([res.data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${SHEET_CODE}_数据.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error('导出数据失败') }
}

async function handleImportFile(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d1/import-data`,
      formData,
      { params: { sheet: SHEET_CODE }, headers: { 'Content-Type': 'multipart/form-data' } }
    )
    const data = res.data?.data ?? res.data
    ElMessage.success(`成功导入${data.imported_count}行数据`)
    if (data.warning) ElMessage.warning(data.warning)
  } catch (e: any) {
    const errData = e?.response?.data?.data ?? e?.response?.data
    if (e?.response?.status === 400 && errData?.invalid_columns?.length) {
      ElMessage.error(`列名不匹配: ${errData.invalid_columns.join(', ')}`)
    } else {
      ElMessage.error('导入失败')
    }
  }
}
</script>

<template>
  <div class="d1-tab-bad-debt">
    <!-- Mode Switcher -->
    <div class="mode-switcher">
      <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
      <el-tooltip v-if="!ooHealthy" content="OnlyOffice服务不可用" placement="top">
        <span class="oo-disabled-hint">⚠️</span>
      </el-tooltip>
    </div>

    <!-- OnlyOffice mode -->
    <template v-if="editorMode === 'oo'">
      <GtOnlyOfficeSheet :wp-id="wpId" :sheet-name="ooSheetName" :project-id="projectId" />
    </template>

    <!-- HTML mode -->
    <template v-if="editorMode === 'html'">
    <!-- Toolbar -->
    <div class="table-toolbar">
      <el-button-group size="small">
        <el-button @click="exportTemplate">导出模板</el-button>
        <el-button @click="exportData">导出数据</el-button>
        <el-upload
          :show-file-list="false"
          accept=".xlsx"
          :auto-upload="false"
          :on-change="(f: any) => handleImportFile(f.raw)"
          style="display:inline-block"
        >
          <el-button size="small">导入数据</el-button>
        </el-upload>
      </el-button-group>
      <el-button-group>
        <el-button
          size="small"
          :disabled="isReadonly"
          @click="addSubRow('individual')"
        >
          + 按单项子行
        </el-button>
        <el-button
          size="small"
          :disabled="isReadonly"
          @click="addSubRow('portfolio')"
        >
          + 按组合子行
        </el-button>
      </el-button-group>
    </div>

    <!-- ECL Warning -->
    <el-alert
      v-if="eclWarning"
      :title="eclWarning"
      type="warning"
      show-icon
      :closable="false"
      class="ecl-warning"
    />

    <!-- Main Table -->
    <el-table
      :data="tableData"
      border
      size="small"
      :row-class-name="getRowClass"
    >
      <!-- 项目 -->
      <el-table-column label="项目" width="160" fixed>
        <template #default="{ row }">
          <template v-if="row.rowId === 'subtotal'">
            <span style="font-weight: 600">小计</span>
          </template>
          <template v-else-if="isParentRow(row)">
            <span style="font-weight: 600">{{ row.label }}</span>
          </template>
          <template v-else>
            <div class="sub-row-cell">
              <span class="sub-row-indent">└</span>
              <el-input
                :model-value="row.label"
                size="small"
                placeholder="子项名称"
                :disabled="isReadonly"
                @change="(v: string) => updateCell(row.rowId, 'label', v as any)"
              />
              <el-button
                v-if="!isReadonly"
                type="danger"
                size="small"
                text
                class="delete-btn"
                @click="removeSubRow(row.rowId)"
              >
                ✕
              </el-button>
            </div>
          </template>
        </template>
      </el-table-column>

      <!-- 期初未审 -->
      <el-table-column label="期初未审" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="isCellEditable(row, 'priorUnadjusted')"
            :model-value="row.priorUnadjusted"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateCell(row.rowId, 'priorUnadjusted', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.priorUnadjusted)" />
        </template>
      </el-table-column>

      <!-- 期初AJE -->
      <el-table-column label="期初AJE" width="95" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="isCellEditable(row, 'priorAje')"
            :model-value="row.priorAje"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateCell(row.rowId, 'priorAje', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.priorAje)" />
        </template>
      </el-table-column>

      <!-- 期初RJE -->
      <el-table-column label="期初RJE" width="95" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="isCellEditable(row, 'priorRje')"
            :model-value="row.priorRje"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateCell(row.rowId, 'priorRje', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.priorRje)" />
        </template>
      </el-table-column>

      <!-- 期初审定 (computed) -->
      <el-table-column label="期初审定" width="100" align="right">
        <template #default="{ row }">
          <span style="font-weight: 600" v-html="fmtAmount(row.priorAudited)" />
        </template>
      </el-table-column>

      <!-- 本期计提 -->
      <el-table-column label="本期计提" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="isCellEditable(row, 'currentProvision')"
            :model-value="row.currentProvision"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateCell(row.rowId, 'currentProvision', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.currentProvision)" />
        </template>
      </el-table-column>

      <!-- 本期收回 -->
      <el-table-column label="本期收回" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="isCellEditable(row, 'currentRecovery')"
            :model-value="row.currentRecovery"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateCell(row.rowId, 'currentRecovery', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.currentRecovery)" />
        </template>
      </el-table-column>

      <!-- 本期转回 -->
      <el-table-column label="本期转回" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="isCellEditable(row, 'currentReversal')"
            :model-value="row.currentReversal"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateCell(row.rowId, 'currentReversal', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.currentReversal)" />
        </template>
      </el-table-column>

      <!-- 本期核销 -->
      <el-table-column label="本期核销" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="isCellEditable(row, 'currentWriteOff')"
            :model-value="row.currentWriteOff"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateCell(row.rowId, 'currentWriteOff', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.currentWriteOff)" />
        </template>
      </el-table-column>

      <!-- 本期其他 -->
      <el-table-column label="本期其他" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="isCellEditable(row, 'currentOther')"
            :model-value="row.currentOther"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateCell(row.rowId, 'currentOther', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.currentOther)" />
        </template>
      </el-table-column>

      <!-- 期末未审 (computed) -->
      <el-table-column label="期末未审" width="100" align="right">
        <template #default="{ row }">
          <span v-html="fmtAmount(row.currentUnadjusted)" />
        </template>
      </el-table-column>

      <!-- 期末AJE -->
      <el-table-column label="期末AJE" width="95" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="isCellEditable(row, 'currentAje')"
            :model-value="row.currentAje"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateCell(row.rowId, 'currentAje', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.currentAje)" />
        </template>
      </el-table-column>

      <!-- 期末RJE -->
      <el-table-column label="期末RJE" width="95" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="isCellEditable(row, 'currentRje')"
            :model-value="row.currentRje"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateCell(row.rowId, 'currentRje', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.currentRje)" />
        </template>
      </el-table-column>

      <!-- 期末审定 (computed) -->
      <el-table-column label="期末审定" width="100" align="right">
        <template #default="{ row }">
          <span style="font-weight: 600" v-html="fmtAmount(row.currentAudited)" />
        </template>
      </el-table-column>
    </el-table>
    </template>
  </div>
</template>

<style scoped>
.d1-tab-bad-debt {
  padding: 12px;
}

.mode-switcher {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.oo-disabled-hint {
  cursor: help;
  font-size: 14px;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
}

.ecl-warning {
  margin-bottom: 12px;
}

/* 小计行样式 */
:deep(.el-table .is-summary td) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}

/* 父行样式（按单项/按组合标题行） */
:deep(.el-table .is-parent-row td) {
  background-color: #fafbfc !important;
}

/* 子行缩进 */
.is-sub-row .sub-row-cell {
  padding-left: 8px;
}

/* 负数红色括号 */
:deep(.negative-amount) {
  color: #f56c6c;
}

/* 子行单元格布局 */
.sub-row-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

.sub-row-indent {
  color: #c0c4cc;
  font-size: 12px;
  flex-shrink: 0;
}

.sub-row-cell .el-input {
  flex: 1;
}

.delete-btn {
  padding: 2px 4px;
  min-height: auto;
}
</style>
