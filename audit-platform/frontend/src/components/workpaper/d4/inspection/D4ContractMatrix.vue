<script setup lang="ts">
/**
 * D4ContractMatrix — D4-12 合同检查矩阵视图（只读比对）
 *
 * 横向N列=N份合同，纵向20+1行=检查字段+结论
 * 用于审计师一览比对所有合同检查结果
 */
import { computed } from 'vue'
import {
  FIELD_GROUPS,
  type ContractInspectionItem,
} from '../../composables/useD4ContractInspection'

const props = defineProps<{
  contracts: ContractInspectionItem[]
  totalContractAmount: number
  coverageRate: number
}>()

// ─── 行数据构建 ──────────────────────────────────────────────────────

interface MatrixRow {
  key: string
  label: string
  type: string
  isGroupHeader?: boolean
  groupLabel?: string
}

const matrixRows = computed<MatrixRow[]>(() => {
  const rows: MatrixRow[] = []
  for (const group of FIELD_GROUPS) {
    // 分组标题行
    rows.push({ key: `__group_${group.label}`, label: group.label, type: 'group', isGroupHeader: true, groupLabel: group.label })
    for (const field of group.fields) {
      rows.push({ key: field.key, label: field.label, type: field.type })
    }
  }
  // 结论行
  rows.push({ key: 'conclusion', label: '结论', type: 'radio' })
  return rows
})

// ─── 汇总统计 ──────────────────────────────────────────────────────

const ynCounts = computed(() => {
  let y = 0, n = 0, na = 0
  for (const c of props.contracts) {
    if (c.conclusion === 'Y') y++
    else if (c.conclusion === 'N') n++
    else if (c.conclusion === 'NA') na++
  }
  return { y, n, na }
})

// ─── 格式化 ──────────────────────────────────────────────────────────

function getCellValue(contract: ContractInspectionItem, key: string): any {
  return (contract as any)[key]
}

function fmtAmount(v: number | string | undefined): string {
  const num = typeof v === 'string' ? parseFloat(v) : v
  if (!num && num !== 0) return '—'
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function isYNField(type: string): boolean {
  return type === 'radio'
}

function isAmountField(key: string): boolean {
  return key === 'contractAmount'
}

function getTagType(val: string): string {
  if (val === 'Y') return 'success'
  if (val === 'N') return 'danger'
  if (val === 'NA') return 'info'
  return 'info'
}

function getColumnHeader(c: ContractInspectionItem): string {
  const name = c.counterparty || c.label || '待填写'
  return `${c.indexNo} ${name}`
}
</script>

<template>
  <div class="d4-matrix">
    <el-table
      :data="matrixRows"
      border
      :row-class-name="({ row }: any) => row.isGroupHeader ? 'group-header-row' : ''"
      :span-method="({ row, columnIndex }: any) => {
        if (row.isGroupHeader) {
          if (columnIndex === 0) return { rowspan: 1, colspan: contracts.length + 1 }
          return { rowspan: 0, colspan: 0 }
        }
        return { rowspan: 1, colspan: 1 }
      }"
      style="width: 100%"
      class="matrix-table"
    >
      <!-- 字段标签列（固定） -->
      <el-table-column
        fixed
        label="检查项目"
        min-width="200"
        class-name="field-label-col"
      >
        <template #default="{ row }">
          <span v-if="row.isGroupHeader" class="group-header-text">{{ row.groupLabel }}</span>
          <span v-else class="field-label">{{ row.label }}</span>
        </template>
      </el-table-column>

      <!-- 合同列 -->
      <el-table-column
        v-for="c in contracts"
        :key="c.id"
        :label="getColumnHeader(c)"
        min-width="180"
      >
        <template #default="{ row }">
          <template v-if="row.isGroupHeader"><!-- merged --></template>
          <template v-else-if="isYNField(row.type)">
            <el-tag
              v-if="getCellValue(c, row.key)"
              :type="getTagType(getCellValue(c, row.key))"
              size="small"
              effect="plain"
            >{{ getCellValue(c, row.key) }}</el-tag>
            <span v-else class="empty-cell">—</span>
          </template>
          <template v-else-if="isAmountField(row.key)">
            <span class="amount-cell">{{ fmtAmount(getCellValue(c, row.key)) }}</span>
          </template>
          <template v-else-if="row.key === 'recognitionMethod'">
            <el-tag v-if="getCellValue(c, row.key)" size="small" effect="plain" type="warning">
              {{ getCellValue(c, row.key) }}
            </el-tag>
            <span v-else class="empty-cell">—</span>
          </template>
          <template v-else>
            <span v-if="getCellValue(c, row.key)" class="text-cell">{{ getCellValue(c, row.key) }}</span>
            <span v-else class="empty-cell">—</span>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <!-- 汇总行 -->
    <div class="matrix-summary">
      <div class="summary-item">
        <span class="summary-label">合同金额合计</span>
        <span class="summary-value">{{ fmtAmount(totalContractAmount) }} 元</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">覆盖率</span>
        <span class="summary-value" :class="{ 'warn': coverageRate < 60 }">{{ coverageRate.toFixed(1) }}%</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">结论分布</span>
        <span class="summary-tags">
          <el-tag type="success" size="small" effect="plain">Y: {{ ynCounts.y }}</el-tag>
          <el-tag type="danger" size="small" effect="plain">N: {{ ynCounts.n }}</el-tag>
          <el-tag type="info" size="small" effect="plain">NA: {{ ynCounts.na }}</el-tag>
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.d4-matrix {
  font-size: 13px;
}

.matrix-table {
  font-size: 13px;
}

:deep(.group-header-row) {
  background-color: #f3f0ff !important;
}
:deep(.group-header-row td) {
  background-color: #f3f0ff !important;
}

.group-header-text {
  font-weight: 600;
  color: #7c5cff;
  font-size: 13px;
}

.field-label {
  font-weight: 500;
  color: #303133;
  font-size: 13px;
}

:deep(.field-label-col) {
  background-color: #fafafa;
}

.empty-cell {
  color: #c0c4cc;
}

.amount-cell {
  text-align: right;
  display: block;
  font-variant-numeric: tabular-nums;
  color: #303133;
}

.text-cell {
  color: #606266;
  line-height: 1.5;
  word-break: break-all;
}

.matrix-summary {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 12px 16px;
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-top: none;
  border-radius: 0 0 8px 8px;
}

.summary-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.summary-label {
  color: #909399;
  font-size: 13px;
}

.summary-value {
  font-weight: 600;
  color: #303133;
  font-size: 13px;
}

.summary-value.warn {
  color: #e6a23c;
}

.summary-tags {
  display: flex;
  gap: 6px;
}

:deep(.el-table) {
  --el-table-border-color: #ebeef5;
}

:deep(.el-table th) {
  font-size: 13px;
  font-weight: 500;
}

:deep(.el-table td) {
  font-size: 13px;
  padding: 8px 12px;
}
</style>
