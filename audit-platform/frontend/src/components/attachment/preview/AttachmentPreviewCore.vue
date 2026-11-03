<!--
  AttachmentPreviewCore — 附件预览唯一逻辑宿主（单一预览宿主）
  收敛自原 extension/AttachmentPreview.vue（弹窗）与 common/AttachmentPreviewDrawer.vue（抽屉）。
  容器形态（el-dialog / el-drawer）由外层薄壳负责，本组件只负责：
    - familyVerdict 判定（共享 Format_Registry 单一真源）
    - 新增三类（archive/email/dxf）→ ExtendedFormatPreview 分发
    - legacy 渲染：variant='client' 走 vue-office 客户端渲染 blob；variant='server' 走 preview-pdf iframe
    - OCR 徽标/文本、Office 健康探测（仅 server variant）
    - unsupported / CAD 文案与下载入口
  两种 variant 的 legacy DOM/文案/URL 与收敛前各宿主逐项一致（Req 5.1 零回归）。
-->
<template>
  <div class="gt-apc" :class="`gt-apc--${variant}`">
    <div v-if="variant === 'server' && attachment" class="gt-attach-preview__meta">
      <span class="gt-attach-preview__name">{{ attachment.name }}</span>
      <OcrStatusBadge v-if="attachment.ocr_status" :status="attachment.ocr_status" />
    </div>

    <div class="gt-apc__stage" v-loading="variant === 'client' && loading && !isExtended">
      <!-- 新增三类：两 variant 完全一致 -->
      <ExtendedFormatPreview
        v-if="active && isExtended && attachmentId && downloadUrl"
        :attachment-id="attachmentId"
        :download-url="downloadUrl"
        :file-name="fileName"
        :type-hint="effectiveTypeHint"
        @download="onDownload"
      />

      <!-- ── legacy: 客户端 vue-office（原 Preview_Host 弹窗）── -->
      <template v-else-if="variant === 'client'">
        <el-empty
          v-if="clientStateText && !officeLoadError"
          :description="clientStateText"
          :image-size="80"
        >
          <el-button type="primary" @click="onDownload">下载文件</el-button>
        </el-empty>
        <el-empty
          v-else-if="officeLoadError && isOfficeClient"
          description="预览组件加载失败，请下载文件后查看"
          :image-size="80"
        >
          <el-button type="primary" @click="onDownload">下载文件</el-button>
        </el-empty>
        <vue-office-docx
          v-else-if="isDocx && previewSrc"
          :src="previewSrc"
          @rendered="onRendered"
          @error="onError"
          class="gt-preview-content"
        />
        <vue-office-excel
          v-else-if="isExcel && previewSrc"
          :src="previewSrc"
          @rendered="onRendered"
          @error="onError"
          class="gt-preview-content"
        />
        <vue-office-pdf
          v-else-if="isPdfClient && previewSrc"
          :src="previewSrc"
          @rendered="onRendered"
          @error="onError"
          class="gt-preview-content"
        />
        <el-image
          v-else-if="isImageClient && previewSrc"
          :src="previewSrc"
          fit="contain"
          class="gt-preview-image"
          :alt="fileName"
          @load="loading = false"
        />
        <div v-else-if="loading && !isExtended" class="gt-preview-loading-placeholder" />
        <el-empty v-else :description="unsupportedCopy" :image-size="80">
          <el-button type="primary" @click="onDownload">下载文件</el-button>
        </el-empty>
      </template>

      <!-- ── legacy: 服务端 preview-pdf iframe（原 Drawer_Host 抽屉）── -->
      <template v-else>
        <iframe
          v-if="(isPdfServer || (isOfficeServer && officeAvailable !== false)) && serverObjectUrl"
          :src="serverObjectUrl"
          class="gt-attach-preview__frame"
          :title="`预览：${fileName || '原件'}`"
        />
        <img
          v-else-if="isImageServer && serverObjectUrl"
          :src="serverObjectUrl"
          class="gt-attach-preview__img"
          :alt="attachment?.name"
        />
        <div v-else-if="isOfficeServer && officeAvailable === false" class="gt-attach-preview__fallback">
          <el-empty description="服务器未安装 LibreOffice，Office 在线预览不可用">
            <el-button type="primary" @click="onDownload">下载查看</el-button>
          </el-empty>
        </div>
        <div v-else-if="serverWantsInline" v-loading="serverState === 'loading'" class="gt-attach-preview__fallback">
          <el-empty :description="serverStateText">
            <el-button type="primary" @click="onDownload">下载查看</el-button>
          </el-empty>
        </div>
        <div v-else class="gt-attach-preview__fallback">
          <el-empty :description="unsupportedCopy">
            <el-button type="primary" @click="onDownload">下载查看</el-button>
          </el-empty>
        </div>
      </template>
    </div>

    <div v-if="variant === 'server' && attachment?.ocr_text" class="gt-attach-preview__ocr">
      <h4>OCR 识别结果</h4>
      <pre class="gt-attach-preview__ocr-text">{{ attachment.ocr_text }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, defineComponent, ref, watch } from 'vue'
