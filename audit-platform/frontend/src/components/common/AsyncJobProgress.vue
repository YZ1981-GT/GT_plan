/**
 * AsyncJobProgress.vue — 统一异步任务进度条组件 [wp-frontend-ux-polish Task 5]
 *
 * 适用于 import / word-export / archive / generate 等异步任务。
 * 提供统一的进度条 + 状态文案 + 取消/重试操作。
 */
<template>
  <div v-if="visible" class="gt-async-job-progress" :class="`gt-async-job-progress--${status}`">
    <div class="gt-async-job-progress__header">
      <span class="gt-async-job-progress__title">{{ title }}</span>
      <el-tag v-if="statusLabel" :type="statusTagType" size="small" effect="plain">
        {{ statusLabel }}
      </el-tag>
      <el-button
        v-if="closable && (status === 'completed' || status === 'failed')"
        type="info"
        link
        size="small"
        @click="$emit('close')"
      >
        关闭
      </el-button>
    </div>

    <el-progress
      :percentage="clampedPercent"
      :stroke-width="strokeWidth"
      :status="progressStatus"
      :text-inside="strokeWidth >= 14"
      :show-text="showText"
    />

    <div v-if="message" class="gt-async-job-progress__message">
      {{ message }}
    </div>

    <div v-if="showActions" class="gt-async-job-progress__actions">
      <el-button
        v-if="status === 'running' && cancelable"
        type="danger"
        size="small"
        plain
        @click="$emit('cancel')"
      >
        取消
      </el-button>
      <el-button
        v-if="status === 'failed' && retryable"
        type="primary"
        size="small"
        plain
        @click="$emit('retry')"
      >
        重试
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export type AsyncJobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface AsyncJobProgressProps {
  /** 任务标题 */
  title?: string
  /** 进度百分比 0-100 */
  percentage?: number
  /** 任务状态 */
  status?: AsyncJobStatus
  /** 状态描述文案 */
  message?: string
  /** 是否可见 */
  visible?: boolean
  /** 是否可取消 */
  cancelable?: boolean
  /** 是否可重试 */
  retryable?: boolean
  /** 是否可关闭 */
  closable?: boolean
  /** 进度条粗细 */
  strokeWidth?: number
  /** 是否显示百分比文字 */
  showText?: boolean
}

const props = withDefaults(defineProps<AsyncJobProgressProps>(), {
  title: '任务执行中',
  percentage: 0,
  status: 'pending',
  message: '',
  visible: true,
  cancelable: true,
  retryable: true,
  closable: true,
  strokeWidth: 14,
  showText: true,
})

defineEmits<{
  cancel: []
  retry: []
  close: []
}>()

const clampedPercent = computed(() => Math.max(0, Math.min(props.percentage, 100)))

const progressStatus = computed(() => {
  if (props.status === 'completed') return 'success'
  if (props.status === 'failed') return 'exception'
  return ''
})

const statusLabel = computed(() => {
  const map: Record<AsyncJobStatus, string> = {
    pending: '等待中',
    running: '执行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return map[props.status] || ''
})

const statusTagType = computed(() => {
  const map: Record<AsyncJobStatus, 'info' | 'primary' | 'success' | 'danger' | 'warning'> = {
    pending: 'info',
    running: 'primary',
    completed: 'success',
    failed: 'danger',
    cancelled: 'warning',
  }
  return map[props.status] || 'info'
})

const showActions = computed(() => {
  return (props.status === 'running' && props.cancelable) ||
    (props.status === 'failed' && props.retryable)
})
</script>

<style scoped>
.gt-async-job-progress {
  padding: 12px 16px;
  border-radius: 6px;
  background: var(--el-fill-color-lighter, #f5f7fa);
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
}

.gt-async-job-progress--failed {
  background: var(--el-color-danger-light-9, #fef0f0);
  border-color: var(--el-color-danger-light-5, #fab6b6);
}

.gt-async-job-progress--completed {
  background: var(--el-color-success-light-9, #f0f9eb);
  border-color: var(--el-color-success-light-5, #b3e19d);
}

.gt-async-job-progress__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.gt-async-job-progress__title {
  font-weight: 600;
  font-size: 14px;
  flex: 1;
}

.gt-async-job-progress__message {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}

.gt-async-job-progress__actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
}
</style>
