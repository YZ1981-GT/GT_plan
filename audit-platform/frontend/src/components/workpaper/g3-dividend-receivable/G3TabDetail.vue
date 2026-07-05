<!--
  G3TabDetail.vue — G3-2 应收股利明细表（33列 → 4区段Tab）

  4区段Tab切换：被投资方信息(8列) / 持股明细(9列) / 分红方案(8列) / 应收核算(8列)
  区段间行同步：所有区段共享同一行集合，切换Tab只改可见列
  公式列：权益份额/分红总额/实际分红率/应收股利/期末应收/逾期天数

  Spec: .kiro/specs/g3-dividend-receivable/ Task 6.2
  Requirements: 5.1~5.11
-->
<template>
  <div class="g3-detail">
    <div class="section-head">
      <h3 class="sheet-title">G3-2 应收股利明细表</h3>
      <div class="head-actions">
        <el-button size="small" :disabled="isReadonly" @click="detail.addRow()">＋ 新增明细行</el-button>
        <el-dropdown trigger="click" size="small">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReviewDialog('G3-2-detail')">💬复核</el-button>
      </div>
    </div>

    <!-- 4区段Tab -->
    <el-tabs v-model="detail.segment.value" type="border-card" class="segment-tabs">
      <el-tab-pane
        v-for="seg in detail.segments"
        :key="seg.key"
        :label="seg.label"
        :name="seg.key"
      />
    </el-tabs>

    <!-- 动态列表格 -->
    <el-table
      :data="detail.rows.value"
      border
      size="small"
      max-height="520"
      :row-class-name="rowClassName"
      class="detail-table"
    >
      <!-- 序号列（所有区段始终显示） -->
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">{{ row.seq }}</template>
      </el-table-column>

      <!-- 被投资方名称（所有区段始终显示作为锚定列） -->
      <el-table-column label="被投资方" width="150" fixed>
        <template #default="{ row }">
          <el-input
            :model-value="row.investeeName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => detail.updateRow(row.id, { investeeName: v })"
          />
        </template>
      </el-table-column>

      <!-- 动态区段列 -->
      <el-table-column
        v-for="col in currentColumns"
        :key="col.prop"
        :label="col.label"
        :min-width="col.width"
        align="right"
      >
        <template #default="{ row }">
          <!-- 公式列：只读 + 虚线下划线 -->
          <template v-if="col.formula">
            <span
              class="formula-cell"
              :title="getFormulaTooltip(col.prop)"
            >
              {{ formatCellValue(row, col) }}
            </span>
          </template>

          <!-- 投资类型下拉 -->
          <template v-else-if="col.type === 'invest-type'">
            <el-select
              :model-value="row[col.prop]"
              size="small"
              :disabled="isReadonly"
              style="width:100%"
              @change="(v: string) => detail.updateRow(row.id, { [col.prop]: v })"
            >
              <el-option
                v-for="opt in investTypeOptions"
                :key="opt.value"
                :value="opt.value"
                :label="opt.label"
              />
            </el-select>
          </template>

          <!-- 核算方法下拉 -->
          <template v-else-if="col.type === 'method'">
            <el-select
              :model-value="row[col.prop]"
              size="small"
              :disabled="isReadonly"
              style="width:100%"
              @change="(v: string) => detail.updateRow(row.id, { [col.prop]: v })"
            >
              <el-option
                v-for="opt in methodOptions"
                :key="opt.value"
                :value="opt.value"
                :label="opt.label"
              />
            </el-select>
          </template>

          <!-- 日期列 -->
          <template v-else-if="col.type === 'date'">
            <el-date-picker
              :model-value="row[col.prop]"
              type="date"
              size="small"
              :disabled="isReadonly"
              value-format="YYYY-MM-DD"
              style="width:100%"
              @update:model-value="(v: string) => detail.updateRow(row.id, { [col.prop]: v ?? '' })"
            />
          </template>

          <!-- 数字列 -->
          <template v-else-if="col.type === 'number'">
            <el-input-number
              :model-value="row[col.prop] as number"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { [col.prop]: v ?? 0 })"
            />
          </template>

          <!-- 文本列 -->
          <template v-else>
            <el-input
              :model-value="row[col.prop] as string"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => detail.updateRow(row.id, { [col.prop]: v })"
            />
          </template>
        </template>
      </el-table-column>

      <!-- 操作列(删除) -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-icon class="delete-icon" @click="detail.removeRow(row.id)">
            <Delete />
          </el-icon>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部合计 -->
    <div class="totals-bar">
      <span class="totals-label">合计</span>
      <span class="total-item">投资成本：{{ fmtNum(detail.totals.value.initialCost) }}</span>
      <span class="total-item">分红总额：{{ fmtNum(detail.totals.value.totalDividend) }}</span>
      <span class="total-item">应收股利：{{ fmtNum(detail.totals.value.dividendReceivable) }}</span>
      <span class="total-item">已收金额：{{ fmtNum(detail.totals.value.receivedAmount) }}</span>
      <span class="total-item">期末应收：{{ fmtNum(detail.totals.value.netReceivable) }}</span>
    </div>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>权益份额 = 被投资方净资产 × 持股比例 / 100</li>
        <li>分红总额 = 持股数量 × 每股股利</li>
        <li>实际分红率 = 分红总额 / 被投资方净利润 × 100%（净利润≤0时显示N/A）</li>
        <li>应收股利 = 持股数量 × 每股股利</li>
        <li>期末应收 = 应收股利 - 已收金额</li>
        <li>逾期天数 = MAX(0, 当前日期 - 股权登记日)</li>
        <li>逾期行以橙色背景高亮</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, inject } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import {
  useG3Detail,
  G3_DETAIL_SEGMENTS,
  G3_INVEST_TYPE_OPTIONS,
  G3_ACCOUNTING_METHOD_OPTIONS,
  isRowOverdue,
} from '../composables/useG3Detail'
import type { G3DetailColumn, DividendDetailRow } from '../composables/useG3Detail'
import type { ChecklistResponse } from '../composables/useF1FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const detail = useG3Detail({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const investTypeOptions = G3_INVEST_TYPE_OPTIONS
const methodOptions = G3_ACCOUNTING_METHOD_OPTIONS

