<!--
  AttachmentPreview — 弹窗形态预览薄壳（el-dialog）
  逻辑全部下沉 AttachmentPreviewCore（variant='client'）；本文件只负责弹窗容器与对外 props 契约。
-->
<template>
  <el-dialog append-to-body
    v-model="visible"
    :title="fileName"
    width="80%"
    top="5vh"
    destroy-on-close
    @close="$emit('close')"
  >
    <AttachmentPreviewCore
      :attachment="coreAttachment"
      :active="visible"
      variant="client"
    />

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button @click="download">下载</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { downloadFile } from '@/utils/http'
import AttachmentPreviewCore, {
  type AttachmentForPreview,
} from '@/components/attachment/preview/AttachmentPreviewCore.vue'

const props = defineProps<{
  modelValue: boolean
  fileUrl: string
  fileName: string
  fileType?: string
  /** 新增三类显式通道 */
  attachmentId?: string
  downloadUrl?: string
  typeHint?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'close'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const resolvedDownloadUrl = computed(
  () => props.downloadUrl || props.fileUrl.replace('/preview', '/download'),
)

/** 把弹窗壳的扁平 props 映射为 core 统一附件描述 */
const coreAttachment = computed<AttachmentForPreview | null>(() => {
  if (!props.fileName && !props.fileUrl && !props.attachmentId) return null
  return {
    id: props.attachmentId || '',
    name: props.fileName,
    type_hint: props.typeHint || props.fileType,
    preview_url: props.fileUrl,
    download_url: resolvedDownloadUrl.value,
  }
})

async function download() {
  await downloadFile(resolvedDownloadUrl.value)
}
</script>
