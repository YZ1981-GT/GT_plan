<template>
  <N5DisclosureBody
    class="n5-tab-disclosure-listed"
    v-bind="$props"
    variant="listed"
    @navigate="(s: string) => emit('navigate', s)"
  />
</template>

<script setup lang="ts">
/**
 * N5TabDisclosureListed — 所得税费用附注披露（上市公司）
 *
 * 薄壳：实现在 `n5/shared/N5DisclosureBody.vue`（两变体列结构与交互完全相同，
 * 只有章节号 / sheet 名 / 表名 / 行骨架 / 表（2）标题括注不同）。
 *
 * 🔴 **薄壳必须逐个显式声明并转发 prop**：`v-bind="$props"` 只转发已声明的 prop，
 * 漏 `projectId` 会让同步按钮永久 disabled（G9 实测过的静默锁死）。此处显式列出。
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
