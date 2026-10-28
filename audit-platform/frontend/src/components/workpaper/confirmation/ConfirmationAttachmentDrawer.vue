<template>
  <el-drawer
    :model-value="visible"
    :title="`附件管理 — ${counterpartyName}`"
    direction="rtl"
    size="480px"
    @close="emit('update:visible', false)"
    append-to-body
  >
    <!-- 上传区（只读时不显示：复核 / 已归档只能查看，spec attachment-confirmation-evidence-loop 需求 1.3） -->
    <div v-if="!readonly" class="gt-ca-drawer__upload-section">
      <div class="gt-ca-drawer__upload-row">
        <span class="gt-ca-drawer__upload-label">角色</span>
        <el-select v-model="uploadRole" size="small" style="width:120px">
          <el-option label="发函件" value="outbound" />
          <el-option label="回函件" value="inbound" />
        </el-select>

        <!-- 回函件选配对发函件 -->
        <template v-if="uploadRole === 'inbound' && outboundList.length > 0">
          <span class="gt-ca-drawer__upload-label" style="margin-left:12px">配对发函件</span>
          <el-select
            v-model="pairedOutboundId"
            size="small"
            style="width:180px"
            :placeholder="outboundList.length === 1 ? '自动配对' : '请选择发函件'"
          >
            <el-option
              v-for="att in outboundList"
              :key="att.link_id"
              :label="att.file_name"
              :value="att.attachment_id"
            />
          </el-select>
        </template>
      </div>

      <el-upload
        action=""
        :before-upload="handleBeforeUpload"
        :show-file-list="false"
        :disabled="uploadRole === 'inbound' && outboundList.length === 0"
      >
        <el-button
          type="primary"
          size="small"
          :disabled="uploadRole === 'inbound' && outboundList.length === 0"
        >
          上传{{ uploadRole === 'outbound' ? '发函件' : '回函件' }}
        </el-button>
      </el-upload>
      <div v-if="uploadRole === 'inbound' && outboundList.length === 0" class="gt-ca-drawer__hint-warn">
        请先上传发函件后，才能上传回函件
      </div>
    </div>

    <el-divider v-if="!readonly" />

    <!-- 发函件列表 -->
    <div class="gt-ca-drawer__section">
      <h4 class="gt-ca-drawer__section-title">
        <el-tag type="primary" size="small" effect="dark">发函件</el-tag>
        <span class="gt-ca-drawer__count">{{ outboundList.length }} 份</span>
      </h4>
      <div v-if="outboundList.length === 0" class="gt-ca-drawer__empty">暂无发函件</div>
      <div v-for="att in outboundList" :key="att.link_id" class="gt-ca-drawer__item">
        <div class="gt-ca-drawer__item-info">
          <span class="gt-ca-drawer__filename" :title="att.file_name">{{ att.file_name }}</span>
          <span class="gt-ca-drawer__time">{{ formatTime(att.upload_time || att.link_created_at) }}</span>
        </div>
        <div class="gt-ca-drawer__item-actions">
          <el-button link type="primary" size="small" @click="handlePreview(att)">预览</el-button>
          <el-button v-if="!readonly" link type="danger" size="small" @click="handleUnlink(att)">解绑</el-button>
        </div>
      </div>
    </div>

    <!-- 回函件列表 -->
    <div class="gt-ca-drawer__section">
      <h4 class="gt-ca-drawer__section-title">
        <el-tag type="success" size="small" effect="dark">回函件</el-tag>
        <span class="gt-ca-drawer__count">{{ inboundList.length }} 份</span>
      </h4>
      <div v-if="inboundList.length === 0" class="gt-ca-drawer__empty">暂无回函件</div>
      <div v-for="att in inboundList" :key="att.link_id" class="gt-ca-drawer__item-wrapper">
        <div class="gt-ca-drawer__item">
          <div class="gt-ca-drawer__item-info">
            <span class="gt-ca-drawer__filename" :title="att.file_name">{{ att.file_name }}</span>
            <span class="gt-ca-drawer__time">{{ formatTime(att.upload_time || att.link_created_at) }}</span>
          </div>
          <div class="gt-ca-drawer__item-tags">
            <el-tag v-if="pairedOutboundName(att)" type="info" size="small" effect="plain">
              配对：{{ pairedOutboundName(att) }}
            </el-tag>
            <el-tag :type="ocrTagType(att.ocr_status)" size="small" effect="plain" data-testid="ocr-status">
              {{ ocrLabel(att.ocr_status) }}
            </el-tag>
          </div>
          <div class="gt-ca-drawer__item-actions">
            <el-button link type="primary" size="small" @click="handlePreview(att)">预览</el-button>
            <el-button
              v-if="!readonly"
              link
              type="warning"
              size="small"
              :loading="ocrLoadingMap[att.attachment_id]"
              title="没有识别文本时先识别原件，再与账面金额比对（结果需人工确认）"
              @click="handleTriggerOcr(att)"
            >识别比对</el-button>
            <el-button v-if="!readonly" link type="danger" size="small" @click="handleUnlink(att)">解绑</el-button>
          </div>
        </div>

        <!-- OCR 比对结果面板 -->
        <div v-if="!readonly && ocrResultMap[att.attachment_id]" class="gt-ca-drawer__ocr-panel">
          <div class="gt-ca-drawer__ocr-advisory">AI辅助·待人工确认</div>

          <!-- 比对结论标签 -->
          <div class="gt-ca-drawer__ocr-verdict">
            <el-tag
              :type="verdictTagType(ocrResultMap[att.attachment_id].match_verdict)"
              size="small"
              effect="dark"
            >
              {{ verdictLabel(ocrResultMap[att.attachment_id].match_verdict) }}
            </el-tag>
            <span v-if="ocrResultMap[att.attachment_id].counterparty_mismatch" class="gt-ca-drawer__ocr-warn-entity">
              ⚠️ 主体名称不一致，请核对
            </span>
          </div>

          <!-- 低置信度警告 -->
          <div
            v-if="ocrResultMap[att.attachment_id].confidence === 'low'"
            class="gt-ca-drawer__ocr-warn-low"
          >
            ⚠️ 置信度低，建议人工逐份核对原始影像
          </div>

          <!-- 识别结果详情 -->
          <div class="gt-ca-drawer__ocr-details">
            <div class="gt-ca-drawer__ocr-row">
              <span class="gt-ca-drawer__ocr-label">回函金额：</span>
              <span class="gt-ca-drawer__ocr-value">{{ ocrResultMap[att.attachment_id].reply_amount ?? '—' }}</span>
            </div>
            <div class="gt-ca-drawer__ocr-row">
              <span class="gt-ca-drawer__ocr-label">回函日期：</span>
              <span class="gt-ca-drawer__ocr-value">{{ ocrResultMap[att.attachment_id].reply_date ?? '—' }}</span>
            </div>
            <div class="gt-ca-drawer__ocr-row">
              <span class="gt-ca-drawer__ocr-label">回函主体：</span>
              <span class="gt-ca-drawer__ocr-value">{{ ocrResultMap[att.attachment_id].reply_entity ?? '—' }}</span>
            </div>
            <div v-if="ocrResultMap[att.attachment_id].diff != null" class="gt-ca-drawer__ocr-row">
              <span class="gt-ca-drawer__ocr-label">差异金额：</span>
              <span
                class="gt-ca-drawer__ocr-value"
                :class="{ 'gt-ca-drawer__ocr-diff-warn': Math.abs(ocrResultMap[att.attachment_id].diff) > 0.01 }"
              >{{ ocrResultMap[att.attachment_id].diff }}</span>
            </div>
          </div>

          <!-- 可编辑修正区 -->
          <div class="gt-ca-drawer__ocr-edit">
            <div class="gt-ca-drawer__ocr-edit-row">
              <span class="gt-ca-drawer__ocr-edit-label">确认金额：</span>
              <el-input-number
                v-model="backfillFormMap[att.attachment_id].confirmed_amount"
                :precision="2"
                :controls="false"
                size="small"
                style="width: 160px"
              />
            </div>
            <div class="gt-ca-drawer__ocr-edit-row">
              <span class="gt-ca-drawer__ocr-edit-label">回函日期：</span>
              <el-date-picker
                v-model="backfillFormMap[att.attachment_id].reply_date"
                type="date"
                value-format="YYYY-MM-DD"
                size="small"
                style="width: 160px"
                placeholder="选择日期"
              />
            </div>
            <div class="gt-ca-drawer__ocr-edit-row">
              <span class="gt-ca-drawer__ocr-edit-label">建议状态：</span>
              <el-select
                v-model="backfillFormMap[att.attachment_id].target_status"
                size="small"
                style="width: 160px"
              >
                <el-option label="相符" value="matched" />
                <el-option label="不符" value="discrepancy" />
              </el-select>
            </div>
          </div>

          <!-- 确认回填按钮 -->
          <div class="gt-ca-drawer__ocr-action">
            <el-button
              type="primary"
              size="small"
              :loading="applyLoadingMap[att.attachment_id]"
              @click="handleApplyReply(att)"
            >确认回填</el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 原件预览：已鉴权的预览抽屉（append-to-body，不受本抽屉布局影响） -->
    <AttachmentPreviewDrawer
      v-model="previewOpen"
      :attachment="previewTarget"
      downloadable
      size="min(960px, 72vw)"
    />
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { handleApiError } from '@/utils/errorHandler'
import { parseServerTime } from '@/utils/formatters'
import AttachmentPreviewDrawer, {
  type AttachmentForPreview,
} from '@/components/common/AttachmentPreviewDrawer.vue'
import { toAttachmentPreview } from '@/components/attachment/attachmentPreviewTarget'

