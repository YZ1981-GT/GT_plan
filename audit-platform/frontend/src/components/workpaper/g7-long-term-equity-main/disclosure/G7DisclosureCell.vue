<!--
  G7 披露表**单元格渲染**（上市 / 国企两个 Tab 共用）。

  抽出来的唯一理由：接两级表头后，列渲染必须分「有父表头（嵌套 el-table-column）」与
  「单级列」两个分支，若把单元格模板在两个分支里各抄一遍，两个 Tab 就会出现 4 份副本，
  日后必然分叉（平台已记过同款：注释与值自相矛盾的 `labelHeader`）。

  🔴 «哪些行算计算行» 与 «计算行显示什么» **由父组件决定**（`mode` / `computedText`）——
  两个 Tab 原本语义不同（国企把 `kind === 'group'` 也当计算行并显示 `—`，上市不含该分支），
  下沉到本组件会造成跨 Tab 行为串味。故本组件只负责「按 mode 渲染」，不自作判断。
-->
<template>
  <span v-if="mode === 'computed'" class="computed-value">{{ computedText }}</span>

  <el-input
    v-else-if="column.type === 'text'"
    :model-value="(row.values[column.key] as string) ?? ''"
    size="small"
    :disabled="readonly"
    @update:model-value="onText"
  />

  <el-input-number
    v-else-if="column.type === 'percent'"
    :model-value="row.values[column.key] as number"
    size="small"
    controls-position="right"
    :precision="4"
    :min="0"
    :max="100"
    :disabled="readonly"
    @update:model-value="onNumber"
  />

  <WpAmountInput
    v-else
    :model-value="row.values[column.key]"
    :disabled="readonly"
    @update:model-value="onNumber"
  />
</template>

<script setup lang="ts">
import WpAmountInput from '@/components/workpaper/shared/WpAmountInput.vue'
import type { G7DisclosureColumn } from './g7SoeDisclosureModel'

interface CellRow {
  values: Record<string, unknown>
  [key: string]: unknown
}

const props = defineProps<{
  row: CellRow
  column: G7DisclosureColumn
  /** `computed` = 只读展示 `computedText`；`editable` = 按 `column.type` 出录入控件。 */
  mode: 'computed' | 'editable'
  /** 计算行要显示的文本（父组件已格式化，含「国企 group 行显示 —」这类差异）。 */
  computedText?: string
  readonly?: boolean
}>()

const emit = defineEmits<{ (e: 'change'): void }>()

/**
 * 🔴 文本列必须走 `update:model-value` 回写，不能只监听 `change`：
 * element-plus 的 `handleInput` 在 `await nextTick()` 后调 `setNativeInputValue()`
 * 把 DOM 值重置回 `modelValue`；只监听 `change` 时 `modelValue` 不随键入更新 ⇒
 * 用户敲进去的字会被抹掉（平台实测证据：N1 互抵明细行名落库为 `label: ""`）。
 */
function onText(value: string): void {
  props.row.values[props.column.key] = value
  emit('change')
}

function onNumber(value: number | null | undefined): void {
  props.row.values[props.column.key] = value ?? undefined
  emit('change')
}
</script>
