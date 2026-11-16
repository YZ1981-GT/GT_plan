<!--
  AttachmentTabPanel — 底稿右栏「附件」Tab 内容容器 [AT-2 实时预览接入]

  职责：
    - 列出当前底稿关联的附件：读统一视图（整稿关联 ∪ reference ∪ 函证挂载 ∪ 行级证据链接，
      spec attachment-evidence-intake 需求 4.3；原先只读 reference_type='working_paper'，行级证据看不到）
    - 关联底稿数取视图里的 linked_wp_count；具体底稿清单悬停时再取（原先每个附件加载时一个请求）
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

      <div v-if="loading" v-loading="true" class="gt-attach-tab__loading" role="status" aria-label="正在加载关联附件">
        正在加载关联附件…
      </div>
      <div v-else-if="listStatus === 'error' || listStatus === 'forbidden'" class="gt-attach-tab__empty gt-attach-tab__error" role="alert" data-testid="attachment-tab-load-error">
        <div>{{ listStatus === 'forbidden' ? '无权查看本底稿附件' : '关联附件加载失败' }}</div>
        <div class="gt-attach-tab__error-detail">{{ listError || '请检查网络后重试' }}</div>
        <button type="button" class="gt-attach-tab__retry" data-testid="attachment-tab-retry" @click="loadList">重试</button>
      </div>
      <div v-else-if="listStatus === 'empty'" class="gt-attach-tab__empty">暂无关联附件</div>
      <ul v-else-if="listStatus === 'ready'" class="gt-attach-tab__list">
        <li
          v-for="att in list"
          :key="att.id"
          class="gt-attach-tab__item"
          @click="onPreview(att, $event)"
        >
          <span class="gt-attach-tab__icon" aria-hidden="true">{{ iconFor(att.file_name) }}</span>
          <div class="gt-attach-tab__body">
            <button
              type="button"
              class="gt-attach-tab__name"
              :title="`预览 ${att.file_name}`"
              :aria-label="`预览附件 ${att.file_name}`"
              @click.stop="onPreview(att, $event)"
              @keydown="onItemKeydown($event, att)"
            >{{ att.file_name }}</button>
            <div class="gt-attach-tab__meta">
              {{ humanSize(att.file_size) }} · {{ shortTime(att.created_at) }}
              <span v-if="isRowOnly(att)" class="gt-attach-tab__row-tag" data-testid="row-evidence-tag">行级证据</span>
              <!-- 关联底稿计数 badge：数量取统一视图，清单悬停时再取 -->
              <el-popover
                v-if="(att.linked_wp_count || 0) > 1"
                placement="bottom"
                trigger="hover"
                :width="220"
                @show="loadLinkedWps(att.id)"
              >
                <template #reference>
                  <span class="gt-attach-tab__link-badge" :data-attachment="att.id">📋 ×{{ att.linked_wp_count }}</span>
                </template>
                <div class="gt-attach-tab__link-list">
                  <div v-if="linkedWps[att.id] === undefined" class="gt-attach-tab__link-hint">加载中…</div>
                  <div v-else-if="linkedWps[att.id] === null" class="gt-attach-tab__link-hint" role="alert">
                    关联底稿加载失败
                    <button type="button" class="gt-attach-tab__link-retry" aria-label="重试关联底稿列表" title="重试关联底稿列表" @click.stop="loadLinkedWps(att.id)">重试</button>
                  </div>
                  <div
                    v-for="wp in linkedWps[att.id] || []"
                    :key="wp.wp_id"
                    class="gt-attach-tab__link-item"
                    @click.stop="jumpToWp(wp.wp_id)"
                  >
                    <span class="gt-attach-tab__link-code">{{ wp.wp_code }}</span>
                    <span class="gt-attach-tab__link-name">{{ wp.wp_name }}</span>
                  </div>
                </div>
              </el-popover>
            </div>
          </div>
          <el-tag v-if="isOffice(att.file_name)" size="small" type="info" round>Office</el-tag>
          <!-- 整行点击照旧预览；小眼睛让入口一眼可见（spec attachment-inline-preview 需求 2.2） -->
          <el-tooltip content="预览" placement="top" :show-after="300">
            <el-button
              link
              type="primary"
              size="small"
              class="gt-attach-tab__eye"
              :aria-label="`预览 ${att.file_name}`"
              :title="`预览 ${att.file_name}`"
              data-testid="attachment-eye"
              @click.stop="onPreview(att, $event)"
            ><el-icon><View /></el-icon></el-button>
          </el-tooltip>
        </li>
      </ul>
    </AttachmentDropZone>

    <AttachmentPreviewDrawer v-model="drawerOpen" :attachment="selected" downloadable size="min(960px, 72vw)" />

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
import { reactive, ref, watch, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { Paperclip, View } from '@element-plus/icons-vue'
import AttachmentDropZone from '@/components/workpaper/AttachmentDropZone.vue'
import AttachmentPreviewDrawer, {
  type AttachmentForPreview,
} from '@/components/common/AttachmentPreviewDrawer.vue'
import { toAttachmentPreview } from '@/components/attachment/attachmentPreviewTarget'
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
  sources?: string[]
  linked_wp_count?: number
}

