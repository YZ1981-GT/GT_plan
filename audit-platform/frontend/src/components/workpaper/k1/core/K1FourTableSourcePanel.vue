<template>
  <WpFourTableSourcePanel
    :source-codes="props.sourceCodes"
    gross-label="其他应收款原值"
    provision-label="坏账准备"
    provision-filter-label="其他应收款"
    :extra-labels="K1_EXTRA_LABELS"
    :hints="K1_HINTS"
    fallback-row-code="BS-009"
  />
</template>

<script setup lang="ts">
/**
 * K1 四表库取数溯源面板 —— 共用面板 `WpFourTableSourcePanel` 的薄壳。
 *
 * 只声明 K1 的报表行 / 口径中文名 / 附加科目名 / 口径提示，展示逻辑全在共用件
 * （K2 起各循环同款接入，禁止再复制一份面板）。
 *
 * spec: .kiro/specs/k1-four-table-extraction-and-disclosure-alignment/ R1.7
 */
import WpFourTableSourcePanel from '../../shared/WpFourTableSourcePanel.vue'
import type { K1TbSourceCodes } from '../../composables/k1TbSourceCodes'

const props = defineProps<{
  sourceCodes?: K1TbSourceCodes | null
}>()

/** 附加科目中文名（报表公式引用但不并入本表第一段） */
const K1_EXTRA_LABELS: Record<string, string> = {
  '1131': '应收股利',
  '1132': '应收利息',
}

const K1_HINTS: string[] = [
  '坏账准备只取「其他应收款」对应的备抵子科目 —— 科目表把各类应收款的坏账分别编在 '
  + '<code>1231.01</code>（应收票据）/<code>1231.02</code>（应收账款）/'
  + '<code>1231.03</code>（其他应收款）等，取整个 <code>1231</code> 会把应收账款的坏账并进来。',
  '余额表按<strong>叶子科目</strong>汇总（无下级明细的最末级），叶子之和等于父科目期末余额。',
  '应收利息 / 应收股利不计入本表第一段，单独用于「与经审计的财务报表核对」区。',
]
</script>
