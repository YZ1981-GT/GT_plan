<script setup lang="ts">
/**
 * WpAmountInput — 底稿可编辑金额输入框（千分符 + 两位小数）
 *
 * **为什么不用 `el-input-number`**：实证 element-plus 2.13.6 的 `input-number`
 * 编译产物中不存在 `formatter` / `parser` prop（`es/components/input-number/**`
 * 全文无 `formatter`），挂 `:formatter="amountFormatter"` 是未知属性、千分符不生效。
 * 要千分符必须用 `el-input` 自行接管显示态与提交态。
 *
 * 行为：
 * - 失焦态显示 `1,234,567.50`（千分符 + 固定两位小数），0 显示 `0.00`
 * - 聚焦态去掉千分符便于键入，失焦时归一并 emit `change`
 * - 只接受数字字符：非法输入回退上一次有效值，不 emit
 *
 * 仅用于「金额」字段。利率 / 汇率 / 比例 / 笔数 / 年度等保留各自 `el-input-number`
 * 与 precision，不要套用本组件。
 */
import { computed, ref, watch } from 'vue'
import { amountFormatter, amountParser } from '../composables/wpAmountInput'

const props = withDefaults(
  defineProps<{
    modelValue?: number | null
    disabled?: boolean
    size?: 'large' | 'default' | 'small'
    placeholder?: string
    /** 无障碍标签（表格内建议传列名+行名） */
    ariaLabel?: string
  }>(),
  { modelValue: 0, disabled: false, size: 'small', placeholder: '', ariaLabel: '' },
)

const emit = defineEmits<{
  (e: 'update:modelValue', v: number): void
  (e: 'change', v: number): void
}>()

const focused = ref(false)
/** 聚焦期间的原始编辑串（不带千分符） */
const draft = ref('')

const numeric = computed(() => {
  const n = Number(props.modelValue)
  return Number.isFinite(n) ? n : 0
})

const display = computed(() =>
  focused.value ? draft.value : amountFormatter(numeric.value),
)

watch(
  () => props.modelValue,
  () => {
    if (!focused.value) draft.value = String(numeric.value)
  },
  { immediate: true },
)

function onFocus(): void {
  draft.value = numeric.value === 0 ? '' : String(numeric.value)
  focused.value = true
}

function onInput(val: string): void {
  draft.value = val
}

function onBlur(): void {
  focused.value = false
  const parsed = Number(amountParser(draft.value).trim())
  // 非法输入 → 回退上一次有效值，不 emit（避免把 NaN 写进底稿）
  if (!Number.isFinite(parsed)) {
    draft.value = String(numeric.value)
    return
  }
  const rounded = Math.round(parsed * 100) / 100
  draft.value = String(rounded)
  if (rounded !== numeric.value) {
    emit('update:modelValue', rounded)
    emit('change', rounded)
  }
}
</script>

<template>
  <el-input
    :model-value="display"
    :disabled="disabled"
    :size="size"
    :placeholder="placeholder"
    :aria-label="ariaLabel || undefined"
    class="wp-amount-input"
    @focus="onFocus"
    @input="onInput"
    @blur="onBlur"
    @keyup.enter="onBlur"
  />
</template>

<style scoped>
.wp-amount-input :deep(.el-input__inner) {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
</style>
