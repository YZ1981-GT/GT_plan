<template>
  <div class="gt-attachment-page" @dragover.prevent="onDragOver" @dragleave="onDragLeave" @drop.prevent="onDrop">
    <!-- 拖拽上传遮罩 -->
    <Transition name="gt-fade">
      <div v-if="isDragging" class="gt-att-dropzone">
        <div class="gt-att-dropzone-inner">
          <div class="gt-att-dropzone-icon">📎</div>
          <div class="gt-att-dropzone-text">释放文件以上传附件</div>
          <div class="gt-att-dropzone-hint">支持 {{ SUPPORTED_TYPES_DESC }}，单文件最大 50MB</div>
        </div>
      </div>
    </Transition>

    <!-- 顶部：标题 + 操作区 -->
    <div class="gt-att-top">
      <div class="gt-att-title-row">
        <div class="gt-att-title-left">
          <h2 class="gt-att-title">📎 附件管理</h2>
          <el-button class="gt-att-handbook-btn" :icon="Reading" @click="handbookVisible = true">使用手册</el-button>
        </div>
        <div class="gt-att-actions">
          <el-input v-model="searchQuery" placeholder="搜索文件名..." size="default" clearable
            :prefix-icon="Search" class="gt-att-search" @keyup.enter="onSearch" />
          <el-select v-model="filterType" placeholder="全部类型" size="default" clearable class="gt-att-type-filter" @change="loadAttachments">
            <el-option label="PDF" value="pdf" />
            <el-option label="Word" value="word" />
            <el-option label="Excel" value="excel" />
            <el-option label="PPT" value="ppt" />
            <el-option label="图片" value="image" />
            <el-option label="文本" value="text" />
            <el-option label="压缩包" value="archive" />
            <el-option label="邮件" value="email" />
            <el-option label="OFD/CAD" value="ofd" />
          </el-select>
          <el-upload :show-file-list="false" :before-upload="beforeUpload" :http-request="uploadAttachment" multiple :accept="ACCEPT_TYPES">
            <el-button type="primary"><el-icon><Upload /></el-icon> 上传文件</el-button>
          </el-upload>
          <el-tooltip content="上传整个文件夹（含子目录）" placement="bottom">
            <el-button @click="triggerFolderUpload"><el-icon><FolderOpened /></el-icon> 上传文件夹</el-button>
          </el-tooltip>
          <el-tooltip content="附件·OCR·AI·证据链治理中心" placement="bottom">
            <el-button @click="router.push({ name: 'EvidenceGovernanceCenter', params: { projectId } })">
              <el-icon><FolderChecked /></el-icon> 证据链治理
            </el-button>
          </el-tooltip>
          <!-- 隐藏的文件夹选择 input -->
          <input
            ref="folderInputRef"
            type="file"
            webkitdirectory
            multiple
            :accept="ACCEPT_TYPES"
            class="gt-att-hidden-input"
            @change="onFolderSelected"
          />
        </div>
      </div>

      <!-- 统计卡片 -->
      <div class="gt-att-stats">
        <div class="gt-att-stat-card">
          <div class="gt-att-stat-value">{{ attachments.length }}</div>
          <div class="gt-att-stat-label">总文件数</div>
        </div>
        <div class="gt-att-stat-card">
          <div class="gt-att-stat-value">{{ totalSizeFormatted }}</div>
          <div class="gt-att-stat-label">总大小</div>
        </div>
        <div class="gt-att-stat-card">
          <div class="gt-att-stat-value gt-att-stat-value--success">{{ ocrCompletedPct }}%</div>
          <div class="gt-att-stat-label">OCR 完成率</div>
        </div>
        <div class="gt-att-stat-card">
          <div class="gt-att-stat-value gt-att-stat-value--purple">{{ linkedCount }}</div>
          <div class="gt-att-stat-label">已关联底稿</div>
        </div>
      </div>
    </div>

    <!-- 附件列表 -->
    <div v-loading="loading" class="gt-att-body">
      <!-- 空状态 -->
      <div v-if="!loading && attachments.length === 0" class="gt-att-empty">
        <div class="gt-att-empty-icon">📂</div>
        <div class="gt-att-empty-title">暂无附件</div>
        <div class="gt-att-empty-desc">拖拽文件或文件夹到此区域，或点击上方按钮上传</div>
      </div>

      <!-- 文件列表 -->
      <TransitionGroup v-else name="gt-list" tag="div" class="gt-att-list">
        <div v-for="(row, idx) in filteredAttachments" :key="row.id" class="gt-att-item" :class="{ 'gt-att-item--highlight': row.id === highlightId }" :data-att-id="row.id" :style="{ '--delay': idx * 0.03 + 's' }">
          <div class="gt-att-item-icon" :class="'gt-att-icon--' + getFileCategory(row.file_type)">
            {{ getFileEmoji(row.file_type) }}
          </div>
          <div class="gt-att-item-info">
            <div class="gt-att-item-name" @click="preview(row)">{{ row.file_name }}</div>
            <div class="gt-att-item-meta">
              <el-tag size="small" :type="typeTagType(row.file_type) || undefined" effect="plain">{{ row.file_type || '未知' }}</el-tag>
              <span class="gt-att-item-size">{{ formatSize(row.file_size) }}</span>
              <span class="gt-att-item-date">{{ formatDate(row.created_at) }}</span>
              <!-- 溯源：关联底稿 chip -->
              <span v-if="row.wp_code" class="gt-att-lineage-chip" @click="jumpToWorkpaper(row)">
                📋 {{ row.wp_code }}
                <el-icon :size="12" class="gt-att-lineage-arrow"><Right /></el-icon>
              </span>
            </div>
          </div>
          <div class="gt-att-item-status">
            <el-tag v-if="row.ocr_status === 'completed' && !row.ocr_confirmed" size="small" type="warning" effect="dark" round class="gt-att-pending-badge" @click="openOcrConfirm(row)">
              🔍 待确认
            </el-tag>
            <el-tag v-else-if="row.ocr_status" size="small" :type="ocrTagType(row.ocr_status) || undefined" effect="light" round>
              {{ ocrLabel(row.ocr_status) }}
            </el-tag>
          </div>
          <div class="gt-att-item-actions">
            <el-tooltip content="预览" placement="top">
              <el-button circle size="small" @click="preview(row)"><el-icon><View /></el-icon></el-button>
            </el-tooltip>
            <el-tooltip v-if="row.ocr_status === 'completed' && !row.ocr_confirmed" content="确认 OCR 结果" placement="top">
              <el-button circle size="small" type="warning" @click="openOcrConfirm(row)"><el-icon><Check /></el-icon></el-button>
            </el-tooltip>
            <el-tooltip content="关联底稿" placement="top">
              <el-button circle size="small" @click="associateDialog(row)"><el-icon><Link /></el-icon></el-button>
            </el-tooltip>
            <el-tooltip content="下载" placement="top">
              <el-button circle size="small" @click="download(row)"><el-icon><Download /></el-icon></el-button>
            </el-tooltip>
            <el-tooltip v-if="row.ocr_status === 'failed'" content="重试 OCR" placement="top">
              <el-button circle size="small" type="warning" @click="retryOCR(row)"><el-icon><RefreshRight /></el-icon></el-button>
            </el-tooltip>
          </div>
        </div>
      </TransitionGroup>
    </div>

    <!-- 附件预览弹窗 -->
    <AttachmentPreview
      v-model="previewVisible"
      :file-url="previewUrl"
      :file-name="previewName"
      :file-type="previewType"
      @close="previewVisible = false"
    />

    <!-- 关联底稿弹窗 -->
    <el-dialog append-to-body v-model="associateVisible" title="关联到底稿" width="480px" class="gt-att-assoc-dialog">
      <el-form ref="assocFormRef" :model="assocForm" :rules="assocRules" label-width="80px">
        <el-form-item label="搜索底稿" prop="associateWpId">
          <el-select
            v-model="associateWpId"
            filterable
            remote
            :remote-method="searchWorkpapers"
            :loading="wpSearchLoading"
            placeholder="输入底稿编号或名称搜索"
            style="width: 100%"
            value-key="id"
          >
            <el-option v-for="wp in wpSearchResults" :key="wp.id" :label="`${wp.wp_code} ${wp.wp_name}`" :value="wp.id">
              <span style="float: left; font-weight: 600">{{ wp.wp_code }}</span>
              <span style="float: right; color: var(--gt-color-text-secondary); font-size: 12px">{{ wp.wp_name }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="关联类型">
          <el-select v-model="associateType" style="width: 100%">
            <el-option label="审计证据" value="evidence" />
            <el-option label="支持文件" value="support" />
            <el-option label="函证回函" value="confirmation" />
            <el-option label="合同" value="contract" />
            <el-option label="银行对账单" value="bank_statement" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="associateNotes" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="associateVisible = false">取消</el-button>
        <el-button type="primary" @click="submitAssociate" :disabled="!associateWpId">确认关联</el-button>
      </template>
    </el-dialog>

    <!-- OCR 识别结果确认弹窗（单文件） -->
    <OcrConfirmDialog
      v-model="ocrConfirmVisible"
      :payload="ocrConfirmPayload"
      @confirmed="onOcrConfirmed"
      @rejected="onOcrRejected"
    />

    <!-- 批量上传结果台账（多文件/文件夹） -->
    <BatchUploadResultDialog
      v-model="batchResultVisible"
      :items="batchItems"
      @all-done="loadAttachments"
    />

    <!-- 使用手册 -->
    <AttachmentHandbookDialog v-model="handbookVisible" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { Search, Upload, Document, View, Link, Download, RefreshRight, Right, Check, FolderOpened, FolderChecked, Reading } from '@element-plus/icons-vue'
import AttachmentPreview from '@/components/extension/AttachmentPreview.vue'
import OcrConfirmDialog from '@/components/attachment/OcrConfirmDialog.vue'
import type { OcrConfirmPayload } from '@/components/attachment/OcrConfirmDialog.vue'
import BatchUploadResultDialog from '@/components/attachment/BatchUploadResultDialog.vue'
import type { BatchUploadItem } from '@/components/attachment/BatchUploadResultDialog.vue'
import AttachmentHandbookDialog from './AttachmentHandbookDialog.vue'
import { downloadFile } from '@/utils/http'
import { api } from '@/services/apiProxy'
import { workpapers as P_wp, attachments as P_att } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { rules } from '@/utils/formRules'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)

