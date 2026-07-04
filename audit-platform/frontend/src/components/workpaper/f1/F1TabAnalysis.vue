<template>
<div class="d3-analysis">
  <!-- 集中度警告 -->
  <el-alert
    v-if="top5ConcentrationWarning"
    type="warning"
    :title="top5ConcentrationWarning"
    :closable="false"
    show-icon
    style="margin-bottom: 12px"
  />

  <!-- 区块一：借方发生额分析 -->
  <div class="analysis-card">
    <h4 class="card-title">(一) 借方发生额分析</h4>
    <el-table :data="debitTableData" size="small" border stripe>
      <el-table-column prop="label" label="项目" width="180" />
      <el-table-column label="金额" width="130" align="right">
        <template #default="{ row }">
          <span :class="{ 'diff-red': row.rowKey === 'debit-diff' && row.amount !== 0 }">
            {{ fmtAmount(row.amount) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="source" label="来源" width="140" />
      <el-table-column prop="remark" label="备注" min-width="120" />
    </el-table>
  </div>

  <!-- 区块二：贷方发生额分析 -->
  <div class="analysis-card">
    <h4 class="card-title">(二) 贷方发生额分析</h4>
    <el-table :data="creditTableData" size="small" border stripe>
      <el-table-column prop="label" label="项目" width="180" />
      <el-table-column label="金额" width="130" align="right">
        <template #default="{ row }">
          <span :class="{ 'diff-red': row.rowKey === 'credit-diff' && row.amount !== 0 }">
            {{ fmtAmount(row.amount) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="source" label="来源" width="140" />
      <el-table-column prop="remark" label="备注" min-width="120" />
    </el-table>
  </div>

  <!-- 区块三：Top5债务人 -->
  <div class="analysis-card">
    <h4 class="card-title">(三) 期末主要债务人分析</h4>
    <el-table :data="top5Debtors" size="small" border stripe>
      <el-table-column type="index" label="序号" width="50" />
      <el-table-column prop="customerName" label="债务人名称" width="160">
        <template #default="{ row }">
          <span>{{ row.customerName }}</span>
          <GtIndexChip target="F1-2" :label="row.customerName" />
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.endAudited) }}</template>
      </el-table-column>
      <el-table-column label="期初余额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.priorAudited) }}</template>
      </el-table-column>
      <el-table-column label="变动金额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.changeAmount) }}</template>
      </el-table-column>
      <el-table-column label="变动比例" width="90">
        <template #default="{ row }">
          <span :class="{ 'rate-exceed': isRateHigh(row.changeRate) }">
            {{ fmtRate(row.changeRate) }}
          </span>
        </template>
      </el-table-column>
    </el-table>
  </div>

  <!-- 区块四：审计说明 -->
  <div class="analysis-card">
    <h4 class="card-title">三、审计说明</h4>
    <div class="note-block">
      <div class="note-label">
        分析性复核说明
        <el-button size="small" :disabled="true" title="AI功能暂未开放">🤖AI</el-button>
      </div>
      <el-input
        v-model="auditNote"
        type="textarea"
        :rows="4"
        :disabled="isReadonly"
        placeholder="对预付账款借贷方发生额变动、Top5集中度等进行分析性复核说明..."
      />
    </div>
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * F1TabAnalysis.vue — F1-4 分析表
 * 4区块卡片：借方/贷方/Top5/审计说明
 */
import { computed, type Ref } from 'vue'
import { isChangeRateExceeding } from '../composables/useF1FormulaEngine'
import { useF1Analysis } from '../composables/useF1Analysis'
import type { useF1CrossSheet } from '../composables/useF1CrossSheet'
import type { ChecklistResponse } from '../composables/useF1FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  isReadonly: boolean
  crossSheet: ReturnType<typeof useF1CrossSheet>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const {
  sections,
  top5Debtors,
  top5ConcentrationWarning,
  auditNote,
  debitRows,
  creditRows,
} = useF1Analysis({
  allResponses: props.allResponses,
  wpId: props.wpId,
  projectId: props.projectId,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  crossSheet: props.crossSheet,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

// Build table data for debit/credit including total + diff rows
const debitTableData = computed(() => {
  const sec = sections.value[0]
  if (!sec) return []
  return [...sec.rows, ...(sec.totalRow ? [sec.totalRow] : []), ...(sec.diffRow ? [sec.diffRow] : [])]
})

const creditTableData = computed(() => {
  const sec = sections.value[1]
  if (!sec) return []
  return [...sec.rows, ...(sec.totalRow ? [sec.totalRow] : []), ...(sec.diffRow ? [sec.diffRow] : [])]
})

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function fmtRate(rate: number | '' | 'N/A'): string {
  if (rate === '' || rate === 'N/A') return String(rate)
  return `${(rate * 100).toFixed(1)}%`
}

function isRateHigh(rate: number | '' | 'N/A'): boolean {
  return isChangeRateExceeding(rate, 0.3)
}
</script>

<style scoped>
.d3-analysis { padding: 16px; }
.analysis-card { margin-bottom: 20px; padding: 16px; background: #fff; border: 1px solid #ebeef5; border-radius: 6px; }
.card-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: #303133; }
.diff-red { color: #f56c6c; font-weight: 600; }
.rate-exceed { color: #f56c6c; font-weight: 600; }
.note-block { margin-top: 8px; }
.note-label { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 13px; color: #606266; }
</style>