interface Props {
  visible: boolean
  confirmationId: string
  projectId: string
  counterpartyName?: string
  /** 只读：只能预览（不显示上传、解绑、识别比对、回填） */
  readonly?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  counterpartyName: '',
  readonly: false,
})

const emit = defineEmits<{
  'update:visible': [val: boolean]
  'updated': []
}>()

// ─── 附件数据 ───

/**
 * 挂载列表接口的真实形状（`confirmation_evidence_service.list_attachments`）。
 * 原先按 `id` / `created_at` / `paired_outbound_file_name` 读：接口没有这三个字段 ⇒ 解绑请求里是 `undefined`、
 * 时间与配对名恒空（spec attachment-confirmation-evidence-loop 需求 1.4）。
 */
interface AttachmentLink {
  link_id: string
  attachment_id: string
  file_name: string
  role: 'outbound' | 'inbound'
  paired_outbound_attachment_id: string | null
  match_status?: string | null
  ocr_status: string | null
  upload_time: string | null
  link_created_at: string | null
}

const attachments = ref<AttachmentLink[]>([])
const loading = ref(false)

const outboundList = computed(() => attachments.value.filter((a) => a.role === 'outbound'))
const inboundList = computed(() => attachments.value.filter((a) => a.role === 'inbound'))

/** 回函件配对的发函件名（在本笔的发函件里查） */
function pairedOutboundName(att: AttachmentLink): string {
  if (!att.paired_outbound_attachment_id) return ''
  return outboundList.value.find((o) => o.attachment_id === att.paired_outbound_attachment_id)?.file_name || ''
}

