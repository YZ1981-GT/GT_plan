<script setup lang="ts">
import type { BundleAssignee } from './bundleAssignee'

defineProps<{
  tabCode: string
  assignment?: BundleAssignee
}>()
</script>

<template>
  <div
    v-if="assignment"
    class="gt-bundle-assignee"
    :aria-label="`${tabCode} 编制人：${assignment.displayName}`"
  >
    <span class="gt-bundle-assignee__label">编制人</span>
    <strong>{{ assignment.displayName }}</strong>
  </div>
</template>

<style scoped>
.gt-bundle-assignee {
  display: inline-flex;
  align-items: center;
  gap: var(--gt-space-2);
  margin-block-end: var(--gt-space-3);
  color: var(--gt-color-text-secondary);
  font-size: var(--gt-font-size-sm);
}
.gt-bundle-assignee__label { color: var(--gt-color-text-tertiary); }
</style>
