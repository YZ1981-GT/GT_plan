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
        displayPrefs.amountClass(value, priorValue),
        { 'gt-amount-cell--clickable': clickable },
      ]"
      style="white-space: nowrap"
      @click="handleClick"
    >
      {{ displayPrefs.fmt(value) }}
    </span>
  </CommentTooltip>
</template>

<script setup lang="ts">
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import CommentTooltip from '@/components/common/CommentTooltip.vue'
import type { CellComment } from '@/composables/useCellComments'

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
  font-size: 13px;
  padding: 2px 8px;
  color: #555;
  display: inline-block;
  border-radius: var(--gt-radius-sm, 4px);
  transition: all 0.15s ease;
}

.gt-amount-cell--clickable {
  cursor: pointer;
  color: #333;
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
  color: #d94840 !important;
}

.gt-amount--highlight {
  background: #fff8e1 !important;
  border-radius: 3px;
}
</style>
