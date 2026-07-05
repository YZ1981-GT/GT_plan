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
import { ref, computed, inject, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useD1DetailCustomer, type CustomerRow } from '../composables/useD1DetailCustomer'
import type { ChecklistResponse } from '../composables/useD1FormData'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { useD1TabImportExport } from '../composables/useD1TabImportExport'
import { useD1VirtualBrowse } from '../composables/useD1VirtualBrowse'
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

const rowCount = computed(() => filteredRows.value.length)
const { useLargeTable, tableMaxHeight } = useD1VirtualBrowse(rowCount)

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

const wpIdRef = toRef(props, 'wpId')
const { onExportTemplate, onExportData, onImportFile } = useD1TabImportExport(wpIdRef, 'D1-3')
</script>

<template>
  <div class="d1-tab-detail-customer">
    <div class="tab-header">
      <h4>原值明细按客户 D1-3</h4>
      <GtReviewTrigger section-id="D1-detail-cust-header" />
    </div>
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
        <el-button @click="onExportTemplate">导出模板</el-button>
        <el-button @click="onExportData">导出数据</el-button>
        <el-upload
          :show-file-list="false"
          accept=".xlsx"
          :before-upload="onImportFile"
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
    <el-alert v-if="useLargeTable" type="info" :closable="false" show-icon class="large-table-hint">
      行数较多，已启用固定高度滚动浏览（{{ rowCount }} 行）
    </el-alert>
    <el-table
      :data="getTableData()"
      border
      size="small"
      :row-class-name="getRowClassName"
      style="width: 100%"
      :max-height="tableMaxHeight"
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
              <GtReviewDot row-prefix="D1-cust" :row-key="row.rowId" />
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
  </div>
</template>

<style scoped>
.d1-tab-detail-customer {
  padding: 12px;
}

.tab-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.tab-header h4 {
  margin: 0;
  font-size: 15px;
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
