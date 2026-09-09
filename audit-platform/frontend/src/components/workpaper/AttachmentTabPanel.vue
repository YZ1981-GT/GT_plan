<!--
  AttachmentTabPanel — 底稿右栏「附件」Tab 内容容器 [AT-2 实时预览接入]

  职责：
    - 列出当前底稿关联的附件（process_record.attachments 端点）
    - 行内点击 → AttachmentPreviewDrawer（PDF/图片/Office 转 PDF iframe）
    - 顶部 AttachmentDropZone 包装一层，支持拖拽上传
    - link-created 事件触发后刷新列表

  接入：WorkpaperSidePanel 附件 Tab。
-->
<template>
  <div class="gt-attach-tab">
    <AttachmentDropZone
      :project-id="projectId"
      :wp-id="wpId"
      @link-created="onLinkCreated"
      @ocr-ready="onOcrReady"
    >
      <div class="gt-attach-tab__hint">
        <el-icon><Paperclip /></el-icon>
        <span>拖拽文件到此处上传，或点击行预览</span>
      </div>

      <div v-if="loading" v-loading="true" class="gt-attach-tab__loading" />
      <div v-else-if="!list.length" class="gt-attach-tab__empty">暂无关联附件</div>
      <ul v-else class="gt-attach-tab__list">
        <li
          v-for="att in list"
          :key="att.id"
          class="gt-attach-tab__item"
          @click="onPreview(att)"
        >
          <span class="gt-attach-tab__icon">{{ iconFor(att.file_name) }}</span>
          <div class="gt-attach-tab__body">
            <div class="gt-attach-tab__name" :title="att.file_name">{{ att.file_name }}</div>
            <div class="gt-attach-tab__meta">
              {{ humanSize(att.file_size) }} · {{ shortTime(att.created_at) }}
              <!-- 关联底稿计数 badge -->
              <el-popover
                v-if="att._linked_wps && att._linked_wps.length > 1"
                placement="bottom"
                trigger="hover"
                :width="200"
              >
                <template #reference>
                  <span class="gt-attach-tab__link-badge">📋 ×{{ att._linked_wps.length }}</span>
                </template>
                <div class="gt-attach-tab__link-list">
                  <div v-for="wp in att._linked_wps" :key="wp.wp_id" class="gt-attach-tab__link-item" @click.stop="jumpToWp(wp.wp_id)">
                    <span class="gt-attach-tab__link-code">{{ wp.wp_code }}</span>
                    <span class="gt-attach-tab__link-name">{{ wp.wp_name }}</span>
                  </div>
                </div>
              </el-popover>
            </div>
          </div>
          <el-tag v-if="isOffice(att.file_name)" size="small" type="info" round>Office</el-tag>
        </li>
      </ul>
    </AttachmentDropZone>

    <AttachmentPreviewDrawer v-model="drawerOpen" :attachment="selected" />

    <!-- OCR 确认弹窗（底稿内上传同样走确认流程） -->
    <OcrConfirmDialog
      v-model="ocrDialogVisible"
      :payload="ocrPayload"
      @confirmed="onOcrConfirmed"
      @rejected="onOcrRejected"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Paperclip } from '@element-plus/icons-vue'
import AttachmentDropZone from '@/components/workpaper/AttachmentDropZone.vue'
import AttachmentPreviewDrawer, {
  type AttachmentForPreview,
} from '@/components/common/AttachmentPreviewDrawer.vue'
import {
  LEGACY_CAPABILITIES,
} from '@/components/attachment/preview/attachmentPreviewFormats'
import OcrConfirmDialog from '@/components/attachment/OcrConfirmDialog.vue'
import type { OcrConfirmPayload } from '@/components/attachment/OcrConfirmDialog.vue'
import { api as httpApi } from '@/services/apiProxy'
import { processRecord as P_pr, attachments as P_att } from '@/services/apiPaths'

interface AttachmentRow {
  id: string
  file_name: string
  file_size: number | null
  file_type: string | null
  created_at: string | null
  ocr_status?: 'ok' | 'processing' | 'failed' | 'pending' | null
  ocr_text?: string | null
}

const props = defineProps<{
  projectId: string
  wpId: string
}>()

const router = useRouter()
const list = ref<AttachmentRow[]>([])
const loading = ref(false)
const drawerOpen = ref(false)
const selected = ref<AttachmentForPreview | null>(null)

const OFFICE_EXTS = LEGACY_CAPABILITIES.attachmentTab.office

function getExt(name: string): string {
  const idx = name.lastIndexOf('.')
  return idx < 0 ? '' : name.slice(idx).toLowerCase()
}

function isOffice(name: string): boolean {
  return (OFFICE_EXTS as readonly string[]).includes(getExt(name))
}

function iconFor(name: string): string {
  const ext = getExt(name)
  const groups = LEGACY_CAPABILITIES.attachmentTab.iconGroups
  if ((groups.pdf as readonly string[]).includes(ext)) return '📄'
  if ((groups.image as readonly string[]).includes(ext)) return '🖼️'
  if ((groups.word as readonly string[]).includes(ext)) return '📝'
  if ((groups.excel as readonly string[]).includes(ext)) return '📊'
  if ((groups.ppt as readonly string[]).includes(ext)) return '📽️'
  return '📎'
}

