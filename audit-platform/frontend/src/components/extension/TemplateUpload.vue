<template>
  <el-upload
    ref="uploadRef"
    drag
    :auto-upload="false"
    :limit="1"
    :on-change="onFileChange"
    :on-exceed="onExceed"
    :before-upload="beforeUpload"
    accept=".xlsx,.docx"
    class="gt-template-upload"
  >
    <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
    <div class="el-upload__text">拖拽文件到此处，或 <em>点击上传</em></div>
    <template #tip>
      <div class="el-upload__tip">支持 .xlsx 和 .docx 格式，单文件不超过 20MB</div>
    </template>
  </el-upload>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { UploadFile, UploadInstance } from 'element-plus'

const emit = defineEmits<{
  (e: 'update:modelValue', file: File | null): void
}>()

const uploadRef = ref<UploadInstance>()
const allowedExts = ['.xlsx', '.docx']

function beforeUpload(file: File) {
  const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase()
  if (!allowedExts.includes(ext)) {
    ElMessage.error('仅支持 .xlsx 和 .docx 格式')
    return false
  }
  if (file.size > 20 * 1024 * 1024) {
    ElMessage.error('文件大小不能超过 20MB')
    return false
  }
  return true
}

function onFileChange(uploadFile: UploadFile) {
  if (uploadFile.raw) {
    const ext = uploadFile.name.substring(uploadFile.name.lastIndexOf('.')).toLowerCase()
    if (!allowedExts.includes(ext)) {
      ElMessage.error('仅支持 .xlsx 和 .docx 格式')
      uploadRef.value?.clearFiles()
      emit('update:modelValue', null)
      return
    }
    emit('update:modelValue', uploadFile.raw)
  }
}

function onExceed() {
  ElMessage.warning('只能上传一个文件，请先删除已有文件')
}
</script>

<style scoped>
.gt-template-upload { width: 100%; }
.gt-template-upload :deep(.el-upload-dragger) {
  border-color: var(--gt-color-border);
  border-radius: var(--gt-radius-md);
}
.gt-template-upload :deep(.el-upload-dragger:hover) {
  border-color: var(--gt-color-primary);
}
</style>
