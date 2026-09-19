<template>
  <WpFourTableSourcePanel
    :source-codes="sourceCodes"
    gross-label="应付账款原值"
    :fallback-row-code="F4_REPORT_ROW_CODE"
    :hints="hints"
  />
</template>

<script setup lang="ts">
/**
 * F4FourTableSourcePanel — F4 应付账款四表库取数溯源面板（薄壳）。
 *
 * 委托 `WpFourTableSourcePanel`；无备抵科目不传 `provisionLabel`。
 *
 * spec: f-cycle-four-table-extraction-and-disclosure-completion Task 9.1
 */
import WpFourTableSourcePanel from '../shared/WpFourTableSourcePanel.vue'
import { F4_REPORT_ROW_CODE } from '../composables/f4AccountScope'
import type { TbSourceCodes } from '../composables/shared/tbSourceCodes'

defineProps<{
  sourceCodes?: TbSourceCodes | null
}>()

const hints = [
  '应付账款（2202）为负债类科目，无备抵科目。',
  '叶子子科目按款项性质归类：货款 / 工程款 / 设备款 / 服务费 / 其他。',
  '「暂估应付款」「预提供应商返利」「进项税」「商务系统」等内部核算科目归入「其他」。',
]
</script>
