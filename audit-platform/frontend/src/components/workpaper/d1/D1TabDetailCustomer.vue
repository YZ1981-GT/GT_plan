<script setup lang="ts">
/**
 * D1TabDetailCustomer.vue — 原值明细按客户D1-3 HTML渲染
 *
 * Spec: .kiro/specs/d1-adjudication-table/
 * Task: 10.1
 *
 * 渲染 el-table：客户名称|公司代码|关联关系|期初未审|期初AJE|期初RJE|期初审定|
 *   本期增加|本期减少|期末余额|重分类|期末未审|期末AJE|期末RJE|期末审定（14+列）
 * 关联方行橙色背景高亮 + 搜索框过滤 + 动态行增删 + 小计行
 */
import { ref, computed, inject, toRef, onMounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useD1DetailCustomer, type CustomerRow } from '../composables/useD1DetailCustomer'
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

const ooSheetName = computed(() => props.sheetName || '原值明细按客户D1-3')

onMounted(async () => {
  try {
    const health = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    ooHealthy.value = health.data?.data?.healthy ?? health.data?.healthy ?? false
  } catch { ooHealthy.value = false }
})

// ─── Related Parties (from project context or inject) ────────────────────────

const relatedParties = ref<string[]>([])

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  filteredRows,
  subtotalRow,
  searchQuery,
  addRow,
  removeRow,
  updateCell,
} = useD1DetailCustomer({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: async (items) => {
    try {
      await http.post(`/api/workpapers/${props.wpId}/checklist-responses/batch`, { items })
    } catch { ElMessage.warning('保存失败，请重试') }
  },
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  relatedParties,
})

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  if (val < 0) return `<span class="negative-amount">(${displayPrefs.fmtAmount(Math.abs(val))})</span>`
  return displayPrefs.fmtAmount(val)
}

// ─── Table Helpers ───────────────────────────────────────────────────────────

function getTableData(): CustomerRow[] {
  return [...filteredRows.value, subtotalRow.value]
}

function getRowClassName({ row }: { row: CustomerRow }): string {
  if (row.rowId === 'subtotal') return 'is-summary'
  if (row.relationType === '关联方') return 'related-party-row'
  return ''
}

function isComputedField(field: string): boolean {
  return ['priorAudited', 'currentUnadjusted', 'currentAudited'].includes(field)
}

function isCellEditable(row: CustomerRow, field: string): boolean {
  if (props.isReadonly) return false
  if (row.rowId === 'subtotal') return false
  if (isComputedField(field)) return false
  return true
}

// ─── Import/Export ───────────────────────────────────────────────────────────

const SHEET_CODE = 'D1-3'

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
  <div class="d1-tab-detail-customer">
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
    <!-- Toolbar: Search + Import/Export + Add -->
    <div class="table-toolbar">
      <el-input
        v-model="searchQuery"
        size="small"
        placeholder="搜索客户名称..."
        clearable
        class="search-input"
      >
        <template #prefix>
          <span>🔍</span>
        </template>
      </el-input>
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
        + 添加客户
      </el-button>
    </div>

    <!-- Main Table -->
    <el-table
      :data="getTableData()"
      border
      size="small"
      :row-class-name="getRowClassName"
      style="width: 100%"
    >
      <!-- 客户名称 (left-aligned) -->
      <el-table-column label="客户名称" width="160" fixed>
        <template #default="{ row }">
          <template v-if="row.rowId === 'subtotal'">
            <span style="font-weight: 600">{{ row.customerName }}</span>
          </template>
          <template v-else>
            <div class="customer-name-cell">
              <el-input
                :model-value="row.customerName"
                size="small"
                placeholder="客户名称"
                :disabled="isReadonly"
                @change="(v: string) => updateCell(row.rowId, 'customerName', v)"
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

      <!-- 公司代码 -->
      <el-table-column label="公司代码" width="100">
        <template #default="{ row }">
          <el-input
            v-if="isCellEditable(row, 'companyCode')"
            :model-value="row.companyCode"
            size="small"
            placeholder=""
            @change="(v: string) => updateCell(row.rowId, 'companyCode', v)"
          />
          <span v-else>{{ row.companyCode || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 关联关系 -->
      <el-table-column label="关联关系" width="100">
        <template #default="{ row }">
          <template v-if="row.rowId === 'subtotal'">
            <span>-</span>
          </template>
          <template v-else>
            <el-tag
              v-if="row.relationType === '关联方'"
              type="warning"
              size="small"
            >
              关联方
            </el-tag>
            <span v-else-if="row.relationType">{{ row.relationType }}</span>
            <span v-else>-</span>
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

      <!-- 期末余额 -->
      <el-table-column label="期末余额" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="isCellEditable(row, 'currentBalance')"
            :model-value="row.currentBalance"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateCell(row.rowId, 'currentBalance', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.currentBalance)" />
        </template>
      </el-table-column>

      <!-- 重分类 -->
      <el-table-column label="重分类" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="isCellEditable(row, 'reclassification')"
            :model-value="row.reclassification"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateCell(row.rowId, 'reclassification', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.reclassification)" />
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
.d1-tab-detail-customer {
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

.search-input {
  width: 240px;
}

/* 小计行样式 */
:deep(.el-table .is-summary td) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}

/* 关联方行橙色背景高亮 */
:deep(.el-table .related-party-row td) {
  background-color: #fdf6ec !important;
}

/* 负数红色括号 */
:deep(.negative-amount) {
  color: #f56c6c;
}

/* 客户名称列带删除按钮 */
.customer-name-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

.customer-name-cell .el-input {
  flex: 1;
}

.delete-btn {
  padding: 2px 4px;
  min-height: auto;
}
</style>