const loading = ref(false)
const attachments = ref<any[]>([])
const handbookVisible = ref(false)
const highlightId = ref('')
let highlightTimer: ReturnType<typeof setTimeout> | null = null
const searchQuery = ref('')
const filterType = ref('')
const isDragging = ref(false)
const folderInputRef = ref<HTMLInputElement | null>(null)

// ─── 支持的文件类型 ───
const ACCEPT_TYPES = [
  // PDF
  '.pdf',
  // Word
  '.doc', '.docx',
  // Excel
  '.xls', '.xlsx',
  // PowerPoint
  '.ppt', '.pptx',
  // 图片
  '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff', '.tif',
  // 文本
  '.txt', '.csv', '.md',
  // 扫描件
  '.heic', '.heif',
  // 压缩包
  '.zip', '.rar', '.7z',
  // 电子邮件
  '.eml', '.msg',
  // CAD/签章
  '.dwg', '.ofd',
].join(',')

/** 支持的文件类型说明（用于拖拽区提示） */
const SUPPORTED_TYPES_DESC = 'PDF / Word / Excel / PPT / 图片 / 文本 / 扫描件 / 压缩包 / 邮件 / OFD'

// 统计 computed
const totalSizeFormatted = computed(() => {
  const total = attachments.value.reduce((sum, a) => sum + (a.file_size || 0), 0)
  return formatSize(total)
})
const ocrCompletedPct = computed(() => {
  const total = attachments.value.length
  if (total === 0) return 0
  const done = attachments.value.filter(a => a.ocr_status === 'completed').length
  return Math.round((done / total) * 100)
})
const linkedCount = computed(() =>
  attachments.value.filter(a => a.wp_code || a.wp_id).length
)
const filteredAttachments = computed(() => {
  if (!searchQuery.value) return attachments.value
  const q = searchQuery.value.toLowerCase()
  return attachments.value.filter(a => (a.file_name || '').toLowerCase().includes(q))
})

