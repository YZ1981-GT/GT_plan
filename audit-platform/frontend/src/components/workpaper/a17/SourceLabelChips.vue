<script setup lang="ts">
/**
 * SourceLabelChips — source_label 区域按 + 分割后各段独立渲染为 RefChip
 *
 * Requirements: 2.4
 */
import { computed } from 'vue'
import { parseSourceLabel } from '@/composables/useWpCodeParser'
import type { WpCodeNavState } from '@/composables/useA17Navigation'
import RefChipInline from './RefChipInline.vue'

const props = defineProps<{
  sourceLabel: string
  navStateMap: Record<string, WpCodeNavState>
  projectId: string
}>()

const chips = computed(() => {
  if (!props.sourceLabel) return []
  const segments = parseSourceLabel(props.sourceLabel)
  return segments.map((seg) => {
    const trimmed = seg.trim()
    const navState = props.navStateMap[trimmed] || {
      exists: false,
      wpId: null,
      disabled: true,
      tooltip: '该底稿在当前项目中不存在',
    }
    return { code: trimmed, navState }
  })
})
</script>

<template>
  <span v-if="chips.length" class="source-label-chips">
    <span class="source-label-chips__label">来源：</span>
    <template v-for="(chip, idx) in chips" :key="idx">
      <RefChipInline
        :wp-code="chip.code"
        :disabled="chip.navState.disabled"
        :tooltip="chip.navState.tooltip"
        :project-id="projectId"
        :wp-id="chip.navState.wpId ?? undefined"
      />
      <span v-if="idx < chips.length - 1" class="source-label-chips__sep">+</span>
    </template>
  </span>
</template>

<style scoped>
.source-label-chips {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex-wrap: wrap;
}
.source-label-chips__label {
  font-size: 12px;
  color: var(--gt-color-text-secondary, #606266);
  margin-right: 4px;
}
.source-label-chips__sep {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
  margin: 0 2px;
}
</style>
