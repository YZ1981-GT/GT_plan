<template>
  <AsyncJobProgress
    v-if="snapshot"
    :title="title"
    :percentage="percent"
    :status="viewStatus"
    :message="message"
    :cancelable="canCancel && !terminal"
    :retryable="canRetry && failed"
    @cancel="cancel"
    @retry="retry"
  />
  <el-alert v-else-if="error" type="error" :title="error" :closable="false" show-icon />
</template>

<script setup lang="ts">
/**
 * 统一 platform_jobs 进度视图：SSE 只唤醒、GET 状态端点是断线/刷新后的权威恢复路径。
 * B5：B3 导出、B4 公式推送/合并重新汇总等任务复用，不再各自维护定时器和终态映射。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import AsyncJobProgress from './AsyncJobProgress.vue'
import {
  cancelPlatformJob,
  getPlatformJob,
  isPlatformJobFailed,
  isPlatformJobTerminal,
  platformJobPercent,
  retryPlatformJob,
  subscribePlatformJob,
  type PlatformJobSnapshot,
  type PlatformJobSubscription,
} from '@/services/platformJobs'

const props = withDefaults(defineProps<{
  projectId: string
  jobId: string
  title?: string
  canCancel?: boolean
  canRetry?: boolean
}>(), {
  title: '后台任务',
  canCancel: true,
  canRetry: true,
})

const emit = defineEmits<{
  'update:jobId': [jobId: string]
  completed: [job: PlatformJobSnapshot]
  failed: [job: PlatformJobSnapshot]
}>()

type ViewStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

// platform_jobs 六态 → AsyncJobProgress 五态的显式映射，避免在渲染/事件分支里裸用字符串字面量。
const PLATFORM_TO_VIEW: Record<PlatformJobStatus, ViewStatus> = {
  queued: 'pending',
  running: 'running',
  retry_wait: 'pending',
  succeeded: 'completed',
  failed: 'failed',
  cancelled: 'cancelled',
}

const snapshot = ref<PlatformJobSnapshot | null>(null)
const error = ref('')
let subscription: PlatformJobSubscription | null = null
let sequence = 0

const terminal = computed(() => snapshot.value ? isPlatformJobTerminal(snapshot.value.status) : false)
const failed = computed(() => snapshot.value ? isPlatformJobFailed(snapshot.value.status) : false)
const percent = computed(() => snapshot.value ? platformJobPercent(snapshot.value) : 0)
const message = computed(() => snapshot.value?.error_message || snapshot.value?.progress_message || '')
const viewStatus = computed<ViewStatus>(() => {
  const status = snapshot.value?.status
  return status ? PLATFORM_TO_VIEW[status] : 'pending'
})

function stop(): void {
  subscription?.close()
  subscription = null
}

function apply(next: PlatformJobSnapshot, current: number): void {
  if (current !== sequence) return
  snapshot.value = next
  if (isPlatformJobTerminal(next.status)) {
    stop()
    if (isPlatformJobFailed(next.status)) emit('failed', next)
    else emit('completed', next)
  }
}

async function start(jobId = props.jobId): Promise<void> {
  const current = ++sequence
  stop()
  snapshot.value = null
  error.value = ''
  if (!props.projectId || !jobId) return
  try {
    const initial = await getPlatformJob(props.projectId, jobId)
    if (current !== sequence) return
    apply(initial, current)
    if (!isPlatformJobTerminal(initial.status)) {
      subscription = subscribePlatformJob(
        props.projectId,
        initial,
        (next) => apply(next, current),
        (cause) => { if (current === sequence) error.value = cause instanceof Error ? cause.message : '任务状态读取失败' },
      )
    }
  } catch (cause) {
    if (current === sequence) error.value = cause instanceof Error ? cause.message : '任务状态读取失败'
  }
}

async function cancel(): Promise<void> {
  if (!snapshot.value || terminal.value) return
  try {
    apply(await cancelPlatformJob(props.projectId, snapshot.value.job_id), sequence)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '取消任务失败'
  }
}

async function retry(): Promise<void> {
  if (!snapshot.value || !failed.value) return
  try {
    const next = await retryPlatformJob(props.projectId, snapshot.value.job_id)
    emit('update:jobId', next.job_id)
    snapshot.value = next
    await start(next.job_id)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '重试任务失败'
  }
}

watch(() => [props.projectId, props.jobId] as const, () => { void start() }, { immediate: true })
onBeforeUnmount(stop)
</script>
