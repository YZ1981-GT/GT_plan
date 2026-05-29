<template>
  <!--
    GtAmountCell — 通用金额单元格组件
    内部 Decimal.js 计算（避免 0.1+0.2 浮点误差），展示侧仍用千分位字符串
    跟随 displayPrefs 偏好（单位 / 小数位 / 零值 / 负数红 / 变动阈值）
    可点击穿透 + hover 高亮 + CommentTooltip 包裹（comment 为 null/undefined 时直接渲染 slot）
    Validates: Requirements R5.6 + V3 Req 2（金额 Decimal 化）
  -->
  <CommentTooltip :comment="comment">
    <span
      class="gt-amount-cell"
      :class="[
        cssClass,
        { 'gt-amount-cell--clickable': clickable },
      ]"
      style="white-space: nowrap"
      @click="handleClick"
    >
      {{ formattedDisplay }}
    </span>
  </CommentTooltip>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import Decimal from 'decimal.js'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import CommentTooltip from '@/components/common/CommentTooltip.vue'
import type { CellComment } from '@/composables/useCellComments'
import { AMOUNT_DIVISOR_KEY } from '@/constants/amountDivisor'
import { toDecimal } from '@/utils/decimal'
import { AMOUNT_UNITS } from '@/utils/formatters'

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

/** 注入的除数（父组件 provide AMOUNT_DIVISOR_KEY，预留扩展，本组件未做二次除法） */
const injectedDivisor = inject(AMOUNT_DIVISOR_KEY, 1) as number | (() => number)
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const _divisor = computed(() =>
  typeof injectedDivisor === 'function' ? injectedDivisor() : injectedDivisor,
)

/**
 * 安全地将任意值转为 Decimal；非法值返回 null（不抛异常）。
 * 业务侧大量出现 null/undefined/空字符串/'-' 等"无值"占位，需要静默兜底。
 */
function safeDecimal(v: unknown): Decimal | null {
  if (v === null || v === undefined) return null
  if (typeof v === 'string' && v.trim() === '') return null
  try {
    return toDecimal(v as any, false, '金额')
  } catch {
    return null
  }
}

/**
 * 千分位格式化：保留 Decimal 精度，避免最后一步 Number() 丢精度。
 * 输入：已 quantize 后的 Decimal；输出：'1,234,567.89' / '-1,234.50'
 */
function formatWithSeparator(d: Decimal, decimals: number): string {
  const fixed = d.toFixed(decimals) // Decimal.toFixed 走内部高精度，无浮点误差
  const negative = fixed.startsWith('-')
  const absStr = negative ? fixed.slice(1) : fixed
  const [intPart, decPart] = absStr.split('.')
  const intWithSep = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const body = decPart ? `${intWithSep}.${decPart}` : intWithSep
  return negative ? `-${body}` : body
}

/**
 * Decimal 化展示值：
 * - null/undefined/非法 → '-'
 * - 0 且 showZero=false → '-'（审计惯例）
 * - 否则按 displayPrefs 单位 / 小数位 进行 Decimal 除法 + 四舍五入 + 千分位
 */
const formattedDisplay = computed<string>(() => {
  const d = safeDecimal(props.value)
  if (d === null) return '-'
  if (d.isZero() && !displayPrefs.showZero) return '-'

  const unitCfg = AMOUNT_UNITS[displayPrefs.amountUnit] ?? AMOUNT_UNITS.yuan
  // Decimal 除法替代 n / cfg.divisor 的浮点除法
  const converted = d.dividedBy(unitCfg.divisor)
  const rounded = converted.toDecimalPlaces(displayPrefs.decimals, Decimal.ROUND_HALF_UP)
  return formatWithSeparator(rounded, displayPrefs.decimals)
})

/**
 * Decimal 化条件 CSS 类：
 * - 负数 → 'gt-amount--negative'（受 displayPrefs.negativeRed 控制）
 * - 变动率 |本期-上期|/|上期| ≥ 阈值 → 'gt-amount--highlight'
 * - 上期为 0、本期非 0 → 直接高亮（新增科目）
 */
const cssClass = computed<string>(() => {
  const classes: string[] = []
  const d = safeDecimal(props.value)
  if (d === null) return ''

  if (displayPrefs.negativeRed && d.isNegative()) {
    classes.push('gt-amount--negative')
  }

  const threshold = displayPrefs.highlightThreshold
  if (threshold > 0 && props.priorValue !== null && props.priorValue !== undefined) {
    const prior = safeDecimal(props.priorValue)
    if (prior !== null) {
      if (prior.isZero() && !d.isZero()) {
        classes.push('gt-amount--highlight')
      } else if (!prior.isZero()) {
        // Decimal 化变动率计算，避免 (n - prior) / prior 浮点误差
        const changeRate = d.minus(prior).dividedBy(prior).abs()
        const thresholdD = new Decimal(threshold)
        if (changeRate.greaterThanOrEqualTo(thresholdD)) {
          classes.push('gt-amount--highlight')
        }
      }
    }
  }

  return classes.join(' ')
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
/* 非 scoped：条件格式类名由 cssClass computed 动态返回 */
.gt-amount--negative {
  color: var(--gt-color-coral) !important;
}

.gt-amount--highlight {
  background: var(--gt-color-wheat-light) !important;
  border-radius: 3px;
}
</style>
