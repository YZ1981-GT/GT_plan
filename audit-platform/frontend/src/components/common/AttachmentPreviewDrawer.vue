<!--
  AttachmentPreviewDrawer — 抽屉形态预览薄壳（el-drawer）
  逻辑全部下沉 AttachmentPreviewCore（variant='server'：preview-pdf iframe + OCR + office health）。
  本文件只负责抽屉容器；AttachmentForPreview 从 core re-export 以保持既有消费方 import 不变。
-->
<template>
  <el-drawer
    v-model="visible"
    title="附件预览"
    direction="rtl"
    size="480px"
    :close-on-click-modal="true"
    append-to-body
  >
    <AttachmentPreviewCore
      v-if="attachment"
      :attachment="attachment"
      :active="visible"
      variant="server"
    />
  </el-drawer>
</template>

<script setup lang="ts">
import AttachmentPreviewCore, {
  type AttachmentForPreview,
} from '@/components/attachment/preview/AttachmentPreviewCore.vue'

defineProps<{
  attachment: AttachmentForPreview | null
}>()

const visible = defineModel<boolean>({ default: false })
</script>

<script lang="ts">
export type { AttachmentForPreview } from '@/components/attachment/preview/AttachmentPreviewCore.vue'
</script>
