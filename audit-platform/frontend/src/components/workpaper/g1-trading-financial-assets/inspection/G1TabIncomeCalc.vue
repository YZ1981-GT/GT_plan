<template>
  <div class="g1-income-calc">
    <div class="section-head">
      <h3 class="sheet-title">G1-5 投资收益测算表</h3>
      <div class="head-actions tab-toolbar">
        <G1ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G1-5"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="calc.addRow()">新增测算行</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-2" /></span>
        <el-tag size="small" type="info">共 {{ calc.rows.value.length }} 行</el-tag>
        <el-button size="small" @click="openReviewDialog('G1-5-conclusion')">💬复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：测算交易性金融资产投资收益（股利/利息）与处置损益，核实应收与实收差异、处置损益及净损益的准确性，确认投资收益确认恰当、完整。"
      class="objective-alert"
    />

    <el-segmented v-model="segment" :options="segmentOptions" size="small" class="segment-bar" />

    <el-table :data="calc.rows.value" border size="small" max-height="500">
      <el-table-column
        v-for="col in currentColumns"
        :key="String(col.prop)"
        :label="col.label"
        :width="col.width"
        :align="col.type === 'number' ? 'right' : 'left'"
        :class-name="col.formula ? 'auto-calc-col' : ''"
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


    <G1AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      :conclusion="calc.auditConclusion.value"
      @update:conclusion="(v: string) => { calc.auditConclusion.value = v }"
      note-ai-section="income-note"
      conclusion-ai-section="income-conclusion"
      note-placeholder="填写审计说明：股利/利息及处置损益测算过程与异常差异。"
      note-hint="覆盖收益测算过程与异常差异。"
    />


    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>应收金额 = 持有数量 × 每股股利（或面值×利率×天数/365）；差异 = 应收 - 实收。</li>
        <li>处置损益 = 成交金额 - 原始成本；净损益 = 处置损益 - 手续费。</li>
        <li>18列拆为2区段：投资收益测算 / 处置损益测算，切换 Tab 时行保持同步。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, inject, watch } from 'vue'
import { useG1IncomeCalc, type G1IncomeCalcRow } from '../../composables/useG1IncomeCalc'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import G1AuditTextCards from '../G1AuditTextCards.vue'
import G1ImportExportDropdown from '../G1ImportExportDropdown.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
}>()

const wpId = computed(() => props.wpId ?? '')

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const calc = useG1IncomeCalc({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const AUDIT_NOTE_KEY = 'G1-5-audit-note'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
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
</script>

<style scoped>
.g1-income-calc { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g1-income-calc :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g1-income-calc :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.sheet-title { margin: 0; font-size: 16px; font-weight: 600; color: #1f2a37; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 12px; }
.stats-bar { margin-bottom: 10px; padding: 8px 12px; background: #f8f9fb; border: 1px solid #ebeef5; border-radius: 6px; font-size: 12px; color: #606266; }
.segment-bar { margin-bottom: 12px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
.conclusion-card { margin-top: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
