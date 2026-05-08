<template>
  <el-dialog
    v-model="dialogVisible"
    title="账表导入"
    width="900px"
    append-to-body
    destroy-on-close
    :close-on-click-modal="false"
    @close="onClose"
  >
    <!-- 步骤条 -->
    <el-steps :active="currentStep" finish-status="success" style="margin-bottom: 24px">
      <el-step title="上传文件" />
      <el-step title="预检确认" />
      <el-step title="列映射" />
      <el-step title="导入进度" />
    </el-steps>

    <!-- Step 0: 上传文件 -->
    <UploadStep
      v-if="currentStep === 0"
      :project-id="projectId"
      @detect-complete="onDetectComplete"
    />

    <!-- Step 1: 预检确认 -->
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
    />
  </el-dialog>

  <!-- 错误弹窗 -->
  <ErrorDialog
    v-model:visible="errorDialogVisible"
    :errors="importErrors"
  />
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import UploadStep from './UploadStep.vue'
import DetectionPreview from './DetectionPreview.vue'
import ColumnMappingEditor from './ColumnMappingEditor.vue'
import ImportProgress from './ImportProgress.vue'
import ErrorDialog from './ErrorDialog.vue'

// ─── Types ──────────────────────────────────────────────────────────────────

export interface LedgerDetectionResult {
  upload_token: string
  files: FileDetection[]
  detected_year: number | null
  year_confidence: number
  year_evidence: Record<string, unknown>
  merged_tables: Record<string, [string, string][]>
  missing_tables: string[]
  can_derive: Record<string, boolean>
  errors: ImportError[]
  requires_manual_confirm: boolean
}

export interface FileDetection {
  file_name: string
  file_size_bytes: number
  file_type: string
  encoding: string | null
  sheets: SheetDetection[]
  errors: ImportError[]
}

export interface SheetDetection {
  file_name: string
  sheet_name: string
  row_count_estimate: number
  header_row_index: number
  data_start_row: number
  table_type: string
  table_type_confidence: number
  confidence_level: string
  adapter_id: string | null
  column_mappings: ColumnMatch[]
  has_aux_dimension: boolean
  aux_dimension_columns: number[]
  preview_rows: string[][]
  detection_evidence: Record<string, unknown>
  warnings: string[]
}

export interface ColumnMatch {
  column_index: number
  column_header: string
  standard_field: string | null
  column_tier: 'key' | 'recommended' | 'extra'
  confidence: number
  source: string
  sample_values: string[]
}

export interface ImportError {
  code: string
  severity: 'fatal' | 'blocking' | 'warning'
  message: string
  file?: string | null
  sheet?: string | null
  row?: number | null
  column?: string | null
  suggestion?: string | null
}

export interface ConfirmedMapping {
  file: string
  sheet: string
  table_type: string
  column_mapping: Record<string, string>
  aux_dimension_columns: number[]
}

// ─── Props & Emits ──────────────────────────────────────────────────────────

const props = defineProps<{
  modelValue: boolean
  projectId: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'import-complete': []
}>()

// ─── State ──────────────────────────────────────────────────────────────────

const currentStep = ref(0)
const detectionResult = ref<LedgerDetectionResult | null>(null)
const confirmedSheets = ref<SheetDetection[]>([])
const jobId = ref('')
const importErrors = ref<ImportError[]>([])
const errorDialogVisible = ref(false)

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (val: boolean) => emit('update:modelValue', val),
})

// ─── Handlers ───────────────────────────────────────────────────────────────

function onDetectComplete(result: LedgerDetectionResult) {
  detectionResult.value = result
  // 如果有 fatal 错误，弹错误窗
  const fatalErrors = result.errors.filter(e => e.severity === 'fatal')
  if (fatalErrors.length > 0) {
    importErrors.value = fatalErrors
    errorDialogVisible.value = true
    return
  }
  currentStep.value = 1
}

function onDetectionConfirm(sheets: SheetDetection[]) {
  confirmedSheets.value = sheets
  currentStep.value = 2
}

function onMappingConfirm(mappings: ConfirmedMapping[]) {
  // 提交导入作业
  submitImportJob(mappings)
}

async function submitImportJob(mappings: ConfirmedMapping[]) {
  if (!detectionResult.value) return
  try {
    const { api } = await import('@/services/apiProxy')
    const res = await api.post(
      `/api/projects/${props.projectId}/ledger-import/submit`,
      {
        upload_token: detectionResult.value.upload_token,
        year: detectionResult.value.detected_year,
        confirmed_mappings: mappings,
        force_activate: false,
      }
    )
    jobId.value = (res as { job_id: string }).job_id
    currentStep.value = 3
  } catch (err) {
    console.error('提交导入作业失败', err)
  }
}

function onImportComplete() {
  emit('import-complete')
  dialogVisible.value = false
}

function onImportFailed() {
  // 可以展示错误详情
  errorDialogVisible.value = true
}

function onImportCanceled() {
  currentStep.value = 0
}

function onClose() {
  currentStep.value = 0
  detectionResult.value = null
  confirmedSheets.value = []
  jobId.value = ''
  importErrors.value = []
}
</script>

<style scoped>
.el-dialog {
  --el-dialog-padding-primary: 20px;
}
</style>