function humanSize(bytes: number | null): string {
  if (!bytes || bytes <= 0) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function shortTime(iso: string | null): string {
  if (!iso) return ''
  return iso.slice(0, 16).replace('T', ' ')
}

async function loadList() {
  if (!props.projectId || !props.wpId) {
    list.value = []
    return
  }
  loading.value = true
  try {
    const data: any = await httpApi.get(P_pr.attachments(props.projectId, props.wpId))
    const items = Array.isArray(data) ? data : data?.items || []
    // 加载每个附件的关联底稿列表（批量）
    for (const att of items) {
      att._linked_wps = []
      try {
        const linked: any = await httpApi.get(P_pr.attachmentWorkpapers(att.id))
        att._linked_wps = Array.isArray(linked) ? linked : linked?.items || []
      } catch { /* 单个失败不阻塞 */ }
    }
    list.value = items
  } catch {
    list.value = []
  } finally {
    loading.value = false
  }
}

function jumpToWp(wpId: string) {
  if (wpId) {
    router.push(`/projects/${props.projectId}/workpapers/${wpId}`)
  }
}

function onPreview(att: AttachmentRow) {
  selected.value = {
    id: att.id,
    name: att.file_name,
    type_hint: att.file_type || '',
    preview_url: P_att.preview(att.id),
    download_url: P_att.download(att.id),
    ocr_status: att.ocr_status || undefined,
    ocr_text: att.ocr_text || undefined,
  }
  drawerOpen.value = true
}

function onLinkCreated() {
  loadList()
}

// ─── OCR 确认弹窗 ───
const ocrDialogVisible = ref(false)
const ocrPayload = ref<OcrConfirmPayload | null>(null)

function onOcrReady(payload: { attachmentId: string; fileName: string; fileType: string; ocrText: string; confidence?: number }) {
  ocrPayload.value = {
    attachmentId: payload.attachmentId,
    fileName: payload.fileName,
    fileType: payload.fileType,
    previewUrl: P_att.preview(payload.attachmentId),
    ocrText: payload.ocrText,
    confidence: payload.confidence,
  }
  ocrDialogVisible.value = true
}

function onOcrConfirmed() {
  loadList()
}

function onOcrRejected() {
  // 用户放弃，不影响列表（附件已上传已关联，仅 OCR 文本不入库）
}

watch(
  () => [props.projectId, props.wpId],
  () => loadList(),
  { immediate: true },
)

// #4: OCR 状态轮询 — processing 状态的附件每 5s 检查一次直到完成
let _ocrPollTimer: ReturnType<typeof setInterval> | null = null

function _startOcrPolling() {
  _stopOcrPolling()
  const hasPending = list.value.some((a: any) => a.ocr_status === 'processing' || a.ocr_status === 'pending')
  if (!hasPending) return
  _ocrPollTimer = setInterval(async () => {
    const pending = list.value.filter((a: any) => a.ocr_status === 'processing' || a.ocr_status === 'pending')
    if (!pending.length) { _stopOcrPolling(); return }
    // 逐个检查更新（轻量 GET）
    let anyUpdated = false
    for (const att of pending) {
      try {
        const detail: any = await httpApi.get(`/api/attachments/${att.id}`, { _silent: true } as any)
        if (detail?.ocr_status && detail.ocr_status !== (att as any).ocr_status) {
          ;(att as any).ocr_status = detail.ocr_status
          ;(att as any).ocr_text = detail.ocr_text
          anyUpdated = true
        }
      } catch { /* 单个轮询失败不阻塞 */ }
    }
    if (anyUpdated) {
      // 全部完成则停止轮询
      const stillPending = list.value.some((a: any) => a.ocr_status === 'processing' || a.ocr_status === 'pending')
      if (!stillPending) _stopOcrPolling()
    }
  }, 5000)
}

function _stopOcrPolling() {
  if (_ocrPollTimer) { clearInterval(_ocrPollTimer); _ocrPollTimer = null }
}

onUnmounted(() => _stopOcrPolling())

// loadList 完成后启动轮询
watch(list, () => _startOcrPolling(), { deep: false })
</script>

<style scoped>
.gt-attach-tab { display: flex; flex-direction: column; height: 100%; }
.gt-attach-tab__hint {
  display: flex; align-items: center; gap: 6px;
  padding: var(--gt-space-2) var(--gt-space-3);
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
  border-bottom: 1px dashed var(--gt-color-border-light);
}
.gt-attach-tab__loading { min-height: 80px; }
.gt-attach-tab__empty {
  padding: var(--gt-space-6);
  text-align: center;
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-sm);
}
.gt-attach-tab__list { list-style: none; margin: 0; padding: 0; }
.gt-attach-tab__item {
  display: flex; align-items: center; gap: var(--gt-space-2);
  padding: var(--gt-space-2) var(--gt-space-3);
  border-bottom: 1px solid var(--gt-color-border-light);
  cursor: pointer;
  transition: background 0.15s;
}
.gt-attach-tab__item:hover { background: var(--gt-color-primary-bg); }
.gt-attach-tab__icon { font-size: 18px; flex-shrink: 0; }
.gt-attach-tab__body { flex: 1; min-width: 0; }
.gt-attach-tab__name {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.gt-attach-tab__meta {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
  display: flex;
  align-items: center;
  gap: 6px;
}
.gt-attach-tab__link-badge {
  display: inline-flex;
  align-items: center;
  padding: 0 6px;
  border-radius: 10px;
  background: var(--gt-purple-light, #f4f0fa);
  color: var(--gt-purple, #4b2d77);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}
.gt-attach-tab__link-badge:hover {
  background: var(--gt-purple, #4b2d77);
  color: #fff;
}
.gt-attach-tab__link-list { display: flex; flex-direction: column; gap: 4px; }
.gt-attach-tab__link-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
}
.gt-attach-tab__link-item:hover { background: var(--gt-color-primary-bg, #f4f0fa); }
.gt-attach-tab__link-code { font-weight: 600; font-size: 12px; color: var(--gt-purple, #4b2d77); }
.gt-attach-tab__link-name { font-size: 11px; color: var(--gt-color-text-tertiary); }
</style>
