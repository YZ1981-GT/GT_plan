<script setup lang="ts">
/**
 * D4TabOtherRevenue — D4-3 其他业务收入明细
 *
 * el-table + 审定/占比/变动自动计算 + 变动>30%红色
 * "添加项目行" + 合计行 + 核对行
 * 审计说明/结论 + 💬复核
 *
 * Requirements: 4.1-4.7, 21.2
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { useD4OtherRevenue, type OtherRevenueRow } from '../../composables/useD4OtherRevenue'
import { isChangeRateExceeding } from '../../composables/useD4FormulaEngine'
import { useD4ImportExport } from '../../composables/useD4ImportExport'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── 金额格式化 ───────────────────────────────────────────────────────
function fmtAmount(v: number): string {
  if (v === 0) return '-'
  if (v < 0) return `(${Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(rate: number | '' | 'N/A'): string {
  if (rate === '' || rate === 'N/A') return rate === '' ? '-' : 'N/A'
  return (rate * 100).toFixed(1) + '%'
}

function fmtPercent(v: number): string {
  return v.toFixed(2) + '%'
}

// ─── Composable ───────────────────────────────────────────────────────
const {
  rows,
  subtotalRow,
  verificationRow,
  addRow,
  removeRow,
  updateCell,
} = useD4OtherRevenue({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── 导入导出 ─────────────────────────────────────────────────────────
const { exportTemplate, exportData, importData, importing } = useD4ImportExport({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
})

function handleImportUpload(file: File): boolean {
  importData('D4-3', file)
  return false
}

// ─── 样式判断 ─────────────────────────────────────────────────────────
function getRateCellClass(rate: number | '' | 'N/A'): string {
  if (isChangeRateExceeding(rate, 0.3)) return 'rate-warning'
  return ''
}

function getRowClassName({ row }: { row: OtherRevenueRow }): string {
  if (row.rowId === 'subtotal') return 'subtotal-row-bg'
  return ''
}

// ─── 核对 ─────────────────────────────────────────────────────────────
const hasDifference = computed(() => Math.abs(verificationRow.value.diff) > 0.005)

// ─── 审计说明/结论 ────────────────────────────────────────────────────
const auditNote = computed({
  get: () => props.allResponses.get('D4-3-note')?.remark || '',
  set: (val: string) => {
    const map = props.allResponses as Map<string, any>
    map.set('D4-3-note', { item_id: 'D4-3-note', conclusion: null, remark: val })
  },
})

const auditConclusion = computed({
  get: () => props.allResponses.get('D4-3-conclusion')?.remark || '',
  set: (val: string) => {
    const map = props.allResponses as Map<string, any>
    map.set('D4-3-conclusion', { item_id: 'D4-3-conclusion', conclusion: null, remark: val })
  },
})
</script>

<template>
  <div class="d4-tab-other-revenue">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表列示被审计单位其他业务收入（科目6051）明细。</p>
        <p>2. "审定数""占比""变动额""变动率"为自动计算列，不可手工编辑。</p>
        <p>3. 变动率超过30%自动标红，请关注重大变动项目。</p>
      </div>
    </details>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tooltip placement="top" :show-after="300">
          <template #content>
            本表为手工填列，非自动取数。<br/>
            建议先导出模板，离线填写后再导入，效率更高。
          </template>
          <el-button size="small" :disabled="isReadonly" @click="addRow">+ 添加项目行</el-button>
        </el-tooltip>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click" :disabled="isReadonly">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate('D4-3')">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData('D4-3')">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload
                  :show-file-list="false"
                  accept=".xlsx,.xls"
                  :before-upload="handleImportUpload"
                  :disabled="importing"
                >
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 主表 -->
    <el-table
      :data="[...rows, subtotalRow]"
      border
      size="small"
      :row-class-name="getRowClassName"
      style="width: 100%; margin-bottom: 12px"
    >
      <!-- 项目名称 -->
      <el-table-column label="项目" width="150" fixed>
        <template #default="{ row }">
          <template v-if="row.rowId === 'subtotal'">
            <span class="font-bold">合计</span>
          </template>
          <template v-else>
            <el-input
              v-if="!isReadonly"
              :model-value="row.item"
              size="small"
              placeholder="项目名称"
              @change="(v: string) => updateCell(row.rowId, 'item', v)"
            />
            <span v-else>{{ row.item || '(未命名)' }}</span>
          </template>
        </template>
      </el-table-column>

      <!-- 本期 -->
      <el-table-column label="本期" align="center">
        <el-table-column label="未审数" width="120" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === 'subtotal'">
              <span class="font-bold">{{ fmtAmount(row.currentUnadjusted) }}</span>
            </template>
            <template v-else>
              <el-input
                v-if="!isReadonly"
                :model-value="row.currentUnadjusted"
                size="small"
                type="number"
                @change="(v: string) => updateCell(row.rowId, 'currentUnadjusted', v)"
              />
              <span v-else>{{ fmtAmount(row.currentUnadjusted) }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="审计调整" width="110" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === 'subtotal'">
              <span class="font-bold">{{ fmtAmount(row.currentAdjustment) }}</span>
            </template>
            <template v-else>
              <el-input
                v-if="!isReadonly"
                :model-value="row.currentAdjustment"
                size="small"
                type="number"
                @change="(v: string) => updateCell(row.rowId, 'currentAdjustment', v)"
              />
              <span v-else>{{ fmtAmount(row.currentAdjustment) }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="audited-cell">{{ fmtAmount(row.currentAudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="占比" width="80" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span>{{ fmtPercent(row.currentProportion) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 上期 -->
      <el-table-column label="上期" align="center">
        <el-table-column label="未审数" width="120" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === 'subtotal'">
              <span class="font-bold">{{ fmtAmount(row.priorUnadjusted) }}</span>
            </template>
            <template v-else>
              <el-input
                v-if="!isReadonly"
                :model-value="row.priorUnadjusted"
                size="small"
                type="number"
                @change="(v: string) => updateCell(row.rowId, 'priorUnadjusted', v)"
              />
              <span v-else>{{ fmtAmount(row.priorUnadjusted) }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="审计调整" width="110" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === 'subtotal'">
              <span class="font-bold">{{ fmtAmount(row.priorAdjustment) }}</span>
            </template>
            <template v-else>
              <el-input
                v-if="!isReadonly"
                :model-value="row.priorAdjustment"
                size="small"
                type="number"
                @change="(v: string) => updateCell(row.rowId, 'priorAdjustment', v)"
              />
              <span v-else>{{ fmtAmount(row.priorAdjustment) }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span>{{ fmtAmount(row.priorAudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="占比" width="80" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span>{{ fmtPercent(row.priorProportion) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 变动 -->
      <el-table-column label="变动额" width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span>{{ fmtAmount(row.changeAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动率" width="95" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span :class="getRateCellClass(row.changeRate)">{{ fmtRate(row.changeRate) }}</span>
        </template>
      </el-table-column>

      <!-- 备注 -->
      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <template v-if="row.rowId === 'subtotal'">
            <span>-</span>
          </template>
          <template v-else>
            <el-input
              v-if="!isReadonly"
              :model-value="row.remark"
              size="small"
              placeholder="备注"
              @change="(v: string) => updateCell(row.rowId, 'remark', v)"
            />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </template>
      </el-table-column>

      <!-- 操作 -->
      <el-table-column label="" width="50" align="center">
        <template #default="{ row }">
          <el-button
            v-if="row.rowId !== 'subtotal' && !isReadonly"
            type="danger"
            size="small"
            link
            @click="removeRow(row.rowId)"
          >删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 核对行 -->
    <div class="tb-check-row">
      <span class="tb-label">与试算平衡表核对（科目6051）：</span>
      <el-tag v-if="hasDifference" type="danger" size="small">差异 {{ fmtAmount(verificationRow.diff) }}</el-tag>
      <el-tag v-else type="success" size="small">核对一致</el-tag>
    </div>

    <!-- 审计说明 -->
    <div class="audit-note-section">
      <div class="note-header">
        <h4>审计说明</h4>
        <div class="note-actions">
          <el-button size="small" disabled>🤖 AI生成</el-button>
          <el-button size="small" circle @click="openReviewDialog?.('D4-3-note')">💬</el-button>
        </div>
      </div>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请输入审计说明..."
        :disabled="isReadonly"
      />
    </div>

    <!-- 审计结论 -->
    <div class="audit-note-section">
      <div class="note-header">
        <h4>审计结论</h4>
      </div>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        placeholder="请输入审计结论..."
        :disabled="isReadonly"
      />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-other-revenue {
  padding: 12px;
}
.d4-tab-other-revenue :deep(.el-table) {
  --el-table-font-size: 13px;
  font-size: 13px;
}
.d4-tab-other-revenue :deep(.el-table .cell) {
  font-size: 13px !important;
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.rate-warning {
  color: #f56c6c;
  font-weight: 600;
}
.audited-cell {
  font-weight: 600;
}
.font-bold {
  font-weight: 600;
}
:deep(.subtotal-row-bg) {
  background-color: #fafafa !important;
  font-weight: 600;
}
.tb-check-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 16px;
  font-size: 13px;
}
.tb-label {
  color: #909399;
}
.audit-note-section {
  margin-bottom: 16px;
}
.note-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.note-header h4 {
  margin: 0;
  font-size: 14px;
  color: #303133;
}
.note-actions {
  display: flex;
  gap: 6px;
}
</style>
