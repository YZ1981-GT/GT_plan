<template>
  <div class="gt-ledger-window-pager" role="navigation" aria-label="账簿窗口翻页">
    <span class="gt-ledger-window-pager__range">{{ rangeText }}</span>
    <el-button size="small" :disabled="loading || !hasPrevious" @click="$emit('previous')">上一页</el-button>
    <el-button size="small" :disabled="loading || !hasNext" @click="$emit('next')">下一页</el-button>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  rangeText: string
  hasPrevious: boolean
  hasNext: boolean
  loading?: boolean
}>()
defineEmits<{ previous: []; next: [] }>()
</script>

<style scoped>
.gt-ledger-window-pager {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
.gt-ledger-window-pager__range {
  color: var(--gt-color-text-secondary);
  font-size: var(--gt-font-size-sm);
  font-variant-numeric: tabular-nums;
}
</style>
