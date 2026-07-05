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
import { computed, inject, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useD1DetailCategory, type CategoryRow } from '../composables/useD1DetailCategory'
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

const rowCount = computed(() => rows.value.length)
const { useLargeTable, tableMaxHeight } = useD1VirtualBrowse(rowCount)

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

const wpIdRef = toRef(props, 'wpId')
const { onExportTemplate, onExportData, onImportFile } = useD1TabImportExport(wpIdRef, 'D1-2')
</script>

<template>
  <div class="d1-tab-detail-category">
    <div class="tab-header">
      <h4>原值明细按类别 D1-2</h4>
      <GtReviewTrigger section-id="D1-detail-cat-header" />
    </div>
    <!-- Toolbar -->
    <div class="table-toolbar">
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
        + 添加种类
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
      :row-class-name="getRowClass"
      :max-height="tableMaxHeight"
    >
      <!-- 票据种类 -->
      <el-table-column label="票据种类" width="160" fixed>
        <template #default="{ row }">
          <template v-if="row.rowId === 'subtotal'">
            <span style="font-weight: 600">{{ row.category }}</span>
          </template>
          <template v-else-if="row.isFixed">
            <span>{{ row.category }}</span>
            <GtReviewDot row-prefix="D1-cat" :row-key="row.rowId" />
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
              <GtReviewDot row-prefix="D1-cat" :row-key="row.rowId" />
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
  </div>
</template>

<style scoped>
.d1-tab-detail-category {
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
