<template>
  <div class="import-progress">
    <!-- 四段式进度 -->
    <div class="phase-segments">
      <div
        v-for="phase in phases"
        :key="phase.key"
        class="phase-segment"
        :class="{ active: phase.key === currentPhase, completed: phase.completed }"
      >
        <div class="phase-label">{{ phase.label }}</div>
        <el-progress
          :percentage="phase.percent"
          :status="phase.completed ? 'success' : undefined"
          :stroke-width="8"
        />
      </div>
    </div>

    <!-- 当前状态 -->
    <div class="status-area">
      <div class="status-message">
        <el-icon v-if="!isFinished" class="is-loading"><Loading /></el-icon>
        <el-icon v-else-if="isSuccess"><CircleCheck /></el-icon>
        <el-icon v-else><CircleClose /></el-icon>
        <span>{{ statusMessage }}</span>
      </div>

      <div v-if="currentFile" class="current-file">
        正在处理：{{ currentFile }}
      </div>
    </div>

    <!-- 总进度 -->
    <el-progress
      :percentage="totalPercent"
      :status="progressStatus"
      :stroke-width="12"
      style="margin-top: 20px"
    />

    <!-- 操作按钮 -->
    <div class="step-actions">
      <el-button
        v-if="!isFinished"
        type="danger"
        plain
        aria-label="取消导入"
        @click="onCancel"
      >
        取消导入
      </el-button>
      <el-button
        v-if="isSuccess"
        type="primary"
        aria-label="完成导入"
        @click="emit('complete')"
      >
        完成
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Loading, CircleCheck, CircleClose } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

// ─── Props & Emits ──────────────────────────────────────────────────────────

const props = defineProps<{
  projectId: string
  jobId: string
}>()

const emit = defineEmits<{
  complete: []
  failed: []
  canceled: []
}>()

// ─── Types ──────────────────────────────────────────────────────────────────

interface PhaseInfo {
  key: string
  label: string
  percent: number
  completed: boolean
}

interface SSEMessage {
  phase: string
  percent?: number
  file?: string
  sheet?: string
  rows?: number
  message?: string
  dataset_id?: string
  error?: string
}

// ─── State ──────────────────────────────────────────────────────────────────

const currentPhase = ref('uploading')
const totalPercent = ref(0)
const statusMessage = ref('准备中...')
const currentFile = ref('')
const isFinished = ref(false)
const isSuccess = ref(false)
let eventSource: EventSource | null = null

const phases = ref<PhaseInfo[]>([
  { key: 'uploading', label: '上传', percent: 100, completed: true },
  { key: 'parsing', label: '解析', percent: 0, completed: false },
  { key: 'validating', label: '校验', percent: 0, completed: false },
  { key: 'activating', label: '激活', percent: 0, completed: false },
])

// ─── Computed ───────────────────────────────────────────────────────────────

const progressStatus = computed(() => {
  if (isSuccess.value) return 'success'
  if (isFinished.value && !isSuccess.value) return 'exception'
  return undefined
})

// ─── SSE Subscription ───────────────────────────────────────────────────────

function connectSSE() {
  const url = `/api/projects/${props.projectId}/ledger-import/jobs/${props.jobId}/stream`
  eventSource = new EventSource(url)

  eventSource.onmessage = (event) => {
    try {
      const data: SSEMessage = JSON.parse(event.data)
      handleSSEMessage(data)
    } catch {
      // ignore parse errors
    }
  }

  eventSource.onerror = () => {
    // SSE 断开，可能是完成或网络问题
    if (!isFinished.value) {
      statusMessage.value = '连接中断，正在重试...'
    }
  }
}

function handleSSEMessage(data: SSEMessage) {
  currentPhase.value = data.phase

  if (data.file) {
    currentFile.value = data.file + (data.sheet ? ` / ${data.sheet}` : '')
  }

  if (data.message) {
    statusMessage.value = data.message
  }

  // 更新各阶段进度
  const phaseIdx = phases.value.findIndex(p => p.key === data.phase)
  if (phaseIdx >= 0 && data.percent !== undefined) {
    phases.value[phaseIdx].percent = data.percent
    // 标记之前的阶段为完成
    for (let i = 0; i < phaseIdx; i++) {
      phases.value[i].percent = 100
      phases.value[i].completed = true
    }
  }

  // 计算总进度（4 段各占 25%）
  const total = phases.value.reduce((sum, p) => sum + p.percent, 0)
  totalPercent.value = Math.round(total / 4)

  // 完成
  if (data.phase === 'completed') {
    isFinished.value = true
    isSuccess.value = true
    statusMessage.value = '导入完成'
    currentFile.value = ''
    phases.value.forEach(p => { p.percent = 100; p.completed = true })
    totalPercent.value = 100
    closeSSE()
  }

  // 失败
  if (data.phase === 'failed' || data.error) {
    isFinished.value = true
    isSuccess.value = false
    statusMessage.value = data.error || '导入失败'
    closeSSE()
    emit('failed')
  }
}

function closeSSE() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
}

// ─── Actions ────────────────────────────────────────────────────────────────

async function onCancel() {
  try {
    await ElMessageBox.confirm('确定要取消当前导入作业吗？已处理的数据将被清理。', '取消导入', {
      type: 'warning',
    })
    const { api } = await import('@/services/apiProxy')
    await api.post(`/api/projects/${props.projectId}/ledger-import/jobs/${props.jobId}/cancel`)
    closeSSE()
    isFinished.value = true
    statusMessage.value = '已取消'
    emit('canceled')
  } catch {
    // 用户取消确认
  }
}

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(() => {
  connectSSE()
})

onUnmounted(() => {
  closeSSE()
})
</script>

<style scoped>
.import-progress {
  padding: 16px;
}

.phase-segments {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 24px;
}

.phase-segment {
  text-align: center;
}

.phase-segment .phase-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}

.phase-segment.active .phase-label {
  color: var(--el-color-primary);
  font-weight: 600;
}

.phase-segment.completed .phase-label {
  color: var(--el-color-success);
}

.status-area {
  text-align: center;
  padding: 16px 0;
}

.status-message {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 14px;
}

.current-file {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.step-actions {
  margin-top: 24px;
  text-align: center;
}
</style>
