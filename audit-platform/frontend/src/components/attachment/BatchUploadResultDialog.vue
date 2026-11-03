<template>
  <el-dialog
    v-model="visible"
    title="📋 批量上传结果"
    width="85%"
    :close-on-click-modal="false"
    class="gt-batch-upload-dialog"
    destroy-on-close
  >
    <div class="gt-batch-layout">
      <!-- 左侧：汇总台账 -->
      <div class="gt-batch-left">
        <div class="gt-batch-summary">
          <div class="gt-batch-summary-item gt-batch-summary--success">
            <span class="gt-batch-summary-val">{{ successCount }}</span>
            <span class="gt-batch-summary-label">上传成功</span>
          </div>
          <div class="gt-batch-summary-item gt-batch-summary--warning">
            <span class="gt-batch-summary-val">{{ pendingOcrCount }}</span>
            <span class="gt-batch-summary-label">待确认 OCR</span>
          </div>
          <div class="gt-batch-summary-item gt-batch-summary--danger">
            <span class="gt-batch-summary-val">{{ failedCount }}</span>
            <span class="gt-batch-summary-label">上传失败</span>
          </div>
        </div>

        <!-- 文件列表 -->
        <div class="gt-batch-file-list">
          <div
            v-for="(item, idx) in items"
            :key="idx"
            class="gt-batch-file-row"
            :class="{
              'gt-batch-file-row--active': selectedIdx === idx,
              'gt-batch-file-row--failed': item.status === 'failed',
              'gt-batch-file-row--pending': item.status === 'ocr_pending',
            }"
            @click="selectItem(idx)"
          >
            <span class="gt-batch-file-icon">{{ getEmoji(item) }}</span>
            <div class="gt-batch-file-info">
              <div class="gt-batch-file-name">{{ item.fileName }}</div>
              <div class="gt-batch-file-meta">{{ formatSize(item.fileSize) }}</div>
            </div>
            <div class="gt-batch-file-status">
              <el-tag v-if="item.status === 'success'" size="small" type="success" effect="light" round>✓</el-tag>
              <el-tag v-else-if="item.status === 'ocr_pending'" size="small" type="warning" effect="dark" round>🔍 待确认</el-tag>
              <el-tag v-else-if="item.status === 'ocr_confirmed'" size="small" type="success" effect="light" round>✓ 已确认</el-tag>
              <el-tag v-else-if="item.status === 'failed'" size="small" type="danger" effect="light" round>✗ 失败</el-tag>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧：选中文件的 OCR 对照详情 -->
      <div class="gt-batch-right">
        <template v-if="selectedItem">
          <!-- 失败的文件显示错误信息 -->
          <div v-if="selectedItem.status === 'failed'" class="gt-batch-detail-error">
            <div class="gt-batch-detail-error-icon">❌</div>
            <div class="gt-batch-detail-error-msg">{{ selectedItem.error || '上传失败' }}</div>
          </div>

          <!-- OCR 待确认的文件显示对照编辑 -->
          <template v-else-if="selectedItem.status === 'ocr_pending' || selectedItem.status === 'ocr_confirmed'">
            <div class="gt-batch-detail-header">
              <span>{{ selectedItem.fileName }}</span>
              <el-tag v-if="selectedItem.confidence != null" size="small" :type="selectedItem.confidence > 0.9 ? 'success' : 'warning'" effect="plain">
                置信度 {{ (selectedItem.confidence * 100).toFixed(0) }}%
              </el-tag>
            </div>
            <div class="gt-batch-detail-split">
              <!-- 预览 -->
              <div class="gt-batch-detail-preview" v-loading="previewState === 'loading'">
                <img v-if="isImage(selectedItem) && previewSrc" :src="previewSrc" class="gt-batch-preview-img" alt="原件" />
                <iframe v-else-if="isPdf(selectedItem) && previewSrc" :src="previewSrc" class="gt-batch-preview-iframe" frameborder="0" title="原件" />
                <div v-else class="gt-batch-preview-fallback">
                  <div style="font-size:36px">{{ getEmoji(selectedItem) }}</div>
                  <div style="margin-top:8px;font-size:12px;color:var(--gt-color-text-tertiary)">{{ previewHint }}</div>
                </div>
              </div>
              <!-- OCR 文本 -->
              <div class="gt-batch-detail-ocr" v-loading="loadingIdx === selectedIdx">
                <el-input
                  v-model="selectedItem.ocrText"
                  type="textarea"
                  :autosize="{ minRows: 8, maxRows: 20 }"
                  :disabled="selectedItem.status === 'ocr_confirmed' || !selectedItem.ocrBaseSha256"
                  class="gt-batch-ocr-textarea"
                />
                <el-button
                  v-if="selectedItem.status === 'ocr_pending'"
                  type="primary"
                  size="small"
                  style="margin-top: 8px"
                  :loading="confirming"
                  :disabled="!selectedItem.ocrBaseSha256"
                  @click="confirmSingleOcr(selectedIdx)"
                >
                  确认此文件
                </el-button>
              </div>
            </div>
          </template>

          <!-- 纯成功无 OCR 的文件 -->
          <div v-else class="gt-batch-detail-ok">
            <div class="gt-batch-detail-ok-icon">✅</div>
            <div>上传成功，无 OCR 内容需确认</div>
          </div>
        </template>
        <div v-else class="gt-batch-detail-placeholder">
          ← 点击左侧文件查看详情
        </div>
      </div>
    </div>

    <template #footer>
      <div class="gt-batch-footer">
        <span class="gt-batch-footer-hint" v-if="pendingOcrCount > 0">
          还有 {{ pendingOcrCount }} 个文件的 OCR 结果待确认
        </span>
        <el-button v-if="pendingOcrCount > 0" @click="confirmAllOcr" :loading="confirmingAll">
          全部确认入库
        </el-button>
        <el-button type="primary" @click="visible = false">完成</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { authedObjectUrlFailureText, useAuthedObjectUrl } from '@/composables/useAuthedObjectUrl'
