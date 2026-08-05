<template>
  <WpFourTableSourcePanel
    :source-codes="sourceCodes"
    gross-label="应付票据原值"
    :fallback-row-code="F3_REPORT_ROW_CODE"
    :hints="hints"
  />
</template>

<script setup lang="ts">
/**
 * F3FourTableSourcePanel — F3 应付票据四表库取数溯源面板（薄壳）。
 *
 * 委托 `WpFourTableSourcePanel`；无备抵科目不传 `provisionLabel`。
 *
 * spec: f-cycle-four-table-extraction-and-disclosure-completion Task 9.1
 */
import WpFourTableSourcePanel from '../shared/WpFourTableSourcePanel.vue'
import { F3_REPORT_ROW_CODE } from '../composables/f3AccountScope'
import type { TbSourceCodes } from '../composables/shared/tbSourceCodes'

defineProps<{
  sourceCodes?: TbSourceCodes | null
}>()

const hints = [
  '应付票据（2201）为负债类科目，无备抵科目（不计提减值）。',
  '叶子子科目按票据种类归类：银行承兑 / 商业承兑 / 信用证 / 供应链 / 其他。',
]
</script>