// ─── 上传 ───

const uploadRole = ref<'outbound' | 'inbound'>('outbound')
const pairedOutboundId = ref<string>('')

async function handleBeforeUpload(file: File): Promise<boolean> {
  // 回函件必须有发函件
  if (uploadRole.value === 'inbound' && outboundList.value.length === 0) {
    ElMessage.warning('请先上传发函件')
    return false
  }

  // 回函件单份发函件时自动配对
  let pairedId = pairedOutboundId.value
  if (uploadRole.value === 'inbound') {
    if (outboundList.value.length === 1) {
      pairedId = outboundList.value[0].attachment_id
    } else if (!pairedId) {
      ElMessage.warning('请选择配对的发函件')
      return false
    }
  }

  try {
    // Step1: 上传附件（复用现有附件上传机制）
    const formData = new FormData()
    formData.append('file', file)
    formData.append('attachment_type', 'confirmation')
    formData.append('reference_type', 'confirmation_list')
    formData.append('reference_id', props.confirmationId)

    const uploadRes: any = await http.post(
      `/api/projects/${props.projectId}/attachments/upload`,
      formData,
    )
    const attachmentId = uploadRes?.data?.id || uploadRes?.id

    if (!attachmentId) {
      ElMessage.error('上传失败：未获取到附件ID')
      return false
    }

    // Step2: 挂载到函证（POST attachments 链接）
    await http.post(
      `/api/projects/${props.projectId}/confirmations/${props.confirmationId}/attachments`,
      {
        attachment_id: attachmentId,
        role: uploadRole.value,
        paired_outbound_id: uploadRole.value === 'inbound' ? pairedId : undefined,
      },
    )

    ElMessage.success(`${uploadRole.value === 'outbound' ? '发函件' : '回函件'}上传成功`)
    await loadAttachments()
    emit('updated')
  } catch (e) {
    handleApiError(e, '上传附件')
  }

  return false // 阻止 el-upload 默认上传
}

