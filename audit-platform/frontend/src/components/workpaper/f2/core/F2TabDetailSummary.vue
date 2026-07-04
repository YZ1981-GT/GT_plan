<template>
  <div class="f2-summary">
    <div class="sheet-header">
      <h3 class="sheet-title">F2-2 存货明细汇总表</h3>
      <F2ReviewChip section-id="F2-2-summary" />
    </div>
    <p class="hint">数据自动从 F2-3~F2-13 各明细表合计行聚合（含 F2-10 开发产品）</p>

    <el-tag v-if="summary.agingMismatchCount.value > 0" type="warning" size="small" class="warn-tag">
      {{ summary.agingMismatchCount.value }} 类库龄合计≠期末金额
    </el-tag>

    <div class="table-wrap">
      <el-table
        :data="[...summary.rows.value, summary.totals.value]"
        border
        size="small"
        style="width: 100%; font-size: 13px"
        :row-class-name="rowClassName"
      >
        <el-table-column prop="label" label="存货类别" min-width="140" fixed>
          <template #default="{ row }">
            <span :class="{ 'total-label': row.sheetCode === '' }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="72" fixed>
          <template #default="{ row }">
            <GtIndexChip
              v-if="row.sheetCode"
              :value="row.sheetCode"
              :context-project-id="projectId"
            />
          </template>
        </el-table-column>

        <el-table-column label="期初数量" min-width="100" align="right">
          <template #default="{ row }">{{ fmtQty(row.openingQty, row.hasQuantity) }}</template>
        </el-table-column>
        <el-table-column label="期初单价" min-width="100" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式：金额 ÷ 数量" placement="top">
              <span class="formula-cell">{{ fmtPrice(row.openingUnitPrice) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="期初金额" min-width="110" align="right">
          <template #default="{ row }">{{ fmtAmt(row.openingAmt) }}</template>
        </el-table-column>

        <el-table-column label="增加数量" min-width="100" align="right">
          <template #default="{ row }">{{ fmtQty(row.increaseQty, row.hasQuantity) }}</template>
        </el-table-column>
        <el-table-column label="增加单价" min-width="100" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式：金额 ÷ 数量" placement="top">
              <span class="formula-cell">{{ fmtPrice(row.increaseUnitPrice) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="增加金额" min-width="110" align="right">
          <template #default="{ row }">{{ fmtAmt(row.increaseAmt) }}</template>
        </el-table-column>

        <el-table-column label="减少数量" min-width="100" align="right">
          <template #default="{ row }">{{ fmtQty(row.decreaseQty, row.hasQuantity) }}</template>
        </el-table-column>
        <el-table-column label="减少单价" min-width="100" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式：金额 ÷ 数量" placement="top">
              <span class="formula-cell">{{ fmtPrice(row.decreaseUnitPrice) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="减少金额" min-width="110" align="right">
          <template #default="{ row }">{{ fmtAmt(row.decreaseAmt) }}</template>
        </el-table-column>

        <el-table-column label="期末数量" min-width="100" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式：期初 + 增加 - 减少" placement="top">
              <span class="formula-cell">{{ fmtQty(row.closingQty, row.hasQuantity) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="期末单价" min-width="100" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式：金额 ÷ 数量" placement="top">
              <span class="formula-cell">{{ fmtPrice(row.closingUnitPrice) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="期末金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式：期初金额 + 增加 - 减少" placement="top">
              <span class="formula-cell">{{ fmtAmt(row.closingAmt) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="1年以内" min-width="100" align="right">
          <template #default="{ row }">{{ fmtAmt(row.agingLt1) }}</template>
        </el-table-column>
        <el-table-column label="1-2年" min-width="90" align="right">
          <template #default="{ row }">{{ fmtAmt(row.aging1to2) }}</template>
        </el-table-column>
        <el-table-column label="2-3年" min-width="90" align="right">
          <template #default="{ row }">{{ fmtAmt(row.aging2to3) }}</template>
        </el-table-column>
        <el-table-column label="3年以上" min-width="90" align="right">
          <template #default="{ row }">{{ fmtAmt(row.agingGt3) }}</template>
        </el-table-column>
        <el-table-column label="库龄合计" min-width="110" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式：Σ(1年以内 + 1-2年 + 2-3年 + 3年以上)" placement="top">
              <span :class="['formula-cell', { 'aging-warn': row.agingMismatch }]">{{ fmtAmt(row.agingTotal) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2DetailSummary } from '../../composables/useF2DetailSummary'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import type { F2SummaryRow } from '../../composables/useF2DetailSummary'
import GtIndexChip from '../../GtIndexChip.vue'
import F2ReviewChip from '../shared/F2ReviewChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  projectId?: string
}>()

const summary = useF2DetailSummary(toRef(props, 'allResponses'))

function fmtAmt(v: number): string {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtQty(v: number, hasQuantity: boolean): string {
  if (!hasQuantity) return '—'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}

function fmtPrice(v: number | ''): string {
  if (v === '' || v == null) return '—'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 4, maximumFractionDigits: 4 })
}

function rowClassName({ row }: { row: F2SummaryRow }): string {
  if (row.sheetCode === '') return 'total-row'
  if (row.agingMismatch) return 'warn-row'
  return ''
}
</script>

<style scoped>
.f2-summary { padding: 12px; font-size: 13px; }
.sheet-title { margin: 0; }
.sheet-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.hint { font-size: 12px; color: #909399; margin-bottom: 8px; }
.warn-tag { margin-bottom: 8px; }
.table-wrap { overflow-x: auto; }
.aging-warn { color: #e6a23c; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #c0c4cc; cursor: help; }
.total-label { font-weight: 600; }
:deep(.warn-row) { background: #fdf6ec; }
:deep(.total-row) { background: #f5f7fa; font-weight: 600; }
</style>
