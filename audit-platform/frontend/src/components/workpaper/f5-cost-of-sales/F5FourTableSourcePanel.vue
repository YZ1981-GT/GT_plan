<template>
  <WpFourTableSourcePanel
    :source-codes="sourceCodes"
    gross-label="营业成本"
    :fallback-row-code="F5_REPORT_ROW_CODE"
    :hints="hints"
  />
</template>

<script setup lang="ts">
/**
 * F5FourTableSourcePanel — F5 营业成本四表库取数溯源面板（薄壳）。
 *
 * 委托 `WpFourTableSourcePanel`；损益类无备抵科目。
 *
 * spec: f-cycle-four-table-extraction-and-disclosure-completion Task 9.1
 */
import WpFourTableSourcePanel from '../shared/WpFourTableSourcePanel.vue'
import { F5_REPORT_ROW_CODE } from '../composables/f5AccountScope'
import type { TbSourceCodes } from '../composables/shared/tbSourceCodes'

defineProps<{
  sourceCodes?: TbSourceCodes | null
}>()

const hints = [
  '营业成本（报表行 IS-002）= SUM_TB(6401~6499, 本期发生额)，覆盖主营业务成本 + 其他业务成本。',
  '损益类取叶子 debit_amount 之和（含年末结转损益的全年账下 debit−credit 恒为 0）。',
  '科目编码在项目间有冲突（6402 既可能是其他业务成本也可能是其他业务支出），按名称归类。',
]
</script>