// ─── 解绑 ───

async function handleUnlink(att: AttachmentLink) {
  try {
    await ElMessageBox.confirm(
      `确认解绑「${att.file_name}」？解绑后附件不会被物理删除`,
      '解绑确认',
      { confirmButtonText: '确认解绑', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }

  try {
    await http.delete(
      `/api/projects/${props.projectId}/confirmations/${props.confirmationId}/attachments/${att.link_id}`,
    )
    ElMessage.success('已解绑')
    await loadAttachments()
    emit('updated')
  } catch (e) {
    handleApiError(e, '解绑附件')
  }
}

// ─── 预览/下载 ───

// 原先 window.open 了一条不存在的路由（/api/projects/{pid}/attachments/{id}/download），
// 且新标签页带不上 Bearer 头 ⇒ 预览恒失败。改用已鉴权的预览抽屉（spec attachment-security-baseline 任务 12）。
const previewOpen = ref(false)
const previewTarget = ref<AttachmentForPreview | null>(null)

/** 链接行没有 file_type：判型按扩展名（统一构造，spec attachment-inline-preview ADR-AIP-02） */
function handlePreview(att: AttachmentLink) {
  previewTarget.value = toAttachmentPreview({ id: att.attachment_id, file_name: att.file_name })
  previewOpen.value = true
}

// ─── OCR 识别 + 比对 ───

interface OcrCompareResult {
  reply_amount: number | null
  reply_date: string | null
  reply_entity: string | null
  confidence: 'high' | 'medium' | 'low'
  diff: number | null
  match_verdict: 'matched' | 'discrepancy' | 'low_confidence'
  counterparty_mismatch: boolean
  governed: boolean
  requires_human_confirmation: boolean
}

interface BackfillForm {
  confirmed_amount: number | null
  reply_date: string | null
  target_status: 'matched' | 'discrepancy'
}

const ocrResultMap = reactive<Record<string, OcrCompareResult>>({})
const ocrLoadingMap = reactive<Record<string, boolean>>({})
const backfillFormMap = reactive<Record<string, BackfillForm>>({})
const applyLoadingMap = reactive<Record<string, boolean>>({})

/**
 * 识别比对：后端先补识别（没有全文时识别原件并写回），再与账面金额比对（需求 2.1）。
 * `_silent`：自己提示错误；不静默的话全局拦截器会先弹一次，5xx 还会自动重发两次（重复识别）。
 * 成功、失败都重取列表：识别状态（已识别 / 识别失败）以库里为准。
 */
async function handleTriggerOcr(att: AttachmentLink) {
  ocrLoadingMap[att.attachment_id] = true
  try {
    const res: any = await http.post(
      `/api/projects/${props.projectId}/confirmations/attachments/${att.attachment_id}/extract-compare`,
      undefined,
      { _silent: true } as any,
    )
    const data = res?.data ?? res
    ocrResultMap[att.attachment_id] = data

    // 初始化回填表单（OCR 值作默认，用户可修改）
    const suggestedStatus: 'matched' | 'discrepancy' =
      data.diff != null && Math.abs(data.diff) <= 0.01 ? 'matched' : 'discrepancy'

    backfillFormMap[att.attachment_id] = {
      confirmed_amount: data.reply_amount ?? null,
      reply_date: data.reply_date ?? null,
      target_status: suggestedStatus,
    }

    ElMessage.success('识别比对完成，请核对后确认回填')
  } catch (e) {
    delete ocrResultMap[att.attachment_id]
    handleApiError(e, '识别比对')
  } finally {
    ocrLoadingMap[att.attachment_id] = false
    void loadAttachments()
  }
}

// ─── 确认回填 ───

async function handleApplyReply(att: AttachmentLink) {
  const form = backfillFormMap[att.attachment_id]
  if (!form) return

  if (form.confirmed_amount == null) {
    ElMessage.warning('请填写确认金额')
    return
  }

  // 二次确认（涉及金额变更）
  try {
    await ElMessageBox.confirm(
      `确认将回函金额 ${form.confirmed_amount} 回填到台账？状态将置为「${form.target_status === 'matched' ? '相符' : '不符'}」`,
      '确认回填',
      { confirmButtonText: '确认回填', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }

  applyLoadingMap[att.attachment_id] = true
  try {
    await http.post(
      `/api/projects/${props.projectId}/confirmations/${props.confirmationId}/apply-reply`,
      {
        confirmed_amount: form.confirmed_amount,
        reply_date: form.reply_date,
        target_status: form.target_status,
        attachment_id: att.attachment_id,
      },
    )
    ElMessage.success('回填成功')
    await loadAttachments()
    emit('updated')
  } catch (e) {
    handleApiError(e, '确认回填')
  } finally {
    applyLoadingMap[att.attachment_id] = false
  }
}

// ─── OCR 辅助函数 ───

function verdictTagType(verdict: string | undefined): 'success' | 'danger' | 'warning' {
  if (verdict === 'matched') return 'success'
  if (verdict === 'discrepancy') return 'danger'
  return 'warning'
}

function verdictLabel(verdict: string | undefined): string {
  if (verdict === 'matched') return '相符'
  if (verdict === 'discrepancy') return '不符'
  if (verdict === 'low_confidence') return '低置信度'
  return '待识别'
}

// ─── 加载列表 ───

async function loadAttachments() {
  loading.value = true
  try {
    const res: any = await http.get(
      `/api/projects/${props.projectId}/confirmations/${props.confirmationId}/attachments`,
    )
    attachments.value = res?.data?.items ?? res?.items ?? res?.data ?? []
  } catch (e) {
    handleApiError(e, '加载附件列表')
  } finally {
    loading.value = false
  }
}

// ─── 可见性监听 ───

watch(
  () => props.visible,
  (val) => {
    if (val && props.confirmationId) {
      loadAttachments()
      // 重置上传状态
      uploadRole.value = 'outbound'
      pairedOutboundId.value = ''
    }
  },
)

// ─── 辅助函数 ───

function formatTime(ts: string | null): string {
  if (!ts) return ''
  const d = parseServerTime(ts)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** 回函件识别状态（挂载后不自动识别，需求 2.3） */
function ocrTagType(status: string | null): 'warning' | 'success' | 'info' | 'danger' {
  if (status === 'processing') return 'warning'
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  return 'info'
}

function ocrLabel(status: string | null): string {
  if (status === 'processing') return '识别中'
  if (status === 'completed') return '已识别'
  if (status === 'failed') return '识别失败'
  return '未识别'
}
</script>

<style scoped>
.gt-ca-drawer__upload-section {
  padding: 0 0 8px;
}
.gt-ca-drawer__upload-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.gt-ca-drawer__upload-label {
  font-size: 13px;
  color: var(--gt-color-text-secondary, #606266);
}
.gt-ca-drawer__hint-warn {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-color-warning, #e6a23c);
}

.gt-ca-drawer__section {
  margin-bottom: 16px;
}
.gt-ca-drawer__section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
}
.gt-ca-drawer__count {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
  font-weight: 400;
}

.gt-ca-drawer__empty {
  font-size: 13px;
  color: var(--gt-color-text-tertiary, #c0c4cc);
  padding: 8px 0;
}

.gt-ca-drawer__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--el-fill-color-lighter, #f5f7fa);
  margin-bottom: 6px;
  flex-wrap: wrap;
}
.gt-ca-drawer__item-info {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}
.gt-ca-drawer__filename {
  font-size: 13px;
  color: var(--gt-color-text-primary, #303133);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gt-ca-drawer__time {
  font-size: 11px;
  color: var(--gt-color-text-tertiary, #909399);
  margin-top: 2px;
}
.gt-ca-drawer__item-tags {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}
.gt-ca-drawer__item-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}
.gt-ca-drawer__item-actions :deep(.el-button) {
  padding: 0;
  height: auto;
}

/* ─── OCR Panel ─── */
.gt-ca-drawer__item-wrapper {
  margin-bottom: 6px;
}
.gt-ca-drawer__ocr-panel {
  margin: 6px 0 10px;
  padding: 10px 12px;
  border-radius: 6px;
  background: var(--el-fill-color-lighter, #fafafa);
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
  font-size: 13px;
}
.gt-ca-drawer__ocr-advisory {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--el-color-warning-light-9, #fdf6ec);
  color: var(--el-color-warning, #e6a23c);
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 8px;
}
.gt-ca-drawer__ocr-verdict {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.gt-ca-drawer__ocr-warn-entity {
  font-size: 12px;
  color: var(--el-color-warning, #e6a23c);
  font-weight: 500;
}
.gt-ca-drawer__ocr-warn-low {
  font-size: 12px;
  color: var(--el-color-warning, #e6a23c);
  margin-bottom: 6px;
  padding: 4px 8px;
  background: var(--el-color-warning-light-9, #fdf6ec);
  border-radius: 4px;
}
.gt-ca-drawer__ocr-details {
  margin-bottom: 8px;
}
.gt-ca-drawer__ocr-row {
  display: flex;
  align-items: center;
  gap: 4px;
  line-height: 1.8;
}
.gt-ca-drawer__ocr-label {
  color: var(--gt-color-text-secondary, #606266);
  min-width: 70px;
  flex-shrink: 0;
}
.gt-ca-drawer__ocr-value {
  color: var(--gt-color-text-primary, #303133);
  font-weight: 500;
}
.gt-ca-drawer__ocr-diff-warn {
  color: var(--el-color-danger, #f56c6c);
}
.gt-ca-drawer__ocr-edit {
  border-top: 1px dashed var(--el-border-color-lighter, #dcdfe6);
  padding-top: 8px;
  margin-bottom: 8px;
}
.gt-ca-drawer__ocr-edit-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.gt-ca-drawer__ocr-edit-label {
  font-size: 13px;
  color: var(--gt-color-text-secondary, #606266);
  min-width: 70px;
  flex-shrink: 0;
}
.gt-ca-drawer__ocr-action {
  text-align: right;
}
</style>