interface LinkedWp {
  wp_id: string
  wp_code?: string
  wp_name?: string
}

const props = defineProps<{
  projectId: string
  wpId: string
}>()

const router = useRouter()
const list = ref<AttachmentRow[]>([])
type AttachmentListStatus = 'idle' | 'loading' | 'ready' | 'empty' | 'forbidden' | 'error'
const listStatus = ref<AttachmentListStatus>('idle')
const listError = ref('')
const loading = ref(false)
let listSeq = 0
let listAbort: AbortController | null = null
const drawerOpen = ref(false)
const selected = ref<AttachmentForPreview | null>(null)
let previewOpener: HTMLElement | null = null

function rememberPreviewOpener(source: Event | EventTarget | null | undefined) {
  const eventLike = source && typeof source === 'object'
    && ('currentTarget' in source || 'target' in source)
  const candidate = eventLike
    ? ((source as Event).currentTarget || (source as Event).target)
    : source
  const element = candidate instanceof Element
    ? ((candidate.closest('button') as HTMLElement | null) || (candidate instanceof HTMLElement ? candidate : null))
    : null
  previewOpener = element
}

function restorePreviewFocus() {
  const opener = previewOpener
  previewOpener = null
  if (!opener?.isConnected) return
  void nextTick(() => {
    if (opener.isConnected) opener.focus()
  })
}

watch(drawerOpen, (open) => {
  if (!open) restorePreviewFocus()
})

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

/** 只挂在某一行 / 单元格上的证据（没有整稿关联与 reference）。 */
function isRowOnly(att: AttachmentRow): boolean {
  const sources = att.sources || []
  return sources.includes('evidence_link') && !sources.includes('associated') && !sources.includes('referenced')
}

async function loadList() {
  const mine = ++listSeq
  listAbort?.abort()
  if (!props.projectId || !props.wpId) {
    list.value = []
    listError.value = ''
    listStatus.value = 'empty'
    listAbort = null
    return
  }
  const controller = new AbortController()
  listAbort = controller
  loading.value = true
  listStatus.value = 'loading'
  listError.value = ''
  try {
    const data: any = await httpApi.get(P_att.wpView(props.wpId), {
      _silent: true,
      _dedupe: false,
      signal: controller.signal,
    } as any)
    if (mine !== listSeq) return
    const items = Array.isArray(data) ? data : Array.isArray(data?.items) ? data.items : null
    if (!items) throw new Error('关联附件响应格式不正确')
    list.value = items
    listStatus.value = items.length ? 'ready' : 'empty'
  } catch (error: any) {
    if (mine !== listSeq || controller.signal.aborted) return
    const status = Number(error?.response?.status || error?.status || 0)
    listStatus.value = status === 403 ? 'forbidden' : 'error'
    listError.value = status === 403 ? '你没有查看本底稿附件的权限' : '请检查网络或稍后重试'
  } finally {
    if (mine === listSeq) {
      loading.value = false
      if (listAbort === controller) listAbort = null
    }
  }
}

/** 附件 id → 关联底稿清单；undefined = 未取，null = 取失败（悬停时取一次，之后复用）。 */
const linkedWps = reactive<Record<string, LinkedWp[] | null | undefined>>({})
const linkedWpLoading = reactive<Record<string, boolean>>({})
const linkedWpControllers = new Map<string, AbortController>()

