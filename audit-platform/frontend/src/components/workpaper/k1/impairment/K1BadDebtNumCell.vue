<template>
  <el-input-number
    v-if="editable"
    :model-value="value"
    :controls="false"
    size="small"
    class="num-cell-input"
    @update:model-value="(v: number) => emit('change', v ?? 0)"
  />
  <span v-else class="num-cell-read">{{ fmt(value) }}</span>
</template>

<script setup lang="ts">
defineProps<{
  value: number
  editable: boolean
}>()

const emit = defineEmits<{ (e: 'change', v: number): void }>()

function fmt(val: number): string {
  if (!Number.isFinite(val)) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.num-cell-input { width: 100%; }
.num-cell-read { font-variant-numeric: tabular-nums; }
</style>
