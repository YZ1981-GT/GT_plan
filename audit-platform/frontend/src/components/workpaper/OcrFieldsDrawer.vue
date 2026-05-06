<template>
  <el-drawer
    v-model="visible"
    title="📄 从附件 OCR 提取"
    direction="rtl"
    size="50%"
    :before-close="handleClose"
    class="ocr-fields-drawer"
  >
    <!-- 步骤 1：选择附件 -->
    <div v-if="step === 'select'" class="ocr-step-select">
      <p class="ocr-step-hint">选择一个关联附件进行 OCR 字段提取：</p>
      <el-table
        :data="attachments"
        size="small"
        stripe
        border
        highlight-current-row
        @current-change="onAttachmentSelect"
        style="width: 100%"
        max-height="400"
      >
        <el-table-column prop="file_name" label="文件名" min-width="200" show-overflow-tooltip />
        <el-table-column prop="file_type" label="类型" width="100" />
        <el-table-column label="OCR 状态" width="120">
          <template #default="{ row }">
            <el-tag
              :type="ocrStatusTagType(row.ocr_status)"
              size="small"
            >
              {{ ocrStatusLabel(row.ocr_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              link
              @click="onExtractFields(row)"
            >
              提取字段
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty
        v-if="attachments.length === 0 && !loadingAttachments"
        description="当前底稿无关联附件"
      />
      <div v-if="loadingAttachments" class="ocr-loading">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
        <span>加载附件列表...</span>
      </div>
    </div>

    <!-- 步骤 2：OCR 处理中 -->
    <div v-else-if="step === 'processing'" class="ocr-step-processing">
      <div class="ocr-loading">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <p>正在进行 OCR 识别，请稍候...</p>
        <p class="ocr-loading-hint">{{ pollingMessage }}</p>
      </div>
    </div>

    <!-- 步骤 3：字段预览 + 填入 -->
    <div v-else-if="step === 'fields'" class="ocr-step-fields">
      <div class="ocr-fields-header">
        <span class="ocr-fields-title">
          📋 识别结果 — {{ selectedAttachment?.file_name }}
        </span>
        <el-button size="small" text @click="step = 'select'">← 返回选择</el-button>
      </div>

      <el-table
        :data="fieldList"
        size="small"
        stripe
        border
        style="width: 100%; margin-top: 12px"
      >
        <el-table-column prop="label" label="字段名" width="140" />
        <el-table-column prop="value" label="识别值" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="160" align="center">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              @click="onFillCell(row)"
            >
              填入当前单元格
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 差异预览确认对话框 -->
      <el-dialog
        v-model="diffDialogVisible"
        title="填入确认"
        width="420px"
        :close-on-click-modal="false"
      >
        <div class="ocr-diff-preview">
          <div class="ocr-diff-row">
            <span class="ocr-diff-label">目标单元格：</span>
            <span class="ocr-diff-value">{{ currentCellRef || '未选中' }}</span>
          </div>
          <div class="ocr-diff-row">
            <span class="ocr-diff-label">当前值：</span>
            <span class="ocr-diff-value ocr-diff-old">{{ currentCellValue ?? '（空）' }}</span>
          </div>
          <div class="ocr-diff-row">
            <span class="ocr-diff-label">新值：</span>
            <span class="ocr-diff-value ocr-diff-new">{{ pendingFillField?.value ?? '' }}</span>
          </div>
          <div class="ocr-diff-row">
            <span class="ocr-diff-label">来源：</span>
            <span class="ocr-diff-value">OCR · {{ selectedAttachment?.file_name }} · {{ pendingFillField?.key }}</span>
          </div>
        </div>
        <template #footer>
          <el-button @click="diffDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="confirmFill">确认填入</el-button>
        </template>
      </el-dialog>
    </div>

    <!-- 步骤 4：错误 -->
    <div v-else-if="step === 'error'" class="ocr-step-error">
      <el-empty :description="errorMessage">
        <el-button type="primary" size="small" @click="step = 'select'">返回重试</el-button>
      </el-empty>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'

/**
 * OcrFieldsDrawer — OCR 字段提取抽屉
 *
 * 需求 12：从附件 OCR 提取字段并填入单元格
 * - 列出底稿关联附件
 * - 选择附件后调 POST /api/attachments/{id}/ocr-fields
 * - 若 ocr_status != completed，轮询等待
 * - 展示字段预览 + 填入按钮
 * - 填入前显示差异预览（现值→新值），确认后写入
 * - 填入时 cell_provenance 记 source='ocr', source_ref='attachment:{id}:{field_name}'
 *
 * Validates: Requirements 12
 */

interface OcrField {
  key: string
  label: string
  value: string
}

interface AttachmentItem {
  id: string
  file_name: string
  file_type: string
  ocr_status: string | null
}

const props = defineProps<{
  projectId: string
  wpId: string
  /** 当前选中单元格引用 */
  currentCellRef: string | null
  /** 当前选中单元格值 */
  currentCellValue: any
}>()

const emit = defineEmits<{
  /** 填入单元格事件 */
  (e: 'fill-cell', payload: {
    value: string
    provenance: {
      source: 'ocr'
      source_ref: string
      filled_at: string
      filled_by_service_version: string
    }
  }): void
}>()

type Step = 'select' | 'processing' | 'fields' | 'error'

const visible = ref(false)
const step = ref<Step>('select')
const attachments = ref<AttachmentItem[]>([])
const loadingAttachments = ref(false)
const selectedAttachment = ref<AttachmentItem | null>(null)
const ocrFields = ref<Record<string, string>>({})
const errorMessage = ref('')
const pollingMessage = ref('')
const diffDialogVisible = ref(false)
const pendingFillField = ref<OcrField | null>(null)

// OCR 字段中文标签映射
const FIELD_LABELS: Record<string, string> = {
  buyer_name: '购买方名称',
  seller_name: '销售方名称',
  amount: '金额',
  tax_amount: '税额',
  total_amount: '价税合计',
  invoice_date: '开票日期',
  invoice_no: '发票号码',
  invoice_code: '发票代码',
  bank_name: '银行名称',
  account_no: '账号',
  transaction_date: '交易日期',
  transaction_amount: '交易金额',
  payer: '付款方',
  payee: '收款方',
  remark: '备注',
}

/** 将 ocrFields 对象转为列表 */
const fieldList = computed<OcrField[]>(() => {
  return Object.entries(ocrFields.value).map(([key, value]) => ({
    key,
    label: FIELD_LABELS[key] || key,
    value: String(value ?? ''),
  }))
})

/** 打开抽屉 */
async function open() {
  visible.value = true
  step.value = 'select'
  selectedAttachment.value = null
  ocrFields.value = {}
  errorMessage.value = ''
  await loadAttachments()
}

/** 加载底稿关联附件列表 */
async function loadAttachments() {
  loadingAttachments.value = true
  try {
    const data = await api.get(
      `/api/working-papers/${props.wpId}/attachments`,
      { validateStatus: (s: number) => s < 600 },
    )
    const items: any[] = Array.isArray(data) ? data : (data?.items || [])
    attachments.value = items.map((item: any) => ({
      id: item.id || item.attachment_id,
      file_name: item.file_name || item.filename || '未命名',
      file_type: item.file_type || item.content_type || '未知',
      ocr_status: item.ocr_status || null,
    }))
  } catch {
    attachments.value = []
    ElMessage.error('加载附件列表失败')
  } finally {
    loadingAttachments.value = false
  }
}

/** 选择附件 */
function onAttachmentSelect(row: AttachmentItem | null) {
  selectedAttachment.value = row
}

/** 提取字段 */
async function onExtractFields(attachment: AttachmentItem) {
  selectedAttachment.value = attachment
  step.value = 'processing'
  pollingMessage.value = '正在调用 OCR 服务...'

  try {
    const data = await api.post(
      `/api/attachments/${attachment.id}/ocr-fields`,
      {},
      { validateStatus: (s: number) => s < 600 },
    )

    // 检查响应状态
    if (data?.status === 'completed' || data?.fields) {
      // 直接返回了结果（缓存命中或已完成）
      ocrFields.value = data.fields || {}
      step.value = 'fields'
      return
    }

    if (data?.status === 'processing' && data?.job_id) {
      // 异步处理中，需要轮询
      await pollOcrJob(data.job_id)
      return
    }

    // 其他错误情况
    if (data?.detail || data?.error) {
      errorMessage.value = data.detail || data.error || 'OCR 提取失败'
      step.value = 'error'
      return
    }

    // 兜底：尝试当作 fields 处理
    if (typeof data === 'object' && data !== null) {
      ocrFields.value = data
      step.value = 'fields'
    } else {
      errorMessage.value = 'OCR 返回格式异常'
      step.value = 'error'
    }
  } catch (err: any) {
    errorMessage.value = 'OCR 提取失败: ' + (err?.message || '未知错误')
    step.value = 'error'
  }
}

/** 轮询 OCR 任务状态 */
async function pollOcrJob(jobId: string) {
  const MAX_POLLS = 30
  const POLL_INTERVAL = 2000 // 2 秒

  for (let i = 0; i < MAX_POLLS; i++) {
    pollingMessage.value = `正在处理中... (${i + 1}/${MAX_POLLS})`

    await sleep(POLL_INTERVAL)

    try {
      const data = await api.get(
        `/api/ocr-jobs/${jobId}`,
        { validateStatus: (s: number) => s < 600 },
      )

      if (data?.status === 'completed') {
        ocrFields.value = data.fields || data.result?.fields || {}
        step.value = 'fields'
        return
      }

      if (data?.status === 'failed') {
        errorMessage.value = data.error || 'OCR 处理失败'
        step.value = 'error'
        return
      }

      // 继续轮询（pending/processing）
    } catch {
      // 网络错误，继续重试
    }
  }

  // 超时
  errorMessage.value = 'OCR 处理超时，请稍后重试'
  step.value = 'error'
}

/** 点击"填入当前单元格" */
function onFillCell(field: OcrField) {
  if (!props.currentCellRef) {
    ElMessage.warning('请先在底稿中选中一个单元格')
    return
  }
  // 显示差异预览对话框
  pendingFillField.value = field
  diffDialogVisible.value = true
}

/** 确认填入 */
function confirmFill() {
  if (!pendingFillField.value || !selectedAttachment.value) return

  const field = pendingFillField.value
  const attachmentId = selectedAttachment.value.id

  emit('fill-cell', {
    value: field.value,
    provenance: {
      source: 'ocr',
      source_ref: `attachment:${attachmentId}:${field.key}`,
      filled_at: new Date().toISOString(),
      filled_by_service_version: 'ocr_v1',
    },
  })

  diffDialogVisible.value = false
  pendingFillField.value = null
  ElMessage.success(`已将"${field.label}"填入 ${props.currentCellRef}`)
}

function handleClose(done: () => void) {
  done()
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}

/** OCR 状态标签类型 */
function ocrStatusTagType(status: string | null): 'success' | 'warning' | 'info' | 'primary' | 'danger' | undefined {
  const map: Record<string, 'success' | 'warning' | 'info' | 'primary' | 'danger'> = {
    completed: 'success',
    processing: 'warning',
    pending: 'info',
    failed: 'danger',
  }
  return map[status || ''] || 'info'
}

/** OCR 状态标签文案 */
function ocrStatusLabel(status: string | null): string {
  const map: Record<string, string> = {
    completed: '已完成',
    processing: '处理中',
    pending: '待处理',
    failed: '失败',
  }
  return map[status || ''] || '未识别'
}

/** 检查底稿是否有关联附件（供父组件判断右键菜单可见性） */
async function hasAttachments(): Promise<boolean> {
  try {
    const data = await api.get(
      `/api/working-papers/${props.wpId}/attachments`,
      { validateStatus: (s: number) => s < 600 },
    )
    const items: any[] = Array.isArray(data) ? data : (data?.items || [])
    return items.length > 0
  } catch {
    return false
  }
}

// 暴露方法供父组件调用
defineExpose({ open, hasAttachments })
</script>

<style scoped>
.ocr-fields-drawer :deep(.el-drawer__header) {
  margin-bottom: 0;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.ocr-step-hint {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 12px;
}

.ocr-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  gap: 12px;
  color: #999;
}

.ocr-loading-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.ocr-step-processing {
  padding: 40px 20px;
}

.ocr-step-error {
  padding: 40px 20px;
}

.ocr-fields-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.ocr-fields-title {
  font-weight: 600;
  font-size: 14px;
}

/* 差异预览 */
.ocr-diff-preview {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}

.ocr-diff-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 13px;
}

.ocr-diff-label {
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  min-width: 80px;
}

.ocr-diff-value {
  color: var(--el-text-color-primary);
  word-break: break-all;
}

.ocr-diff-old {
  text-decoration: line-through;
  color: var(--el-color-danger);
}

.ocr-diff-new {
  color: var(--el-color-success);
  font-weight: 600;
}
</style>
