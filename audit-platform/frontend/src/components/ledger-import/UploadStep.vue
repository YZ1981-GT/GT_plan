<template>
  <div class="upload-step">
    <el-upload
      ref="uploadRef"
      drag
      multiple
      :auto-upload="false"
      accept=".xlsx,.xlsm,.csv,.tsv,.zip"
      :on-change="onFileChange"
      :on-remove="onFileRemove"
      :file-list="fileList"
      class="upload-area"
    >
      <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
      <div class="el-upload__text">
        将文件拖到此处，或<em>点击上传</em>
      </div>
      <template #tip>
        <div class="el-upload__tip">
          支持 .xlsx / .xlsm / .csv / .tsv / .zip 格式，单文件最大 1GB
        </div>
      </template>
    </el-upload>

    <!-- 文件列表 -->
    <div v-if="selectedFiles.length > 0" class="file-list">
      <div v-for="(file, idx) in selectedFiles" :key="idx" class="file-item">
        <el-icon><Document /></el-icon>
        <span class="file-name">{{ file.name }}</span>
        <span class="file-size">{{ formatSize(file.size) }}</span>
        <el-button link type="danger" aria-label="移除文件" @click="removeFile(idx)">
          <el-icon><Close /></el-icon>
        </el-button>
      </div>
    </div>

    <!-- 上传进度 -->
    <el-progress
      v-if="uploading"
      :percentage="uploadProgress"
      :status="uploadProgress === 100 ? 'success' : undefined"
      style="margin-top: 16px"
    />

    <!-- 操作按钮 -->
    <div class="step-actions">
      <el-button
        type="primary"
        aria-label="开始预检"
        :loading="detecting"
        :disabled="selectedFiles.length === 0"
        @click="startDetect"
      >
        {{ detecting ? '预检中...' : '开始预检' }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { UploadFilled, Document, Close } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { UploadFile, UploadInstance } from 'element-plus'
import type { LedgerDetectionResult } from './LedgerImportDialog.vue'

// ─── Props & Emits ──────────────────────────────────────────────────────────

const props = defineProps<{
  projectId: string
}>()

const emit = defineEmits<{
  'detect-complete': [result: LedgerDetectionResult]
}>()

// ─── State ──────────────────────────────────────────────────────────────────

const uploadRef = ref<UploadInstance>()
const fileList = ref<UploadFile[]>([])
const selectedFiles = ref<File[]>([])
const uploading = ref(false)
const uploadProgress = ref(0)
const detecting = ref(false)

// ─── Handlers ───────────────────────────────────────────────────────────────

function onFileChange(uploadFile: UploadFile) {
  if (uploadFile.raw) {
    selectedFiles.value.push(uploadFile.raw)
  }
}

function onFileRemove(uploadFile: UploadFile) {
  const idx = selectedFiles.value.findIndex(f => f.name === uploadFile.name)
  if (idx >= 0) selectedFiles.value.splice(idx, 1)
}

function removeFile(idx: number) {
  selectedFiles.value.splice(idx, 1)
  fileList.value.splice(idx, 1)
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

async function startDetect() {
  if (selectedFiles.value.length === 0) return

  detecting.value = true
  uploading.value = true
  uploadProgress.value = 0

  try {
    const { api } = await import('@/services/apiProxy')

    // 分 chunk 上传（5MB 每片），对于小文件直接整体上传
    const CHUNK_SIZE = 5 * 1024 * 1024 // 5MB
    const formData = new FormData()

    for (const file of selectedFiles.value) {
      if (file.size <= CHUNK_SIZE) {
        // 小文件直接添加
        formData.append('files', file, file.name)
      } else {
        // 大文件分片：这里简化为整体上传（真正分片需要后端支持分片接口）
        formData.append('files', file, file.name)
      }
    }

    uploadProgress.value = 50

    const result = await api.post(
      `/api/projects/${props.projectId}/ledger-import/detect`,
      formData
    ) as LedgerDetectionResult

    uploadProgress.value = 100
    emit('detect-complete', result)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : '预检失败'
    ElMessage.error(msg)
  } finally {
    detecting.value = false
    uploading.value = false
  }
}
</script>

<style scoped>
.upload-step {
  padding: 0 16px;
}

.upload-area {
  width: 100%;
}

.file-list {
  margin-top: 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px 12px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid var(--el-border-color-extra-light);
}

.file-item:last-child {
  border-bottom: none;
}

.file-name {
  flex: 1;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-size {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  min-width: 60px;
  text-align: right;
}

.step-actions {
  margin-top: 24px;
  text-align: right;
}
</style>
