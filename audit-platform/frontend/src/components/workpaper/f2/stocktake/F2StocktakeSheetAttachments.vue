<template>
  <div v-if="projectId && wpId" class="f2-st-attachments">
    <span class="label">监盘附件</span>
    <ItemAttachment
      :project-id="projectId"
      :wp-id="wpId"
      :sheet-key="sheetCode"
      :item-index="0"
      accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls,.mp4,.mov"
    />
  </div>
</template>

<script setup lang="ts">
import ItemAttachment from '../../ItemAttachment.vue'

defineProps<{
  projectId?: string
  wpId?: string
  sheetCode: string
}>()
</script>

<style scoped>
.f2-st-attachments { margin: 8px 0 12px; display: flex; align-items: flex-start; gap: 12px; flex-wrap: wrap; }
.label { font-size: 12px; color: #606266; padding-top: 6px; white-space: nowrap; }
</style>
