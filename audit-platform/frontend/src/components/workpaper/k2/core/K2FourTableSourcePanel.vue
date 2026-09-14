<template>
  <WpFourTableSourcePanel
    :source-codes="props.sourceCodes"
    gross-label="其他流动资产"
    :extra-labels="K2_EXTRA_LABELS"
    :hints="K2_HINTS"
    fallback-row-code="BS-014"
  />
</template>

<script setup lang="ts">
/**
 * K2 四表库取数溯源面板 —— 共用面板 `WpFourTableSourcePanel` 的薄壳。
 *
 * 其他流动资产**无备抵科目** → 不传 `provisionLabel`，面板自动隐藏备抵行与 tag。
 *
 * spec: .kiro/specs/k2-four-table-extraction-and-dynamic-rows/ Task 2.2
 */
import WpFourTableSourcePanel from '../../shared/WpFourTableSourcePanel.vue'
import type { TbSourceCodes } from '../../composables/shared/tbSourceCodes'

const props = defineProps<{
  sourceCodes?: TbSourceCodes | null
}>()

/** 附加科目中文名（报表公式引用但不并入其他流动资产原值） */
const K2_EXTRA_LABELS: Record<string, string> = {
  '1131': '应收股利（单列，不并入）',
}

const K2_HINTS: string[] = [
  '科目由报表行 <code>BS-014 其他流动资产</code> 的映射规则解析得出 —— '
  + '实证四个准则的公式均为 <code>TB(\'1901\',\'期末余额\')</code>（上市个别报表另加 '
  + '<code>TB(\'1131\')</code>）。',
  '🔴 历史实现误把 <code>1231</code> 当其他流动资产，但 <code>1231</code> 是'
  + '<strong>应收款项的坏账准备</strong>（贷方备抵），与本科目无关，且会与 D1/D2/K1 重复计入。',
  '<code>1131 应收股利</code>已被报表行 <code>BS-009 其他应收款</code>（K1 循环）占用，'
  + '故在本表<strong>单列不并入</strong>原值。',
  '余额表按<strong>叶子科目</strong>汇总（无下级明细的最末级），叶子之和等于父科目期末余额。',
]
</script>
