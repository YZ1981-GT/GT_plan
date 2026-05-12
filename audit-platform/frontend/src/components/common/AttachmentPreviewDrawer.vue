<!--
  AttachmentPreviewDrawer — 附件预览抽屉 [R7-S3-11 Task 54]

  从右侧滑入（480px 宽），替代当前 window.open 新标签预览。
  支持 PDF/图片直接嵌入，Word/Excel 显示下载提示。

  用法：
    <AttachmentPreviewDrawer v-model="showPreview" :attachment="currentAttachment" />
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
    <div v-if="attachment" class="gt-attach-preview">
      <!-- 文件信息 -->
      <div class="gt-attach-preview__meta">
        <span class="gt-attach-preview__name">{{ attachment.name }}</span>
        <OcrStatusBadge v-if="attachment.ocr_status" :status="attachment.ocr_status" />
      </div>

      <!-- PDF 预览 -->
      <iframe
        v-if="isPdf"
        :src="previewUrl"
        class="gt-attach-preview__frame"
      />

      <!-- 图片预览 -->
      <img
        v-else-if="isImage"
        :src="previewUrl"
        class="gt-attach-preview__img"
        :alt="attachment.name"
      />

      <!-- 其他格式：下载提示 -->
      <div v-else class="gt-attach-preview__fallback">
        <el-empty description="该格式暂不支持在线预览">
          <el-button type="primary" @click="onDownload">下载查看</el-button>
        </el-empty>
      </div>

      <!-- OCR 结果（如有） -->
      <div v-if="attachment.ocr_text" class="gt-attach-preview__ocr">
        <h4>OCR 识别结果</h4>
        <pre class="gt-attach-preview__ocr-text">{{ attachment.ocr_text }}</pre>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import OcrStatusBadge from '@/components/common/OcrStatusBadge.vue'

export interface AttachmentForPreview {
  id: string
  name: string
  mime_type?: string
  preview_url?: string
  download_url?: string
  ocr_status?: 'ok' | 'processing' | 'failed' | 'pending'
  ocr_text?: string
}

const props = defineProps<{
  attachment: AttachmentForPreview | null
}>()

const visible = defineModel<boolean>({ default: false })

const isPdf = computed(() => {
  const mime = props.attachment?.mime_type || ''
  const name = props.attachment?.name || ''
  return mime === 'application/pdf' || name.endsWith('.pdf')
})

const isImage = computed(() => {
  const mime = props.attachment?.mime_type || ''
  return mime.startsWith('image/')
})

const previewUrl = computed(() => props.attachment?.preview_url || '')

function onDownload() {
  const url = props.attachment?.download_url
  if (url) window.open(url, '_blank')
}
</script>

<style scoped>
.gt-attach-preview { display: flex; flex-direction: column; gap: var(--gt-space-3); height: 100%; }
.gt-attach-preview__meta { display: flex; align-items: center; gap: 8px; padding-bottom: var(--gt-space-2); border-bottom: 1px solid var(--gt-color-border-light); }
.gt-attach-preview__name { font-weight: 600; font-size: var(--gt-font-size-sm); flex: 1; }
.gt-attach-preview__frame { flex: 1; border: none; border-radius: var(--gt-radius-sm); min-height: 400px; }
.gt-attach-preview__img { max-width: 100%; border-radius: var(--gt-radius-sm); object-fit: contain; }
.gt-attach-preview__fallback { flex: 1; display: flex; align-items: center; justify-content: center; }
.gt-attach-preview__ocr { border-top: 1px solid var(--gt-color-border-light); padding-top: var(--gt-space-3); }
.gt-attach-preview__ocr h4 { margin: 0 0 var(--gt-space-2); font-size: var(--gt-font-size-sm); }
.gt-attach-preview__ocr-text { font-size: var(--gt-font-size-xs); line-height: 1.6; white-space: pre-wrap; max-height: 200px; overflow-y: auto; background: var(--gt-color-bg); padding: var(--gt-space-2); border-radius: var(--gt-radius-sm); }
</style>
