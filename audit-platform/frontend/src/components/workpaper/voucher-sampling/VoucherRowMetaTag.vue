<script setup lang="ts">
/**
 * 凭证检查行的元数据标签（spec voucher-identity-writeback-and-audit-phase 需求 4.8 / 6.3 / 8，design §4）
 *
 * 只读展示行上的 `_gt`：阶段（预审 / 年审 / 阶段未标）、来源（抽凭 / 挂凭 / 手工，可并列）、
 * 配对状态（非配对 / 借贷栏不明；配上的不显示）、预审存续核对状态（任务 17 写入）。
 * 没有 `_gt` 的旧行按「手工」显示（ADR-VK-12）。
 */
import { computed, hasInjectionContext, inject, ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useAuthStore } from '@/stores/auth'
import { WorkpaperRuntimeContextKey } from '../composables/useWorkpaperScaffold'
import {
  acknowledgeVoucherSurvivalRow,
  notifyVoucherSurvivalRowsChanged,
} from '../composables/shared/voucherSurvivalRegistry'
import { AUDIT_PHASE, AUDIT_PHASE_LABEL } from '@/composables/useProjectAuditPhase'
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

const runtime = hasInjectionContext() ? inject(WorkpaperRuntimeContextKey, null) : null
const auth = useAuthStore()
const acknowledging = ref(false)

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
  const sv = (meta.value?.sv ?? null) as {
    status?: string
    datasetId?: string
    checkId?: string
    detail?: string
    ackAt?: string | null
  } | null
  const status = sv?.status as SurvivalStatus | undefined
  if (!status || !(status in SURVIVAL_LABEL)) return null
  const acked = !!sv?.ackAt
  return {
    status,
    label: `${SURVIVAL_LABEL[status]}${acked && status !== 'unchanged' ? '（已确认）' : ''}`,
    type: status === 'unchanged' ? 'success' : acked ? 'info' : 'danger',
    detail: sv?.detail ?? '',
    canAck: status !== 'unchanged' && !acked && !!sv?.checkId && !!sv?.datasetId
      && !!runtime?.wpId.value && !!runtime?.projectId.value && !runtime?.readonly?.value,
  } as const
})

async function acknowledge(): Promise<void> {
  const item = survival.value
  const lfp = meta.value?.lfp
  if (!item?.canAck || !lfp || !runtime || acknowledging.value || !auth.userId) return
  acknowledging.value = true
  const ackAt = new Date().toISOString()
  try {
    // 先持久化行元数据，再更新汇总：后一步失败只会让项目概览保守地多报未确认，不会少报。
    const projection = await acknowledgeVoucherSurvivalRow(runtime.wpId.value, lfp, auth.userId, ackAt)
    if (!projection) throw new Error('未找到该行的存续核对上下文')
    try {
      await http.patch(`/api/projects/${runtime.projectId.value}/sampling/interim-survival/${projection.checkId}`, {
        wp_id: runtime.wpId.value, dataset_id: projection.datasetId, unacked: projection.unacked,
      }, { _silent: true } as any)
      notifyVoucherSurvivalRowsChanged() // PATCH 已完成，再让底稿横幅回读服务端汇总
      ElMessage.success('已确认该预审样本的存续变化')
    } catch {
      ElMessage.warning('行内确认已保存；项目抽样概览暂未同步，重新核对后会自动校正')
    }
  } catch {
    ElMessage.error('存续核对确认保存失败，请重试')
  } finally {
    acknowledging.value = false
  }
}
</script>

<template>
  <span class="gt-voucher-row-meta" data-testid="voucher-row-meta">
    <el-tag
      v-if="meta"
      size="small"
      effect="plain"
      :type="meta.ph === AUDIT_PHASE.preliminary ? 'warning' : meta.ph === AUDIT_PHASE.final ? 'primary' : 'info'"
    >{{ phaseLabel }}</el-tag>
    <el-tag size="small" effect="plain" type="info">{{ sourceLabel }}</el-tag>
    <el-tag v-if="pairingLabel" size="small" effect="plain" type="warning">{{ pairingLabel }}</el-tag>
    <el-tag
      v-if="survival"
      size="small"
      effect="plain"
      :type="survival.type"
      :title="survival.detail"
    >{{ survival.label }}</el-tag>
    <el-button
      v-if="survival?.canAck"
      link
      type="danger"
      size="small"
      :loading="acknowledging"
      data-testid="ack-voucher-survival"
      @click.stop="acknowledge"
    >确认变化</el-button>
    <el-tag v-if="locked" size="small" effect="plain" type="info" title="年审阶段预审行只读">只读</el-tag>
  </span>
</template>

<style scoped>
.gt-voucher-row-meta {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--gt-space-1);
}
</style>
