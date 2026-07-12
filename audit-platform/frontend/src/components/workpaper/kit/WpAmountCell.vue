<script setup lang="ts">
/**
 * WpAmountCell — 底稿金额单元格组件
 *
 * 金额格式统一走 DisplayPrefs_Store（单位/小数/负数红字/变动高亮）。
 * 内部通过 inject(DisplayPrefs_Key) 获取显示偏好，
 * 若上下文无 provide 则回退到 useDisplayPrefsStore()。
 *
 * Feature: platform-global-hardening
 * Requirements: 4.2, 4.7
 */
import { computed, inject } from 'vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  /** 金额值（元为单位的原始数字），null 表示无数据 */
  value: number | null
  /** 上期/对比值（可选），提供时显示变动指示器 */
  priorValue?: number | null
  /** 覆盖单位转换：为 true 时不做单位换算，直接格式化原始值 */
  rawUnit?: boolean
}>()

// 优先从祖先注入获取 displayPrefs，兜底直接使用 store
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

/** 格式化后的金额文本 */
const formattedValue = computed(() => {
  return displayPrefs.fmtAmount(props.value, { rawUnit: props.rawUnit })
})

/** 金额 CSS 类名（负数红字 + 变动高亮） */
const cellClass = computed(() => {
  return displayPrefs.amountClass(props.value, props.priorValue)
})

/** 变动方向指示器（仅在有 priorValue 时显示） */
const varianceIndicator = computed(() => {
  if (props.priorValue == null || props.value == null) return null
  const current = props.value
  const prior = props.priorValue
  if (current > prior) return '↑'
  if (current < prior) return '↓'
  return null
})
</script>

<template>
  <span class="wp-amount-cell" :class="cellClass">
    <span class="wp-amount-cell__value">{{ formattedValue }}</span>
    <span
      v-if="varianceIndicator"
      class="wp-amount-cell__variance"
      :class="{
        'wp-amount-cell__variance--up': varianceIndicator === '↑',
        'wp-amount-cell__variance--down': varianceIndicator === '↓',
      }"
    >{{ varianceIndicator }}</span>
  </span>
</template>

<style scoped>
.wp-amount-cell {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.wp-amount-cell__value {
  /* 右对齐（标准会计格式） */
  text-align: right;
}

/* 负数红字 */
:deep(.gt-amount--negative) .wp-amount-cell__value,
.wp-amount-cell.gt-amount--negative .wp-amount-cell__value {
  color: var(--el-color-danger, #f56c6c);
}

/* 变动高亮 */
:deep(.gt-amount--highlight) .wp-amount-cell__value,
.wp-amount-cell.gt-amount--highlight .wp-amount-cell__value {
  font-weight: 600;
}

.wp-amount-cell__variance {
  font-size: 0.75em;
  line-height: 1;
}

.wp-amount-cell__variance--up {
  color: var(--el-color-danger, #f56c6c);
}

.wp-amount-cell__variance--down {
  color: var(--el-color-success, #67c23a);
}
</style>
