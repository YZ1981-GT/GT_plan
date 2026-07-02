<script setup lang="ts">
/**
 * D1TabDetailCategory.vue — 原值明细按类别D1-2 HTML渲染
 *
 * Spec: .kiro/specs/d1-adjudication-table/
 * Task: 9.1
 *
 * 渲染 el-table：票据种类|期初未审|期初AJE|期初RJE|期初审定|本期增加|本期减少|期末未审|期末AJE|期末RJE|期末审定
 * 预设银行承兑/商业承兑固定行（不可删除）+ 动态行增删 + 小计行自动SUM
 */
import { ref, computed, inject, toRef, onMounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useD1DetailCategory, type CategoryRow } from '../composables/useD1DetailCategory'
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

const ooSheetName = computed(() => props.sheetName || '原值明细按类别D1-2')

onMounted(async () => {
  try {
    const health = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    ooHealthy.value = health.data?.data?.healthy ?? health.data?.healthy ?? false
  } catch { ooHealthy.value = false }
})

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  rows,
  subtotalRow,
  addRow,
  removeRow,
  updateCell,
} = useD1DetailCategory({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: async (items) => {
    try {
      await http.post(`/api/workpapers/${props.wpId}/checklist-responses/batch`, { items })
    } catch { ElMessage.warning('保存失败，请重试') }
  },
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  if (val < 0) return `<span class="negative-amount">(${displayPrefs.fmtAmount(Math.abs(val))})</span>`
  return displayPrefs.fmtAmount(val)
}

// ─── Table Helpers ───────────────────────────────────────────────────────────

function getTableData(): CategoryRow[] {
  return [...rows.value, subtotalRow.value]
}

function getRowClass({ row }: { row: CategoryRow }): string {
  if (row.rowId === 'subtotal') return 'is-summary'
  return ''
}

function isComputedField(field: string): boolean {
  return ['priorAudited', 'currentUnadjusted', 'currentAudited'].includes(field)
}

function isCellEditable(row: CategoryRow, field: string): boolean {
  if (props.isReadonly) return false
  if (row.rowId === 'subtotal') return false
  if (isComputedField(field)) return false
  return true
}

// ─── Import/Export ───────────────────────────────────────────────────────────

const SHEET_CODE = 'D1-2'

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
  <div class="d1-tab-detail-category">
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
      <el-button
        type="primary"
        size="small"
        :disabled="isReadonly"
        @click="addRow()"
      >
        + 添加种类
      </el-button>
    </div>

    <!-- Main Table -->
    <el-table
      :data="getTableData()"
      border
      size="small"
      :row-class-name="getRowClass"
    >
      <!-- 票据种类 -->
      <el-table-column label="票据种类" width="160" fixed>
        <template #default="{ row }">
          <template v-if="row.rowId === 'subtotal'">
            <span style="font-weight: 600">{{ row.category }}</span>
          </template>
          <template v-else-if="row.isFixed">
            <span>{{ row.category }}</span>
          </template>
          <template v-else>
            <div class="category-cell">
              <el-input
                :model-value="row.category"
                size="small"
                placeholder="输入种类名称"
                :disabled="isReadonly"
                @change="(v: string) => updateCell(row.rowId, 'category', v)"
              />
              <el-button
                v-if="!isReadonly"
                type="danger"
                size="small"
                text
                class="delete-btn"
                @click="removeRow(row.rowId)"
              >
                ✕
              </el-button>
            </div>
          </template>
        </template>
      </el-table-column>

      <!-- 期初未审 -->
      <el-table-column label="期初未审" width="110" align="right">
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
      <el-table-column label="期初AJE" width="100" align="right">
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
      <el-table-column label="期初RJE" width="100" align="right">
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
      <el-table-column label="期初审定" width="110" align="right">
        <template #default="{ row }">
          <span style="font-weight: 600" v-html="fmtAmount(row.priorAudited)" />
        </template>
      </el-table-column>

      <!-- 本期增加 -->
      <el-table-column label="本期增加" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="isCellEditable(row, 'currentIncrease')"
            :model-value="row.currentIncrease"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateCell(row.rowId, 'currentIncrease', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.currentIncrease)" />
        </template>
      </el-table-column>

      <!-- 本期减少 -->
      <el-table-column label="本期减少" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="isCellEditable(row, 'currentDecrease')"
            :model-value="row.currentDecrease"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateCell(row.rowId, 'currentDecrease', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.currentDecrease)" />
        </template>
      </el-table-column>

      <!-- 期末未审 (computed) -->
      <el-table-column label="期末未审" width="110" align="right">
        <template #default="{ row }">
          <span v-html="fmtAmount(row.currentUnadjusted)" />
        </template>
      </el-table-column>

      <!-- 期末AJE -->
      <el-table-column label="期末AJE" width="100" align="right">
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
      <el-table-column label="期末RJE" width="100" align="right">
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
      <el-table-column label="期末审定" width="110" align="right">
        <template #default="{ row }">
          <span style="font-weight: 600" v-html="fmtAmount(row.currentAudited)" />
        </template>
      </el-table-column>
    </el-table>
    </template>
  </div>
</template>

<style scoped>
.d1-tab-detail-category {
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

/* 小计行样式 */
:deep(.el-table .is-summary td) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}

/* 负数红色括号 */
:deep(.negative-amount) {
  color: #f56c6c;
}

/* 种类列带删除按钮 */
.category-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

.category-cell .el-input {
  flex: 1;
}

.delete-btn {
  padding: 2px 4px;
  min-height: auto;
}
</style>