// 预览
const previewVisible = ref(false)
const previewUrl = ref('')
const previewName = ref('')
const previewType = ref('')

// OCR 确认弹窗（单文件）
const ocrConfirmVisible = ref(false)
const ocrConfirmPayload = ref<OcrConfirmPayload | null>(null)

// 批量上传结果台账
const batchResultVisible = ref(false)
const batchItems = ref<BatchUploadItem[]>([])

// 关联
const associateVisible = ref(false)
const associateAttachmentId = ref('')
const associateWpId = ref('')
const associateType = ref('evidence')
const associateNotes = ref('')
const wpSearchLoading = ref(false)
const wpSearchResults = ref<any[]>([])
const assocFormRef = ref<FormInstance>()
const assocForm = computed(() => ({ associateWpId: associateWpId.value }))
const assocRules: FormRules = {
  associateWpId: [rules.required('底稿', 'change')],
}

// ─── 拖拽上传 ───
let dragCounter = 0
function onDragOver(e: DragEvent) {
  dragCounter++
  isDragging.value = true
}
function onDragLeave() {
  dragCounter--
  if (dragCounter <= 0) { isDragging.value = false; dragCounter = 0 }
}
async function onDrop(e: DragEvent) {
  isDragging.value = false
  dragCounter = 0
  const files = e.dataTransfer?.files
  if (!files || files.length === 0) return

  const validFiles = Array.from(files).filter(beforeUpload)
  if (validFiles.length === 0) return

  // 单文件走原逻辑（直接上传 + 单个 OCR 弹窗）
  if (validFiles.length === 1) {
    await uploadAttachment({ file: validFiles[0] } as any)
    return
  }

  // 多文件走批量台账
  ElMessage.info(`正在上传 ${validFiles.length} 个文件...`)
  const results: BatchUploadItem[] = []
  for (const file of validFiles) {
    const item: BatchUploadItem = {
      fileName: file.name,
      fileSize: file.size,
      fileType: file.name.split('.').pop() || '',
      status: 'success',
    }
    try {
      const formData = new FormData()
      formData.append('file', file)
      const resp = await api.post(P_att.upload(projectId.value), formData)
      const att = resp ?? {}
      item.attachmentId = att.id
      item.previewUrl = att.id ? P_att.preview(att.id) : ''
      if (att.ocr_text || att.ocr_status === 'completed') {
        item.status = 'ocr_pending'
        item.ocrText = att.ocr_text || ''
        item.confidence = att.ocr_confidence
      }
    } catch (err: any) {
      item.status = 'failed'
      item.error = err?.response?.data?.detail || err?.message || '上传失败'
    }
    results.push(item)
  }
  batchItems.value = results
  batchResultVisible.value = true
  await loadAttachments()
}

