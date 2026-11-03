<template>
  <span class="gt-att-eye">
    <el-tooltip content="预览" placement="top" :show-after="300">
      <el-button
        class="gt-att-eye__btn"
        link
        type="primary"
        size="small"
        :loading="loading"
        :aria-label="`预览 ${displayName}`"
        data-testid="attachment-eye"
        @click.stop.prevent="open"
      >
        <el-icon><View /></el-icon>
      </el-button>
    </el-tooltip>
    <AttachmentPreviewDrawer
      v-if="mounted"
      v-model="visible"
      :attachment="target"
      downloadable
      size="min(960px, 72vw)"
    />
  </span>
</template>

<script setup lang="ts">
/**
 * AttachmentEyeButton — 底稿内附件的「小眼睛」（spec attachment-inline-preview ADR-AIP-01）
 *
 * 只要附件编号即可：点开时取附件信息（文件名 / 类型 / 识别状态；同时校验附件仍在、本人可见），
 * 识别文本被截断时再取全文；预览抽屉第一次点开才挂载。附件已删除或无权查看 ⇒ 中文提示，不开空预览。
 */
import { computed, ref } from 'vue'
import { View } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { attachments as P_att } from '@/services/apiPaths'
import AttachmentPreviewDrawer, {
  type AttachmentForPreview,
} from '@/components/common/AttachmentPreviewDrawer.vue'
import { toAttachmentPreview } from '@/components/attachment/attachmentPreviewTarget'

const props = withDefaults(
  defineProps<{
    attachmentId: string
    fileName?: string | null
    fileType?: string | null
    ocrStatus?: string | null
  }>(),
  { fileName: null, fileType: null, ocrStatus: null },
)

const loading = ref(false)
const mounted = ref(false)
const visible = ref(false)
const target = ref<AttachmentForPreview | null>(null)

const displayName = computed(() => props.fileName || '附件')

function unwrap(body: any): any {
  if (body && typeof body === 'object' && 'code' in body && 'data' in body) return body.data
  return body
}

function statusOf(err: any): number {
  return Number(err?.response?.status || err?.status || 0)
}

async function open(): Promise<void> {
  if (!props.attachmentId || loading.value) return
  loading.value = true
  try {
    let detail: any
    try {
      const res = await http.get(P_att.detail(props.attachmentId), { _silent: true } as any)
      detail = unwrap(res?.data) || {}
    } catch (err: any) {
      const code = statusOf(err)
      if (code === 404 || code === 403) {
        ElMessage.warning('附件不存在或无权查看')
      } else {
        ElMessage.error('附件信息读取失败，请稍后重试')
      }
      return
    }
    let ocrText: string = detail.ocr_text || ''
    if (detail.ocr_text_truncated) {
      try {
        const full = await http.get(P_att.ocrText(props.attachmentId), { _silent: true } as any)
        ocrText = unwrap(full?.data)?.ocr_text || ocrText
      } catch {
        // 全文取不到时保留预览片段，不影响看原件
      }
    }
    target.value = toAttachmentPreview({
      id: props.attachmentId,
      file_name: detail.file_name || props.fileName,
      file_type: detail.file_type || props.fileType,
      ocr_status: detail.ocr_status || props.ocrStatus,
      ocr_text: ocrText,
    })
    mounted.value = true
    visible.value = true
  } finally {
    loading.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.gt-att-eye {
  display: inline-flex;
  align-items: center;
}
.gt-att-eye__btn {
  padding: 0 2px;
  min-height: auto;
}
</style>
