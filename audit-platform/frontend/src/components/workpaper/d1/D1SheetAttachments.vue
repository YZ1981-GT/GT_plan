<template>
  <div v-if="projectId && wpId" class="d1-sheet-attachments">
    <span class="label">📎 {{ label }}</span>
    <ItemAttachment
      :project-id="projectId"
      :wp-id="wpId"
      :sheet-key="sheetKey"
      :item-index="0"
      accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls,.doc,.docx"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * D1SheetAttachments — D1 披露表子节级证据归档
 *
 * 直接复用平台既有 `ItemAttachment`（比照 F1/F3/F4/F5SheetAttachments），
 * **不新建上传后端**：走 `/api/projects/{id}/attachments/upload` +
 * `/api/working-papers/{wp_id}/attachments` 既有通道。
 *
 * 用在需要证据支撑的披露项：核销（履行的核销程序）、质押、背书贴现。
 *
 * spec: .kiro/specs/d1-notes-receivable-disclosure-alignment/ R11
 */
import ItemAttachment from '../ItemAttachment.vue'

withDefaults(defineProps<{
  projectId?: string
  wpId?: string
  /** 附件归属键：`D1-disc-{variant}-{sectionKey}`，保证两版与各子节互不串档 */
  sheetKey: string
  label?: string
}>(), {
  label: '证据附件',
})
</script>

<style scoped>
.d1-sheet-attachments {
  margin: 8px 0 4px;
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
