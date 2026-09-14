<script setup lang="ts">
/**
 * OcrGovernanceTab — OCR 任务时间线 + 差异确认 + 写回（复用 useOcrGovernance + 三个 OCR 组件）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening (R5/R6)
 */
import { ref, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import { useOcrGovernance, type OcrJob } from '@/composables/useOcrGovernance'
import GtOcrTimeline from '@/components/common/GtOcrTimeline.vue'
import GtOcrConfirmationPanel, { type FieldConfirmation } from '@/components/common/GtOcrConfirmationPanel.vue'
import GtOcrWritebackDialog from '@/components/common/GtOcrWritebackDialog.vue'

const props = defineProps<{ projectId: string; year: number; role: string }>()

const projectIdRef = toRef(props, 'projectId') as any
const yearRef = toRef(props, 'year') as any
const roleRef = toRef(props, 'role') as any
const ocr = useOcrGovernance(projectIdRef, yearRef, roleRef)

// ── submit ──
const attachmentId = ref('')
const versionId = ref('')
const contentHash = ref('')

// ── job view ──
const jobIdInput = ref('')
const job = ref<OcrJob | null>(null)
const transitions = ref<any[]>([])

// ── result / confirmation ──
const resultIdInput = ref('')
const fields = ref<FieldConfirmation[]>([])
const writebackVisible = ref(false)
const mapping = ref<Record<string, string> | null>(null)
const allDecided = ref(false)
const readyForWriteback = ref(false)
const conflictWarning = ref<string | null>(null)
const wbTargetType = ref('workpaper_cell')
const wbTargetId = ref('')

async function submitJob() {
  if (!versionId.value || !contentHash.value) {
    ElMessage.warning('请填写附件版本 ID 与 Content Hash')
    return
  }
  const res = await ocr.submitJob({
    attachment_id: attachmentId.value,
    attachment_version_id: versionId.value,
    content_hash: contentHash.value,
  })
  if (res?.job) {
    job.value = res.job
    jobIdInput.value = res.job.id
    ElMessage.success(res.created ? '任务已创建' : '幂等复用已有任务')
    await loadTimeline()
  } else if (ocr.error.value) {
    ElMessage.error(ocr.error.value)
  }
}

async function loadJob() {
  if (!jobIdInput.value) return
  job.value = await ocr.getJob(jobIdInput.value)
  if (job.value) await loadTimeline()
  else if (ocr.error.value) ElMessage.error(ocr.error.value)
}

async function loadTimeline() {
  if (!jobIdInput.value) return
  const tl = await ocr.getTimeline(jobIdInput.value)
  transitions.value = tl?.transitions || []
}

async function retryJob() {
  if (!jobIdInput.value) return
  const res = await ocr.retryJob(jobIdInput.value)
  if (res?.job) {
    job.value = res.job
    ElMessage.success('已触发重试')
    await loadTimeline()
  } else if (ocr.error.value) {
    ElMessage.error(ocr.error.value)
  }
}

async function loadConfirmations() {
  if (!jobIdInput.value || !resultIdInput.value) {
    ElMessage.warning('请填写 Job ID 与 Result ID')
    return
  }
  const result = await ocr.getResult(jobIdInput.value, resultIdInput.value)
  const list = await ocr.listConfirmations(jobIdInput.value, resultIdInput.value)
  const confs = list?.confirmations || []
  // 以 OCR result fields 为基础，叠加已有确认决定
  const rawFields = (result?.fields || {}) as Record<string, unknown>
  const byName = new Map(confs.map((c) => [c.field_name, c]))
  fields.value = Object.keys(rawFields).map((name) => {
    const c = byName.get(name)
    return {
      field_name: name,
      original_value: String(rawFields[name] ?? ''),
      confirmed_value: c?.confirmed_value ?? null,
      decision: (c?.decision as any) ?? null,
    }
  })
  // 若 result 无 fields，用确认记录本身渲染
  if (fields.value.length === 0 && confs.length) {
    fields.value = confs.map((c) => ({
      field_name: c.field_name,
      original_value: c.original_value,
      confirmed_value: c.confirmed_value,
      decision: c.decision,
    }))
  }
}

async function onConfirm(payload: { field_name: string; decision: string; confirmed_value?: string }) {
  const res = await ocr.addConfirmation(jobIdInput.value, resultIdInput.value, {
    field_name: payload.field_name,
    decision: payload.decision as any,
    confirmed_value: payload.confirmed_value,
  })
  if (res) {
    ElMessage.success('确认已记录')
    await loadConfirmations()
  } else if (ocr.error.value) {
    ElMessage.error(ocr.error.value)
  }
}

async function openWriteback() {
  const m = await ocr.previewMapping(jobIdInput.value, resultIdInput.value)
  if (m) {
    mapping.value = m.mapping
    allDecided.value = m.all_required_decided
    readyForWriteback.value = m.ready_for_writeback
    conflictWarning.value = null
    writebackVisible.value = true
  } else if (ocr.error.value) {
    ElMessage.error(ocr.error.value)
  }
}

async function doWriteback() {
  if (!wbTargetId.value) {
    ElMessage.warning('请填写写回目标 ID')
    return
  }
  const res = await ocr.executeWriteback(jobIdInput.value, resultIdInput.value, {
    target_type: wbTargetType.value,
    target_id: wbTargetId.value,
    idempotency_key: `wb:${jobIdInput.value}:${resultIdInput.value}:${wbTargetId.value}`,
  })
  if (res) {
    ElMessage.success(`写回成功，写入 ${res.fields_written} 个字段`)
    writebackVisible.value = false
    await loadTimeline()
  } else if (ocr.error.value) {
    conflictWarning.value = ocr.error.value
    ElMessage.error(ocr.error.value)
  }
}

const STATE_LABELS: Record<string, string> = {
  queued: '排队中', running: '识别中', awaiting_confirmation: '待确认',
  confirmed: '已确认', written_back: '已写回', failed: '失败',
}
</script>

<template>
  <div class="evgov-tab">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="OCR 持久任务状态机：提交 → 时间线追踪 → 人工差异确认 → 原子写回。重试受 ocr.retry 权限限制。"
      style="margin-bottom: 12px"
    />

    <el-row :gutter="16">
      <el-col :span="12">
        <el-card shadow="never" header="提交 OCR 任务">
          <el-form label-width="120px" size="default">
            <el-form-item label="附件 ID">
              <el-input v-model="attachmentId" placeholder="attachment_id" />
            </el-form-item>
            <el-form-item label="附件版本 ID">
              <el-input v-model="versionId" placeholder="attachment_version_id" />
            </el-form-item>
            <el-form-item label="Content Hash">
              <el-input v-model="contentHash" placeholder="sha-256" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="ocr.loading.value" :disabled="!ocr.canStartOcr.value" @click="submitJob">
                提交任务
              </el-button>
              <el-text v-if="!ocr.canStartOcr.value" type="warning" size="small" style="margin-left: 8px">当前角色无提交权限</el-text>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never" header="加载任务 / 时间线">
          <el-form label-width="120px" size="default">
            <el-form-item label="Job ID">
              <el-input v-model="jobIdInput" placeholder="ocr_job_id" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="ocr.loading.value" @click="loadJob">加载任务</el-button>
              <el-button :disabled="!ocr.canRetryOcr.value" @click="retryJob">重试</el-button>
              <el-text v-if="!ocr.canRetryOcr.value" type="warning" size="small" style="margin-left: 8px">无重试权限</el-text>
            </el-form-item>
          </el-form>
          <div v-if="job" class="job-state">
            <el-tag size="small">状态：{{ STATE_LABELS[job.state] || job.state }}</el-tag>
            <el-tag size="small" type="info">进度 {{ job.progress }}%</el-tag>
            <el-tag size="small" type="info">尝试 {{ job.attempt_count }}/{{ job.max_attempts }}</el-tag>
            <el-tag v-if="job.error_message" size="small" type="danger">{{ job.error_message }}</el-tag>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card v-if="transitions.length" shadow="never" header="状态迁移时间线" style="margin-top: 16px">
      <GtOcrTimeline :transitions="transitions" :loading="ocr.loading.value" />
    </el-card>

    <el-card shadow="never" header="字段确认与写回" style="margin-top: 16px">
      <el-form :inline="true" size="default">
        <el-form-item label="Result ID">
          <el-input v-model="resultIdInput" placeholder="ocr_result_id" style="width: 260px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadConfirmations">加载结果字段</el-button>
          <el-button :disabled="fields.length === 0 || !ocr.canWritebackOcr.value" @click="openWriteback">预览写回</el-button>
        </el-form-item>
      </el-form>
      <GtOcrConfirmationPanel
        v-if="fields.length"
        :fields="fields"
        :readonly="!ocr.canConfirmOcr.value"
        :loading="ocr.loading.value"
        @confirm="onConfirm"
      />

      <div v-if="fields.length" class="wb-target">
        <span>写回目标：</span>
        <el-select v-model="wbTargetType" size="small" style="width: 160px">
          <el-option label="底稿单元格" value="workpaper_cell" />
          <el-option label="抽样项" value="sampling_item" />
          <el-option label="凭证" value="voucher" />
        </el-select>
        <el-input v-model="wbTargetId" size="small" placeholder="目标 ID" style="width: 220px" />
      </div>
    </el-card>

    <GtOcrWritebackDialog
      v-model:visible="writebackVisible"
      :mapping="mapping"
      :all-decided="allDecided"
      :ready-for-writeback="readyForWriteback"
      :conflict-warning="conflictWarning"
      :loading="ocr.loading.value"
      @confirm-writeback="doWriteback"
    />
  </div>
</template>

<style scoped>
.evgov-tab { padding: 4px 0; }
.job-state { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
.wb-target { display: flex; align-items: center; gap: 8px; margin-top: 12px; }
</style>
