<template>
  <div class="workflow-progress" v-if="loaded">
    <el-steps :active="currentStep" finish-status="success" simple class="workflow-progress__steps">
      <el-step title="导入" />
      <el-step title="映射" />
      <el-step title="试算表" />
      <el-step title="报表" />
      <el-step title="底稿" />
      <el-step title="附注" />
    </el-steps>
    <el-button
      v-if="nextAction"
      type="primary"
      size="small"
      class="workflow-progress__next-btn"
      @click="onNext"
    >
      {{ nextAction.label }}
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/services/apiProxy'

interface StepInfo {
  completed: boolean
  count?: number
  rate?: number
}

interface NextAction {
  label: string
  route: string
}

interface WorkflowStatusResponse {
  steps: Record<string, StepInfo>
  current_step: number
  next_action: NextAction | null
}

const props = defineProps<{
  projectId: string
  year?: number
}>()

const router = useRouter()

const loaded = ref(false)
const currentStep = ref(0)
const nextAction = ref<NextAction | null>(null)

async function fetchStatus() {
  try {
    const yr = props.year || 2025
    const res = await api.get(`/api/projects/${props.projectId}/workflow-status?year=${yr}`) as WorkflowStatusResponse
    currentStep.value = res.current_step
    nextAction.value = res.next_action
    loaded.value = true
  } catch {
    // 静默失败，不阻断页面
    loaded.value = false
  }
}

function onNext() {
  if (nextAction.value?.route) {
    router.push(nextAction.value.route)
  }
}

onMounted(fetchStatus)

watch(() => [props.projectId, props.year], fetchStatus)
</script>

<style scoped>
.workflow-progress {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 16px;
  background: #f8f7fc;
  border-radius: 8px;
  margin-bottom: 12px;
}

.workflow-progress__steps {
  flex: 1;
}

.workflow-progress__next-btn {
  flex-shrink: 0;
}
</style>
