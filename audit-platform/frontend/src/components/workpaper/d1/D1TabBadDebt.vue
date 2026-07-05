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
import { ref, inject, toRef, computed, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useD1BadDebt, type BadDebtRow } from '../composables/useD1BadDebt'
import type { ChecklistResponse } from '../composables/useD1FormData'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { useD1TabImportExport } from '../composables/useD1TabImportExport'
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

const wpIdRef = toRef(props, 'wpId')
const { onExportTemplate, onExportData, onImportFile } = useD1TabImportExport(wpIdRef, 'D1-4')
</script>

<template>
  <div class="d1-tab-bad-debt">
    <div class="tab-header">
      <h4>坏账准备 D1-4</h4>
      <GtReviewTrigger section-id="D1-baddebt-header" />
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
            <GtReviewDot row-prefix="D1-baddebt" :row-key="row.rowId" />
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
              <GtReviewDot row-prefix="D1-baddebt" :row-key="row.rowId" />
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
  </div>
</template>

<style scoped>
.d1-tab-bad-debt {
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