/** 触发隐藏的文件夹选择 input */
function triggerFolderUpload() {
  folderInputRef.value?.click()
}

/** 文件夹选择后批量上传 */
async function onFolderSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (!files || files.length === 0) return

  const validFiles = Array.from(files).filter(beforeUpload)
  if (validFiles.length === 0) {
    ElMessage.warning('所选文件夹中没有支持的文件类型')
    input.value = ''
    return
  }

  ElMessage.info(`正在上传 ${validFiles.length} 个文件...`)
  const results: BatchUploadItem[] = []

  for (const file of validFiles) {
    const item: BatchUploadItem = {
      fileName: file.name,
      fileSize: file.size,
      fileType: file.name.split('.').pop() || '',
      status: 'success',
    }
    try {
      const formData = new FormData()
      formData.append('file', file)
      const resp = await api.post(P_att.upload(projectId.value), formData)
      const att = resp ?? {}
      item.attachmentId = att.id
      item.previewUrl = att.id ? P_att.preview(att.id) : ''
      if (att.ocr_text || att.ocr_status === 'completed') {
        item.status = 'ocr_pending'
        item.ocrText = att.ocr_text || ''
        item.confidence = att.ocr_confidence
      }
    } catch (err: any) {
      item.status = 'failed'
      item.error = err?.response?.data?.detail || err?.message || '上传失败'
    }
    results.push(item)
  }

  // 显示批量结果台账
  batchItems.value = results
  batchResultVisible.value = true
  await loadAttachments()
  input.value = ''
}