import '@vue-office/docx/lib/index.css'
import '@vue-office/excel/lib/index.css'
import OcrStatusBadge from '@/components/common/OcrStatusBadge.vue'
import ExtendedFormatPreview from '@/components/attachment/preview/ExtendedFormatPreview.vue'
import {
  LEGACY_CAPABILITIES,
  isExtendedFamily,
  resolvePreviewFamily,
} from '@/components/attachment/preview/attachmentPreviewFormats'
import { attachments as P_att, officePreview as P_office } from '@/services/apiPaths'
import { api } from '@/services/apiProxy'
import { downloadFile } from '@/utils/http'
import { authedObjectUrlFailureText, useAuthedObjectUrl } from '@/composables/useAuthedObjectUrl'

// 任一客户端 Office 预览首次命中时加载共享重块；失败重试一次，再显示中文下载降级。
const officeLoadError = ref(false)
const OfficePreviewUnavailable = defineComponent({ name: 'OfficePreviewUnavailable', render: () => null })
function lazyOffice(loader: () => Promise<any>) {
  return defineAsyncComponent(async () => {
    try {
      return await loader()
    } catch {
      try {
        return await loader()
      } catch {
        officeLoadError.value = true
        loading.value = false
        return OfficePreviewUnavailable
      }
    }
  })
}
const VueOfficeDocx = lazyOffice(() => import('@vue-office/docx'))
const VueOfficeExcel = lazyOffice(() => import('@vue-office/excel'))
const VueOfficePdf = lazyOffice(() => import('@vue-office/pdf'))

/** 单一预览宿主统一附件描述 */
export interface AttachmentForPreview {
  id: string
  name: string
  type_hint?: string
  preview_url?: string
  download_url?: string
  ocr_status?: 'ok' | 'processing' | 'failed' | 'pending'
  ocr_text?: string
}

const props = defineProps<{
  /** 统一附件描述；null 时不渲染 */
  attachment: AttachmentForPreview | null
  /** 是否处于激活态（外层容器 visible）——用于门控 ExtendedFormatPreview 释放资源 */
  active: boolean
  /** legacy 渲染方式：client=vue-office 客户端；server=preview-pdf iframe */
  variant: 'client' | 'server'
}>()

const emit = defineEmits<{
  (e: 'download'): void
}>()

const loading = ref(true)

const attachmentId = computed(() => props.attachment?.id || '')
const downloadUrl = computed(() => props.attachment?.download_url || '')
const fileName = computed(() => props.attachment?.name || '')
const effectiveTypeHint = computed(() => props.attachment?.type_hint)

const familyVerdict = computed(() =>
  resolvePreviewFamily(props.attachment?.name || '', props.attachment?.type_hint),
)
const isExtended = computed(() => isExtendedFamily(familyVerdict.value.family))

const unsupportedCopy = computed(() => {
  if (familyVerdict.value.advice === 'cad_download_only') {
    return props.variant === 'server'
      ? 'DWG 图纸请下载后用 CAD 软件打开'
      : 'DWG 图纸请下载后用 CAD 软件打开'
  }
  return props.variant === 'server' ? '该格式暂不支持在线预览' : '暂不支持预览此格式，请下载后查看'
})

// ─────────── client variant（原 Preview_Host 弹窗，按扩展名/分类词判定）───────────
const normalizedFileType = computed(() => (props.attachment?.type_hint || '').toLowerCase())
const ext = computed(() => {
  if (
    normalizedFileType.value &&
    !(LEGACY_CAPABILITIES.previewHost.categoryHints as readonly string[]).includes(normalizedFileType.value)
  ) {
    return normalizedFileType.value
  }
  const name = props.attachment?.name || ''
  const dot = name.lastIndexOf('.')
  return dot >= 0 ? name.slice(dot + 1).toLowerCase() : ''
})
const isDocx = computed(
  () =>
    normalizedFileType.value === 'word' ||
    (LEGACY_CAPABILITIES.previewHost.word as readonly string[]).includes(ext.value),
)
const isExcel = computed(
  () =>
    normalizedFileType.value === 'excel' ||
    (LEGACY_CAPABILITIES.previewHost.excel as readonly string[]).includes(ext.value),
)
const isPdfClient = computed(() => normalizedFileType.value === 'pdf' || ext.value === 'pdf')
const isImageClient = computed(
  () =>
    normalizedFileType.value === 'image' ||
    (LEGACY_CAPABILITIES.previewHost.image as readonly string[]).includes(ext.value),
)
const isOfficeClient = computed(() => isDocx.value || isExcel.value || isPdfClient.value)
const isPreviewableClient = computed(
  () => isOfficeClient.value || isImageClient.value,
)

