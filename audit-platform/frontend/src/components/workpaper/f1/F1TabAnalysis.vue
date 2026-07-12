<template>
<div class="d3-analysis">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 本表对预付账款（科目1123）借方/贷方发生额及主要债务人集中度进行分析性复核。</p>
      <p>2. 借贷方发生额应与序时账及明细表勾稽一致，差异行标红时须查明原因。</p>
      <p>3. Top5 债务人集中度偏高或单户变动率超30%时应关注长期挂账与关联方预付风险。</p>
      <p>4. 结合账龄结构评估预付款可收回性，识别潜在减值及重分类迹象。</p>
    </div>
  </details>

  <!-- 审计目标 -->
  <el-alert
    type="info"
    :closable="false"
    title="审计目标：通过分析性复核评价预付账款发生额变动与集中度的合理性，识别异常波动、长期挂账及关联方预付风险。"
    class="objective-alert"
  />

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
          <GtIndexChip value="wp:F1-2" :context-project-id="projectId" />
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

  <!-- 区块四：审计说明（卡片式） -->
  <el-card class="opinion-card" shadow="never">
    <template #header>
      <div class="opinion-header">
        <span class="opinion-title">审计说明</span>
        <div class="opinion-chips">
          <GtIndexChip value="wp:F1-2" :context-project-id="projectId" />
        </div>
      </div>
    </template>
    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">分析性复核说明</span>
      </div>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="对预付账款借贷方发生额变动、Top5集中度等进行分析性复核说明..."
      />
    </div>
  </el-card>
</div>
</template>

<script setup lang="ts">
/**
 * F1TabAnalysis.vue — F1-4 分析表
 * 4区块卡片：借方/贷方/Top5/审计说明
 */
import { computed, toRef, type Ref } from 'vue'
import { isChangeRateExceeding } from '../composables/useF1FormulaEngine'
import { useF1Analysis } from '../composables/useF1Analysis'
import type { useF1CrossSheet } from '../composables/useF1CrossSheet'
import type { ChecklistResponse } from '../composables/useF1FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  crossSheet: ReturnType<typeof useF1CrossSheet>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const {
  sections,
  top5Debtors,
  top5ConcentrationWarning,
  auditNote,
  debitRows,
  creditRows,
} = useF1Analysis({
  allResponses: allResponsesRef,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
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
.d3-analysis :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.d3-analysis :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

.analysis-card { margin-bottom: 20px; padding: 16px; background: #fff; border: 1px solid #ebeef5; border-radius: 6px; }
.card-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: #303133; }
.diff-red { color: #f56c6c; font-weight: 600; }
.rate-exceed { color: #f56c6c; font-weight: 600; }

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.opinion-section-label { font-size: 14px; font-weight: 500; color: #303133; }
</style>