// ─── API ───
async function searchWorkpapers(query: string) {
  if (!query || query.length < 1) { wpSearchResults.value = []; return }
  wpSearchLoading.value = true
  try {
    const data = await api.get(P_wp.wpIndex(projectId.value))
    const items = Array.isArray(data) ? data : data ?? []
    const q = query.toLowerCase()
    wpSearchResults.value = items.filter((w: any) =>
      (w.wp_code || '').toLowerCase().includes(q) ||
      (w.wp_name || '').toLowerCase().includes(q)
    ).slice(0, 20)
  } catch { wpSearchResults.value = [] }
  finally { wpSearchLoading.value = false }
}

async function loadAttachments() {
  loading.value = true
  try {
    const params: any = {}
    if (filterType.value) params.file_type = filterType.value
    const data = await api.get(P_att.list(projectId.value), { params })
    attachments.value = data ?? []
  } catch { attachments.value = [] }
  finally { loading.value = false }
}

async function onSearch() {
  if (!searchQuery.value) { loadAttachments(); return }
  loading.value = true
  try {
    const data = await api.get(P_att.search, {
      params: { project_id: projectId.value, q: searchQuery.value },
    })
    attachments.value = data ?? []
  } catch { attachments.value = [] }
  finally { loading.value = false }
}

function preview(row: any) {
  previewUrl.value = P_att.preview(row.id)
  previewName.value = row.file_name
  previewType.value = row.file_type
  previewVisible.value = true
}

async function download(row: any) {
  try { await downloadFile(P_att.download(row.id)) }
  catch (e: any) { handleApiError(e, '下载') }
}

function associateDialog(row: any) {
  associateAttachmentId.value = row.id
  associateWpId.value = ''
  associateNotes.value = ''
  associateVisible.value = true
}

async function submitAssociate() {
  if (!associateWpId.value) { ElMessage.warning('请选择底稿'); return }
  try {
    await api.post(P_att.associate(associateAttachmentId.value), {
      wp_id: associateWpId.value,
      association_type: associateType.value,
      notes: associateNotes.value || undefined,
    })
    ElMessage.success('关联成功')
    associateVisible.value = false
    await loadAttachments()
  } catch (e: any) { handleApiError(e, '关联') }
}

function jumpToWorkpaper(row: any) {
  if (row.wp_id) {
    router.push(`/projects/${projectId.value}/workpapers/${row.wp_id}`)
  }
}

function beforeUpload(file: File) {
  const maxSize = 50 * 1024 * 1024
  if (file.size > maxSize) { ElMessage.warning(`"${file.name}" 超过 50MB 限制`); return false }
  // 验证文件扩展名
  const ext = file.name.includes('.') ? '.' + file.name.split('.').pop()!.toLowerCase() : ''
  const allowedExts = ACCEPT_TYPES.split(',')
  if (ext && !allowedExts.includes(ext)) {
    ElMessage.warning(`"${file.name}" 文件类型不支持（${ext}）`)
    return false
  }
  // 跳过隐藏文件（文件夹上传时常见 .DS_Store / Thumbs.db）
  if (file.name.startsWith('.') || file.name === 'Thumbs.db' || file.name === 'desktop.ini') {
    return false
  }
  return true
}