import { OCR_TEXT_CHANGED_TIP, confirmOcrText, isOcrTextChanged, loadOcrText } from './ocrTextApi'

export interface BatchUploadItem {
  fileName: string
  fileSize: number
  fileType: string
  attachmentId?: string
  previewUrl?: string
  /** 上传回执里是 200 字预览；选中待确认文件时换成全文（loadFullText） */
  ocrText?: string
  /** 取全文时的原文与 sha256：确认时作 base（spec attachment-security-baseline 需求 3.5） */
  ocrOriginalText?: string
  ocrBaseSha256?: string
  confidence?: number
  status: 'success' | 'ocr_pending' | 'ocr_confirmed' | 'failed'
  error?: string
}

const props = defineProps<{
  modelValue: boolean
  items: BatchUploadItem[]
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  'all-done': []
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const selectedIdx = ref<number>(0)
const confirming = ref(false)
const confirmingAll = ref(false)

const selectedItem = computed(() => props.items[selectedIdx.value] ?? null)

const successCount = computed(() => props.items.filter(i => i.status === 'success' || i.status === 'ocr_confirmed').length)
const pendingOcrCount = computed(() => props.items.filter(i => i.status === 'ocr_pending').length)
const failedCount = computed(() => props.items.filter(i => i.status === 'failed').length)

function selectItem(idx: number) {
  selectedIdx.value = idx
}

function isImage(item: BatchUploadItem): boolean {
  const t = (item.fileType || '').toLowerCase()
  return ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'].some(ext => t.includes(ext))
}

function isPdf(item: BatchUploadItem): boolean {
  return (item.fileType || '').toLowerCase().includes('pdf')
}

// 原件经已鉴权请求换成 blob: 地址：iframe / img 直接用 /api 路径带不上令牌，恒 401
const canPreview = computed(() => {
  const item = selectedItem.value
  return !!item?.previewUrl
    && (item.status === 'ocr_pending' || item.status === 'ocr_confirmed')
    && (isImage(item) || isPdf(item))
})
const { url: previewSrc, state: previewState } = useAuthedObjectUrl(
  () => (visible.value && canPreview.value ? selectedItem.value?.previewUrl : ''),
  { type: () => (selectedItem.value && isPdf(selectedItem.value) ? 'application/pdf' : undefined) },
)
const previewHint = computed(() =>
  canPreview.value ? authedObjectUrlFailureText(previewState.value) || '原件加载中…' : '暂不可预览',
)

function getEmoji(item: BatchUploadItem): string {
  const t = (item.fileType || item.fileName || '').toLowerCase()
  if (t.includes('pdf')) return '📕'
  if (t.includes('doc') || t.includes('word')) return '📘'
  if (t.includes('xls') || t.includes('excel')) return '📗'
  if (t.includes('ppt')) return '📙'
  if (['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'tif', 'heic'].some(e => t.includes(e))) return '🖼️'
  if (t.includes('zip') || t.includes('rar') || t.includes('7z')) return '📦'
  if (t.includes('eml') || t.includes('msg')) return '✉️'
  return '📄'
}

function formatSize(bytes: number): string {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

const loadingIdx = ref<number | null>(null)

/** 取全文与 sha256（原先确认写回的是上传回执里的 200 字预览，全文被截断）。 */
async function loadFullText(item: BatchUploadItem, force = false): Promise<void> {
  if (!item.attachmentId || (item.ocrBaseSha256 && !force)) return
  const snap = await loadOcrText(item.attachmentId)
  item.ocrText = snap.text
  item.ocrOriginalText = snap.text
  item.ocrBaseSha256 = snap.sha256
}

watch(() => [visible.value, selectedIdx.value] as const, async ([show, idx]) => {
  const item = props.items[idx]
  if (!show || !item || item.status !== 'ocr_pending' || item.ocrBaseSha256) return
  loadingIdx.value = idx
  try {
    await loadFullText(item)
  } catch {
    ElMessage.error(`"${item.fileName}" 识别全文加载失败`)
  } finally {
    if (loadingIdx.value === idx) loadingIdx.value = null
  }
}, { immediate: true })

/** 确认一个文件：未取过全文的先取（批量确认时未打开过的文件按原文确认）；返回是否成功。 */
async function confirmItem(item: BatchUploadItem): Promise<boolean> {
  if (!item.attachmentId) return false
  try {
    await loadFullText(item)
    const revised = item.ocrText !== item.ocrOriginalText ? item.ocrText : undefined
    await confirmOcrText(item.attachmentId, item.ocrBaseSha256 || '', revised)
    item.status = 'ocr_confirmed'
    return true
  } catch (e: any) {
    if (isOcrTextChanged(e)) {
      ElMessage.warning(`"${item.fileName}"：${OCR_TEXT_CHANGED_TIP}`)
      await loadFullText(item, true).catch(() => undefined)
    } else {
      ElMessage.error(`"${item.fileName}" 确认失败`)
    }
    return false
  }
}

async function confirmSingleOcr(idx: number) {
  const item = props.items[idx]
  if (!item || !item.attachmentId) return
  confirming.value = true
  try {
    if (await confirmItem(item)) ElMessage.success(`"${item.fileName}" OCR 已确认`)
  } finally {
    confirming.value = false
  }
}

async function confirmAllOcr() {
  confirmingAll.value = true
  let count = 0
  for (const item of props.items) {
    if (item.status === 'ocr_pending' && item.attachmentId && await confirmItem(item)) count++
  }
  confirmingAll.value = false
  ElMessage.success(`已确认 ${count} 个文件的 OCR 结果`)
  if (pendingOcrCount.value === 0) {
    emit('all-done')
  }
}
</script>

<style scoped>
.gt-batch-layout {
  display: flex;
  gap: 0;
  min-height: 460px;
  max-height: 65vh;
}

/* ─── 左侧台账 ─── */
.gt-batch-left {
  width: 320px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--gt-color-border-light, #eee);
  padding-right: 16px;
}

.gt-batch-summary {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.gt-batch-summary-item {
  flex: 1;
  text-align: center;
  padding: 10px 4px;
  border-radius: 8px;
  background: var(--gt-color-bg-white, #f9f9f9);
  border: 1px solid var(--gt-color-border-light, #eee);
}

.gt-batch-summary--success .gt-batch-summary-val { color: #67C23A; }
.gt-batch-summary--warning .gt-batch-summary-val { color: #E6A23C; }
.gt-batch-summary--danger .gt-batch-summary-val { color: #F56C6C; }

.gt-batch-summary-val { font-size: 20px; font-weight: 700; display: block; }
.gt-batch-summary-label { font-size: 11px; color: var(--gt-color-text-tertiary); }

.gt-batch-file-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.gt-batch-file-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid transparent;
}

.gt-batch-file-row:hover { background: var(--gt-color-bg-white, #f5f5f5); }
.gt-batch-file-row--active {
  background: var(--gt-purple-light, #f4f0fa);
  border-color: var(--gt-purple, #4b2d77);
}
.gt-batch-file-row--failed { opacity: 0.6; }
.gt-batch-file-row--pending .gt-batch-file-name { color: #E6A23C; }

.gt-batch-file-icon { font-size: 20px; flex-shrink: 0; }
.gt-batch-file-info { flex: 1; min-width: 0; }
.gt-batch-file-name {
  font-size: 13px; font-weight: 500;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.gt-batch-file-meta { font-size: 11px; color: var(--gt-color-text-tertiary); }
.gt-batch-file-status { flex-shrink: 0; }

/* ─── 右侧详情 ─── */
.gt-batch-right {
  flex: 1;
  padding-left: 16px;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.gt-batch-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
}

.gt-batch-detail-split {
  display: flex;
  gap: 12px;
  flex: 1;
  min-height: 0;
}

.gt-batch-detail-preview {
  flex: 1;
  border: 1px solid var(--gt-color-border-light, #eee);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f8f8fa;
}

.gt-batch-preview-img { max-width: 100%; max-height: 100%; object-fit: contain; }
.gt-batch-preview-iframe { width: 100%; height: 100%; min-height: 300px; }
.gt-batch-preview-fallback { text-align: center; padding: 40px; }

.gt-batch-detail-ocr { flex: 1; display: flex; flex-direction: column; min-height: 0; }

/* 全文封顶、内部滚动，不得溢出盖住「确认此文件」与底部按钮（同 OcrConfirmDialog） */
.gt-batch-ocr-textarea :deep(.el-textarea__inner) {
  max-height: calc(65vh - 110px);
  overflow-y: auto;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  line-height: 1.6;
  border-radius: 8px;
}

.gt-batch-detail-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #F56C6C;
}
.gt-batch-detail-error-icon { font-size: 40px; margin-bottom: 12px; }
.gt-batch-detail-error-msg { font-size: 14px; }

.gt-batch-detail-ok {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--gt-color-text-secondary);
}
.gt-batch-detail-ok-icon { font-size: 40px; margin-bottom: 8px; }

.gt-batch-detail-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--gt-color-text-tertiary);
  font-size: 14px;
}

/* ─── Footer ─── */
.gt-batch-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  width: 100%;
}
.gt-batch-footer-hint {
  margin-right: auto;
  font-size: 13px;
  color: #E6A23C;
}

/* ─── 响应式 ─── */
@media (max-width: 768px) {
  .gt-batch-layout { flex-direction: column; }
  .gt-batch-left { width: 100%; border-right: none; border-bottom: 1px solid var(--gt-color-border-light); padding-right: 0; padding-bottom: 12px; }
  .gt-batch-right { padding-left: 0; padding-top: 12px; }
  .gt-batch-detail-split { flex-direction: column; }
}
</style>
