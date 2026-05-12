<template>
  <div class="operation-feedback">
    <el-progress v-if="showProgress" :percentage="progress" :status="(progressStatus as '' | 'success' | 'warning' | 'exception')" :stroke-width="4" />
  </div>
</template>

<script setup lang="ts">
import { ElNotification } from 'element-plus'

withDefaults(defineProps<{
  showProgress?: boolean
  progress?: number
  progressStatus?: string
}>(), {
  showProgress: false,
  progress: 0,
  progressStatus: '',
})

function notifySuccess(message: string) {
  ElNotification({ title: '操作成功', message, type: 'success', duration: 3000 })
}

function notifyError(message: string) {
  ElNotification({ title: '操作失败', message, type: 'error', duration: 5000 })
}

function notifyProgress(message: string) {
  ElNotification({ title: '处理中', message, type: 'info', duration: 2000 })
}

defineExpose({ notifySuccess, notifyError, notifyProgress })
</script>
