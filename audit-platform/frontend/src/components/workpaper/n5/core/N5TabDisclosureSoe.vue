<template>
  <N5DisclosureBody
    class="n5-tab-disclosure-soe"
    v-bind="$props"
    variant="soe"
    @navigate="(s: string) => emit('navigate', s)"
  />
</template>

<script setup lang="ts">
/**
 * N5TabDisclosureSoe — 所得税费用附注披露（国企）
 *
 * 薄壳：实现在 `n5/shared/N5DisclosureBody.vue`。
 *
 * 🔴 本变体源模板 sheet tab 名是 `附注披露信息（国企`（**缺右括号**，A2 单元格才是
 * 完整的 `附注披露信息（国企）`）→ 同步 `sheet_name` 逐字用 tab 名，禁"修正"。
 * 🔴 薄壳必须逐个显式声明并转发 prop（漏 `projectId` = 同步按钮永久锁死）。
 *
 * Spec: `.kiro/specs/n-cycle-tax-disclosure-alignment/`
 */
import N5DisclosureBody from '../shared/N5DisclosureBody.vue'

defineProps<{
  wpId: string
  projectId: string
  allResponses?: Map<string, any>
  isReadonly?: boolean
  year?: number
}>()

const emit = defineEmits<{ (e: 'navigate', sheetName: string): void }>()
</script>
