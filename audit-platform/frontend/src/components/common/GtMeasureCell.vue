<template>
  <span
    :class="[
      'gt-measure-cell',
      {
        'text-red-500': props.negativeRed && numericValue < 0
      }
    ]"
    :data-gt-value="dataGtValue"
    :style="{ fontVariantNumeric: 'tabular-nums' }"
  >
    {{ formattedValue }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { MeasureKind, RatioScale, validateRatioScale } from '@/types/measureKind';
import { formatMeasure } from '@/utils/formatMeasure';

export interface GtMeasureCellProps {
  /** 原始值 */
  value: number | string | null | undefined;
  /** 度量类型 */
  kind?: MeasureKind | null;
  /** 比例刻度（仅 ratio 时必须） */
  ratioScale?: RatioScale | null;
  /** 账号小数位（amount 和未登记类型使用） */
  decimals?: number;
  /** 是否显示零值 */
  showZero?: boolean;
  /** 负数是否显示为红色 */
  negativeRed?: boolean;
}

const props = withDefaults(defineProps<GtMeasureCellProps>(), {
  kind: null,
  ratioScale: null,
  decimals: 2,
  showZero: true,
  negativeRed: false
});

// 校验 ratioScale 使用规则
if (import.meta.env.DEV) {
  try {
    validateRatioScale(props.kind, props.ratioScale);
  } catch (error) {
    console.error('[GtMeasureCell] 校验失败:', error);
  }
}

// 格式化后的值
const formattedValue = computed(() => {
  return formatMeasure(props.value, {
    kind: props.kind,
    ratioScale: props.ratioScale,
    decimals: props.decimals,
    showZero: props.showZero,
    negativeRed: props.negativeRed
  });
});

// 数值部分（用于判断正负）
const numericValue = computed(() => {
  if (props.value == null || props.value === '') return 0;
  const num = Number(props.value);
  return isNaN(num) ? 0 : num;
});

/**
 * `data-gt-value` 的**显式字符串化**。
 *
 * 🔴 不能直接绑 `props.value`：`null` / `undefined` 时 Vue 会把该属性整个**移除**，
 * 读取方拿到 `undefined` 而不是空串（`GtMeasureCell.spec.ts` 的「应保存 null 值」
 * 用例因此一直红）。验收脚本按属性是否存在判「这一格有没有被 kind 化」，
 * 属性被移除会让「未登记 kind」与「未渲染」不可区分。
 *
 * 口径：`null`/`undefined` → `''`（保留属性、值为空），其余按原值字符串化
 * （不格式化 —— 该属性是**原始值**证据，与屏幕显示文本是两件事）。
 */
const dataGtValue = computed(() => {
  const raw = props.value;
  if (raw == null) return '';
  return String(raw);
});
</script>

<style scoped>
.gt-measure-cell {
  font-family: var(--gt-font-numeric, inherit);
}
</style>
