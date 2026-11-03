<script setup lang="ts">
/**
 * 宿主凭证检查表的「来源」列（spec voucher-identity-writeback-and-audit-phase 需求 4.8，任务 10~13）
 *
 * 一列放下：阶段 / 来源 / 配对状态 / 存续核对标签（VoucherRowMetaTag），配不上的行再给「多科目」入口看整张凭证
 * （VoucherPairingCell）。宿主的对方科目列多半是可编辑输入框，不替换它，入口放在这一列。
 */
import { computed } from 'vue'
import VoucherRowMetaTag from './VoucherRowMetaTag.vue'
import VoucherPairingCell from './VoucherPairingCell.vue'
import VoucherEvidenceTag from './VoucherEvidenceTag.vue'
import { metaOf, MULTI_ACCOUNT } from '../composables/shared/voucherCheckFill'

const props = defineProps<{
  row: unknown
  /** 年审阶段的预审行（只读） */
  locked?: boolean
  projectId: string
  /** 审计年度（看整张凭证时兜底；行上凭证键带年度时以键为准）；项目没填审计年度为 null */
  year?: number | null
  /** 本行科目：分录过多的凭证跳序时账时定位用 */
  accountCode?: string | null
}>()

const multi = computed(() => {
  const pr = metaOf(props.row)?.pr
  return pr === 'multi' || pr === 'large'
})
</script>

<template>
  <span class="gt-voucher-row-meta-cell">
    <VoucherRowMetaTag :row="row" :locked="locked" />
    <VoucherPairingCell
      v-if="multi"
      :row="row"
      :account="MULTI_ACCOUNT"
      :project-id="projectId"
      :year="year"
      :account-code="accountCode"
    />
    <!-- 凭证证据：本底稿份数、他稿提示与引用（spec attachment-voucher-evidence-binding 需求 3） -->
    <VoucherEvidenceTag :row="row" :project-id="projectId" :locked="locked" />
  </span>
</template>

<style scoped>
.gt-voucher-row-meta-cell {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
</style>
