<template>
  <div class="g1-income-calc">
    <div class="section-head">
      <h3 class="sheet-title">G1-5 投资收益测算表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="calc.addRow()">新增测算行</el-button>
        <el-button size="small" :disabled="isReadonly" @click="fillAiDraft">🤖AI辅助</el-button>
        <el-button size="small" @click="openReviewDialog('G1-5-conclusion')">💬复核</el-button>
      </div>
    </div>

    <el-segmented v-model="segment" :options="segmentOptions" size="small" class="segment-bar" />

    <el-table :data="calc.rows.value" border size="small" max-height="500">
      <el-table-column
        v-for="col in currentColumns"
        :key="String(col.prop)"
        :label="col.label"
        :width="col.width"
        :align="col.type === 'number' ? 'right' : 'left'"
        :fixed="col.prop === 'securityName' ? 'left' : undefined"
      >
        <template #default="{ row }">
          <span v-if="col.formula" class="formula-cell" :title="formulaHint(col.prop)">
            {{ fmtNum(row[col.prop]) }}
          </span>
          <el-input-number
            v-else-if="col.type === 'number'"
            v-model="row[col.prop]"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @change="calc.updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
          <el-input
            v-else
            v-model="row[col.prop]"
            size="small"
            :disabled="isReadonly"
            @change="calc.updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="calc.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals">
      <div v-if="segment === 'income'" class="grand-total">
        <span class="subtotal-label">投资收益合计</span>
        应收金额 {{ fmtNum(calc.grandTotal.value.receivableAmount) }} ·
        实收金额 {{ fmtNum(calc.grandTotal.value.receivedAmount) }} ·
        差异 {{ fmtNum(calc.grandTotal.value.incomeDiff) }}
      </div>
      <div v-else class="grand-total">
        <span class="subtotal-label">处置损益合计</span>
        成交金额 {{ fmtNum(calc.grandTotal.value.dealAmount) }} ·
        原始成本 {{ fmtNum(calc.grandTotal.value.originalCost) }} ·
        处置损益 {{ fmtNum(calc.grandTotal.value.realizedGain) }} ·
        净损益 {{ fmtNum(calc.grandTotal.value.netGain) }}
      </div>
    </div>

    <el-card class="conclusion-card" shadow="never">
      <template #header>审计结论</template>
      <el-input v-model="calc.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly" placeholder="对投资收益/处置损益测算的复核结论..." />
    </el-card>

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>应收金额 = 持有数量 × 每股股利（或面值×利率×天数/365）；差异 = 应收 - 实收。</li>
        <li>处置损益 = 成交金额 - 原始成本；净损益 = 处置损益 - 手续费。</li>
        <li>18列拆为2区段：投资收益测算 / 处置损益测算，切换 Tab 时行保持同步。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, inject } from 'vue'
import { useG1IncomeCalc, type G1IncomeCalcRow } from '../../composables/useG1IncomeCalc'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const calc = useG1IncomeCalc({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const segment = ref<'income' | 'disposal'>('income')
const segmentOptions = [
  { label: '投资收益测算', value: 'income' },
  { label: '处置损益测算', value: 'disposal' },
]

const currentColumns = computed(() =>
  segment.value === 'income' ? calc.incomeColumns : calc.disposalColumns,
)

const FORMULA_HINTS: Partial<Record<keyof G1IncomeCalcRow, string>> = {
  receivableAmount: '应收金额 = 持有数量 × 每股股利',
  incomeDiff: '差异 = 应收金额 - 实收金额',
  realizedGain: '处置损益 = 成交金额 - 原始成本',
  netGain: '净损益 = 处置损益 - 手续费',
}

function formulaHint(prop: keyof G1IncomeCalcRow): string {
  return FORMULA_HINTS[prop] ?? ''
}

function fmtNum(v: unknown): string {
  return typeof v === 'number' ? v.toLocaleString() : String(v ?? '')
}

function fillAiDraft() {
  if (props.isReadonly) return
  const t = calc.grandTotal.value
  const draft =
    `经测算，本期投资收益应收金额合计 ${t.receivableAmount.toLocaleString()} 元，` +
    `实收 ${t.receivedAmount.toLocaleString()} 元，差异 ${t.incomeDiff.toLocaleString()} 元；` +
    `处置损益合计 ${t.realizedGain.toLocaleString()} 元，扣除手续费后净损益 ${t.netGain.toLocaleString()} 元。` +
    `测算结果与企业账面确认金额核对一致，投资收益确认恰当。`
  calc.auditConclusion.value = calc.auditConclusion.value ? `${calc.auditConclusion.value}\n${draft}` : draft
}
</script>

<style scoped>
.g1-income-calc { padding: 12px; font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; }
.segment-bar { margin-bottom: 12px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
.conclusion-card { margin-top: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