async function uploadAttachment(options: any) {
  const formData = new FormData()
  formData.append('file', options.file)
  try {
    const resp = await api.post(P_att.upload(projectId.value), formData)
    ElMessage.success('上传成功')
    await loadAttachments()
    // 如果返回了 OCR 结果（同步识别），弹出确认窗
    const att = resp ?? {}
    if (att.ocr_text || att.ocr_status === 'completed') {
      ocrConfirmPayload.value = {
        attachmentId: att.id,
        fileName: att.file_name || options.file.name,
        fileType: att.file_type || '',
        previewUrl: P_att.preview(att.id),
        ocrText: att.ocr_text || '',
        confidence: att.ocr_confidence,
      }
      ocrConfirmVisible.value = true
    }
  } catch (error) {
    handleApiError(error, '上传')
  }
}

function onOcrConfirmed() {
  loadAttachments()
}

function onOcrRejected() {
  // 用户放弃识别结果，刷新列表即可
  loadAttachments()
}

/** 从列表打开异步 OCR 结果确认（针对上传时未同步返回 OCR 的场景） */
function openOcrConfirm(row: any) {
  ocrConfirmPayload.value = {
    attachmentId: row.id,
    fileName: row.file_name,
    fileType: row.file_type || '',
    previewUrl: P_att.preview(row.id),
    ocrText: row.ocr_text || '',
    confidence: row.ocr_confidence,
  }
  ocrConfirmVisible.value = true
}

async function retryOCR(row: any) {
  try {
    await api.put(P_att.ocrStatus(row.id), { status: 'pending' })
    ElMessage.success('已重新提交 OCR 识别')
    await loadAttachments()
  } catch (e: any) { handleApiError(e, '重试') }
}

// ─── Helpers ───
function formatSize(bytes: number): string {
  if (!bytes) return '0'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

function formatDate(d: string): string {
  if (!d) return '-'
  const date = new Date(d)
  return `${date.getMonth() + 1}月${date.getDate()}日`
}

function getFileCategory(type: string): string {
  if (!type) return 'other'
  const t = type.toLowerCase()
  if (t.includes('pdf')) return 'pdf'
  if (t.includes('doc') || t.includes('word')) return 'word'
  if (t.includes('xls') || t.includes('excel')) return 'excel'
  if (t.includes('ppt') || t.includes('powerpoint')) return 'ppt'
  if (t.includes('png') || t.includes('jpg') || t.includes('jpeg') || t.includes('gif') || t.includes('bmp') || t.includes('webp') || t.includes('tif') || t.includes('heic') || t.includes('image')) return 'image'
  if (t.includes('txt') || t.includes('csv') || t.includes('md') || t.includes('text')) return 'text'
  if (t.includes('zip') || t.includes('rar') || t.includes('7z') || t.includes('archive')) return 'archive'
  if (t.includes('eml') || t.includes('msg') || t.includes('email')) return 'email'
  if (t.includes('ofd') || t.includes('dwg')) return 'ofd'
  return 'other'
}

function getFileEmoji(type: string): string {
  const cat = getFileCategory(type)
  const map: Record<string, string> = { pdf: '📕', word: '📘', excel: '📗', ppt: '📙', image: '🖼️', text: '📝', archive: '📦', email: '✉️', ofd: '📐', other: '📄' }
  return map[cat] || '📄'
}

function typeTagType(t: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const m: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = { pdf: 'danger', docx: '', doc: '', xlsx: 'success', xls: 'success', image: 'warning', png: 'warning', jpg: 'warning' }
  return m[t?.toLowerCase()] || 'info'
}

function ocrTagType(s: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const m: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = { pending: 'info', processing: 'warning', completed: 'success', failed: 'danger' }
  return m[s] || 'info'
}

function ocrLabel(s: string): string {
  const m: Record<string, string> = { pending: '待识别', processing: '识别中', completed: '已完成', failed: '失败' }
  return m[s] || s || ''
}

/** 从索引芯片（GtIndexChip Layer-4）跳转过来时 ?id= 定位：高亮 + 滚动到目标附件 */
async function locateFromQuery() {
  const targetId = (route.query.id as string) || ''
  if (!targetId) return
  // 目标可能被类型筛选挡住 → 先清筛选保证在列表中
  if (filterType.value) { filterType.value = ''; await loadAttachments() }
  const exists = attachments.value.some(a => String(a.id) === String(targetId))
  if (!exists) return
  highlightId.value = targetId
  await nextTick()
  const el = document.querySelector(`[data-att-id="${targetId}"]`)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  // 用 history.replaceState 清掉 ?id=（DefaultLayout router-view 以 fullPath 为 key，
  // 用 router.replace 会整页重挂载 → 丢定位）
  const url = new URL(window.location.href)
  url.searchParams.delete('id')
  window.history.replaceState(window.history.state, '', url.pathname + url.search + url.hash)
  if (highlightTimer) clearTimeout(highlightTimer)
  highlightTimer = setTimeout(() => { highlightId.value = '' }, 3000)
}

onMounted(async () => {
  await loadAttachments()
  await locateFromQuery()
})

// ─── SSE 实时同步：监听其他入口上传的附件 ───
let sseSource: EventSource | null = null
onMounted(() => {
  try {
    sseSource = new EventSource(`/api/sse/projects/${projectId.value}`)
    sseSource.addEventListener('attachment.uploaded', () => {
      loadAttachments()
    })
  } catch { /* SSE 不可用时静默降级 */ }
})
onUnmounted(() => {
  sseSource?.close()
  if (highlightTimer) clearTimeout(highlightTimer)
})
</script>

<style scoped>
.gt-attachment-page {
  padding: 24px;
  position: relative;
  min-height: 100%;
}

/* ─── 拖拽遮罩 ─── */
.gt-att-dropzone {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(75, 45, 119, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(4px);
}
.gt-att-dropzone-inner {
  text-align: center;
  color: #fff;
  animation: gt-pulse 1.5s ease-in-out infinite;
}
.gt-att-dropzone-icon { font-size: 56px; margin-bottom: 12px; }
.gt-att-dropzone-text { font-size: 20px; font-weight: 600; }
.gt-att-dropzone-hint { font-size: 13px; opacity: 0.8; margin-top: 6px; }

@keyframes gt-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.03); opacity: 0.9; }
}

