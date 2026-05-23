<!--
  AttachmentPreviewDrawer — 附件预览抽屉 [R7-S3-11 Task 54 / AT-2 Office iframe]

  从右侧滑入（480px 宽），替代 window.open 新标签预览。
  支持：
    - PDF / 图片 直接 iframe / img 嵌入
    - Office (doc/docx/xls/xlsx/ppt/pptx) → 后端 LibreOffice 转 PDF iframe（高保真）
    - LibreOffice 不可用（503）→ 友好降级到下载提示
    - 其他格式 → 下载提示

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

      <!-- PDF / Office (转 PDF) 预览 -->
      <iframe
        v-if="isPdf || (isOffice && officeAvailable !== false)"
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

      <!-- Office 但 LibreOffice 不可用 → 友好降级 -->
      <div v-else-if="isOffice && officeAvailable === false" class="gt-attach-preview__fallback">
        <el-empty description="服务器未安装 LibreOffice，Office 在线预览不可用">
          <el-button type="primary" @click="onDownload">下载查看</el-button>
        </el-empty>
      </div>

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
import { computed, ref, watch } from 'vue'
import OcrStatusBadge from '@/components/common/OcrStatusBadge.vue'
import { attachments as P_att, officePreview as P_office } from '@/services/apiPaths'
import { api as httpApi } from '@/services/apiProxy'

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

// 模块级缓存：health 探测结果（避免每次开抽屉都打一次后端）
let officeHealthCache: boolean | null = null

const officeAvailable = ref<boolean | null>(officeHealthCache)

const OFFICE_EXTS = ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp', '.rtf']

function getExt(name: string): string {
  const idx = name.lastIndexOf('.')
  return idx < 0 ? '' : name.slice(idx).toLowerCase()
}

const isPdf = computed(() => {
  const mime = props.attachment?.mime_type || ''
  const name = props.attachment?.name || ''
  return mime === 'application/pdf' || name.endsWith('.pdf')
})

const isImage = computed(() => {
  const mime = props.attachment?.mime_type || ''
  return mime.startsWith('image/')
})

const isOffice = computed(() => {
  const name = props.attachment?.name || ''
  return OFFICE_EXTS.includes(getExt(name))
})

const previewUrl = computed(() => {
  // Office 文件优先走 LibreOffice 转 PDF 端点
  if (isOffice.value && props.attachment?.id) {
    return P_att.previewPdf(props.attachment.id)
  }
  return props.attachment?.preview_url || ''
})

async function probeOfficeHealth() {
  if (officeHealthCache !== null) {
    officeAvailable.value = officeHealthCache
    return
  }
  try {
    const data: any = await httpApi.get(P_office.health)
    officeHealthCache = !!data?.available
    officeAvailable.value = officeHealthCache
  } catch {
    officeHealthCache = false
    officeAvailable.value = false
  }
}

// 抽屉打开时若是 Office 文件，按需探测健康状态
watch(
  () => visible.value && isOffice.value,
  (need) => {
    if (need && officeAvailable.value === null) probeOfficeHealth()
  },
  { immediate: true },
)

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
