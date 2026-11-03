<!--
  AttachmentPreviewDrawer — 抽屉形态预览薄壳（el-drawer）
  逻辑全部下沉 AttachmentPreviewCore（variant='server'：preview-pdf iframe + OCR + office health）。
  本文件只负责抽屉容器；AttachmentForPreview 从 core re-export 以保持既有消费方 import 不变。
  可选（spec attachment-inline-preview ADR-AIP-05）：downloadable 显示底部「下载」；size 抽屉宽度（缺省 480px）。
  不传时 DOM 与原先一致。
-->
<template>
  <el-drawer
    v-model="visible"
    title="附件预览"
    direction="rtl"
    :size="size"
    :close-on-click-modal="true"
    append-to-body
  >
    <AttachmentPreviewCore
      v-if="attachment"
      :attachment="attachment"
      :active="visible"
      variant="server"
    />
    <template v-if="downloadable && attachment?.download_url" #footer>
      <el-button
        data-testid="attachment-preview-download"
        :loading="downloading"
        :aria-label="`下载 ${attachment.name}`"
        @click="onDownload"
      >下载</el-button>
      <el-button type="primary" @click="visible = false">关闭</el-button>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import AttachmentPreviewCore, {
  type AttachmentForPreview,
} from '@/components/attachment/preview/AttachmentPreviewCore.vue'
import { downloadFile } from '@/utils/http'
import { handleApiError } from '@/utils/errorHandler'

const props = withDefaults(
  defineProps<{
    attachment: AttachmentForPreview | null
    /** 底部显示「下载」按钮 */
    downloadable?: boolean
    /** 抽屉宽度 */
    size?: string
  }>(),
  { downloadable: false, size: '480px' },
)

const visible = defineModel<boolean>({ default: false })
const downloading = ref(false)

async function onDownload(): Promise<void> {
  const att = props.attachment
  if (!att?.download_url) return
  downloading.value = true
  try {
    await downloadFile(att.download_url, { fileName: att.name || undefined, silent: true })
  } catch (e) {
    handleApiError(e, '下载附件')
  } finally {
    downloading.value = false
  }
}
</script>

<script lang="ts">
export type { AttachmentForPreview } from '@/components/attachment/preview/AttachmentPreviewCore.vue'
</script>
