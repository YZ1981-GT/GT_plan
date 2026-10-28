<script setup lang="ts">
/**
 * 凭证检查行的元数据标签（spec voucher-identity-writeback-and-audit-phase 需求 4.8 / 6.3 / 8，design §4）
 *
 * 只读展示行上的 `_gt`：阶段（预审 / 年审 / 阶段未标）、来源（抽凭 / 挂凭 / 手工，可并列）、
 * 配对状态（非配对 / 借贷栏不明；配上的不显示）、预审存续核对状态（任务 17 写入）。
 * 没有 `_gt` 的旧行按「手工」显示（ADR-VK-12）。
 */
import { computed } from 'vue'
import { AUDIT_PHASE_LABEL } from '@/composables/useProjectAuditPhase'
import {
  metaOf,
  SOURCE_LABEL,
  SURVIVAL_LABEL,
  type SurvivalStatus,
} from '../composables/shared/voucherCheckFill'

const props = defineProps<{
  row: unknown
  /** 年审阶段的预审行（只读）：加「只读」提示 */
  locked?: boolean
}>()

const PAIRING_LABEL: Record<string, string> = {
  multi: '非配对',
  large: '非配对（分录过多）',
  unknown_side: '借贷栏不明',
}

const meta = computed(() => metaOf(props.row))
const phaseLabel = computed(() => (meta.value?.ph ? AUDIT_PHASE_LABEL[meta.value.ph] : '阶段未标'))
const sourceLabel = computed(() => {
  const src = meta.value?.src ?? []
  return (src.length ? src : ['manual' as const]).map(s => SOURCE_LABEL[s]).join(' + ')
})
const pairingLabel = computed(() => PAIRING_LABEL[meta.value?.pr ?? ''] ?? null)
const survival = computed(() => {
  const sv = (meta.value?.sv ?? null) as { status?: string; ackAt?: string | null } | null
  const status = sv?.status as SurvivalStatus | undefined
  if (!status || !(status in SURVIVAL_LABEL)) return null
  const acked = !!sv?.ackAt
  return {
    label: `${SURVIVAL_LABEL[status]}${acked && status !== 'unchanged' ? '（已确认）' : ''}`,
    type: status === 'unchanged' ? 'success' : acked ? 'info' : 'danger',
  } as const
})
</script>

<template>
  <span class="gt-voucher-row-meta" data-testid="voucher-row-meta">
    <el-tag
      v-if="meta"
      size="small"
      effect="plain"
      :type="meta.ph === 'preliminary' ? 'warning' : meta.ph === 'final' ? 'primary' : 'info'"
    >{{ phaseLabel }}</el-tag>
    <el-tag size="small" effect="plain" type="info">{{ sourceLabel }}</el-tag>
    <el-tag v-if="pairingLabel" size="small" effect="plain" type="warning">{{ pairingLabel }}</el-tag>
    <el-tag v-if="survival" size="small" effect="plain" :type="survival.type">{{ survival.label }}</el-tag>
    <el-tag v-if="locked" size="small" effect="plain" type="info" title="年审阶段预审行只读">只读</el-tag>
  </span>
</template>

<style scoped>
.gt-voucher-row-meta {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
}
</style>
