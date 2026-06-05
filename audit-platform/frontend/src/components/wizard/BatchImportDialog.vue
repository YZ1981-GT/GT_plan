<template>
  <el-dialog
    :model-value="modelValue"
    title="批量建项"
    width="680px"
    append-to-body
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @open="handleOpen"
  >
    <div class="batch-import-content">
      <!-- 步骤 1：下载模板 -->
      <div class="batch-import-section">
        <h4 class="batch-import-section__title">1. 下载建项模板</h4>
        <p class="batch-import-section__desc">
          请先下载标准建项模板，按照模板中「说明事项」sheet 的要求填写数据后上传。
        </p>
        <el-button type="primary" plain @click="downloadTemplate" :loading="downloading">
          <el-icon><Download /></el-icon>
          下载模板
        </el-button>
      </div>

      <!-- 步骤 2：上传文件 -->
      <div class="batch-import-section">
        <h4 class="batch-import-section__title">2. 上传填写好的文件</h4>
        <el-upload
          ref="uploadRef"
          :auto-upload="false"
          :limit="1"
          accept=".xlsx"
          :on-change="handleFileChange"
          :on-exceed="handleExceed"
          drag
          class="batch-import-upload"
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">将 .xlsx 文件拖到此处，或<em>点击上传</em></div>
          <template #tip>
            <div class="el-upload__tip">仅支持 .xlsx 格式，最多 500 行数据</div>
          </template>
        </el-upload>
        <el-button
          type="primary"
          :loading="uploading"
          :disabled="!selectedFile"
          style="margin-top: 12px"
          @click="doImport"
        >
          开始导入
        </el-button>
      </div>

      <!-- 步骤 3：导入结果 -->
      <div v-if="importResult" class="batch-import-section">
        <h4 class="batch-import-section__title">3. 导入结果</h4>
        <el-alert
          v-if="importResult.success_count > 0"
          :title="`成功创建 ${importResult.success_count} 个项目`"
          type="success"
          :closable="false"
          show-icon
          style="margin-bottom: 12px"
        />
        <el-alert
          v-if="importResult.fail_count > 0"
          :title="`${importResult.fail_count} 行导入失败`"
          type="warning"
          :closable="false"
          show-icon
          style="margin-bottom: 12px"
        />
        <!-- 失败明细表 -->
        <el-table
          v-if="importResult.failures && importResult.failures.length > 0"
          :data="importResult.failures"
          size="small"
          border
          max-height="240"
          style="width: 100%"
        >
          <el-table-column prop="row_number" label="行号" width="80" align="center" />
          <el-table-column label="错误原因" min-width="300">
            <template #default="{ row }">
              <span class="batch-import-error-text">{{ row.errors.join('；') }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, UploadFilled } from '@element-plus/icons-vue'
import http from '@/utils/http'
import { downloadFile } from '@/utils/http'
import type { UploadFile, UploadInstance } from 'element-plus'

interface BatchImportFailure {
  row_number: number
  errors: string[]
}

interface BatchImportResult {
  success_count: number
  fail_count: number
  failures: BatchImportFailure[]
}

defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  success: []
}>()

const downloading = ref(false)
const uploading = ref(false)
const selectedFile = ref<File | null>(null)
const uploadRef = ref<UploadInstance>()
const importResult = ref<BatchImportResult | null>(null)

function handleOpen() {
  // 重置状态
  selectedFile.value = null
  importResult.value = null
  uploadRef.value?.clearFiles()
}

async function downloadTemplate() {
  downloading.value = true
  try {
    await downloadFile('/api/projects/batch-template', { fileName: '建项模板.xlsx' })
  } catch {
    ElMessage.error('模板下载失败，请稍后重试')
  } finally {
    downloading.value = false
  }
}

function handleFileChange(file: UploadFile) {
  if (file.raw) {
    selectedFile.value = file.raw
  }
}

function handleExceed() {
  ElMessage.warning('仅支持上传一个文件，请先移除已选文件')
}

async function doImport() {
  if (!selectedFile.value) return
  uploading.value = true
  importResult.value = null
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    const { data } = await http.post('/api/projects/batch-import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    importResult.value = data as BatchImportResult
    if (importResult.value && importResult.value.success_count > 0) {
      ElMessage.success(`成功导入 ${importResult.value.success_count} 个项目`)
      emit('success')
    }
    // 导入完成后清除文件，允许用户修正后重新上传
    selectedFile.value = null
    uploadRef.value?.clearFiles()
  } catch {
    ElMessage.error('批量导入失败，请检查文件格式')
  } finally {
    uploading.value = false
  }
}
</script>

<style scoped>
.batch-import-content {
  padding: 0 4px;
}

.batch-import-section {
  margin-bottom: 24px;
}

.batch-import-section__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-primary);
  margin: 0 0 8px;
}

.batch-import-section__desc {
  font-size: var(--gt-font-size-xs, 12px);
  color: var(--gt-color-text-secondary);
  line-height: 1.6;
  margin: 0 0 12px;
}

.batch-import-upload {
  width: 100%;
}

.batch-import-upload :deep(.el-upload-dragger) {
  border-color: var(--gt-color-border);
  border-radius: var(--gt-radius-md, 8px);
}

.batch-import-upload :deep(.el-upload-dragger:hover) {
  border-color: var(--gt-color-primary);
}

.batch-import-upload :deep(.el-icon--upload) {
  color: var(--gt-color-primary);
}

.batch-import-error-text {
  font-size: var(--gt-font-size-xs, 12px);
  color: var(--gt-color-coral, #FF5149);
}
</style>
