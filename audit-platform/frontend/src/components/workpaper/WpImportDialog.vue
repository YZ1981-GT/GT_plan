<template>
  <el-dialog
    v-model="visible"
    title="导入底稿"
    width="680px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <!-- 步骤 1: 文件上传 -->
    <div v-if="step === 'upload'">
      <el-upload
        ref="uploadRef"
        drag
        :auto-upload="false"
        :limit="1"
        accept=".xlsx,.docx"
        :on-change="handleFileChange"
        :on-exceed="handleExceed"
      >
        <el-icon class="el-icon--upload"><Upload /></el-icon>
        <div class="el-upload__text">
          拖拽文件到此处，或 <em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            仅支持 .xlsx / .docx 格式文件
          </div>
        </template>
      </el-upload>
    </div>

    <!-- 步骤 2: 校验报告 -->
    <div v-else-if="step === 'validation'" class="wp-import-validation">
      <WpValidationReport :report="validationReport!" />
      <div v-if="validationReport?.overall === 'error'" class="wp-import-validation__hint">
        <el-alert type="error" :closable="false" show-icon>
          校验存在错误，无法继续导入。请修正后重新上传。
        </el-alert>
      </div>
    </div>

    <!-- 步骤 3: 冲突处理 -->
    <div v-else-if="step === 'conflict'" class="wp-import-conflict">
      <WpConflictPanel
        :conflict="conflictResult!"
        :loading="loading"
        @resolve="handleConflictResolve"
      />
    </div>

    <!-- 步骤 4: 完成 -->
    <div v-else-if="step === 'done'" class="wp-import-done">
      <el-result icon="success" title="导入成功">
        <template #sub-title>
          <span>新版本号: {{ importResult?.new_version }}</span>
        </template>
      </el-result>
    </div>

    <template #footer>
      <el-button @click="handleClose">{{ step === 'done' ? '关闭' : '取消' }}</el-button>
      <el-button
        v-if="step === 'upload'"
        type="primary"
        :loading="loading"
        :disabled="!selectedFile"
        @click="handleImport"
      >
        开始导入
      </el-button>
      <el-button
        v-if="step === 'validation' && validationReport?.overall !== 'error'"
        type="primary"
        :loading="loading"
        @click="handleImport"
      >
        继续导入
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * WpImportDialog — 导入上传弹窗
 *
 * 文件上传 (el-upload) + 格式限制 (.xlsx/.docx)。
 * 调用 import 端点 multipart/form-data。
 * 409 时弹出冲突详情，展示校验报告。
 *
 * Requirements: 3.3, 4.3, 4.4, 5.1, 5.6
 */
import { ref, computed } from 'vue'
import { Upload } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { UploadFile, UploadInstance } from 'element-plus'
import { useWpExportImport } from '@/composables/useWpExportImport'
import type { ValidationReport, ConflictResult, ImportResult } from '@/composables/useWpExportImport'
import WpValidationReport from './WpValidationReport.vue'
import WpConflictPanel from './WpConflictPanel.vue'

const props = defineProps<{
  modelValue: boolean
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'imported', result: ImportResult): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const { importEnhanced, importResolve, loading } = useWpExportImport()

type Step = 'upload' | 'validation' | 'conflict' | 'done'
const step = ref<Step>('upload')
const selectedFile = ref<File | null>(null)
const uploadRef = ref<UploadInstance>()
const validationReport = ref<ValidationReport | null>(null)
const conflictResult = ref<ConflictResult | null>(null)
const importResult = ref<ImportResult | null>(null)
const conflictWpId = ref<string>('')

function handleFileChange(uploadFile: UploadFile) {
  const file = uploadFile.raw
  if (!file) return
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (!['xlsx', 'docx'].includes(ext || '')) {
    ElMessage.warning('仅支持 .xlsx 和 .docx 格式')
    return
  }
  selectedFile.value = file
}

function handleExceed() {
  ElMessage.warning('只能上传一个文件')
}

async function handleImport() {
  if (!selectedFile.value) return

  try {
    const result = await importEnhanced(props.projectId, selectedFile.value)

    if (result.status === 'conflict' && result.conflict_result) {
      conflictResult.value = result.conflict_result
      conflictWpId.value = result.wp_id
      step.value = 'conflict'
      return
    }

    if (result.status === 'validation_error' && result.validation_report) {
      validationReport.value = result.validation_report
      step.value = 'validation'
      return
    }

    // 成功
    importResult.value = result
    step.value = 'done'
    emit('imported', result)
  } catch (err: any) {
    ElMessage.error(err?.message || '导入失败')
  }
}

async function handleConflictResolve(resolution: 'force_overwrite' | 'parallel_version' | 'cancel') {
  if (resolution === 'cancel') {
    handleClose()
    return
  }

  if (!selectedFile.value) return

  // 将文件转 base64
  const buffer = await selectedFile.value.arrayBuffer()
  const base64 = btoa(
    new Uint8Array(buffer).reduce((data, byte) => data + String.fromCharCode(byte), ''),
  )

  try {
    const result = await importResolve(
      props.projectId,
      conflictWpId.value,
      resolution,
      base64,
      selectedFile.value.name,
    )
    importResult.value = result
    step.value = 'done'
    emit('imported', result)
  } catch (err: any) {
    ElMessage.error(err?.message || '冲突解决失败')
  }
}

function handleClose() {
  step.value = 'upload'
  selectedFile.value = null
  validationReport.value = null
  conflictResult.value = null
  importResult.value = null
  visible.value = false
}
</script>

<style scoped>
.wp-import-validation,
.wp-import-conflict,
.wp-import-done {
  min-height: 200px;
}

.wp-import-validation__hint {
  margin-top: 16px;
}
</style>
