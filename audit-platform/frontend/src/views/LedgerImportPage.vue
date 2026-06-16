<template>
  <div class="ledger-import-page">
    <GtPageHeader title="账套导入" :show-back="true" />

    <!-- 步骤条 -->
    <el-steps :active="currentStep" finish-status="success" class="import-steps">
      <el-step title="上传" />
      <el-step title="识别预览" />
      <el-step title="列映射" />
      <el-step :title="currentStep >= 3 ? (isSuccess ? '完成' : '导入中') : '导入中'" />
    </el-steps>

    <div class="step-content">
      <!-- Step 0: 上传文件 -->
      <UploadStep
        v-if="currentStep === 0"
        :project-id="projectId"
        @detect-complete="onDetectComplete"
      />

      <!-- Step 1: 识别预览 -->
      <DetectionPreview
        v-if="currentStep === 1"
        :detection-result="detectionResult"
        @confirm="onDetectionConfirm"
        @back="currentStep = 0"
      />

      <!-- Step 2: 列映射 -->
      <ColumnMappingEditor
        v-if="currentStep === 2"
        :sheets="confirmedSheets"
        :detection-result="detectionResult"
        :project-id="projectId"
        @confirm="onMappingConfirm"
        @back="currentStep = 1"
      />

      <!-- Step 3: 导入进度 -->
      <div v-if="currentStep === 3 && !jobId" class="submit-placeholder">
        <template v-if="!submitFailed">
          <el-icon class="is-loading submit-spinner"><Loading /></el-icon>
          <p class="submit-msg">正在提交导入作业…</p>
          <p class="submit-hint">{{ submitHint }}</p>
          <el-progress :percentage="100" :indeterminate="true" :duration="2" :show-text="false" status="" style="width: 60%; margin: 16px auto 0" />
        </template>
        <template v-else>
          <el-icon class="submit-spinner submit-spinner--fail"><CircleClose /></el-icon>
          <p class="submit-msg submit-msg--fail">提交导入作业失败</p>
          <p class="submit-hint">{{ submitFailMsg || '请检查网络或稍后重试' }}</p>
          <div style="margin-top: 16px; display: flex; gap: 12px; justify-content: center">
            <el-button type="primary" @click="retrySubmit">重试提交</el-button>
            <el-button @click="currentStep = 2">返回列映射</el-button>
          </div>
        </template>
      </div>
      <ImportProgress
        v-if="currentStep === 3 && jobId"
        :project-id="projectId"
        :job-id="jobId"
        @complete="onImportComplete"
        @failed="onImportFailed"
        @canceled="onImportCanceled"
        @background="onMoveToBackground"
      />
    </div>

    <!-- 错误弹窗 -->
    <ErrorDialog
      v-model:visible="errorDialogVisible"
      :errors="importErrors"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Loading, CircleClose } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import UploadStep from '@/components/ledger-import/UploadStep.vue'
import DetectionPreview from '@/components/ledger-import/DetectionPreview.vue'
import ColumnMappingEditor from '@/components/ledger-import/ColumnMappingEditor.vue'
import ImportProgress from '@/components/ledger-import/ImportProgress.vue'
import ErrorDialog from '@/components/ledger-import/ErrorDialog.vue'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import type {
  LedgerDetectionResult,
  SheetDetection,
  ConfirmedMapping,
  ImportError,
} from '@/components/ledger-import/LedgerImportDialog.vue'

const route = useRoute()
const router = useRouter()

const projectId = route.params.projectId as string

// ─── State ──────────────────────────────────────────────────────────────────

const currentStep = ref(0)
const detectionResult = ref<LedgerDetectionResult | null>(null)
const confirmedSheets = ref<SheetDetection[]>([])
const forceSubmitFlag = ref(false)
const jobId = ref('')
const importErrors = ref<ImportError[]>([])
const errorDialogVisible = ref(false)
const isSuccess = ref(false)
const submitFailed = ref(false)
const submitFailMsg = ref('')
const lastMappings = ref<ConfirmedMapping[] | null>(null)

// 提交占位提示：根据 detect 估算的耗时给出预期
const submitHint = computed(() => {
  const secs = (detectionResult.value as any)?.estimated_duration_seconds
  if (typeof secs === 'number' && secs > 0) {
    const mins = Math.ceil(secs / 60)
    if (mins >= 2) {
      return `大文件提交约需 ${mins} 分钟，正在上传并校验，请耐心等待，勿重复点击`
    }
  }
  return '正在上传并校验规模，请稍候，勿重复点击'
})

