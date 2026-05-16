<template>
  <div class="workflow-progress" v-if="loaded">
    <div class="workflow-progress__steps">
      <template v-for="(step, idx) in steps" :key="step.key">
        <span
          class="wf-step"
          :class="{
            'wf-step--done': idx < currentStep,
            'wf-step--active': idx === currentStep,
            'wf-step--future': idx > currentStep,
          }"
          @click="onStepClick(step)"
        >
          <span class="wf-step__icon">{{ idx < currentStep ? '✓' : (idx + 1) }}</span>
          <span class="wf-step__label">{{ step.label }}</span>
        </span>
        <span v-if="idx < steps.length - 1" class="wf-step__connector" :class="{ 'wf-connector--done': idx < currentStep }"></span>
      </template>
    </div>
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

// 步骤定义：每步对应一个路由或动作
const steps = [
  { key: 'import', label: '导入', route: (pid: string) => `/projects/${pid}/trial-balance`, action: 'import' },
  { key: 'mapping', label: '映射', route: (pid: string) => `/projects/${pid}/trial-balance`, action: 'mapping' },
  { key: 'trial_balance', label: '试算表', route: (pid: string) => `/projects/${pid}/trial-balance` },
  { key: 'reports', label: '报表', route: (pid: string) => `/projects/${pid}/reports` },
  { key: 'workpapers', label: '底稿', route: (pid: string) => `/projects/${pid}/workpapers` },
  { key: 'notes', label: '附注', route: (pid: string) => `/projects/${pid}/disclosure-notes` },
]

async function fetchStatus() {
  if (!props.projectId) return
  try {
    const yr = props.year || 2025
    const res = await api.get(`/api/projects/${props.projectId}/workflow-status?year=${yr}`) as WorkflowStatusResponse
    currentStep.value = res.current_step
    nextAction.value = res.next_action
    loaded.value = true
  } catch {
    // 静默失败，不阻断页面
    loaded.value = true
    currentStep.value = 2 // 默认在试算表步骤
  }
}

const emit = defineEmits<{ (e: 'step-action', action: string): void }>()

function onStepClick(step: typeof steps[number]) {
  if (!props.projectId) return
  // 特殊动作：不跳转，通知父组件
  if ((step as any).action) {
    emit('step-action', (step as any).action)
    return
  }
  router.push(step.route(props.projectId))
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
  gap: 12px;
  padding: 10px 20px;
  background: linear-gradient(135deg, #f8f7fc 0%, #f0edf5 100%);
  border: 1px solid #e8e0f0;
  border-radius: 8px;
  margin-bottom: 12px;
}

.workflow-progress__steps {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 0;
}

.workflow-progress__next-btn {
  flex-shrink: 0;
}

.wf-step {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 6px 12px;
  border-radius: 16px;
  transition: all 0.2s;
  font-size: var(--gt-font-size-sm);
  user-select: none;
  white-space: nowrap;
}
.wf-step:hover { background: rgba(75, 45, 119, 0.08); }

.wf-step__icon {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
  flex-shrink: 0;
  transition: all 0.2s;
}

.wf-step--done .wf-step__icon { background: var(--gt-color-success-light); color: var(--gt-color-success); }
.wf-step--done .wf-step__label { color: var(--gt-color-success); font-weight: 500; }
.wf-step--done:hover .wf-step__icon { background: var(--gt-color-success-light); }

.wf-step--active .wf-step__icon { background: #4b2d77; color: #fff; box-shadow: 0 2px 6px rgba(75,45,119,0.3); }
.wf-step--active .wf-step__label { color: var(--gt-color-primary); font-weight: 600; }
.wf-step--active { background: rgba(75, 45, 119, 0.06); }

.wf-step--future .wf-step__icon { background: var(--gt-color-primary-bg); color: var(--gt-color-primary-lighter); border: 1px solid #e0dce8; }
.wf-step--future .wf-step__label { color: var(--gt-color-primary-lighter); }
.wf-step--future:hover .wf-step__icon { background: var(--gt-color-border-light); color: var(--gt-color-primary-light); }
.wf-step--future:hover .wf-step__label { color: var(--gt-color-primary-light); }

.wf-step__label {
  font-size: var(--gt-font-size-sm);
  letter-spacing: 0.3px;
}

.wf-step__connector {
  width: 24px;
  height: 1px;
  background: var(--gt-color-primary-lighter);
  margin: 0 2px;
  flex-shrink: 0;
}
.wf-step--done + .wf-step__connector,
.wf-connector--done { background: var(--gt-color-success); }
</style>
