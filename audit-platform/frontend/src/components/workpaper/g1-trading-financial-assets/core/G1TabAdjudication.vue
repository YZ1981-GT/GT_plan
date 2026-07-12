<template>
  <div class="g1-adjudication">
    <div class="section-head">
      <h3 class="sheet-title">G1-1 交易性金融资产审定表</h3>
      <div class="head-actions">
        <span class="chip-wrap"><GtIndexChip value="wp:G1-2" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-3" /></span>
        <el-button size="small" @click="openReviewDialog('G1-1-conclusion')">💬复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实交易性金融资产（科目1501）各投资品种本期与上期审定金额的准确与完整，确认公允价值变动损益及处置损益列报恰当，为资产负债表列报及附注披露提供审定依据。"
      class="objective-alert"
    />

    <el-table :data="rows" border size="small" :span-method="spanInvest">
      <el-table-column prop="investLabel" label="投资品种" width="100" fixed />
      <el-table-column prop="measureLabel" label="项目" width="120" fixed />
      <el-table-column label="上期未审" width="110">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowKey !== 'subtotal'"
            :model-value="row.priorUnadjusted"
            size="small" :controls="false" :disabled="isReadonly"
            @update:model-value="(v: number) => updateField(row.investKey, row.measureKey, 'prior', 'unadj', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="上期AJE" width="100">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowKey !== 'subtotal'"
            :model-value="row.priorAje"
            size="small" :controls="false" :disabled="isReadonly"
            @update:model-value="(v: number) => updateField(row.investKey, row.measureKey, 'prior', 'aje', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="上期RJE" width="100">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowKey !== 'subtotal'"
            :model-value="row.priorRje"
            size="small" :controls="false" :disabled="isReadonly"
            @update:model-value="(v: number) => updateField(row.investKey, row.measureKey, 'prior', 'rje', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="上期审定" width="110" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="上期审定 = 上期未审 + 上期AJE + 上期RJE">{{ row.priorAudited.toLocaleString() }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期未审" width="110">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowKey !== 'subtotal'"
            :model-value="row.currentUnadjusted"
            size="small" :controls="false" :disabled="isReadonly"
            @update:model-value="(v: number) => updateField(row.investKey, row.measureKey, 'cur', 'unadj', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="本期AJE" width="100">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowKey !== 'subtotal'"
            :model-value="row.currentAje"
            size="small" :controls="false" :disabled="isReadonly"
            @update:model-value="(v: number) => updateField(row.investKey, row.measureKey, 'cur', 'aje', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="本期RJE" width="100">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowKey !== 'subtotal'"
            :model-value="row.currentRje"
            size="small" :controls="false" :disabled="isReadonly"
            @update:model-value="(v: number) => updateField(row.investKey, row.measureKey, 'cur', 'rje', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="本期审定" width="110" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="本期审定 = 本期未审 + 本期AJE + 本期RJE">{{ row.currentAudited.toLocaleString() }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动额" width="100" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="变动额 = 本期审定 - 上期审定">{{ row.changeAmount.toLocaleString() }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动率" width="80" class-name="auto-calc-col">
        <template #default="{ row }">
          <span v-if="row.changeRate === 'N/A'">N/A</span>
          <span v-else-if="row.changeRate === ''">—</span>
          <span v-else>{{ (Number(row.changeRate) * 100).toFixed(1) }}%</span>
        </template>
      </el-table-column>
    </el-table>

    <el-table :data="[totalRow]" border size="small" class="subtotal-table" :show-header="false">
      <el-table-column width="100"><template #default="{ row }"><b>{{ row.investLabel }}</b></template></el-table-column>
      <el-table-column width="120" />
      <el-table-column width="110"><template #default="{ row }">{{ row.priorUnadjusted.toLocaleString() }}</template></el-table-column>
      <el-table-column width="100"><template #default="{ row }">{{ row.priorAje.toLocaleString() }}</template></el-table-column>
      <el-table-column width="100"><template #default="{ row }">{{ row.priorRje.toLocaleString() }}</template></el-table-column>
      <el-table-column width="110"><template #default="{ row }">{{ row.priorAudited.toLocaleString() }}</template></el-table-column>
      <el-table-column width="110"><template #default="{ row }">{{ row.currentUnadjusted.toLocaleString() }}</template></el-table-column>
      <el-table-column width="100"><template #default="{ row }">{{ row.currentAje.toLocaleString() }}</template></el-table-column>
      <el-table-column width="100"><template #default="{ row }">{{ row.currentRje.toLocaleString() }}</template></el-table-column>
      <el-table-column width="110"><template #default="{ row }">{{ row.currentAudited.toLocaleString() }}</template></el-table-column>
      <el-table-column width="100"><template #default="{ row }">{{ row.changeAmount.toLocaleString() }}</template></el-table-column>
      <el-table-column width="80" />
    </el-table>

    <div class="tb-diff-row">
      <span>试算平衡表数（1501）：
        <el-input-number v-model="trialBalanceAmount" size="small" :controls="false" :disabled="isReadonly" />
      </span>
      <span :class="{ 'diff-red': trialBalanceDiff !== 0 }">
        差异：{{ trialBalanceDiff.toLocaleString() }}
        <template v-if="trialBalanceDiff === 0"> ✓</template>
        <template v-else> ✗</template>
      </span>
    </div>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
        </div>
      </template>
      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">1. 审计说明</span>
        </div>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
          placeholder="交易性金融资产审定说明（如公允价值变动来源、处置损益核对、与试算表核对等）..." />
      </div>
      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">2. 审计结论</span>
        </div>
        <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
          placeholder="审计结论..." />
      </div>
    </el-card>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>审定 = 未审 + AJE + RJE；本表按投资品种（股票/基金/债券/衍生工具/其他）×损益分类（成本/公允价值变动/处置损益）矩阵列示。</li>
        <li>灰底列为自动计算列（审定/变动额/变动率），不可手动编辑。</li>
        <li>本期审定合计应与试算平衡表科目1501核对一致，差异为 0 方为核对通过。</li>
        <li>审定数变更自动发布 EventBus（substantive:adjudicated，科目1501）联动附注披露与 trial_balance。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { toRef, inject } from 'vue'
import { useG1Adjudication } from '../../composables/useG1Adjudication'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// 解构到顶层：composable 返回的 ref/computed 只有作为顶层绑定时才会在模板中自动解包。
// 嵌套访问（adj.rows / adj.trialBalanceAmount）不解包 → el-table 收到 Ref（空表）、
// v-model 绑定到 ref 对象、computed 值读为 undefined（空白）。
const {
  rows,
  totalRow,
  trialBalanceAmount,
  trialBalanceDiff,
  auditNote,
  conclusion,
  updateField,
} = useG1Adjudication({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

function spanInvest({ row, rowIndex, columnIndex }: { row: { investKey: string; rowKey: string }; rowIndex: number; columnIndex: number }) {
  if (columnIndex !== 0) return { rowspan: 1, colspan: 1 }
  const data = rows.value
  if (row.rowKey === 'subtotal') return { rowspan: 1, colspan: 1 }
  const firstIdx = data.findIndex((r) => r.investKey === row.investKey)
  if (firstIdx !== rowIndex) return { rowspan: 0, colspan: 0 }
  const same = data.filter((r) => r.investKey === row.investKey && r.rowKey !== 'subtotal').length
  return { rowspan: same, colspan: 1 }
}
</script>

<style scoped>
.g1-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g1-adjudication :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g1-adjudication :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 12px; }
.subtotal-table { margin-top: -1px; }
.tb-diff-row { display: flex; gap: 24px; margin: 16px 0; align-items: center; }
.diff-red { color: #f56c6c; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa; }
.opinion-card { margin-top: 12px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.opinion-section-label { font-size: 14px; font-weight: 500; color: #303133; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
