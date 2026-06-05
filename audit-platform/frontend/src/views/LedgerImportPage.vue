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
      <ImportProgress
        v-if="currentStep === 3"
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
import { ref } from 'vue'
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

async function submitImportJob(mappings: ConfirmedMapping[]) {
  if (!detectionResult.value) return
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
      }
    )
    jobId.value = (res as { job_id: string }).job_id
    currentStep.value = 3
  } catch (err) {
    console.error('提交导入作业失败', err)
    importErrors.value = [{
      code: 'SUBMIT_FAILED',
      severity: 'fatal',
      message: '提交导入作业失败，请稍后重试',
    }]
    errorDialogVisible.value = true
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