// ─── 当前区段可见列（排除seq和investeeName，已作固定列） ───
const currentColumns = computed<G3DetailColumn[]>(() => {
  const seg = G3_DETAIL_SEGMENTS.find((s) => s.key === detail.segment.value)
  if (!seg) return []
  // 排除 seq 和 investeeName，它们作为固定列已单独渲染
  return seg.columns.filter((c) => c.prop !== 'seq' && c.prop !== 'investeeName')
})

// ─── 行样式：逾期行橙色 ───
function rowClassName({ row }: { row: DividendDetailRow }): string {
  return isRowOverdue(row) ? 'row-overdue' : ''
}

// ─── 公式列tooltip ───
function getFormulaTooltip(prop: keyof DividendDetailRow): string {
  const tooltips: Partial<Record<keyof DividendDetailRow, string>> = {
    seq: '序号（自动）',
    equityShare: '权益份额 = 被投资方净资产 × 持股比例 / 100',
    totalDividend: '分红总额 = 持股数量 × 每股股利',
    payoutRatio: '实际分红率 = 分红总额 / 净利润 × 100%',
    dividendReceivable: '应收股利 = 持股数量 × 每股股利',
    netReceivable: '期末应收 = 应收股利 - 已收金额',
    overdueDays: '逾期天数 = MAX(0, 当前日期 - 股权登记日)',
  }
  return tooltips[prop] ?? '公式计算'
}

// ─── 单元格格式化（分红率N/A处理） ───
function formatCellValue(row: DividendDetailRow, col: G3DetailColumn): string {
  const val = row[col.prop]
  // 分红率特殊处理：净利润≤0时显示N/A
  if (col.prop === 'payoutRatio') {
    if (row.investeeNetProfit <= 0) return 'N/A'
    return fmtNum(val)
  }
  if (typeof val === 'number') return fmtNum(val)
  return String(val ?? '')
}

// ─── 数字格式化 ───
function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

// ─── 导入导出（占位，useG3ImportExport Task 8.2 实现） ───
function handleExportTemplate() {
  ElMessage.info('导出模板功能将在导入导出模块完成后启用')
}
function handleExportData() {
  ElMessage.info('导出数据功能将在导入导出模块完成后启用')
}
function handleImportData() {
  ElMessage.info('导入数据功能将在导入导出模块完成后启用')
}
</script>

<style scoped>
.g3-detail {
  padding: 12px;
  font-size: 13px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.sheet-title {
  margin: 0;
  font-size: 15px;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 区段Tab */
.segment-tabs {
  margin-bottom: 0;
}

.segment-tabs :deep(.el-tabs__content) {
  display: none; /* 内容区由下方el-table渲染，不需要tab-pane内容 */
}

/* 表格 */
.detail-table {
  border-top: none;
}

/* 公式列：虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  display: inline-block;
  min-width: 40px;
  text-align: right;
}

/* 逾期行橙色 */
:deep(.row-overdue) {
  background-color: #fdf6ec !important;
}
:deep(.row-overdue td) {
  background-color: #fdf6ec !important;
}

/* 删除图标 */
.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover {
  color: #f56c6c;
}

/* 底部合计 */
.totals-bar {
  display: flex;
  gap: 16px;
  margin-top: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 600;
  flex-wrap: wrap;
}
.totals-label {
  color: #303133;
  min-width: 36px;
}
.total-item {
  color: #606266;
}

/* 编制提示 */
.prep-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}
.prep-hint summary {
  cursor: pointer;
}
.prep-hint ul {
  margin: 8px 0 0;
  padding-left: 18px;
}
</style>
