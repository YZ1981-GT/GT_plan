<template>
  <el-autocomplete
    v-model="query"
    :fetch-suggestions="fetchSuggestions"
    placeholder="搜索 wp_code / 名称"
    size="small"
    style="width: 220px"
    clearable
    @select="onSelect"
  >
    <template #default="{ item }">
      <span class="sl-row">
        <span class="sl-dot" :style="{ backgroundColor: cycleColor(item.cycle) }"></span>
        <span class="sl-code">{{ item.wp_code }}</span>
        <span v-if="item.label && item.label !== item.wp_code" class="sl-label">{{ item.label }}</span>
        <span class="sl-cycle">{{ item.cycle }}</span>
      </span>
    </template>
  </el-autocomplete>
</template>

<script setup lang="ts">
/**
 * SearchLocator.vue — 节点搜索定位（Requirements 6.3, 6.4）
 */
import { ref } from 'vue'
import type { D3Node } from '@/composables/usePanoramaGraph'
import { cycleColor } from './colorMaps'

const props = defineProps<{
  /** 搜索函数（usePanoramaGraph.searchNodes） */
  searchFn: (q: string) => D3Node[]
}>()

const emit = defineEmits<{
  (e: 'locate', nodeId: string): void
}>()

const query = ref('')

interface Suggestion {
  value: string
  wp_code: string
  cycle: string
  label: string
  id: string
}

function fetchSuggestions(q: string, cb: (results: Suggestion[]) => void) {
  const matches = props.searchFn(q).slice(0, 20)
  cb(
    matches.map(n => ({
      value: n.wp_code,
      wp_code: n.wp_code,
      cycle: n.cycle,
      label: n.label,
      id: n.id,
    })),
  )
}

function onSelect(item: Suggestion) {
  emit('locate', item.id)
  query.value = ''
}
</script>

<style scoped>
.sl-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.sl-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.sl-code {
  font-weight: 600;
  color: #333;
}

.sl-label {
  color: #666;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sl-cycle {
  color: #999;
  font-size: 11px;
  background: #f0f0f0;
  padding: 1px 6px;
  border-radius: 8px;
}
</style>
