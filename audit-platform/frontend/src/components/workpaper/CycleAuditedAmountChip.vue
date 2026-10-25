<template>
  <el-popover
    v-if="showAuditedAmounts"
    trigger="hover"
    placement="top"
    :width="300"
    @show="loadAmounts"
  >
    <template #reference>
      <span data-testid="cycle-audited-chip-reference">
        <GtIndexChip
          :value="value"
          :label="label"
          :wp-code="wpCode"
          :target="target"
          :validate="validate"
          :context-project-id="contextProjectId"
          :prevent-navigate="preventNavigate"
          :disabled="disabled"
          :context="context"
          :title="title"
          @click="emit('click', $event)"
        />
      </span>
    </template>

    <div class="cycle-audited-amounts" data-testid="cycle-audited-amounts-popover">
      <div class="cycle-audited-amounts__title">{{ cycleCode }} 外部引用（只读审定/TB）</div>
      <div class="cycle-audited-amounts__source">数据源：cycle_audited_amounts</div>
      <div v-if="loading" class="cycle-audited-amounts__muted">正在读取审定数…</div>
      <div v-else-if="error" class="cycle-audited-amounts__muted">{{ error }}</div>
      <template v-else-if="amounts">
        <div v-for="row in amountRows" :key="row.key" class="cycle-audited-amounts__row">
          <span>{{ row.label }}</span><strong>{{ formatAmount(row.value) }}</strong>
        </div>
        <div v-if="amounts.summary" class="cycle-audited-amounts__summary">{{ amounts.summary }}</div>
      </template>
      <div v-else class="cycle-audited-amounts__muted">暂无审定数</div>
    </div>
  </el-popover>

  <GtIndexChip
    v-else
    :value="value"
    :label="label"
    :wp-code="wpCode"
    :target="target"
    :validate="validate"
    :context-project-id="contextProjectId"
    :prevent-navigate="preventNavigate"
    :disabled="disabled"
    :context="context"
    :title="title"
    @click="emit('click', $event)"
  />
</template>

<script setup lang="ts">
import { computed, toRef } from 'vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import type { ResolvedIndexRef } from '@/utils/parseIndexRef'
import { isCycleExternalRef, type CycleCode } from './composables/cycleCrossRef'
import { useCycleAuditedAmounts } from './composables/useCycleAuditedAmounts'

const props = withDefaults(defineProps<{
  value?: string
  label?: string
  wpCode?: string
  target?: string
  validate?: boolean
  contextProjectId?: string
  preventNavigate?: boolean
  disabled?: boolean
  context?: string
  title?: string
  cycleCode?: CycleCode
  projectId?: string
  year?: number
}>(), { validate: true, preventNavigate: false, disabled: false })

const emit = defineEmits<{ click: [resolved: ResolvedIndexRef] }>()
const referenceValue = computed(() => props.value ?? props.wpCode ?? props.target ?? props.label ?? '')
const showAuditedAmounts = computed(() =>
  !props.disabled && Boolean(props.projectId && props.year) && isCycleExternalRef(referenceValue.value, props.cycleCode),
)
const { amounts, loading, error, load } = useCycleAuditedAmounts(
  toRef(props, 'projectId'),
  toRef(props, 'year'),
)
const amountRows = computed(() => [
  { key: 'asset_total', label: '资产审定数', value: amounts.value?.asset_total ?? null },
  { key: 'liability_total', label: '负债审定数', value: amounts.value?.liability_total ?? null },
  { key: 'equity_total', label: '权益审定数', value: amounts.value?.equity_total ?? null },
  { key: 'revenue_total', label: '收入审定数', value: amounts.value?.revenue_total ?? null },
  { key: 'expense_total', label: '费用审定数', value: amounts.value?.expense_total ?? null },
])

function loadAmounts(): void {
  void load()
}

function formatAmount(value: number | null): string {
  return value == null ? '—' : value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.cycle-audited-amounts { font-size: 12px; line-height: 1.6; color: var(--gt-color-text-primary, #303133); }
.cycle-audited-amounts__title { margin-bottom: 4px; font-weight: 600; }
.cycle-audited-amounts__source { margin-bottom: 4px; color: var(--gt-color-text-secondary, #606266); font-size: 11px; }
.cycle-audited-amounts__row { display: flex; justify-content: space-between; gap: 16px; }
.cycle-audited-amounts__row strong { font-variant-numeric: tabular-nums; }
.cycle-audited-amounts__summary, .cycle-audited-amounts__muted { color: var(--gt-color-text-secondary, #606266); }
.cycle-audited-amounts__summary { margin-top: 4px; border-top: 1px solid var(--gt-color-border-light, #ebeef5); padding-top: 4px; }
</style>
