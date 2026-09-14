<template>
  <el-table :data="rows" border size="small" :row-class-name="rowClass" class="stage-ecl-table">
    <el-table-column label="类　别" min-width="240">
      <template #default="{ row }">
        <span
          :class="{
            'is-total': row.kind === 'total' || row.kind === 'subtotal',
            'is-sub': row.kind === 'data' && row.rowKey !== 'individual-header',
          }"
        >{{ row.label }}</span>
      </template>
    </el-table-column>
    <el-table-column label="账面余额" width="160" align="right">
      <template #default="{ row }">
        <WpAmountInput
          v-if="canEdit(row)"
          :model-value="row.balance"
          size="small"
          style="width: 100%"
          @change="(v: number) => emit('update', row.rowId, 'balance', v ?? 0)"
        />
        <span v-else class="amount-cell">{{ fmt(row.balance) }}</span>
      </template>
    </el-table-column>
    <el-table-column :label="rateLabel" width="180" align="right">
      <template #default="{ row }">
        <el-input-number
          v-if="canEdit(row)"
          :model-value="row.eclRate ?? 0"
          size="small"
          :controls="false"
          :precision="2"
          :min="0"
          :max="100"
          style="width: 100%"
          @change="(v: number) => emit('update', row.rowId, 'eclRate', v ?? 0)"
        />
        <span v-else>{{ row.kind === 'header' ? '—' : formatRate(row.eclRate) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="坏账准备" width="160" align="right">
      <template #default="{ row }">
        <WpAmountInput
          v-if="canEdit(row)"
          :model-value="row.provision"
          size="small"
          style="width: 100%"
          @change="(v: number) => emit('update', row.rowId, 'provision', v ?? 0)"
        />
        <span v-else class="amount-cell">{{ row.kind === 'header' ? '—' : fmt(row.provision) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="账面价值" width="160" align="right">
      <template #default="{ row }">
        <el-tooltip v-if="row.kind !== 'header'" content="公式：账面余额 − 坏账准备" placement="top">
          <span class="formula-cell">{{ fmt(row.bookValue) }}</span>
        </el-tooltip>
        <span v-else>—</span>
      </template>
    </el-table-column>
    <el-table-column label="理由" min-width="180">
      <template #default="{ row }">
        <el-input
          v-if="canEdit(row)"
          :model-value="row.reason"
          size="small"
          placeholder="计提理由 / 阶段划分依据"
          @change="(v: string) => emit('update', row.rowId, 'reason', v)"
        />
        <span v-else>{{ row.reason || '—' }}</span>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * K1StageEclTable.vue — ECL 三阶段坏账准备快照表（上市披露表复用 6 次）
 *
 * 结构对齐源模板「附注披露信息(上市公司）」R32-R39（期末第一阶段）等 6 个同构区块：
 * 类别 | 账面余额 | 预期信用损失率(%) | 坏账准备 | 账面价值 | 理由
 * spec: k1-other-receivable-disclosure-alignment Sprint 4
 */
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { amountFormatter, amountParser } from '../../composables/wpAmountInput'
import type { K1StageEclDisclosureRow } from '../../composables/k1DisclosureModel'

const props = defineProps<{
  rows: K1StageEclDisclosureRow[]
  rateLabel: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  update: [rowId: string, field: 'balance' | 'eclRate' | 'provision' | 'reason', value: string | number]
}>()

const displayPrefs = useDisplayPrefsStore()

function canEdit(row: K1StageEclDisclosureRow): boolean {
  return row.editable && row.kind === 'data' && !props.isReadonly
}

function fmt(v: number | null | undefined): string {
  return displayPrefs.fmtAmount(v)
}

function formatRate(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v) || v === 0) return '—'
  return `${v.toFixed(2)}%`
}

function rowClass({ row }: { row: K1StageEclDisclosureRow }): string {
  if (row.kind === 'total') return 'row-total'
  if (row.kind === 'subtotal') return 'row-subtotal'
  if (row.kind === 'header') return 'row-header'
  return ''
}
</script>

<style scoped>
.stage-ecl-table { margin-bottom: 10px; }
.amount-cell, .formula-cell { font-variant-numeric: tabular-nums; white-space: nowrap; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.is-total { font-weight: 600; }
.is-sub { padding-left: 16px; display: inline-block; }
:deep(.row-total) { font-weight: 600; background: #fafafa; }
:deep(.row-subtotal) { font-weight: 600; background: #f6f9ff; }
:deep(.row-header) { color: var(--el-text-color-secondary); font-weight: 600; }
:deep(.el-table td.is-right .cell) { white-space: nowrap; font-variant-numeric: tabular-nums; }
</style>