/* ─── 顶部区 ─── */
.gt-att-top { margin-bottom: 24px; }
.gt-att-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}
.gt-att-title-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.gt-att-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--gt-color-text-primary);
}
.gt-att-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.gt-att-search { width: 220px; }
.gt-att-type-filter { width: 120px; }

/* ─── 统计卡片 ─── */
.gt-att-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.gt-att-stat-card {
  background: var(--gt-color-bg-white, #fff);
  border: 1px solid var(--gt-color-border-light, #eee);
  border-radius: 12px;
  padding: 16px 20px;
  text-align: center;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.gt-att-stat-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(75, 45, 119, 0.1);
  border-color: var(--gt-purple-light, #d8b8ee);
}
.gt-att-stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--gt-color-text-primary);
  line-height: 1.2;
}
.gt-att-stat-value--success { color: #67C23A; }
.gt-att-stat-value--purple { color: var(--gt-purple, #4b2d77); }
.gt-att-stat-label {
  font-size: 12px;
  color: var(--gt-color-text-tertiary);
  margin-top: 4px;
}

/* ─── 文件列表 ─── */
.gt-att-body { min-height: 200px; }
.gt-att-list { display: flex; flex-direction: column; gap: 8px; }

.gt-att-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 18px;
  background: var(--gt-color-bg-white, #fff);
  border: 1px solid var(--gt-color-border-light, #eee);
  border-radius: 10px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  animation: gt-slide-in 0.3s ease-out both;
  animation-delay: var(--delay, 0s);
}
.gt-att-item:hover {
  border-color: var(--gt-purple-light, #d8b8ee);
  box-shadow: 0 4px 16px rgba(75, 45, 119, 0.08);
  transform: translateX(4px);
}
.gt-att-item--highlight {
  border-color: var(--gt-color-primary, #4b2d77);
  background: var(--gt-color-primary-bg, #f4f0fa);
  box-shadow: 0 0 0 2px rgba(75, 45, 119, 0.18);
  animation: gt-att-highlight-pulse 1.2s ease-in-out 2;
}
@keyframes gt-att-highlight-pulse {
  0%, 100% { box-shadow: 0 0 0 2px rgba(75, 45, 119, 0.18); }
  50% { box-shadow: 0 0 0 5px rgba(75, 45, 119, 0.28); }
}

/* 文件类型图标 */
.gt-att-item-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  flex-shrink: 0;
  transition: transform 0.2s;
}
.gt-att-item:hover .gt-att-item-icon { transform: scale(1.1) rotate(-3deg); }
.gt-att-icon--pdf { background: rgba(245, 108, 108, 0.12); }
.gt-att-icon--word { background: rgba(64, 158, 255, 0.12); }
.gt-att-icon--excel { background: rgba(103, 194, 58, 0.12); }
.gt-att-icon--ppt { background: rgba(230, 162, 60, 0.12); }
.gt-att-icon--image { background: rgba(230, 162, 60, 0.12); }
.gt-att-icon--text { background: rgba(144, 147, 153, 0.08); }
.gt-att-icon--archive { background: rgba(144, 147, 153, 0.12); }
.gt-att-icon--email { background: rgba(64, 158, 255, 0.08); }
.gt-att-icon--ofd { background: rgba(103, 194, 58, 0.08); }
.gt-att-icon--other { background: rgba(144, 147, 153, 0.1); }

/* 信息区 */
.gt-att-item-info { flex: 1; min-width: 0; }
.gt-att-item-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-text-primary);
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: color 0.15s;
}
.gt-att-item-name:hover { color: var(--gt-purple, #4b2d77); }
.gt-att-item-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--gt-color-text-tertiary);
}
.gt-att-item-size { min-width: 50px; }

/* 溯源跳转 chip */
.gt-att-lineage-chip {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 1px 8px;
  border-radius: 12px;
  background: var(--gt-purple-light, #f4f0fa);
  color: var(--gt-purple, #4b2d77);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}
.gt-att-lineage-chip:hover {
  background: var(--gt-purple, #4b2d77);
  color: #fff;
  transform: translateX(2px);
}
.gt-att-lineage-arrow { transition: transform 0.2s; }
.gt-att-lineage-chip:hover .gt-att-lineage-arrow { transform: translateX(3px); }

/* 状态 */
.gt-att-item-status { min-width: 60px; text-align: center; }
.gt-att-pending-badge { cursor: pointer; transition: transform 0.2s; }
.gt-att-pending-badge:hover { transform: scale(1.1); }

/* 操作按钮 */
.gt-att-item-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}
.gt-att-item:hover .gt-att-item-actions { opacity: 1; }

/* ─── 空状态 ─── */
.gt-att-empty {
  text-align: center;
  padding: 60px 20px;
  color: var(--gt-color-text-tertiary);
}
.gt-att-empty-icon { font-size: 56px; margin-bottom: 12px; animation: gt-float 3s ease-in-out infinite; }
.gt-att-empty-title { font-size: 16px; font-weight: 600; color: var(--gt-color-text-secondary); margin-bottom: 6px; }
.gt-att-empty-desc { font-size: 13px; }

@keyframes gt-float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}

/* ─── 列表动画 ─── */
@keyframes gt-slide-in {
  from { opacity: 0; transform: translateX(-12px); }
  to { opacity: 1; transform: translateX(0); }
}

.gt-list-enter-active { animation: gt-slide-in 0.3s ease-out; }
.gt-list-leave-active { animation: gt-slide-in 0.2s ease-in reverse; }
.gt-list-move { transition: transform 0.3s ease; }

/* ─── Fade 过渡 ─── */
.gt-fade-enter-active, .gt-fade-leave-active { transition: opacity 0.25s; }
.gt-fade-enter-from, .gt-fade-leave-to { opacity: 0; }

/* ─── 响应式 ─── */
.gt-att-hidden-input { display: none; }

@media (max-width: 768px) {
  .gt-att-stats { grid-template-columns: repeat(2, 1fr); }
  .gt-att-title-row { flex-direction: column; align-items: flex-start; }
  .gt-att-actions { flex-wrap: wrap; }
}
</style>