async function loadLinkedWps(attachmentId: string) {
  if (linkedWps[attachmentId] || linkedWpLoading[attachmentId]) return
  const controller = new AbortController()
  linkedWpControllers.set(attachmentId, controller)
  linkedWpLoading[attachmentId] = true
  try {
    const linked: any = await httpApi.get(P_pr.attachmentWorkpapers(attachmentId), {
      _silent: true,
      _dedupe: false,
      signal: controller.signal,
    } as any)
    if (controller.signal.aborted) return
    linkedWps[attachmentId] = Array.isArray(linked) ? linked : linked?.items || []
  } catch {
    if (!controller.signal.aborted) linkedWps[attachmentId] = null
  } finally {
    if (linkedWpControllers.get(attachmentId) === controller) linkedWpControllers.delete(attachmentId)
    linkedWpLoading[attachmentId] = false
  }
}

function jumpToWp(wpId: string) {
  if (wpId) {
    router.push(`/projects/${props.projectId}/workpapers/${wpId}`)
  }
}

function onPreview(att: AttachmentRow, opener?: Event | EventTarget | null) {
  rememberPreviewOpener(opener)
  // 判型统一构造：file_type 是分类词（image / word），原样当类型提示时图片判不出、
  // 识别状态 completed 显示成英文（spec attachment-inline-preview ADR-AIP-02）
  selected.value = toAttachmentPreview({
    id: att.id,
    file_name: att.file_name,
    file_type: att.file_type,
    ocr_status: att.ocr_status,
    ocr_text: att.ocr_text,
  })
  drawerOpen.value = true
}

function onItemKeydown(event: KeyboardEvent, att: AttachmentRow) {
  if (event.key !== 'Enter' && event.key !== ' ') return
  event.preventDefault()
  onPreview(att, event)
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

onUnmounted(() => {
  listSeq += 1
  listAbort?.abort()
  listAbort = null
  for (const controller of linkedWpControllers.values()) controller.abort()
  linkedWpControllers.clear()
  previewOpener = null
  _stopOcrPolling()
})

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
  display: block;
  width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  text-align: left;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  cursor: pointer;
}
.gt-attach-tab__name:hover { color: var(--gt-color-primary); text-decoration: underline; }
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
.gt-attach-tab__link-hint { font-size: 12px; color: var(--gt-color-text-tertiary); padding: 4px 8px; }
.gt-attach-tab__row-tag {
  padding: 0 6px;
  border-radius: 10px;
  background: var(--gt-color-fill-light, #f2f3f5);
  color: var(--gt-color-text-secondary, #606266);
  font-size: 11px;
}
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
.gt-attach-tab__error-detail { margin-top: 4px; font-size: 12px; }
.gt-attach-tab__retry,
.gt-attach-tab__link-retry {
  border: 0;
  background: transparent;
  color: var(--el-color-primary, #409eff);
  cursor: pointer;
  text-decoration: underline;
}
.gt-attach-tab__retry { margin-top: 8px; padding: 4px 8px; }
.gt-attach-tab__item:focus-visible,
.gt-attach-tab__name:focus-visible,
.gt-attach-tab__retry:focus-visible,
.gt-attach-tab__link-retry:focus-visible,
.gt-attach-tab__eye:focus-visible {
  outline: 2px solid var(--el-color-primary, #409eff);
  outline-offset: 2px;
}

@media (max-width: 768px) {
  .gt-attach-tab__item { align-items: flex-start; flex-wrap: wrap; }
  .gt-attach-tab__body { min-width: calc(100% - 48px); }
  .gt-attach-tab__meta { flex-wrap: wrap; }
  .gt-attach-tab__eye { margin-left: auto; }
}

@media (max-width: 390px) {
  .gt-attach-tab__hint { padding-inline: 8px; }
  .gt-attach-tab__item { padding-inline: 8px; }
  .gt-attach-tab__body { min-width: calc(100% - 36px); }
  .gt-attach-tab__meta { gap: 4px; }
  .gt-attach-tab__eye { width: 100%; justify-content: flex-end; }
}
</style>
