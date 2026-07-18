<template>
  <div v-if="projectId && wpId" class="f3-sheet-attachments">
    <span class="label">{{ label }}</span>
    <ItemAttachment
      :project-id="projectId"
      :wp-id="wpId"
      :sheet-key="sheetCode"
      :item-index="0"
      accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls,.doc,.docx"
    />
  </div>
</template>

<script setup lang="ts">
/** F3SheetAttachments — Sheet 级证据归档（比照 F2StocktakeSheetAttachments） */
import ItemAttachment from '../ItemAttachment.vue'

withDefaults(defineProps<{
  projectId?: string
  wpId?: string
  sheetCode: string
  label?: string
}>(), {
  label: '底稿附件',
})
</script>

<style scoped>
.f3-sheet-attachments {
  margin: 8px 0 12px;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}
.label {
  font-size: 12px;
  color: #606266;
  padding-top: 6px;
  white-space: nowrap;
}
</style>
