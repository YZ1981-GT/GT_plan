<template>
  <el-select
    :model-value="modelValue"
    multiple
    collapse-tags
    collapse-tags-tooltip
    placeholder="按循环过滤"
    size="small"
    style="width: 240px"
    clearable
    @update:model-value="onChange"
  >
    <el-option
      v-for="cycle in availableCycles"
      :key="cycle"
      :label="`${CYCLE_DISPLAY_NAME[cycle] ?? cycle} (${counts[cycle] ?? 0})`"
      :value="cycle"
    >
      <span class="opt-row">
        <span class="opt-dot" :style="{ backgroundColor: cycleColor(cycle) }"></span>
        <span class="opt-name">{{ CYCLE_DISPLAY_NAME[cycle] ?? cycle }}</span>
        <span class="opt-count">({{ counts[cycle] ?? 0 }})</span>
      </span>
    </el-option>
  </el-select>
</template>

<script setup lang="ts">
/**
 * CycleFilter.vue — 循环多选过滤器（Requirements 7.1, 7.4, 7.5, 7.6）
 */
import { computed } from 'vue'
import { CYCLE_DISPLAY_NAME, cycleColor } from './colorMaps'

const props = defineProps<{
  modelValue: string[]
  counts: Record<string, number>
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: string[]): void
}>()

const FULL_ORDER = [
  'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N',
  'A', 'B', 'C', 'S',
  'report', 'note', 'module', 'other',
]

const availableCycles = computed(() =>
  FULL_ORDER.filter(c => (props.counts[c] ?? 0) > 0),
)

function onChange(val: string[]) {
  emit('update:modelValue', val)
}
</script>

<style scoped>
.opt-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.opt-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.opt-name {
  flex: 1;
  font-size: 12px;
}

.opt-count {
  color: #999;
  font-size: 11px;
}
</style>
