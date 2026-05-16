<template>
  <!--
    GtAmountCell — 通用金额单元格组件
    跟随 displayPrefs 格式化 + amountClass 条件格式
    可点击穿透 + hover 高亮 + CommentTooltip 包裹
    CommentTooltip 支持 null/undefined comment，直接渲染 slot，无需 v-if 分支。
    Validates: Requirements R5.6
  -->
  <CommentTooltip :comment="comment">
    <span
      class="gt-amount-cell"
      :class="[
        displayPrefs.amountClass(scaledValue, priorValue),
        { 'gt-amount-cell--clickable': clickable },
      ]"
      style="white-space: nowrap"
      @click="handleClick"
    >
      {{ displayPrefs.fmt(scaledValue) }}
    </span>
  </CommentTooltip>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import CommentTooltip from '@/components/common/CommentTooltip.vue'
import type { CellComment } from '@/composables/useCellComments'
import { AMOUNT_DIVISOR_KEY } from '@/constants/amountDivisor'

const props = withDefaults(
  defineProps<{
    /** 金额值（number | string | null） */
    value: number | string | null | undefined
    /** 是否可点击（穿透查询等） */
    clickable?: boolean
    /** 批注对象（传入则包裹 CommentTooltip，null/undefined 时直接渲染） */
    comment?: CellComment | null
    /** 上期金额（用于变动高亮对比） */
    priorValue?: number | string | null
  }>(),
  {
    clickable: false,
    comment: undefined,
    priorValue: undefined,
  },
)

const emit = defineEmits<{
  click: [value: number | string | null | undefined]
}>()

const displayPrefs = useDisplayPrefsStore()

/** 注入的除数（父组件 provide AMOUNT_DIVISOR_KEY） */
const injectedDivisor = inject(AMOUNT_DIVISOR_KEY, 1) as number | (() => number)
const divisor = computed(() => typeof injectedDivisor === 'function' ? injectedDivisor() : injectedDivisor)

/** 按除数换算后的值（用于显示） */
const scaledValue = computed(() => {
  // 不再做额外除法——displayPrefs.fmt() 已经内置单位换算
  return props.value
})

function handleClick() {
  if (props.clickable) {
    emit('click', props.value)
  }
}
</script>

<style scoped>
.gt-amount-cell {
  font-variant-numeric: tabular-nums;
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-size: var(--gt-font-size-sm);
  padding: 2px 8px;
  color: var(--gt-color-text-regular);
  display: inline-block;
  border-radius: var(--gt-radius-sm, 4px);
  transition: all 0.15s ease;
}

.gt-amount-cell--clickable {
  cursor: pointer;
  color: var(--gt-color-text-primary);
  font-weight: 500;
}

.gt-amount-cell--clickable:hover {
  color: var(--gt-color-primary, #4b2d77);
  background: var(--gt-color-primary-bg, #f4f0fa);
}
</style>

<style>
/* 非 scoped：条件格式类名由 displayPrefs.amountClass() 动态返回 */
.gt-amount--negative {
  color: var(--gt-color-coral) !important;
}

.gt-amount--highlight {
  background: var(--gt-color-wheat-light) !important;
  border-radius: 3px;
}
</style>