// ─────────── server variant（原 Drawer_Host 抽屉，按 image/* mime + office 扩展名判定）───────────
const OFFICE_EXTS = LEGACY_CAPABILITIES.drawerHost.office
function getExtWithDot(name: string): string {
  const idx = name.lastIndexOf('.')
  return idx < 0 ? '' : name.slice(idx).toLowerCase()
}
const isPdfServer = computed(() => {
  const hint = props.attachment?.type_hint || ''
  const name = props.attachment?.name || ''
  return hint === 'application/pdf' || name.endsWith(LEGACY_CAPABILITIES.drawerHost.pdfSuffix)
})
const isImageServer = computed(() =>
  (props.attachment?.type_hint || '').startsWith(LEGACY_CAPABILITIES.drawerHost.imageTypePrefix),
)
const isOfficeServer = computed(() =>
  (OFFICE_EXTS as readonly string[]).includes(getExtWithDot(props.attachment?.name || '')),
)
const serverPreviewUrl = computed(() => {
  if (isOfficeServer.value && props.attachment?.id) return P_att.previewPdf(props.attachment.id)
  return props.attachment?.preview_url || ''
})

// ── Office 健康探测（仅 server variant，进程级缓存与原抽屉一致）──
let officeHealthCache: boolean | null = null
const officeAvailable = ref<boolean | null>(officeHealthCache)
async function probeOfficeHealth() {
  if (officeHealthCache !== null) {
    officeAvailable.value = officeHealthCache
    return
  }
  try {
    const data: any = await api.get(P_office.health)
    officeHealthCache = !!data?.available
    officeAvailable.value = officeHealthCache
  } catch {
    officeHealthCache = false
    officeAvailable.value = false
  }
}

// ── server variant：原件经已鉴权请求换成 blob: 地址（iframe / img 直接用 /api 路径带不上令牌，恒 401）──
const serverWantsInline = computed(
  () => isPdfServer.value || isImageServer.value || (isOfficeServer.value && officeAvailable.value !== false),
)
const { url: serverObjectUrl, state: serverState } = useAuthedObjectUrl(
  () => (props.variant === 'server' && props.active && serverWantsInline.value ? serverPreviewUrl.value : ''),
  { type: () => (isImageServer.value ? undefined : 'application/pdf') },
)
const serverStateText = computed(() => authedObjectUrlFailureText(serverState.value) || '原件加载中…')

// ── client variant：与 server 共用鉴权 blob URL 生命周期（Abort/序号/revoke/错误分型）──
const clientPreviewUrl = computed(() =>
  props.variant === 'client' && props.active && isPreviewableClient.value && !isExtended.value
    ? (props.attachment?.preview_url || '')
    : '',
)
const { url: previewSrc, state: clientState } = useAuthedObjectUrl(clientPreviewUrl)
const clientStateText = computed(() => authedObjectUrlFailureText(clientState.value))
watch(
  () => [clientPreviewUrl.value, clientState.value],
  () => {
    officeLoadError.value = false
    loading.value = clientState.value === 'loading'
  },
  { immediate: true },
)
function onRendered() {
  loading.value = false
}
function onError() {
  loading.value = false
}

async function onDownload() {
  const url = props.attachment?.download_url
  if (url) {
    await downloadFile(url)
  }
  emit('download')
}

// ── variant=server 的 office health 触发 ──
watch(
  () => props.variant === 'server' && props.active && isOfficeServer.value,
  (need) => {
    if (need && officeAvailable.value === null) probeOfficeHealth()
  },
  { immediate: true },
)

</script>

<style scoped>
.gt-apc {
  display: flex;
  flex-direction: column;
  height: 100%;
}
/* client（弹窗）舞台 —— class 名与收敛前 Preview_Host 逐项一致 */
.gt-apc--client .gt-apc__stage {
  min-height: 400px;
  max-height: 70vh;
  overflow: auto;
}
.gt-preview-content {
  width: 100%;
  min-height: 400px;
}
.gt-preview-image {
  max-width: 100%;
  max-height: 60vh;
  display: block;
  margin: 0 auto;
}
.gt-preview-loading-placeholder {
  min-height: 400px;
}
/* server（抽屉）舞台 —— class 名与收敛前 Drawer_Host 逐项一致 */
.gt-apc--server {
  gap: var(--gt-space-3);
}
.gt-apc--server .gt-apc__stage {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.gt-attach-preview__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: var(--gt-space-2);
  border-bottom: 1px solid var(--gt-color-border-light);
}
.gt-attach-preview__name {
  font-weight: 600;
  font-size: var(--gt-font-size-sm);
  flex: 1;
}
.gt-attach-preview__frame {
  flex: 1;
  border: none;
  border-radius: var(--gt-radius-sm);
  min-height: 400px;
}
.gt-attach-preview__img {
  max-width: 100%;
  border-radius: var(--gt-radius-sm);
  object-fit: contain;
}
.gt-attach-preview__fallback {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.gt-attach-preview__ocr {
  border-top: 1px solid var(--gt-color-border-light);
  padding-top: var(--gt-space-3);
}
.gt-attach-preview__ocr h4 {
  margin: 0 0 var(--gt-space-2);
  font-size: var(--gt-font-size-sm);
}
.gt-attach-preview__ocr-text {
  font-size: var(--gt-font-size-xs);
  line-height: 1.6;
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
  background: var(--gt-color-bg);
  padding: var(--gt-space-2);
  border-radius: var(--gt-radius-sm);
}
</style>
