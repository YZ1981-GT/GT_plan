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

    <!-- 耗时预估 + 关注事项（文件选中后显示） -->
    <el-alert
      v-if="selectedFiles.length > 0"
      :type="alertLevel"
      :closable="false"
      show-icon
      style="margin-top: 12px"
    >
      <template #title>
        <b>预计耗时 {{ estimateText }}</b>
        <span v-if="isLargeFile"> · 建议使用"放到后台继续"</span>
      </template>
      <div class="tips-list">
        <div>• 总大小 <b>{{ formatSize(totalBytes) }}</b>，共 {{ selectedFiles.length }} 个文件</div>
        <div>• 识别 + 入库顺序执行；损益类科目期末结转后 opening/closing 为空属正常</div>
        <div v-if="isLargeFile">• 大文件（&gt;50MB）识别阶段较慢，首屏有 3-5 秒白屏属正常</div>
        <div>• 上传前请确保：同一项目年度无进行中的导入作业，否则会被阻塞</div>
      </div>
    </el-alert>

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
import { ref, computed } from 'vue'
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

// 耗时预估（基于 YG4001-30 0.81MB → ~11 秒 / YG36 3.5MB → ~40 秒 / YG2101 128MB → ~20 分钟 的真实样本统计）
// P2-1.3: 公式 = 上传时间 + 后端处理时间
// - 上传假设：有效带宽 20 Mbps（2.5 MB/s），大致覆盖办公网 / 家庭宽带
// - 后端处理：文件 MB × 系数（非线性，大文件更慢）
const UPLOAD_MB_PER_SECOND = 2.5
const totalBytes = computed(() => selectedFiles.value.reduce((sum, f) => sum + f.size, 0))
const totalMB = computed(() => totalBytes.value / (1024 * 1024))
const isLargeFile = computed(() => totalMB.value > 50)

const estimateSeconds = computed(() => {
  const mb = totalMB.value
  const uploadSec = Math.round(mb / UPLOAD_MB_PER_SECOND)  // 上传耗时
  let processSec: number
  if (mb < 1) processSec = 10
  else if (mb < 5) processSec = Math.round(mb * 11)
  else if (mb < 20) processSec = Math.round(mb * 12)
  else if (mb < 100) processSec = Math.round(mb * 14)
  else processSec = Math.round(mb * 16)
  return uploadSec + processSec
})

const estimateText = computed(() => {
  const s = estimateSeconds.value
  if (s < 60) return `约 ${s} 秒`
  if (s < 600) return `约 ${Math.round(s / 60)} 分钟`
  return `约 ${Math.round(s / 60)} 分钟（建议放后台继续）`
})

const alertLevel = computed<'info' | 'warning'>(() => isLargeFile.value ? 'warning' : 'info')

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

    // 注：当前实现整体上传，不做客户端分片
    // TODO: 真正分片需后端加 chunked upload 端点，>500MB 文件浏览器内存会承压
    const formData = new FormData()
    for (const file of selectedFiles.value) {
      formData.append('files', file, file.name)
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
  font-size: var(--gt-font-size-sm);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-size {
  font-size: var(--gt-font-size-xs);
  color: var(--el-text-color-secondary);
  min-width: 60px;
  text-align: right;
}

.step-actions {
  margin-top: 24px;
  text-align: right;
}

.tips-list {
  margin: 6px 0 0;
  font-size: var(--gt-font-size-xs);
  line-height: 1.8;
  color: var(--el-text-color-regular);
}
</style>