// ─── Handlers ───────────────────────────────────────────────────────────────

function onDetectComplete(result: LedgerDetectionResult) {
  detectionResult.value = result
  const fatalErrors = result.errors.filter(e => e.severity === 'fatal')
  if (fatalErrors.length > 0) {
    importErrors.value = fatalErrors
    errorDialogVisible.value = true
    return
  }
  currentStep.value = 1
}

function onDetectionConfirm(sheets: SheetDetection[], forceSubmit?: boolean) {
  confirmedSheets.value = sheets
  forceSubmitFlag.value = forceSubmit || false
  currentStep.value = 2
}

function onMappingConfirm(mappings: ConfirmedMapping[]) {
  submitImportJob(mappings)
}

const submitting = ref(false)

async function submitImportJob(mappings: ConfirmedMapping[]) {
  if (!detectionResult.value) return
  if (submitting.value) return  // 防重复点击
  submitting.value = true
  lastMappings.value = mappings
  submitFailed.value = false
  submitFailMsg.value = ''
  // 立即切到"导入中"步骤，显示提交占位（避免用户以为没反应而重复点击）
  currentStep.value = 3
  try {
    const { api } = await import('@/services/apiProxy')
    const res = await api.post(
      `/api/projects/${projectId}/ledger-import/submit`,
      {
        upload_token: detectionResult.value.upload_token,
        year: detectionResult.value.detected_year,
        confirmed_mappings: mappings,
        force_activate: false,
        force_submit: forceSubmitFlag.value,
      },
      { timeout: 600000, _silent: true } as any
    )
    jobId.value = (res as { job_id: string }).job_id
  } catch (err: any) {
    console.error('提交导入作业失败', err)
    // 提交失败 → 停留在 step 3 显示失败态 + 重试按钮（不突兀地弹窗+退步骤）
    submitFailed.value = true
    submitFailMsg.value = err?.message || '提交导入作业失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}

function retrySubmit() {
  if (lastMappings.value) {
    submitImportJob(lastMappings.value)
  } else {
    currentStep.value = 2
  }
}

function onImportComplete() {
  isSuccess.value = true
  // 导入成功后跳转至查账页
  router.push({ path: `/projects/${projectId}/ledger` })
}

function onImportFailed() {
  importErrors.value = [{
    code: 'IMPORT_FAILED',
    severity: 'fatal',
    message: '导入过程中发生错误，请查看详情',
  }]
  errorDialogVisible.value = true
}

function onImportCanceled() {
  currentStep.value = 0
}

function onMoveToBackground() {
  // 放后台继续——跳回项目列表或查账页
  router.push({ path: `/projects/${projectId}/ledger` })
}
</script>

<style scoped>
.ledger-import-page {
  padding: 24px 32px;
  max-width: 960px;
  margin: 0 auto;
}

.import-steps {
  margin-bottom: 32px;
}

.step-content {
  min-height: 400px;
}

/* 提交占位 loading */
.submit-placeholder {
  text-align: center;
  padding: 60px 0;
}
.submit-spinner {
  font-size: 40px;
  color: var(--gt-color-primary, #4b2d77);
}
.submit-msg {
  margin-top: 16px;
  font-size: 16px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}
.submit-hint {
  margin-top: 6px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.submit-spinner--fail {
  color: var(--el-color-danger);
}
.submit-msg--fail {
  color: var(--el-color-danger);
}

:deep(.el-steps) {
  --el-color-primary: var(--gt-color-primary, #4b2d77);
}

:deep(.el-step__head.is-finish) {
  color: var(--gt-color-primary, #4b2d77);
  border-color: var(--gt-color-primary, #4b2d77);
}

:deep(.el-step__title.is-finish) {
  color: var(--gt-color-primary, #4b2d77);
}

:deep(.el-step__head.is-process) {
  color: var(--gt-color-primary, #4b2d77);
  border-color: var(--gt-color-primary, #4b2d77);
}

:deep(.el-step__title.is-process) {
  color: var(--gt-color-primary, #4b2d77);
  font-weight: 600;
}
</style>
